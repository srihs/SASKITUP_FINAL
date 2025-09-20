from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count, Sum, Prefetch
from django.views.generic import ListView, DetailView, TemplateView
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.management import call_command
import logging
import subprocess
import threading
from .models import School
from .services import SchoolAPIService

# Import SyncJob from clubs app
from clubs.models import SyncJob

# Import wholesale models from clubs app
from clubs.models_wholesale import WholesaleSyncJob

# Import TUS models from clubs app
from clubs.models_tus import (
    TUSLocation, TUSSchool, TUSSchoolCategory, TUSGeneralCategory,
    TUSProduct, TUSProductVariation, TUSProductCategoryAssignment
)

# Import TUS utility functions
from .tus_utils import (
    get_tus_locations_with_stats, get_tus_schools_in_location,
    get_tus_school_with_categories, get_tus_school_category_products,
    get_tus_general_category_products, get_tus_product_with_variations,
    search_tus_entities, get_tus_dashboard_stats, get_tus_featured_locations,
    get_tus_featured_categories, check_tus_variation_availability,
    get_tus_available_options, filter_tus_products, get_tus_breadcrumbs
)

# Import wholesale utility functions
from .wholesale_utils import (
    is_tus_available, get_wholesale_dashboard_stats,
    get_wholesale_locations_with_stats, get_wholesale_schools_in_location,
    get_wholesale_school_detail, search_wholesale_entities
)


class SchoolListView(ListView):
    """List view for schools database"""
    model = School
    template_name = 'schools/school_list.html'
    context_object_name = 'schools'
    paginate_by = 20

    def get_queryset(self):
        # By default show only open schools
        queryset = School.objects.filter(status='Open')

        # Search functionality
        search_query = self.request.GET.get('q', '')
        if search_query:
            queryset = queryset.filter(
                Q(org_name__icontains=search_query) |
                Q(school_id__icontains=search_query) |
                Q(add1_city__icontains=search_query) |
                Q(regional_council__icontains=search_query) |
                Q(territorial_authority__icontains=search_query)
            )

        # Filter by organization type
        org_type = self.request.GET.get('org_type', '')
        if org_type:
            queryset = queryset.filter(org_type=org_type)

        # Filter by regional council
        regional_council = self.request.GET.get('regional_council', '')
        if regional_council:
            queryset = queryset.filter(regional_council=regional_council)

        # Filter by authority
        authority = self.request.GET.get('authority', '')
        if authority:
            queryset = queryset.filter(authority=authority)

        # Filter by status
        status = self.request.GET.get('status', '')
        if status:
            queryset = queryset.filter(status=status)

        # Sorting
        sort_by = self.request.GET.get('sort', 'org_name')
        if sort_by == 'name':
            queryset = queryset.order_by('org_name')
        elif sort_by == 'type':
            queryset = queryset.order_by('org_type', 'org_name')
        elif sort_by == 'location':
            queryset = queryset.order_by('regional_council', 'org_name')
        elif sort_by == 'size':
            queryset = queryset.order_by('-total', 'org_name')
        else:
            queryset = queryset.order_by('org_name')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add search query to context
        context['search_query'] = self.request.GET.get('q', '')

        # Add filter options
        context['filter_options'] = SchoolAPIService.get_filter_options()

        # Add current filters
        context['current_filters'] = {
            'org_type': self.request.GET.get('org_type', ''),
            'regional_council': self.request.GET.get('regional_council', ''),
            'authority': self.request.GET.get('authority', ''),
            'status': self.request.GET.get('status', ''),
            'sort': self.request.GET.get('sort', 'name'),
        }

        # Add statistics for open schools only
        open_schools = School.objects.filter(status='Open')
        context['total_schools'] = open_schools.count()

        # Get statistics for display (open schools only)
        context['statistics'] = {
            'total_students': open_schools.aggregate(total=Sum('total'))['total'] or 0,
            'school_types': open_schools.values('org_type').annotate(
                count=Count('id')
            ).order_by('-count')[:5],
            'regional_distribution': open_schools.values('regional_council').annotate(
                count=Count('id')
            ).exclude(regional_council='').order_by('-count')[:5],
        }

        return context


class SchoolDetailView(DetailView):
    """Detail view for individual school"""
    model = School
    template_name = 'schools/school_detail.html'
    context_object_name = 'school'

    def get_object(self, queryset=None):
        school_id = self.kwargs.get('school_id')
        return get_object_or_404(School, school_id=school_id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add enrollment breakdown as percentages
        school = self.object
        if school.total > 0:
            context['enrollment_percentages'] = {
                'european': (school.european / school.total * 100) if school.total else 0,
                'maori': (school.maori / school.total * 100) if school.total else 0,
                'pacific': (school.pacific / school.total * 100) if school.total else 0,
                'asian': (school.asian / school.total * 100) if school.total else 0,
                'melaa': (school.melaa / school.total * 100) if school.total else 0,
                'other': (school.other / school.total * 100) if school.total else 0,
                'international': (school.international / school.total * 100) if school.total else 0,
            }

        # Find nearby schools (same territorial authority or regional council)
        context['nearby_schools'] = School.objects.filter(
            Q(territorial_authority=school.territorial_authority) |
            Q(regional_council=school.regional_council)
        ).exclude(
            school_id=school.school_id
        ).order_by('org_name')[:5]

        return context


class RetailSchoolsView(TemplateView):
    """Legacy placeholder view for Retail Schools"""
    template_name = 'schools/retail_schools.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Retail Schools'
        return context


class WholesaleSchoolsView(ListView):
    """Main wholesale schools view - shows Cin7 wholesale schools data"""
    template_name = 'schools/wholesale_schools.html'
    context_object_name = 'schools'
    paginate_by = 12

    def get_queryset(self):
        try:
            # Import wholesale models from clubs app
            from clubs.models_wholesale import WholesaleSchool

            queryset = WholesaleSchool.objects.filter(is_active=True)

            # Search functionality
            search_query = self.request.GET.get('search')
            if search_query:
                queryset = queryset.filter(
                    Q(name__icontains=search_query) |
                    Q(description__icontains=search_query) |
                    Q(contact_person__icontains=search_query) |
                    Q(city__icontains=search_query)
                )

            return queryset.order_by('name')

        except ImportError:
            # Wholesale models not available - return empty queryset
            from django.db import models
            return models.QuerySet().none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Wholesale Schools'

        try:
            # Import wholesale models
            from clubs.models_wholesale import WholesaleSchool, WholesaleCategory, WholesaleProduct

            context['wholesale_available'] = True

            # Add wholesale statistics
            context['total_schools'] = WholesaleSchool.objects.filter(is_active=True).count()
            context['total_categories'] = WholesaleCategory.objects.filter(is_active=True).count()
            context['total_products'] = WholesaleProduct.objects.filter(is_active=True).count()

            # Get schools by region for display
            context['schools_by_region'] = WholesaleSchool.objects.filter(
                is_active=True
            ).values('region').annotate(
                count=Count('id')
            ).order_by('-count')[:5]

        except ImportError:
            context['wholesale_available'] = False
            context['error_message'] = 'Wholesale integration is not available. Please contact your administrator.'

        return context


def school_search_ajax(request):
    """AJAX endpoint for school search autocomplete"""
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'results': []})

    schools = School.objects.filter(
        Q(org_name__icontains=query) |
        Q(school_id__icontains=query)
    )[:10]

    results = [
        {
            'id': school.school_id,
            'name': school.org_name,
            'type': school.org_type,
            'city': school.add1_city,
        }
        for school in schools
    ]

    return JsonResponse({'results': results})


# ================================
# TUS Retail Schools Views
# ================================

class TUSRetailSchoolsView(ListView):
    """Main retail schools listing view - shows locations and featured content"""
    model = TUSLocation
    template_name = 'schools/retail/retail_schools.html'
    context_object_name = 'locations'
    paginate_by = 12

    def get_queryset(self):
        # Use utility function to get locations with stats
        queryset = get_tus_locations_with_stats()

        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            # Search locations and schools within those locations
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(schools__name__icontains=search_query) |
                Q(schools__contact_person__icontains=search_query) |
                Q(schools__address__icontains=search_query)
            ).distinct()

        # Location filter
        location_filter = self.request.GET.get('location')
        if location_filter:
            # Filter by specific location slug
            queryset = queryset.filter(slug=location_filter)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add statistics using utility function
        context.update(get_tus_dashboard_stats())

        # Featured locations and categories using utility functions
        context['featured_locations'] = get_tus_featured_locations(limit=6)
        context['featured_categories'] = get_tus_featured_categories(limit=6)

        # Add all locations for the filter dropdown
        context['all_locations'] = TUSLocation.objects.filter(is_active=True).order_by('name')

        # Add current search and location filter values
        context['current_location'] = self.request.GET.get('location', '')

        return context


class TUSLocationDetailView(DetailView):
    """Location detail view - shows schools within a location"""
    model = TUSLocation
    template_name = 'schools/retail/location_detail.html'
    context_object_name = 'location'
    slug_field = 'slug'
    slug_url_kwarg = 'location_slug'

    def get_object(self, queryset=None):
        location_slug = self.kwargs.get('location_slug')
        location, _ = get_tus_schools_in_location(location_slug)
        return location

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        location = self.object

        # Get schools using utility function
        search_query = self.request.GET.get('search')
        school_type = self.request.GET.get('school_type')

        location, schools = get_tus_schools_in_location(
            location.slug,
            search_query=search_query,
            school_type=school_type
        )

        # Pagination for schools
        paginator = Paginator(schools, 12)
        page = self.request.GET.get('page')
        context['schools'] = paginator.get_page(page)

        # Get available school types for filtering using utility function
        from .tus_utils import get_tus_school_types
        context['school_types'] = get_tus_school_types()

        # Get recent products for this location
        context['recent_products'] = TUSProduct.objects.filter(
            category_assignments__school_category__school__location=location,
            stock_status__in=['instock', 'onbackorder']
        ).distinct().order_by('-created_at')[:6]

        return context


class TUSSchoolDetailView(DetailView):
    """School detail view - shows categories and products for a specific school"""
    model = TUSSchool
    template_name = 'schools/retail/school_detail.html'
    context_object_name = 'school'
    slug_field = 'slug'
    slug_url_kwarg = 'school_slug'

    def get_object(self, queryset=None):
        school_slug = self.kwargs.get('school_slug')
        school, _, _ = get_tus_school_with_categories(school_slug)
        return school

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = self.object

        # Get school data using utility function
        school, categories, featured_products = get_tus_school_with_categories(school.slug)

        context['categories'] = categories
        context['featured_products'] = featured_products

        # Get base products queryset for filtering (not sliced)
        base_products_queryset = TUSProduct.objects.filter(
            category_assignments__school_category__school=school,
            stock_status__in=['instock', 'onbackorder']
        ).select_related().prefetch_related(
            'category_assignments__school_category',
            'variations'
        ).distinct()

        # Category filter
        category_filter = self.request.GET.get('category')
        if category_filter:
            filtered_products = filter_tus_products(
                base_products_queryset,
                category=category_filter
            )
            products_queryset = filtered_products
        else:
            # Use base products for filtering
            products_queryset = base_products_queryset
        search_query = self.request.GET.get('search')
        if search_query:
            products_queryset = products_queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(sku__icontains=search_query)
            )

        # Pagination for products
        paginator = Paginator(products_queryset, 12)
        page = self.request.GET.get('page')
        context['products'] = paginator.get_page(page)
        # Show all categories including "General" - schools may only have General categories
        context['categories'] = categories

        # Remove similar schools section - not needed
        # context['similar_schools'] = []

        return context


class TUSSchoolCategoryDetailView(DetailView):
    """School category detail view - shows products within a school category"""
    model = TUSSchoolCategory
    template_name = 'schools/retail/school_category_detail.html'
    context_object_name = 'category'
    slug_field = 'slug'
    slug_url_kwarg = 'category_slug'

    def get_object(self, queryset=None):
        school_slug = self.kwargs.get('school_slug')
        category_slug = self.kwargs.get('category_slug')

        return get_object_or_404(
            TUSSchoolCategory.objects.select_related('school', 'school__location'),
            school__slug=school_slug,
            slug=category_slug,
            school__is_active=True
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.object
        school = category.school

        # Get products in this category
        products = TUSProduct.objects.filter(
            category_assignments__school_category=category,
            stock_status__in=['instock', 'onbackorder']
        ).distinct()

        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            products = products.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(sku__icontains=search_query)
            )

        # Price filter
        price_range = self.request.GET.get('price_range')
        if price_range:
            if price_range == 'under_50':
                products = products.filter(price__lt=50)
            elif price_range == '50_100':
                products = products.filter(price__gte=50, price__lt=100)
            elif price_range == '100_200':
                products = products.filter(price__gte=100, price__lt=200)
            elif price_range == 'over_200':
                products = products.filter(price__gte=200)

        # Sort options
        sort_by = self.request.GET.get('sort', 'name')
        if sort_by == 'price_low':
            products = products.order_by('price')
        elif sort_by == 'price_high':
            products = products.order_by('-price')
        elif sort_by == 'newest':
            products = products.order_by('-created_at')
        else:
            products = products.order_by('name')

        # Pagination
        paginator = Paginator(products, 12)
        page = self.request.GET.get('page')
        context['products'] = paginator.get_page(page)

        # Add school and other categories
        context['school'] = school
        context['other_categories'] = school.categories.exclude(
            id=category.id
        ).filter(product_count__gt=0).order_by('display_order', 'name')

        return context


class TUSGeneralCategoryDetailView(DetailView):
    """General category detail view - shows products in general categories"""
    model = TUSGeneralCategory
    template_name = 'schools/retail/general_category_detail.html'
    context_object_name = 'category'
    slug_field = 'slug'
    slug_url_kwarg = 'category_slug'

    def get_queryset(self):
        return TUSGeneralCategory.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.object

        # Get products in this general category
        products = TUSProduct.objects.filter(
            category_assignments__general_category=category,
            stock_status__in=['instock', 'onbackorder']
        ).distinct()

        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            products = products.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(sku__icontains=search_query)
            )

        # Price filter
        price_range = self.request.GET.get('price_range')
        if price_range:
            if price_range == 'under_50':
                products = products.filter(price__lt=50)
            elif price_range == '50_100':
                products = products.filter(price__gte=50, price__lt=100)
            elif price_range == '100_200':
                products = products.filter(price__gte=100, price__lt=200)
            elif price_range == 'over_200':
                products = products.filter(price__gte=200)

        # Sort options
        sort_by = self.request.GET.get('sort', 'name')
        if sort_by == 'price_low':
            products = products.order_by('price')
        elif sort_by == 'price_high':
            products = products.order_by('-price')
        elif sort_by == 'newest':
            products = products.order_by('-created_at')
        else:
            products = products.order_by('name')

        # Pagination
        paginator = Paginator(products, 12)
        page = self.request.GET.get('page')
        context['products'] = paginator.get_page(page)

        # Get related categories
        context['related_categories'] = TUSGeneralCategory.objects.filter(
            is_active=True
        ).exclude(id=category.id).order_by('display_order', 'name')[:6]

        return context


class TUSProductDetailView(DetailView):
    """Product detail view for TUS products"""
    model = TUSProduct
    template_name = 'schools/retail/product_detail.html'
    context_object_name = 'product'
    pk_url_kwarg = 'product_id'

    def get_queryset(self):
        return TUSProduct.objects.filter(
            stock_status__in=['instock', 'onbackorder']
        ).prefetch_related(
            'variations',
            'category_assignments__school_category__school',
            'category_assignments__general_category'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object

        # Get product variations
        context['variations'] = product.variations.filter(is_active=True).order_by('menu_order')

        # Get categories
        context['categories'] = product.all_categories

        # Get related products from same categories
        related_products = TUSProduct.objects.filter(
            Q(category_assignments__school_category__in=product.school_categories.all()) |
            Q(category_assignments__general_category__in=product.general_categories.all()),
            stock_status__in=['instock', 'onbackorder']
        ).exclude(id=product.id).distinct()[:6]

        context['related_products'] = related_products

        # Check if product belongs to a specific school
        school_category = product.category_assignments.filter(
            school_category__isnull=False
        ).first()
        if school_category:
            context['school'] = school_category.school_category.school

        return context


# ================================
# TUS AJAX Views
# ================================

def tus_search_ajax(request):
    """AJAX endpoint for general TUS search"""
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'results': []})

    # Search across locations, schools, and products
    results = []

    # Search locations
    locations = TUSLocation.objects.filter(
        Q(name__icontains=query) | Q(description__icontains=query),
        is_active=True
    )[:3]

    for location in locations:
        results.append({
            'type': 'location',
            'id': location.slug,
            'title': location.name,
            'subtitle': f"{location.total_schools} schools",
            'url': f"/schools/retail/location/{location.slug}/"
        })

    # Search schools
    schools = TUSSchool.objects.filter(
        Q(name__icontains=query) | Q(contact_person__icontains=query),
        is_active=True
    )[:3]

    for school in schools:
        results.append({
            'type': 'school',
            'id': school.slug,
            'title': school.name,
            'subtitle': f"{school.location.name} - {school.school_type}",
            'url': f"/schools/retail/school/{school.slug}/"
        })

    # Search products
    products = TUSProduct.objects.filter(
        Q(name__icontains=query) | Q(description__icontains=query),
        stock_status__in=['instock', 'onbackorder']
    )[:4]

    for product in products:
        results.append({
            'type': 'product',
            'id': product.id,
            'title': product.name,
            'subtitle': f"${product.price}",
            'url': f"/schools/retail/product/{product.id}/"
        })

    return JsonResponse({'results': results})


def tus_location_search_ajax(request):
    """AJAX endpoint for location search"""
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'results': []})

    locations = TUSLocation.objects.filter(
        Q(name__icontains=query) | Q(description__icontains=query),
        is_active=True
    )[:10]

    results = [
        {
            'id': location.slug,
            'name': location.name,
            'schools_count': location.total_schools,
            'url': f"/schools/retail/location/{location.slug}/"
        }
        for location in locations
    ]

    return JsonResponse({'results': results})


def tus_school_search_ajax(request):
    """AJAX endpoint for school search"""
    query = request.GET.get('q', '')
    location_slug = request.GET.get('location', '')

    if len(query) < 2:
        return JsonResponse({'results': []})

    schools = TUSSchool.objects.filter(
        Q(name__icontains=query) | Q(contact_person__icontains=query),
        is_active=True
    )

    if location_slug:
        schools = schools.filter(location__slug=location_slug)

    schools = schools[:10]

    results = [
        {
            'id': school.slug,
            'name': school.name,
            'location': school.location.name,
            'type': school.school_type,
            'products_count': school.total_products,
            'url': f"/schools/retail/school/{school.slug}/"
        }
        for school in schools
    ]

    return JsonResponse({'results': results})


# ================================
# TUS Product Variation API Views
# ================================

def tus_product_variations_api(request, product_id):
    """API endpoint to get product variations"""
    try:
        product = get_object_or_404(TUSProduct, id=product_id)
        variations = product.variations.filter(is_active=True)

        # Group variations by type
        variation_data = {}
        for variation in variations:
            var_type = variation.variation_type
            if var_type not in variation_data:
                variation_data[var_type] = []

            variation_data[var_type].append({
                'id': variation.id,
                'value': variation.variation_value,
                'price': str(variation.price),
                'stock_status': variation.stock_status,
                'stock_quantity': variation.stock_quantity,
                'sku': variation.sku,
                'image_url': variation.effective_image_url,
                'in_stock': variation.is_in_stock
            })

        return JsonResponse({
            'success': True,
            'variations': variation_data,
            'base_price': str(product.price)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


def tus_check_variation_availability(request, product_id):
    """Check availability of specific variation combination"""
    try:
        product = get_object_or_404(TUSProduct, id=product_id)

        # Get variation selection from request
        variation_selection = {}
        for key, value in request.GET.items():
            if key.startswith('variation_'):
                var_type = key.replace('variation_', '')
                variation_selection[var_type] = value

        if not variation_selection:
            return JsonResponse({
                'success': False,
                'error': 'No variation selection provided'
            }, status=400)

        # Find matching variation
        variations = product.variations.filter(is_active=True)

        for var_type, var_value in variation_selection.items():
            variations = variations.filter(
                variation_type=var_type,
                variation_value=var_value
            )

        if variations.exists():
            variation = variations.first()
            return JsonResponse({
                'success': True,
                'available': variation.is_in_stock,
                'price': str(variation.price),
                'stock_quantity': variation.stock_quantity,
                'stock_status': variation.stock_status,
                'sku': variation.sku
            })
        else:
            return JsonResponse({
                'success': True,
                'available': False,
                'message': 'This combination is not available'
            })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


def tus_get_variation_details(request, product_id):
    """Get detailed information about a specific variation"""
    try:
        product = get_object_or_404(TUSProduct, id=product_id)
        variation_id = request.GET.get('variation_id')

        if not variation_id:
            return JsonResponse({
                'success': False,
                'error': 'Variation ID not provided'
            }, status=400)

        variation = get_object_or_404(
            TUSProductVariation,
            id=variation_id,
            product=product,
            is_active=True
        )

        return JsonResponse({
            'success': True,
            'variation': {
                'id': variation.id,
                'type': variation.variation_type,
                'value': variation.variation_value,
                'price': str(variation.price),
                'regular_price': str(variation.regular_price) if variation.regular_price else None,
                'sale_price': str(variation.sale_price) if variation.sale_price else None,
                'stock_status': variation.stock_status,
                'stock_quantity': variation.stock_quantity,
                'sku': variation.sku,
                'image_url': variation.effective_image_url,
                'in_stock': variation.is_in_stock,
                'is_on_sale': variation.is_on_sale,
                'discount_percentage': variation.discount_percentage
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


def tus_get_available_options(request, product_id, attribute_type):
    """Get available options for a specific attribute type"""
    try:
        product = get_object_or_404(TUSProduct, id=product_id)

        # Get selected variations to filter available options
        selected_variations = {}
        for key, value in request.GET.items():
            if key.startswith('variation_') and key != f'variation_{attribute_type}':
                var_type = key.replace('variation_', '')
                selected_variations[var_type] = value

        # Filter variations based on selected attributes
        variations = product.variations.filter(is_active=True)
        for var_type, var_value in selected_variations.items():
            variations = variations.filter(
                variation_type=var_type,
                variation_value=var_value
            )

        # Get available options for the requested attribute type
        available_options = variations.filter(
            variation_type=attribute_type
        ).values_list('variation_value', flat=True).distinct()

        return JsonResponse({
            'success': True,
            'options': list(available_options)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


# ================================
# TUS Sync Management Views
# ================================

@csrf_exempt
@require_http_methods(["POST"])
def sync_tus_schools(request):
    """
    Async endpoint to trigger TUS schools synchronization from WooCommerce API
    Returns immediate response with job ID for polling
    """
    logger = logging.getLogger(__name__)

    try:
        logger.info("Starting async sync request for TUS schools")

        # Auto-cleanup stale jobs before checking for running jobs
        cleaned_count = SyncJob.cleanup_stale_jobs(max_age_hours=2)
        if cleaned_count > 0:
            logger.info(f"Auto-cleaned {cleaned_count} stale sync jobs before starting new sync")

        # Check if there's already a running sync job (after cleanup)
        existing_job = SyncJob.objects.filter(
            sync_type='tus',
            status='running'
        ).first()

        if existing_job:
            # Double-check if the existing job is actually stale
            if existing_job.is_stale(max_age_hours=2):
                logger.warning(f"Found stale job {existing_job.id}, cleaning it up")
                existing_job.fail(
                    'Job was stale and cleaned up to allow new sync',
                    'AUTO_CLEANUP_ON_NEW_SYNC'
                )
                existing_job.add_log_message('Job was automatically cleaned up due to being stale when new sync was requested', 'warning')
            else:
                logger.info(f"Sync already in progress (job {existing_job.id})")
                return JsonResponse({
                    'success': True,
                    'message': 'Sync already in progress',
                    'job_id': str(existing_job.id),
                    'status': existing_job.status,
                    'progress_percentage': existing_job.progress_percentage,
                    'current_step': existing_job.current_step,
                    'already_running': True
                })

        # Create a new sync job
        sync_job = SyncJob.objects.create(
            sync_type='tus',
            status='running',
            current_step='Initializing TUS sync...',
            progress_percentage=0
        )

        def run_sync_command():
            """Background thread function to run the sync command"""
            logger = logging.getLogger(f'{__name__}.sync_thread')
            try:
                logger.info(f"Starting TUS sync job {sync_job.id}")
                sync_job.start()
                sync_job.add_log_message('TUS sync process started', 'info')

                # Call the management command
                call_command('sync_tus_schools', verbosity=2)

                # Mark as completed
                sync_job.complete()
                sync_job.add_log_message('TUS sync completed successfully', 'success')
                logger.info(f"TUS sync job {sync_job.id} completed successfully")

            except Exception as e:
                error_message = f"TUS sync failed: {str(e)}"
                logger.error(error_message, exc_info=True)
                sync_job.fail(error_message, 'SYNC_COMMAND_FAILED')
                sync_job.add_log_message(error_message, 'error')

        # Start the sync in a background thread
        sync_thread = threading.Thread(target=run_sync_command, daemon=True)
        sync_thread.start()

        logger.info(f"TUS sync job {sync_job.id} started successfully")

        return JsonResponse({
            'success': True,
            'message': 'TUS sync started successfully',
            'job_id': str(sync_job.id),
            'status': sync_job.status,
            'progress_percentage': sync_job.progress_percentage,
            'current_step': sync_job.current_step,
            'sync_type': sync_job.sync_type,
        })

    except Exception as e:
        logger.error(f"Failed to start TUS sync: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Failed to start TUS sync: {str(e)}',
            'error_code': 'SYNC_START_FAILED'
        }, status=500)


# Wholesale Sync Views (Delegates to clubs app functionality)

@require_http_methods(["POST"])
def wholesale_sync_execute(request):
    """
    Execute wholesale data sync from CIN7
    Delegates to clubs app wholesale sync functionality
    """
    try:
        # Import the clubs app wholesale sync function
        from clubs.views import wholesale_sync_execute as clubs_wholesale_sync_execute

        # Delegate to the clubs app function
        return clubs_wholesale_sync_execute(request)

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to execute wholesale sync: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Failed to execute wholesale sync: {str(e)}',
            'error_code': 'WHOLESALE_SYNC_EXECUTE_FAILED'
        }, status=500)


@require_http_methods(["GET"])
def wholesale_sync_status(request):
    """
    Get current wholesale sync status
    Delegates to clubs app wholesale sync functionality
    """
    try:
        # Import the clubs app wholesale sync status function
        from clubs.views import wholesale_sync_status as clubs_wholesale_sync_status

        # Delegate to the clubs app function
        return clubs_wholesale_sync_status(request)

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to get wholesale sync status: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Failed to get wholesale sync status: {str(e)}',
            'error_code': 'WHOLESALE_SYNC_STATUS_FAILED'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def wholesale_csv_upload(request):
    """
    Handle CSV file upload for wholesale schools data
    Uses the import_wholesale_csv management command
    """
    import os
    import tempfile
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    from django.core.management import call_command
    from io import StringIO
    import sys

    logger = logging.getLogger(__name__)

    if 'csv_file' not in request.FILES:
        return JsonResponse({
            'success': False,
            'error': 'No CSV file provided'
        }, status=400)

    csv_file = request.FILES['csv_file']

    # Validate file type
    allowed_extensions = ['.csv', '.xls', '.xlsx']
    file_extension = os.path.splitext(csv_file.name)[1].lower()
    if file_extension not in allowed_extensions:
        return JsonResponse({
            'success': False,
            'error': f'Invalid file type. Allowed types: {", ".join(allowed_extensions)}'
        }, status=400)

    # Validate file size (max 10MB)
    if csv_file.size > 10 * 1024 * 1024:
        return JsonResponse({
            'success': False,
            'error': 'File size must be less than 10MB'
        }, status=400)

    try:
        # Create a temporary file to store the uploaded CSV
        with tempfile.NamedTemporaryFile(mode='w+b', suffix=file_extension, delete=False) as temp_file:
            # Write uploaded file content to temporary file
            for chunk in csv_file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        # Capture command output
        captured_output = StringIO()
        original_stdout = sys.stdout
        original_stderr = sys.stderr

        try:
            # Redirect output to capture it
            sys.stdout = captured_output
            sys.stderr = captured_output

            # Call the management command with the temporary file
            call_command(
                'import_wholesale_csv',
                temp_file_path,
                verbosity=1
            )

            # Get the captured output
            command_output = captured_output.getvalue()

            # Parse the output to extract statistics
            stats = {
                'schools_created': 0,
                'schools_updated': 0,
                'categories_created': 0,
                'categories_updated': 0,
                'products_created': 0,
                'products_updated': 0,
                'variations_created': 0,
                'variations_updated': 0,
                'rows_processed': 0
            }

            errors = []

            # Parse command output for statistics
            for line in command_output.split('\n'):
                if 'Schools created:' in line:
                    stats['schools_created'] = int(line.split(':')[1].strip())
                elif 'Schools updated:' in line:
                    stats['schools_updated'] = int(line.split(':')[1].strip())
                elif 'Categories created:' in line:
                    stats['categories_created'] = int(line.split(':')[1].strip())
                elif 'Categories updated:' in line:
                    stats['categories_updated'] = int(line.split(':')[1].strip())
                elif 'Products created:' in line:
                    stats['products_created'] = int(line.split(':')[1].strip())
                elif 'Products updated:' in line:
                    stats['products_updated'] = int(line.split(':')[1].strip())
                elif 'Variations created:' in line:
                    stats['variations_created'] = int(line.split(':')[1].strip())
                elif 'Variations updated:' in line:
                    stats['variations_updated'] = int(line.split(':')[1].strip())
                elif 'Rows processed:' in line:
                    stats['rows_processed'] = int(line.split(':')[1].strip())
                elif 'Row ' in line and ':' in line:
                    # Extract error messages
                    errors.append(line.strip())

            logger.info(f"CSV import completed successfully. Stats: {stats}")

            return JsonResponse({
                'success': True,
                'message': 'CSV file processed successfully',
                'stats': stats,
                'errors': errors[:10],  # Limit to first 10 errors
                'command_output': command_output
            })

        finally:
            # Restore original stdout/stderr
            sys.stdout = original_stdout
            sys.stderr = original_stderr

    except Exception as e:
        logger.error(f"CSV import failed: {str(e)}", exc_info=True)

        # Clean up temp file
        try:
            if 'temp_file_path' in locals():
                os.unlink(temp_file_path)
        except:
            pass

        return JsonResponse({
            'success': False,
            'error': f'CSV import failed: {str(e)}',
            'command_output': captured_output.getvalue() if 'captured_output' in locals() else ''
        }, status=500)

    finally:
        # Clean up temporary file
        try:
            if 'temp_file_path' in locals():
                os.unlink(temp_file_path)
        except:
            pass


# Wholesale School Detail Views

class WholesaleSchoolDetailView(DetailView):
    """
    Detailed view of a wholesale school with categories and products
    """
    model = None  # Will be set in get_queryset
    template_name = 'schools/wholesale/school_detail.html'
    context_object_name = 'school'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        from clubs.models_wholesale import WholesaleSchool
        self.model = WholesaleSchool
        return WholesaleSchool.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        from clubs.models_wholesale import WholesaleCategory, WholesaleProduct
        context = super().get_context_data(**kwargs)
        school = self.get_object()

        # Get categories for this school through products
        categories_with_products = WholesaleCategory.objects.filter(
            products__school=school,
            is_active=True
        ).distinct().order_by('name')

        context['categories'] = categories_with_products

        # Get products for this school
        products = WholesaleProduct.objects.filter(
            school=school,
            is_active=True
        ).select_related('school').prefetch_related('categories').order_by('name')

        context['products'] = products

        return context


class WholesaleCategoryDetailView(DetailView):
    """
    Detailed view of a wholesale category with products
    """
    model = None  # Will be set in get_queryset
    template_name = 'schools/wholesale/category_detail.html'
    context_object_name = 'category'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        from clubs.models_wholesale import WholesaleCategory
        self.model = WholesaleCategory
        return WholesaleCategory.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        from clubs.models_wholesale import WholesaleProduct
        context = super().get_context_data(**kwargs)
        category = self.get_object()

        # Get subcategories
        context['subcategories'] = category.subcategories.filter(is_active=True).order_by('name')

        # Get products in this category
        products = WholesaleProduct.objects.filter(
            categories=category,
            is_active=True
        ).select_related('school').prefetch_related('variations').order_by('name')

        context['products'] = products

        # Get the school from the first product in this category
        # Since products belong to schools, we can get the school this way
        first_product = products.first()
        if first_product:
            context['school'] = first_product.school
        else:
            context['school'] = None

        # Stock statistics
        context['in_stock_products'] = products.filter(stock_status='in_stock').count()
        context['out_of_stock_products'] = products.filter(stock_status='out_of_stock').count()

        # Total quantity statistics
        from django.db.models import Sum
        total_stats = products.aggregate(
            total_available=Sum('quantity_available'),
            total_on_hand=Sum('quantity_on_hand'),
            total_committed=Sum('quantity_committed')
        )
        context['total_available'] = total_stats['total_available'] or 0
        context['total_on_hand'] = total_stats['total_on_hand'] or 0
        context['total_committed'] = total_stats['total_committed'] or 0

        return context


class WholesaleProductDetailView(DetailView):
    """
    Detailed view of a wholesale product with variations
    """
    model = None  # Will be set in get_queryset
    template_name = 'schools/wholesale/product_detail.html'
    context_object_name = 'product'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        from clubs.models_wholesale import WholesaleProduct
        self.model = WholesaleProduct
        return WholesaleProduct.objects.filter(is_active=True).select_related('school')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()

        # Get product variations
        context['variations'] = product.variations.filter(is_active=True).order_by('variation_type', 'variation_value')

        return context


def tus_sync_status(request, job_id):
    """
    Get TUS retail sync status
    Delegates to clubs app sync_status functionality
    """
    try:
        # Import the clubs app sync status function
        from clubs.views import sync_status

        # Delegate to the clubs app function
        return sync_status(request, job_id)

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting TUS sync status for job {job_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to get sync status: {str(e)}'
        }, status=500)
