"""
Quotation views for SASKITUP project.

This module provides comprehensive quotation workflow views:
1. Institution Selection - User selects school/club
2. Product Listing - Browse products for selected institution
3. Quotation Cart - Manage quotation items
4. Save Quotation - Convert session to database record
5. My Quotations - View user's quotations
"""

from decimal import Decimal, ROUND_HALF_UP
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.validators import validate_email
from django.db.models import Q, Prefetch
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, DetailView, FormView
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib import messages
import logging

from authentication.permissions import (
    SalesRepOrAccountManagerMixin,
    CustomerRequiredMixin,
    SalesRepOrAccountManagerOrCustomerMixin,
)
from authentication.models import User, SalesRepSchoolAssignment, SalesRepClubAssignment, AuditLog
from schools.models import School, WholesaleSchool, WholesaleProduct, WholesaleProductVariation
from schools.models_tus import TUSProductVariation
from clubs.models_lotto import LottoClub, LottoProduct
from clubs.models_sas import SASClub, SASProduct
from .models import Quotation, QuotationItem, CustomerInstitutionAssignment, SiteSettings
from .forms import SiteSettingsForm

logger = logging.getLogger(__name__)


# =====================================
# HELPER FUNCTIONS & UTILITIES
# =====================================

def round_to_nearest_5(value):
    """
    Round a decimal value to the nearest $5 increment.

    Examples:
        $78.50 → $80.00
        $76.20 → $75.00
        $163.84 → $165.00
        $52.00 → $50.00
        $0.00 → $0.00

    Args:
        value: Decimal value to round

    Returns:
        Decimal: Value rounded to nearest $5
    """
    if not value or value == 0:
        return Decimal('0')
    # Divide by 5, round to nearest integer, multiply by 5
    return (value / Decimal('5')).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * Decimal('5')


def validate_additional_emails(emails_string):
    """
    Validate semicolon-separated email addresses.

    Args:
        emails_string: String of email addresses separated by semicolons

    Returns:
        tuple: (is_valid, error_message)
    """
    if not emails_string or not emails_string.strip():
        return True, None

    # Split by semicolon and clean up
    emails = [email.strip() for email in emails_string.split(';') if email.strip()]

    # Validate each email
    for email in emails:
        try:
            validate_email(email)
        except ValidationError:
            return False, f"Invalid email address: {email}"

    return True, None

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
    from .models import SiteSettings

    subtotal = Decimal('0.00')

    # Get GST percentage from site settings
    settings = SiteSettings.objects.get_settings()
    tax_percentage = settings.gst_percentage

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


def get_assigned_staff_from_products(quotation_items):
    """
    Automatically determine sales rep and account manager based on products in quotation.

    Logic:
    - Extract all unique schools/clubs from quotation products
    - Find assigned sales reps and account managers for those institutions
    - If all products belong to same institution: return that institution's assignments
    - If products from multiple institutions with same assignments: return those
    - If products from multiple institutions with different assignments: return None (ambiguous)

    Args:
        quotation_items: List of quotation item dictionaries with product_type and product_id

    Returns:
        dict: {
            'sales_rep': User instance or None,
            'account_manager': User instance or None,
            'institution_count': Number of unique institutions,
            'institutions': List of institution names (for display)
        }
    """
    from schools.models_tus import TUSSchool
    from collections import defaultdict

    if not quotation_items:
        return {
            'sales_rep': None,
            'account_manager': None,
            'institution_count': 0,
            'institutions': []
        }

    # Track institutions and their assigned staff
    institution_staff = {}  # Key: (institution_type, institution_id), Value: {'sales_rep': User, 'account_manager': User, 'name': str}

    for item in quotation_items:
        product = get_product_by_type_and_id(item['product_type'], item['product_id'])
        if not product:
            continue

        institution_key = None
        institution_name = None
        sales_rep = None
        account_manager = None

        # Determine institution based on product type
        product_type = item['product_type'].lower()

        if product_type == 'wholesaleproduct':
            # WholesaleProduct → school FK → WholesaleSchool
            school = getattr(product, 'school', None)
            if school:
                institution_key = ('wholesaleschool', school.id)
                institution_name = school.name

                # Find assignment for this wholesale school
                assignment = SalesRepSchoolAssignment.objects.filter(
                    wholesale_school=school,
                    is_active=True
                ).first()

                if assignment:
                    sales_rep = assignment.sales_rep if assignment.sales_rep.user_type == 'sales_rep' else None
                    account_manager = assignment.sales_rep if assignment.sales_rep.user_type == 'account_manager' else None

        elif product_type == 'tusproduct':
            # TUSProduct → category_assignments → school_category → school
            # Get the primary school category assignment
            category_assignment = getattr(product, 'category_assignments', None)
            if category_assignment:
                # Try to get the first school category (primary if possible)
                school_assignment = category_assignment.filter(
                    school_category__isnull=False
                ).select_related('school_category__school').first()

                if school_assignment and school_assignment.school_category:
                    school = school_assignment.school_category.school
                    if school:
                        institution_key = ('tusschool', school.id)
                        institution_name = school.name

                        # Find assignment for this TUS school
                        assignment = SalesRepSchoolAssignment.objects.filter(
                            tus_school=school,
                            is_active=True
                        ).first()

                        if assignment:
                            sales_rep = assignment.sales_rep if assignment.sales_rep.user_type == 'sales_rep' else None
                            account_manager = assignment.sales_rep if assignment.sales_rep.user_type == 'account_manager' else None

        elif product_type == 'lottoproduct':
            # LottoProduct → category → club
            category = getattr(product, 'category', None)
            if category:
                club = getattr(category, 'club', None)
                if club:
                    institution_key = ('lottoclub', club.id)
                    institution_name = club.name

                    # Find assignment for this LOTTO club
                    from django.contrib.contenttypes.models import ContentType
                    club_ct = ContentType.objects.get_for_model(club)

                    assignment = SalesRepClubAssignment.objects.filter(
                        club_content_type=club_ct,
                        club_object_id=club.id,
                        is_active=True
                    ).first()

                    if assignment:
                        sales_rep = assignment.sales_rep if assignment.sales_rep.user_type == 'sales_rep' else None
                        account_manager = assignment.sales_rep if assignment.sales_rep.user_type == 'account_manager' else None

        elif product_type == 'sasproduct':
            # SASProduct → club FK → SASClub
            club = getattr(product, 'club', None)
            if club:
                institution_key = ('sasclub', club.id)
                institution_name = club.name

                # Find assignment for this SAS club
                from django.contrib.contenttypes.models import ContentType
                club_ct = ContentType.objects.get_for_model(club)

                assignment = SalesRepClubAssignment.objects.filter(
                    club_content_type=club_ct,
                    club_object_id=club.id,
                    is_active=True
                ).first()

                if assignment:
                    sales_rep = assignment.sales_rep if assignment.sales_rep.user_type == 'sales_rep' else None
                    account_manager = assignment.sales_rep if assignment.sales_rep.user_type == 'account_manager' else None

        # Store institution and its staff
        if institution_key:
            if institution_key not in institution_staff:
                institution_staff[institution_key] = {
                    'sales_rep': sales_rep,
                    'account_manager': account_manager,
                    'name': institution_name
                }

    # Analyze results
    unique_institutions = list(institution_staff.values())
    institution_count = len(unique_institutions)
    institution_names = [inst['name'] for inst in unique_institutions if inst['name']]

    # If no institutions found, return None
    if institution_count == 0:
        return {
            'sales_rep': None,
            'account_manager': None,
            'institution_count': 0,
            'institutions': []
        }

    # If single institution, return its assignments
    if institution_count == 1:
        inst = unique_institutions[0]
        return {
            'sales_rep': inst['sales_rep'],
            'account_manager': inst['account_manager'],
            'institution_count': 1,
            'institutions': institution_names
        }

    # If multiple institutions, check if they have the same assignments
    first_inst = unique_institutions[0]
    first_sales_rep = first_inst['sales_rep']
    first_account_manager = first_inst['account_manager']

    all_same_sales_rep = all(
        inst['sales_rep'] == first_sales_rep
        for inst in unique_institutions
    )
    all_same_account_manager = all(
        inst['account_manager'] == first_account_manager
        for inst in unique_institutions
    )

    return {
        'sales_rep': first_sales_rep if all_same_sales_rep else None,
        'account_manager': first_account_manager if all_same_account_manager else None,
        'institution_count': institution_count,
        'institutions': institution_names
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
    from ballstore.models import BallStoreProduct

    product_models = {
        'tusproduct': TUSProduct,
        'wholesaleproduct': WholesaleProduct,
        'lottoproduct': LottoProduct,
        'sasproduct': SASProduct,
        'ballstoreproduct': BallStoreProduct,
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

        # Get user's accessible institutions for dropdown
        institutions_list = []
        if request.user.is_authenticated:
            institutions = get_user_institutions(request.user)

            # Format TUS schools
            for school in institutions.get('tus_schools', []):
                institutions_list.append({
                    'id': f'tusschool_{school.id}',
                    'text': f'{school.name} - TUS School',
                    'type': 'tusschool'
                })

            # Format wholesale schools
            for school in institutions.get('wholesale_schools', []):
                institutions_list.append({
                    'id': f'wholesaleschool_{school.id}',
                    'text': f'{school.name} - Wholesale School',
                    'type': 'wholesaleschool'
                })

            # Format LOTTO clubs
            for club in institutions.get('lotto_clubs', []):
                institutions_list.append({
                    'id': f'lottoclub_{club.id}',
                    'text': f'{club.name} - LOTTO Club',
                    'type': 'lottoclub'
                })

            # Format SAS clubs
            for club in institutions.get('sas_clubs', []):
                institutions_list.append({
                    'id': f'sasclub_{club.id}',
                    'text': f'{club.name} - SAS Club',
                    'type': 'sasclub'
                })

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
                    # Round margin price to nearest $5
                    rounded_margin_price = round_to_nearest_5(margin_price)

                    # Use rounded margin price for all calculations
                    enriched_item['margin_75_price'] = rounded_margin_price
                    unit_discount = rounded_margin_price - unit_price_decimal
                    item_savings = unit_discount * Decimal(str(item['quantity']))
                    total_savings += item_savings
                    enriched_item['unit_discount'] = unit_discount
                    enriched_item['item_discount'] = item_savings
                    # Calculate discount percentage using rounded margin price
                    discount_percentage = int(((rounded_margin_price - unit_price_decimal) / rounded_margin_price) * 100)
                    enriched_item['discount_percentage'] = discount_percentage
                else:
                    enriched_item['unit_discount'] = Decimal('0.00')
                    enriched_item['item_discount'] = Decimal('0.00')
                    enriched_item['discount_percentage'] = 0

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

        # Prepare user data for auto-population (for customer users)
        user_full_name = ''
        user_address = ''
        if request.user.is_customer:
            user_full_name = request.user.get_full_name()
            user_address = getattr(request.user, 'address', '')

        # Prepare institutions_json for Select2
        import json
        institutions_json = json.dumps(institutions_list)

        # Get currently selected institution if any
        current_institution_id = None
        if institution:
            if institution_type:
                current_institution_id = f'{institution_type.lower()}_{institution.id}'

        # Check if we're editing an existing quotation
        editing_quotation_id = quotation_data.get('editing_quotation_id')
        editing_quotation = None
        current_sales_rep_id = None
        current_account_manager_id = None
        auto_assigned_sales_rep = None
        auto_assigned_account_manager = None
        assignment_info = {}

        if editing_quotation_id:
            try:
                editing_quotation = Quotation.objects.get(pk=editing_quotation_id)
                if editing_quotation.assigned_sales_rep:
                    current_sales_rep_id = str(editing_quotation.assigned_sales_rep.id)
                if editing_quotation.account_manager:
                    current_account_manager_id = str(editing_quotation.account_manager.id)
            except Quotation.DoesNotExist:
                pass

        # Automatically determine sales rep and account manager from products
        if not editing_quotation_id:  # Only auto-assign for new quotations
            assignment_info = get_assigned_staff_from_products(quotation_data.get('items', []))
            auto_assigned_sales_rep = assignment_info.get('sales_rep')
            auto_assigned_account_manager = assignment_info.get('account_manager')

            # Set current IDs to auto-assigned values if available
            if auto_assigned_sales_rep:
                current_sales_rep_id = str(auto_assigned_sales_rep.id)
            if auto_assigned_account_manager:
                current_account_manager_id = str(auto_assigned_account_manager.id)

        context = {
            'cart_items': enriched_items,  # Changed from 'items' to match template
            'subtotal': totals['subtotal'],
            'tax': totals['tax_amount'],
            'total': totals['total'],
            'total_savings': total_savings,
            'institution': institution,
            'institution_type': institution_type,
            'institution_slug': institution_slug,
            'user_full_name': user_full_name,
            'user_address': user_address,
            'is_customer': request.user.is_customer,
            'institutions_json': institutions_json,
            'current_institution_id': current_institution_id,
            'current_sales_rep_id': current_sales_rep_id,
            'current_account_manager_id': current_account_manager_id,
            'auto_assigned_sales_rep': auto_assigned_sales_rep,
            'auto_assigned_account_manager': auto_assigned_account_manager,
            'assignment_institution_count': assignment_info.get('institution_count', 0),
            'assignment_institutions': ', '.join(assignment_info.get('institutions', [])),
            'is_editing': editing_quotation is not None,
            'editing_quotation': editing_quotation,
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
                existing_item['quantity'] = new_quantity
            else:
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

                # Get margin_75_price from variations or product
                margin_75_price = variations.get('margin_75_price') or str(getattr(product, 'margin_75_price', None) or '')

                quotation_data['items'].append({
                    'product_type': product_type,
                    'product_id': product_id,
                    'product_name': product_name,
                    'product_sku': product_sku,
                    'quantity': quantity,
                    'unit_price': str(unit_price),
                    'margin_75_price': margin_75_price,
                    'variations': variations,
                })

            # Save session
            save_quotation_session(request, quotation_data)

            # Calculate totals
            totals = calculate_quotation_totals(quotation_data)

            # Log action
            variation_info = f" ({variations.get('size', '')})" if variations.get('size') else ""
            if existing_item:
                action_desc = f'Updated quotation: Changed "{product.name}{variation_info}" quantity to {quantity}'
            else:
                action_desc = f'Updated quotation: Added item "{product.name}{variation_info}" (Qty: {quantity}, Price: ${unit_price})'
            AuditLog.log_action(
                user=request.user,
                action_type='quotation_updated',
                description=action_desc,
                request=request,
                affected_model='QuotationItem',
                product_name=product.name,
                product_type=product_type,
                product_id=product_id,
                quantity=quantity,
                unit_price=str(unit_price),
                variations=str(variations) if variations else None
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

            # Log cart state before update
            items_before = len(quotation_data.get('items', []))
            logger.info(f"Updating item {item_index}, cart has {items_before} items before update")

            if item_index < 0 or item_index >= len(quotation_data['items']):
                logger.error(f"Invalid item index {item_index}, cart has {len(quotation_data['items'])} items")
                return JsonResponse({'success': False, 'error': 'Invalid item index'}, status=400)

            # Get the item and store old quantity
            item = quotation_data['items'][item_index]
            old_quantity = item.get('quantity', 0)

            # Update quantity
            quotation_data['items'][item_index]['quantity'] = quantity

            # Save session
            save_quotation_session(request, quotation_data)

            # Verify session was saved correctly
            verification_data = get_quotation_session(request)
            items_after = len(verification_data.get('items', []))

            if items_before != items_after:
                logger.error(f"Cart corruption detected! Had {items_before} items before, {items_after} after update")
                return JsonResponse({
                    'success': False,
                    'error': 'Cart data integrity error. Please refresh the page.'
                }, status=500)

            logger.info(f"Successfully updated item {item_index}, cart has {items_after} items after update")

            # Calculate totals
            totals = calculate_quotation_totals(quotation_data)

            # Calculate line total
            line_total = Decimal(str(item['unit_price'])) * Decimal(str(quantity))

            # Calculate discounts for response
            unit_price_decimal = Decimal(str(item.get('unit_price', 0)))
            margin_price = Decimal(str(item.get('margin_75_price', 0))) if item.get('margin_75_price') else Decimal('0')

            unit_discount = Decimal('0')
            item_discount = Decimal('0')
            discount_percentage = 0

            if margin_price > 0 and margin_price > unit_price_decimal:
                unit_discount = margin_price - unit_price_decimal
                item_discount = unit_discount * Decimal(str(quantity))
                # Calculate discount percentage
                discount_percentage = int(((margin_price - unit_price_decimal) / margin_price) * 100)

            # Calculate total savings across all items
            total_savings = Decimal('0.00')
            for cart_item in quotation_data.get('items', []):
                item_unit_price = Decimal(str(cart_item.get('unit_price', 0)))
                item_margin_price = Decimal(str(cart_item.get('margin_75_price', 0))) if cart_item.get('margin_75_price') else Decimal('0')
                item_qty = Decimal(str(cart_item.get('quantity', 0)))

                if item_margin_price > 0 and item_margin_price > item_unit_price:
                    item_unit_discount = item_margin_price - item_unit_price
                    item_total_discount = item_unit_discount * item_qty
                    total_savings += item_total_discount

            # Log action
            AuditLog.log_action(
                user=request.user,
                action_type='quotation_updated',
                description=f'Updated quotation: Changed "{item["product_name"]}" quantity from {old_quantity} to {quantity}',
                request=request,
                affected_model='QuotationItem',
                product_name=item['product_name'],
                product_type=item.get('product_type', 'unknown'),
                item_index=item_index,
                old_quantity=old_quantity,
                new_quantity=quantity,
                unit_price=str(item.get('unit_price', 0)),
                line_total=str(line_total)
            )

            # Build complete cart data for verification
            cart_items = []
            for idx, cart_item in enumerate(quotation_data.get('items', [])):
                item_unit_price = Decimal(str(cart_item.get('unit_price', 0)))
                item_margin_price = Decimal(str(cart_item.get('margin_75_price', 0))) if cart_item.get('margin_75_price') else Decimal('0')
                item_qty = int(cart_item.get('quantity', 0))
                item_line_total = item_unit_price * Decimal(str(item_qty))

                item_unit_discount = Decimal('0')
                item_total_discount = Decimal('0')
                item_discount_pct = 0

                if item_margin_price > 0 and item_margin_price > item_unit_price:
                    item_unit_discount = item_margin_price - item_unit_price
                    item_total_discount = item_unit_discount * Decimal(str(item_qty))
                    item_discount_pct = int(((item_margin_price - item_unit_price) / item_margin_price) * 100)

                cart_items.append({
                    'index': idx,
                    'product_name': cart_item.get('product_name', ''),
                    'quantity': item_qty,
                    'unit_price': str(item_unit_price),
                    'line_total': str(item_line_total),
                    'unit_discount': str(item_unit_discount),
                    'item_discount': str(item_total_discount),
                    'discount_percentage': item_discount_pct,
                })

            return JsonResponse({
                'success': True,
                'item_index': item_index,  # Index of updated item
                'line_total': str(line_total),
                'item_total': str(line_total),  # Alternative key for compatibility
                'unit_discount': str(unit_discount),
                'item_discount': str(item_discount),
                'discount_percentage': discount_percentage,
                'subtotal': str(totals['subtotal']),
                'tax': str(totals['tax_amount']),
                'tax_amount': str(totals['tax_amount']),
                'total': str(totals['total']),
                'total_savings': str(total_savings),
                'cart_items': cart_items,  # Complete cart for verification
                'total_items': len(cart_items),  # Total number of items in cart
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
                action_type='quotation_updated',
                description=f'Updated quotation: Removed item "{removed_item["product_name"]}" (Qty: {removed_item.get("quantity", 0)})',
                request=request,
                affected_model='QuotationItem',
                product_name=removed_item['product_name'],
                product_type=removed_item.get('product_type', 'unknown'),
                quantity=removed_item.get('quantity', 0),
                unit_price=str(removed_item.get('unit_price', 0))
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
                action_type='quotation_updated',
                description='Updated quotation: Cleared all items from cart',
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

            # Check if we're editing an existing quotation
            editing_quotation_id = quotation_data.get('editing_quotation_id')
            is_editing = editing_quotation_id is not None

            if is_editing:
                # Get existing quotation
                try:
                    quotation = Quotation.objects.get(pk=editing_quotation_id)

                    # Verify ownership
                    if not (quotation.created_by == request.user or
                            request.user.is_admin or
                            request.user.is_account_manager):
                        return JsonResponse({
                            'success': False,
                            'error': 'You do not have permission to edit this quotation.'
                        }, status=403)

                    # Verify quotation is not approved/confirmed
                    if quotation.status in ['approved', 'confirmed']:
                        return JsonResponse({
                            'success': False,
                            'error': 'Approved quotations cannot be edited.'
                        }, status=400)

                    # Validate change note is provided when editing
                    change_note = request.POST.get('change_note', '').strip()
                    if not change_note:
                        return JsonResponse({
                            'success': False,
                            'error': 'Please provide a note explaining the changes you made to this quotation.'
                        }, status=400)

                    # Delete existing quotation items
                    quotation.items.all().delete()

                    # Update recipient information if provided
                    recipient_name = request.POST.get('recipient_name', '').strip()
                    recipient_address = request.POST.get('recipient_address', '').strip()
                    additional_emails = request.POST.get('additional_emails', '').strip()

                    # Validate additional emails
                    is_valid, error_message = validate_additional_emails(additional_emails)
                    if not is_valid:
                        return JsonResponse({
                            'success': False,
                            'error': error_message
                        }, status=400)

                    if recipient_name:
                        quotation.recipient_name = recipient_name
                    if recipient_address:
                        quotation.recipient_address = recipient_address
                    quotation.additional_emails = additional_emails

                    # Update assigned sales rep and account manager if provided
                    from authentication.models import User

                    assigned_sales_rep_id = request.POST.get('assigned_sales_rep', '').strip()
                    assigned_sales_rep = None
                    if assigned_sales_rep_id:
                        try:
                            assigned_sales_rep = User.objects.get(pk=int(assigned_sales_rep_id))
                            # Validate user type
                            if assigned_sales_rep.user_type != 'sales_rep':
                                return JsonResponse({
                                    'success': False,
                                    'error': 'Selected user is not a sales representative'
                                }, status=400)
                        except (User.DoesNotExist, ValueError):
                            return JsonResponse({
                                'success': False,
                                'error': 'Invalid sales representative selected'
                            }, status=400)

                    # Auto-assign sales rep and account manager if not manually set
                    assignment_info = None
                    if not assigned_sales_rep:
                        assignment_info = get_assigned_staff_from_products(quotation_data.get('items', []))
                        if assignment_info.get('sales_rep'):
                            assigned_sales_rep = assignment_info['sales_rep']
                            logger.info(f"Auto-assigned sales rep for editing: {assigned_sales_rep.get_full_name()}")

                    quotation.assigned_sales_rep = assigned_sales_rep

                    account_manager_id = request.POST.get('account_manager', '').strip()
                    account_manager = None
                    if account_manager_id:
                        try:
                            account_manager = User.objects.get(pk=int(account_manager_id))
                            # Validate user type
                            if account_manager.user_type != 'account_manager':
                                return JsonResponse({
                                    'success': False,
                                    'error': 'Selected user is not an account manager'
                                }, status=400)
                        except (User.DoesNotExist, ValueError):
                            return JsonResponse({
                                'success': False,
                                'error': 'Invalid account manager selected'
                            }, status=400)

                    # Auto-assign account manager if not manually set
                    if not account_manager:
                        # Reuse assignment_info if already fetched, otherwise fetch it
                        if not assignment_info:
                            assignment_info = get_assigned_staff_from_products(quotation_data.get('items', []))
                        if assignment_info.get('account_manager'):
                            account_manager = assignment_info['account_manager']
                            logger.info(f"Auto-assigned account manager for editing: {account_manager.get_full_name()}")

                    quotation.account_manager = account_manager

                except Quotation.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Quotation not found.'
                    }, status=404)

            else:
                # Get institution from POST data (optional)
                institution_id_param = request.POST.get('institution_id', '').strip()
                institution = None
                institution_content_type = None

                if institution_id_param:
                    # Parse institution_id parameter (format: "institutiontype_id")
                    try:
                        institution_type, institution_id = institution_id_param.split('_', 1)
                        institution_id = int(institution_id)

                        # Get institution object
                        from schools.models_tus import TUSSchool

                        institution_models = {
                            'tusschool': TUSSchool,
                            'wholesaleschool': WholesaleSchool,
                            'lottoclub': LottoClub,
                            'sasclub': SASClub,
                        }
                        model_class = institution_models.get(institution_type.lower())
                        if not model_class:
                            return JsonResponse({
                                'success': False,
                                'error': 'Invalid institution type'
                            }, status=400)

                        try:
                            institution = model_class.objects.get(pk=institution_id)
                        except model_class.DoesNotExist:
                            return JsonResponse({
                                'success': False,
                                'error': 'Institution not found'
                            }, status=404)

                        # Verify user has access to this institution
                        if not user_can_access_institution(request.user, institution_type, institution_id):
                            return JsonResponse({
                                'success': False,
                                'error': 'You do not have permission to create quotations for this institution'
                            }, status=403)

                        # Get content type for institution
                        institution_content_type = ContentType.objects.get_for_model(institution)

                    except (ValueError, IndexError) as e:
                        return JsonResponse({
                            'success': False,
                            'error': 'Invalid institution ID format'
                        }, status=400)

                # Get recipient information from POST data
                recipient_name = request.POST.get('recipient_name', '').strip()
                recipient_address = request.POST.get('recipient_address', '').strip()
                additional_emails = request.POST.get('additional_emails', '').strip()

                # Validate additional emails
                is_valid, error_message = validate_additional_emails(additional_emails)
                if not is_valid:
                    return JsonResponse({
                        'success': False,
                        'error': error_message
                    }, status=400)

                # Get assigned sales rep and account manager from POST data or auto-assign
                from authentication.models import User
                assigned_sales_rep = None
                account_manager = None

                # Try to get from POST data first (for manual override)
                assigned_sales_rep_id = request.POST.get('assigned_sales_rep', '').strip()
                if assigned_sales_rep_id:
                    try:
                        assigned_sales_rep = User.objects.get(pk=int(assigned_sales_rep_id))
                        # Validate user type
                        if assigned_sales_rep.user_type != 'sales_rep':
                            return JsonResponse({
                                'success': False,
                                'error': 'Selected user is not a sales representative'
                            }, status=400)
                    except (User.DoesNotExist, ValueError):
                        return JsonResponse({
                            'success': False,
                            'error': 'Invalid sales representative selected'
                        }, status=400)

                account_manager_id = request.POST.get('account_manager', '').strip()
                if account_manager_id:
                    try:
                        account_manager = User.objects.get(pk=int(account_manager_id))
                        # Validate user type
                        if account_manager.user_type != 'account_manager':
                            return JsonResponse({
                                'success': False,
                                'error': 'Selected user is not an account manager'
                            }, status=400)
                    except (User.DoesNotExist, ValueError):
                        return JsonResponse({
                            'success': False,
                            'error': 'Invalid account manager selected'
                        }, status=400)

                # Auto-assign if not explicitly provided
                if not assigned_sales_rep or not account_manager:
                    assignment_info = get_assigned_staff_from_products(quotation_data.get('items', []))

                    # Use auto-assignment if not manually set
                    if not assigned_sales_rep and assignment_info.get('sales_rep'):
                        assigned_sales_rep = assignment_info['sales_rep']
                        logger.info(f"Auto-assigned sales rep: {assigned_sales_rep.get_full_name()}")

                    if not account_manager and assignment_info.get('account_manager'):
                        account_manager = assignment_info['account_manager']
                        logger.info(f"Auto-assigned account manager: {account_manager.get_full_name()}")

                # Create Quotation (with or without institution)
                quotation = Quotation.objects.create(
                    created_by=request.user,
                    institution_content_type=institution_content_type,
                    institution_object_id=institution.id if institution else None,
                    status='pending',  # Changed from 'draft' to 'pending' for approval workflow
                    recipient_name=recipient_name,
                    recipient_address=recipient_address,
                    additional_emails=additional_emails,
                    assigned_sales_rep=assigned_sales_rep,
                    account_manager=account_manager,
                )

            # Create QuotationItems (for both new and edited quotations)
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
                if not is_editing:
                    quotation.delete()
                return JsonResponse({
                    'success': False,
                    'error': 'No valid products found in your cart. Please try again.'
                }, status=400)

            # Calculate quotation totals
            quotation.calculate_totals()

            # Create version snapshot for edited quotations
            if is_editing:
                try:
                    quotation.create_edit_snapshot(
                        user=request.user,
                        change_note=change_note,
                        description=f'Edited by {request.user.get_full_name()}: {items_created} items'
                    )
                except ValueError as e:
                    return JsonResponse({
                        'success': False,
                        'error': str(e)
                    }, status=400)

            # Clear session
            clear_quotation_session(request)

            # Send email notification
            from .emails import send_quotation_email

            try:
                email_success, email_error = send_quotation_email(
                    quotation=quotation,
                    is_update=is_editing,
                    request=request
                )

                if not email_success:
                    logger.warning(f"Email send failed for {quotation.quotation_number}: {email_error}")
                    # Continue with quotation creation even if email fails
            except Exception as e:
                logger.error(f"Unexpected error sending email for {quotation.quotation_number}: {e}", exc_info=True)
                # Continue with quotation creation even if email fails

            # Log action
            if is_editing:
                action_type = 'quotation_updated'
                action_description = f'Updated quotation {quotation.quotation_number} with {items_created} items. Change note: {change_note}'
            else:
                action_type = 'quotation_created'
                action_description = f'Created quotation {quotation.quotation_number} with {items_created} items'

            AuditLog.log_action(
                user=request.user,
                action_type=action_type,
                description=action_description,
                request=request,
                affected_model='Quotation',
                affected_object_id=str(quotation.id),
                quotation_id=str(quotation.id),
                quotation_number=quotation.quotation_number,
                item_count=items_created,
                institution_id=quotation.institution_object_id if quotation.institution else None,
                institution_type=quotation.institution_content_type.model if quotation.institution_content_type else None,
                status=quotation.status,
                total_amount=str(quotation.total)
            )

            success_message = f'Quotation {quotation.quotation_number} updated successfully!' if is_editing else f'Quotation {quotation.quotation_number} generated successfully!'

            return JsonResponse({
                'success': True,
                'quotation_id': str(quotation.id),
                'quotation_number': quotation.quotation_number,
                'item_count': items_created,
                'total_amount': str(quotation.total),
                'redirect_url': reverse('quotations:quotation-preview', kwargs={'pk': quotation.id}),
                'message': success_message
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
        from django.db.models import Case, When, Value, BooleanField, OuterRef, Subquery
        from quotations.models import QuotationVersion

        # Subquery to get the latest change note for each quotation
        latest_change_note = QuotationVersion.objects.filter(
            quotation=OuterRef('pk')
        ).order_by('-version_number').values('change_note')[:1]

        queryset = Quotation.objects.filter(
            created_by=self.request.user
        ).select_related(
            'created_by',
            'approved_by',
            'rejected_by'
        ).prefetch_related('items').annotate(
            is_edited=Case(
                When(version__gt=1, then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            ),
            latest_change_note=Subquery(latest_change_note)
        )

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
# EDIT QUOTATION VIEW
# =====================================

class EditQuotationView(LoginRequiredMixin, View):
    """
    Edit an existing quotation by loading it into the session cart.
    Only allows editing of unapproved quotations (draft, pending, rejected).
    """

    def get(self, request, pk):
        try:
            # Get the quotation
            quotation = get_object_or_404(Quotation, pk=pk)

            # Check ownership (user must own the quotation or be admin/account manager)
            if not (quotation.created_by == request.user or
                    request.user.is_admin or
                    request.user.is_account_manager):
                messages.error(request, 'You do not have permission to edit this quotation.')
                return redirect('quotations:my-quotations')

            # Check if quotation is approved/confirmed - these cannot be edited
            if quotation.status in ['approved', 'confirmed']:
                messages.error(request, 'Approved quotations cannot be edited.')
                return redirect('quotations:quotation-detail', pk=quotation.id)

            # Clear any existing cart session
            clear_quotation_session(request)

            # Load quotation into session
            quotation_data = {
                'editing_quotation_id': str(quotation.id),  # Track that we're editing
                'items': [],
                'institution_type': None,
                'institution_id': None,
            }

            # Set institution data if exists
            if quotation.institution:
                quotation_data['institution_type'] = quotation.institution_content_type.model
                quotation_data['institution_id'] = quotation.institution_object_id

            # Load quotation items into session
            for item in quotation.items.all():
                quotation_data['items'].append({
                    'product_type': item.product_content_type.model,
                    'product_id': item.product_object_id,
                    'product_name': item.product_name,
                    'product_sku': item.product_sku,
                    'quantity': item.quantity,
                    'unit_price': str(item.unit_price),
                    'margin_75_price': '',  # Will be populated if available
                    'variations': item.variations,
                })

            # Save to session
            save_quotation_session(request, quotation_data)

            # Log action
            AuditLog.log_action(
                user=request.user,
                action_type='quotation_updated',
                description=f'Updated quotation: Started editing quotation {quotation.quotation_number}',
                request=request,
                affected_model='Quotation',
                affected_object_id=str(quotation.id),
                quotation_id=str(quotation.id),
                quotation_number=quotation.quotation_number,
                status=quotation.status,
                institution_id=quotation.institution_object_id if quotation.institution else None,
                institution_type=quotation.institution_content_type.model if quotation.institution_content_type else None
            )

            messages.success(request, f'Quotation {quotation.quotation_number} loaded for editing.')
            return redirect('quotations:cart')

        except Exception as e:
            logger.error(f"Error loading quotation for editing: {e}")
            messages.error(request, 'An error occurred while loading the quotation for editing.')
            return redirect('quotations:my-quotations')


# =====================================
# QUOTATION HISTORY VIEW
# =====================================

class QuotationHistoryView(LoginRequiredMixin, View):
    """
    View quotation edit history and version snapshots.
    Shows all versions with change notes and diffs.
    """

    def get(self, request, pk):
        try:
            # Get the quotation
            quotation = get_object_or_404(Quotation, pk=pk)

            # Check ownership (user must own the quotation or be admin/account manager)
            if not (quotation.created_by == request.user or
                    request.user.is_admin or
                    request.user.is_account_manager):
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to view this quotation history.'
                }, status=403)

            # Get all versions
            versions = quotation.get_version_history()

            # Build version data with diffs
            version_data = []
            previous_snapshot = None

            for version in versions:
                current_snapshot = version.snapshot_data

                # Calculate differences from previous version
                diff_info = None
                if previous_snapshot:
                    diff_info = self._calculate_diff(previous_snapshot, current_snapshot)

                version_data.append({
                    'version_number': version.version_number,
                    'created_at': version.created_at.isoformat(),
                    'created_by': {
                        'id': version.created_by.id if version.created_by else None,
                        'name': version.created_by.get_full_name() if version.created_by else 'System',
                        'email': version.created_by.email if version.created_by else None,
                    },
                    'change_description': version.change_description,
                    'change_note': version.change_note,
                    'snapshot': current_snapshot,
                    'diff': diff_info
                })

                previous_snapshot = current_snapshot

            # Transform version_data to match frontend expectations
            history_data = []
            for v_data in version_data:
                # Calculate items changes summary
                items_added = 0
                items_removed = 0
                items_modified = 0

                if v_data['diff']:
                    for change in v_data['diff'].get('changes', []):
                        if change['field'] == 'item_count':
                            diff = change['new_value'] - change['old_value']
                            if diff > 0:
                                items_added = diff
                            else:
                                items_removed = abs(diff)
                        elif change['field'].startswith('item_') and '_' in change['field']:
                            items_modified += 1

                history_entry = {
                    'version': v_data['version_number'],
                    'date': v_data['created_at'],
                    'user': v_data['created_by']['name'],
                    'note': v_data['change_note'] or v_data['change_description'] or 'No note provided',
                    'changes': {
                        'items_added': items_added,
                        'items_removed': items_removed,
                        'items_modified': items_modified if items_modified > 0 else len(v_data['snapshot'].get('items', [])),
                        'pricing_changed': v_data['diff']['pricing_changed'] if v_data['diff'] else False,
                        'old_total': None,
                        'new_total': v_data['snapshot'].get('total', '0.00'),
                        'discount_changed': False
                    }
                }

                # Extract old total from diff if available
                if v_data['diff']:
                    for change in v_data['diff'].get('changes', []):
                        if change['field'] == 'total':
                            history_entry['changes']['old_total'] = change.get('old_value')
                        elif change['field'] in ['discount_percentage', 'discount_amount']:
                            history_entry['changes']['discount_changed'] = True

                history_data.append(history_entry)

            return JsonResponse({
                'success': True,
                'quotation_number': quotation.quotation_number,
                'current_version': quotation.version,
                'total_versions': len(history_data),
                'history': history_data  # Changed from 'versions' to 'history' for frontend compatibility
            })

        except Exception as e:
            logger.error(f"Error retrieving quotation history: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while retrieving quotation history.'
            }, status=500)

    def _calculate_diff(self, old_snapshot, new_snapshot):
        """
        Calculate differences between two version snapshots

        Args:
            old_snapshot: Previous version snapshot data
            new_snapshot: Current version snapshot data

        Returns:
            dict: Differences organized by category
        """
        diff = {
            'status_changed': old_snapshot.get('status') != new_snapshot.get('status'),
            'pricing_changed': False,
            'items_changed': False,
            'changes': []
        }

        # Check status change
        if diff['status_changed']:
            diff['changes'].append({
                'field': 'status',
                'old_value': old_snapshot.get('status'),
                'new_value': new_snapshot.get('status')
            })

        # Check pricing changes
        pricing_fields = ['subtotal', 'discount_percentage', 'discount_amount', 'tax_percentage', 'tax_amount', 'total']
        for field in pricing_fields:
            old_value = old_snapshot.get(field)
            new_value = new_snapshot.get(field)
            if old_value != new_value:
                diff['pricing_changed'] = True
                diff['changes'].append({
                    'field': field,
                    'old_value': old_value,
                    'new_value': new_value
                })

        # Check items changes
        old_items = old_snapshot.get('items', [])
        new_items = new_snapshot.get('items', [])

        if len(old_items) != len(new_items):
            diff['items_changed'] = True
            diff['changes'].append({
                'field': 'item_count',
                'old_value': len(old_items),
                'new_value': len(new_items)
            })
        else:
            # Compare individual items
            for i, (old_item, new_item) in enumerate(zip(old_items, new_items)):
                for key in ['product_name', 'quantity', 'unit_price', 'line_total']:
                    if old_item.get(key) != new_item.get(key):
                        diff['items_changed'] = True
                        diff['changes'].append({
                            'field': f'item_{i+1}_{key}',
                            'old_value': old_item.get(key),
                            'new_value': new_item.get(key)
                        })

        return diff


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
        from .models import SiteSettings
        from decimal import Decimal

        context = super().get_context_data(**kwargs)
        context['items'] = self.object.items.all().select_related('product_content_type').order_by('sort_order', 'created_at')

        # Calculate discount amount
        if self.object.discount_percentage:
            context['discount_amount'] = (self.object.subtotal * self.object.discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
        else:
            context['discount_amount'] = self.object.discount_amount

        # Get quotation validity days from settings
        settings = SiteSettings.objects.get_settings()
        context['quotation_validity_days'] = settings.quotation_validity_days

        # Split additional emails into a list for template iteration
        if self.object.additional_emails:
            context['additional_emails_list'] = [
                email.strip()
                for email in self.object.additional_emails.split(';')
                if email.strip()
            ]
        else:
            context['additional_emails_list'] = []

        # Log quotation view
        AuditLog.log_action(
            user=self.request.user,
            action_type='quotation_viewed',
            description=f'Viewed quotation {self.object.quotation_number}',
            request=self.request,
            affected_model='Quotation',
            affected_object_id=str(self.object.id),
            quotation_id=str(self.object.id),
            quotation_number=self.object.quotation_number,
            status=self.object.status
        )

        return context


# =====================================
# QUOTATION PREVIEW VIEW
# =====================================

class QuotationPreviewView(LoginRequiredMixin, DetailView):
    """
    Preview quotation with professional invoice-style design.
    Accessible by quotation creator and admin/account managers.
    """
    model = Quotation
    template_name = 'quotations/quotation_preview.html'
    context_object_name = 'quotation'

    def get_queryset(self):
        """Ensure user can only view their own quotations (or all if admin/account manager)"""
        if self.request.user.is_admin or self.request.user.is_account_manager:
            return Quotation.objects.all()
        return Quotation.objects.filter(created_by=self.request.user)

    def get_context_data(self, **kwargs):
        from .models import SiteSettings

        context = super().get_context_data(**kwargs)

        # Get quotation items with product details
        context['items'] = self.object.items.all().select_related('product_content_type').order_by('sort_order', 'created_at')

        # Company details
        context['company'] = {
            'name': 'SAS CORPORATE',
            'address': '521 ROSEBANK ROAD, AVONDALE, AUCKLAND, NEW ZEALAND',
            'email': 'CUSTOMERSERVICES@SAS.CO.NZ',
            'phone': '09 2998412',
            'logo': 'assets/images/logo-dark.png'
        }

        # Calculate subtotal before discount
        context['subtotal_before_discount'] = self.object.subtotal

        # Calculate discount amount
        if self.object.discount_percentage:
            context['discount_amount'] = (self.object.subtotal * self.object.discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
        else:
            context['discount_amount'] = self.object.discount_amount

        # Calculate taxable amount (subtotal - discount)
        context['taxable_amount'] = self.object.subtotal - context['discount_amount']

        # Get quotation validity days from settings
        settings = SiteSettings.objects.get_settings()
        context['quotation_validity_days'] = settings.quotation_validity_days

        return context


# =====================================
# NEW QUOTATION PAGE - TAB-BASED PRODUCT SELECTION
# =====================================

class ProductDetailForQuotationView(LoginRequiredMixin, SalesRepOrAccountManagerOrCustomerMixin, DetailView):
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
                    var_data['sku'] = getattr(variation, 'sku_suffix', '')

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
                    # Round margin price to nearest $5
                    rounded_margin_price = round_to_nearest_5(margin_price)

                    # Use rounded margin price for all calculations
                    var_data['margin_75_price'] = str(rounded_margin_price)
                    discount_amount = rounded_margin_price - selling_price
                    discount_percentage = (discount_amount / rounded_margin_price * 100).quantize(Decimal('0'))
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

            elif product_type.lower() == 'ballstoreproduct':
                # BallStore products are generic products
                return "BallStore"

        except Exception as e:
            logger.error(f"Error getting institution name: {e}")

        return "Unknown Institution"


class NewQuotationView(LoginRequiredMixin, SalesRepOrAccountManagerOrCustomerMixin, View):
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

        # Get category type filter (for tile navigation)
        category_type_filter = request.GET.get('category_type', '')

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
                        Q(variations__sku__icontains=search_query) |  # Search in variation SKUs
                        Q(category_assignments__school_category__name__icontains=search_query) |  # School category name
                        Q(category_assignments__general_category__name__icontains=search_query) |  # General category name
                        Q(category_assignments__school_category__school__name__icontains=search_query) |  # School name
                        Q(category_assignments__school_category__school__location__name__icontains=search_query) |  # Location name
                        Q(category_assignments__school_category__school__address__icontains=search_query)  # Address
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
                        Q(variations__cin7_sku__icontains=search_query) |  # Search in variation SKUs
                        Q(category_assignments__category__name__icontains=search_query) |  # Category name
                        Q(school__name__icontains=search_query) |  # School name
                        Q(school__city__icontains=search_query) |  # City
                        Q(school__address_line1__icontains=search_query) |  # Address line 1
                        Q(school__address_line2__icontains=search_query)  # Address line 2
                    ).distinct()  # Use distinct() to avoid duplicates from variation joins

            # PERFORMANCE OPTIMIZATION: Paginate BEFORE processing variations
            # Convert to lists and merge (since they're different models)
            tus_products_list = list(tus_products_qs)
            wholesale_products_list = list(wholesale_products_qs)

            # Group wholesale products by base SKU BEFORE pagination
            grouped_wholesale_products = self._group_wholesale_products_by_base_sku(wholesale_products_list)

            # Combine and paginate FIRST (before variation processing)
            combined_products = tus_products_list + grouped_wholesale_products
            paginator = Paginator(combined_products, self.paginate_by)
            try:
                page_obj = paginator.get_page(page)
            except PageNotAnInteger:
                page_obj = paginator.get_page(1)
            except EmptyPage:
                page_obj = paginator.get_page(paginator.num_pages)

            is_paginated = paginator.num_pages > 1

            # ONLY process variations for products on CURRENT PAGE (24 products instead of ALL)
            for product in page_obj.object_list:
                if not hasattr(product, 'product_type'):
                    # Determine product type by model class
                    if product.__class__.__name__ == 'TUSProduct':
                        product.product_type = 'tusproduct'
                        # Fetch variations only for displayed products
                        if product.has_variations:
                            variations = list(product.variations.all())
                            product.variation_display = self._get_variation_display_data(variations, 'tus')
                        else:
                            product.variation_display = {}
                    elif product.__class__.__name__ == 'WholesaleProduct':
                        product.product_type = 'wholesaleproduct'
                        # Fetch variations only for displayed products
                        if product.has_variations:
                            variations = list(product.variations.filter(is_active=True))
                            product.variation_display = self._get_variation_display_data(variations, 'wholesale')
                        else:
                            product.variation_display = {}

        # ========================================
        # CLUBS TAB - SAS Clubs and LOTTO Clubs
        # ========================================
        elif active_tab == 'clubs':
            from django.db.models import Exists, OuterRef, Q as QOuter
            from clubs.models_sas import SASProductVariation
            from clubs.models_lotto import LottoProductVariation

            # Get assigned clubs (EXCLUDE generic categories/shops - they go to accessories tab)
            if request.user.is_admin or request.user.is_account_manager:
                # Admin and account managers have access to all clubs (excluding generic)
                sas_clubs = SASClub.objects.filter(is_active=True, is_generic_category=False)
                lotto_clubs = LottoClub.objects.filter(is_active=True, is_generic_shop=False)
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

                sas_clubs = SASClub.objects.filter(id__in=sas_club_ids, is_generic_category=False)
                lotto_clubs = LottoClub.objects.filter(id__in=lotto_club_ids, is_generic_shop=False)
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
                    Q(variations__sku_suffix__icontains=search_query) |  # Search in variation SKU suffix
                    Q(club__name__icontains=search_query) |  # Club name (acts as category)
                    Q(club__sport__name__icontains=search_query) |  # Sport name (parent category)
                    Q(club__city__icontains=search_query) |  # City
                    Q(club__province__icontains=search_query) |  # Province
                    Q(club__address__icontains=search_query)  # Address
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
                    Q(variations__sku_suffix__icontains=search_query) |  # Search in variation SKU suffix
                    Q(category__name__icontains=search_query) |  # Category name
                    Q(category__club__name__icontains=search_query) |  # Club name
                    Q(category__club__address__icontains=search_query)  # Address
                ).distinct()

            # PERFORMANCE OPTIMIZATION: Paginate BEFORE processing variations
            # Convert to lists and merge (since they're different models)
            sas_products_list = list(sas_products_qs)
            lotto_products_list = list(lotto_products_qs)

            # Combine and paginate FIRST (before variation processing)
            combined_products = sas_products_list + lotto_products_list
            paginator = Paginator(combined_products, self.paginate_by)
            try:
                page_obj = paginator.get_page(page)
            except PageNotAnInteger:
                page_obj = paginator.get_page(1)
            except EmptyPage:
                page_obj = paginator.get_page(paginator.num_pages)

            is_paginated = paginator.num_pages > 1

            # ONLY process variations for products on CURRENT PAGE (24 products instead of ALL)
            for product in page_obj.object_list:
                # Determine product type by model class
                if product.__class__.__name__ == 'SASProduct':
                    product.product_type = 'sasproduct'
                    # Fetch variations only for displayed products
                    if product.has_variations:
                        variations = list(product.variations.filter(is_active=True))
                        product.variation_display = self._get_variation_display_data(variations, 'sas')
                    else:
                        product.variation_display = {}
                elif product.__class__.__name__ == 'LottoProduct':
                    product.product_type = 'lottoproduct'
                    # Fetch variations only for displayed products
                    if product.has_variations:
                        variations = list(product.variations.filter(is_active=True))
                        product.variation_display = self._get_variation_display_data(variations, 'lotto')
                    else:
                        product.variation_display = {}

        # ========================================
        # ACCESSORIES TAB - Generic Products Only (SAS Generic + LOTTO Generic Shop + BallStore)
        # ========================================
        elif active_tab == 'accessories':
            from django.db.models import Exists, OuterRef, Q as QOuter
            from clubs.models_sas import SASProductVariation
            from clubs.models_lotto import LottoProductVariation
            from ballstore.models import BallStoreProduct, BallStoreProductVariation

            # Get ONLY generic categories/shops - these are available to all users
            # Generic products are not club-specific, so we don't filter by user assignments
            sas_generic_clubs = SASClub.objects.filter(is_active=True, is_generic_category=True)
            lotto_generic_clubs = LottoClub.objects.filter(is_active=True, is_generic_shop=True)

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

            # Get SAS Generic Products with stock filtering
            sas_products_qs = SASProduct.objects.filter(
                club__in=sas_generic_clubs,
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
                    Q(variations__sku_suffix__icontains=search_query) |  # Search in variation SKU suffix
                    Q(club__name__icontains=search_query) |  # Club name (acts as category)
                    Q(club__sport__name__icontains=search_query) |  # Sport name (parent category)
                    Q(club__city__icontains=search_query) |  # City
                    Q(club__province__icontains=search_query) |  # Province
                    Q(club__address__icontains=search_query)  # Address
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

            # Get LOTTO Generic Products with stock filtering
            lotto_products_qs = LottoProduct.objects.filter(
                category__club__in=lotto_generic_clubs,
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
                    Q(variations__sku_suffix__icontains=search_query) |  # Search in variation SKU suffix
                    Q(category__name__icontains=search_query) |  # Category name
                    Q(category__club__name__icontains=search_query) |  # Club name
                    Q(category__club__address__icontains=search_query)  # Address
                ).distinct()

            # Stock filtering for BallStore Products:
            # - If product is variable type: At least ONE variation must have stock_quantity > 0
            # - If product is simple type: Base product must have stock_status in ['instock', 'onbackorder']

            # Subquery to check if product has at least one variation with stock
            has_stock_variation_ballstore = Exists(
                BallStoreProductVariation.objects.filter(
                    parent_product=OuterRef('pk'),
                    is_active=True,
                    stock_quantity__gt=0
                )
            )

            # Get BallStore Products with stock filtering
            ballstore_products_qs = BallStoreProduct.objects.filter(
                is_active=True
            ).annotate(
                has_stock_variation=has_stock_variation_ballstore
            ).filter(
                # Filter: (variable type AND has stock in at least one variation) OR
                #         (simple type AND product stock_status is instock/onbackorder)
                QOuter(
                    QOuter(product_type='variable', has_stock_variation=True) |
                    QOuter(product_type='simple', stock_status__in=['instock', 'onbackorder'])
                )
            ).prefetch_related('variations', 'categories')

            # Apply search filter
            if search_query:
                ballstore_products_qs = ballstore_products_qs.filter(
                    Q(name__icontains=search_query) |
                    Q(sku__icontains=search_query) |
                    Q(description__icontains=search_query) |
                    Q(short_description__icontains=search_query) |
                    Q(variations__sku__icontains=search_query) |  # Search in variation SKU
                    Q(categories__name__icontains=search_query)  # Category name
                ).distinct()

            # PERFORMANCE OPTIMIZATION: Paginate BEFORE processing variations
            # Convert to lists and merge (since they're different models)
            sas_products_list = list(sas_products_qs)
            lotto_products_list = list(lotto_products_qs)
            ballstore_products_list = list(ballstore_products_qs)

            # Combine and paginate FIRST (before variation processing)
            combined_products = sas_products_list + lotto_products_list + ballstore_products_list
            paginator = Paginator(combined_products, self.paginate_by)
            try:
                page_obj = paginator.get_page(page)
            except PageNotAnInteger:
                page_obj = paginator.get_page(1)
            except EmptyPage:
                page_obj = paginator.get_page(paginator.num_pages)

            is_paginated = paginator.num_pages > 1

            # ONLY process variations for products on CURRENT PAGE (24 products instead of ALL)
            for product in page_obj.object_list:
                # Determine product type by model class
                if product.__class__.__name__ == 'SASProduct':
                    product.product_type = 'sasproduct'
                    # Fetch variations only for displayed products
                    if product.has_variations:
                        variations = list(product.variations.filter(is_active=True))
                        product.variation_display = self._get_variation_display_data(variations, 'sas')
                    else:
                        product.variation_display = {}
                elif product.__class__.__name__ == 'LottoProduct':
                    product.product_type = 'lottoproduct'
                    # Fetch variations only for displayed products
                    if product.has_variations:
                        variations = list(product.variations.filter(is_active=True))
                        product.variation_display = self._get_variation_display_data(variations, 'lotto')
                    else:
                        product.variation_display = {}
                elif product.__class__.__name__ == 'BallStoreProduct':
                    product.product_type = 'ballstoreproduct'
                    # Fetch variations only for displayed products
                    if product.product_type == 'variable':
                        variations = list(product.variations.filter(is_active=True))
                        product.variation_display = self._get_variation_display_data(variations, 'ballstore')
                    else:
                        product.variation_display = {}

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

        # Category grouping disabled for all tabs - show flat product list instead
        use_category_grouping = False
        grouped_products = None
        grouped_products_page_obj = None
        grouped_products_is_paginated = False

        if use_category_grouping:
            # Use category TYPE grouping (Apparel, Accessories, etc.) instead of specific categories
            # Group ALL products (not just current page) to show all category tiles
            all_grouped_products = self._group_products_by_category_type(combined_products)

            # DEBUG: Log category type mapping
            logger.info(f"DEBUG: Total products for category grouping: {len(combined_products)}")
            logger.info(f"DEBUG: Category types found: {list(all_grouped_products.keys())}")
            for cat_type, cat_data in all_grouped_products.items():
                logger.info(f"DEBUG:   - {cat_type}: {cat_data['count']} products")

            # Paginate the category tiles themselves (10 tiles per page)
            tiles_per_page = 10
            grouped_items_list = list(all_grouped_products.items())
            grouped_paginator = Paginator(grouped_items_list, tiles_per_page)

            try:
                grouped_products_page_obj = grouped_paginator.get_page(page)
            except PageNotAnInteger:
                grouped_products_page_obj = grouped_paginator.get_page(1)
            except EmptyPage:
                grouped_products_page_obj = grouped_paginator.get_page(grouped_paginator.num_pages)

            grouped_products_is_paginated = grouped_paginator.num_pages > 1

            # Convert back to OrderedDict for template compatibility
            from collections import OrderedDict
            grouped_products = OrderedDict(grouped_products_page_obj.object_list)

        # If category type filter is active, filter products by that type
        filtered_by_category_type = False
        if category_type_filter and page_obj:
            # Filter products by category type
            filtered_products = []
            for product in page_obj.object_list:
                category_info = self._get_category_info(product)
                if category_info:
                    cat_type, _ = self._get_category_type_mapping(category_info['name'])
                    cat_type_key = cat_type.lower().replace(' ', '_')
                    if cat_type_key == category_type_filter.lower():
                        filtered_products.append(product)

            # Replace page_obj with filtered results
            if filtered_products:
                paginator = Paginator(filtered_products, self.paginate_by)
                try:
                    page_obj = paginator.get_page(page)
                except PageNotAnInteger:
                    page_obj = paginator.get_page(1)
                except EmptyPage:
                    page_obj = paginator.get_page(paginator.num_pages)
                is_paginated = paginator.num_pages > 1
                filtered_by_category_type = True

        context = {
            'active_tab': active_tab,
            'search_query': search_query,
            'category_type_filter': category_type_filter,
            'category_type_display': category_type_filter.replace('_', ' ').title() if category_type_filter else '',
            'filtered_by_category_type': filtered_by_category_type,

            # Category grouping (when search is active)
            'use_category_grouping': use_category_grouping,
            'grouped_products': grouped_products,
            'grouped_products_page_obj': grouped_products_page_obj,
            'grouped_products_is_paginated': grouped_products_is_paginated,

            # Paginated products (flat list when not searching)
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

            # Handle BallStore variations (which use attributes JSON field)
            if product_type.lower() == 'ballstore':
                attributes = getattr(variation, 'attributes', [])
                if isinstance(attributes, list):
                    for attr in attributes:
                        if isinstance(attr, dict):
                            attr_name = attr.get('name', '').lower()
                            attr_option = attr.get('option', '')

                            if attr_name in ['size', 'pa_size']:
                                sizes.add(attr_option)
                            elif attr_name in ['color', 'colour', 'pa_color', 'pa_colour']:
                                colors.add(attr_option)
            else:
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
                # SASProductVariation and LottoProductVariation have 'sku_suffix' field
                sku = getattr(variation, 'sku_suffix', None)
            elif product_type.lower() == 'ballstore':
                # BallStoreProductVariation has 'sku' field
                sku = getattr(variation, 'sku', None)

            # Add SKU to list if it exists
            if sku:
                # For BallStore, create variation label from attributes
                if product_type.lower() == 'ballstore':
                    attributes = getattr(variation, 'attributes', [])
                    attr_values = []
                    if isinstance(attributes, list):
                        for attr in attributes:
                            if isinstance(attr, dict):
                                attr_values.append(attr.get('option', ''))
                    variation_label = ' - '.join(attr_values) if attr_values else var_value
                else:
                    variation_label = var_value

                skus.append({
                    'sku': sku,
                    'variation': variation_label,
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

    def _get_category_info(self, product):
        """
        Extract category information from product based on type.

        Returns dict with keys:
        - key: unique identifier for grouping
        - id: category object id
        - name: category name
        - category_type: type identifier
        - display_name: name for display headers
        - institution: school/club name
        - institution_type: tus_school, sas_club, lotto_club, wholesale_school
        - order: sort order
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            # Check product type using class name instead of product_type attribute
            product_class_name = product.__class__.__name__.lower()

            if product_class_name == 'tusproduct' or getattr(product, 'product_type', '') == 'tusproduct':
                # TUS Products: school_category -> school
                if hasattr(product, 'primary_category_assignment') and product.primary_category_assignment:
                    school_category = product.primary_category_assignment.school_category
                    if school_category:
                        school = school_category.school
                        return {
                            'key': f'tus_school_category_{school_category.id}',
                            'id': school_category.id,
                            'name': school_category.name,
                            'category_type': 'tus_school_category',
                            'display_name': school_category.name,
                            'institution': school.name if school else 'Unknown School',
                            'institution_type': 'tus_school',
                            'order': school.id if school else 999
                        }
                return None

            elif product_class_name == 'wholesaleproduct' or getattr(product, 'product_type', '') == 'wholesaleproduct':
                # Wholesale Products: school (acts as category)
                if hasattr(product, 'school') and product.school:
                    return {
                        'key': f'wholesale_school_{product.school.id}',
                        'id': product.school.id,
                        'name': product.school.name,
                        'category_type': 'wholesale_school',
                        'display_name': product.school.name,
                        'institution': product.school.name,
                        'institution_type': 'wholesale_school',
                        'order': product.school.id
                    }
                return None

            elif product_class_name == 'sasproduct' or getattr(product, 'product_type', '') == 'sasproduct':
                # SAS Products: club (acts as category)
                if hasattr(product, 'club') and product.club:
                    return {
                        'key': f'sas_club_{product.club.id}',
                        'id': product.club.id,
                        'name': product.club.name,
                        'category_type': 'sas_club',
                        'display_name': product.club.name,
                        'institution': f"SAS - {product.club.name}",
                        'institution_type': 'sas_club',
                        'order': product.club.id
                    }
                return None

            elif product_class_name == 'lottoproduct' or getattr(product, 'product_type', '') == 'lottoproduct':
                # LOTTO Products: category -> club
                if hasattr(product, 'category') and product.category:
                    category = product.category
                    club = category.club if hasattr(category, 'club') else None
                    return {
                        'key': f'lotto_category_{category.id}',
                        'id': category.id,
                        'name': category.name,
                        'category_type': 'lotto_category',
                        'display_name': category.name,
                        'institution': f"LOTTO - {club.name}" if club else 'Unknown Club',
                        'institution_type': 'lotto_club',
                        'order': category.id
                    }
                return None

        except Exception as e:
            logger.error(f"Error extracting category info from product {product}: {e}")

        return None

    def _get_category_type_mapping(self, category_name, product_name=None):
        """
        Map specific category names to generic category types.
        Falls back to product name analysis if category name doesn't match.

        SPECIAL RULE: All club/federation categories (containing "club", "federation", "referee")
        are automatically mapped to "Apparel" regardless of product name.

        Returns tuple: (category_type, icon_class)
        """
        category_name_lower = category_name.lower()

        # Try product name if provided
        product_name_lower = product_name.lower() if product_name else ''

        # PRIORITY 1: Check if this is a club/federation/referee category
        # These should ALL go to Apparel tile
        club_indicators = ['club', 'federation', 'referee', 'school football', 'regional football']
        if any(indicator in category_name_lower for indicator in club_indicators):
            return ('Apparel', 'mdi-tshirt-crew')

        # PRIORITY 2: Generic categories get their own tiles
        # Apparel categories (only for generic "Apparel" category)
        apparel_terms = [
            'apparel', 'clothing', 'shirt', 'polo', 'jersey', 'hoodie',
            'jacket', 'fleece', 'top', 'bottom', 'pant', 'short', 'tracksuit',
            'uniform', 'kit', 'sweater', 'vest', 'tee', 't-shirt'
        ]
        if (any(term in category_name_lower for term in apparel_terms) or
            any(term in product_name_lower for term in apparel_terms)):
            return ('Apparel', 'mdi-tshirt-crew')

        # Accessories categories
        accessories_terms = [
            'accessories', 'accessory', 'bag', 'backpack', 'hat', 'cap',
            'sock', 'glove', 'scarf', 'beanie', 'headband', 'wristband', 'water bottle'
        ]
        if (any(term in category_name_lower for term in accessories_terms) or
            any(term in product_name_lower for term in accessories_terms)):
            return ('Accessories', 'mdi-shopping')

        # Footballs specific (check before Equipment since it's more specific)
        football_terms = ['football', 'soccer ball']
        if (any(term in category_name_lower for term in football_terms) or
            any(term in product_name_lower for term in football_terms)):
            return ('Footballs', 'mdi-soccer')

        # Equipment categories
        equipment_terms = [
            'equipment', 'ball', 'goal', 'net', 'training', 'cone', 'marker',
            'whistle', 'pump', 'kit bag', 'medical', 'first aid'
        ]
        if (any(term in category_name_lower for term in equipment_terms) or
            any(term in product_name_lower for term in equipment_terms)):
            return ('Equipment', 'mdi-soccer')

        # Footwear categories
        footwear_terms = [
            'footwear', 'boot', 'shoe', 'cleat', 'trainer', 'sneaker'
        ]
        if (any(term in category_name_lower for term in footwear_terms) or
            any(term in product_name_lower for term in footwear_terms)):
            return ('Footwear', 'mdi-shoe-cleat')

        # Protective gear
        protective_terms = [
            'protective', 'guard', 'pad', 'helmet', 'shin', 'knee', 'elbow'
        ]
        if (any(term in category_name_lower for term in protective_terms) or
            any(term in product_name_lower for term in protective_terms)):
            return ('Protective Gear', 'mdi-shield')

        # Other/Uncategorized
        return ('Other', 'mdi-package-variant')

    def _group_products_by_category_type(self, products):
        """
        Group products by generic category type (Apparel, Accessories, Equipment, etc.)
        Returns OrderedDict of category type groups with product count and sample products.

        Format:
        {
            'apparel': {
                'name': 'Apparel',
                'icon': 'mdi-tshirt-crew',
                'count': 25,
                'products': [...],
                'order': 1
            }
        }
        """
        import logging
        from collections import OrderedDict, defaultdict

        logger = logging.getLogger(__name__)
        grouped = defaultdict(lambda: {
            'products': [],
            'count': 0
        })

        # Track products without categories
        products_without_category = 0

        # Map products to category types
        for product in products:
            category_info = self._get_category_info(product)

            if category_info:
                # Pass product name to help with category type mapping
                product_name = getattr(product, 'name', '')
                category_type, icon = self._get_category_type_mapping(
                    category_info['name'],
                    product_name=product_name
                )
                key = category_type.lower().replace(' ', '_')

                # DEBUG: Log first few mappings
                if len(grouped[key]['products']) < 3:
                    logger.info(f"DEBUG: Product '{product.name[:50]}' -> category '{category_info['name']}' -> type '{category_type}'")

                if not grouped[key].get('name'):
                    grouped[key]['name'] = category_type
                    grouped[key]['icon'] = icon

                grouped[key]['products'].append(product)
                grouped[key]['count'] = len(grouped[key]['products'])
            else:
                products_without_category += 1

        if products_without_category > 0:
            logger.info(f"DEBUG: {products_without_category} products have no category info")

        # Define order for category types
        category_order = {
            'apparel': 1,
            'footwear': 2,
            'accessories': 3,
            'equipment': 4,
            'footballs': 5,
            'protective_gear': 6,
            'other': 99
        }

        # Add order to each group
        for key in grouped:
            grouped[key]['order'] = category_order.get(key, 50)

        # Sort by order
        return OrderedDict(
            sorted(grouped.items(), key=lambda x: x[1]['order'])
        )

    def _group_products_by_category(self, products):
        """
        Group products by category when search is active.
        Returns OrderedDict of category groups with products.

        Format:
        {
            'group_key': {
                'category': {...},
                'products': [...]
            }
        }
        """
        from collections import OrderedDict

        grouped = OrderedDict()

        for product in products:
            # Get category info based on product type
            category_info = self._get_category_info(product)

            if not category_info:
                # Products without category go to 'Uncategorized'
                key = 'uncategorized'
                if key not in grouped:
                    grouped[key] = {
                        'category': {
                            'id': None,
                            'name': 'Uncategorized',
                            'category_type': 'uncategorized',
                            'display_name': 'Uncategorized',
                            'institution': '',
                            'order': 999
                        },
                        'products': []
                    }
                grouped[key]['products'].append(product)
            else:
                # Use category_info as key
                key = category_info['key']
                if key not in grouped:
                    grouped[key] = {
                        'category': category_info,
                        'products': []
                    }
                grouped[key]['products'].append(product)

        # Sort groups by order, then by name
        return OrderedDict(
            sorted(grouped.items(),
                   key=lambda x: (x[1]['category']['order'],
                                x[1]['category']['display_name']))
        )


# =====================================
# SITE SETTINGS VIEW
# =====================================

class SiteSettingsView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    """
    Site Settings management view.
    Allows admin users to configure site-wide settings like GST percentage
    and quotation validity days.
    """
    template_name = 'quotations/site_settings.html'
    form_class = SiteSettingsForm
    success_url = reverse_lazy('quotations:site-settings')

    def test_func(self):
        """Only admin users can access site settings"""
        return self.request.user.is_authenticated and self.request.user.is_admin

    def get_object(self):
        """Get or create the singleton SiteSettings instance"""
        return SiteSettings.objects.get_settings()

    def get_form_kwargs(self):
        """Pass the SiteSettings instance to the form"""
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.get_object()
        return kwargs

    def form_valid(self, form):
        """Save the form and show success message"""
        settings = form.save(commit=False)
        settings.updated_by = self.request.user
        settings.save()

        # Log action
        AuditLog.log_action(
            user=self.request.user,
            action_type='data_update',
            description=f'Updated site settings: GST={settings.gst_percentage}%, Validity={settings.quotation_validity_days} days',
            request=self.request,
            gst_percentage=str(settings.gst_percentage),
            quotation_validity_days=settings.quotation_validity_days
        )

        messages.success(self.request, 'Site settings updated successfully!')
        return super().form_valid(form)

    def form_invalid(self, form):
        """Show error message if form validation fails"""
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        """Add additional context for template"""
        context = super().get_context_data(**kwargs)
        settings = self.get_object()
        context['settings'] = settings
        context['page_title'] = 'Site Settings'
        return context


# =====================================
# APPROVE QUOTATION VIEW
# =====================================

class ApproveQuotationView(LoginRequiredMixin, View):
    """
    Approve a pending quotation.
    Accessible to quotation creator.
    """

    def post(self, request, pk):
        try:
            # Get quotation - ensure user is the creator
            quotation = get_object_or_404(Quotation, pk=pk, created_by=request.user)

            # Check if quotation is pending
            if quotation.status != 'pending':
                return JsonResponse({
                    'success': False,
                    'error': f'Cannot approve quotation with status: {quotation.get_status_display()}'
                }, status=400)

            # Approve the quotation
            quotation.approve(
                approved_by=request.user,
                notes=f'Approved by {request.user.get_full_name()}'
            )

            # Log action
            AuditLog.log_action(
                user=request.user,
                action_type='quotation_approved',
                description=f'Approved quotation {quotation.quotation_number}',
                request=request,
                affected_model='Quotation',
                affected_object_id=str(quotation.id),
                quotation_id=str(quotation.id),
                quotation_number=quotation.quotation_number,
                old_status='pending',
                new_status='confirmed',
                institution_id=quotation.institution_object_id if quotation.institution else None,
                institution_type=quotation.institution_content_type.model if quotation.institution_content_type else None,
                total_amount=str(quotation.total)
            )

            return JsonResponse({
                'success': True,
                'message': f'Quotation {quotation.quotation_number} approved successfully',
                'quotation_number': quotation.quotation_number,
                'approved_at': quotation.approved_at.strftime('%Y-%m-%d %H:%M:%S') if quotation.approved_at else None
            })

        except ValidationError as e:
            logger.error(f"Validation error approving quotation {pk}: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
        except Exception as e:
            logger.error(f"Error approving quotation {pk}: {e}")
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while approving the quotation'
            }, status=500)


# =====================================
# REPORTS - PRODUCTS MISSING COST
# =====================================

class ProductsMissingCostView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Report showing products and variations with missing or zero cost_price.

    For products with variations: Shows only variations with missing cost_price.
    For products without variations: Shows products with missing cost_price.

    Accessible to Admin, Account Managers, and Sales Reps only.
    """
    template_name = 'quotations/reports/products_missing_cost.html'

    def test_func(self):
        """Check if user has permission to view reports"""
        user = self.request.user
        return (user.is_staff or user.is_superuser or
                user.groups.filter(name__in=['account_manager', 'sales_rep']).exists() or
                user.is_admin or user.is_account_manager or user.is_sales_rep)

    def get(self, request):
        from schools.models_tus import TUSProduct, TUSProductVariation
        from schools.models import WholesaleProduct, WholesaleProductVariation

        # Get filter parameter
        product_type_filter = request.GET.get('product_type', 'all')

        # Initialize product collections
        products_by_type = {
            'tus': [],
            'lotto': [],
            'sas': [],
            'wholesale': [],
        }

        # Query TUS Products with missing cost
        if product_type_filter in ['all', 'tus']:
            # Get all TUS products with prefetch of variations
            tus_products = TUSProduct.objects.prefetch_related('variations').order_by('name')

            for product in tus_products:
                # Get school name
                school_name = "Unknown"
                if hasattr(product, 'primary_category_assignment') and product.primary_category_assignment:
                    if product.primary_category_assignment.school_category and product.primary_category_assignment.school_category.school:
                        school_name = product.primary_category_assignment.school_category.school.name

                # Check if product has variations
                variations = product.variations.all()
                if variations.exists():
                    # If product has variations, check each variation for missing cost
                    for variation in variations:
                        if variation.cost_price is None or variation.cost_price == 0:
                            # Build variation display name
                            variation_name = f"{product.name} - {variation.variation_value}"

                            products_by_type['tus'].append({
                                'product': product,
                                'variation': variation,
                                'product_name': variation_name,
                                'sku': getattr(variation, 'sku', ''),
                                'category': school_name,
                                'status': getattr(variation, 'stock_status', 'unknown'),
                                'is_variation': True,
                            })
                else:
                    # No variations - check product cost
                    if product.cost_price is None or product.cost_price == 0:
                        products_by_type['tus'].append({
                            'product': product,
                            'variation': None,
                            'product_name': product.name,
                            'sku': getattr(product, 'sku', ''),
                            'category': school_name,
                            'status': product.stock_status if hasattr(product, 'stock_status') else 'unknown',
                            'is_variation': False,
                        })

        # Query LOTTO Products with missing cost
        if product_type_filter in ['all', 'lotto']:
            from clubs.models_lotto import LottoProductVariation

            # Get all LOTTO products with prefetch of variations
            lotto_products = LottoProduct.objects.prefetch_related('variations').order_by('name')

            for product in lotto_products:
                club_name = product.category.club.name if product.category and product.category.club else "Unknown"

                # Check if product has variations
                variations = product.variations.all()
                if variations.exists():
                    # If product has variations, check each variation for missing cost
                    for variation in variations:
                        if variation.cost_price is None or variation.cost_price == 0:
                            # Build variation display name
                            variation_name = f"{product.name} - {variation.variation_value}"

                            products_by_type['lotto'].append({
                                'product': product,
                                'variation': variation,
                                'product_name': variation_name,
                                'sku': getattr(variation, 'sku', ''),
                                'category': club_name,
                                'status': getattr(variation, 'stock_status', 'unknown'),
                                'is_variation': True,
                            })
                else:
                    # No variations - check product cost
                    if product.cost_price is None or product.cost_price == 0:
                        products_by_type['lotto'].append({
                            'product': product,
                            'variation': None,
                            'product_name': product.name,
                            'sku': getattr(product, 'sku', ''),
                            'category': club_name,
                            'status': product.stock_status if hasattr(product, 'stock_status') else 'unknown',
                            'is_variation': False,
                        })

        # Query SAS Products with missing cost
        if product_type_filter in ['all', 'sas']:
            from clubs.models_sas import SASProductVariation

            # Get all SAS products with prefetch of variations
            sas_products = SASProduct.objects.prefetch_related('variations').order_by('name')

            for product in sas_products:
                club_name = product.club.name if product.club else "Unknown"

                # Check if product has variations
                variations = product.variations.all()
                if variations.exists():
                    # If product has variations, check each variation for missing cost
                    for variation in variations:
                        if variation.cost_price is None or variation.cost_price == 0:
                            # Build variation display name
                            variation_name = f"{product.name} - {variation.variation_value}"

                            products_by_type['sas'].append({
                                'product': product,
                                'variation': variation,
                                'product_name': variation_name,
                                'sku': getattr(variation, 'sku', ''),
                                'category': club_name,
                                'status': getattr(variation, 'stock_status', 'unknown'),
                                'is_variation': True,
                            })
                else:
                    # No variations - check product cost
                    if product.cost_price is None or product.cost_price == 0:
                        products_by_type['sas'].append({
                            'product': product,
                            'variation': None,
                            'product_name': product.name,
                            'sku': getattr(product, 'sku', ''),
                            'category': club_name,
                            'status': product.stock_status if hasattr(product, 'stock_status') else 'unknown',
                            'is_variation': False,
                        })

        # Query Wholesale Products with missing cost
        if product_type_filter in ['all', 'wholesale']:
            # Get all Wholesale products with prefetch of variations
            wholesale_products = WholesaleProduct.objects.prefetch_related('variations').order_by('name')

            for product in wholesale_products:
                school_name = product.school.name if product.school else "Unknown"

                # Check if product has variations
                variations = product.variations.all()
                if variations.exists():
                    # If product has variations, check each variation for missing cost
                    for variation in variations:
                        if variation.cost_price is None or variation.cost_price == 0:
                            # Build variation display name
                            variation_name = f"{product.name} - {variation.variation_value}"

                            products_by_type['wholesale'].append({
                                'product': product,
                                'variation': variation,
                                'product_name': variation_name,
                                'sku': getattr(variation, 'cin7_sku', ''),
                                'category': school_name,
                                'status': 'active' if product.is_active else 'inactive',
                                'is_variation': True,
                            })
                else:
                    # No variations - check product cost
                    if product.cost_price is None or product.cost_price == 0:
                        products_by_type['wholesale'].append({
                            'product': product,
                            'variation': None,
                            'product_name': product.name,
                            'sku': getattr(product, 'cin7_sku', ''),
                            'category': school_name,
                            'status': 'active' if product.is_active else 'inactive',
                            'is_variation': False,
                        })

        # Calculate counts
        counts = {
            'tus': len(products_by_type['tus']),
            'lotto': len(products_by_type['lotto']),
            'sas': len(products_by_type['sas']),
            'wholesale': len(products_by_type['wholesale']),
        }
        counts['total'] = sum(counts.values())

        # Log access
        AuditLog.log_action(
            user=request.user,
            action_type='report_access',
            description=f'Viewed Products Missing Cost report (filter: {product_type_filter})',
            request=request,
            product_type_filter=product_type_filter,
            total_products=counts['total']
        )

        context = {
            'products_by_type': products_by_type,
            'counts': counts,
            'product_type_filter': product_type_filter,
            'page_title': 'Products Missing Cost Report',
        }

        return render(request, self.template_name, context)


# =====================================
# REPORTS - PRICE ANOMALY
# =====================================

class ProductsPriceAnomalyView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Report showing products where unit_price > margin_75_price.
    This indicates pricing anomalies where selling price exceeds the 75% margin price.
    Accessible to Admin, Account Managers, and Sales Reps only.
    """
    template_name = 'quotations/reports/products_price_anomaly.html'

    def test_func(self):
        """Check if user has permission to view reports"""
        user = self.request.user
        return (user.is_staff or user.is_superuser or
                user.groups.filter(name__in=['account_manager', 'sales_rep']).exists() or
                user.is_admin or user.is_account_manager or user.is_sales_rep)

    def get(self, request):
        from schools.models_tus import TUSProduct

        # Get filter parameter
        product_type_filter = request.GET.get('product_type', 'all')

        # Initialize product collections
        products_by_type = {
            'tus': [],
            'lotto': [],
            'sas': [],
            'wholesale': [],
        }

        # Query TUS Products with price anomaly
        if product_type_filter in ['all', 'tus']:
            tus_products = TUSProduct.objects.filter(
                margin_75_price__isnull=False,
                price__isnull=False
            ).order_by('name')

            for product in tus_products:
                unit_price = product.price or Decimal('0')
                margin_75_price = product.margin_75_price or Decimal('0')

                # Check if unit_price > margin_75_price
                if unit_price > margin_75_price and margin_75_price > 0:
                    difference = unit_price - margin_75_price
                    percentage_over = ((difference / margin_75_price) * 100).quantize(Decimal('0.01'))

                    # Get school name
                    school_name = "Unknown"
                    if hasattr(product, 'primary_category_assignment') and product.primary_category_assignment:
                        if product.primary_category_assignment.school_category and product.primary_category_assignment.school_category.school:
                            school_name = product.primary_category_assignment.school_category.school.name

                    products_by_type['tus'].append({
                        'product': product,
                        'product_name': product.name,
                        'sku': getattr(product, 'sku', ''),
                        'category': school_name,
                        'unit_price': unit_price,
                        'margin_75_price': margin_75_price,
                        'difference': difference,
                        'percentage_over': percentage_over,
                    })

        # Query LOTTO Products with price anomaly
        if product_type_filter in ['all', 'lotto']:
            lotto_products = LottoProduct.objects.filter(
                margin_75_price__isnull=False,
                price__isnull=False
            ).order_by('name')

            for product in lotto_products:
                unit_price = product.price or Decimal('0')
                margin_75_price = product.margin_75_price or Decimal('0')

                if unit_price > margin_75_price and margin_75_price > 0:
                    difference = unit_price - margin_75_price
                    percentage_over = ((difference / margin_75_price) * 100).quantize(Decimal('0.01'))

                    club_name = product.category.club.name if product.category and product.category.club else "Unknown"
                    products_by_type['lotto'].append({
                        'product': product,
                        'product_name': product.name,
                        'sku': getattr(product, 'sku', ''),
                        'category': club_name,
                        'unit_price': unit_price,
                        'margin_75_price': margin_75_price,
                        'difference': difference,
                        'percentage_over': percentage_over,
                    })

        # Query SAS Products with price anomaly
        if product_type_filter in ['all', 'sas']:
            sas_products = SASProduct.objects.filter(
                margin_75_price__isnull=False,
                price__isnull=False
            ).order_by('name')

            for product in sas_products:
                unit_price = product.price or Decimal('0')
                margin_75_price = product.margin_75_price or Decimal('0')

                if unit_price > margin_75_price and margin_75_price > 0:
                    difference = unit_price - margin_75_price
                    percentage_over = ((difference / margin_75_price) * 100).quantize(Decimal('0.01'))

                    club_name = product.club.name if product.club else "Unknown"
                    products_by_type['sas'].append({
                        'product': product,
                        'product_name': product.name,
                        'sku': getattr(product, 'sku', ''),
                        'category': club_name,
                        'unit_price': unit_price,
                        'margin_75_price': margin_75_price,
                        'difference': difference,
                        'percentage_over': percentage_over,
                    })

        # Query Wholesale Products with price anomaly
        if product_type_filter in ['all', 'wholesale']:
            wholesale_products = WholesaleProduct.objects.filter(
                margin_75_price__isnull=False,
                wholesale_price__isnull=False
            ).order_by('name')

            for product in wholesale_products:
                unit_price = product.wholesale_price or Decimal('0')
                margin_75_price = product.margin_75_price or Decimal('0')

                if unit_price > margin_75_price and margin_75_price > 0:
                    difference = unit_price - margin_75_price
                    percentage_over = ((difference / margin_75_price) * 100).quantize(Decimal('0.01'))

                    school_name = product.school.name if product.school else "Unknown"
                    products_by_type['wholesale'].append({
                        'product': product,
                        'product_name': product.name,
                        'sku': getattr(product, 'cin7_sku', ''),
                        'category': school_name,
                        'unit_price': unit_price,
                        'margin_75_price': margin_75_price,
                        'difference': difference,
                        'percentage_over': percentage_over,
                    })

        # Calculate counts
        counts = {
            'tus': len(products_by_type['tus']),
            'lotto': len(products_by_type['lotto']),
            'sas': len(products_by_type['sas']),
            'wholesale': len(products_by_type['wholesale']),
        }
        counts['total'] = sum(counts.values())

        # Log access
        AuditLog.log_action(
            user=request.user,
            action_type='report_access',
            description=f'Viewed Products Price Anomaly report (filter: {product_type_filter})',
            request=request,
            product_type_filter=product_type_filter,
            total_products=counts['total']
        )

        context = {
            'products_by_type': products_by_type,
            'counts': counts,
            'product_type_filter': product_type_filter,
            'page_title': 'Products with Selling Price > 75% Margin',
        }

        return render(request, self.template_name, context)


# =====================================
# REPORTS - LOW MARGIN PRODUCTS
# =====================================
class ProductsLowMarginView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Report showing products with margin below 66% (price < cost_price / 0.34).
    Products should have 66% margin of their cost price.
    Accessible to Admin, Account Managers, and Sales Reps only.
    Supports search by SKU, Barcode, Style Code (for wholesale), and Product Name.
    """
    template_name = 'quotations/reports/products_low_margin.html'

    def test_func(self):
        """Check if user has permission to view reports"""
        user = self.request.user
        return (user.is_staff or user.is_superuser or
                user.groups.filter(name__in=['account_manager', 'sales_rep']).exists() or
                user.is_admin or user.is_account_manager or user.is_sales_rep)

    def get(self, request):
        from schools.models_tus import TUSProduct, TUSProductVariation
        from schools.models import WholesaleProduct, WholesaleProductVariation
        from clubs.models import LottoProduct, LottoProductVariation, SASProduct, SASProductVariation

        # Get filter parameters
        product_type_filter = request.GET.get('product_type', 'all')
        search_query = request.GET.get('search', '').strip()

        # Initialize product collections
        products_by_type = {
            'tus': [],
            'lotto': [],
            'sas': [],
            'wholesale': [],
        }

        # Target margin is 66% (price should be cost / 0.34 = cost * 2.94117647)
        TARGET_MARGIN = Decimal('0.66')
        COST_MULTIPLIER = Decimal('1') / (Decimal('1') - TARGET_MARGIN)  # 1 / 0.34 = 2.94117647

        # Query TUS Products with low margin
        if product_type_filter in ['all', 'tus']:
            tus_query = TUSProduct.objects.filter(
                cost_price__isnull=False,
                cost_price__gt=0,
                price__isnull=False,
                price__gt=0
            )

            # Apply search filter
            if search_query:
                from django.db.models import Q
                tus_query = tus_query.filter(
                    Q(sku__icontains=search_query) |
                    Q(barcode__icontains=search_query) |
                    Q(name__icontains=search_query)
                )

            tus_products = tus_query.prefetch_related('variations').order_by('name')

            for product in tus_products:
                # Get school name
                school_name = "Unknown"
                if hasattr(product, 'primary_category_assignment') and product.primary_category_assignment:
                    if product.primary_category_assignment.school_category and product.primary_category_assignment.school_category.school:
                        school_name = product.primary_category_assignment.school_category.school.name

                # Check if product has variations
                variations = product.variations.all()
                if variations.exists():
                    # Check each variation for low margin
                    for variation in variations:
                        if variation.cost_price and variation.cost_price > 0 and variation.price and variation.price > 0:
                            target_price = variation.cost_price * COST_MULTIPLIER
                            if variation.price < target_price:
                                actual_margin = ((variation.price - variation.cost_price) / variation.price * 100).quantize(Decimal('0.01'))
                                price_shortfall = target_price - variation.price

                                products_by_type['tus'].append({
                                    'is_variation': True,
                                    'product_name': f"{product.name} - {variation.variation_value or 'Variation'}",
                                    'sku': variation.sku or product.sku or '',
                                    'barcode': variation.barcode or product.barcode or '',
                                    'category': school_name,
                                    'cost_price': variation.cost_price,
                                    'current_price': variation.price,
                                    'target_price': target_price,
                                    'actual_margin': actual_margin,
                                    'price_shortfall': price_shortfall,
                                    'status': variation.stock_status,
                                })
                else:
                    # Product without variations
                    target_price = product.cost_price * COST_MULTIPLIER
                    if product.price < target_price:
                        actual_margin = ((product.price - product.cost_price) / product.price * 100).quantize(Decimal('0.01'))
                        price_shortfall = target_price - product.price

                        products_by_type['tus'].append({
                            'is_variation': False,
                            'product_name': product.name,
                            'sku': product.sku or '',
                            'barcode': product.barcode or '',
                            'category': school_name,
                            'cost_price': product.cost_price,
                            'current_price': product.price,
                            'target_price': target_price,
                            'actual_margin': actual_margin,
                            'price_shortfall': price_shortfall,
                            'status': product.stock_status,
                        })

        # Query LOTTO Products with low margin
        if product_type_filter in ['all', 'lotto']:
            lotto_query = LottoProduct.objects.filter(
                cost_price__isnull=False,
                cost_price__gt=0,
                price__isnull=False,
                price__gt=0
            )

            if search_query:
                from django.db.models import Q
                lotto_query = lotto_query.filter(
                    Q(sku__icontains=search_query) |
                    Q(barcode__icontains=search_query) |
                    Q(name__icontains=search_query)
                )

            lotto_products = lotto_query.prefetch_related('variations').order_by('name')

            for product in lotto_products:
                club_name = product.category.club.name if product.category and product.category.club else "Unknown"

                variations = product.variations.all()
                if variations.exists():
                    for variation in variations:
                        if variation.cost_price and variation.cost_price > 0 and variation.price and variation.price > 0:
                            target_price = variation.cost_price * COST_MULTIPLIER
                            if variation.price < target_price:
                                actual_margin = ((variation.price - variation.cost_price) / variation.price * 100).quantize(Decimal('0.01'))
                                price_shortfall = target_price - variation.price

                                products_by_type['lotto'].append({
                                    'is_variation': True,
                                    'product_name': f"{product.name} - {variation.variation_value or 'Variation'}",
                                    'sku': getattr(variation, 'full_sku', product.sku or ''),
                                    'barcode': product.barcode or '',
                                    'category': club_name,
                                    'cost_price': variation.cost_price,
                                    'current_price': variation.price,
                                    'target_price': target_price,
                                    'actual_margin': actual_margin,
                                    'price_shortfall': price_shortfall,
                                    'status': variation.stock_status,
                                })
                else:
                    target_price = product.cost_price * COST_MULTIPLIER
                    if product.price < target_price:
                        actual_margin = ((product.price - product.cost_price) / product.price * 100).quantize(Decimal('0.01'))
                        price_shortfall = target_price - product.price

                        products_by_type['lotto'].append({
                            'is_variation': False,
                            'product_name': product.name,
                            'sku': product.sku or '',
                            'barcode': product.barcode or '',
                            'category': club_name,
                            'cost_price': product.cost_price,
                            'current_price': product.price,
                            'target_price': target_price,
                            'actual_margin': actual_margin,
                            'price_shortfall': price_shortfall,
                            'status': product.stock_status,
                        })

        # Query SAS Products with low margin
        if product_type_filter in ['all', 'sas']:
            sas_query = SASProduct.objects.filter(
                cost_price__isnull=False,
                cost_price__gt=0,
                price__isnull=False,
                price__gt=0
            )

            if search_query:
                from django.db.models import Q
                sas_query = sas_query.filter(
                    Q(sku__icontains=search_query) |
                    Q(barcode__icontains=search_query) |
                    Q(name__icontains=search_query)
                )

            sas_products = sas_query.prefetch_related('variations').order_by('name')

            for product in sas_products:
                club_name = product.club.name if product.club else "Unknown"

                variations = product.variations.all()
                if variations.exists():
                    for variation in variations:
                        if variation.cost_price and variation.cost_price > 0 and variation.price and variation.price > 0:
                            target_price = variation.cost_price * COST_MULTIPLIER
                            if variation.price < target_price:
                                actual_margin = ((variation.price - variation.cost_price) / variation.price * 100).quantize(Decimal('0.01'))
                                price_shortfall = target_price - variation.price

                                products_by_type['sas'].append({
                                    'is_variation': True,
                                    'product_name': f"{product.name} - {variation.variation_value or 'Variation'}",
                                    'sku': getattr(variation, 'full_sku', product.sku or ''),
                                    'barcode': product.barcode or '',
                                    'category': club_name,
                                    'cost_price': variation.cost_price,
                                    'current_price': variation.price,
                                    'target_price': target_price,
                                    'actual_margin': actual_margin,
                                    'price_shortfall': price_shortfall,
                                    'status': variation.stock_status,
                                })
                else:
                    target_price = product.cost_price * COST_MULTIPLIER
                    if product.price < target_price:
                        actual_margin = ((product.price - product.cost_price) / product.price * 100).quantize(Decimal('0.01'))
                        price_shortfall = target_price - product.price

                        products_by_type['sas'].append({
                            'is_variation': False,
                            'product_name': product.name,
                            'sku': product.sku or '',
                            'barcode': product.barcode or '',
                            'category': club_name,
                            'cost_price': product.cost_price,
                            'current_price': product.price,
                            'target_price': target_price,
                            'actual_margin': actual_margin,
                            'price_shortfall': price_shortfall,
                            'status': product.stock_status,
                        })

        # Query Wholesale Products with low margin
        if product_type_filter in ['all', 'wholesale']:
            wholesale_query = WholesaleProduct.objects.filter(
                cost_price__isnull=False,
                cost_price__gt=0,
                wholesale_price__isnull=False,
                wholesale_price__gt=0
            )

            if search_query:
                from django.db.models import Q
                wholesale_query = wholesale_query.filter(
                    Q(cin7_sku__icontains=search_query) |
                    Q(cin7_barcode__icontains=search_query) |
                    Q(name__icontains=search_query)
                )

            wholesale_products = wholesale_query.prefetch_related('variations').order_by('name')

            for product in wholesale_products:
                school_name = product.school.name if product.school else "Unknown"

                variations = product.variations.all()
                if variations.exists():
                    for variation in variations:
                        if variation.cost_price and variation.cost_price > 0 and variation.wholesale_price and variation.wholesale_price > 0:
                            target_price = variation.cost_price * COST_MULTIPLIER
                            if variation.wholesale_price < target_price:
                                actual_margin = ((variation.wholesale_price - variation.cost_price) / variation.wholesale_price * 100).quantize(Decimal('0.01'))
                                price_shortfall = target_price - variation.wholesale_price

                                products_by_type['wholesale'].append({
                                    'is_variation': True,
                                    'product_name': f"{product.name} - {variation.variation_value or 'Variation'}",
                                    'sku': variation.cin7_sku or product.cin7_sku or '',
                                    'barcode': variation.cin7_barcode or product.cin7_barcode or '',
                                    'style_code': variation.variation_value or '',
                                    'category': school_name,
                                    'cost_price': variation.cost_price,
                                    'current_price': variation.wholesale_price,
                                    'target_price': target_price,
                                    'actual_margin': actual_margin,
                                    'price_shortfall': price_shortfall,
                                    'status': 'in_stock' if variation.is_in_stock else 'out_of_stock',
                                })
                else:
                    target_price = product.cost_price * COST_MULTIPLIER
                    if product.wholesale_price < target_price:
                        actual_margin = ((product.wholesale_price - product.cost_price) / product.wholesale_price * 100).quantize(Decimal('0.01'))
                        price_shortfall = target_price - product.wholesale_price

                        products_by_type['wholesale'].append({
                            'is_variation': False,
                            'product_name': product.name,
                            'sku': product.cin7_sku or '',
                            'barcode': product.cin7_barcode or '',
                            'style_code': '',
                            'category': school_name,
                            'cost_price': product.cost_price,
                            'current_price': product.wholesale_price,
                            'target_price': target_price,
                            'actual_margin': actual_margin,
                            'price_shortfall': price_shortfall,
                            'status': product.stock_status,
                        })

        # Calculate counts
        counts = {
            'tus': len(products_by_type['tus']),
            'lotto': len(products_by_type['lotto']),
            'sas': len(products_by_type['sas']),
            'wholesale': len(products_by_type['wholesale']),
        }
        counts['total'] = sum(counts.values())

        # Log access
        AuditLog.log_action(
            user=request.user,
            action_type='report_access',
            description=f'Viewed Low Margin Products report (filter: {product_type_filter}, search: {search_query or "none"})',
            request=request,
            product_type_filter=product_type_filter,
            search_query=search_query,
            total_products=counts['total']
        )

        context = {
            'products_by_type': products_by_type,
            'counts': counts,
            'product_type_filter': product_type_filter,
            'search_query': search_query,
            'page_title': 'Low Margin Products (Below 66%)',
            'target_margin': TARGET_MARGIN * 100,
        }

        return render(request, self.template_name, context)


# =====================================
# API ENDPOINT - QUOTATION VERSION HISTORY
# =====================================

class QuotationVersionsAPIView(LoginRequiredMixin, View):
    """
    API endpoint to fetch all version history for a quotation.

    Returns JSON with all QuotationVersion records including:
    - version_number
    - created_at (formatted timestamp)
    - created_by (user name)
    - change_note
    - changes_summary (snapshot_data)

    Permissions:
    - User must own the quotation (created_by) or be admin/staff

    URL: /quotations/<quotation_id>/versions/
    """

    def get(self, request, quotation_id):
        """
        Fetch all version history for a quotation

        Args:
            request: HTTP request object
            quotation_id: UUID of the quotation

        Returns:
            JsonResponse with version history or error
        """
        try:
            # Get the quotation
            quotation = get_object_or_404(
                Quotation.objects.select_related('created_by'),
                pk=quotation_id
            )

            # Permission check: user must own quotation or be admin/staff
            user = request.user
            has_permission = False

            if user.is_admin or user.is_staff or user.is_superuser:
                has_permission = True
            elif quotation.created_by == user:
                has_permission = True
            elif user.is_account_manager:
                # Account managers can view all quotations
                has_permission = True
            elif user.is_sales_rep:
                # Sales reps can view quotations they're assigned to
                if quotation.assigned_sales_rep == user:
                    has_permission = True

            if not has_permission:
                logger.warning(
                    f"Permission denied: User {user.id} ({user.username}) "
                    f"attempted to access version history for quotation {quotation_id}"
                )
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to view this quotation version history.'
                }, status=403)

            # Get all versions ordered by version_number descending (newest first)
            versions = quotation.versions.all().select_related('created_by').order_by('-version_number')

            # Build response data
            version_data = []
            for version in versions:
                # Format the created_at timestamp
                created_at_formatted = version.created_at.strftime('%Y-%m-%d %H:%M:%S')

                # Get user name
                user_name = 'Unknown User'
                if version.created_by:
                    user_name = version.created_by.get_full_name() or version.created_by.username

                # Parse snapshot data to extract changes
                snapshot = version.snapshot_data or {}

                # Use detailed changes if available, otherwise fallback to basic info
                if version.changes_detail:
                    # Use the detailed changes we calculated
                    changes = {
                        'before_total': version.changes_detail.get('before_total'),
                        'after_total': version.changes_detail.get('after_total'),
                        'items_added': version.changes_detail.get('items_added', []),
                        'items_removed': version.changes_detail.get('items_removed', []),
                        'items_modified': version.changes_detail.get('items_modified', [])
                    }
                else:
                    # Fallback for older versions without detailed changes
                    items = snapshot.get('items', [])
                    changes = {
                        'before_total': None,
                        'after_total': snapshot.get('total', '0.00'),
                        'items_added': [],
                        'items_removed': [],
                        'items_modified': []
                    }

                # Build version object (format expected by frontend)
                version_obj = {
                    'version': version.version_number,
                    'date': version.created_at.isoformat(),  # ISO format for JavaScript Date parsing
                    'user': user_name,
                    'note': version.change_note or version.change_description or 'No note provided',
                    'changes': changes
                }

                version_data.append(version_obj)

            # Log successful access
            AuditLog.log_action(
                user=request.user,
                action_type='api_access',
                description=f'Accessed version history API for quotation {quotation.quotation_number}',
                request=request,
                quotation_id=str(quotation_id),
                version_count=len(version_data)
            )

            return JsonResponse({
                'success': True,
                'quotation_number': quotation.quotation_number,
                'quotation_id': str(quotation.id),
                'total_versions': len(version_data),
                'versions': version_data
            })

        except Quotation.DoesNotExist:
            logger.warning(f"Quotation not found: {quotation_id}")
            return JsonResponse({
                'success': False,
                'error': 'Quotation not found.'
            }, status=404)

        except Exception as e:
            logger.error(f"Error fetching version history for quotation {quotation_id}: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while fetching version history.'
            }, status=500)
