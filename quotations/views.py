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
from django.core.exceptions import PermissionDenied
import logging

from authentication.permissions import (
    SalesRepOrAccountManagerMixin,
    CustomerRequiredMixin,
)
from authentication.models import User, SalesRepSchoolAssignment, SalesRepClubAssignment, AuditLog
from schools.models import School, WholesaleSchool, WholesaleProduct
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
    from clubs.models_tus import TUSProduct

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


def user_can_access_institution(user, institution_type, institution_id):
    """Check if user can access the specified institution"""
    from clubs.models_tus import TUSSchool

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
    from clubs.models_tus import TUSSchool

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
        from clubs.models_tus import TUSSchool, TUSProduct

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
        from clubs.models_tus import TUSSchool, TUSProduct

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
    """
    template_name = 'quotations/quotation_cart.html'

    def get(self, request):
        quotation_data = get_quotation_session(request)

        # Enrich items with product details
        enriched_items = []
        for item in quotation_data.get('items', []):
            product = get_product_by_type_and_id(item['product_type'], item['product_id'])
            if product:
                enriched_item = item.copy()
                enriched_item['product'] = product
                enriched_item['line_total'] = Decimal(str(item['unit_price'])) * Decimal(str(item['quantity']))
                enriched_items.append(enriched_item)

        # Calculate totals
        totals = calculate_quotation_totals(quotation_data)

        # Get institution if set
        institution = None
        if quotation_data.get('institution_type') and quotation_data.get('institution_id'):
            from clubs.models_tus import TUSSchool

            institution_models = {
                'tusschool': TUSSchool,
                'wholesaleschool': WholesaleSchool,
                'lottoclub': LottoClub,
                'sasclub': SASClub,
            }
            model_class = institution_models.get(quotation_data['institution_type'].lower())
            if model_class:
                try:
                    institution = model_class.objects.get(pk=quotation_data['institution_id'])
                except model_class.DoesNotExist:
                    pass

        context = {
            'items': enriched_items,
            'totals': totals,
            'institution': institution,
            'institution_type': quotation_data.get('institution_type'),
            'institution_id': quotation_data.get('institution_id'),
        }

        return render(request, self.template_name, context)


# =====================================
# AJAX ENDPOINTS
# =====================================

class AddToQuotationView(LoginRequiredMixin, View):
    """AJAX endpoint to add product to quotation"""

    def post(self, request):
        try:
            product_type = request.POST.get('product_type')
            product_id = int(request.POST.get('product_id'))
            quantity = int(request.POST.get('quantity', 1))

            # Get product
            product = get_product_by_type_and_id(product_type, product_id)
            if not product:
                return JsonResponse({'success': False, 'error': 'Product not found'}, status=404)

            # Get quotation session
            quotation_data = get_quotation_session(request)

            # Check if item already exists
            existing_item = None
            for item in quotation_data['items']:
                if item['product_type'] == product_type and item['product_id'] == product_id:
                    existing_item = item
                    break

            if existing_item:
                # Update quantity
                existing_item['quantity'] += quantity
            else:
                # Add new item
                quotation_data['items'].append({
                    'product_type': product_type,
                    'product_id': product_id,
                    'product_name': product.name,
                    'product_sku': getattr(product, 'cin7_sku', '') or getattr(product, 'sku', ''),
                    'quantity': quantity,
                    'unit_price': str(getattr(product, 'wholesale_price', None) or getattr(product, 'price', 0)),
                    'variations': {},
                })

            # Save session
            save_quotation_session(request, quotation_data)

            # Calculate totals
            totals = calculate_quotation_totals(quotation_data)

            # Log action
            AuditLog.log_action(
                user=request.user,
                action_type='data_access',
                description=f'Added {product.name} to quotation',
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

            # Update quantity
            quotation_data['items'][item_index]['quantity'] = quantity

            # Save session
            save_quotation_session(request, quotation_data)

            # Calculate totals
            totals = calculate_quotation_totals(quotation_data)

            # Calculate line total
            item = quotation_data['items'][item_index]
            line_total = Decimal(str(item['unit_price'])) * Decimal(str(quantity))

            return JsonResponse({
                'success': True,
                'line_total': str(line_total),
                'subtotal': str(totals['subtotal']),
                'tax_amount': str(totals['tax_amount']),
                'total': str(totals['total']),
            })

        except Exception as e:
            logger.error(f"Error updating quotation item: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


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
                action_type='data_access',
                description=f'Removed {removed_item["product_name"]} from quotation',
                request=request,
                product_name=removed_item['product_name']
            )

            return JsonResponse({
                'success': True,
                'item_count': totals['item_count'],
                'subtotal': str(totals['subtotal']),
                'tax_amount': str(totals['tax_amount']),
                'total': str(totals['total']),
            })

        except Exception as e:
            logger.error(f"Error removing quotation item: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


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
    """

    def post(self, request):
        try:
            quotation_data = get_quotation_session(request)

            # Validate quotation has items
            if not quotation_data.get('items'):
                return JsonResponse({'success': False, 'error': 'Quotation is empty'}, status=400)

            # Validate institution is set
            if not quotation_data.get('institution_type') or not quotation_data.get('institution_id'):
                return JsonResponse({'success': False, 'error': 'No institution selected'}, status=400)

            # Get institution
            from clubs.models_tus import TUSSchool

            institution_models = {
                'tusschool': TUSSchool,
                'wholesaleschool': WholesaleSchool,
                'lottoclub': LottoClub,
                'sasclub': SASClub,
            }
            model_class = institution_models.get(quotation_data['institution_type'].lower())
            institution = get_object_or_404(model_class, pk=quotation_data['institution_id'])

            # Create Quotation
            institution_content_type = ContentType.objects.get_for_model(institution)
            quotation = Quotation.objects.create(
                created_by=request.user,
                institution_content_type=institution_content_type,
                institution_object_id=institution.id,
                status='draft',
            )

            # Create QuotationItems
            for item_data in quotation_data['items']:
                product = get_product_by_type_and_id(item_data['product_type'], item_data['product_id'])
                if not product:
                    continue

                product_content_type = ContentType.objects.get_for_model(product)
                QuotationItem.objects.create(
                    quotation=quotation,
                    product_content_type=product_content_type,
                    product_object_id=product.id,
                    product_name=product.name,
                    product_sku=getattr(product, 'cin7_sku', '') or getattr(product, 'sku', ''),
                    quantity=item_data['quantity'],
                    unit_price=Decimal(str(item_data['unit_price'])),
                    variations=item_data.get('variations', {}),
                )

            # Calculate quotation totals
            quotation.calculate_totals()

            # Clear session
            clear_quotation_session(request)

            # Log action
            AuditLog.log_action(
                user=request.user,
                action_type='data_access',
                description=f'Saved quotation {quotation.quotation_number}',
                request=request,
                quotation_id=str(quotation.id),
                quotation_number=quotation.quotation_number
            )

            return JsonResponse({
                'success': True,
                'quotation_id': str(quotation.id),
                'quotation_number': quotation.quotation_number,
                'redirect_url': reverse('quotations:my-quotations'),
            })

        except Exception as e:
            logger.error(f"Error saving quotation: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


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
