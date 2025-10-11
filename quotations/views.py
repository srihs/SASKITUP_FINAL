"""
Quotation views for SASKITUP project.

This module provides comprehensive quotation workflow views:
1. Institution Selection - User selects school/club
2. Product Listing - Browse products for selected institution
3. Quotation Cart - Manage quotation items
4. Save Quotation - Convert session to database record
5. My Quotations - View user's quotations
"""

from decimal import Decimal
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Prefetch
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, DetailView, FormView
from django.core.exceptions import PermissionDenied, ValidationError
import logging

from authentication.permissions import (
    SalesRepOrAccountManagerMixin,
    CustomerRequiredMixin,
)
from authentication.models import User, SalesRepSchoolAssignment, SalesRepClubAssignment, AuditLog
from schools.models import School, WholesaleSchool, WholesaleProduct, WholesaleProductVariation
from schools.models_tus import TUSProductVariation
from clubs.models_lotto import LottoClub, LottoProduct
from clubs.models_sas import SASClub, SASProduct
from .models import Quotation, QuotationItem, CustomerInstitutionAssignment

logger = logging.getLogger(__name__)


# =====================================
# HELPER FUNCTIONS & UTILITIES
# =====================================

def get_quotation_session(request):
    """Get or create quotation session data"""
    if 'quotation' not in request.session:
        request.session['quotation'] = {
            'items': [],  # List of quotation items
            'institution_type': None,  # 'school', 'wholesaleschool', 'lottoclub', 'sasclub'
            'institution_id': None,
        }
    return request.session['quotation']


def save_quotation_session(request, quotation_data):
    """Save quotation data to session"""
    request.session['quotation'] = quotation_data
    request.session.modified = True


def clear_quotation_session(request):
    """Clear quotation session data"""
    if 'quotation' in request.session:
        del request.session['quotation']
    request.session.modified = True


def calculate_quotation_totals(quotation_data):
    """Calculate totals for quotation session data"""
    subtotal = Decimal('0.00')
    tax_percentage = Decimal('15.00')  # 15% VAT

    for item in quotation_data.get('items', []):
        line_total = Decimal(str(item['unit_price'])) * Decimal(str(item['quantity']))
        subtotal += line_total

    tax_amount = (subtotal * tax_percentage / Decimal('100')).quantize(Decimal('0.01'))
    total = (subtotal + tax_amount).quantize(Decimal('0.01'))

    return {
        'subtotal': subtotal,
        'tax_percentage': tax_percentage,
        'tax_amount': tax_amount,
        'total': total,
        'item_count': len(quotation_data.get('items', [])),
    }


def get_product_by_type_and_id(product_type, product_id):
    """Get product object by type and ID"""
    from schools.models_tus import TUSProduct

    product_models = {
        'tusproduct': TUSProduct,
        'wholesaleproduct': WholesaleProduct,
        'lottoproduct': LottoProduct,
        'sasproduct': SASProduct,
    }

    model_class = product_models.get(product_type.lower())
    if not model_class:
        return None

    try:
        return model_class.objects.get(pk=product_id)
    except model_class.DoesNotExist:
        return None


def get_product_by_type_and_slug(product_type, product_slug):
    """Get product object by type and slug"""
    from schools.models_tus import TUSProduct

    product_models = {
        'tusproduct': TUSProduct,
        'wholesaleproduct': WholesaleProduct,
        'lottoproduct': LottoProduct,
        'sasproduct': SASProduct,
    }

    model_class = product_models.get(product_type.lower())
    if not model_class:
        return None

    try:
        return model_class.objects.get(slug=product_slug)
    except model_class.DoesNotExist:
        return None


def user_can_access_institution(user, institution_type, institution_id):
    """Check if user can access the specified institution"""
    from schools.models_tus import TUSSchool

    # Admin and account managers can access all institutions
    if user.is_admin or user.is_account_manager:
        return True

    # Map institution type to model
    institution_models = {
        'tusschool': TUSSchool,
        'wholesaleschool': WholesaleSchool,
        'lottoclub': LottoClub,
        'sasclub': SASClub,
    }

    model_class = institution_models.get(institution_type.lower())
    if not model_class:
        return False

    try:
        institution = model_class.objects.get(pk=institution_id)
    except model_class.DoesNotExist:
        return False

    # Check access based on user type
    if user.is_sales_rep:
        # Check TUS school assignments (direct FK)
        if institution_type.lower() == 'tusschool':
            return SalesRepSchoolAssignment.objects.filter(
                sales_rep=user,
                is_active=True,
                tus_school=institution
            ).exists()
        # Check wholesale school assignments
        elif institution_type.lower() == 'wholesaleschool':
            return SalesRepSchoolAssignment.objects.filter(
                sales_rep=user,
                is_active=True,
                wholesale_school=institution
            ).exists()
        # Check club assignments
        elif institution_type.lower() in ['lottoclub', 'sasclub']:
            content_type = ContentType.objects.get_for_model(institution)
            return SalesRepClubAssignment.objects.filter(
                sales_rep=user,
                is_active=True,
                club_content_type=content_type,
                club_object_id=institution.id
            ).exists()

    elif user.is_customer:
        # Check customer institution assignments (direct GenericForeignKey)
        content_type = ContentType.objects.get_for_model(institution)
        return CustomerInstitutionAssignment.objects.filter(
            customer=user,
            is_active=True,
            institution_content_type=content_type,
            institution_object_id=institution.id
        ).exists()

    return False


def get_user_institutions(user):
    """
    Get all institutions accessible by the user, grouped by type.
    Returns dict with keys: tus_schools, wholesale_schools, lotto_clubs, sas_clubs
    """
    from schools.models_tus import TUSSchool

    institutions = {
        'tus_schools': [],
        'wholesale_schools': [],
        'lotto_clubs': [],
        'sas_clubs': [],
    }

    # Admin and account managers get all institutions
    if user.is_admin or user.is_account_manager:
        # Get all active TUS schools
        institutions['tus_schools'] = TUSSchool.objects.filter(is_active=True).select_related('location').order_by('name')
        institutions['wholesale_schools'] = WholesaleSchool.objects.filter(is_active=True).order_by('name')
        institutions['lotto_clubs'] = LottoClub.objects.filter(is_active=True).order_by('name')
        institutions['sas_clubs'] = SASClub.objects.filter(is_active=True).order_by('name')
        return institutions

    # Sales reps get assigned institutions
    if user.is_sales_rep:
        # Get school assignments
        school_assignments = SalesRepSchoolAssignment.objects.filter(
            sales_rep=user,
            is_active=True
        ).select_related('tus_school', 'tus_school__location', 'wholesale_school')

        for assignment in school_assignments:
            if assignment.tus_school:
                institutions['tus_schools'].append(assignment.tus_school)
            elif assignment.wholesale_school:
                institutions['wholesale_schools'].append(assignment.wholesale_school)

        # Get club assignments
        club_assignments = SalesRepClubAssignment.objects.filter(
            sales_rep=user,
            is_active=True
        ).select_related('club_content_type')

        for assignment in club_assignments:
            if assignment.club:
                if isinstance(assignment.club, LottoClub):
                    institutions['lotto_clubs'].append(assignment.club)
                elif isinstance(assignment.club, SASClub):
                    institutions['sas_clubs'].append(assignment.club)

    # Customers get assigned institutions
    elif user.is_customer:
        customer_assignments = CustomerInstitutionAssignment.objects.filter(
            customer=user,
            is_active=True
        ).select_related('institution_content_type')

        for assignment in customer_assignments:
            if assignment.institution:
                if isinstance(assignment.institution, TUSSchool):
                    institutions['tus_schools'].append(assignment.institution)
                elif isinstance(assignment.institution, WholesaleSchool):
                    institutions['wholesale_schools'].append(assignment.institution)
                elif isinstance(assignment.institution, LottoClub):
                    institutions['lotto_clubs'].append(assignment.institution)
                elif isinstance(assignment.institution, SASClub):
                    institutions['sas_clubs'].append(assignment.institution)

    return institutions


# =====================================
# STEP 1: INSTITUTION SELECTION
# =====================================

class InstitutionSelectionView(LoginRequiredMixin, View):
    """
    Step 1: Display institutions accessible by the user.
    User selects institution to create quotation for.
    """
    template_name = 'quotations/select_institution.html'

    def get(self, request):
        # Get user's accessible institutions
        institutions = get_user_institutions(request.user)

        # Count total institutions
        total_count = (
            len(institutions['tus_schools']) +
            len(institutions['wholesale_schools']) +
            len(institutions['lotto_clubs']) +
            len(institutions['sas_clubs'])
        )

        # Log access
        AuditLog.log_action(
            user=request.user,
            action_type='data_access',
            description='Viewed institution selection for quotation',
            request=request,
            institution_count=total_count
        )

        context = {
            'tus_schools': institutions.get('tus_schools', []),
            'wholesale_schools': [{'school': school} for school in institutions.get('wholesale_schools', [])],
            'lotto_clubs': [{'club': club} for club in institutions.get('lotto_clubs', [])],
            'sas_clubs': [{'club': club} for club in institutions.get('sas_clubs', [])],
            'total_count': total_count,
        }

        return render(request, self.template_name, context)


# =====================================
# STEP 2: PRODUCT LISTING
# =====================================

class ProductListingView(LoginRequiredMixin, View):
    """
    Step 2: Display products for selected institution.
    Products shown based on institution type.
    """
    template_name = 'quotations/product_listing.html'
    items_per_page = 20

    def get(self, request, institution_type, institution_slug):
        # Get institution object first
        institution = self.get_institution(institution_type, institution_slug)

        # Verify user has access to institution
        if not user_can_access_institution(request.user, institution_type, institution.id):
            AuditLog.log_action(
                user=request.user,
                action_type='permission_denied',
                description=f'Attempted to access institution {institution_type}/{institution_slug} without permission',
                request=request,
                institution_type=institution_type,
                institution_slug=institution_slug
            )
            raise PermissionDenied("You don't have permission to access this institution")

        # Get products based on institution type
        products = self.get_products_for_institution(institution_type, institution.id)

        # Apply search/filter
        search_query = request.GET.get('search', '')
        if search_query:
            products = products.filter(
                Q(name__icontains=search_query) |
                Q(cin7_sku__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        # Pagination
        paginator = Paginator(products, self.items_per_page)
        page = request.GET.get('page', 1)

        try:
            products_page = paginator.page(page)
        except PageNotAnInteger:
            products_page = paginator.page(1)
        except EmptyPage:
            products_page = paginator.page(paginator.num_pages)

        # Get current quotation count
        quotation_data = get_quotation_session(request)
        totals = calculate_quotation_totals(quotation_data)

        # Update quotation session with institution
        quotation_data['institution_type'] = institution_type
        quotation_data['institution_id'] = institution.id
        quotation_data['institution_slug'] = institution_slug
        save_quotation_session(request, quotation_data)

        # Log access
        AuditLog.log_action(
            user=request.user,
            action_type='data_access',
            description=f'Viewed product listing for {institution_type} {institution_slug}',
            request=request,
            institution_type=institution_type,
            institution_slug=institution_slug,
            search_query=search_query
        )

        context = {
            'institution': institution,
            'institution_type': institution_type,
            'institution_slug': institution_slug,
            'products': products_page,
            'search_query': search_query,
            'quotation_item_count': totals['item_count'],
        }

        return render(request, self.template_name, context)

    def get_institution(self, institution_type, institution_slug):
        """Get institution object by type and slug"""
        from schools.models_tus import TUSSchool, TUSProduct

        institution_models = {
            'tusschool': TUSSchool,
            'wholesaleschool': WholesaleSchool,
            'lottoclub': LottoClub,
            'sasclub': SASClub,
        }

        model_class = institution_models.get(institution_type.lower())
        if not model_class:
            raise PermissionDenied("Invalid institution type")

        return get_object_or_404(model_class, slug=institution_slug)

    def get_products_for_institution(self, institution_type, institution_id):
        """Get products based on institution type"""
        from schools.models_tus import TUSSchool, TUSProduct

        # TUSSchool → TUSProduct (products linked to school via categories)
        if institution_type.lower() == 'tusschool':
            tus_school = get_object_or_404(TUSSchool, pk=institution_id)
            return TUSProduct.objects.filter(
                category_assignments__school_category__school=tus_school,
                stock_status__in=['instock', 'onbackorder']
            ).distinct().order_by('name')

        # WholesaleSchool → WholesaleProduct
        elif institution_type.lower() == 'wholesaleschool':
            return WholesaleProduct.objects.filter(
                is_active=True
            ).select_related('school').order_by('name')

        # LottoClub → LottoProduct
        elif institution_type.lower() == 'lottoclub':
            return LottoProduct.objects.filter(
                is_active=True
            ).order_by('name')

        # SASClub → SASProduct
        elif institution_type.lower() == 'sasclub':
            return SASProduct.objects.filter(
                is_active=True
            ).order_by('name')

        return []


# =====================================
# STEP 3: QUOTATION CART VIEW
# =====================================

class QuotationCartView(LoginRequiredMixin, View):
    """
    Step 3: Display quotation cart with all items.
    User can adjust quantities, remove items, or save quotation.
    Supports both authenticated and guest users via session storage.
    """
    template_name = 'quotations/quotation_cart.html'

    def get(self, request):
        quotation_data = get_quotation_session(request)

        # Enrich items with product details
        enriched_items = []
        total_savings = Decimal('0.00')

        for idx, item in enumerate(quotation_data.get('items', [])):
            product = get_product_by_type_and_id(item['product_type'], item['product_id'])
            if product:
                enriched_item = item.copy()
                enriched_item['product'] = product
                enriched_item['index'] = idx  # Add index for update/remove operations
                enriched_item['line_total'] = Decimal(str(item['unit_price'])) * Decimal(str(item['quantity']))

                # Add pricing information for discount display
                margin_price = None
                unit_price_decimal = Decimal(str(item['unit_price']))

                # Check if item has variation data with variation_id
                variation_obj = None
                if item.get('variations') and item['variations'].get('variation_id'):
                    variation_id = item['variations']['variation_id']
                    product_type = item['product_type'].lower()

                    # Get the appropriate variation model based on product type
                    try:
                        if product_type == 'tusproduct':
                            from schools.models_tus import TUSProductVariation
                            variation_obj = TUSProductVariation.objects.get(pk=variation_id)
                        elif product_type == 'wholesaleproduct':
                            variation_obj = WholesaleProductVariation.objects.get(pk=variation_id)
                        elif product_type == 'sasproduct':
                            from clubs.models_sas import SASProductVariation
                            variation_obj = SASProductVariation.objects.get(pk=variation_id)
                        elif product_type == 'lottoproduct':
                            from clubs.models_lotto import LottoProductVariation
                            variation_obj = LottoProductVariation.objects.get(pk=variation_id)
                    except Exception as e:
                        logger.warning(f"Could not fetch variation {variation_id} for {product_type}: {e}")
                        variation_obj = None

                # If we have a variation object, ensure we're using the variation's price
                # This handles both new items (with price in variations dict) and legacy items
                if variation_obj:
                    variation_price = getattr(variation_obj, 'price', None) or getattr(variation_obj, 'wholesale_price', None)
                    if variation_price:
                        unit_price_decimal = Decimal(str(variation_price))
                        enriched_item['unit_price'] = str(variation_price)
                        enriched_item['line_total'] = unit_price_decimal * Decimal(str(item['quantity']))

                # Try to get margin_75_price from variation first, then fall back to product
                # Priority: variation.margin_75_price > product.margin_75_price > calculated > retail > regular

                # Check variation first if it exists
                if variation_obj and hasattr(variation_obj, 'margin_75_price') and variation_obj.margin_75_price:
                    margin_price = variation_obj.margin_75_price
                # Fall back to product's margin_75_price
                elif hasattr(product, 'margin_75_price') and product.margin_75_price:
                    margin_price = product.margin_75_price
                # Try to calculate from variation's cost_price
                elif variation_obj and hasattr(variation_obj, 'cost_price') and variation_obj.cost_price and variation_obj.cost_price > 0:
                    calculated_margin = (variation_obj.cost_price / Decimal('0.25')).quantize(Decimal('0.01'))
                    if calculated_margin > unit_price_decimal:
                        margin_price = calculated_margin
                # Try to calculate from product's cost_price
                elif hasattr(product, 'cost_price') and product.cost_price and product.cost_price > 0:
                    calculated_margin = (product.cost_price / Decimal('0.25')).quantize(Decimal('0.01'))
                    if calculated_margin > unit_price_decimal:
                        margin_price = calculated_margin
                # For variations with retail_price
                elif variation_obj and hasattr(variation_obj, 'retail_price') and variation_obj.retail_price and variation_obj.retail_price > 0:
                    if variation_obj.retail_price > unit_price_decimal:
                        margin_price = variation_obj.retail_price
                # For products with retail_price
                elif hasattr(product, 'retail_price') and product.retail_price and product.retail_price > 0:
                    if product.retail_price > unit_price_decimal:
                        margin_price = product.retail_price
                # For variations with regular_price
                elif variation_obj and hasattr(variation_obj, 'regular_price') and variation_obj.regular_price and variation_obj.regular_price > 0:
                    if variation_obj.regular_price > unit_price_decimal:
                        margin_price = variation_obj.regular_price
                # For products with regular_price
                elif hasattr(product, 'regular_price') and product.regular_price and product.regular_price > 0:
                    if product.regular_price > unit_price_decimal:
                        margin_price = product.regular_price

                # Only set margin_75_price if we found a valid margin price greater than unit price
                if margin_price and margin_price > unit_price_decimal:
                    enriched_item['margin_75_price'] = margin_price
                    item_savings = (margin_price - unit_price_decimal) * Decimal(str(item['quantity']))
                    total_savings += item_savings
                    enriched_item['item_discount'] = item_savings
                else:
                    enriched_item['item_discount'] = Decimal('0.00')

                # Get discount_percentage from variation first, then product
                if variation_obj and hasattr(variation_obj, 'discount_percentage') and variation_obj.discount_percentage:
                    enriched_item['discount_percentage'] = variation_obj.discount_percentage
                elif hasattr(product, 'discount_percentage') and product.discount_percentage:
                    enriched_item['discount_percentage'] = product.discount_percentage

                # Add variation display info if variations exist
                if item.get('variations'):
                    variation_details = {}
                    if item['variations'].get('size'):
                        variation_details['size'] = item['variations']['size']
                    if item['variations'].get('color'):
                        variation_details['color'] = item['variations']['color']
                    enriched_item['variation_details'] = variation_details

                enriched_items.append(enriched_item)

        # Calculate totals
        totals = calculate_quotation_totals(quotation_data)

        # Get institution if set
        institution = None
        institution_type = quotation_data.get('institution_type')
        institution_slug = quotation_data.get('institution_slug')

        if institution_type and quotation_data.get('institution_id'):
            from schools.models_tus import TUSSchool

            institution_models = {
                'tusschool': TUSSchool,
                'wholesaleschool': WholesaleSchool,
                'lottoclub': LottoClub,
                'sasclub': SASClub,
            }
            model_class = institution_models.get(institution_type.lower())
            if model_class:
                try:
                    institution = model_class.objects.get(pk=quotation_data['institution_id'])
                except model_class.DoesNotExist:
                    pass

        # Log access
        AuditLog.log_action(
            user=request.user,
            action_type='data_access',
            description=f'Viewed quotation cart with {len(enriched_items)} items',
            request=request,
            item_count=len(enriched_items)
        )

        context = {
            'cart_items': enriched_items,  # Changed from 'items' to match template
            'subtotal': totals['subtotal'],
            'tax': totals['tax_amount'],
            'total': totals['total'],
            'total_savings': total_savings,
            'institution': institution,
            'institution_type': institution_type,
            'institution_slug': institution_slug,
        }

        return render(request, self.template_name, context)


# =====================================
# AJAX ENDPOINTS
# =====================================

class AddToQuotationView(LoginRequiredMixin, View):
    """AJAX endpoint to add product to quotation"""

    def post(self, request):
        try:
            import json

            product_type = request.POST.get('product_type')
            product_id = int(request.POST.get('product_id'))
            quantity = int(request.POST.get('quantity', 1))

            # Get variation data if provided
            variations_json = request.POST.get('variations', '{}')
            try:
                variations = json.loads(variations_json)
            except json.JSONDecodeError:
                variations = {}

            # Get product
            product = get_product_by_type_and_id(product_type, product_id)
            if not product:
                return JsonResponse({'success': False, 'error': 'Product not found'}, status=404)

            # BUSINESS RULE ENFORCEMENT: Stock quantity validation
            stock_qty = variations.get('stock_quantity', 0)

            # Rule 1: Cannot order out-of-stock items
            if stock_qty == 0:
                return JsonResponse({
                    'success': False,
                    'error': 'This item is out of stock and cannot be added to your quote.'
                }, status=400)

            # Get quotation session
            quotation_data = get_quotation_session(request)

            # Check if item with same variation already exists
            existing_item = None
            for item in quotation_data['items']:
                if (item['product_type'] == product_type and
                    item['product_id'] == product_id and
                    item.get('variations', {}) == variations):
                    existing_item = item
                    break

            if existing_item:
                # Update quantity for existing variation
                new_quantity = existing_item['quantity'] + quantity

                # Rule 2: Cannot order more than stock quantity
                if stock_qty > 0 and new_quantity > stock_qty:
                    return JsonResponse({
                        'success': False,
                        'error': f'Cannot add {quantity} more. Only {stock_qty - existing_item["quantity"]} units available (stock limit: {stock_qty}).'
                    }, status=400)

                existing_item['quantity'] = new_quantity
            else:
                # Rule 2: Cannot order more than stock quantity (for new items)
                if stock_qty > 0 and quantity > stock_qty:
                    return JsonResponse({
                        'success': False,
                        'error': f'Cannot add {quantity} units. Only {stock_qty} units available in stock.'
                    }, status=400)

                # Add new item with variation
                product_name = product.name
                product_sku = getattr(product, 'cin7_sku', '') or getattr(product, 'sku', '')

                # If variation has SKU, use that instead
                if variations.get('sku'):
                    product_sku = variations.get('sku')

                # If variation has size, append to product name
                if variations.get('size'):
                    product_name = f"{product.name} - {variations.get('size')}"
                    if variations.get('color'):
                        product_name = f"{product.name} - {variations.get('color')} - {variations.get('size')}"

                # Use variation price if available, otherwise fall back to product price
                unit_price = variations.get('price') or str(getattr(product, 'wholesale_price', None) or getattr(product, 'price', 0))

                quotation_data['items'].append({
                    'product_type': product_type,
                    'product_id': product_id,
                    'product_name': product_name,
                    'product_sku': product_sku,
                    'quantity': quantity,
                    'unit_price': str(unit_price),
                    'variations': variations,
                })

            # Save session
            save_quotation_session(request, quotation_data)

            # Calculate totals
            totals = calculate_quotation_totals(quotation_data)

            # Log action
            variation_info = f" ({variations.get('size', '')})" if variations.get('size') else ""
            AuditLog.log_action(
                user=request.user,
                action_type='data_access',
                description=f'Added {product.name}{variation_info} to quotation',
                request=request,
                product_type=product_type,
                product_id=product_id,
                quantity=quantity
            )

            return JsonResponse({
                'success': True,
                'item_count': totals['item_count'],
                'subtotal': str(totals['subtotal']),
                'total': str(totals['total']),
            })

        except Exception as e:
            logger.error(f"Error adding to quotation: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class UpdateQuotationItemView(LoginRequiredMixin, View):
    """AJAX endpoint to update quotation item quantity"""

    def post(self, request):
        try:
            item_index = int(request.POST.get('item_index'))
            quantity = int(request.POST.get('quantity'))

            if quantity < 1:
                return JsonResponse({'success': False, 'error': 'Quantity must be at least 1'}, status=400)

            quotation_data = get_quotation_session(request)

            if item_index < 0 or item_index >= len(quotation_data['items']):
                return JsonResponse({'success': False, 'error': 'Invalid item index'}, status=400)

            # Get the item to check stock limits
            item = quotation_data['items'][item_index]

            # BUSINESS RULE ENFORCEMENT: Stock quantity validation
            stock_qty = item.get('variations', {}).get('stock_quantity', 0)

            # Rule 1: Cannot order more than stock quantity
            if stock_qty > 0 and quantity > stock_qty:
                return JsonResponse({
                    'success': False,
                    'error': f'Cannot set quantity to {quantity}. Only {stock_qty} units available in stock.'
                }, status=400)

            # Update quantity
            quotation_data['items'][item_index]['quantity'] = quantity

            # Save session
            save_quotation_session(request, quotation_data)

            # Calculate totals
            totals = calculate_quotation_totals(quotation_data)

            # Calculate line total
            line_total = Decimal(str(item['unit_price'])) * Decimal(str(quantity))

            # Log action
            AuditLog.log_action(
                user=request.user,
                action_type='data_modification',
                description=f'Updated quotation item quantity to {quantity}',
                request=request,
                item_index=item_index,
                quantity=quantity
            )

            return JsonResponse({
                'success': True,
                'line_total': str(line_total),
                'item_total': str(line_total),  # Alternative key for compatibility
                'subtotal': str(totals['subtotal']),
                'tax': str(totals['tax_amount']),
                'tax_amount': str(totals['tax_amount']),
                'total': str(totals['total']),
            })

        except ValueError as e:
            logger.error(f"Invalid input in update quotation item: {e}")
            return JsonResponse({'success': False, 'error': 'Invalid input values'}, status=400)
        except Exception as e:
            logger.error(f"Error updating quotation item: {e}")
            return JsonResponse({'success': False, 'error': 'An error occurred while updating the item'}, status=500)


class RemoveQuotationItemView(LoginRequiredMixin, View):
    """AJAX endpoint to remove item from quotation"""

    def post(self, request):
        try:
            item_index = int(request.POST.get('item_index'))

            quotation_data = get_quotation_session(request)

            if item_index < 0 or item_index >= len(quotation_data['items']):
                return JsonResponse({'success': False, 'error': 'Invalid item index'}, status=400)

            # Remove item
            removed_item = quotation_data['items'].pop(item_index)

            # Save session
            save_quotation_session(request, quotation_data)

            # Calculate totals
            totals = calculate_quotation_totals(quotation_data)

            # Log action
            AuditLog.log_action(
                user=request.user,
                action_type='data_modification',
                description=f'Removed {removed_item["product_name"]} from quotation',
                request=request,
                product_name=removed_item['product_name']
            )

            return JsonResponse({
                'success': True,
                'item_count': totals['item_count'],
                'subtotal': str(totals['subtotal']),
                'tax': str(totals['tax_amount']),
                'tax_amount': str(totals['tax_amount']),
                'total': str(totals['total']),
                'message': f'Removed {removed_item["product_name"]} from cart'
            })

        except ValueError as e:
            logger.error(f"Invalid input in remove quotation item: {e}")
            return JsonResponse({'success': False, 'error': 'Invalid item index'}, status=400)
        except Exception as e:
            logger.error(f"Error removing quotation item: {e}")
            return JsonResponse({'success': False, 'error': 'An error occurred while removing the item'}, status=500)


class ClearQuotationView(LoginRequiredMixin, View):
    """AJAX endpoint to clear all quotation items"""

    def post(self, request):
        try:
            clear_quotation_session(request)

            # Log action
            AuditLog.log_action(
                user=request.user,
                action_type='data_access',
                description='Cleared quotation cart',
                request=request
            )

            return JsonResponse({'success': True})

        except Exception as e:
            logger.error(f"Error clearing quotation: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================================
# STEP 4: SAVE QUOTATION
# =====================================

class SaveQuotationView(LoginRequiredMixin, View):
    """
    Step 4: Save quotation session to database.
    Creates Quotation and QuotationItem records.
    Handles both authenticated users and validates institution access.
    """

    def post(self, request):
        try:
            quotation_data = get_quotation_session(request)

            # Validate quotation has items
            if not quotation_data.get('items'):
                return JsonResponse({
                    'success': False,
                    'error': 'Your quotation cart is empty. Please add items before submitting.'
                }, status=400)

            # Validate institution is set
            if not quotation_data.get('institution_type') or not quotation_data.get('institution_id'):
                return JsonResponse({
                    'success': False,
                    'error': 'No institution selected. Please select an institution before submitting your quotation.'
                }, status=400)

            # Get institution
            from schools.models_tus import TUSSchool

            institution_models = {
                'tusschool': TUSSchool,
                'wholesaleschool': WholesaleSchool,
                'lottoclub': LottoClub,
                'sasclub': SASClub,
            }
            model_class = institution_models.get(quotation_data['institution_type'].lower())
            if not model_class:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid institution type'
                }, status=400)

            try:
                institution = model_class.objects.get(pk=quotation_data['institution_id'])
            except model_class.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Institution not found'
                }, status=404)

            # Verify user has access to this institution
            if not user_can_access_institution(request.user, quotation_data['institution_type'], quotation_data['institution_id']):
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to create quotations for this institution'
                }, status=403)

            # Create Quotation
            institution_content_type = ContentType.objects.get_for_model(institution)
            quotation = Quotation.objects.create(
                created_by=request.user,
                institution_content_type=institution_content_type,
                institution_object_id=institution.id,
                status='pending',  # Changed from 'draft' to 'pending' for approval workflow
            )

            # Create QuotationItems
            items_created = 0
            for item_data in quotation_data['items']:
                product = get_product_by_type_and_id(item_data['product_type'], item_data['product_id'])
                if not product:
                    logger.warning(f"Product not found: {item_data['product_type']} {item_data['product_id']}")
                    continue

                product_content_type = ContentType.objects.get_for_model(product)

                # Get product image URL
                product_image_url = ''
                if hasattr(product, 'image_url') and product.image_url:
                    product_image_url = product.image_url
                elif hasattr(product, 'image') and product.image:
                    product_image_url = str(product.image)

                QuotationItem.objects.create(
                    quotation=quotation,
                    product_content_type=product_content_type,
                    product_object_id=product.id,
                    product_name=item_data.get('product_name', product.name),
                    product_sku=item_data.get('product_sku', getattr(product, 'cin7_sku', '') or getattr(product, 'sku', '')),
                    product_image_url=product_image_url,
                    quantity=item_data['quantity'],
                    unit_price=Decimal(str(item_data['unit_price'])),
                    variations=item_data.get('variations', {}),
                )
                items_created += 1

            if items_created == 0:
                quotation.delete()
                return JsonResponse({
                    'success': False,
                    'error': 'No valid products found in your cart. Please try again.'
                }, status=400)

            # Calculate quotation totals
            quotation.calculate_totals()

            # Clear session
            clear_quotation_session(request)

            # Log action
            AuditLog.log_action(
                user=request.user,
                action_type='data_creation',
                description=f'Created quotation {quotation.quotation_number} with {items_created} items',
                request=request,
                quotation_id=str(quotation.id),
                quotation_number=quotation.quotation_number,
                item_count=items_created
            )

            return JsonResponse({
                'success': True,
                'quotation_id': str(quotation.id),
                'quotation_number': quotation.quotation_number,
                'item_count': items_created,
                'total_amount': str(quotation.total),
                'redirect_url': reverse('quotations:my-quotations'),
                'message': f'Quotation {quotation.quotation_number} submitted successfully!'
            })

        except ValidationError as e:
            logger.error(f"Validation error saving quotation: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
        except Exception as e:
            logger.error(f"Error saving quotation: {e}")
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while saving your quotation. Please try again.'
            }, status=500)


# =====================================
# STEP 5: MY QUOTATIONS LIST
# =====================================

class MyQuotationsListView(LoginRequiredMixin, ListView):
    """
    Step 5: Display user's quotations.
    List all quotations created by the user.
    """
    model = Quotation
    template_name = 'quotations/my_quotations.html'
    context_object_name = 'quotations'
    paginate_by = 20

    def get_queryset(self):
        """Get quotations for current user"""
        queryset = Quotation.objects.filter(
            created_by=self.request.user
        ).select_related(
            'institution_content_type',
            'created_by',
            'approved_by',
            'rejected_by'
        ).prefetch_related('items')

        # Apply filters
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        # Date range filter
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)

        # Search by quotation number
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(quotation_number__icontains=search_query)

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Quotation.STATUS_CHOICES
        context['current_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('search', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        return context


# =====================================
# QUOTATION DETAIL VIEW
# =====================================

class QuotationDetailView(LoginRequiredMixin, DetailView):
    """View quotation details"""
    model = Quotation
    template_name = 'quotations/quotation_detail.html'
    context_object_name = 'quotation'

    def get_queryset(self):
        """Ensure user can only view their own quotations (or all if admin/account manager)"""
        if self.request.user.is_admin or self.request.user.is_account_manager:
            return Quotation.objects.all()
        return Quotation.objects.filter(created_by=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.all().select_related('product_content_type')
        return context


# =====================================
# NEW QUOTATION PAGE - TAB-BASED PRODUCT SELECTION
# =====================================

class ProductDetailForQuotationView(LoginRequiredMixin, SalesRepOrAccountManagerMixin, DetailView):
    """
    Product detail page for quotation system.
    Shows product details, variations, and allows adding to quote.
    """
    template_name = 'quotations/product_detail.html'
    context_object_name = 'product'

    def get_object(self):
        product_type = self.kwargs.get('product_type')
        product_slug = self.kwargs.get('product_slug')

        # Get product by type and slug
        product = get_product_by_type_and_slug(product_type, product_slug)
        if not product:
            raise PermissionDenied("Product not found")
        return product

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        product_type = self.kwargs.get('product_type')

        # Add product type for variation fetching
        context['product_type'] = product_type

        # Add permission flag for cost price alerts (visible to admins, sales reps, account managers)
        context['can_view_cost_price_alerts'] = (
            self.request.user.is_admin or
            self.request.user.is_sales_rep or
            self.request.user.is_account_manager
        )

        # Add institution name
        context['institution_name'] = self._get_institution_name(product, product_type)

        # Determine active tab based on product type
        if product_type.lower() in ['tusproduct', 'wholesaleproduct']:
            context['active_tab'] = 'schools'
        else:
            context['active_tab'] = 'clubs'

        # Get quotation summary from session
        quotation_data = get_quotation_session(self.request)
        totals = calculate_quotation_totals(quotation_data)
        context['quotation_item_count'] = totals['item_count']
        context['quotation_total'] = totals['total']

        # Get product variations if available
        variations = []
        if hasattr(product, 'variations'):
            variations_qs = product.variations.filter(is_active=True) if hasattr(product.variations, 'filter') else product.variations.all()
            for variation in variations_qs:
                # Get price and convert Decimal to string
                price = getattr(variation, 'price', None) or getattr(variation, 'wholesale_price', None)
                price_str = str(price) if price is not None else None

                var_data = {
                    'id': variation.id,
                    'variation_type': getattr(variation, 'variation_type', ''),
                    'variation_value': getattr(variation, 'variation_value', ''),
                    'stock_quantity': getattr(variation, 'stock_quantity', 0) or getattr(variation, 'quantity_available', 0),
                    'price': price_str,
                }
                # Add SKU based on product type
                if product_type.lower() == 'tusproduct':
                    var_data['sku'] = getattr(variation, 'sku', '')
                elif product_type.lower() == 'wholesaleproduct':
                    var_data['sku'] = getattr(variation, 'cin7_sku', '')
                elif product_type.lower() in ['sasproduct', 'lottoproduct']:
                    var_data['sku'] = getattr(variation, 'full_sku', '')

                # Add image URL if available
                image_url = None
                if hasattr(variation, 'image') and variation.image:
                    # Handle both ImageField (has .url) and string URLs
                    image_url = variation.image.url if hasattr(variation.image, 'url') else variation.image
                elif hasattr(variation, 'main_image') and variation.main_image:
                    # Handle both ImageField (has .url) and string URLs
                    image_url = variation.main_image.url if hasattr(variation.main_image, 'url') else variation.main_image

                var_data['image_url'] = image_url

                # Add pricing information for variation (same fallback logic as cart)
                # Priority: variation.margin_75_price > product.margin_75_price > calculated > retail > regular
                margin_price = None
                selling_price = Decimal(str(price_str)) if price_str else Decimal('0')

                # Try variation's margin_75_price first
                if hasattr(variation, 'margin_75_price') and variation.margin_75_price:
                    margin_price = variation.margin_75_price
                # Fall back to product's margin_75_price
                elif hasattr(product, 'margin_75_price') and product.margin_75_price:
                    margin_price = product.margin_75_price
                # Try to calculate from variation's cost_price
                elif hasattr(variation, 'cost_price') and variation.cost_price and variation.cost_price > 0:
                    calculated_margin = (variation.cost_price / Decimal('0.25')).quantize(Decimal('0.01'))
                    if calculated_margin > selling_price:
                        margin_price = calculated_margin
                # Try to calculate from product's cost_price
                elif hasattr(product, 'cost_price') and product.cost_price and product.cost_price > 0:
                    calculated_margin = (product.cost_price / Decimal('0.25')).quantize(Decimal('0.01'))
                    if calculated_margin > selling_price:
                        margin_price = calculated_margin
                # For variations with retail_price
                elif hasattr(variation, 'retail_price') and variation.retail_price and variation.retail_price > 0:
                    if variation.retail_price > selling_price:
                        margin_price = variation.retail_price
                # For products with retail_price
                elif hasattr(product, 'retail_price') and product.retail_price and product.retail_price > 0:
                    if product.retail_price > selling_price:
                        margin_price = product.retail_price
                # For variations with regular_price
                elif hasattr(variation, 'regular_price') and variation.regular_price and variation.regular_price > 0:
                    if variation.regular_price > selling_price:
                        margin_price = variation.regular_price
                # For products with regular_price
                elif hasattr(product, 'regular_price') and product.regular_price and product.regular_price > 0:
                    if product.regular_price > selling_price:
                        margin_price = product.regular_price

                # Add margin price if valid and calculate discount
                if margin_price and margin_price > selling_price:
                    var_data['margin_75_price'] = str(margin_price)
                    discount_amount = margin_price - selling_price
                    discount_percentage = (discount_amount / margin_price * 100).quantize(Decimal('0'))
                    var_data['discount_amount'] = str(discount_amount)
                    var_data['discount_percentage'] = str(discount_percentage)
                else:
                    var_data['margin_75_price'] = None
                    var_data['discount_amount'] = None
                    var_data['discount_percentage'] = None

                # Add cost price missing indicator for variation
                var_data['missing_cost_price'] = (
                    not hasattr(variation, 'cost_price') or
                    variation.cost_price is None or
                    variation.cost_price <= 0
                )

                variations.append(var_data)

        context['variations'] = variations
        context['has_variations'] = len(variations) > 0

        # Convert variations to JSON for JavaScript
        import json
        context['variations_json'] = json.dumps(variations)

        # Check if product is missing cost price
        # Logic: If variations exist, check if ALL variations are missing cost price
        #        If no variations, check main product's cost price
        if variations:
            # Check if ALL variations are missing cost price
            context['product_missing_cost_price'] = all(
                var_data.get('missing_cost_price', True)
                for var_data in variations
            )
        else:
            # No variations - check main product's cost price
            context['product_missing_cost_price'] = (
                not hasattr(product, 'cost_price') or
                product.cost_price is None or
                product.cost_price <= 0
            )

        return context

    def _get_institution_name(self, product, product_type):
        """Get school/club name based on product type"""
        from schools.models_tus import TUSProduct

        try:
            if product_type.lower() == 'tusproduct':
                # Get school from primary category assignment
                if hasattr(product, 'primary_category_assignment') and product.primary_category_assignment:
                    school_category = product.primary_category_assignment.school_category
                    if school_category and school_category.school:
                        return school_category.school.name
                return "TUS School"

            elif product_type.lower() == 'wholesaleproduct':
                # Get school from direct FK
                if hasattr(product, 'school') and product.school:
                    return product.school.name
                return "Wholesale School"

            elif product_type.lower() == 'sasproduct':
                # Get club from direct FK
                if hasattr(product, 'club') and product.club:
                    return f"SAS - {product.club.name}"
                return "SAS Club"

            elif product_type.lower() == 'lottoproduct':
                # Get club from category
                if hasattr(product, 'category') and product.category and product.category.club:
                    return f"LOTTO - {product.category.club.name}"
                return "LOTTO Club"

        except Exception as e:
            logger.error(f"Error getting institution name: {e}")

        return "Unknown Institution"


class NewQuotationView(LoginRequiredMixin, SalesRepOrAccountManagerMixin, View):
    """
    New quotation page with tab-based product selection.
    Shows Schools and Clubs tabs with products from assigned institutions.
    Only accessible to sales reps and account managers.
    """
    template_name = 'quotations/new_quotation.html'
    paginate_by = 24  # Products per page

    def get(self, request):
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
        from schools.models_tus import TUSProduct, TUSSchool

        # Get search query
        search_query = request.GET.get('search', '')

        # Get current tab (default to 'schools')
        active_tab = request.GET.get('tab', 'schools')

        # Get page number
        page = request.GET.get('page', 1)

        # Initialize product collections and pagination objects
        combined_products = []
        page_obj = None
        is_paginated = False

        # Get user's assigned institutions
        assigned_schools = request.user.get_assigned_schools()

        # ========================================
        # SCHOOLS TAB - TUS Schools and Wholesale Schools
        # ========================================
        if active_tab == 'schools':
            from django.db.models import Exists, OuterRef, Q as QOuter

            # Get TUS School Products
            tus_products_qs = TUSProduct.objects.none()
            if assigned_schools.get('regular'):
                tus_school_ids = [school.id for school in assigned_schools['regular']]

                # Stock filtering for TUS Products:
                # - If product has variations: At least ONE variation must have stock_quantity > 0
                # - If product has no variations: Base product must have stock_status in ['instock', 'onbackorder']

                # Subquery to check if product has at least one variation with stock
                has_stock_variation = Exists(
                    TUSProductVariation.objects.filter(
                        product=OuterRef('pk'),
                        is_active=True,
                        stock_quantity__gt=0
                    )
                )

                tus_products_qs = TUSProduct.objects.filter(
                    category_assignments__school_category__school_id__in=tus_school_ids,
                ).annotate(
                    has_stock_variation=has_stock_variation
                ).filter(
                    # Filter: (has variations AND has stock in at least one variation) OR
                    #         (no variations AND product stock_status is instock/onbackorder)
                    QOuter(
                        QOuter(type='variable', has_stock_variation=True) |
                        QOuter(type='simple', stock_status__in=['instock', 'onbackorder'])
                    )
                ).prefetch_related(
                    'category_assignments__school_category__school',
                    'variations'
                ).distinct()

                # Apply search filter
                if search_query:
                    tus_products_qs = tus_products_qs.filter(
                        Q(name__icontains=search_query) |
                        Q(sku__icontains=search_query) |
                        Q(barcode__icontains=search_query) |
                        Q(description__icontains=search_query) |
                        Q(variations__sku__icontains=search_query)  # Search in variation SKUs
                    ).distinct()  # Use distinct() to avoid duplicates from variation joins

            # Get Wholesale School Products with variations
            wholesale_products_qs = WholesaleProduct.objects.none()
            if assigned_schools.get('wholesale'):
                from schools.models import WholesaleProductVariation

                wholesale_school_ids = [school.id for school in assigned_schools['wholesale']]

                # Stock filtering for Wholesale Products:
                # - If product has variations: At least ONE variation must have stock_quantity > 0
                # - If product has no variations: Base product must be is_active=True (already filtered)

                # Subquery to check if product has at least one variation with stock
                has_stock_variation_wholesale = Exists(
                    WholesaleProductVariation.objects.filter(
                        product=OuterRef('pk'),
                        is_active=True,
                        quantity_available__gt=0
                    )
                )

                # Subquery to check if product has any variations at all
                has_any_variation_wholesale = Exists(
                    WholesaleProductVariation.objects.filter(
                        product=OuterRef('pk'),
                        is_active=True
                    )
                )

                wholesale_products_qs = WholesaleProduct.objects.filter(
                    school_id__in=wholesale_school_ids,
                    is_active=True
                ).annotate(
                    has_stock_variation=has_stock_variation_wholesale,
                    has_any_variation=has_any_variation_wholesale
                ).filter(
                    # Filter: (has variations AND has stock in at least one variation) OR
                    #         (no variations - show all active products without variations)
                    QOuter(
                        QOuter(has_any_variation=True, has_stock_variation=True) |
                        QOuter(has_any_variation=False)
                    )
                ).select_related('school').prefetch_related('variations')

                # Apply search filter
                if search_query:
                    # Search in product fields and variation SKUs (for grouped products)
                    # This allows searching by any variation SKU and finding the base product
                    wholesale_products_qs = wholesale_products_qs.filter(
                        Q(name__icontains=search_query) |
                        Q(cin7_sku__icontains=search_query) |
                        Q(description__icontains=search_query) |
                        Q(variations__cin7_sku__icontains=search_query)  # Search in variation SKUs
                    ).distinct()  # Use distinct() to avoid duplicates from variation joins

            # Combine querysets for pagination
            # Convert to lists and merge (since they're different models)
            tus_products_list = list(tus_products_qs)
            wholesale_products_list = list(wholesale_products_qs)

            # Add product_type attribute and variation info for template rendering
            for product in tus_products_list:
                product.product_type = 'tusproduct'
                # TUSProduct already has has_variations property - just add variation display data
                if product.has_variations:
                    variations = list(product.variations.all())
                    product.variation_display = self._get_variation_display_data(variations, 'tus')
                else:
                    product.variation_display = {}

            # Group wholesale products by base SKU (like in WholesaleSchoolDetailView)
            grouped_wholesale_products = self._group_wholesale_products_by_base_sku(wholesale_products_list)

            for product in grouped_wholesale_products:
                product.product_type = 'wholesaleproduct'
                # WholesaleProduct now has has_variations property - just add variation display data
                if product.has_variations:
                    variations = list(product.variations.filter(is_active=True))
                    product.variation_display = self._get_variation_display_data(variations, 'wholesale')
                else:
                    product.variation_display = {}

            combined_products = tus_products_list + grouped_wholesale_products

            # Apply pagination to combined list
            paginator = Paginator(combined_products, self.paginate_by)
            try:
                page_obj = paginator.get_page(page)
            except PageNotAnInteger:
                page_obj = paginator.get_page(1)
            except EmptyPage:
                page_obj = paginator.get_page(paginator.num_pages)

            is_paginated = paginator.num_pages > 1

        # ========================================
        # CLUBS TAB - SAS Clubs and LOTTO Clubs
        # ========================================
        elif active_tab == 'clubs':
            from django.db.models import Exists, OuterRef, Q as QOuter
            from clubs.models_sas import SASProductVariation
            from clubs.models_lotto import LottoProductVariation

            # Get assigned clubs
            if request.user.is_admin or request.user.is_account_manager:
                # Admin and account managers have access to all clubs
                sas_clubs = SASClub.objects.filter(is_active=True)
                lotto_clubs = LottoClub.objects.filter(is_active=True)
            elif request.user.is_sales_rep:
                # Get club assignments (GenericForeignKey)
                club_assignments = SalesRepClubAssignment.objects.filter(
                    sales_rep=request.user,
                    is_active=True
                ).select_related('club_content_type')

                sas_club_ids = []
                lotto_club_ids = []

                for assignment in club_assignments:
                    if assignment.club:
                        if isinstance(assignment.club, SASClub):
                            sas_club_ids.append(assignment.club.id)
                        elif isinstance(assignment.club, LottoClub):
                            lotto_club_ids.append(assignment.club.id)

                sas_clubs = SASClub.objects.filter(id__in=sas_club_ids)
                lotto_clubs = LottoClub.objects.filter(id__in=lotto_club_ids)
            else:
                sas_clubs = SASClub.objects.none()
                lotto_clubs = LottoClub.objects.none()

            # Stock filtering for SAS Products:
            # - If product has variations: At least ONE variation must have stock_quantity > 0
            # - If product has no variations: Base product must have stock_status in ['instock', 'onbackorder']

            # Subquery to check if product has at least one variation with stock
            has_stock_variation_sas = Exists(
                SASProductVariation.objects.filter(
                    product=OuterRef('pk'),
                    is_active=True,
                    stock_quantity__gt=0
                )
            )

            # Subquery to check if product has any variations at all
            has_any_variation_sas = Exists(
                SASProductVariation.objects.filter(
                    product=OuterRef('pk'),
                    is_active=True
                )
            )

            # Get SAS Products with stock filtering
            sas_products_qs = SASProduct.objects.filter(
                club__in=sas_clubs,
                is_active=True
            ).annotate(
                has_stock_variation=has_stock_variation_sas,
                has_any_variation=has_any_variation_sas
            ).filter(
                # Filter: (has variations AND has stock in at least one variation) OR
                #         (no variations AND product stock_status is instock/onbackorder)
                QOuter(
                    QOuter(has_any_variation=True, has_stock_variation=True) |
                    QOuter(has_any_variation=False, stock_status__in=['instock', 'onbackorder'])
                )
            ).select_related('club').prefetch_related('variations')

            # Apply search filter
            if search_query:
                sas_products_qs = sas_products_qs.filter(
                    Q(name__icontains=search_query) |
                    Q(sku__icontains=search_query) |
                    Q(description__icontains=search_query) |
                    Q(variations__sku_suffix__icontains=search_query)  # Search in variation SKU suffix
                ).distinct()

            # Stock filtering for LOTTO Products:
            # - If product has variations: At least ONE variation must have stock_quantity > 0
            # - If product has no variations: Base product must have stock_status in ['instock', 'onbackorder']

            # Subquery to check if product has at least one variation with stock
            has_stock_variation_lotto = Exists(
                LottoProductVariation.objects.filter(
                    product=OuterRef('pk'),
                    is_active=True,
                    stock_quantity__gt=0
                )
            )

            # Get LOTTO Products with stock filtering
            lotto_products_qs = LottoProduct.objects.filter(
                category__club__in=lotto_clubs,
            ).annotate(
                has_stock_variation=has_stock_variation_lotto
            ).filter(
                # Filter: (has variations AND has stock in at least one variation) OR
                #         (no variations AND product stock_status is instock/onbackorder)
                QOuter(
                    QOuter(type='variable', has_stock_variation=True) |
                    QOuter(type='simple', stock_status__in=['instock', 'onbackorder'])
                )
            ).select_related('category__club').prefetch_related('variations')

            # Apply search filter
            if search_query:
                lotto_products_qs = lotto_products_qs.filter(
                    Q(name__icontains=search_query) |
                    Q(sku__icontains=search_query) |
                    Q(description__icontains=search_query) |
                    Q(variations__sku_suffix__icontains=search_query)  # Search in variation SKU suffix
                ).distinct()

            # Combine querysets for pagination
            sas_products_list = list(sas_products_qs)
            lotto_products_list = list(lotto_products_qs)

            # Add product_type attribute and variation info for template rendering
            for product in sas_products_list:
                product.product_type = 'sasproduct'
                # SASProduct already has has_variations property - just add variation display data
                if product.has_variations:
                    variations = list(product.variations.filter(is_active=True))
                    product.variation_display = self._get_variation_display_data(variations, 'sas')
                else:
                    product.variation_display = {}

            for product in lotto_products_list:
                product.product_type = 'lottoproduct'
                # LottoProduct already has has_variations property - just add variation display data
                if product.has_variations:
                    variations = list(product.variations.filter(is_active=True))
                    product.variation_display = self._get_variation_display_data(variations, 'lotto')
                else:
                    product.variation_display = {}

            combined_products = sas_products_list + lotto_products_list

            # Apply pagination to combined list
            paginator = Paginator(combined_products, self.paginate_by)
            try:
                page_obj = paginator.get_page(page)
            except PageNotAnInteger:
                page_obj = paginator.get_page(1)
            except EmptyPage:
                page_obj = paginator.get_page(paginator.num_pages)

            is_paginated = paginator.num_pages > 1

        # Get current quotation count from session
        quotation_data = get_quotation_session(request)
        totals = calculate_quotation_totals(quotation_data)

        # Log access
        AuditLog.log_action(
            user=request.user,
            action_type='data_access',
            description='Viewed new quotation page',
            request=request,
            active_tab=active_tab,
            search_query=search_query
        )

        context = {
            'active_tab': active_tab,
            'search_query': search_query,

            # Paginated products
            'products': page_obj.object_list if page_obj else [],
            'page_obj': page_obj,
            'is_paginated': is_paginated,

            # Quotation summary
            'quotation_item_count': totals['item_count'],
            'quotation_total': totals['total'],

            # Total product counts (for display)
            'total_product_count': len(combined_products),
        }

        return render(request, self.template_name, context)

    def _group_wholesale_products_by_base_sku(self, products):
        """
        Group wholesale products by their base SKU pattern.
        For example: "POLO 45 FT BLK SAS WLC XS" and "POLO 45 FT BLK SAS WLC S"
        both belong to base SKU "POLO 45 FT BLK SAS WLC"

        This follows the same logic as WholesaleSchoolDetailView._group_products_by_base_sku()
        """
        from collections import defaultdict

        grouped = defaultdict(lambda: {
            'main_product': None,
            'variations': [],
            'variation_summary': set()
        })

        for product in products:
            # Extract base SKU by removing variation suffixes
            base_sku = self._extract_base_sku(product.cin7_sku or '')

            if not base_sku:
                base_sku = product.name or 'unknown'

            # Use the first product as the main product for this base SKU
            if grouped[base_sku]['main_product'] is None:
                grouped[base_sku]['main_product'] = product

            # Extract variation info from the SKU suffix
            variation_info = self._extract_variation_from_sku(product.cin7_sku or '')
            if variation_info:
                grouped[base_sku]['variations'].append(product)
                grouped[base_sku]['variation_summary'].add(variation_info)

        # Convert to list format and add variation summary to main products
        result = []
        for base_sku, group_data in grouped.items():
            main_product = group_data['main_product']
            if main_product:
                # Add variation summary as a property
                main_product.variation_count = len(group_data['variations']) + 1  # +1 for main product
                main_product.variation_summary = ', '.join(sorted(group_data['variation_summary'])) if group_data['variation_summary'] else ''
                main_product.variation_list = sorted(list(group_data['variation_summary'])) if group_data['variation_summary'] else []  # List for template iteration
                main_product.base_sku = base_sku
                main_product.all_variations = [main_product] + group_data['variations']  # Store all variations
                result.append(main_product)

        return sorted(result, key=lambda p: p.name or '')

    def _extract_base_sku(self, sku):
        """
        Extract base SKU by removing common variation patterns.
        Examples:
        - "POLO 45 FT BLK SAS WLC XS" -> "POLO 45 FT BLK SAS WLC"
        - "US FLC 789 CGS - XL" -> "US FLC 789 CGS"
        """
        if not sku:
            return ''

        import re

        # Pattern 1: Remove " - anything" (dash with spaces)
        base = re.sub(r'\s*-\s*.+$', '', sku)

        # Pattern 2: Remove common size indicators at the end
        base = re.sub(r'\s+(XS|S|M|L|XL|XXL|2XL|3XL|\d+)$', '', base, flags=re.IGNORECASE)

        # Pattern 3: Remove trailing numbers that might be sizes
        base = re.sub(r'\s+\d+$', '', base)

        return base.strip()

    def _extract_variation_from_sku(self, sku):
        """
        Extract variation information from SKU.
        Examples:
        - "POLO 45 FT BLK SAS WLC XS" -> "XS"
        - "US FLC 789 CGS - XL" -> "XL"
        """
        if not sku:
            return ''

        import re

        # Pattern 1: After dash (e.g., " - XL")
        match = re.search(r'\s*-\s*(.+)$', sku)
        if match:
            return match.group(1).strip()

        # Pattern 2: Last word if it looks like a size
        parts = sku.split()
        if parts:
            last_part = parts[-1]
            # Check if last part looks like a size
            if re.match(r'^(XS|S|M|L|XL|XXL|2XL|3XL|\d+)$', last_part, re.IGNORECASE):
                return last_part

        return ''

    def _get_variation_display_data(self, variations, product_type):
        """
        Extract variation display data from variation objects.
        Returns dict with sizes, colors, total_stock, variation_count, and SKU info.
        """
        sizes = set()
        colors = set()
        total_stock = 0
        skus = []  # Store SKUs for display

        for variation in variations:
            # Extract variation type and value
            var_type = getattr(variation, 'variation_type', '').lower()
            var_value = getattr(variation, 'variation_value', '')

            # Parse composite values like "XL - Black" or "Large - Red"
            if ' - ' in var_value:
                parts = [p.strip() for p in var_value.split(' - ')]
                # First part usually size, second usually color
                if len(parts) >= 2:
                    sizes.add(parts[0])
                    colors.add(parts[1])
                else:
                    if var_type in ['size', 'pa_size']:
                        sizes.add(parts[0])
                    elif var_type in ['color', 'colour', 'pa_color', 'pa_colour']:
                        colors.add(parts[0])
            else:
                # Single attribute value
                if var_type in ['size', 'pa_size']:
                    sizes.add(var_value)
                elif var_type in ['color', 'colour', 'pa_color', 'pa_colour']:
                    colors.add(var_value)

            # Add stock
            stock_qty = getattr(variation, 'stock_quantity', 0)
            if stock_qty:
                total_stock += stock_qty

            # Extract SKU based on product type
            sku = None
            if product_type == 'TUS':
                # TUSProductVariation has 'sku' field
                sku = getattr(variation, 'sku', None)
            elif product_type == 'Wholesale':
                # WholesaleProductVariation has 'cin7_sku' field
                sku = getattr(variation, 'cin7_sku', None)
            elif product_type in ['SAS', 'LOTTO']:
                # SASProductVariation and LottoProductVariation have 'full_sku' property
                sku = getattr(variation, 'full_sku', None)

            # Add SKU to list if it exists
            if sku:
                skus.append({
                    'sku': sku,
                    'variation': var_value,
                    'stock': stock_qty
                })

        return {
            'sizes': sorted(list(sizes)) if sizes else [],
            'colors': sorted(list(colors)) if colors else [],
            'total_stock': total_stock,
            'variation_count': len(variations),
            'skus': skus,  # List of SKU information
            'has_skus': len(skus) > 0,  # Quick check for template
        }
