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
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView, FormView
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib import messages
import logging
import requests
import os

from authentication.permissions import (
    SalesRepOrAccountManagerMixin,
    CustomerRequiredMixin,
    SalesRepOrAccountManagerOrCustomerMixin,
)
from authentication.models import User, SalesRepSchoolAssignment, SalesRepClubAssignment, AuditLog
from functools import wraps
from schools.models import School, WholesaleSchool, WholesaleProduct, WholesaleProductVariation
from schools.models_tus import TUSProductVariation
from clubs.models_lotto import LottoClub, LottoProduct
from clubs.models_sas import SASClub, SASProduct
from .models import Quotation, QuotationItem, CustomerInstitutionAssignment, SiteSettings
from .models_shipping import ShippingSettings
from .utils_shipping import get_region_from_address, get_capacity_key_for_product
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


def calculate_session_shipping(cart_items, customer):
    """
    Calculate shipping cost for session-based cart items before quotation is saved.

    Args:
        cart_items: List of cart item dicts from session
        customer: User object (request.user)

    Returns:
        dict with: shipping_cost, shipping_boxes, shipping_region, is_rural_delivery,
                   box_breakdown (dict of product_type: box_count)
    """
    import math

    # Default return values
    result = {
        'shipping_cost': Decimal('0.00'),
        'shipping_boxes': 0,
        'shipping_region': None,
        'is_rural_delivery': False,
        'box_breakdown': {},
    }

    # Check if customer has address information
    if not customer or not hasattr(customer, 'city'):
        logger.debug("Customer has no city information, cannot calculate shipping")
        return result

    # Get customer address fields
    city = getattr(customer, 'city', None)
    suburb = getattr(customer, 'suburb', None)
    street_address = getattr(customer, 'street_address', None)
    postcode = getattr(customer, 'postcode', None)

    # Get region from address
    region = get_region_from_address(
        street_address=street_address,
        suburb=suburb,
        city=city,
        postcode=postcode
    )

    if not region:
        logger.warning(f"Could not determine region for customer {customer.id} with city={city}")
        return result

    result['shipping_region'] = region

    # Get shipping settings
    shipping_settings = ShippingSettings.get_solo()

    # Calculate boxes needed per product type
    box_breakdown = {}

    for item in cart_items:
        # Skip addon items - they don't require separate shipping boxes
        # Addons (Heat Transfer, Screen Print, etc.) are applied to base garments
        if item.get('is_addon', False):
            logger.debug(f"Skipping addon item {item.get('product_name', 'Unknown')} for shipping calculation")
            continue

        # Get product to determine capacity key
        product = get_product_by_type_and_id(item['product_type'], item['product_id'])
        if not product:
            logger.warning(f"Could not find product {item['product_type']} {item['product_id']}")
            continue

        # Get capacity key for this product
        capacity_key = get_capacity_key_for_product(product)

        # Get quantity for this item
        quantity = int(item.get('quantity', 0))

        # Add to box breakdown by capacity key
        if capacity_key not in box_breakdown:
            box_breakdown[capacity_key] = {
                'quantity': 0,
                'capacity': shipping_settings.get_product_capacity(capacity_key) or 1,
                'boxes': 0,
            }

        box_breakdown[capacity_key]['quantity'] += quantity

    # Calculate boxes needed for each capacity key
    total_boxes = 0
    for capacity_key, data in box_breakdown.items():
        boxes_needed = math.ceil(data['quantity'] / data['capacity'])
        data['boxes'] = boxes_needed
        total_boxes += boxes_needed

    result['shipping_boxes'] = total_boxes
    result['box_breakdown'] = box_breakdown

    # Get shipping rate for region
    rate_area = shipping_settings.get_rate_area_for_region(region)
    if not rate_area:
        logger.warning(f"No rate area found for region {region}")
        return result

    # Check if rural delivery (based on rate area name)
    is_rural = 'rural' in rate_area.lower()
    result['is_rural_delivery'] = is_rural

    # Get base shipping cost per box
    rate_info = shipping_settings.get_shipping_rate(rate_area)
    if not rate_info:
        logger.warning(f"No rate info found for rate area {rate_area}")
        return result

    cost_per_box = Decimal(str(rate_info.get('cost', '0.00')))

    # Calculate total shipping cost
    base_shipping = cost_per_box * Decimal(str(total_boxes))

    # Add rural delivery surcharge if applicable
    total_shipping = base_shipping
    if is_rural:
        rd_surcharge = shipping_settings.rd_delivery_surcharge * Decimal(str(total_boxes))
        total_shipping += rd_surcharge

    result['shipping_cost'] = total_shipping.quantize(Decimal('0.01'))

    logger.info(f"Calculated shipping: {total_boxes} boxes to {region} = ${result['shipping_cost']}")

    return result


def calculate_quotation_totals(quotation_data, customer=None):
    """Calculate totals for quotation session data including addons and shipping"""
    from .models import SiteSettings

    subtotal = Decimal('0.00')

    # Get GST percentage from site settings
    settings = SiteSettings.objects.get_settings()
    tax_percentage = settings.gst_percentage

    for item in quotation_data.get('items', []):
        # Base product price
        line_total = Decimal(str(item['unit_price'])) * Decimal(str(item['quantity']))
        subtotal += line_total

        # Add addon prices ONLY for Bespoke products
        product_type = item.get('product_type', '')
        if product_type and product_type.lower() == 'bespokeproduct':
            for addon in item.get('addons', []):
                addon_total = Decimal(str(addon.get('total_price', 0)))
                subtotal += addon_total

    # Calculate shipping if customer provided
    shipping_info = {
        'shipping_cost': Decimal('0.00'),
        'shipping_boxes': 0,
        'shipping_region': None,
        'is_rural_delivery': False,
        'box_breakdown': {},
    }

    if customer:
        shipping_info = calculate_session_shipping(quotation_data.get('items', []), customer)

    shipping_cost = shipping_info['shipping_cost']

    # Calculate tax on subtotal + shipping
    tax_amount = ((subtotal + shipping_cost) * tax_percentage / Decimal('100')).quantize(Decimal('0.01'))
    total = (subtotal + shipping_cost + tax_amount).quantize(Decimal('0.01'))

    return {
        'subtotal': subtotal,
        'shipping_cost': shipping_cost,
        'shipping_boxes': shipping_info['shipping_boxes'],
        'shipping_region': shipping_info['shipping_region'],
        'is_rural_delivery': shipping_info['is_rural_delivery'],
        'box_breakdown': shipping_info['box_breakdown'],
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
    from ballstore.models import BallStoreProduct
    from bespoke.models import BespokeProduct

    product_models = {
        'tusproduct': TUSProduct,
        'wholesaleproduct': WholesaleProduct,
        'lottoproduct': LottoProduct,
        'sasproduct': SASProduct,
        'ballstoreproduct': BallStoreProduct,
        'bespokeproduct': BespokeProduct,
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
    from bespoke.models import BespokeProduct

    product_models = {
        'tusproduct': TUSProduct,
        'wholesaleproduct': WholesaleProduct,
        'lottoproduct': LottoProduct,
        'sasproduct': SASProduct,
        'ballstoreproduct': BallStoreProduct,
        'bespokeproduct': BespokeProduct,
    }

    model_class = product_models.get(product_type.lower())
    if not model_class:
        return None

    try:
        # Check if model has is_active field
        # TUSProduct and LottoProduct don't have is_active
        model_instance = model_class()
        if hasattr(model_instance, 'is_active'):
            # Filter by is_active for models that have this field
            return model_class.objects.filter(slug=product_slug, is_active=True).first()
        else:
            # For models without is_active, just filter by slug
            return model_class.objects.filter(slug=product_slug).first()
    except Exception:
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

                # Check if this is an addon item and enrich with addon-specific display data
                is_addon = item.get('is_addon', False)
                enriched_item['is_addon'] = is_addon

                if is_addon:
                    # Get addon type and create display name
                    addon_type = item.get('addon_type', '')
                    addon_details = item.get('addon_details', {})

                    # Map addon types to display names
                    addon_type_map = {
                        'heat_transfer': 'Heat Transfer',
                        'screen_print': 'Screen Print',
                        'emb_applique': 'Embroidery/Applique',
                    }
                    addon_type_display = addon_type_map.get(addon_type, addon_type.replace('_', ' ').title())
                    enriched_item['addon_type_display'] = addon_type_display

                    # Build descriptive SKU label for addon
                    addon_sku_parts = [addon_type_display]

                    # Add size if available
                    if addon_details.get('size'):
                        addon_sku_parts.append(addon_details['size'].title())

                    # Add color/stitch info
                    if addon_type in ['heat_transfer', 'screen_print'] and addon_details.get('colors'):
                        colors = addon_details['colors']
                        # Handle both numeric and string color values (e.g., "3-4" or 3)
                        if isinstance(colors, str):
                            addon_sku_parts.append(f"{colors} colors")
                        else:
                            addon_sku_parts.append(f"{colors} color{'s' if colors > 1 else ''}")
                    elif addon_type == 'emb_applique':
                        if addon_details.get('stitch_complexity'):
                            addon_sku_parts.append(f"{addon_details['stitch_complexity'].upper()} stitch")
                        if addon_details.get('emb_or_applique'):
                            addon_sku_parts.append(addon_details['emb_or_applique'].title())

                    # Create formatted SKU label
                    addon_sku_label = f"Addon: {' - '.join(addon_sku_parts)}"
                    enriched_item['addon_sku_label'] = addon_sku_label
                    enriched_item['product_sku'] = ''  # Clear product SKU for addons to use addon_sku_label

                # Add pricing information for discount display
                # Skip margin calculation for addons (they are service charges, not wholesale products)
                is_addon = item.get('is_addon', False)
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
                        elif product_type == 'bespokeproduct':
                            from bespoke.models import BespokeProductVariation
                            variation_obj = BespokeProductVariation.objects.get(pk=variation_id)
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
                # Skip this entire section for addons (they don't have wholesale/retail margins)

                if not is_addon:
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
                else:
                    # For addons, set all margin/discount fields to zero
                    enriched_item['margin_75_price'] = None
                    enriched_item['unit_discount'] = Decimal('0.00')
                    enriched_item['item_discount'] = Decimal('0.00')
                    enriched_item['discount_percentage'] = 0

                # Get discount_percentage from variation first, then product (skip for addons)
                if not is_addon:
                    if variation_obj and hasattr(variation_obj, 'discount_percentage') and variation_obj.discount_percentage:
                        enriched_item['discount_percentage'] = variation_obj.discount_percentage
                    elif hasattr(product, 'discount_percentage') and product.discount_percentage:
                        enriched_item['discount_percentage'] = product.discount_percentage

                # Get SKU from variation object if available
                if variation_obj and hasattr(variation_obj, 'sku') and variation_obj.sku:
                    enriched_item['product_sku'] = variation_obj.sku
                # If not in variation_obj, check if it's in the item data already
                elif not enriched_item.get('product_sku'):
                    # Fall back to product SKU if variation SKU not available
                    enriched_item['product_sku'] = getattr(product, 'cin7_sku', '') or getattr(product, 'sku', '')

                # Add variation display info if variations exist
                if item.get('variations'):
                    variation_details = {}
                    if item['variations'].get('size'):
                        variation_details['size'] = item['variations']['size']
                    if item['variations'].get('color'):
                        variation_details['color'] = item['variations']['color']
                    enriched_item['variation_details'] = variation_details

                enriched_items.append(enriched_item)

        # Calculate totals (pass customer for shipping calculation)
        totals = calculate_quotation_totals(quotation_data, customer=request.user)

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
        user_street_address = ''
        user_suburb = ''
        user_city = ''
        user_postcode = ''
        if request.user.is_customer:
            user_full_name = request.user.get_full_name()
            user_address = getattr(request.user, 'address', '')
            user_street_address = getattr(request.user, 'street_address', '')
            user_suburb = getattr(request.user, 'suburb', '')
            user_city = getattr(request.user, 'city', '')
            user_postcode = getattr(request.user, 'postcode', '')

        # Check if cart has bespoke items (for conditional section display)
        has_bespoke_items = any(
            'bespoke' in item.get('product_type', '').lower()
            for item in quotation_data.get('items', [])
        )

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

        # Get shipping details from session if available (for editing quotations)
        shipping_details = quotation_data.get('shipping_details', {})

        # Override user address fields with shipping details if present (editing quotation)
        if shipping_details:
            user_street_address = shipping_details.get('delivery_street_address', user_street_address)
            user_suburb = shipping_details.get('delivery_suburb', user_suburb)
            user_city = shipping_details.get('delivery_city', user_city)
            user_postcode = shipping_details.get('delivery_postcode', user_postcode)

        context = {
            'cart_items': enriched_items,  # Changed from 'items' to match template
            'subtotal': totals['subtotal'],
            'shipping_cost': totals['shipping_cost'],
            'shipping_boxes': totals['shipping_boxes'],
            'shipping_region': totals['shipping_region'],
            'is_rural_delivery': totals['is_rural_delivery'],
            'tax': totals['tax_amount'],
            'total': totals['total'],
            'total_savings': total_savings,
            'institution': institution,
            'institution_type': institution_type,
            'institution_slug': institution_slug,
            'user_full_name': user_full_name,
            'user_address': user_address,
            'user_street_address': user_street_address,
            'user_suburb': user_suburb,
            'user_city': user_city,
            'user_postcode': user_postcode,
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
            'has_bespoke_items': has_bespoke_items,  # Controls bespoke order details section visibility
        }

        return render(request, self.template_name, context)


# =====================================
# AJAX ENDPOINTS
# =====================================

class AddToQuotationView(LoginRequiredMixin, View):
    """AJAX endpoint to add product to quotation with optional addons"""

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

            # Get addons array if provided (only process for Bespoke products)
            addons_json = request.POST.get('addons', '[]')
            addons = []
            player_customizations = []
            if product_type and product_type.lower() == 'bespokeproduct':
                try:
                    addons = json.loads(addons_json)
                except json.JSONDecodeError:
                    addons = []

                # Get player customization data if provided
                player_customizations_json = request.POST.get('player_customizations', '[]')
                try:
                    player_customizations_raw = json.loads(player_customizations_json)
                    # Transform player data to match expected structure
                    # Frontend sends: [{row: 1, name: "John", number: "10", initial: "JD"}, ...]
                    # We need: [{player_name: "John", player_number: "10", player_initial: "JD", size: "", is_complete: true}, ...]
                    for player in player_customizations_raw:
                        player_obj = {
                            'player_name': player.get('name', ''),
                            'player_number': player.get('number', ''),
                            'player_initial': player.get('initial', ''),
                            'size': variations.get('size', '') if variations else '',  # Use product variation size
                            'is_complete': bool(player.get('name', '').strip() and
                                              player.get('number', '').strip() and
                                              player.get('initial', '').strip())
                        }
                        player_customizations.append(player_obj)

                    logger.info(f"Parsed {len(player_customizations)} player customizations from request")
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    logger.warning(f"Error parsing player customizations: {e}")
                    player_customizations = []
            # For non-bespoke products, addons and player_customizations remain empty even if sent

            logger.info(f"AddToQuotation: product_type={product_type}, product_id={product_id}, "
                       f"quantity={quantity}, addons={len(addons)}, player_customizations={len(player_customizations)}")

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

                # For Bespoke products, merge or replace player customizations
                if product_type and product_type.lower() == 'bespokeproduct' and player_customizations:
                    # If there are new player customizations, add them to existing ones
                    existing_players = existing_item.get('player_customizations', [])
                    existing_players.extend(player_customizations)
                    existing_item['player_customizations'] = existing_players

                    # Update completion status
                    existing_item['player_customizations_complete'] = (
                        len(existing_players) > 0 and
                        all(p.get('is_complete', False) for p in existing_players)
                    )
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

                # Use variation price if available and > 0, otherwise fall back to product price
                variation_price = variations.get('price')
                # Convert to Decimal for comparison, handle string/None values
                try:
                    variation_price_decimal = Decimal(str(variation_price)) if variation_price else Decimal('0')
                except (ValueError, InvalidOperation):
                    variation_price_decimal = Decimal('0')

                # Only use variation price if it's greater than 0
                if variation_price_decimal > 0:
                    unit_price = str(variation_price_decimal)
                else:
                    # Fall back to product's margin_75_price, wholesale_price, or price
                    unit_price = str(
                        getattr(product, 'margin_75_price', None) or
                        getattr(product, 'wholesale_price', None) or
                        getattr(product, 'price', 0)
                    )

                # Get margin_75_price from variations or product
                margin_75_price = variations.get('margin_75_price') or str(getattr(product, 'margin_75_price', None) or '')

                # Process addons - format them for storage
                formatted_addons = []
                for addon in addons:
                    addon_type = addon.get('addon_type', '')
                    addon_display_name = addon_type.replace('_', ' ').title()

                    # Build display name with details
                    if addon.get('size'):
                        addon_display_name += f" ({addon['size'].capitalize()})"
                    if addon.get('colors'):
                        addon_display_name += f" - {addon['colors']} colors"
                    if addon.get('stitch_complexity'):
                        addon_display_name += f" ({addon['stitch_complexity'].upper()} stitch)"
                    if addon.get('emb_or_applique'):
                        addon_display_name += f" - {addon['emb_or_applique'].upper()}"

                    formatted_addons.append({
                        'addon_type': addon_type,
                        'display_name': addon_display_name,
                        'size': addon.get('size', ''),
                        'colors': addon.get('colors', ''),
                        'stitch_complexity': addon.get('stitch_complexity', ''),
                        'emb_or_applique': addon.get('emb_or_applique', ''),
                        'quantity': addon.get('quantity', 1),
                        'price_per_unit': str(addon.get('price_per_unit', 0)),
                        'total_price': str(addon.get('total_price', 0)),
                    })

                # Prepare cart item data
                cart_item = {
                    'product_type': product_type,
                    'product_id': product_id,
                    'product_name': product_name,
                    'product_sku': product_sku,
                    'quantity': quantity,
                    'unit_price': str(unit_price),
                    'margin_75_price': margin_75_price,
                    'variations': variations,
                    'addons': formatted_addons,  # Store addons with the product
                }

                # Initialize player customizations fields for Bespoke products
                if product_type and product_type.lower() == 'bespokeproduct':
                    cart_item['player_customizations'] = player_customizations
                    # Check if all players have complete data
                    cart_item['player_customizations_complete'] = (
                        len(player_customizations) > 0 and
                        all(p.get('is_complete', False) for p in player_customizations)
                    )

                quotation_data['items'].append(cart_item)

            # Save session
            save_quotation_session(request, quotation_data)

            # Calculate totals
            totals = calculate_quotation_totals(quotation_data)

            # Log action
            variation_info = f" ({variations.get('size', '')})" if variations.get('size') else ""
            addons_info = f" with {len(addons)} customization(s)" if addons else ""
            if existing_item:
                action_desc = f'Updated quotation: Changed "{product.name}{variation_info}" quantity to {quantity}'
            else:
                action_desc = f'Updated quotation: Added item "{product.name}{variation_info}"{addons_info} (Qty: {quantity}, Price: ${unit_price})'
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


# REMOVED: AddAddonToQuotationView - Addons are now added together with the base product in AddToQuotationView


class UpdatePlayerCustomizationsView(LoginRequiredMixin, View):
    """AJAX endpoint to update player customization data for a cart item"""

    def post(self, request):
        try:
            import json

            item_index = int(request.POST.get('item_index'))
            player_customizations_json = request.POST.get('player_customizations', '[]')

            # Parse player customizations data
            try:
                player_customizations = json.loads(player_customizations_json)
            except json.JSONDecodeError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid player customizations data format'
                }, status=400)

            # Get quotation session
            quotation_data = get_quotation_session(request)

            # Validate item index
            if item_index < 0 or item_index >= len(quotation_data['items']):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid item index'
                }, status=400)

            item = quotation_data['items'][item_index]

            # Ensure this is a Bespoke product
            product_type = item.get('product_type', '')
            if not product_type or product_type.lower() != 'bespokeproduct':
                return JsonResponse({
                    'success': False,
                    'error': 'Player customizations can only be added to Bespoke products'
                }, status=400)

            # Update player customizations
            item['player_customizations'] = player_customizations
            item['player_customizations_complete'] = len(player_customizations) > 0

            # Save session
            save_quotation_session(request, quotation_data)

            # Calculate updated totals
            totals = calculate_quotation_totals(quotation_data)

            # Log action
            product_name = item.get('product_name', 'Unknown Product')
            player_count = len(player_customizations)
            logger.info(
                f"Updated player customizations for item {item_index} ({product_name}): "
                f"{player_count} players"
            )

            AuditLog.log_action(
                user=request.user,
                action_type='quotation_updated',
                description=f'Updated player customizations for "{product_name}": {player_count} players',
                request=request,
                affected_model='QuotationItem',
                product_name=product_name,
            )

            return JsonResponse({
                'success': True,
                'item_count': totals['item_count'],
                'subtotal': str(totals['subtotal']),
                'total': str(totals['total']),
                'player_count': player_count,
            })

        except Exception as e:
            logger.error(f"Error updating player customizations: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class GetPlayerCustomizationsView(LoginRequiredMixin, View):
    """AJAX endpoint to retrieve player customization data for a cart item"""

    def get(self, request, cart_index):
        try:
            # Get quotation session
            quotation_data = get_quotation_session(request)

            # Validate cart_index is within bounds
            if cart_index < 0 or cart_index >= len(quotation_data['items']):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid cart index'
                }, status=404)

            item = quotation_data['items'][cart_index]

            # Ensure this is a Bespoke product
            product_type = item.get('product_type', '')
            if not product_type or product_type.lower() != 'bespokeproduct':
                return JsonResponse({
                    'success': False,
                    'error': 'Player customizations are only available for Bespoke products'
                }, status=400)

            # Get player customizations (return empty array if not found)
            players = item.get('player_customizations', [])

            # Calculate statistics
            total_players = len(players)
            complete_players = sum(1 for p in players if p.get('is_complete', False))
            incomplete_players = total_players - complete_players

            stats = {
                'total': total_players,
                'complete': complete_players,
                'incomplete': incomplete_players
            }

            # Extract product information
            product_info = {
                'name': item.get('product_name', 'Unknown Product'),
                'color': item.get('variations', {}).get('color', ''),
                'size': item.get('variations', {}).get('size', ''),
                'quantity': item.get('quantity', 1),
                'image_url': item.get('product_image_url', '')
            }

            logger.info(
                f"Retrieved player customizations for cart item {cart_index}: "
                f"{total_players} players ({complete_players} complete, {incomplete_players} incomplete)"
            )

            return JsonResponse({
                'success': True,
                'players': players,
                'stats': stats,
                'product': product_info
            })

        except ValueError as e:
            logger.error(f"ValueError in GetPlayerCustomizationsView: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Invalid cart index format'
            }, status=400)

        except Exception as e:
            logger.error(f"Error retrieving player customizations: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


class RemoveAddonView(LoginRequiredMixin, View):
    """AJAX endpoint to remove individual addon from cart item"""

    def post(self, request):
        try:
            item_index = int(request.POST.get('item_index'))
            addon_index = int(request.POST.get('addon_index'))

            # Get quotation session
            quotation_data = get_quotation_session(request)

            # Validate item index
            if item_index < 0 or item_index >= len(quotation_data['items']):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid item index'
                }, status=400)

            item = quotation_data['items'][item_index]

            # Validate addon index
            addons = item.get('addons', [])
            if addon_index < 0 or addon_index >= len(addons):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid addon index'
                }, status=400)

            # Get addon info before removal for logging
            removed_addon = addons[addon_index]
            addon_name = removed_addon.get('display_name', 'Unknown Addon')

            # Remove addon
            addons.pop(addon_index)
            item['addons'] = addons

            # Save session
            save_quotation_session(request, quotation_data)

            # Recalculate totals
            totals = calculate_quotation_totals(quotation_data)

            # Log action
            product_name = item.get('product_name', 'Unknown Product')
            logger.info(
                f"Removed addon from item {item_index} ({product_name}): "
                f"{addon_name}"
            )

            AuditLog.log_action(
                user=request.user,
                action_type='quotation_updated',
                description=f'Removed addon "{addon_name}" from "{product_name}"',
                request=request,
                affected_model='QuotationItem',
                product_name=product_name,
            )

            return JsonResponse({
                'success': True,
                'item_count': totals['item_count'],
                'subtotal': str(totals['subtotal']),
                'total': str(totals['total']),
                'remaining_addons': len(addons),
            })

        except Exception as e:
            logger.error(f"Error removing addon: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


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

            # If this is a bespoke product, sync addon quantities and player details
            if item.get('product_type', '').lower() == 'bespokeproduct':
                # Sync addon quantities
                if item.get('addons'):
                    logger.info(f"Syncing addon quantities for bespoke product. Parent qty changed from {old_quantity} to {quantity}")

                    for addon in item['addons']:
                        old_addon_qty = addon.get('quantity', 0)

                        # Update addon quantity to match parent quantity
                        addon['quantity'] = quantity

                        # Recalculate addon total price based on new quantity
                        price_per_unit = Decimal(str(addon.get('price_per_unit', 0)))
                        new_total_price = price_per_unit * Decimal(str(quantity))
                        addon['total_price'] = str(new_total_price)

                        logger.info(f"Addon '{addon.get('addon_type')}' qty updated from {old_addon_qty} to {quantity}, new total: {new_total_price}")

                # Sync player customizations
                player_customizations = item.get('player_customizations', [])
                current_player_count = len(player_customizations)

                if quantity > current_player_count:
                    # INCREASE: Add empty player slots
                    logger.info(f"Increasing player slots from {current_player_count} to {quantity}")
                    for i in range(current_player_count, quantity):
                        player_customizations.append({
                            'player_name': '',
                            'player_number': '',
                            'player_initial': '',
                            'size': item.get('variations', {}).get('size', ''),
                            'is_complete': False
                        })
                    item['player_customizations'] = player_customizations
                    item['player_customizations_complete'] = False
                    logger.info(f"Added {quantity - current_player_count} empty player slots")

                elif quantity < current_player_count:
                    # DECREASE: Require user to select which players to keep
                    logger.info(f"Quantity decrease detected: {current_player_count} players → {quantity} quantity. Requiring player selection.")
                    return JsonResponse({
                        'success': False,
                        'requires_player_selection': True,
                        'message': f'This item has {current_player_count} player details but you are decreasing quantity to {quantity}. Please select which players to keep.',
                        'current_players': player_customizations,
                        'new_quantity': quantity,
                        'item_index': item_index
                    })

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


class UpdateQuotationItemWithPlayersView(LoginRequiredMixin, View):
    """AJAX endpoint to update quotation item quantity with player selection"""

    def post(self, request):
        try:
            item_index = int(request.POST.get('item_index'))
            quantity = int(request.POST.get('quantity'))
            player_customizations_json = request.POST.get('player_customizations', '[]')

            if quantity < 1:
                return JsonResponse({'success': False, 'error': 'Quantity must be at least 1'}, status=400)

            try:
                player_customizations = json.loads(player_customizations_json)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in player_customizations: {player_customizations_json}")
                return JsonResponse({'success': False, 'error': 'Invalid player data format'}, status=400)

            quotation_data = get_quotation_session(request)

            if item_index < 0 or item_index >= len(quotation_data['items']):
                return JsonResponse({'success': False, 'error': 'Invalid item index'}, status=400)

            item = quotation_data['items'][item_index]
            old_quantity = item.get('quantity', 0)

            # Validate that player count matches new quantity
            if len(player_customizations) != quantity:
                return JsonResponse({
                    'success': False,
                    'error': f'Player count ({len(player_customizations)}) must match quantity ({quantity})'
                }, status=400)

            # Update quantity
            item['quantity'] = quantity

            # Update player customizations
            item['player_customizations'] = player_customizations
            item['player_customizations_complete'] = (
                len(player_customizations) > 0 and
                all(p.get('is_complete', False) for p in player_customizations)
            )

            # Sync addon quantities if this is a bespoke product with addons
            if item.get('product_type', '').lower() == 'bespokeproduct' and item.get('addons'):
                logger.info(f"Syncing addon quantities after player selection. Qty changed from {old_quantity} to {quantity}")
                for addon in item['addons']:
                    addon['quantity'] = quantity
                    price_per_unit = Decimal(str(addon.get('price_per_unit', 0)))
                    new_total_price = price_per_unit * Decimal(str(quantity))
                    addon['total_price'] = str(new_total_price)

            save_quotation_session(request, quotation_data)

            logger.info(f"Updated item {item_index} quantity to {quantity} with {len(player_customizations)} selected players")

            # Log action
            AuditLog.log_action(
                user=request.user,
                action_type='quotation_updated',
                description=f'Updated quotation: Changed "{item["product_name"]}" quantity from {old_quantity} to {quantity} with player selection',
                request=request,
                affected_model='QuotationItem',
                product_name=item['product_name'],
                product_type=item.get('product_type', 'unknown'),
                item_index=item_index,
                old_quantity=old_quantity,
                new_quantity=quantity,
                player_count=len(player_customizations)
            )

            return JsonResponse({'success': True})

        except ValueError as e:
            logger.error(f"Invalid input in update with players: {e}")
            return JsonResponse({'success': False, 'error': 'Invalid input values'}, status=400)
        except Exception as e:
            logger.error(f"Error updating item with players: {e}", exc_info=True)
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

def parse_order_date(date_string):
    """
    Parse order_required_date from either HTML5 date format (YYYY-MM-DD) or display format (DD/MM/YYYY).
    Returns a date object or None if parsing fails.
    """
    if not date_string:
        return None

    from datetime import datetime

    # Try YYYY-MM-DD format first (HTML5 date input)
    try:
        return datetime.strptime(date_string, '%Y-%m-%d').date()
    except ValueError:
        pass

    # Try DD/MM/YYYY format (formatted display)
    try:
        return datetime.strptime(date_string, '%d/%m/%Y').date()
    except ValueError:
        logger.warning(f"Could not parse order_required_date: {date_string}")
        return None


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
                    recipient_phone = request.POST.get('recipient_phone', '').strip()
                    recipient_address = request.POST.get('recipient_address', '').strip()
                    additional_emails = request.POST.get('additional_emails', '').strip()

                    # Capture structured delivery address fields
                    delivery_street_address = request.POST.get('delivery_street_address', '').strip()
                    delivery_suburb = request.POST.get('delivery_suburb', '').strip()
                    delivery_city = request.POST.get('delivery_city', '').strip()
                    delivery_postcode = request.POST.get('delivery_postcode', '').strip()
                    delivery_state = request.POST.get('delivery_state', '').strip()

                    # Validate additional emails
                    is_valid, error_message = validate_additional_emails(additional_emails)
                    if not is_valid:
                        return JsonResponse({
                            'success': False,
                            'error': error_message
                        }, status=400)

                    if recipient_name:
                        quotation.recipient_name = recipient_name
                    if recipient_phone:
                        quotation.recipient_phone = recipient_phone
                    if recipient_address:
                        quotation.recipient_address = recipient_address
                    quotation.additional_emails = additional_emails

                    # Update structured delivery address fields
                    quotation.delivery_street_address = delivery_street_address
                    quotation.delivery_suburb = delivery_suburb
                    quotation.delivery_city = delivery_city
                    quotation.delivery_postcode = delivery_postcode
                    quotation.delivery_state = delivery_state

                    # Extract and update bespoke order fields
                    shipping_mode = request.POST.get('shipping_mode', 'sea').strip()
                    if shipping_mode not in ['sea', 'air']:
                        shipping_mode = 'sea'  # Default to sea if invalid
                    quotation.shipping_mode = shipping_mode

                    order_label = request.POST.get('order_label', '').strip()
                    if order_label:
                        quotation.order_label = order_label[:255]  # Enforce max length

                    order_required_date_str = request.POST.get('order_required_date', '').strip()
                    if order_required_date_str:
                        parsed_date = parse_order_date(order_required_date_str)
                        if parsed_date:
                            quotation.order_required_date = parsed_date
                            logger.info(f"Updated order_required_date: {parsed_date}")

                    logger.info(f"Updated bespoke fields - shipping_mode: {shipping_mode}, order_label: {order_label}")

                    # Update CIN7 contact fields from institution if institution is linked
                    if quotation.institution:
                        quotation.cin7_email = getattr(quotation.institution, 'cin7_email', '') or ''
                        quotation.cin7_first_name = getattr(quotation.institution, 'cin7_first_name', '') or ''
                        quotation.cin7_last_name = getattr(quotation.institution, 'cin7_last_name', '') or ''
                        quotation.cin7_phone = getattr(quotation.institution, 'cin7_phone', '') or ''

                        # Log CIN7 contact update for debugging
                        if quotation.cin7_email or quotation.cin7_first_name or quotation.cin7_last_name or quotation.cin7_phone:
                            logger.info(
                                f"Updated CIN7 contact from institution during edit: "
                                f"email={quotation.cin7_email}, name={quotation.cin7_first_name} {quotation.cin7_last_name}, "
                                f"phone={quotation.cin7_phone}"
                            )

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

                # Capture CIN7 contact details from institution (if available)
                cin7_email = ''
                cin7_first_name = ''
                cin7_last_name = ''
                cin7_phone = ''

                if institution:
                    cin7_email = getattr(institution, 'cin7_email', '') or ''
                    cin7_first_name = getattr(institution, 'cin7_first_name', '') or ''
                    cin7_last_name = getattr(institution, 'cin7_last_name', '') or ''
                    cin7_phone = getattr(institution, 'cin7_phone', '') or ''

                    # Log CIN7 contact capture for debugging
                    if cin7_email or cin7_first_name or cin7_last_name or cin7_phone:
                        logger.info(
                            f"Captured CIN7 contact from {institution_type}: "
                            f"email={cin7_email}, name={cin7_first_name} {cin7_last_name}, phone={cin7_phone}"
                        )

                # Get recipient information from POST data
                recipient_name = request.POST.get('recipient_name', '').strip()
                recipient_phone = request.POST.get('recipient_phone', '').strip()
                recipient_address = request.POST.get('recipient_address', '').strip()
                additional_emails = request.POST.get('additional_emails', '').strip()

                # Capture structured delivery address fields
                delivery_street_address = request.POST.get('delivery_street_address', '').strip()
                delivery_suburb = request.POST.get('delivery_suburb', '').strip()
                delivery_city = request.POST.get('delivery_city', '').strip()
                delivery_postcode = request.POST.get('delivery_postcode', '').strip()
                delivery_state = request.POST.get('delivery_state', '').strip()

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

                # Extract bespoke order fields (for new quotations)
                shipping_mode = request.POST.get('shipping_mode', 'sea').strip()
                if shipping_mode not in ['sea', 'air']:
                    shipping_mode = 'sea'  # Default to sea if invalid

                order_label = request.POST.get('order_label', '').strip()
                if len(order_label) > 255:
                    order_label = order_label[:255]  # Enforce max length

                order_required_date = None
                order_required_date_str = request.POST.get('order_required_date', '').strip()
                if order_required_date_str:
                    order_required_date = parse_order_date(order_required_date_str)
                    if order_required_date:
                        logger.info(f"Parsed order_required_date: {order_required_date}")

                logger.info(f"Creating quotation with bespoke fields - shipping_mode: {shipping_mode}, order_label: {order_label}")

                # Create Quotation (with or without institution)
                quotation = Quotation.objects.create(
                    created_by=request.user,
                    institution_content_type=institution_content_type,
                    institution_object_id=institution.id if institution else None,
                    status='pending',  # Changed from 'draft' to 'pending' for approval workflow
                    recipient_name=recipient_name,
                    recipient_phone=recipient_phone,
                    recipient_address=recipient_address,
                    additional_emails=additional_emails,
                    assigned_sales_rep=assigned_sales_rep,
                    account_manager=account_manager,
                    # Structured delivery address fields
                    delivery_street_address=delivery_street_address,
                    delivery_suburb=delivery_suburb,
                    delivery_city=delivery_city,
                    delivery_postcode=delivery_postcode,
                    delivery_state=delivery_state,
                    # CIN7 contact fields (captured from institution)
                    cin7_email=cin7_email,
                    cin7_first_name=cin7_first_name,
                    cin7_last_name=cin7_last_name,
                    cin7_phone=cin7_phone,
                    # Bespoke order fields
                    shipping_mode=shipping_mode,
                    order_label=order_label,
                    order_required_date=order_required_date,
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

                # Create base garment item
                # Prepare variations data with player customizations for Bespoke products
                variations_data = item_data.get('variations', {})
                product_type = item_data.get('product_type', '')

                # Store player customizations in variations JSONField for Bespoke products
                if product_type and product_type.lower() == 'bespokeproduct':
                    player_customizations = item_data.get('player_customizations', [])
                    if player_customizations:
                        variations_data['player_customizations'] = player_customizations

                base_item = QuotationItem.objects.create(
                    quotation=quotation,
                    product_content_type=product_content_type,
                    product_object_id=product.id,
                    product_name=item_data.get('product_name', product.name),
                    product_sku=item_data.get('product_sku', getattr(product, 'cin7_sku', '') or getattr(product, 'sku', '')),
                    product_image_url=product_image_url,
                    quantity=item_data['quantity'],
                    unit_price=Decimal(str(item_data['unit_price'])),
                    variations=variations_data,
                )
                items_created += 1

                # Create addon items ONLY for Bespoke products
                if product_type and product_type.lower() == 'bespokeproduct':
                    for addon in item_data.get('addons', []):
                        QuotationItem.objects.create(
                            quotation=quotation,
                            product_content_type=product_content_type,
                            product_object_id=product.id,
                            product_name=addon.get('display_name', 'Customization'),
                            product_sku='',
                            product_image_url='',
                            quantity=addon.get('quantity', 1),
                            unit_price=Decimal(str(addon.get('price_per_unit', 0))),
                            variations={
                                'size': addon.get('size', ''),
                                'colors': addon.get('colors', ''),
                                'stitch_complexity': addon.get('stitch_complexity', ''),
                                'emb_or_applique': addon.get('emb_or_applique', ''),
                            },
                            is_addon=True,
                            parent_item=base_item,
                            addon_type=addon.get('addon_type', ''),
                        )

            if items_created == 0:
                if not is_editing:
                    quotation.delete()
                return JsonResponse({
                    'success': False,
                    'error': 'No valid products found in your cart. Please try again.'
                }, status=400)

            # Calculate quotation totals
            quotation.calculate_totals()

            # Calculate air freight surcharge if applicable (6% of subtotal)
            if quotation.shipping_mode == 'air':
                air_surcharge = (quotation.subtotal * Decimal('0.06')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                quotation.air_freight_surcharge = air_surcharge
                quotation.save(update_fields=['air_freight_surcharge'])
                logger.info(f"Applied air freight surcharge: ${air_surcharge} (6% of ${quotation.subtotal})")
            else:
                # Ensure surcharge is zero for sea freight
                quotation.air_freight_surcharge = Decimal('0.00')
                quotation.save(update_fields=['air_freight_surcharge'])

            # Track account manager edits
            if is_editing:
                # Update edit tracking fields
                quotation.last_edited_by = request.user
                quotation.last_edited_at = timezone.now()
                quotation.save(update_fields=['last_edited_by', 'last_edited_at', 'updated_at'])

                # Create version snapshot with appropriate note
                try:
                    if request.user.is_account_manager or request.user.is_admin:
                        version_note = f"Edited by Account Manager: {request.user.get_full_name()}"
                    else:
                        version_note = f"Edited by {request.user.get_full_name()}"

                    quotation.create_edit_snapshot(
                        user=request.user,
                        change_note=change_note,
                        description=f'{version_note}: {items_created} items'
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
            'rejected_by',
            'customer_approved_by',
            'approval_override_by'
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

            # Permission check logic:
            # 1. Owner can edit draft/pending quotations
            # 2. Account Managers can edit pending quotations (for approval workflow)
            # 3. Admins can edit any non-approved quotations

            # Allow owner to edit draft/pending quotations
            if quotation.created_by == request.user and quotation.status in ['draft', 'pending', 'rejected']:
                pass  # Permission granted
            # Allow account managers to edit pending quotations
            elif quotation.can_be_edited_by_account_manager(request.user):
                pass  # Permission granted
            # Allow admins to edit any non-approved quotations
            elif request.user.is_admin and quotation.status not in ['approved', 'confirmed']:
                pass  # Permission granted
            else:
                messages.error(request, 'You do not have permission to edit this quotation.')
                return redirect('quotations:quotation-detail', pk=quotation.id)

            # Prevent editing if approved/confirmed
            if quotation.status in ['approved', 'confirmed']:
                messages.error(request, 'Approved or confirmed quotations cannot be edited.')
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

            # Load shipping details from quotation
            # Check if any delivery address field has data
            if any([quotation.delivery_street_address, quotation.delivery_suburb,
                   quotation.delivery_city, quotation.delivery_postcode, quotation.delivery_state]):
                quotation_data['shipping_details'] = {
                    'delivery_street_address': quotation.delivery_street_address or '',
                    'delivery_suburb': quotation.delivery_suburb or '',
                    'delivery_city': quotation.delivery_city or '',
                    'delivery_postcode': quotation.delivery_postcode or '',
                    'delivery_state': quotation.delivery_state or '',
                }

            # Load bespoke order details if present
            if quotation.order_label or quotation.order_required_date:
                quotation_data['bespoke_details'] = {
                    'shipping_mode': quotation.shipping_mode,
                    'order_label': quotation.order_label or '',
                    'order_required_date': quotation.order_required_date.strftime('%Y-%m-%d') if quotation.order_required_date else '',
                }

            # Load quotation items into session
            # Build a map of parent items and their addons
            parent_items = {}
            addon_items = {}

            for item in quotation.items.all():
                if item.is_addon:
                    # Store addon items separately
                    parent_id = str(item.parent_item_id) if item.parent_item_id else None
                    if parent_id not in addon_items:
                        addon_items[parent_id] = []

                    addon_data = {
                        'addon_type': item.addon_type,
                        'display_name': item.product_name,
                        'size': item.variations.get('size', ''),
                        'colors': item.variations.get('colors', ''),
                        'stitch_complexity': item.variations.get('stitch_complexity', ''),
                        'emb_or_applique': item.variations.get('emb_or_applique', ''),
                        'quantity': item.quantity,
                        'price_per_unit': str(item.unit_price),
                        'total_price': str(item.unit_price * item.quantity),
                    }
                    addon_items[parent_id].append(addon_data)
                else:
                    # Store parent items with their UUID as key
                    item_id = str(item.id)
                    parent_items[item_id] = {
                        'product_type': item.product_content_type.model,
                        'product_id': item.product_object_id,
                        'product_name': item.product_name,
                        'product_sku': item.product_sku,
                        'quantity': item.quantity,
                        'unit_price': str(item.unit_price),
                        'margin_75_price': '',  # Will be populated if available
                        'variations': item.variations,
                        'is_addon': False,
                    }

                    # Extract player_customizations from variations for BespokeProduct
                    if item.product_content_type.model == 'bespokeproduct':
                        if 'player_customizations' in item.variations:
                            parent_items[item_id]['player_customizations'] = item.variations['player_customizations']

            # Reconstruct items array with nested addon structure
            for item_id, item_data in parent_items.items():
                # Attach addons to their parent
                if item_id in addon_items:
                    item_data['addons'] = addon_items[item_id]

                quotation_data['items'].append(item_data)

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
# DUPLICATE QUOTATION VIEW
# =====================================

class DuplicateQuotationView(LoginRequiredMixin, View):
    """
    Duplicate an existing quotation as a new draft quotation.

    Creates a complete copy of the quotation with:
    - All items (with variations, addons, player customizations)
    - Recipient and delivery information
    - Bespoke order details
    - Institution reference
    - Assigned staff

    Resets:
    - Status to 'draft'
    - created_by to current user
    - New quotation number
    - Fresh expiry date
    - Clear approval/sync/edit history
    """

    def get(self, request, pk):
        """Handle GET request to duplicate quotation"""
        try:
            # Get the original quotation
            original = get_object_or_404(Quotation, pk=pk)

            # Permission check:
            # - Quotation creator
            # - Sales rep assigned to quotation
            # - Account managers
            # - Admin users
            can_duplicate = (
                original.created_by == request.user or
                original.assigned_sales_rep == request.user or
                request.user.is_account_manager or
                request.user.is_admin
            )

            if not can_duplicate:
                messages.error(request, 'You do not have permission to duplicate this quotation.')
                return redirect('quotations:quotation-detail', pk=original.id)

            # Use transaction to ensure atomicity
            with transaction.atomic():
                # Create new quotation instance (copy all fields)
                new_quotation = Quotation()

                # Copy basic fields from original
                new_quotation.created_by = request.user  # Set to current user
                new_quotation.assigned_sales_rep = original.assigned_sales_rep
                new_quotation.account_manager = original.account_manager

                # Copy institution reference
                new_quotation.institution_content_type = original.institution_content_type
                new_quotation.institution_object_id = original.institution_object_id

                # Set status to draft
                new_quotation.status = 'draft'

                # Dates - will be set automatically by save() method
                # expires_at will be set by save() based on site settings
                # created_at, updated_at will be auto-populated

                # Copy pricing fields (will be recalculated)
                new_quotation.discount_percentage = original.discount_percentage
                new_quotation.discount_amount = original.discount_amount
                new_quotation.tax_percentage = original.tax_percentage

                # Copy recipient information
                new_quotation.recipient_name = original.recipient_name
                new_quotation.recipient_phone = original.recipient_phone
                new_quotation.recipient_address = original.recipient_address
                new_quotation.additional_emails = original.additional_emails

                # Copy delivery address fields
                new_quotation.delivery_street_address = original.delivery_street_address
                new_quotation.delivery_suburb = original.delivery_suburb
                new_quotation.delivery_city = original.delivery_city
                new_quotation.delivery_postcode = original.delivery_postcode
                new_quotation.delivery_state = original.delivery_state

                # Copy bespoke order fields
                new_quotation.shipping_mode = original.shipping_mode
                new_quotation.order_label = original.order_label
                new_quotation.order_required_date = original.order_required_date

                # Copy notes
                new_quotation.notes = original.notes
                new_quotation.customer_notes = original.customer_notes
                new_quotation.terms_and_conditions = original.terms_and_conditions

                # Copy reference fields
                new_quotation.reference_number = original.reference_number

                # Copy CIN7 contact fields (from institution snapshot)
                new_quotation.cin7_email = original.cin7_email
                new_quotation.cin7_first_name = original.cin7_first_name
                new_quotation.cin7_last_name = original.cin7_last_name
                new_quotation.cin7_phone = original.cin7_phone

                # Reset fields - these should NOT be copied:
                # - quotation_number: will be auto-generated by save()
                # - version: will default to 1
                # - approved_at, rejected_at, approved_by, rejected_by, rejection_reason
                # - submitted_for_approval_at, submitted_by
                # - customer_approved_at, customer_approved_by
                # - account_manager_approved_at
                # - approval_override_by, approval_override_at
                # - last_edited_by, last_edited_at
                # - is_locked
                # - cin7_so_number, cin7_so_id, cin7_sync_status, cin7_sync_error, cin7_synced_at
                # - subtotal, tax_amount, total, shipping_cost, shipping_boxes, shipping_region, is_rural_delivery, air_freight_surcharge
                # (These will be recalculated)

                # Save new quotation (this generates quotation_number and sets defaults)
                new_quotation.save()

                # Copy quotation items
                # Build a mapping of original item IDs to new item IDs for addon parent references
                item_id_mapping = {}

                # First pass: Copy base items (non-addon items)
                for original_item in original.items.filter(is_addon=False).order_by('sort_order', 'created_at'):
                    new_item = QuotationItem()

                    # Link to new quotation
                    new_item.quotation = new_quotation

                    # Copy product reference
                    new_item.product_content_type = original_item.product_content_type
                    new_item.product_object_id = original_item.product_object_id

                    # Copy product snapshot
                    new_item.product_snapshot = original_item.product_snapshot

                    # Copy item details
                    new_item.product_name = original_item.product_name
                    new_item.product_sku = original_item.product_sku
                    new_item.product_image_url = original_item.product_image_url

                    # Copy quantity and pricing
                    new_item.quantity = original_item.quantity
                    new_item.unit_price = original_item.unit_price

                    # Copy variations (includes player_customizations for Bespoke)
                    new_item.variations = original_item.variations

                    # Copy notes
                    new_item.notes = original_item.notes

                    # Copy ordering
                    new_item.sort_order = original_item.sort_order

                    # Reset fields - these will be recalculated/re-looked-up on save:
                    # - line_total (calculated on save)
                    # - cin7_product_option_id, cin7_match_method, cin7_matched_at (will be re-looked-up)

                    # Save new item (this triggers CIN7 lookup and calculates line_total)
                    new_item.save()

                    # Store mapping for addon items
                    item_id_mapping[original_item.id] = new_item.id

                    logger.info(f"Duplicated item: {new_item.product_name} (original: {original_item.id}, new: {new_item.id})")

                # Second pass: Copy addon items with updated parent references
                for original_addon in original.items.filter(is_addon=True).order_by('sort_order', 'created_at'):
                    new_addon = QuotationItem()

                    # Link to new quotation
                    new_addon.quotation = new_quotation

                    # Copy product reference
                    new_addon.product_content_type = original_addon.product_content_type
                    new_addon.product_object_id = original_addon.product_object_id

                    # Copy product snapshot
                    new_addon.product_snapshot = original_addon.product_snapshot

                    # Copy item details
                    new_addon.product_name = original_addon.product_name
                    new_addon.product_sku = original_addon.product_sku
                    new_addon.product_image_url = original_addon.product_image_url

                    # Copy quantity and pricing
                    new_addon.quantity = original_addon.quantity
                    new_addon.unit_price = original_addon.unit_price

                    # Copy variations
                    new_addon.variations = original_addon.variations

                    # Copy notes
                    new_addon.notes = original_addon.notes

                    # Copy addon-specific fields
                    new_addon.is_addon = True
                    new_addon.addon_type = original_addon.addon_type
                    new_addon.addon_details = original_addon.addon_details

                    # Update parent_item reference using mapping
                    if original_addon.parent_item_id and original_addon.parent_item_id in item_id_mapping:
                        new_addon.parent_item_id = item_id_mapping[original_addon.parent_item_id]

                    # Copy ordering
                    new_addon.sort_order = original_addon.sort_order

                    # Save new addon item
                    new_addon.save()

                    logger.info(f"Duplicated addon: {new_addon.product_name} (original: {original_addon.id}, new: {new_addon.id})")

                # Recalculate totals (subtotal, shipping, tax, total)
                new_quotation.calculate_totals()

                # Create initial version snapshot
                new_quotation.create_version_snapshot(
                    description=f'Duplicated from quotation {original.quotation_number}',
                    user=request.user,
                    change_note=f'Quotation duplicated from {original.quotation_number} by {request.user.get_full_name()}'
                )

                # Log action
                AuditLog.log_action(
                    user=request.user,
                    action_type='quotation_duplicated',
                    description=f'Duplicated quotation {original.quotation_number} → {new_quotation.quotation_number}',
                    request=request,
                    affected_model='Quotation',
                    affected_object_id=str(new_quotation.id),
                    original_quotation_id=str(original.id),
                    original_quotation_number=original.quotation_number,
                    new_quotation_id=str(new_quotation.id),
                    new_quotation_number=new_quotation.quotation_number,
                    items_count=new_quotation.items.count()
                )

                logger.info(
                    f"Successfully duplicated quotation: {original.quotation_number} → {new_quotation.quotation_number} "
                    f"({new_quotation.items.count()} items) by user {request.user.get_full_name()}"
                )

                messages.success(
                    request,
                    f'Quotation duplicated successfully! New quotation number: {new_quotation.quotation_number}'
                )

                # Redirect to edit view to allow user to review and modify
                return redirect('quotations:edit-quotation', pk=new_quotation.id)

        except Quotation.DoesNotExist:
            messages.error(request, 'Quotation not found.')
            return redirect('quotations:my-quotations')

        except Exception as e:
            logger.error(f"Error duplicating quotation {pk}: {e}", exc_info=True)
            messages.error(request, f'An error occurred while duplicating the quotation: {str(e)}')
            return redirect('quotations:quotation-detail', pk=pk)


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

        # Get quotation items with product details and prefetch addons
        context['items'] = self.object.items.filter(is_addon=False).select_related('product_content_type').prefetch_related('addons').order_by('sort_order', 'created_at')

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

        # Add product descriptions if available (BallStore products)
        context['description'] = getattr(product, 'description', '')
        context['short_description'] = getattr(product, 'short_description', '')

        # Determine active tab based on product type
        if product_type.lower() in ['tusproduct', 'wholesaleproduct']:
            context['active_tab'] = 'schools'
        elif product_type.lower() == 'bespokeproduct':
            context['active_tab'] = 'custom_garments'
        elif product_type.lower() == 'ballstoreproduct':
            context['active_tab'] = 'accessories'
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
                elif product_type.lower() == 'ballstoreproduct':
                    var_data['sku'] = getattr(variation, 'sku', '')
                    var_data['description'] = getattr(variation, 'description', '')
                    var_data['attributes'] = getattr(variation, 'attributes', [])
                elif product_type.lower() == 'bespokeproduct':
                    var_data['sku'] = getattr(variation, 'sku', '')
                    var_data['description'] = getattr(variation, 'description', '')
                    # Construct attributes array from option1_value, option2_value, option3_value
                    attributes = []
                    if hasattr(variation, 'option1_value') and variation.option1_value:
                        attributes.append({
                            'name': 'Size',  # Typically option1 is size for bespoke products
                            'option': variation.option1_value
                        })
                    if hasattr(variation, 'option2_value') and variation.option2_value:
                        attributes.append({
                            'name': 'Color',  # Typically option2 is color for bespoke products
                            'option': variation.option2_value
                        })
                    if hasattr(variation, 'option3_value') and variation.option3_value:
                        attributes.append({
                            'name': 'Option3',
                            'option': variation.option3_value
                        })
                    var_data['attributes'] = attributes

                # Add image URL if available
                image_url = None
                if hasattr(variation, 'image') and variation.image:
                    # Handle both ImageField (has .url) and string URLs
                    image_url = variation.image.url if hasattr(variation.image, 'url') else variation.image
                elif hasattr(variation, 'main_image') and variation.main_image:
                    # Handle both ImageField (has .url) and string URLs
                    image_url = variation.main_image.url if hasattr(variation.main_image, 'url') else variation.main_image
                elif hasattr(variation, 'image_url') and variation.image_url:
                    # BallStore uses image_url field
                    image_url = variation.image_url

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
        # Logic: For BespokeProduct, check main product's cost price (variations inherit pricing)
        #        For other products with variations, check if ALL variations are missing cost price
        #        If no variations, check main product's cost price
        if product_type.lower() == 'bespokeproduct':
            # Bespoke products: Check main product's cost price (variations inherit pricing)
            context['product_missing_cost_price'] = (
                not hasattr(product, 'cost_price') or
                product.cost_price is None or
                product.cost_price <= 0
            )
        elif variations:
            # Other products with variations: Check if ALL variations are missing cost price
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

        # Add addon products for BespokeProduct (same logic as bespoke app)
        if product_type.lower() == 'bespokeproduct':
            # Only add addons if this is a base garment product (not an addon product itself)
            from bespoke.models import BespokeCategory

            is_base_garment = False
            try:
                # Get product categories
                categories = []
                if hasattr(product, 'category_assignments'):
                    categories = [assignment.category for assignment in product.category_assignments.all()]

                # Check if product is in base-garment category (not in addon category)
                for category in categories:
                    if 'base' in category.slug.lower() or 'garment' in category.slug.lower():
                        is_base_garment = True
                        break
                    if 'addon' in category.slug.lower():
                        is_base_garment = False
                        break
            except Exception as e:
                logger.error(f"Error checking if product is base garment: {e}")

            if is_base_garment:
                # Fetch addon products
                try:
                    addon_category = BespokeCategory.objects.filter(
                        slug__icontains='addon',
                        is_active=True
                    ).first()

                    if addon_category:
                        from bespoke.models import BespokeProduct as BespokeProductModel
                        addon_products = BespokeProductModel.objects.filter(
                            category_assignments__category=addon_category,
                            is_active=True
                        ).prefetch_related('variations').distinct().order_by('name')

                        # Group by type based on SKU patterns
                        screen_prints = [p for p in addon_products if p.sku and 'SCREEN PRINT' in p.sku.upper()]
                        heat_transfers = [p for p in addon_products if p.sku and 'HEAT TRANSFER' in p.sku.upper()]
                        embroidery = [p for p in addon_products if p.sku and 'EMB' in p.sku.upper()]

                        context['bespoke_addons'] = {
                            'screen_prints': screen_prints,
                            'heat_transfers': heat_transfers,
                            'embroidery': embroidery,
                        }
                except Exception as e:
                    logger.error(f"Error fetching bespoke addons: {e}")
                    # Continue without addons if there's an error

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

            elif product_type.lower() == 'bespokeproduct':
                # Bespoke products are custom garments
                return "Bespoke - Custom Garment"

        except Exception as e:
            logger.error(f"Error getting institution name: {e}")

        return "Unknown Institution"


class NewQuotationView(LoginRequiredMixin, SalesRepOrAccountManagerOrCustomerMixin, View):
    """
    New quotation page with tab-based product selection.
    Shows:
    - Schools tab: ALL active TUS schools + assigned wholesale schools
    - Accessories tab: Generic products available to all
    - Custom Garments tab: Bespoke products
    Note: Clubs tab removed - not applicable for quotations
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
        print(f"DEBUG: NewQuotationView - active_tab={active_tab}")

        # Get category type filter (for tile navigation)
        category_type_filter = request.GET.get('category_type', '')

        # Get page number
        page = request.GET.get('page', 1)

        # Initialize product collections and pagination objects
        combined_products = []
        page_obj = None
        is_paginated = False

        # Get user's assigned institutions (only used for wholesale schools, NOT TUS schools)
        assigned_schools = request.user.get_assigned_schools()

        # ========================================
        # SCHOOLS TAB - TUS Schools and Wholesale Schools
        # ========================================
        if active_tab == 'schools':
            from django.db.models import Exists, OuterRef, Q as QOuter

            # Get TUS School Products - Show ALL active TUS schools (no customer assignment filtering)
            # Quotations should allow creating quotes for ANY TUS school regardless of assignment
            tus_products_qs = TUSProduct.objects.none()

            # Get ALL active TUS schools (no assignment filtering for quotations)
            active_tus_schools = TUSSchool.objects.filter(is_active=True)
            tus_school_ids = list(active_tus_schools.values_list('id', flat=True))

            if tus_school_ids:
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
        # CLUBS TAB - Club-Specific Products (SAS Clubs + LOTTO Clubs)
        # All authenticated users can access clubs tab for creating quotations
        # ========================================
        elif active_tab == 'clubs':
            from django.db.models import Exists, OuterRef, Q as QOuter
            from clubs.models_sas import SASProductVariation
            from clubs.models_lotto import LottoProductVariation

            # Get assigned clubs based on user role
            if request.user.is_admin or request.user.is_account_manager:
                # Admin and account managers have access to all clubs
                # EXCLUDE generic categories/shops to prevent duplication with accessories tab
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

                # Exclude generic categories/shops for consistency
                sas_clubs = SASClub.objects.filter(id__in=sas_club_ids, is_generic_category=False)
                lotto_clubs = LottoClub.objects.filter(id__in=lotto_club_ids, is_generic_shop=False)
            elif request.user.is_customer:
                # Customers have access to all active clubs for creating quotations
                # EXCLUDE generic categories/shops to prevent duplication with accessories tab
                sas_clubs = SASClub.objects.filter(is_active=True, is_generic_category=False)
                lotto_clubs = LottoClub.objects.filter(is_active=True, is_generic_shop=False)
            else:
                # Fallback: no clubs for other user types
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
                # Filter: (variable type AND (has stock in variations OR stock_status is instock)) OR
                #         (simple type AND stock_status is instock/onbackorder)
                QOuter(
                    QOuter(
                        product_type='variable',
                        has_stock_variation=True
                    ) |
                    QOuter(
                        product_type='variable',
                        stock_status__in=['instock', 'onbackorder']
                    ) |
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
            # BallStore products first (working images), then SAS, then Lotto (CORS blocked images)
            combined_products = ballstore_products_list + sas_products_list + lotto_products_list
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

        # ========================================
        # CUSTOM GARMENTS TAB - Bespoke Base Garment Products
        # ========================================
        elif active_tab == 'custom_garments':
            print(f"DEBUG: Entering custom_garments tab handler, active_tab={active_tab}")
            from django.db.models import Exists, OuterRef, Q as QOuter
            from bespoke.models import BespokeProduct, BespokeProductVariation, BespokeCategory

            # Get Base Garment category (NOT Addon)
            try:
                base_garment_category = BespokeCategory.objects.get(name='Base Garment', is_active=True)
                print(f"DEBUG: Found Base Garment category ID={base_garment_category.id}")
            except BespokeCategory.DoesNotExist:
                base_garment_category = None
                print("DEBUG: Base Garment category NOT FOUND")

            if base_garment_category:
                # Bespoke products are made-to-order custom garments
                # No stock filtering needed - they should always be available regardless of stock status
                # since they are manufactured on demand

                # Get Bespoke Base Garment Products (no stock filtering)
                bespoke_products_qs = BespokeProduct.objects.filter(
                    category_assignments__category=base_garment_category,
                    is_active=True
                ).prefetch_related('variations', 'category_assignments__category')

                # Apply search filter
                if search_query:
                    bespoke_products_qs = bespoke_products_qs.filter(
                        Q(name__icontains=search_query) |
                        Q(sku__icontains=search_query) |
                        Q(barcode__icontains=search_query) |
                        Q(description__icontains=search_query) |
                        Q(short_description__icontains=search_query) |
                        Q(variations__sku__icontains=search_query) |  # Search in variation SKU
                        Q(category_assignments__category__name__icontains=search_query)  # Category name
                    ).distinct()

                # Get all bespoke products for grouping
                bespoke_products_list = list(bespoke_products_qs)

                # Group products by base name (for garments with sizes)
                # This consolidates all size variations under one product card
                grouped_products_dict = {}

                for product in bespoke_products_list:
                    if product.product_type == 'variable' and product.variations.all():
                        # For variable products, show as a single card with all size variations
                        grouped_products_dict[product.id] = {
                            'parent': product,
                            'sizes': [],
                            'is_grouped': False
                        }
                    else:
                        # For simple products, check if they should be grouped by base name
                        base_name = product.base_garment_name

                        # Find existing group with same base name
                        group_key = None
                        for key, group in grouped_products_dict.items():
                            if group['parent'].base_garment_name == base_name:
                                group_key = key
                                break

                        if group_key:
                            # Add to existing group
                            grouped_products_dict[group_key]['sizes'].append(product)
                            grouped_products_dict[group_key]['is_grouped'] = True
                        else:
                            # Create new group with this product as parent
                            grouped_products_dict[product.id] = {
                                'parent': product,
                                'sizes': [product],
                                'is_grouped': False
                            }

                # Convert to list and sort sizes within each group
                # Create a simple class to make groups accessible via dot notation in templates
                class ProductGroup:
                    def __init__(self, parent, sizes, is_grouped):
                        self.parent = parent
                        self.sizes = sizes
                        self.is_grouped = is_grouped

                products_grouped = []
                for group in grouped_products_dict.values():
                    if group['is_grouped']:
                        # Sort sizes: XS, S, M, L, XL, XXL, 2XL, 3XL, etc.
                        size_order = {'XS': 0, 'S': 1, 'M': 2, 'L': 3, 'XL': 4, 'XXL': 5, '2XL': 5, '3XL': 6, '4XL': 7}
                        group['sizes'].sort(key=lambda p: size_order.get(p.size_suffix or '', 99))
                    # Convert dict to object with dot notation
                    products_grouped.append(ProductGroup(
                        parent=group['parent'],
                        sizes=group['sizes'],
                        is_grouped=group['is_grouped']
                    ))

                # DEBUG: Log grouping results
                print(f"DEBUG: Grouped {len(products_grouped)} bespoke products from {len(bespoke_products_list)} total")
                if products_grouped:
                    sample = products_grouped[0]
                    print(f"DEBUG: Sample group - has parent: {hasattr(sample, 'parent')}, parent: {sample.parent.name if sample.parent else 'None'}")
                    print(f"DEBUG: Sample - parent SKU: {sample.parent.sku}, base_garment_name: {sample.parent.base_garment_name}, is_grouped: {sample.is_grouped}, sizes count: {len(sample.sizes)}")

                # Paginate the grouped products
                combined_products = products_grouped
                paginator = Paginator(combined_products, self.paginate_by)
                try:
                    page_obj = paginator.get_page(page)
                except PageNotAnInteger:
                    page_obj = paginator.get_page(1)
                except EmptyPage:
                    page_obj = paginator.get_page(paginator.num_pages)

                is_paginated = paginator.num_pages > 1

                # ONLY process variations for products on CURRENT PAGE (24 groups instead of ALL)
                for group in page_obj.object_list:
                    product = group.parent
                    product.product_type = 'bespokeproduct'
                    # Fetch variations only for displayed products
                    if product.product_type == 'variable':
                        variations = list(product.variations.filter(is_active=True))
                        product.variation_display = self._get_variation_display_data(variations, 'bespoke')
                    else:
                        product.variation_display = {}
            else:
                # No Base Garment category found
                combined_products = []
                page_obj = None
                is_paginated = False

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

        # Add addon products for custom_garments tab
        bespoke_addons = {}
        if active_tab == 'custom_garments':
            from bespoke.models import BespokeProduct, BespokeCategory

            try:
                addon_category = BespokeCategory.objects.get(name='Addon', is_active=True)
                addon_products = BespokeProduct.objects.filter(
                    category_assignments__category=addon_category,
                    is_active=True
                ).prefetch_related('variations').distinct().order_by('name')

                # Group addons by type based on SKU
                screen_prints = []
                heat_transfers = []
                embroidery = []

                for product in addon_products:
                    sku_upper = (product.sku or '').upper()
                    if 'SCREEN PRINT' in sku_upper or 'SP' in sku_upper:
                        screen_prints.append(product)
                    elif 'HEAT TRANSFER' in sku_upper or 'HT' in sku_upper:
                        heat_transfers.append(product)
                    elif 'EMB' in sku_upper or 'EMBROIDERY' in sku_upper:
                        embroidery.append(product)

                bespoke_addons = {
                    'screen_prints': screen_prints,
                    'heat_transfers': heat_transfers,
                    'embroidery': embroidery,
                }
            except BespokeCategory.DoesNotExist:
                pass

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

            # Bespoke addons (for custom_garments tab only)
            'bespoke_addons': bespoke_addons,
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
            # Handle Bespoke variations (which use option1_value, option2_value, option3_value)
            elif product_type.lower() == 'bespoke':
                option1 = getattr(variation, 'option1_value', '')
                option2 = getattr(variation, 'option2_value', '')
                option3 = getattr(variation, 'option3_value', '')

                # Typically option1 is size, but we'll add all non-empty options
                if option1:
                    # Check if it looks like a size
                    if any(size_keyword in option1.lower() for size_keyword in ['xs', 's', 'm', 'l', 'xl', 'small', 'medium', 'large']):
                        sizes.add(option1)
                    else:
                        colors.add(option1)
                if option2:
                    # Check if it looks like a size
                    if any(size_keyword in option2.lower() for size_keyword in ['xs', 's', 'm', 'l', 'xl', 'small', 'medium', 'large']):
                        sizes.add(option2)
                    else:
                        colors.add(option2)
                if option3:
                    colors.add(option3)
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
            elif product_type.lower() == 'bespoke':
                # BespokeProductVariation has 'sku' field
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
                # For Bespoke, create variation label from option values
                elif product_type.lower() == 'bespoke':
                    option1 = getattr(variation, 'option1_value', '')
                    option2 = getattr(variation, 'option2_value', '')
                    option3 = getattr(variation, 'option3_value', '')
                    option_values = [opt for opt in [option1, option2, option3] if opt]
                    variation_label = ' - '.join(option_values) if option_values else var_value
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

            # Send notification to ALL account managers when customer approves quotation
            if request.user.is_customer:
                try:
                    from .emails import send_customer_quotation_notification_to_account_managers
                    send_customer_quotation_notification_to_account_managers(
                        quotation=quotation,
                        action='approved',
                        request=request
                    )
                except Exception as e:
                    logger.error(f"Failed to send account manager notifications for approved quotation {quotation.quotation_number}: {e}")
                    # Don't fail the approval if notifications fail

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


# =====================================
# IMAGE PROXY VIEW
# =====================================

def proxy_image(request):
    """
    Proxy images from password-protected WordPress sites.

    This view fetches images from password-protected sites (Lotto and BallStore)
    using HTTP Basic Auth credentials and returns them to the browser.

    Args:
        request: HTTP request with 'url' query parameter

    Returns:
        HttpResponse with image data or error status
    """
    image_url = request.GET.get('url')

    if not image_url:
        logger.warning("Image proxy called without URL parameter")
        return HttpResponse(status=404)

    # Only proxy images from allowed domains for security
    allowed_domains = ['dev-lottosports.it.sas.co.nz', 'theballstore.co.nz']
    if not any(domain in image_url for domain in allowed_domains):
        logger.warning(f"Image proxy rejected unauthorized domain: {image_url}")
        return HttpResponse(status=403)

    try:
        # Determine credentials based on domain
        # Lotto site uses different credentials than SAS/BallStore
        if 'dev-lottosports.it.sas.co.nz' in image_url:
            # Lotto credentials
            username = os.getenv('LOTTO_USERNAME', 'sas-admin')
            password = os.getenv('LOTTO_PASSWORD', 'mR7HtzMEUpAO64l4r3pd')
        else:
            # SAS/BallStore credentials
            username = os.getenv('USERNAME', 'sas-admin')
            password = os.getenv('PASSWORD', 'gXbPuQUDOUMAymdN0nIe')

        # Fetch the image with authentication
        response = requests.get(
            image_url,
            auth=(username, password),
            timeout=10,
            stream=True  # Stream to handle large images efficiently
        )

        if response.status_code == 200:
            # Return the image with proper content type
            content_type = response.headers.get('Content-Type', 'image/jpeg')
            return HttpResponse(
                response.content,
                content_type=content_type
            )
        else:
            logger.warning(f"Image proxy failed to fetch image: {image_url} (status: {response.status_code})")
            return HttpResponse(status=404)

    except requests.exceptions.Timeout:
        logger.error(f"Image proxy timeout for URL: {image_url}")
        return HttpResponse(status=504)  # Gateway Timeout

    except requests.exceptions.RequestException as e:
        logger.error(f"Image proxy request failed for URL: {image_url} - {e}")
        return HttpResponse(status=500)

    except Exception as e:
        logger.error(f"Image proxy unexpected error for URL: {image_url} - {e}", exc_info=True)
        return HttpResponse(status=500)


# =====================================
# APPROVAL WORKFLOW VIEWS
# =====================================

def account_manager_required(view_func):
    """Decorator to restrict access to account managers and admins"""
    @wraps(view_func)
    def wrapped(self_or_request, *args, **kwargs):
        # Handle both function-based views (request) and class-based views (self, request)
        if hasattr(self_or_request, 'user'):
            # This is a request object (function-based view)
            request = self_or_request
        else:
            # This is self (class-based view), request is in args
            request = args[0] if args else kwargs.get('request')

        if not (request.user.is_authenticated and (request.user.is_account_manager or request.user.is_admin)):
            raise PermissionDenied("Only Account Managers and Admins can access this page")
        return view_func(self_or_request, *args, **kwargs)
    return wrapped


class PendingApprovalsListView(LoginRequiredMixin, ListView):
    """
    Display all quotations with status='pending' for Account Managers/Admins.
    Provides filtering by sales rep, date range, institution.
    """
    model = Quotation
    template_name = 'quotations/pending_approvals.html'
    context_object_name = 'quotations'
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        # Check permissions
        if not (request.user.is_account_manager or request.user.is_admin):
            raise PermissionDenied("Only Account Managers and Admins can access pending approvals")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        """Get pending quotations with filtering"""
        from django.db.models import F, ExpressionWrapper, fields

        queryset = Quotation.objects.filter(
            status='pending'
        ).select_related(
            'created_by',
            'submitted_by',
            'institution_content_type'
        ).prefetch_related('items').annotate(
            days_pending=ExpressionWrapper(
                timezone.now() - F('submitted_for_approval_at'),
                output_field=fields.DurationField()
            )
        )

        # Filter by sales rep
        sales_rep_id = self.request.GET.get('sales_rep')
        if sales_rep_id:
            queryset = queryset.filter(created_by_id=sales_rep_id)

        # Filter by date range
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if date_from:
            queryset = queryset.filter(submitted_for_approval_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(submitted_for_approval_at__lte=date_to)

        # Filter by institution
        institution_type = self.request.GET.get('institution_type')
        institution_id = self.request.GET.get('institution_id')
        if institution_type and institution_id:
            ct = ContentType.objects.get(model=institution_type.lower())
            queryset = queryset.filter(
                institution_content_type=ct,
                institution_object_id=institution_id
            )

        # Search by quotation number
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(quotation_number__icontains=search_query)

        return queryset.order_by('-submitted_for_approval_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all sales reps for filter dropdown
        context['sales_reps'] = User.objects.filter(
            user_type='sales_rep',
            is_active=True
        ).order_by('first_name', 'last_name')

        # Pass filter parameters
        context['selected_sales_rep'] = self.request.GET.get('sales_rep', '')
        context['search_query'] = self.request.GET.get('search', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')

        # Calculate days pending for each quotation
        for quotation in context['quotations']:
            if quotation.submitted_for_approval_at:
                delta = timezone.now() - quotation.submitted_for_approval_at
                quotation.days_pending_count = delta.days

        return context


class QuotationCustomerApproveView(LoginRequiredMixin, View):
    """
    Customer approval endpoint - First level of two-level approval system.
    Can be called from listing grid via AJAX.
    POST only view with CSRF protection.

    Permissions:
    - Customers: Can approve quotations assigned to them
    - Sales Reps: Can approve quotations on behalf of customers
    """

    def post(self, request, pk):
        try:
            quotation = get_object_or_404(Quotation, pk=pk)

            # Validate user permissions
            if not (request.user.is_customer or request.user.is_sales_rep or request.user.is_account_manager or request.user.is_admin):
                return JsonResponse({
                    'success': False,
                    'message': 'You do not have permission to approve quotations'
                }, status=403)

            # Validate quotation can be approved by customer
            if not quotation.can_be_approved_by_customer(request.user):
                if quotation.customer_approved_at:
                    return JsonResponse({
                        'success': False,
                        'message': 'This quotation has already been approved by customer'
                    }, status=400)
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'This quotation cannot be approved at this time'
                    }, status=400)

            # Perform customer approval
            try:
                quotation.customer_approve(request.user)

                # Log approval action
                AuditLog.log_action(
                    user=request.user,
                    action_type='quotation_customer_approved',
                    description=f'Customer approved quotation {quotation.quotation_number}',
                    request=request,
                    affected_model='Quotation',
                    affected_object_id=str(quotation.id),
                    quotation_id=str(quotation.id),
                    quotation_number=quotation.quotation_number,
                    status=quotation.status
                )

                # Send notification to account manager
                try:
                    if quotation.account_manager:
                        # TODO: Send email notification to account manager
                        logger.info(f"Customer approval notification should be sent to account manager for quotation {quotation.quotation_number}")
                except Exception as e:
                    logger.error(f"Failed to send notification to account manager for quotation {quotation.quotation_number}: {e}")

                success_message = f'Quotation {quotation.quotation_number} approved successfully. Awaiting account manager approval.'
                messages.success(request, success_message)

                return JsonResponse({
                    'success': True,
                    'message': success_message,
                    'quotation_status': quotation.status,
                    'customer_approved': True,
                    'customer_approved_at': quotation.customer_approved_at.isoformat() if quotation.customer_approved_at else None,
                    'customer_approved_by': quotation.customer_approved_by.get_full_name() if quotation.customer_approved_by else None
                })

            except ValidationError as ve:
                return JsonResponse({
                    'success': False,
                    'message': str(ve)
                }, status=400)

        except Quotation.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Quotation not found'
            }, status=404)
        except Exception as e:
            logger.error(f"Error approving quotation by customer: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Error approving quotation: {str(e)}'
            }, status=500)


class QuotationApproveView(LoginRequiredMixin, View):
    """
    Approve a quotation and trigger CIN7/eWand sync.
    POST only view with CSRF protection.

    CRITICAL: CIN7 and/or eWand sync must succeed before quotation is approved.
    - Non-bespoke items (Wholesale, Lotto, SAS, TUS, BallStore) → Sync to CIN7
    - Bespoke items → Sync to eWand
    - Mixed quotations → Sync to both systems

    If any sync fails, approval is rolled back and quotation remains in pending status.
    """

    @account_manager_required
    def post(self, request, pk):
        try:
            quotation = get_object_or_404(Quotation, pk=pk)

            # Validate quotation can be approved
            if quotation.status != 'pending':
                return JsonResponse({
                    'success': False,
                    'message': 'Only pending quotations can be approved'
                }, status=400)

            # NEW: Two-level approval system with account manager override capability
            # Check if customer approval exists
            if not quotation.customer_approved_at:
                # Account manager can override customer approval requirement
                quotation.approval_override_by = request.user
                quotation.approval_override_at = timezone.now()
                quotation.save(update_fields=['approval_override_by', 'approval_override_at', 'updated_at'])

                logger.warning(f"Account manager {request.user.get_full_name()} overriding customer approval requirement for {quotation.quotation_number}")

            # Use database transaction to ensure atomicity
            # If CIN7 or eWand sync fails, entire approval will be rolled back
            try:
                with transaction.atomic():
                    # Check if CIN7 sync is required
                    # Pass during_approval=True since we're in the approval flow
                    # This allows validation to pass even though account_manager_approved_at is not set yet
                    requires_cin7_sync = quotation.can_be_synced_to_cin7(during_approval=True)

                    # TEMPORARILY DISABLED: eWand integration (fixing style_id foreign key issue)
                    # Check if eWand sync is required (for bespoke products)
                    # requires_ewand_sync = quotation.has_bespoke_items()
                    requires_ewand_sync = False  # Disabled temporarily

                    # If CIN7 sync required, perform it BEFORE approval
                    if requires_cin7_sync:
                        from quotations.services.cin7_sales_order_service import Cin7SalesOrderService

                        # Update status to syncing
                        quotation.cin7_sync_status = 'syncing'
                        quotation.save(update_fields=['cin7_sync_status', 'updated_at'])

                        # Perform CIN7 sync
                        logger.info(f"Attempting CIN7 sync for quotation {quotation.quotation_number} before approval")
                        service = Cin7SalesOrderService()
                        sync_result = service.create_sales_order(quotation)

                        # Check sync result
                        cin7_sync_success = sync_result.get('success', False)
                        cin7_sync_message = sync_result.get('message', 'CIN7 sync completed')

                        if not cin7_sync_success:
                            # Sync failed - raise exception to trigger rollback
                            raise Exception(f"CIN7 sync failed: {cin7_sync_message}")

                        # Log successful CIN7 sync
                        AuditLog.log_action(
                            user=request.user,
                            action_type='cin7_so_created',
                            description=f'CIN7 sync for quotation {quotation.quotation_number}: {cin7_sync_message}',
                            request=request,
                            affected_model='Quotation',
                            affected_object_id=str(quotation.id),
                            quotation_id=str(quotation.id),
                            cin7_order_id=sync_result.get('cin7_order_id'),
                            cin7_reference=sync_result.get('cin7_reference')
                        )

                    # TEMPORARILY DISABLED: eWand integration (fixing style_id foreign key issue)
                    # If eWand sync required, perform it BEFORE approval
                    # if requires_ewand_sync:
                    #     from quotations.services.ewand_quotation_service import EwandQuotationService
                    #
                    #     # Perform eWand sync
                    #     logger.info(f"Attempting eWand sync for quotation {quotation.quotation_number} before approval")
                    #     ewand_service = EwandQuotationService()
                    #     ewand_result = ewand_service.create_quotation(quotation)
                    #
                    #     # Check sync result
                    #     ewand_sync_success = ewand_result.get('success', False)
                    #     ewand_sync_message = ewand_result.get('message', 'eWand sync completed')
                    #
                    #     if not ewand_sync_success:
                    #         # Sync failed - raise exception to trigger rollback
                    #         raise Exception(f"eWand sync failed: {ewand_sync_message}")
                    #
                    #     # Log successful eWand sync
                    #     AuditLog.log_action(
                    #         user=request.user,
                    #         action_type='ewand_quotation_created',
                    #         description=f'eWand sync for quotation {quotation.quotation_number}: {ewand_sync_message}',
                    #         request=request,
                    #         affected_model='Quotation',
                    #         affected_object_id=str(quotation.id),
                    #         quotation_id=str(quotation.id),
                    #         ewand_data=ewand_result.get('ewand_data')
                    #     )

                    # CIN7 sync succeeded (or not required) - proceed with approval
                    quotation.status = 'approved'
                    quotation.approved_by = request.user
                    quotation.approved_at = timezone.now()
                    quotation.account_manager_approved_at = timezone.now()
                    quotation.save(update_fields=['status', 'approved_by', 'approved_at', 'account_manager_approved_at', 'updated_at'])

                    # Create version snapshot
                    quotation.create_version_snapshot(
                        description=f'Approved by {request.user.get_full_name()}',
                        user=request.user,
                        change_note=f'Quotation approved by Account Manager'
                    )

                    # Log approval action
                    AuditLog.log_action(
                        user=request.user,
                        action_type='quotation_approved',
                        description=f'Approved quotation {quotation.quotation_number}',
                        request=request,
                        affected_model='Quotation',
                        affected_object_id=str(quotation.id),
                        quotation_id=str(quotation.id),
                        quotation_number=quotation.quotation_number,
                        status=quotation.status
                    )

                    # Transaction will commit here if no exceptions raised

            except Exception as sync_error:
                # CIN7 or eWand sync or approval failed - transaction has been rolled back
                error_type = 'CIN7' if 'CIN7' in str(sync_error) else 'eWand' if 'eWand' in str(sync_error) else 'Sync'
                logger.error(f"{error_type} sync failed for quotation {quotation.quotation_number}: {sync_error}")

                # Reload quotation to get fresh state after rollback
                quotation.refresh_from_db()

                # Update quotation with sync error (for CIN7 errors, keep existing field)
                if 'CIN7' in str(sync_error):
                    quotation.cin7_sync_status = 'failed'
                    quotation.cin7_sync_error = str(sync_error)
                    quotation.save(update_fields=['cin7_sync_status', 'cin7_sync_error', 'updated_at'])

                # Log sync failure
                action_type = 'cin7_sync_failed' if 'CIN7' in str(sync_error) else 'ewand_sync_failed'
                AuditLog.log_action(
                    user=request.user,
                    action_type=action_type,
                    description=f'{error_type} sync failed for quotation {quotation.quotation_number}: {str(sync_error)}',
                    request=request,
                    affected_model='Quotation',
                    affected_object_id=str(quotation.id),
                    quotation_id=str(quotation.id),
                    error_message=str(sync_error)
                )

                # Return error response - quotation remains in pending status
                error_message = f'Quotation approval failed: {error_type} sync error - {str(sync_error)}'
                messages.error(request, error_message)

                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'cin7_sync': False,
                    'ewand_sync': False,
                    'quotation_status': quotation.status  # Should still be 'pending'
                }, status=400)

            # Send email notification to sales rep (outside transaction)
            try:
                from quotations.emails import send_quotation_approval_email
                send_quotation_approval_email(quotation)
            except Exception as e:
                logger.error(f"Failed to send approval email for quotation {quotation.quotation_number}: {e}")

            # Success message
            success_message = f'Quotation {quotation.quotation_number} approved successfully'
            sync_details = []
            if requires_cin7_sync:
                sync_details.append('synced to CIN7')
            # TEMPORARILY DISABLED: eWand integration
            # if requires_ewand_sync:
            #     sync_details.append('synced to eWand')

            if sync_details:
                success_message += f' and {" and ".join(sync_details)}'

            messages.success(request, success_message)

            return JsonResponse({
                'success': True,
                'message': success_message,
                'cin7_sync': requires_cin7_sync,
                'ewand_sync': requires_ewand_sync,
                'redirect_url': reverse('quotations:quotation-detail', kwargs={'pk': quotation.id})
            })

        except Quotation.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Quotation not found'
            }, status=404)
        except Exception as e:
            logger.error(f"Error approving quotation: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Error approving quotation: {str(e)}'
            }, status=500)


class QuotationRejectView(LoginRequiredMixin, View):
    """
    Reject a quotation with mandatory reason.
    POST only view with CSRF protection.
    """

    @account_manager_required
    def post(self, request, pk):
        try:
            quotation = get_object_or_404(Quotation, pk=pk)

            # Validate quotation can be rejected
            if quotation.status != 'pending':
                return JsonResponse({
                    'success': False,
                    'message': 'Only pending quotations can be rejected'
                }, status=400)

            # Get rejection reason
            rejection_reason = request.POST.get('reason', '').strip()
            if not rejection_reason:
                return JsonResponse({
                    'success': False,
                    'message': 'Rejection reason is required'
                }, status=400)

            # Update quotation status
            quotation.status = 'rejected'
            quotation.rejected_by = request.user
            quotation.rejected_at = timezone.now()
            quotation.rejection_reason = rejection_reason
            quotation.save(update_fields=['status', 'rejected_by', 'rejected_at', 'rejection_reason', 'updated_at'])

            # Create version snapshot
            quotation.create_version_snapshot(
                description=f'Rejected by {request.user.get_full_name()}',
                user=request.user,
                change_note=f'Quotation rejected: {rejection_reason}'
            )

            # Log rejection action
            AuditLog.log_action(
                user=request.user,
                action_type='quotation_rejected',
                description=f'Rejected quotation {quotation.quotation_number}: {rejection_reason}',
                request=request,
                affected_model='Quotation',
                affected_object_id=str(quotation.id),
                quotation_id=str(quotation.id),
                quotation_number=quotation.quotation_number,
                status=quotation.status,
                rejection_reason=rejection_reason
            )

            # Send email notification to sales rep
            try:
                from quotations.emails import send_quotation_rejection_email
                send_quotation_rejection_email(quotation)
            except Exception as e:
                logger.error(f"Failed to send rejection email for quotation {quotation.quotation_number}: {e}")

            messages.success(request, f'Quotation {quotation.quotation_number} rejected')

            return JsonResponse({
                'success': True,
                'message': f'Quotation {quotation.quotation_number} rejected',
                'redirect_url': reverse('quotations:pending-approvals')
            })

        except Quotation.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Quotation not found'
            }, status=404)
        except Exception as e:
            logger.error(f"Error rejecting quotation: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Error rejecting quotation: {str(e)}'
            }, status=500)


# DEPRECATED: QuotationRequestChangesView - Account Managers can now edit quotations directly
# Keeping this for reference only - functionality replaced by direct editing capability
"""
class QuotationRequestChangesView(LoginRequiredMixin, View):
    '''
    Send quotation back to sales rep for changes.
    POST only view with CSRF protection.

    DEPRECATED: This view is no longer used. Account Managers now edit quotations directly
    instead of requesting changes. See EditQuotationView for the new workflow.
    '''

    @account_manager_required
    def post(self, request, pk):
        try:
            quotation = get_object_or_404(Quotation, pk=pk)

            # Validate quotation can have changes requested
            if quotation.status != 'pending':
                return JsonResponse({
                    'success': False,
                    'message': 'Only pending quotations can have changes requested'
                }, status=400)

            # Get change request notes
            change_notes = request.POST.get('notes', '').strip()
            if not change_notes:
                return JsonResponse({
                    'success': False,
                    'message': 'Change request notes are required'
                }, status=400)

            # Update quotation status to draft
            quotation.status = 'draft'
            quotation.submitted_for_approval_at = None
            quotation.submitted_by = None

            # Add change request note to quotation notes
            if quotation.notes:
                quotation.notes += f"\n\n[{timezone.now().strftime('%Y-%m-%d %H:%M')}] Changes requested by {request.user.get_full_name()}:\n{change_notes}"
            else:
                quotation.notes = f"[{timezone.now().strftime('%Y-%m-%d %H:%M')}] Changes requested by {request.user.get_full_name()}:\n{change_notes}"

            quotation.save(update_fields=['status', 'submitted_for_approval_at', 'submitted_by', 'notes', 'updated_at'])

            # Create version snapshot
            quotation.create_version_snapshot(
                description=f'Changes requested by {request.user.get_full_name()}',
                user=request.user,
                change_note=f'Changes requested: {change_notes}'
            )

            # Log action
            AuditLog.log_action(
                user=request.user,
                action_type='quotation_updated',
                description=f'Requested changes for quotation {quotation.quotation_number}: {change_notes}',
                request=request,
                affected_model='Quotation',
                affected_object_id=str(quotation.id),
                quotation_id=str(quotation.id),
                quotation_number=quotation.quotation_number,
                status=quotation.status,
                change_notes=change_notes
            )

            # Send email notification to sales rep
            try:
                from quotations.emails import send_quotation_changes_requested_email
                send_quotation_changes_requested_email(quotation, change_notes)
            except Exception as e:
                logger.error(f"Failed to send changes requested email for quotation {quotation.quotation_number}: {e}")

            messages.success(request, f'Changes requested for quotation {quotation.quotation_number}')

            return JsonResponse({
                'success': True,
                'message': f'Changes requested for quotation {quotation.quotation_number}',
                'redirect_url': reverse('quotations:pending-approvals')
            })

        except Quotation.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Quotation not found'
            }, status=404)
        except Exception as e:
            logger.error(f"Error requesting changes for quotation: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Error requesting changes: {str(e)}'
            }, status=500)
"""


# =====================================
# REPORTS - QUOTATIONS REPORT
# =====================================

class QuotationsReportView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Comprehensive quotations report for account managers and admins.

    Features:
    - Statistics dashboard (total, approved %, rejected %, pending %)
    - Detailed quotations table with all relevant information
    - Filters: date range, status, created by, approved by, institution
    - Search by quotation number

    Accessible to Admin and Account Managers only.
    """
    template_name = 'quotations/reports/quotations_report.html'

    def test_func(self):
        """Check if user has permission to view quotations report"""
        user = self.request.user
        return user.is_admin or user.is_account_manager

    def get(self, request):
        """Generate and display quotations report"""
        from datetime import datetime, timedelta
        from django.db.models import Count, Q

        # Get filter parameters
        date_from = request.GET.get('date_from', '')
        date_to = request.GET.get('date_to', '')
        status_filter = request.GET.get('status', '')
        created_by_filter = request.GET.get('created_by', '')
        approved_by_filter = request.GET.get('approved_by', '')
        institution_filter = request.GET.get('institution', '')
        search_query = request.GET.get('search', '').strip()

        # Base queryset - all quotations
        quotations = Quotation.objects.all().select_related(
            'created_by',
            'approved_by',
            'customer_approved_by',
            'institution_content_type'
        ).prefetch_related('items')

        # Apply date range filter
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                quotations = quotations.filter(created_at__gte=date_from_obj)
            except ValueError:
                pass

        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                # Add 1 day to include the end date
                date_to_obj = date_to_obj + timedelta(days=1)
                quotations = quotations.filter(created_at__lt=date_to_obj)
            except ValueError:
                pass

        # Apply status filter
        if status_filter and status_filter != 'all':
            quotations = quotations.filter(status=status_filter)

        # Apply created by filter
        if created_by_filter:
            quotations = quotations.filter(created_by_id=created_by_filter)

        # Apply approved by filter (account manager approval)
        if approved_by_filter:
            quotations = quotations.filter(approved_by_id=approved_by_filter)

        # Apply institution filter
        if institution_filter:
            quotations = quotations.filter(
                Q(institution_content_type__model__icontains=institution_filter) |
                Q(institution_object_id=institution_filter)
            )

        # Apply search query (quotation number)
        if search_query:
            quotations = quotations.filter(
                Q(quotation_number__icontains=search_query) |
                Q(recipient_name__icontains=search_query)
            )

        # Calculate statistics
        total_quotations = quotations.count()

        # Approved quotations (have account manager approval)
        approved_quotations = quotations.filter(
            account_manager_approved_at__isnull=False
        ).count()
        approved_percentage = (approved_quotations / total_quotations * 100) if total_quotations > 0 else 0

        # Rejected quotations
        rejected_quotations = quotations.filter(status='rejected').count()
        rejected_percentage = (rejected_quotations / total_quotations * 100) if total_quotations > 0 else 0

        # Open/Pending quotations (not approved by account manager and not rejected)
        open_quotations = quotations.filter(
            account_manager_approved_at__isnull=True,
            status__in=['draft', 'pending']
        ).count()
        open_percentage = (open_quotations / total_quotations * 100) if total_quotations > 0 else 0

        # Get all users for filters (sales reps, account managers, customers, admins)
        all_users = User.objects.filter(
            Q(user_type__in=['sales_rep', 'account_manager', 'customer', 'admin']) |
            Q(is_superuser=True)
        ).order_by('first_name', 'last_name')

        # Get unique account managers who have approved quotations
        approvers = User.objects.filter(
            quotations_approved__isnull=False
        ).distinct().order_by('first_name', 'last_name')

        # Paginate quotations
        paginator = Paginator(quotations, 50)  # 50 quotations per page
        page = request.GET.get('page', 1)

        try:
            quotations_page = paginator.page(page)
        except PageNotAnInteger:
            quotations_page = paginator.page(1)
        except EmptyPage:
            quotations_page = paginator.page(paginator.num_pages)

        # Log access
        AuditLog.log_action(
            user=request.user,
            action_type='report_access',
            description='Viewed Quotations Report',
            request=request,
            total_quotations=total_quotations,
            date_from=date_from or None,
            date_to=date_to or None,
            status_filter=status_filter or None
        )

        context = {
            'quotations': quotations_page,
            'total_quotations': total_quotations,
            'approved_count': approved_quotations,
            'approved_percentage': round(approved_percentage, 1),
            'rejected_count': rejected_quotations,
            'rejected_percentage': round(rejected_percentage, 1),
            'open_count': open_quotations,
            'open_percentage': round(open_percentage, 1),
            'all_users': all_users,
            'approvers': approvers,
            'date_from': date_from,
            'date_to': date_to,
            'status_filter': status_filter,
            'created_by_filter': created_by_filter,
            'approved_by_filter': approved_by_filter,
            'institution_filter': institution_filter,
            'search_query': search_query,
            'page_title': 'Quotations Report',
        }

        return render(request, self.template_name, context)


class PendingApprovalsCountView(LoginRequiredMixin, View):
    """
    API endpoint to get count of pending quotations awaiting account manager approval.
    Used for badge updates in navigation.
    """

    def get(self, request):
        """Return count of pending quotations"""
        # Only account managers and admins can see pending approvals
        if not (request.user.is_account_manager or request.user.is_admin):
            return JsonResponse({'count': 0})

        # Count quotations with pending status
        count = Quotation.objects.filter(status='pending').count()

        return JsonResponse({'count': count})


# =====================================
# SHIPPING SETTINGS VIEW
# =====================================

class ShippingSettingsView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Shipping Settings management view.
    Allows admin users to configure box capacity and shipping rates.
    """
    template_name = 'quotations/settings/shipping_settings.html'

    def test_func(self):
        """Only admin users can access shipping settings"""
        return self.request.user.is_authenticated and self.request.user.is_admin

    def get_object(self):
        """Get or create the singleton ShippingSettings instance"""
        return ShippingSettings.get_settings()

    def get(self, request):
        """Display shipping settings form"""
        settings = self.get_object()

        context = {
            'page_title': 'Shipping & Box Calculation Settings',
            'settings': settings,
            'product_capacities': settings.get_product_capacities_display(),
            'shipping_rates': settings.get_shipping_rates_display(),
        }

        return render(request, self.template_name, context)

    def post(self, request):
        """Save updated shipping settings"""
        try:
            settings = self.get_object()

            # Update box weight limit
            box_weight = request.POST.get('box_weight_limit_kg')
            if box_weight:
                settings.box_weight_limit_kg = Decimal(box_weight)

            # Update RD delivery surcharge
            rd_surcharge = request.POST.get('rd_delivery_surcharge')
            if rd_surcharge:
                settings.rd_delivery_surcharge = Decimal(rd_surcharge)

            # Update product capacities
            product_capacities = {}
            for key in settings.product_capacities.keys():
                capacity_value = request.POST.get(f'capacity_{key}')
                if capacity_value:
                    product_capacities[key] = int(capacity_value)

            if product_capacities:
                settings.product_capacities = product_capacities

            # Update shipping rates
            shipping_rates = {}
            for key in settings.shipping_rates.keys():
                cost = request.POST.get(f'rate_cost_{key}')
                description = request.POST.get(f'rate_desc_{key}')
                regions_str = request.POST.get(f'rate_regions_{key}')

                # Parse regions from comma-separated string
                regions = []
                if regions_str:
                    regions = [r.strip() for r in regions_str.split(',') if r.strip()]

                if cost:
                    shipping_rates[key] = {
                        'cost': cost,
                        'description': description or '',
                        'regions': regions
                    }

            if shipping_rates:
                settings.shipping_rates = shipping_rates

            # Update audit fields
            settings.updated_by = request.user
            settings.save()

            # Log action
            AuditLog.log_action(
                user=request.user,
                action_type='data_update',
                description=f'Updated shipping settings: Box weight={settings.box_weight_limit_kg}kg, RD surcharge=${settings.rd_delivery_surcharge}',
                request=request,
                box_weight_limit=str(settings.box_weight_limit_kg),
                rd_delivery_surcharge=str(settings.rd_delivery_surcharge)
            )

            messages.success(request, 'Shipping settings updated successfully!')

        except (ValueError, KeyError, ValidationError) as e:
            logger.error(f'Error updating shipping settings: {e}')
            messages.error(request, f'Error updating settings: {str(e)}')

        return redirect('quotations:shipping-settings')


class GetInstituteDetailsView(LoginRequiredMixin, View):
    """
    AJAX endpoint to fetch institute contact and address details for auto-populating quotation recipient information.
    Supports all institute types: TUSSchool, WholesaleSchool, LottoClub, SASClub.
    """

    def get(self, request):
        """
        Fetch institute details including contact info and delivery address.

        Query Parameters:
            institution_id: Format "institutiontype_id" (e.g., "tusschool_123")

        Returns:
            JSON with:
                - recipient_name: Combined first_name + last_name
                - phone: Contact phone number
                - delivery_address: Complete delivery address string
                - delivery_city: City
                - delivery_state: State/Region
                - delivery_postcode: Postcode
        """
        try:
            institution_id_param = request.GET.get('institution_id', '').strip()

            if not institution_id_param:
                return JsonResponse({
                    'success': False,
                    'error': 'Institution ID is required'
                }, status=400)

            # Parse institution_id parameter (format: "institutiontype_id")
            try:
                institution_type, institution_id = institution_id_param.split('_', 1)
                institution_id = int(institution_id)
            except (ValueError, AttributeError):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid institution ID format. Expected: institutiontype_id'
                }, status=400)

            # Get institution object based on type
            from schools.models import WholesaleSchool
            from schools.models_tus import TUSSchool
            from clubs.models_lotto import LottoClub
            from clubs.models_sas import SASClub

            institution = None

            if institution_type == 'tusschool':
                try:
                    institution = TUSSchool.objects.get(pk=institution_id)
                except TUSSchool.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'TUS School not found'
                    }, status=404)

            elif institution_type == 'wholesaleschool':
                try:
                    institution = WholesaleSchool.objects.get(pk=institution_id)
                except WholesaleSchool.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Wholesale School not found'
                    }, status=404)

            elif institution_type == 'lottoclub':
                try:
                    institution = LottoClub.objects.get(pk=institution_id)
                except LottoClub.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'LOTTO Club not found'
                    }, status=404)

            elif institution_type == 'sasclub':
                try:
                    institution = SASClub.objects.get(pk=institution_id)
                except SASClub.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'SAS Club not found'
                    }, status=404)

            else:
                return JsonResponse({
                    'success': False,
                    'error': f'Unknown institution type: {institution_type}'
                }, status=400)

            # Extract contact and address information
            first_name = getattr(institution, 'cin7_first_name', '') or ''
            last_name = getattr(institution, 'cin7_last_name', '') or ''
            recipient_name = f"{first_name} {last_name}".strip()

            phone = getattr(institution, 'cin7_phone', '') or ''

            # Build delivery address
            address1 = getattr(institution, 'cin7_delivery_address1', '') or ''
            address2 = getattr(institution, 'cin7_delivery_address2', '') or ''
            city = getattr(institution, 'cin7_delivery_city', '') or ''
            state = getattr(institution, 'cin7_delivery_state', '') or ''
            postcode = getattr(institution, 'cin7_delivery_postcode', '') or ''

            return JsonResponse({
                'success': True,
                'data': {
                    'recipient_name': recipient_name,
                    'phone': phone,
                    'delivery_address1': address1,
                    'delivery_address2': address2,
                    'delivery_city': city,
                    'delivery_state': state,
                    'delivery_postcode': postcode,
                }
            })

        except Exception as e:
            logger.error(f'Error fetching institute details: {e}', exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while fetching institute details'
            }, status=500)


class CalculateShippingView(LoginRequiredMixin, View):
    """
    AJAX endpoint to calculate shipping cost based on delivery address and cart items.

    Calculates shipping based on:
    - Region (derived from city using get_region_from_city())
    - Number of boxes (from cart items using product capacities)
    - Rural delivery status (from suburb/postcode)
    """

    def post(self, request):
        """
        Calculate shipping cost for the current cart and address.

        POST Parameters:
            city: Delivery city (required)
            suburb: Delivery suburb/state (optional)
            postcode: Delivery postcode (optional)

        Returns:
            JSON with:
                - shipping_cost: Dollar amount
                - boxes: Number of boxes calculated
                - region: Region name (e.g., "Auckland", "Wellington")
                - is_rural: Boolean for rural delivery surcharge
                - breakdown: Details of calculation
        """
        try:
            print("=" * 80)
            print("SHIPPING CALCULATION REQUEST RECEIVED")
            print("=" * 80)

            # Get address components from POST data
            city = request.POST.get('city', '').strip()
            suburb = request.POST.get('suburb', '').strip()
            postcode = request.POST.get('postcode', '').strip()

            print(f"Address: city={city}, suburb={suburb}, postcode={postcode}")

            # If city is empty but postcode exists, try geocoding
            geocoded_city = None
            if not city and postcode:
                from .utils_geocoding import get_city_from_postcode
                geocode_result = get_city_from_postcode(postcode)
                if geocode_result and geocode_result.get('city'):
                    city = geocode_result['city']
                    geocoded_city = city
                    print(f"DEBUG: Geocoded city from postcode {postcode}: {city}")

            # Validate required parameters
            if not city:
                return JsonResponse({
                    'success': False,
                    'error': 'City is required for shipping calculation. Please provide a city or valid postcode.'
                }, status=400)

            # Get cart items from session - check multiple possible locations
            print(f"Session keys: {list(request.session.keys())}")

            quotation_data = request.session.get('quotation', {})
            items = quotation_data.get('items', [])

            # Also check if cart is stored differently
            cart_items = request.session.get('cart', [])
            print(f"Quotation items: {len(items)}")
            print(f"Cart items: {len(cart_items)}")

            # Use cart if quotation items is empty
            if not items and cart_items:
                items = cart_items
                print("Using cart items instead of quotation items")

            # Debug logging
            logger.info(f"DEBUG: Cart items from session: {len(items)} items")
            for idx, item in enumerate(items):
                logger.info(f"DEBUG: Item {idx}: type={item.get('product_type')}, id={item.get('product_id')}, name={item.get('product_name')}, qty={item.get('quantity')}")

            if not items:
                return JsonResponse({
                    'success': False,
                    'error': 'Cart is empty'
                }, status=400)

            # Get region from address
            from .utils_shipping import get_region_from_address
            region = get_region_from_address(
                street_address=None,
                suburb=suburb,
                city=city,
                postcode=postcode
            )

            if not region:
                return JsonResponse({
                    'success': False,
                    'error': f'Could not determine shipping region for city: {city}'
                }, status=400)

            # Get shipping settings
            shipping_settings = ShippingSettings.get_settings()

            # Calculate total boxes needed using aggregate capacity
            import math
            total_capacity_fraction = 0.0
            box_breakdown = []

            for item in items:
                # Get product based on type
                product = None
                product_type = item.get('product_type', '')
                product_id = item.get('product_id')

                # Normalize product type to lowercase for comparison
                product_type_lower = product_type.lower()

                print(f"DEBUG: Processing item - product_type='{product_type}' (normalized: '{product_type_lower}'), product_id={product_id}")

                # Match using lowercase comparison to handle both 'TUSProduct' and 'tusproduct'
                if product_type_lower == 'wholesaleproduct':
                    from schools.models import WholesaleProduct
                    try:
                        product = WholesaleProduct.objects.get(pk=product_id)
                        print(f"DEBUG: Found WholesaleProduct: {product.name}")
                    except WholesaleProduct.DoesNotExist:
                        print(f"DEBUG: WholesaleProduct {product_id} not found")
                        continue

                elif product_type_lower == 'tusproduct':
                    from schools.models_tus import TUSProduct
                    try:
                        # Cart stores parent product ID, not variation ID
                        product = TUSProduct.objects.get(pk=product_id)
                        print(f"DEBUG: Found TUSProduct {product_id}: {product.name}")
                    except TUSProduct.DoesNotExist:
                        print(f"DEBUG: TUSProduct {product_id} not found in database - skipping")
                        continue
                    except Exception as e:
                        print(f"DEBUG: Error getting TUSProduct {product_id}: {e}")
                        continue

                elif product_type_lower == 'lottoproduct':
                    from clubs.models_lotto import LottoProduct
                    try:
                        product = LottoProduct.objects.get(pk=product_id)
                        print(f"DEBUG: Found LottoProduct: {product.name}")
                    except LottoProduct.DoesNotExist:
                        print(f"DEBUG: LottoProduct {product_id} not found")
                        continue

                elif product_type_lower == 'sasproduct':
                    from clubs.models_sas import SASProduct
                    try:
                        product = SASProduct.objects.get(pk=product_id)
                        print(f"DEBUG: Found SASProduct: {product.name}")
                    except SASProduct.DoesNotExist:
                        print(f"DEBUG: SASProduct {product_id} not found")
                        continue

                elif product_type_lower == 'bespokeproduct':
                    from bespoke.models import BespokeProduct
                    try:
                        product = BespokeProduct.objects.get(pk=product_id)
                        print(f"DEBUG: Found BespokeProduct: {product.name}")
                    except BespokeProduct.DoesNotExist:
                        print(f"DEBUG: BespokeProduct {product_id} not found")
                        continue

                elif product_type_lower == 'ballstoreproduct':
                    from ballstore.models import BallStoreProduct
                    try:
                        product = BallStoreProduct.objects.get(pk=product_id)
                        print(f"DEBUG: Found BallStoreProduct: {product.name}")
                    except BallStoreProduct.DoesNotExist:
                        print(f"DEBUG: BallStoreProduct {product_id} not found")
                        continue

                else:
                    print(f"DEBUG: Unknown product_type: '{product_type}' (normalized: '{product_type_lower}')")

                if not product:
                    logger.warning(f"DEBUG: No product found for item {product_id}")
                    continue

                # Get capacity key for this product
                from .utils_shipping import get_capacity_key_for_product
                capacity_key = get_capacity_key_for_product(product)
                print(f"DEBUG: Capacity key for {product.name}: {capacity_key}")

                # Get capacity (units per box)
                capacity = shipping_settings.get_product_capacity(capacity_key)
                print(f"DEBUG: Capacity for {capacity_key}: {capacity}")

                if not capacity:
                    # Use conservative default if capacity not found
                    capacity = 8  # sideline_jackets capacity
                    print(f"DEBUG: No capacity found for {capacity_key}, using default: {capacity}")

                # Get quantity from item level (not from variations)
                quantity = item.get('quantity', 1)
                print(f"DEBUG: Quantity from item: {quantity}")

                # Variations dict contains details but not quantity
                variations = item.get('variations')
                if variations:
                    print(f"DEBUG: Item has variations: {variations}")

                # Add to aggregate capacity fraction
                capacity_fraction = quantity / capacity
                total_capacity_fraction += capacity_fraction
                print(f"DEBUG: Item capacity fraction: {capacity_fraction:.2f} (qty={quantity}, capacity={capacity})")
                print(f"DEBUG: Running total capacity fraction: {total_capacity_fraction:.2f}")

                box_breakdown.append({
                    'product_name': getattr(product, 'name', 'Unknown'),
                    'quantity': quantity,
                    'capacity_per_box': capacity,
                    'capacity_fraction': capacity_fraction
                })

            # Calculate total boxes from aggregate capacity
            total_boxes = math.ceil(total_capacity_fraction)
            print(f"DEBUG: FINAL - Total capacity fraction: {total_capacity_fraction:.2f}, Total boxes: {total_boxes}")

            # Check for rural delivery
            is_rural = False
            if postcode:
                # Check if postcode contains 'RD' pattern
                import re
                # Match "RD 1", "RD1", "1234 RD", "RD", etc.
                # Use word boundary at start, optional space/number at end
                rd_pattern = r'\bRD\s*\d*'
                is_rural = bool(re.search(rd_pattern, postcode.upper()))
            print(f"DEBUG: Rural delivery: {is_rural}")

            # Get shipping rate for region
            rate_cost = shipping_settings.get_rate_for_region(region)
            print(f"DEBUG: Rate for {region}: ${rate_cost}")

            if not rate_cost:
                return JsonResponse({
                    'success': False,
                    'error': f'No shipping rate configured for region: {region}'
                }, status=400)

            # Calculate total shipping cost
            base_cost = Decimal(rate_cost) * total_boxes
            rd_surcharge = Decimal('0.00')

            if is_rural:
                rd_surcharge = shipping_settings.rd_delivery_surcharge * total_boxes

            total_shipping_cost = base_cost + rd_surcharge
            print(f"DEBUG: Shipping calculation - base: ${base_cost}, RD: ${rd_surcharge}, total: ${total_shipping_cost}")
            print("=" * 80)

            return JsonResponse({
                'success': True,
                'shipping_cost': str(total_shipping_cost),
                'boxes': total_boxes,
                'region': region,
                'is_rural': is_rural,
                'geocoded_city': geocoded_city,  # Include geocoded city if it was auto-filled
                'breakdown': {
                    'base_cost_per_box': str(rate_cost),
                    'base_cost': str(base_cost),
                    'rd_surcharge_per_box': str(shipping_settings.rd_delivery_surcharge) if is_rural else '0.00',
                    'rd_surcharge': str(rd_surcharge),
                    'total_cost': str(total_shipping_cost),
                    'items': box_breakdown
                }
            })

        except Exception as e:
            logger.error(f'Error calculating shipping: {e}', exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while calculating shipping'
            }, status=500)


# =====================================
# QUOTATION PDF DOWNLOAD VIEW
# =====================================

class QuotationPDFView(LoginRequiredMixin, View):
    """
    Generate and download quotation as PDF.

    Accessible by:
    - Quotation creator
    - Admin users
    - Account managers

    Only approved, rejected, or confirmed quotations can be downloaded as PDF.
    """

    def get(self, request, pk):
        """Handle PDF download request"""
        from .emails import generate_quotation_pdf

        # Get quotation
        quotation = get_object_or_404(Quotation, pk=pk)

        # Check permissions
        user = request.user
        can_access = (
            user.is_admin or
            user.is_account_manager or
            quotation.created_by == user
        )

        if not can_access:
            raise PermissionDenied("You don't have permission to download this quotation.")

        # Only allow PDF download for approved/rejected/confirmed quotations
        if quotation.status not in ['approved', 'rejected', 'confirmed']:
            return HttpResponse(
                "PDF download is only available for approved, rejected, or confirmed quotations.",
                status=400
            )

        # Generate PDF
        pdf_bytes = generate_quotation_pdf(quotation)

        if not pdf_bytes:
            logger.error(f"Failed to generate PDF for quotation {quotation.quotation_number}")
            return HttpResponse(
                "Failed to generate PDF. Please contact support.",
                status=500
            )

        # Create response with PDF
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="quotation_{quotation.quotation_number}.pdf"'

        # Log the download
        AuditLog.log_action(
            user=user,
            action_type='quotation_viewed',
            description=f'Downloaded PDF for quotation {quotation.quotation_number}',
            request=request
        )

        logger.info(f"User {user.email} downloaded PDF for quotation {quotation.quotation_number}")

        return response


# =====================================
# QUOTATION EXCEL EXPORT VIEW
# =====================================

class QuotationExcelExportView(LoginRequiredMixin, View):
    """
    Generate and download quotation as Excel file for bespoke products.

    Accessible by:
    - Quotation creator
    - Admin users
    - Account managers

    Only quotations with bespoke items and player customizations can be exported.
    """

    def get(self, request, pk):
        """Handle Excel export request"""
        from .excel_export import generate_bespoke_quotation_excel

        # Get quotation
        quotation = get_object_or_404(Quotation, pk=pk)

        # Check permissions
        user = request.user
        can_access = (
            user.is_admin or
            user.is_account_manager or
            quotation.created_by == user
        )

        if not can_access:
            raise PermissionDenied("You don't have permission to export this quotation.")

        # Generate Excel
        try:
            excel_bytes = generate_bespoke_quotation_excel(quotation)
        except ValueError as e:
            # No bespoke items with player customizations
            logger.warning(f"Cannot generate Excel for quotation {quotation.quotation_number}: {e}")
            return HttpResponse(
                f"Excel export failed: {str(e)}",
                status=400
            )
        except FileNotFoundError as e:
            # Template file not found
            logger.error(f"Excel template not found: {e}")
            return HttpResponse(
                "Excel template file not found. Please contact support.",
                status=500
            )
        except Exception as e:
            logger.error(f"Failed to generate Excel for quotation {quotation.quotation_number}: {e}")
            return HttpResponse(
                "Failed to generate Excel file. Please contact support.",
                status=500
            )

        # Create response with Excel file
        response = HttpResponse(
            excel_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="quotation_{quotation.quotation_number}.xlsx"'

        # Log the download
        AuditLog.log_action(
            user=user,
            action_type='quotation_viewed',
            description=f'Downloaded Excel for quotation {quotation.quotation_number}',
            request=request
        )

        logger.info(f"User {user.email} downloaded Excel for quotation {quotation.quotation_number}")

        return response


class QuotationWordExportView(LoginRequiredMixin, View):
    """
    Generate and download quotation as Word document (ORDER DETAILS format) for bespoke products.

    Accessible by:
    - Quotation creator
    - Admin users
    - Account managers

    Only quotations with bespoke items and player customizations can be exported.
    """

    def get(self, request, pk):
        """Handle Word export request"""
        from .word_export import generate_bespoke_quotation_word

        # Get quotation
        quotation = get_object_or_404(Quotation, pk=pk)

        # Check permissions
        user = request.user
        can_access = (
            user.is_admin or
            user.is_account_manager or
            quotation.created_by == user
        )

        if not can_access:
            raise PermissionDenied("You don't have permission to export this quotation.")

        # Generate Word document
        try:
            word_bytes = generate_bespoke_quotation_word(quotation)
        except ValueError as e:
            # No bespoke items with player customizations
            logger.warning(f"Cannot generate Word for quotation {quotation.quotation_number}: {e}")
            return HttpResponse(
                f"Word export failed: {str(e)}",
                status=400
            )
        except Exception as e:
            logger.error(f"Failed to generate Word for quotation {quotation.quotation_number}: {e}")
            return HttpResponse(
                "Failed to generate Word document. Please contact support.",
                status=500
            )

        # Create response with Word file
        response = HttpResponse(
            word_bytes,
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="Order_Details_{quotation.quotation_number}.docx"'

        # Log the download
        AuditLog.log_action(
            user=user,
            action_type='quotation_viewed',
            description=f'Downloaded Word (ORDER DETAILS) for quotation {quotation.quotation_number}',
            request=request
        )

        logger.info(f"User {user.email} downloaded Word for quotation {quotation.quotation_number}")

        return response
