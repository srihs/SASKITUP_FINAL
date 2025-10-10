from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count, Sum, Prefetch
from django.views.generic import ListView, DetailView, TemplateView
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.management import call_command
from django.utils import timezone
from decimal import Decimal
import logging
import subprocess
import threading
from .models import School
from .services import SchoolAPIService

# Import SyncJob from clubs app
from clubs.models import SyncJob

# Import wholesale models from schools app
from .models import WholesaleSyncJob

# Import TUS models from schools app
from schools.models_tus import (
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

# Import audit mixins
from .mixins import (
    SchoolViewAuditMixin, WholesaleAuditMixin, TUSAuditMixin,
    SearchAuditMixin, SyncAuditMixin, PriceUpdateAuditMixin,
    CSVAuditMixin, AjaxAuditMixin
)

# Import wholesale utility functions
from .wholesale_utils import (
    is_tus_available, get_wholesale_dashboard_stats,
    get_wholesale_locations_with_stats, get_wholesale_schools_in_location,
    get_wholesale_school_detail, search_wholesale_entities
)


class SchoolListView(SchoolViewAuditMixin, SearchAuditMixin, ListView):
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


class SchoolDetailView(SchoolViewAuditMixin, DetailView):
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


class WholesaleSchoolsView(WholesaleAuditMixin, SearchAuditMixin, ListView):
    """Main wholesale schools view - shows Cin7 wholesale schools data"""
    template_name = 'schools/wholesale_schools.html'
    context_object_name = 'schools'
    paginate_by = 12

    def get_queryset(self):
        try:
            # Import wholesale models from schools app
            from .models import WholesaleSchool
            from authentication.models import SalesRepSchoolAssignment

            queryset = WholesaleSchool.objects.filter(is_active=True)

            user = self.request.user

            # Admin and Account Manager: See ALL schools
            if user.is_admin or user.is_account_manager:
                pass  # No filtering needed, show all

            # Sales Rep: See ONLY assigned schools
            elif user.is_sales_rep:
                # Get assigned wholesale school IDs
                assigned_ids = SalesRepSchoolAssignment.objects.filter(
                    sales_rep=user,
                    is_active=True,
                    wholesale_school__isnull=False
                ).values_list('wholesale_school_id', flat=True)

                queryset = queryset.filter(id__in=assigned_ids)

            # Customer or other user types: No access
            else:
                return queryset.none()

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
        from authentication.models import SalesRepSchoolAssignment

        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Wholesale Schools'
        user = self.request.user

        try:
            # Import wholesale models
            from .models import WholesaleSchool, WholesaleCategory, WholesaleProduct

            context['wholesale_available'] = True

            # Get filtered schools queryset
            schools_queryset = WholesaleSchool.objects.filter(is_active=True)

            if user.is_sales_rep:
                # Filter to assigned wholesale schools only
                assigned_school_ids = SalesRepSchoolAssignment.objects.filter(
                    sales_rep=user,
                    is_active=True,
                    wholesale_school__isnull=False
                ).values_list('wholesale_school_id', flat=True)
                schools_queryset = schools_queryset.filter(id__in=assigned_school_ids)

            # Add wholesale statistics (filtered by user access)
            context['total_schools'] = schools_queryset.count()
            context['total_categories'] = WholesaleCategory.objects.filter(
                is_active=True,
                products__school__in=schools_queryset
            ).distinct().count() if user.is_sales_rep else WholesaleCategory.objects.filter(is_active=True).count()
            context['total_products'] = WholesaleProduct.objects.filter(
                is_active=True,
                school__in=schools_queryset
            ).count()

            # Get schools by region for display (filtered)
            context['schools_by_region'] = schools_queryset.values('region').annotate(
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

    # Log AJAX search
    try:
        from authentication.models import AuditLog
        user = request.user if hasattr(request, 'user') else None
        AuditLog.log_action(
            user=user,
            action_type='school_searched',
            description=f"AJAX school search: '{query}' ({len(results)} results)",
            request=request,
            search_query=query,
            results_count=len(results),
            is_ajax=True
        )
    except Exception as e:
        logger.error(f"Failed to audit AJAX school search: {str(e)}")

    return JsonResponse({'results': results})


# ================================
# TUS Retail Schools Views
# ================================

class TUSRetailSchoolsView(TUSAuditMixin, SearchAuditMixin, ListView):
    """Main retail schools listing view - shows locations and featured content"""
    model = TUSLocation
    template_name = 'schools/retail/retail_schools.html'
    context_object_name = 'locations'
    paginate_by = 12

    def get_queryset(self):
        from authentication.models import SalesRepSchoolAssignment
        from django.db.models import Count, Q

        # Use utility function to get locations with stats
        queryset = get_tus_locations_with_stats()

        user = self.request.user

        # Admin and Account Manager: See ALL locations
        if user.is_admin or user.is_account_manager:
            pass  # No filtering needed, show all

        # Sales Rep: See ONLY locations that contain assigned schools
        elif user.is_sales_rep:
            # Get assigned TUS school IDs
            assigned_school_ids = SalesRepSchoolAssignment.objects.filter(
                sales_rep=user,
                is_active=True,
                tus_school__isnull=False
            ).values_list('tus_school_id', flat=True)

            # Filter locations that contain these schools
            queryset = queryset.filter(schools__id__in=assigned_school_ids).distinct()

            # Override the school count and product count to show only assigned schools
            queryset = queryset.annotate(
                assigned_schools_count=Count(
                    'schools',
                    filter=Q(schools__id__in=assigned_school_ids, schools__is_active=True),
                    distinct=True
                ),
                assigned_products_count=Count(
                    'schools__categories__product_assignments__product',
                    filter=Q(
                        schools__id__in=assigned_school_ids,
                        schools__is_active=True,
                        schools__categories__product_assignments__product__stock_status__in=['instock', 'onbackorder']
                    ),
                    distinct=True
                )
            )

        # Customer or other user types: No access
        else:
            return queryset.none()

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
        from authentication.models import SalesRepSchoolAssignment

        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Get filtered schools queryset for sales reps
        if user.is_sales_rep:
            assigned_school_ids = SalesRepSchoolAssignment.objects.filter(
                sales_rep=user,
                is_active=True,
                tus_school__isnull=False
            ).values_list('tus_school_id', flat=True)

            # Override stats with filtered counts
            context['total_locations'] = TUSLocation.objects.filter(
                is_active=True,
                schools__id__in=assigned_school_ids
            ).distinct().count()
            context['total_schools'] = TUSSchool.objects.filter(
                is_active=True,
                id__in=assigned_school_ids
            ).count()
            context['total_general_categories'] = TUSGeneralCategory.objects.filter(is_active=True).count()
            context['total_school_categories'] = TUSSchoolCategory.objects.filter(
                school__id__in=assigned_school_ids
            ).count()
            context['total_products'] = TUSProduct.objects.filter(
                category_assignments__school_category__school__id__in=assigned_school_ids
            ).distinct().count()
            context['total_variations'] = TUSProductVariation.objects.filter(
                is_active=True,
                product__category_assignments__school_category__school__id__in=assigned_school_ids
            ).distinct().count()
            context['featured_products_count'] = TUSProduct.objects.filter(
                featured=True,
                category_assignments__school_category__school__id__in=assigned_school_ids
            ).distinct().count()
            context['on_sale_products_count'] = TUSProduct.objects.filter(
                on_sale=True,
                category_assignments__school_category__school__id__in=assigned_school_ids
            ).distinct().count()
        else:
            # Admin/Account Manager: Use utility function for all stats
            context.update(get_tus_dashboard_stats())

        # Featured locations using utility functions
        context['featured_locations'] = get_tus_featured_locations(limit=6)

        # Add all locations for the filter dropdown
        context['all_locations'] = TUSLocation.objects.filter(is_active=True).order_by('name')

        # Add current search and location filter values
        context['current_location'] = self.request.GET.get('location', '')

        return context


class TUSLocationDetailView(TUSAuditMixin, DetailView):
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
        from authentication.models import SalesRepSchoolAssignment
        from django.db.models import Count, Q

        context = super().get_context_data(**kwargs)
        location = self.object
        user = self.request.user

        # Get schools using utility function
        search_query = self.request.GET.get('search')
        school_type = self.request.GET.get('school_type')

        location, schools = get_tus_schools_in_location(
            location.slug,
            search_query=search_query,
            school_type=school_type
        )

        # Sales Rep: Filter to only assigned schools
        if user.is_sales_rep:
            assigned_school_ids = SalesRepSchoolAssignment.objects.filter(
                sales_rep=user,
                is_active=True,
                tus_school__isnull=False
            ).values_list('tus_school_id', flat=True)

            schools = schools.filter(id__in=assigned_school_ids)

        # Pagination for schools
        paginator = Paginator(schools, 12)
        page = self.request.GET.get('page')
        context['schools'] = paginator.get_page(page)

        # Get available school types for filtering using utility function
        from .tus_utils import get_tus_school_types
        context['school_types'] = get_tus_school_types()

        # Get recent products for this location (filtered by assigned schools for sales reps)
        recent_products_queryset = TUSProduct.objects.filter(
            category_assignments__school_category__school__location=location,
            stock_status__in=['instock', 'onbackorder']
        )

        if user.is_sales_rep:
            recent_products_queryset = recent_products_queryset.filter(
                category_assignments__school_category__school__id__in=assigned_school_ids
            )

        context['recent_products'] = recent_products_queryset.distinct().order_by('-created_at')[:6]

        return context


class TUSSchoolDetailView(TUSAuditMixin, DetailView):
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


class TUSSchoolCategoryDetailView(TUSAuditMixin, DetailView):
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


class TUSGeneralCategoryDetailView(TUSAuditMixin, DetailView):
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


class TUSProductDetailView(TUSAuditMixin, DetailView):
    """Product detail view for TUS products"""
    model = TUSProduct
    template_name = 'schools/retail/product_detail.html'
    context_object_name = 'product'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

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

        # Get product variations with stock information
        context['variations'] = product.variations.filter(is_active=True).order_by('menu_order')

        # Add stock quantity information for single-variant products
        stock_quantity = 0
        manage_stock = False

        # For TUS products, provide stock management similar to SAS
        effective_stock_status = product.stock_status

        if not product.has_variations and effective_stock_status == 'instock':
            # For single-variant products without specific stock data
            stock_quantity = 25  # Default stock for simple products
            manage_stock = True
        elif hasattr(product, 'stock_quantity') and product.stock_quantity is not None:
            stock_quantity = product.stock_quantity
            manage_stock = True

        context['stock_quantity'] = stock_quantity
        context['manage_stock'] = manage_stock
        context['effective_stock_status'] = effective_stock_status

        # Add available sizes and colors from variations
        variations = product.variations.filter(is_active=True)
        context['available_sizes'] = list(set(
            var.variation_value.split(' - ')[0] if ' - ' in var.variation_value
            else var.variation_value for var in variations
            if var.variation_type in ['size', 'Size']
        ))
        context['available_colors'] = list(set(
            var.variation_value.split(' - ')[-1] if ' - ' in var.variation_value
            else var.variation_value for var in variations
            if var.variation_type in ['color', 'Color', 'colour', 'Colour']
        ))
        context['available_genders'] = list(set(
            var.variation_value for var in variations
            if var.variation_type in ['gender', 'Gender']
        ))

        # Determine variation patterns
        variation_types = set(var.variation_type.lower() for var in variations)
        has_size_variations = any(vtype in ['size', 'sizing'] for vtype in variation_types)
        has_color_variations = any(vtype in ['color', 'colour'] for vtype in variation_types)
        has_gender_variations = any(vtype in ['gender'] for vtype in variation_types)
        has_other_variations = any(
            vtype not in ['size', 'sizing', 'color', 'colour', 'gender']
            for vtype in variation_types
        )

        is_size_only_product = has_size_variations and not has_color_variations and not has_other_variations
        context['is_size_only_product'] = is_size_only_product

        # For size-only products, get size-specific stock information
        if is_size_only_product:
            size_stock_info = []

            for size in context['available_sizes']:
                size_variation = variations.filter(
                    variation_type__iexact='size',
                    variation_value__icontains=size
                ).first()

                if size_variation and hasattr(size_variation, 'stock_quantity'):
                    stock_quantity_size = size_variation.stock_quantity or 0
                else:
                    stock_quantity_size = 25  # Default stock

                size_stock_info.append({
                    'size': size,
                    'stock_quantity': stock_quantity_size,
                    'is_available': stock_quantity_size > 0
                })

            context['size_stock_info'] = size_stock_info

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

        # Get primary category for display
        context['primary_category'] = product.primary_category

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

    # Log TUS search
    try:
        from authentication.models import AuditLog
        user = request.user if hasattr(request, 'user') else None
        AuditLog.log_action(
            user=user,
            action_type='tus_search_performed',
            description=f"TUS AJAX search: '{query}' ({len(results)} results)",
            request=request,
            search_query=query,
            results_count=len(results),
            result_types=[r['type'] for r in results],
            is_ajax=True
        )
    except Exception as e:
        logger.error(f"Failed to audit TUS search: {str(e)}")

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
    """
    API endpoint to get product variations with stock information for TUS products
    Enhanced with proper ordering and filtering support (based on SAS implementation)
    """
    logger = logging.getLogger(__name__)

    try:
        product = get_object_or_404(TUSProduct, id=product_id)

        # Use the new variation methods for TUS products
        if product.has_variations:
            variation_data = product.get_variation_data_for_frontend()
            variations_data = variation_data.get('variations', [])
            grouped_variations = {}

            # Group variations by type for easier frontend handling
            for variation in variations_data:
                var_type = variation['type']
                if var_type not in grouped_variations:
                    grouped_variations[var_type] = []

                # Enhanced variation data with proper structure for frontend
                stock_quantity = variation.get('stock', 0) or 0
                is_in_stock = variation.get('is_in_stock', stock_quantity > 0)

                # Calculate stock_status
                if not variation.get('is_active', True):
                    stock_status = 'discontinued'
                elif stock_quantity > 0:
                    stock_status = 'instock'
                else:
                    stock_status = 'outofstock'

                # For TUS products, genders and colors should always be selectable
                is_available = is_in_stock
                if var_type in ['color', 'colour', 'gender', 'style']:
                    is_available = True  # Always allow selection for TUS

                enhanced_variation = {
                    'id': variation['id'],
                    'type': var_type,
                    'value': variation['value'],
                    'is_available': is_available,
                    'stock_quantity': stock_quantity,
                    'stock_status': stock_status,
                    'price_modifier': variation.get('price_modifier', 0.0),
                    'final_price': variation.get('final_price', float(product.price)),
                    'sku_suffix': variation.get('sku_suffix', ''),
                    'image': variation.get('image', product.image_url),
                    'attributes': variation.get('attributes', {})
                }

                grouped_variations[var_type].append(enhanced_variation)

            # Sort variations in TUS-specific order: gender -> size -> color -> others
            tus_order = ['gender', 'size', 'color', 'colour', 'style', 'length', 'fit']
            ordered_grouped_variations = {}

            # Add variations in the preferred order
            for var_type in tus_order:
                if var_type in grouped_variations:
                    ordered_grouped_variations[var_type] = _sort_variation_values_tus(
                        grouped_variations[var_type], var_type
                    )

            # Add any remaining variations not in the preferred order
            for var_type, variations in grouped_variations.items():
                if var_type not in ordered_grouped_variations:
                    ordered_grouped_variations[var_type] = _sort_variation_values_tus(
                        variations, var_type
                    )

            grouped_variations = ordered_grouped_variations
        else:
            # No variations
            variations_data = []
            grouped_variations = {}

        return JsonResponse({
            'success': True,
            'product_id': product_id,
            'product_name': product.name,
            'base_price': float(product.price),
            'variations': variations_data,
            'grouped_variations': grouped_variations,
            'total_variations': len(variations_data),
            'variation_order': list(grouped_variations.keys())
        })

    except Exception as e:
        logger.error(f"Error fetching TUS product variations: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch product variations',
            'message': str(e)
        }, status=500)


def _sort_variation_values_tus(variations, var_type):
    """
    Helper function to sort variation values in logical order for TUS products
    """
    def sort_key(variation):
        value = variation['value'].lower()

        if var_type == 'size':
            # Standard sizes order
            size_order = ['4', '6', '8', '10', '12', '14', '16', '18',
                         'xs', 's', 'm', 'l', 'xl', '2xl', '3xl', '4xl', '5xl']

            # Try numeric first
            try:
                numeric_value = int(value)
                return (0, numeric_value)
            except ValueError:
                pass

            # Try standard size names
            if value in size_order:
                return (1, size_order.index(value))
            else:
                return (2, value)  # Unknown sizes last

        elif var_type == 'gender':
            # Gender order: Boys/Girls -> Mens/Womens -> Unisex
            gender_order = ['boys', 'girls', 'mens', 'womens', 'men', 'women', 'unisex']
            if value in gender_order:
                return (0, gender_order.index(value))
            else:
                return (1, value)

        elif var_type in ['color', 'colour']:
            # Color order: common colors first
            common_colors = ['black', 'white', 'navy', 'red', 'blue', 'green',
                           'yellow', 'grey', 'gray', 'maroon']
            if value in common_colors:
                return (0, common_colors.index(value))
            else:
                return (1, value)

        else:
            # Default alphabetical sorting
            return (0, value)

    return sorted(variations, key=sort_key)


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

        # Log sync start
        from authentication.models import AuditLog
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        AuditLog.log_action(
            user=user,
            action_type='tus_sync_started',
            description="TUS schools sync initiated",
            request=request,
            sync_type='tus'
        )

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

                # Call the management command, passing the job ID
                call_command('sync_tus_schools', job_id=str(sync_job.id), verbosity=2)

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

class WholesaleSchoolDetailView(WholesaleAuditMixin, DetailView):
    """
    Detailed view of a wholesale school with categories and products
    """
    model = None  # Will be set in get_queryset
    template_name = 'schools/wholesale/school_detail.html'
    context_object_name = 'school'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        from .models import WholesaleSchool
        self.model = WholesaleSchool
        return WholesaleSchool.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        from .models import WholesaleCategory, WholesaleProduct
        context = super().get_context_data(**kwargs)
        school = self.get_object()

        # Get categories for this school through products, excluding "General"
        categories_with_products = WholesaleCategory.objects.filter(
            products__school=school,
            is_active=True
        ).exclude(name__iexact='General').distinct().order_by('name')

        context['categories'] = categories_with_products

        # Get products for this school
        products = WholesaleProduct.objects.filter(
            school=school,
            is_active=True
        ).select_related('school').prefetch_related('categories').order_by('name')

        context['products'] = products

        # Get products specifically from the "General" category for this school
        all_general_products = WholesaleProduct.objects.filter(
            school=school,
            is_active=True,
            categories__name__iexact='General'
        ).select_related('school').prefetch_related('categories').order_by('name')

        # Group products by base SKU to avoid showing duplicates
        grouped_products = self._group_products_by_base_sku(all_general_products)

        context['general_products'] = grouped_products

        return context

    def _group_products_by_base_sku(self, products):
        """
        Group products by their base SKU pattern.
        For example: "US FLC 789 CGS - XL" and "US FLC 789 CGS - 2XL"
        both belong to base SKU "US FLC 789 CGS"
        """
        from collections import defaultdict
        import re

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
                main_product.base_sku = base_sku
                result.append(main_product)

        return sorted(result, key=lambda p: p.name or '')

    def _extract_base_sku(self, sku):
        """
        Extract base SKU by removing common variation patterns.
        Examples:
        - "US FLC 789 CGS - XL" -> "US FLC 789 CGS"
        - "US FLC 789 CGS - 123" -> "US FLC 789 CGS"
        """
        if not sku:
            return ''

        # Remove common variation patterns (after dash, after space followed by size/number)
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
        - "US FLC 789 CGS - XL" -> "XL"
        - "US FLC 789 CGS - 123" -> "123"
        """
        if not sku:
            return ''

        import re

        # Look for variation after dash
        match = re.search(r'-\s*(.+)$', sku)
        if match:
            return match.group(1).strip()

        # Look for common size patterns at the end
        size_match = re.search(r'\s+(XS|S|M|L|XL|XXL|2XL|3XL|\d+)$', sku, re.IGNORECASE)
        if size_match:
            return size_match.group(1)

        return ''


class WholesaleCategoryDetailView(WholesaleAuditMixin, DetailView):
    """
    Detailed view of a wholesale category with products
    """
    model = None  # Will be set in get_queryset
    template_name = 'schools/wholesale/category_detail.html'
    context_object_name = 'category'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        from .models import WholesaleCategory
        self.model = WholesaleCategory
        return WholesaleCategory.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        from .models import WholesaleProduct
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


class WholesaleProductDetailView(WholesaleAuditMixin, DetailView):
    """
    Detailed view of a wholesale product with variations
    """
    model = None  # Will be set in get_queryset
    template_name = 'schools/wholesale/product_detail.html'
    context_object_name = 'product'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        from .models import WholesaleProduct
        self.model = WholesaleProduct
        return WholesaleProduct.objects.filter(is_active=True).select_related('school').prefetch_related('categories', 'variations')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()

        # Get all products with same base SKU for grouped variations
        base_sku = self._extract_base_sku(product.cin7_sku or '')
        if base_sku:
            related_products = self._get_products_by_base_sku(base_sku, product.school)
        else:
            related_products = [product]

        # Process variations from related products
        variations_data = self._process_product_variations(related_products)

        # Calculate price ranges
        price_data = self._calculate_price_ranges(related_products)

        # Check if all variations have the same price (for display as labels vs buttons)
        price_uniformity = self._check_price_uniformity(related_products)

        context.update({
            'base_sku': base_sku or product.cin7_sku,
            'related_products': related_products,
            'variations_data': variations_data,
            'available_sizes': variations_data.get('sizes', []),
            'available_colors': variations_data.get('colors', []),
            'size_only_product': len(variations_data.get('colors', [])) == 0,
            'has_variations': len(variations_data.get('sizes', [])) > 1 or len(variations_data.get('colors', [])) > 1,
            'primary_category': product.categories.first(),
            'price_data': price_data,
            'same_price_variations': price_uniformity['all_same'],
            'price_uniformity': price_uniformity,
        })

        return context

    def _extract_base_sku(self, sku):
        """Extract base SKU by removing variation suffixes"""
        if not sku:
            return ''

        import re
        # Remove common variation patterns
        base = re.sub(r'\s*-\s*.+$', '', sku)  # Remove " - anything"
        base = re.sub(r'\s+(XS|S|M|L|XL|XXL|2XL|3XL|\d+)$', '', base, flags=re.IGNORECASE)
        base = re.sub(r'\s+\d+$', '', base)  # Remove trailing numbers
        return base.strip()

    def _get_products_by_base_sku(self, base_sku, school):
        """Get all products with the same base SKU"""
        from .models import WholesaleProduct

        # Find products where cin7_sku starts with base_sku
        return WholesaleProduct.objects.filter(
            school=school,
            is_active=True,
            cin7_sku__startswith=base_sku
        ).select_related('school').prefetch_related('categories').order_by('cin7_sku')

    def _process_product_variations(self, products):
        """Process products to extract size and color variations from actual variation data"""
        from .models import WholesaleProductVariation

        sizes = set()
        colors = set()
        variations = []

        # Get all variations for these products from the database
        product_ids = [p.id for p in products]
        all_variations = WholesaleProductVariation.objects.filter(
            product_id__in=product_ids
        ).select_related('product')

        for variation in all_variations:
            variation_value = variation.variation_value.strip()

            if not variation_value:
                continue

            # Try to determine if it's a size or color/other
            if self._looks_like_size(variation_value):
                sizes.add(variation_value)
                variation_type = 'size'
            else:
                # Check if it looks like a color or other attribute
                colors.add(variation_value)
                variation_type = 'color'

            # Get price for this variation
            price = None
            if variation.wholesale_price:
                price = variation.wholesale_price
            elif variation.retail_price:
                price = variation.retail_price
            elif variation.cost_price:
                price = variation.cost_price

            variations.append({
                'product': variation.product,
                'variation': variation_value,
                'type': variation_type,
                'stock_status': variation.product.stock_status,
                'quantity': variation.product.quantity_available,
                'variation_object': variation,
                'price': price,
            })

        # Also process any SKU-based variations if no DB variations exist
        if not all_variations:
            for product in products:
                variation_info = self._extract_variation_from_sku(product.cin7_sku or '')

                if variation_info:
                    # Try to determine if it's a size or color/other
                    if self._looks_like_size(variation_info):
                        sizes.add(variation_info)
                        variation_type = 'size'
                    else:
                        colors.add(variation_info)
                        variation_type = 'color'

                    variations.append({
                        'product': product,
                        'variation': variation_info,
                        'type': variation_type,
                        'stock_status': product.stock_status,
                        'quantity': product.quantity_available,
                    })

        return {
            'sizes': sorted(list(sizes), key=self._size_sort_key),
            'colors': sorted(list(colors)),
            'variations': variations,
        }

    def _extract_variation_from_sku(self, sku):
        """Extract variation information from SKU"""
        if not sku:
            return ''

        import re
        # Look for variation after dash
        match = re.search(r'-\s*(.+)$', sku)
        if match:
            return match.group(1).strip()

        # Look for common size patterns at the end
        size_match = re.search(r'\s+(XS|S|M|L|XL|XXL|2XL|3XL|\d+)$', sku, re.IGNORECASE)
        if size_match:
            return size_match.group(1)

        return ''

    def _looks_like_size(self, variation):
        """Determine if a variation looks like a size"""
        import re
        size_patterns = [
            r'^(XS|S|M|L|XL|XXL|2XL|3XL|4XL|5XL|6XL|7XL|8XL|9XL|10XL)$',  # Standard sizes including 6XL, 7XL etc
            r'^\d+$',  # Numbers
            r'^\d+[A-Z]?$',  # Numbers with optional letter
            r'^Size\s+\d+$',  # "Size 12"
            r'^\d+XL$',  # Pattern for 6XL, 7XL, etc.
        ]

        for pattern in size_patterns:
            if re.match(pattern, variation, re.IGNORECASE):
                return True
        return False

    def _size_sort_key(self, size):
        """Custom sort key for sizes"""
        size_order = {
            'XS': 1, 'S': 2, 'M': 3, 'L': 4, 'XL': 5, 'XXL': 6, '2XL': 6,
            '3XL': 7, '4XL': 8, '5XL': 9, '6XL': 10, '7XL': 11, '8XL': 12,
            '9XL': 13, '10XL': 14
        }

        # Check if it's a standard size
        if size.upper() in size_order:
            return (0, size_order[size.upper()])

        # Check if it's a numeric XL pattern (like 11XL, 12XL)
        import re
        xl_match = re.match(r'^(\d+)XL$', size.upper())
        if xl_match:
            return (0, 6 + int(xl_match.group(1)))  # Start after 2XL (6) and add the number

        # Check if it's a number
        if re.match(r'^\d+$', size):
            return (1, int(size))

        # Everything else alphabetically
        return (2, size.lower())

    def _calculate_price_ranges(self, products):
        """Calculate price ranges for wholesale and retail prices"""
        wholesale_prices = []
        retail_prices = []
        cost_prices = []

        for product in products:
            if product.wholesale_price:
                wholesale_prices.append(float(product.wholesale_price))
            if product.retail_price:
                retail_prices.append(float(product.retail_price))
            if product.cost_price:
                cost_prices.append(float(product.cost_price))

        # Calculate wholesale price range
        wholesale_range = None
        if wholesale_prices:
            min_wholesale = min(wholesale_prices)
            max_wholesale = max(wholesale_prices)
            wholesale_range = {
                'min': min_wholesale,
                'max': max_wholesale,
                'has_range': min_wholesale != max_wholesale,
                'single_price': min_wholesale if min_wholesale == max_wholesale else None
            }

        # Calculate retail price range
        retail_range = None
        if retail_prices:
            min_retail = min(retail_prices)
            max_retail = max(retail_prices)
            retail_range = {
                'min': min_retail,
                'max': max_retail,
                'has_range': min_retail != max_retail,
                'single_price': min_retail if min_retail == max_retail else None
            }

        # If no wholesale/retail prices, check if we have cost prices as fallback
        cost_range = None
        if cost_prices and not wholesale_prices and not retail_prices:
            min_cost = min(cost_prices)
            max_cost = max(cost_prices)
            cost_range = {
                'min': min_cost,
                'max': max_cost,
                'has_range': min_cost != max_cost,
                'single_price': min_cost if min_cost == max_cost else None
            }

        return {
            'wholesale': wholesale_range,
            'retail': retail_range,
            'cost': cost_range,
            'has_any_pricing': bool(wholesale_prices or retail_prices or cost_prices),
        }

    def _check_price_uniformity(self, products):
        """Check if all variations have the same price"""
        from .models import WholesaleProductVariation

        # Get all variations for these products
        product_ids = [p.id for p in products]
        variations = WholesaleProductVariation.objects.filter(product_id__in=product_ids)

        wholesale_prices = set()
        retail_prices = set()
        cost_prices = set()

        for variation in variations:
            if variation.wholesale_price:
                wholesale_prices.add(float(variation.wholesale_price))
            if variation.retail_price:
                retail_prices.add(float(variation.retail_price))
            if variation.cost_price:
                cost_prices.add(float(variation.cost_price))

        # Check if all prices are the same for each type
        same_wholesale = len(wholesale_prices) <= 1
        same_retail = len(retail_prices) <= 1
        same_cost = len(cost_prices) <= 1

        # Consider prices uniform if the primary pricing method is uniform
        # Priority: wholesale > retail > cost
        if wholesale_prices:
            primary_uniform = same_wholesale
        elif retail_prices:
            primary_uniform = same_retail
        else:
            primary_uniform = same_cost

        return {
            'all_same': primary_uniform,
            'same_wholesale': same_wholesale,
            'same_retail': same_retail,
            'same_cost': same_cost,
            'has_wholesale': bool(wholesale_prices),
            'has_retail': bool(retail_prices),
            'has_cost': bool(cost_prices),
        }


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


# ================================
# NZ Schools Sync Management Views
# ================================

@csrf_exempt
@require_http_methods(["POST"])
def sync_nz_schools(request):
    """
    Async endpoint to trigger NZ schools synchronization from NZ Government API
    Returns immediate response with job ID for polling
    """
    logger = logging.getLogger(__name__)

    try:
        logger.info("Starting async sync request for NZ schools")

        # Log sync start
        from authentication.models import AuditLog
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        AuditLog.log_action(
            user=user,
            action_type='nz_sync_started',
            description="NZ schools sync initiated",
            request=request,
            sync_type='nz'
        )

        # Auto-cleanup stale jobs before checking for running jobs
        cleaned_count = SyncJob.cleanup_stale_jobs(max_age_hours=2)
        if cleaned_count > 0:
            logger.info(f"Auto-cleaned {cleaned_count} stale sync jobs before starting new sync")

        # Check if there's already a running sync job (after cleanup)
        existing_job = SyncJob.objects.filter(
            sync_type='nz',
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
            sync_type='nz',
            status='running',
            current_step='Initializing NZ schools sync...',
            progress_percentage=0
        )

        def run_sync_command():
            """Background thread function to run the sync command"""
            logger = logging.getLogger(f'{__name__}.sync_thread')
            try:
                logger.info(f"Starting NZ schools sync job {sync_job.id}")
                sync_job.start()
                sync_job.add_log_message('NZ schools sync process started', 'info')

                # Call the management command to sync ALL schools
                # Note: --all-schools flag syncs both open and closed schools
                # The Status:"Open" filter doesn't work with the API, so we sync all and filter in UI
                call_command('sync_schools', all_schools=True, verbosity=2)

                # Mark as completed
                sync_job.complete()
                sync_job.add_log_message('NZ schools sync completed successfully', 'success')
                logger.info(f"NZ schools sync job {sync_job.id} completed successfully")

            except Exception as e:
                error_message = f"NZ schools sync failed: {str(e)}"
                logger.error(error_message, exc_info=True)
                sync_job.fail(error_message, 'SYNC_COMMAND_FAILED')
                sync_job.add_log_message(error_message, 'error')

        # Start the sync in a background thread
        sync_thread = threading.Thread(target=run_sync_command, daemon=True)
        sync_thread.start()

        logger.info(f"NZ schools sync job {sync_job.id} started successfully")

        return JsonResponse({
            'success': True,
            'message': 'NZ schools sync started successfully',
            'job_id': str(sync_job.id),
            'status': sync_job.status,
            'progress_percentage': sync_job.progress_percentage,
            'current_step': sync_job.current_step,
            'sync_type': sync_job.sync_type,
        })

    except Exception as e:
        logger.error(f"Failed to start NZ schools sync: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Failed to start NZ schools sync: {str(e)}',
            'error_code': 'SYNC_START_FAILED'
        }, status=500)


def nz_schools_sync_status(request, job_id):
    """
    Get NZ schools sync status
    Delegates to clubs app sync_status functionality
    """
    try:
        # Import the clubs app sync status function
        from clubs.views import sync_status

        # Delegate to the clubs app function
        return sync_status(request, job_id)

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting NZ schools sync status for job {job_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to get sync status: {str(e)}'
        }, status=500)

# ============================================================================
# OLD EXCEL/CSV-BASED PRICE PREVIEW - COMMENTED OUT - Replaced with Cin7 API
# ============================================================================
'''
@csrf_exempt
@require_http_methods(["POST"])
def wholesale_price_preview(request):
    """
    Generate preview of wholesale price updates from CSV upload.
    Returns detailed preview data for user review before applying changes.
    Supports multiple product categories via ProductMatcherService.
    """
    import os
    import tempfile
    import csv
    import sys
    from decimal import Decimal, InvalidOperation
    from pathlib import Path
    from django.core.files.storage import default_storage
    from django.core.files.base import ContentFile
    from .models import WholesaleProduct, WholesaleSchool
    from .services import ProductMatcherService

    import traceback

    logger = logging.getLogger(__name__)
    logger.info("=== WHOLESALE PRICE PREVIEW STARTED ===")
    start_time = timezone.now()
    logger.info(f"[PERF-START] Operation: wholesale_price_preview | Start: {start_time.isoformat()}")

    # Log price preview access
    try:
        from authentication.models import AuditLog
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        AuditLog.log_action(
            user=user,
            action_type='wholesale_price_preview',
            description="Wholesale price preview requested",
            request=request,
            operation_type='price_preview'
        )
    except Exception as e:
        logger.error(f"Failed to audit price preview: {str(e)}")

    try:
        if 'csv_file' not in request.FILES:
            logger.warning("No CSV file provided in request")
            return JsonResponse({
                'success': False,
                'error': 'No CSV file provided'
            })

        # Get category filter (default to wholesale-schools for backward compatibility)
        category = request.POST.get('category_filter', 'wholesale-schools')
        logger.info(f"[LOTTO-CATEGORY] Category filter selected: {category}")
        logger.info(f"[LOTTO-CATEGORY] Is LOTTO category: {category == 'lotto-clubs'}")

        # Initialize product matcher service
        try:
            matcher = ProductMatcherService()
            category_info = matcher.get_category_info(category)
            logger.info(f"Category info: {category_info}")
        except Exception as e:
            logger.error(f"Error initializing ProductMatcherService: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': f'Failed to initialize product matcher: {str(e)}',
                'traceback': traceback.format_exc(),
                'category': category
            }, status=500)

        csv_file = request.FILES['csv_file']
        logger.info(f"Processing CSV file: {csv_file.name} ({csv_file.size} bytes)")

        # Save file temporarily
        temp_file_path = None
        try:
            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(mode='w+b', suffix='.csv', delete=False)
            temp_file_path = temp_file.name

            for chunk in csv_file.chunks():
                temp_file.write(chunk)
            temp_file.close()

            logger.info(f"CSV file saved to temporary path: {temp_file_path}")

            # Process the CSV
            preview_data = []
            errors = []
            row_count = 0
            valid_rows = 0

            # PRE-LOAD all products into memory for faster lookup
            logger.info(f"Pre-loading {category} products for faster matching...")
            preload_start = timezone.now()
            logger.info(f"[PERF-START] Phase: preload_products | Start: {preload_start.isoformat()} | Category: {category}")

            try:
                model_class = matcher._get_model_class(category)
                if not model_class:
                    return JsonResponse({
                        'success': False,
                        'error': f'Invalid category: {category}'
                    })

                # Get field names
                sku_field = matcher.SKU_FIELDS.get(category)
                barcode_field = matcher.BARCODE_FIELDS.get(category)

                # Create lookup dictionaries for O(1) access
                products_by_sku = {}
                products_by_barcode = {}
                variations_by_key = {}  # Exact match variation instances
                variations_by_normalized_key = {}  # Normalized match variation instances

                # Load all products at once
                product_query_start = timezone.now()
                all_products = model_class.objects.all()
                product_query_elapsed = (timezone.now() - product_query_start).total_seconds()
                logger.info(f"[PERF-PHASE] Phase: product_query | Duration: {product_query_elapsed:.2f}s | Items: {len(all_products)}")
                for product in all_products:
                    # Index by SKU
                    if sku_field and hasattr(product, sku_field):
                        sku_value = getattr(product, sku_field)
                        if sku_value:
                            products_by_sku[str(sku_value).strip().upper()] = product

                    # Index by barcode
                    if barcode_field and hasattr(product, barcode_field):
                        barcode_value = getattr(product, barcode_field)
                        if barcode_value:
                            products_by_barcode[str(barcode_value).strip().upper()] = product

                # ===== OPTIMIZED: Load variations ONCE with all indexes =====
                # Build exact AND normalized indexes in single pass
                if category == 'retail-schools':
                    from schools.models_tus import TUSProductVariation
                    variations = TUSProductVariation.objects.select_related('product').all()
                    logger.info(f"[TUS-MATCH] Loading {variations.count()} TUS variations")
                    for variation in variations:
                        if variation.sku:
                            # Exact key
                            exact_key = str(variation.sku).strip().upper()
                            variations_by_key[exact_key] = variation
                            # Normalized key (no spaces)
                            normalized_key = variation.sku.replace(' ', '').upper()
                            variations_by_normalized_key[normalized_key] = variation

                elif category == 'sas-clubs':
                    from clubs.models_sas import SASProductVariation
                    variations = SASProductVariation.objects.select_related('product').all()
                    logger.info(f"[SAS-MATCH] Loading {variations.count()} SAS variations")
                    for variation in variations:
                        if variation.sku_suffix:
                            exact_key = str(variation.sku_suffix).strip().upper()
                            variations_by_key[exact_key] = variation
                            normalized_key = variation.sku_suffix.replace(' ', '').upper()
                            variations_by_normalized_key[normalized_key] = variation

                elif category == 'lotto-clubs':
                    from clubs.models_lotto import LottoProductVariation
                    variations = LottoProductVariation.objects.select_related('product').all()
                    logger.info(f"[LOTTO-MATCH] Loading {variations.count()} LOTTO variations")
                    for variation in variations:
                        if variation.sku_suffix:
                            exact_key = str(variation.sku_suffix).strip().upper()
                            variations_by_key[exact_key] = variation
                            normalized_key = variation.sku_suffix.replace(' ', '').upper()
                            variations_by_normalized_key[normalized_key] = variation

                preload_elapsed = (timezone.now() - preload_start).total_seconds()
                logger.info(f"Pre-loaded {len(all_products)} products: "
                           f"{len(products_by_sku)} indexed by SKU, "
                           f"{len(products_by_barcode)} indexed by barcode, "
                           f"{len(variations_by_key)} variations (exact), "
                           f"{len(variations_by_normalized_key)} variations (normalized)")
                logger.info(f"[PERF-END] Phase: preload_products | End: {timezone.now().isoformat()} | Total: {preload_elapsed:.2f}s")
            except Exception as e:
                logger.error(f"Error pre-loading products: {str(e)}", exc_info=True)
                return JsonResponse({
                    'success': False,
                    'error': f'Failed to load products from database: {str(e)}',
                    'traceback': traceback.format_exc(),
                    'category': category
                }, status=500)

            csv_parse_start = timezone.now()
            logger.info(f"[PERF-START] Phase: csv_processing | Start: {csv_parse_start.isoformat()}")

            with open(temp_file_path, 'r', encoding='utf-8-sig') as file:
                try:
                    # Detect dialect
                    sample = file.read(1024)
                    file.seek(0)
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(sample)

                    # Increase CSV field size limit to handle large fields
                    csv.field_size_limit(1048576)  # 1MB limit instead of default 128KB

                    reader = csv.DictReader(file, dialect=dialect)
                    logger.info(f"CSV headers detected: {reader.fieldnames}")

                    # ===== PERFORMANCE OPTIMIZATION: Pre-detect column names ONCE =====
                    # Instead of checking 11+ field variations for EVERY row, detect once
                    headers_lower = {h.lower(): h for h in reader.fieldnames}

                    # Find actual column names (case-insensitive)
                    sku_col = None
                    for variant in ['code', 'style code', 'sku', 'product_code', 'product code', 'item code', 'style', 'item_code', 'style_code']:
                        if variant in headers_lower:
                            sku_col = headers_lower[variant]
                            break

                    barcode_col = None
                    for variant in ['barcode', 'upc', 'ean', 'gtin']:
                        if variant in headers_lower:
                            barcode_col = headers_lower[variant]
                            break

                    name_col = None
                    for variant in ['product name', 'product_name', 'name', 'description', 'product']:
                        if variant in headers_lower:
                            name_col = headers_lower[variant]
                            break

                    cost_col = None
                    for variant in ['cost nzd excl', 'cost', 'cost_price', 'unit cost', 'cost_nzd', 'unit_cost']:
                        if variant in headers_lower:
                            cost_col = headers_lower[variant]
                            break

                    retail_col = None
                    for variant in ['retail nzd incl', 'retail', 'retail_price', 'selling_price', 'price', 'current retail nzd incl', 'current_retail_nzd_incl']:
                        if variant in headers_lower:
                            retail_col = headers_lower[variant]
                            break

                    logger.info(f"Column mapping: SKU={sku_col}, Barcode={barcode_col}, Name={name_col}, Cost={cost_col}, Retail={retail_col}")

                except Exception as e:
                    logger.error(f"Error parsing CSV file: {str(e)}", exc_info=True)
                    return JsonResponse({
                        'success': False,
                        'error': f'Failed to parse CSV file: {str(e)}',
                        'traceback': traceback.format_exc(),
                        'file_name': csv_file.name
                    }, status=500)

                for row_num, row in enumerate(reader, 1):
                    row_count += 1

                    # Log progress every 1000 rows instead of every row
                    if row_count % 1000 == 0:
                        logger.info(f"Processing row {row_count}...")

                    try:
                        # ===== FAST PATH: Use pre-detected column names =====
                        product_code = str(row.get(sku_col, '') if sku_col else '').strip()
                        barcode = str(row.get(barcode_col, '') if barcode_col else '').strip()
                        product_name = str(row.get(name_col, '') if name_col else '').strip()

                        if not product_code and not barcode:
                            error_msg = f"Row {row_num}: Missing product code and barcode. Available columns: {', '.join(row.keys())}"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue

                        # Use ProductMatcherService to find product and variation
                        product_code_clean = str(product_code).strip() if product_code else ''
                        barcode_clean = str(barcode).strip() if barcode else ''

                        # ===== FAST PATH: O(1) hash map lookup =====
                        product = None
                        match_method = None
                        variation = None

                        # Try exact variation match first
                        if product_code_clean:
                            lookup_key = product_code_clean.upper()
                            if lookup_key in variations_by_key:
                                variation = variations_by_key[lookup_key]
                                product = variation.product
                                match_method = 'sku_suffix_exact_cached'
                            else:
                                # Try normalized match (no spaces)
                                normalized_key = product_code_clean.replace(' ', '').upper()
                                if normalized_key in variations_by_normalized_key:
                                    variation = variations_by_normalized_key[normalized_key]
                                    product = variation.product
                                    match_method = 'sku_suffix_normalized_cached'

                        # Try barcode if product_code didn't match
                        if not product and barcode_clean:
                            lookup_key = barcode_clean.upper()
                            if lookup_key in products_by_barcode:
                                product = products_by_barcode[lookup_key]
                                match_method = 'barcode_exact_cached'

                        # ===== OPTIMIZATION: Skip slow database lookups in preview mode =====
                        # For preview, hash table misses are just marked as "not found"
                        # The actual update process will handle these with full matching
                        # This avoids 86K database queries for non-matching items
                        # Performance: O(1) hash lookup vs O(N) database query per row
                        # Estimated savings: 20+ minutes reduced to seconds for 86K rows
                        # if not product:
                        #     product, match_method, variation = matcher.find_product_with_variation(
                        #         category, product_code_clean, barcode_clean
                        #     )

                        if row_count <= 5 or row_count % 10000 == 0:
                            logger.info(f"[LOTTO-MATCH] Row {row_num}: SKU='{product_code_clean}' -> Product={product.name if product else 'None'}, Variation={'Yes' if variation else 'No'}, Method={match_method}")

                        # Determine target object: use variation if found, otherwise use product
                        target = variation if variation else product

                        # Get price field name for this category
                        price_field = matcher.get_price_field(category)

                        if category == 'lotto-clubs' and row_count <= 5:
                            logger.info(f"[LOTTO-PRICE] Row {row_num}: price_field={price_field}, target_type={'variation' if variation else 'product'}")

                        # ===== FAST PATH: Use pre-detected columns =====
                        cost_raw = row.get(cost_col, '') if cost_col else ''

                        # Calculate prices when cost > 0
                        margin_75_price = None
                        rrp = None
                        discount_percentage = None
                        cost_value = Decimal('0')

                        if cost_raw:
                            try:
                                cost_value = Decimal(str(cost_raw))
                                if cost_value > 0:
                                    # Calculate 75% margin price: Cost ÷ 0.25
                                    margin_75_price = float(cost_value / Decimal('0.25'))

                                    # Get current retail price from target (variation or product)
                                    current_price = None

                                    if target and price_field:
                                        # For variations, use 'price' field instead of 'retail_price'
                                        if variation:
                                            current_price = getattr(target, 'price', None)
                                        else:
                                            current_price = getattr(target, price_field, None) if hasattr(target, price_field) else None

                                        if current_price:
                                            rrp = float(current_price)

                                            # Calculate discount percentage: ((margin_75 - retail) / margin_75) × 100
                                            # Negative values indicate RRP is higher than 75% margin price
                                            if margin_75_price > 0:
                                                discount_calc = ((Decimal(str(margin_75_price)) - Decimal(str(current_price))) / Decimal(str(margin_75_price))) * 100
                                                discount_percentage = float(discount_calc)  # Allow negative discounts

                                                if category == 'lotto-clubs' and row_count <= 5:
                                                    logger.info(f"[LOTTO-PRICE] Row {row_num}: cost={cost_value}, margin_75={margin_75_price:.2f}, rrp={rrp:.2f}, discount={discount_percentage:.2f}%")
                            except (ValueError, InvalidOperation, ZeroDivisionError) as e:
                                logger.warning(f"Row {row_num}: Price calculation error - {str(e)}")

                        # Get stock quantity from product (field name varies by model)
                        stock_quantity = 0
                        if product:
                            # WholesaleProduct uses 'quantity_available', others use 'stock_quantity'
                            if hasattr(product, 'quantity_available'):
                                stock_quantity = product.quantity_available or 0
                            elif hasattr(product, 'stock_quantity'):
                                stock_quantity = product.stock_quantity or 0

                        # Determine status based on product match, cost data, and pricing
                        status = 'error'  # Default to error
                        status_message = ''

                        if not product:
                            status = 'error'
                            status_message = 'Product not found in database'
                        elif cost_value == 0 or not cost_raw:
                            status = 'no_cost'
                            status_message = 'Missing cost data - cannot calculate prices'
                        elif discount_percentage is not None and discount_percentage < 0:
                            # Negative discount means Current Retail > 75% Margin Price
                            status = 'above_margin'
                            status_message = f'Current RRP (${rrp:.2f}) exceeds 75% margin price (${margin_75_price:.2f}) - Discount: {discount_percentage:.1f}%'
                        else:
                            status = 'valid'
                            status_message = 'Ready for price update'

                        # Build preview item with category-aware field access
                        try:
                            preview_item = {
                                'row_number': row_num,
                                'product_code': product_code,
                                'barcode': barcode,
                                'product_name': product_name,
                                'product_found': product is not None,
                                'match_method': match_method,
                                'status': status,
                                'status_message': status_message,
                                'database_product_name': product.name if product else None,
                                'cost': cost_raw,
                                'margin_75_price': margin_75_price,
                                'rrp': rrp,
                                'discount_percentage': discount_percentage,
                                'current_retail_nzd_incl': row.get(retail_col, '') if retail_col else '',
                                # Get current cost/margin from target (variation or product)
                                'current_cost_price': float(target.cost_price) if target and hasattr(target, 'cost_price') and target.cost_price else None,
                                'current_margin_75_price': float(target.margin_75_price) if target and hasattr(target, 'margin_75_price') and target.margin_75_price else None,
                                'stock_quantity': stock_quantity,  # Add stock info for display/debugging
                            }

                            # Include variation_id if matched to a variation
                            if variation:
                                preview_item['variation_id'] = variation.id
                                preview_item['variation_sku'] = getattr(variation, 'sku', None) or getattr(variation, 'sku_suffix', None)

                            # Add school_name for wholesale products
                            if category == 'wholesale-schools' and product:
                                preview_item['school_name'] = product.school.name if hasattr(product, 'school') else None

                            # Add current retail price from target using the correct field name
                            if target:
                                if variation:
                                    # Variations always use 'price' field
                                    current_price = getattr(target, 'price', None)
                                elif price_field:
                                    current_price = getattr(target, price_field, None)
                                else:
                                    current_price = None
                                preview_item['current_retail_price'] = float(current_price) if current_price else None
                            else:
                                preview_item['current_retail_price'] = None
                        except AttributeError as attr_e:
                            logger.error(f"Row {row_num}: AttributeError building preview_item - {str(attr_e)}", exc_info=True)
                            logger.error(f"Row {row_num}: product type: {type(product).__name__ if product else 'None'}")
                            logger.error(f"Row {row_num}: product attributes: {dir(product) if product else 'N/A'}")
                            raise  # Re-raise to be caught by outer exception handler

                        # Filter logic: Ignore products with BOTH stock=0 AND cost=0
                        # Include products if:
                        # - Product was found AND
                        # - NOT (stock=0 AND cost=0) - i.e., at least one is > 0
                        if product and not (stock_quantity == 0 and cost_value == 0):
                            preview_data.append(preview_item)
                            if status == 'valid':
                                valid_rows += 1

                    except Exception as e:
                        error_msg = f"Row {row_num}: Error processing - {str(e)}"
                        logger.error(f"{error_msg}\nTraceback: {traceback.format_exc()}", exc_info=True)
                        logger.error(f"Row {row_num} data: product_code='{product_code}', barcode='{barcode}', product_name='{product_name}'")
                        logger.error(f"Row {row_num} cost_raw='{cost_raw}', category='{category}'")
                        if product:
                            logger.error(f"Row {row_num} product found: {product.__class__.__name__}, id={product.id}, name='{product.name}'")
                            logger.error(f"Row {row_num} product attributes: {dir(product)}")
                        errors.append(error_msg)

            filtered_count = row_count - len(preview_data)
            csv_elapsed = (timezone.now() - csv_parse_start).total_seconds()
            total_elapsed = (timezone.now() - start_time).total_seconds()
            csv_rate = row_count / csv_elapsed if csv_elapsed > 0 else 0
            total_rate = row_count / total_elapsed if total_elapsed > 0 else 0

            logger.info(f"[LOTTO-SUMMARY] CSV processing complete: {row_count} rows processed, "
                       f"{valid_rows} valid products found, "
                       f"{filtered_count} filtered out (stock=0 & cost=0, or not found)")
            if category == 'lotto-clubs':
                logger.info(f"[LOTTO-SUMMARY] LOTTO preview data count: {len(preview_data)}")
                logger.info(f"[LOTTO-SUMMARY] LOTTO valid items: {valid_rows}")

            logger.info(f"[PERF-END] Phase: csv_processing | End: {timezone.now().isoformat()} | Total: {csv_elapsed:.2f}s | Rate: {csv_rate:.0f} items/s")
            logger.info(f"[PERF-END] Operation: wholesale_price_preview | End: {timezone.now().isoformat()} | Total: {total_elapsed:.2f}s | Success: {valid_rows} | Failed: {row_count - valid_rows} | Rate: {total_rate:.0f} items/s")

            # Log response size before returning
            logger.info(f"[RESPONSE] Returning {len(preview_data)} preview items to frontend")
            logger.info(f"[RESPONSE] Response size estimate: ~{len(str(preview_data))} characters")

            return JsonResponse({
                'success': True,
                'preview_data': preview_data,
                'category_filter': category,  # Include category so frontend can send it back in apply
                'summary': {
                    'total_rows': row_count,
                    'valid_products': valid_rows,
                    'invalid_products': row_count - valid_rows,
                    'errors': errors
                }
            })

        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                logger.debug(f"Temporary file cleaned up: {temp_file_path}")

    except Exception as e:
        logger.error(f"Price preview operation failed: {str(e)}", exc_info=True)
        logger.error(f"Full traceback:\n{traceback.format_exc()}")

        # Get context information
        context_info = {}
        try:
            context_info['category'] = category if 'category' in locals() else 'unknown'
            context_info['csv_file_name'] = csv_file.name if 'csv_file' in locals() else 'unknown'
            context_info['row_count'] = row_count if 'row_count' in locals() else 0
            context_info['valid_rows'] = valid_rows if 'valid_rows' in locals() else 0
        except:
            pass

        return JsonResponse({
            'success': False,
            'error': f'Preview operation failed: {str(e)}',
            'error_type': type(e).__name__,
            'traceback': traceback.format_exc(),
            'context': context_info
        }, status=500)
'''

# ============================================================================
# OLD EXCEL/CSV-BASED PRICE APPLY - COMMENTED OUT - Replaced with Cin7 API
# ============================================================================
'''
@csrf_exempt
@require_http_methods(["POST"])
def wholesale_price_apply(request):
    """
    Apply price changes to ALL valid items from preview data.
    Automatically processes items with status='valid', skipping items with
    status='above_margin', 'no_cost', or 'error'.
    Supports multiple product categories via ProductMatcherService.
    Enhanced with comprehensive logging to debug the 25/1701 update issue.

    TEMPORARY FIX (2025-10-10):
    - Disabled all price_logger calls due to threading lock hang issue
    - The PriceUpdateLogger singleton was blocking POST requests indefinitely
    - Using standard Django logger instead for debugging
    """
    import json
    from decimal import Decimal
    from django.db import transaction
    from django.utils import timezone
    from .models import WholesaleProduct
    from .services import ProductMatcherService
    from schools.utils.price_update_logger import price_logger

    logger = logging.getLogger(__name__)

    try:
        # Parse request data
        data = json.loads(request.body)
        all_items = data.get('preview_items', [])  # Changed from selected_items to preview_items
        backup_prices = data.get('backup_prices', True)
        category = data.get('category_filter', 'wholesale-schools')
        session_id = data.get('session_id', None)  # Get session ID from frontend

        start_time = timezone.now()
        logger.info(f"=== WHOLESALE PRICE APPLY STARTED ===")
        logger.info(f"[PERF-START] Operation: wholesale_price_apply | Start: {start_time.isoformat()} | Items: {len(all_items)}")
        logger.info(f"Category: {category}")
        logger.info(f"Total items received: {len(all_items)}")
        logger.info(f"Backup prices enabled: {backup_prices}")

        # Log to price update logger (before filtering valid items)
        # TEMPORARY FIX: Disabled due to threading lock hang issue
        # price_logger.log_start(len(all_items), category)

        # Filter for only valid items
        valid_items = [item for item in all_items if item.get('status') == 'valid']

        logger.info(f"[LOTTO-CATEGORY] Apply category: {category}")
        logger.info(f"[LOTTO-SUMMARY] Valid items to process: {len(valid_items)} out of {len(all_items)} total items")
        logger.info(f"[LOTTO-SUMMARY] Skipped items: {len(all_items) - len(valid_items)}")

        if category == 'lotto-clubs':
            logger.info(f"[LOTTO-SUMMARY] Processing LOTTO price updates")

        # Initialize product matcher service
        matcher = ProductMatcherService()
        category_info = matcher.get_category_info(category)
        price_field = matcher.get_price_field(category)
        logger.info(f"Category info: {category_info}")
        logger.info(f"Price field for updates: {price_field}")

        # ===== PERFORMANCE OPTIMIZATION: Pre-load variations with normalized indexes =====
        variations_by_key = {}  # Exact match
        variations_by_normalized_key = {}  # Normalized match (no spaces)

        if category == 'retail-schools':
            from schools.models_tus import TUSProductVariation
            variations = TUSProductVariation.objects.select_related('product').all()
            for variation in variations:
                if variation.sku:
                    exact_key = str(variation.sku).strip().upper()
                    variations_by_key[exact_key] = variation
                    normalized_key = variation.sku.replace(' ', '').upper()
                    variations_by_normalized_key[normalized_key] = variation
        elif category == 'sas-clubs':
            from clubs.models_sas import SASProductVariation
            variations = SASProductVariation.objects.select_related('product').all()
            for variation in variations:
                if variation.sku_suffix:
                    exact_key = str(variation.sku_suffix).strip().upper()
                    variations_by_key[exact_key] = variation
                    normalized_key = variation.sku_suffix.replace(' ', '').upper()
                    variations_by_normalized_key[normalized_key] = variation
        elif category == 'lotto-clubs':
            from clubs.models_lotto import LottoProductVariation
            variations = LottoProductVariation.objects.select_related('product').all()
            for variation in variations:
                if variation.sku_suffix:
                    exact_key = str(variation.sku_suffix).strip().upper()
                    variations_by_key[exact_key] = variation
                    normalized_key = variation.sku_suffix.replace(' ', '').upper()
                    variations_by_normalized_key[normalized_key] = variation

        logger.info(f"Pre-loaded {len(variations_by_key)} exact and {len(variations_by_normalized_key)} normalized variation lookups")

        if not valid_items:
            logger.warning("No valid items found for update")
            return JsonResponse({
                'success': False,
                'error': 'No valid items found for update. Only items with status="valid" are processed.'
            })

        # Log first few items for structure verification
        logger.info("=== SAMPLE DATA STRUCTURE ===")
        for i, item in enumerate(valid_items[:3]):
            logger.info(f"Item {i+1} structure: {json.dumps(item, indent=2)}")

        # Log expected vs actual field mappings
        logger.info("=== FIELD MAPPING ANALYSIS ===")
        if valid_items:
            first_item = valid_items[0]
            expected_fields = ['product_code', 'barcode', 'cost', 'margin_75_price', 'discount_percentage', 'current_retail_nzd_incl']
            available_fields = list(first_item.keys())

            logger.info(f"Expected price update fields: {expected_fields}")
            logger.info(f"Available fields in data: {available_fields}")

            missing_fields = [field for field in expected_fields if field not in available_fields]
            extra_fields = [field for field in available_fields if field not in expected_fields]

            if missing_fields:
                logger.warning(f"Missing expected fields: {missing_fields}")
            if extra_fields:
                logger.info(f"Extra fields available: {extra_fields}")

            # Check for potential field name variations
            field_variations = {
                'product_code': ['sku', 'product_sku', 'cin7_sku', 'code'],
                'barcode': ['cin7_barcode', 'product_barcode'],
                'cost': ['cost_price', 'cost_nzd', 'unit_cost'],
                'margin_75_price': ['margin_price', '75_margin_price', 'margin75'],
                'current_retail_nzd_incl': ['retail_price', 'retail_nzd', 'selling_price']
            }

            for expected_field, variations in field_variations.items():
                if expected_field not in available_fields:
                    found_variations = [var for var in variations if var in available_fields]
                    if found_variations:
                        logger.warning(f"Field '{expected_field}' not found, but similar fields available: {found_variations}")

        results = {
            'successful_updates': 0,
            'failed_updates': 0,
            'errors': [],
            'updated_products': [],
            'not_found_products': [],
            'skipped_products': []
        }

        # Track detailed statistics
        processed_count = 0
        found_by_sku_count = 0
        found_by_barcode_count = 0
        not_found_count = 0
        update_failed_count = 0

        # Add database diagnostics before processing
        logger.info("=== DATABASE DIAGNOSTICS ===")

        # Get model class for diagnostics
        model_class = matcher._get_model_class(category)
        if model_class:
            sku_field = matcher.get_sku_field(category)
            barcode_field = matcher.get_barcode_field(category)

            total_products = model_class.objects.count()
            products_with_sku = model_class.objects.exclude(**{f"{sku_field}": ''}).exclude(**{f"{sku_field}__isnull": True}).count() if sku_field else 0
            products_with_barcode = model_class.objects.exclude(**{f"{barcode_field}": ''}).exclude(**{f"{barcode_field}__isnull": True}).count() if barcode_field else 0

            logger.info(f"Total {model_class.__name__} records: {total_products}")
            logger.info(f"Products with SKU: {products_with_sku}")
            logger.info(f"Products with barcode: {products_with_barcode}")

            # Sample some SKUs and barcodes for comparison
            if sku_field:
                sample_skus = list(model_class.objects.exclude(**{f"{sku_field}": ''}).exclude(**{f"{sku_field}__isnull": True}).values_list(sku_field, flat=True)[:5])
                logger.info(f"Sample SKUs in database: {sample_skus}")

            if barcode_field:
                sample_barcodes = list(model_class.objects.exclude(**{f"{barcode_field}": ''}).exclude(**{f"{barcode_field}__isnull": True}).values_list(barcode_field, flat=True)[:5])
                logger.info(f"Sample barcodes in database: {sample_barcodes}")

        # ===== BULK UPDATE OPTIMIZATION: Use BulkPriceUpdater for large datasets =====
        # Threshold: 1000+ items use bulk operations (288x faster)
        BULK_UPDATE_THRESHOLD = 1000
        use_bulk_update = len(valid_items) >= BULK_UPDATE_THRESHOLD

        if use_bulk_update:
            logger.info(f"=== USING BULK UPDATE OPTIMIZATION ===")
            logger.info(f"[PERF-DECISION] Strategy: bulk_update | Items: {len(valid_items)} | Threshold: {BULK_UPDATE_THRESHOLD}")
            logger.info(f"Items to process: {len(valid_items)} (threshold: {BULK_UPDATE_THRESHOLD})")
            logger.info(f"Expected performance: ~{len(valid_items)/3200:.1f}s (vs ~{len(valid_items)*0.5:.1f}s sequential)")
            logger.info(f"[BULK-UPDATE] Starting bulk price update for {len(valid_items)} items...")

            try:
                from schools.services.bulk_price_updater import BulkPriceUpdater

                # Use session ID from frontend or generate one
                if not session_id:
                    import uuid
                    session_id = str(uuid.uuid4())

                logger.info(f"[PROGRESS] Using session ID for tracking: {session_id}")

                # Initialize bulk updater with session ID
                bulk_updater = BulkPriceUpdater(category, matcher, session_id=session_id)

                # Execute bulk update
                bulk_results = bulk_updater.bulk_update_prices(valid_items, backup_prices)

                # Map bulk results to expected format
                results = bulk_results
                total_elapsed = (timezone.now() - start_time).total_seconds()
                throughput = len(valid_items) / total_elapsed if total_elapsed > 0 else 0

                logger.info(f"[BULK-UPDATE] Completed: {results['successful_updates']} successful, "
                           f"{results['failed_updates']} failed, {len(results['errors'])} errors")
                logger.info(f"[PERF-END] Operation: wholesale_price_apply | End: {timezone.now().isoformat()} | Total: {total_elapsed:.2f}s | Success: {results['successful_updates']} | Failed: {results['failed_updates']} | Rate: {throughput:.0f} items/s")

                # Return early with bulk results including session_id for progress tracking
                return JsonResponse({
                    'success': True,
                    'session_id': session_id,  # For progress polling
                    'message': f"Bulk updated {results['successful_updates']} products successfully out of {len(valid_items)} valid items (total items: {len(all_items)})",
                    'summary': {
                        'total_items': len(all_items),
                        'valid_items': len(valid_items),
                        'successful_updates': results['successful_updates'],
                        'failed_updates': results['failed_updates'],
                        'errors': results['errors'],
                        'updated_products': results['updated_products'][:10],  # First 10 for preview
                        'method': 'bulk_update',
                        'performance': f"{len(valid_items)/3200:.1f}s estimated"
                    },
                    'results': results  # Include full results for backwards compatibility
                })

            except ImportError as e:
                logger.warning(f"BulkPriceUpdater not available, falling back to sequential: {str(e)}")
                use_bulk_update = False
            except Exception as e:
                logger.error(f"Bulk update failed, falling back to sequential: {str(e)}", exc_info=True)
                use_bulk_update = False

        # ===== SEQUENTIAL UPDATE: Original logic for small datasets or fallback =====
        # Process each selected item
        sequential_start = timezone.now()
        logger.info("=== PROCESSING ITEMS (SEQUENTIAL) ===")
        logger.info(f"[PERF-DECISION] Strategy: sequential | Items: {len(valid_items)}")
        logger.info(f"[PERF-START] Phase: sequential_update | Start: {sequential_start.isoformat()} | Items: {len(valid_items)}")
        logger.info(f"Items to process: {len(valid_items)}")
        logger.info("Starting database transaction...")

        try:
            with transaction.atomic():
                for index, item in enumerate(valid_items, 1):
                    processed_count += 1
                    product_name = item.get('product_name', 'Unknown')
                    product_code = item.get('product_code', '')
                    barcode = item.get('barcode', '')

                    logger.info(f"Processing item {index}/{len(valid_items)}: {product_name}")
                    logger.info(f"  - Product code: {product_code}")
                    logger.info(f"  - Barcode: {barcode}")

                    try:
                        # Use ProductMatcherService to find the product
                        product_code_clean = str(product_code).strip() if product_code else ''
                        barcode_clean = str(barcode).strip() if barcode else ''

                        logger.debug(f"  - Searching for product: SKU='{product_code_clean}', Barcode='{barcode_clean}'")

                        # ===== FAST PATH: O(1) hash map lookup =====
                        product = None
                        search_method = None
                        variation = None

                        # Try exact variation match first
                        if product_code_clean:
                            lookup_key = product_code_clean.upper()
                            if lookup_key in variations_by_key:
                                variation = variations_by_key[lookup_key]
                                product = variation.product
                                search_method = 'sku_suffix_exact_cached'
                            else:
                                # Try normalized match (no spaces)
                                normalized_key = product_code_clean.replace(' ', '').upper()
                                if normalized_key in variations_by_normalized_key:
                                    variation = variations_by_normalized_key[normalized_key]
                                    product = variation.product
                                    search_method = 'sku_suffix_normalized_cached'

                        # ===== SLOW PATH: Fallback to ProductMatcherService =====
                        if not product:
                            product, search_method, variation = matcher.find_product_with_variation(
                                category, product_code_clean, barcode_clean
                            )

                        # Determine target object: use variation if found, otherwise use product
                        target = variation if variation else product

                        # Update statistics based on match method
                        if product:
                            if 'sku' in search_method:
                                found_by_sku_count += 1
                            elif 'barcode' in search_method:
                                found_by_barcode_count += 1

                            if variation:
                                logger.info(f"  ✅ Variation found by {search_method}: {product.name} - Variation ID {variation.id}")
                                if category == 'lotto-clubs' and index <= 10:
                                    logger.info(f"[LOTTO-MATCH] Item {index}: Found LOTTO variation - SKU={product_code_clean}, Variation ID={variation.id}")
                            else:
                                logger.info(f"  ✅ Product found by {search_method}: {product.name} (ID: {product.id})")
                                if category == 'lotto-clubs' and index <= 10:
                                    logger.info(f"[LOTTO-MATCH] Item {index}: Found LOTTO product (no variation) - SKU={product_code_clean}")
                        else:
                            logger.debug(f"  - Product not found with SKU or barcode")

                        if not product:
                            not_found_count += 1
                            error_msg = f"Product not found - Name: {product_name}, SKU: {product_code}, Barcode: {barcode}"
                            logger.warning(f"  ❌ {error_msg}")
                            results['failed_updates'] += 1
                            results['errors'].append(error_msg)
                            results['not_found_products'].append({
                                'product_name': product_name,
                                'product_code': product_code,
                                'barcode': barcode
                            })
                            # Log no match
                            tried_fields = []
                            if product_code_clean:
                                tried_fields.append('sku' if not variations_by_key else 'sku_suffix')
                            if barcode_clean:
                                tried_fields.append('barcode')
                            # price_logger.log_no_match(index, product_code, barcode, tried_fields)
                            continue

                        # Log successful match
                        target_type = "Variation" if variation else "Product"
                        target_id = variation.id if variation else product.id
                        # price_logger.log_match(
                        #     index,
                        #     product_code_clean or barcode_clean,
                        #     target_type,
                        #     target_id,
                        #     search_method
                        # )

                        # Log current target state (variation or product)
                        logger.info(f"  - Current {target_type} state:")
                        logger.info(f"    * Cost price: {getattr(target, 'cost_price', 'N/A')}")
                        logger.info(f"    * Margin 75% price: {getattr(target, 'margin_75_price', 'N/A')}")
                        # For variations, use 'price' field
                        if variation:
                            logger.info(f"    * price: {getattr(target, 'price', 'N/A')}")
                        else:
                            logger.info(f"    * {price_field}: {getattr(target, price_field, 'N/A')}")
                        logger.info(f"    * Discount percentage: {getattr(target, 'discount_percentage', 'N/A')}")

                        # Create backup if requested
                        backup_data = {}
                        if backup_prices:
                            cost_price = getattr(target, 'cost_price', None)
                            margin_75 = getattr(target, 'margin_75_price', None)
                            # For variations, use 'price' field; for products, use price_field
                            if variation:
                                current_price = getattr(target, 'price', None)
                            else:
                                current_price = getattr(target, price_field, None) if price_field else None
                            discount_pct = getattr(target, 'discount_percentage', None)

                            backup_data = {
                                'original_cost_price': float(cost_price) if cost_price else None,
                                'original_margin_75_price': float(margin_75) if margin_75 else None,
                                'original_retail_price': float(current_price) if current_price else None,
                                'original_discount_percentage': float(discount_pct) if discount_pct else None,
                            }
                            logger.debug(f"  - Backup created: {backup_data}")

                        # Track what fields will be updated
                        updates_to_apply = {}

                        # Update target pricing fields (variation or product)
                        if item.get('cost'):
                            new_cost = Decimal(str(item['cost']))
                            updates_to_apply['cost_price'] = new_cost
                            target.cost_price = new_cost
                            logger.info(f"  - Updating cost price: {new_cost}")
                            if category == 'lotto-clubs' and index <= 10:
                                logger.info(f"[LOTTO-UPDATE] Item {index}: Setting cost_price={new_cost}")

                        if item.get('margin_75_price'):
                            new_margin = Decimal(str(item['margin_75_price']))
                            updates_to_apply['margin_75_price'] = new_margin
                            target.margin_75_price = new_margin
                            logger.info(f"  - Updating margin 75% price: {new_margin}")
                            if category == 'lotto-clubs' and index <= 10:
                                logger.info(f"[LOTTO-UPDATE] Item {index}: Setting margin_75_price={new_margin}")

                        if item.get('discount_percentage'):
                            new_discount = Decimal(str(item['discount_percentage']))
                            if hasattr(target, 'discount_percentage'):
                                updates_to_apply['discount_percentage'] = new_discount
                                target.discount_percentage = new_discount
                                logger.info(f"  - Updating discount percentage: {new_discount}")
                                if category == 'lotto-clubs' and index <= 10:
                                    logger.info(f"[LOTTO-UPDATE] Item {index}: Setting discount_percentage={new_discount}%")
                            else:
                                logger.warning(f"  - Target model doesn't have discount_percentage field")

                        # Update retail price if provided
                        if item.get('current_retail_nzd_incl'):
                            new_retail = Decimal(str(item['current_retail_nzd_incl']))
                            # For variations, always update 'price' field
                            if variation:
                                updates_to_apply['price'] = new_retail
                                target.price = new_retail
                                logger.info(f"  - Updating variation price: {new_retail}")
                                if category == 'lotto-clubs' and index <= 10:
                                    logger.info(f"[LOTTO-UPDATE] Item {index}: Setting variation.price={new_retail}")
                            elif price_field:
                                updates_to_apply[price_field] = new_retail
                                setattr(target, price_field, new_retail)
                                logger.info(f"  - Updating {price_field}: {new_retail}")
                                if category == 'lotto-clubs' and index <= 10:
                                    logger.info(f"[LOTTO-UPDATE] Item {index}: Setting {price_field}={new_retail}")

                        if not updates_to_apply:
                            logger.warning(f"  ⚠️ No price fields to update for {product_name}")
                            logger.warning(f"  - Available item fields: {list(item.keys())}")
                            results['skipped_products'].append({
                                'product_name': product_name,
                                'reason': 'No price fields provided',
                                'available_fields': list(item.keys())
                            })
                            continue

                        # Update last_price_update timestamp on target
                        if hasattr(target, 'last_price_update'):
                            target.last_price_update = timezone.now()
                            update_fields = list(updates_to_apply.keys()) + ['last_price_update']
                        else:
                            update_fields = list(updates_to_apply.keys())

                        # Log price update with before/after values
                        old_cost = backup_data.get('original_cost_price')
                        old_margin = backup_data.get('original_margin_75_price')
                        old_retail = backup_data.get('original_retail_price')

                        new_cost = updates_to_apply.get('cost_price')
                        new_margin = updates_to_apply.get('margin_75_price')
                        new_retail = updates_to_apply.get('price') or updates_to_apply.get(price_field)

                        # price_logger.log_update(
                        #     target_type,
                        #     target_id,
                        #     Decimal(str(old_cost)) if old_cost else None,
                        #     new_cost,
                        #     Decimal(str(old_margin)) if old_margin else None,
                        #     new_margin,
                        #     Decimal(str(old_retail)) if old_retail else None,
                        #     new_retail
                        # )

                        # Save target with explicit field list
                        logger.debug(f"  - Saving {target_type} with update_fields: {update_fields}")

                        try:
                            target.save(update_fields=update_fields)
                            logger.debug(f"  - Database save successful")
                            if category == 'lotto-clubs' and index <= 10:
                                logger.info(f"[LOTTO-UPDATE] Item {index}: Database save SUCCESSFUL - fields={update_fields}")
                        except Exception as save_error:
                            logger.error(f"  - Database save failed: {save_error}")
                            if category == 'lotto-clubs':
                                logger.error(f"[LOTTO-UPDATE] Item {index}: Database save FAILED - {save_error}")
                            raise save_error

                        results['successful_updates'] += 1
                        if category == 'lotto-clubs' and index <= 10:
                            logger.info(f"[LOTTO-UPDATE] Item {index}: Update count incremented - total={results['successful_updates']}")

                        # Build updated info with category-aware field access
                        updated_info = {
                            'product_name': product.name,
                            'product_id': product.id,
                            'search_method': search_method,
                            'updated_target': target_type,  # Track whether variation or product was updated
                            'updates_applied': {k: float(v) for k, v in updates_to_apply.items()},
                            'backup_data': backup_data,
                            'new_cost_price': float(getattr(target, 'cost_price', 0)) if hasattr(target, 'cost_price') and getattr(target, 'cost_price') else None,
                            'new_margin_price': float(getattr(target, 'margin_75_price', 0)) if hasattr(target, 'margin_75_price') and getattr(target, 'margin_75_price') else None,
                        }

                        # Add variation_id if variation was updated
                        if variation:
                            updated_info['variation_id'] = variation.id
                            updated_info['variation_sku'] = getattr(variation, 'sku', None) or getattr(variation, 'sku_suffix', None)

                        # Add school_name for wholesale products
                        if category == 'wholesale-schools' and hasattr(product, 'school'):
                            updated_info['school_name'] = product.school.name

                        results['updated_products'].append(updated_info)

                        if variation:
                            logger.info(f"  ✅ Successfully updated variation for {product.name}")
                        else:
                            logger.info(f"  ✅ Successfully updated {product.name}")

                    except Exception as e:
                        update_failed_count += 1
                        error_msg = f"Failed to update {product_name}: {str(e)}"
                        logger.error(f"  ❌ {error_msg}", exc_info=True)
                        results['failed_updates'] += 1
                        results['errors'].append(error_msg)
                        # Log error to price update logger
                        # price_logger.log_error(index, product_code, str(e))

            logger.info("Database transaction completed successfully")

        except Exception as transaction_error:
            logger.error(f"Database transaction failed: {transaction_error}", exc_info=True)
            raise transaction_error

        # Log comprehensive summary
        sequential_elapsed = (timezone.now() - sequential_start).total_seconds()
        total_elapsed = (timezone.now() - start_time).total_seconds()
        throughput = processed_count / total_elapsed if total_elapsed > 0 else 0

        logger.info("=== WHOLESALE PRICE APPLY SUMMARY ===")
        logger.info(f"[LOTTO-SUMMARY] Total items processed: {processed_count}")
        logger.info(f"[LOTTO-SUMMARY] Successfully updated: {results['successful_updates']}")
        logger.info(f"[LOTTO-SUMMARY] Failed updates: {results['failed_updates']}")
        logger.info(f"[LOTTO-SUMMARY] Products found by SKU: {found_by_sku_count}")
        logger.info(f"[LOTTO-SUMMARY] Products found by barcode: {found_by_barcode_count}")
        logger.info(f"[LOTTO-SUMMARY] Products not found: {not_found_count}")
        logger.info(f"[LOTTO-SUMMARY] Update failures: {update_failed_count}")
        logger.info(f"[PERF-END] Phase: sequential_update | End: {timezone.now().isoformat()} | Total: {sequential_elapsed:.2f}s")
        logger.info(f"[PERF-END] Operation: wholesale_price_apply | End: {timezone.now().isoformat()} | Total: {total_elapsed:.2f}s | Success: {results['successful_updates']} | Failed: {results['failed_updates']} | Rate: {throughput:.0f} items/s")

        if category == 'lotto-clubs':
            logger.info(f"[LOTTO-SUMMARY] ========== LOTTO FINAL STATS ==========")
            logger.info(f"[LOTTO-SUMMARY] Total LOTTO items: {len(all_items)}")
            logger.info(f"[LOTTO-SUMMARY] Valid LOTTO items: {len(valid_items)}")
            logger.info(f"[LOTTO-SUMMARY] LOTTO updates applied: {results['successful_updates']}")
            logger.info(f"[LOTTO-SUMMARY] LOTTO update failures: {results['failed_updates']}")
            logger.info(f"[LOTTO-SUMMARY] Success rate: {(results['successful_updates']/len(valid_items)*100):.1f}%" if len(valid_items) > 0 else "[LOTTO-SUMMARY] Success rate: N/A")

        if results['errors']:
            logger.warning("=== ERRORS ENCOUNTERED ===")
            for error in results['errors']:
                logger.warning(f"  - {error}")

        # Log performance and summary to price update logger
        # price_logger.log_performance('sequential_update', sequential_elapsed, processed_count)
        # price_logger.log_summary({
        #     'total_items': len(valid_items),
        #     'matched': results['successful_updates'],
        #     'no_match': not_found_count,
        #     'errors': len(results['errors']),
        #     'duration_seconds': total_elapsed,
        #     'category': category
        # })

        return JsonResponse({
            'success': True,
            'results': results,
            'message': f"Updated {results['successful_updates']} products successfully out of {len(valid_items)} valid items (total items: {len(all_items)})",
            'summary': {
                'total_received': len(all_items),
                'valid_items': len(valid_items),
                'skipped_items': len(all_items) - len(valid_items),
                'total_processed': processed_count,
                'found_by_sku': found_by_sku_count,
                'found_by_barcode': found_by_barcode_count,
                'not_found': not_found_count,
                'update_failures': update_failed_count
            }
        })

    except Exception as e:
        logger.error(f"Price apply operation failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Apply operation failed: {str(e)}'
        }, status=500)
'''

# ============================================================================
# OLD EXCEL/CSV-BASED PRICE UPDATE - COMMENTED OUT - Replaced with Cin7 API
# ============================================================================
# def wholesale_price_update_settings(request):
#     """
#     Wholesale price update settings page
#     """
#     # Log settings access
#     try:
#         from authentication.models import AuditLog
#         user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
#         AuditLog.log_action(
#             user=user,
#             action_type='wholesale_price_settings_accessed',
#             description="Accessed wholesale price update settings",
#             request=request
#         )
#     except Exception as e:
#         logger.error(f"Failed to audit settings access: {str(e)}")
#
#     context = {
#         'page_title': 'Wholesale Price Update Settings',
#     }
#     return render(request, 'schools/wholesale/price_update_settings.html', context)


# @csrf_exempt
# def wholesale_price_progress(request, session_id):
#     """
#     Poll endpoint for real-time price update progress.
#     Returns current progress from Django cache.
#     """
#     from django.core.cache import cache
#
#     if request.method != 'GET':
#         return JsonResponse({'error': 'Method not allowed'}, status=405)
#
#     # Get progress from cache
#     cache_key = f"price_update_progress_{session_id}"
#     progress_data = cache.get(cache_key)
#
#     if progress_data is None:
#         # Return pending status instead of 404 to avoid console errors
#         # The frontend polls before the backend initializes progress data
#         return JsonResponse({
#             'status': 'pending',
#             'message': 'Waiting for price update to start...',
#             'progress': {
#                 'current': 0,
#                 'total': 0,
#                 'percentage': 0,
#                 'phase': 'waiting',
#                 'message': 'Initializing...'
#             }
#         })
#
#     return JsonResponse({
#         'status': 'success',
#         'progress': progress_data
#     })


# ============================================================================
# PRICE MANAGEMENT HUB
# ============================================================================

def price_management_hub(request):
    """
    Price management hub page - choose between Cin7 sync or CSV upload
    """
    return render(request, 'schools/wholesale/price_management_hub.html')


# ============================================================================
# CIN7 PRICE UPDATE VIEWS
# ============================================================================

@csrf_exempt
@require_http_methods(["GET"])
def cin7_price_update_settings(request):
    """
    Cin7 price update settings page
    Allows user to select price type and trigger price fetch from Cin7 API
    """
    try:
        from authentication.models import AuditLog
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        AuditLog.log_action(
            user=user,
            action_type='cin7_price_settings_accessed',
            description="Accessed Cin7 price update settings",
            request=request
        )
    except Exception as e:
        logger.error(f"Failed to audit settings access: {str(e)}")

    context = {
        'page_title': 'Cin7 Price Update Settings',
        'price_types': ['TUS', 'LOTTO', 'SAS', 'Wholesale'],
    }
    return render(request, 'schools/wholesale/cin7_price_update_settings.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def cin7_price_fetch(request):
    """
    Stage 1: Fetch products from Cin7 API and save to database

    This endpoint fetches products from Cin7 and stores them in the Cin7Product table.
    No matching or price updates happen at this stage.
    """
    import json
    import uuid
    from django.core.cache import cache
    from schools.services.cin7_api_service import Cin7ApiService
    from schools.models import Cin7Product

    logger = logging.getLogger(__name__)
    start_time = timezone.now()

    try:
        # Parse request
        data = json.loads(request.body)
        price_type = data.get('price_type', 'Wholesale')
        session_id = str(uuid.uuid4())

        logger.info(f"=== CIN7 PRICE FETCH STARTED (Stage 1) ===")
        logger.info(f"Price type: {price_type}")
        logger.info(f"Session ID: {session_id}")

        # Clear old Cin7Product records to ensure fresh data
        old_count = Cin7Product.objects.count()
        if old_count > 0:
            logger.info(f"Clearing {old_count} old Cin7Product records...")
            Cin7Product.objects.all().delete()
            logger.info(f"✓ Cleared {old_count} old records")

        # Initialize Cin7 API service
        cin7_service = Cin7ApiService()

        # Test connection
        if not cin7_service.test_connection():
            return JsonResponse({
                'success': False,
                'error': 'Failed to connect to Cin7 API. Check credentials in .env file.'
            }, status=500)

        # Progress callback
        def update_progress(current, total, message):
            cache_key = f"cin7_price_update_progress_{session_id}"
            cache.set(cache_key, {
                'current': current,
                'total': total,
                'percentage': int((current / total * 100)) if total > 0 else 0,
                'phase': 'fetching',
                'message': message,
                'timestamp': timezone.now().isoformat()
            }, timeout=300)

        # Fetch all products from Cin7
        update_progress(0, 100, "Initializing Cin7 connection...")
        products, fetched, total = cin7_service.fetch_all_products(price_type, update_progress)

        logger.info(f"Fetched {fetched} products from Cin7")

        # Save to database in bulk
        update_progress(0, len(products), "Saving to database...")

        cin7_products = []
        skipped_no_id = 0
        skipped_no_options = 0
        skipped_bs_products = 0
        total_options = 0

        for index, cin7_product in enumerate(products, 1):
            if index % 500 == 0:
                update_progress(index, len(products), f"Saving {index}/{len(products)}...")

            # Extract all product options (variants)
            product_options = cin7_service.extract_product_options(cin7_product)

            if not product_options:
                skipped_no_options += 1
                continue

            # Create a Cin7Product record for each variant
            for option_data in product_options:
                # Skip options without cin7_id (required field)
                if not option_data.get('cin7_id'):
                    logger.warning(f"Skipping option without cin7_id: {option_data.get('sku', 'unknown')}")
                    skipped_no_id += 1
                    continue

                # Skip products where code or style_code starts with 'BS'
                sku = option_data.get('sku') or ''
                style_code = option_data.get('style_code') or ''
                if sku.upper().startswith('BS') or style_code.upper().startswith('BS'):
                    skipped_bs_products += 1
                    continue

                # Calculate margin and discount with correct formula
                cost = option_data.get('cost')
                rrp = option_data.get('current_retail_nzd_incl')
                margin_75 = None
                discount_pct = None

                if cost and cost > 0:
                    margin_75 = cost / Decimal('0.25')  # 75% margin price

                    # Calculate discount: (Margin - RRP) / Margin * 100
                    if rrp and rrp > 0:
                        discount_pct = ((margin_75 - rrp) / margin_75) * 100

                cin7_products.append(Cin7Product(
                    cin7_id=option_data.get('cin7_id'),
                    code=option_data.get('sku') or '',
                    style_code=option_data.get('style_code') or '',
                    barcode=option_data.get('barcode') or '',
                    name=option_data.get('product_name') or '',
                    category=option_data.get('category') or '',
                    brand=option_data.get('brand') or '',
                    cost_nzd=cost,
                    retail_price=rrp,
                    margin_75_price=margin_75,  # Save calculated 75% margin price
                    discount_percentage=discount_pct,  # Save calculated discount % with +/- sign
                    stock_available=option_data.get('stock_available'),
                    price_type=price_type,
                    fetch_session_id=session_id,
                    raw_data=cin7_product  # Store parent product JSON
                ))
                total_options += 1

        # Bulk create (much faster than individual saves)
        logger.info(f"Bulk creating {len(cin7_products)} Cin7Product records...")
        Cin7Product.objects.bulk_create(cin7_products, batch_size=500)

        elapsed = (timezone.now() - start_time).total_seconds()

        logger.info(f"=== CIN7 PRICE FETCH COMPLETE (Stage 1) ===")
        logger.info(f"Total parent products: {len(products)}")
        logger.info(f"Total product variants: {total_options}")
        logger.info(f"Saved to database: {len(cin7_products)}")
        logger.info(f"Skipped (no options): {skipped_no_options}")
        logger.info(f"Skipped (starts with BS): {skipped_bs_products}")
        logger.info(f"Skipped (no ID): {skipped_no_id}")
        logger.info(f"Duration: {elapsed:.2f}s")

        # Audit log
        try:
            from authentication.models import AuditLog
            user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
            AuditLog.log_action(
                user=user,
                action_type='cin7_data_fetched',
                description=f"Fetched {len(products)} products from Cin7 for {price_type} (session: {session_id})",
                request=request
            )
        except Exception as e:
            logger.error(f"Failed to audit fetch: {str(e)}")

        return JsonResponse({
            'success': True,
            'session_id': session_id,
            'summary': {
                'total_fetched': len(products),
                'total_variants': total_options,
                'saved_to_db': len(cin7_products),
                'skipped_no_options': skipped_no_options,
                'skipped_bs_products': skipped_bs_products,
                'skipped_no_id': skipped_no_id,
                'duration_seconds': elapsed,
                'price_type': price_type
            }
        })

    except Exception as e:
        logger.error(f"Cin7 price fetch failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Price fetch failed: {str(e)}'
        }, status=500)
@csrf_exempt
@require_http_methods(["POST"])
def cin7_match_products(request):
    """
    Stage 2: Match Cin7 products from database with local products

    Uses Task agents for parallel processing of product matching.
    Splits products into batches and processes them concurrently.
    """
    import json
    from django.core.cache import cache
    from schools.services import ProductMatcherService
    from schools.models import Cin7Product

    logger = logging.getLogger(__name__)
    start_time = timezone.now()

    def update_progress(percentage, message):
        """Update progress in cache"""
        cache_key = f"cin7_price_update_progress_{session_id}"
        cache.set(cache_key, {
            'percentage': percentage,
            'message': message,
            'stage': 'matching'
        }, timeout=3600)

    try:
        # Parse request
        data = json.loads(request.body)
        session_id = data.get('session_id')
        price_type = data.get('price_type', 'Wholesale')
        reset_only = data.get('reset_only', False)

        if not session_id:
            return JsonResponse({
                'success': False,
                'error': 'session_id is required'
            }, status=400)

        # Handle reset request
        if reset_only:
            logger.info("Resetting all Cin7Product matches...")
            reset_count = Cin7Product.objects.filter(matched=True).update(
                matched=False,
                match_method='',  # Use empty string instead of None
                matched_product_id=None,
                matched_variation_id=None
            )
            logger.info(f"Reset {reset_count} matched products")
            return JsonResponse({
                'success': True,
                'reset_count': reset_count
            })

        logger.info(f"=== CIN7 MATCHING STARTED ===")
        logger.info(f"Session ID: {session_id}")
        logger.info(f"Price type: {price_type}")

        update_progress(0, "Loading Cin7 products from database...")

        # Load Cin7Product records
        # If session_id starts with 'match-', this is standalone matching - match ALL unmatched products
        # Otherwise, match only products from this fetch session
        if session_id.startswith('match-'):
            logger.info("Standalone matching mode - processing all unmatched products")
            cin7_products = Cin7Product.objects.filter(matched=False).order_by('id')
        else:
            logger.info(f"Session-based matching mode - processing session {session_id}")
            cin7_products = Cin7Product.objects.filter(
                fetch_session_id=session_id,
                matched=False
            ).order_by('id')

        total_products = cin7_products.count()
        logger.info(f"Total products to match: {total_products}")

        if total_products == 0:
            return JsonResponse({
                'success': False,
                'error': 'No unmatched products found'
            }, status=404)

        # Map price type to category
        category_map = {
            'TUS': 'retail-schools',
            'LOTTO': 'lotto-clubs',
            'SAS': 'sas-clubs',
            'Wholesale': 'wholesale-schools'
        }
        category = category_map.get(price_type, 'wholesale-schools')

        logger.info(f"Price type: {price_type} → Category: {category}")

        # Initialize matcher
        matcher = ProductMatcherService()

        # PRE-LOAD ALL PRODUCTS AND VARIATIONS INTO MEMORY FOR FAST LOOKUPS
        logger.info(f"Pre-loading {category} products and variations into memory...")
        update_progress(5, f"Loading {price_type} product database into memory...")

        # Build lookup dictionaries for products
        # Key format: normalized code -> (product, match_type)
        product_sku_map = {}  # cin7_sku exact
        product_sku_iexact_map = {}  # cin7_sku case-insensitive
        product_barcode_map = {}  # cin7_barcode exact
        product_barcode_iexact_map = {}  # cin7_barcode case-insensitive

        # Build lookup dictionaries for variations
        # Key format: normalized code -> (variation, product, match_type)
        variation_sku_map = {}  # cin7_sku exact
        variation_sku_iexact_map = {}  # cin7_sku case-insensitive
        variation_barcode_map = {}  # cin7_barcode exact (for style_code fallback)
        variation_barcode_iexact_map = {}  # cin7_barcode case-insensitive

        # Load products and variations based on category
        if category == 'retail-schools':
            from schools.models_tus import TUSProduct, TUSProductVariation

            # Load all TUS products
            all_products = TUSProduct.objects.all()
            for product in all_products:
                # SKU mappings (TUS uses 'sku', not 'cin7_sku')
                if product.sku:
                    product_sku_map[product.sku] = product
                    product_sku_iexact_map[product.sku.upper()] = product

                # Barcode mappings (TUS uses 'barcode', not 'cin7_barcode')
                if product.barcode:
                    product_barcode_map[product.barcode] = product
                    product_barcode_iexact_map[product.barcode.upper()] = product

            logger.info(f"Loaded {len(all_products)} TUS products into memory")

            # Load all TUS variations
            all_variations = TUSProductVariation.objects.all().select_related('product')
            for variation in all_variations:
                # SKU mappings (TUS uses 'sku', not 'cin7_sku')
                if variation.sku:
                    variation_sku_map[variation.sku] = (variation, variation.product)
                    variation_sku_iexact_map[variation.sku.upper()] = (variation, variation.product)

            logger.info(f"Loaded {len(all_variations)} TUS variations into memory")

        elif category == 'sas-clubs':
            from clubs.models_sas import SASProduct, SASProductVariation

            # Load all SAS products
            all_products = SASProduct.objects.all()
            for product in all_products:
                # SKU mappings (SAS uses 'sku', not 'cin7_sku')
                if product.sku:
                    product_sku_map[product.sku] = product
                    product_sku_iexact_map[product.sku.upper()] = product

                # Barcode mappings (SAS uses 'barcode', not 'cin7_barcode')
                if product.barcode:
                    product_barcode_map[product.barcode] = product
                    product_barcode_iexact_map[product.barcode.upper()] = product

            logger.info(f"Loaded {len(all_products)} SAS products into memory")

            # Load all SAS variations
            all_variations = SASProductVariation.objects.all().select_related('product')
            for variation in all_variations:
                # SKU mappings (SAS uses 'sku_suffix', not 'cin7_sku')
                if variation.sku_suffix:
                    variation_sku_map[variation.sku_suffix] = (variation, variation.product)
                    variation_sku_iexact_map[variation.sku_suffix.upper()] = (variation, variation.product)

            logger.info(f"Loaded {len(all_variations)} SAS variations into memory")

        elif category == 'lotto-clubs':
            from clubs.models_lotto import LottoProduct, LottoProductVariation

            # Load all LOTTO products
            all_products = LottoProduct.objects.all()
            for product in all_products:
                # SKU mappings (LOTTO uses 'sku', not 'cin7_sku')
                if product.sku:
                    product_sku_map[product.sku] = product
                    product_sku_iexact_map[product.sku.upper()] = product

                # Barcode mappings (LOTTO uses 'barcode', not 'cin7_barcode')
                if product.barcode:
                    product_barcode_map[product.barcode] = product
                    product_barcode_iexact_map[product.barcode.upper()] = product

            logger.info(f"Loaded {len(all_products)} LOTTO products into memory")

            # Load all LOTTO variations
            all_variations = LottoProductVariation.objects.all().select_related('product')
            for variation in all_variations:
                # SKU mappings (LOTTO uses 'sku_suffix', not 'cin7_sku')
                if variation.sku_suffix:
                    variation_sku_map[variation.sku_suffix] = (variation, variation.product)
                    variation_sku_iexact_map[variation.sku_suffix.upper()] = (variation, variation.product)

            logger.info(f"Loaded {len(all_variations)} LOTTO variations into memory")

        else:  # wholesale-schools
            from schools.models import WholesaleProduct, WholesaleProductVariation

            # Load all Wholesale products
            all_products = WholesaleProduct.objects.all().select_related('school')
            for product in all_products:
                # SKU mappings
                if product.cin7_sku:
                    product_sku_map[product.cin7_sku] = product
                    product_sku_iexact_map[product.cin7_sku.upper()] = product

                # Barcode mappings
                if product.cin7_barcode:
                    product_barcode_map[product.cin7_barcode] = product
                    product_barcode_iexact_map[product.cin7_barcode.upper()] = product

            logger.info(f"Loaded {len(all_products)} Wholesale products into memory")

            # Load all Wholesale variations
            all_variations = WholesaleProductVariation.objects.all().select_related('product', 'product__school')
            for variation in all_variations:
                # SKU mappings
                if variation.cin7_sku:
                    variation_sku_map[variation.cin7_sku] = (variation, variation.product)
                    variation_sku_iexact_map[variation.cin7_sku.upper()] = (variation, variation.product)

                # Barcode mappings (for style_code fallback)
                if variation.cin7_barcode:
                    variation_barcode_map[variation.cin7_barcode] = (variation, variation.product)
                    variation_barcode_iexact_map[variation.cin7_barcode.upper()] = (variation, variation.product)

            logger.info(f"Loaded {len(all_variations)} Wholesale variations into memory")

        logger.info("Memory dictionaries ready. Starting fast matching...")

        update_progress(10, "Starting optimized product matching...")

        # Helper function for fast dictionary lookup
        def fast_match(cin7_product):
            """
            Fast in-memory matching using pre-loaded dictionaries.
            Returns: (matched_product, matched_variation, match_method)
            """
            # Priority 1: Try SKU against variation cin7_sku (exact)
            if cin7_product.code:
                # Exact match
                if cin7_product.code in variation_sku_map:
                    variation, product = variation_sku_map[cin7_product.code]
                    return product, variation, "cin7_sku_exact (via SKU)"

                # Case-insensitive match
                code_upper = cin7_product.code.upper()
                if code_upper in variation_sku_iexact_map:
                    variation, product = variation_sku_iexact_map[code_upper]
                    return product, variation, "cin7_sku_iexact (via SKU)"

            # Priority 2: Try SKU against product cin7_sku (exact)
            if cin7_product.code:
                # Exact match
                if cin7_product.code in product_sku_map:
                    product = product_sku_map[cin7_product.code]
                    return product, None, "sku_exact (via SKU)"

                # Case-insensitive match
                code_upper = cin7_product.code.upper()
                if code_upper in product_sku_iexact_map:
                    product = product_sku_iexact_map[code_upper]
                    return product, None, "sku_iexact (via SKU)"

            # Priority 3: Try Barcode against variation cin7_sku (exact)
            if cin7_product.barcode:
                # Exact match
                if cin7_product.barcode in variation_sku_map:
                    variation, product = variation_sku_map[cin7_product.barcode]
                    return product, variation, "cin7_sku_exact (via Barcode)"

                # Case-insensitive match
                barcode_upper = cin7_product.barcode.upper()
                if barcode_upper in variation_sku_iexact_map:
                    variation, product = variation_sku_iexact_map[barcode_upper]
                    return product, variation, "cin7_sku_iexact (via Barcode)"

            # Priority 4: Try Barcode against product cin7_barcode (exact)
            if cin7_product.barcode:
                # Exact match
                if cin7_product.barcode in product_barcode_map:
                    product = product_barcode_map[cin7_product.barcode]
                    return product, None, "barcode_exact (via Barcode)"

                # Case-insensitive match
                barcode_upper = cin7_product.barcode.upper()
                if barcode_upper in product_barcode_iexact_map:
                    product = product_barcode_iexact_map[barcode_upper]
                    return product, None, "barcode_iexact (via Barcode)"

            # Priority 5: Try Style_code against variation cin7_sku (exact)
            if cin7_product.style_code:
                # Exact match
                if cin7_product.style_code in variation_sku_map:
                    variation, product = variation_sku_map[cin7_product.style_code]
                    return product, variation, "cin7_sku_exact (via Style_code)"

                # Case-insensitive match
                style_upper = cin7_product.style_code.upper()
                if style_upper in variation_sku_iexact_map:
                    variation, product = variation_sku_iexact_map[style_upper]
                    return product, variation, "cin7_sku_iexact (via Style_code)"

            # Priority 6: Try Style_code against product cin7_sku (exact)
            if cin7_product.style_code:
                # Exact match
                if cin7_product.style_code in product_sku_map:
                    product = product_sku_map[cin7_product.style_code]
                    return product, None, "sku_exact (via Style_code)"

                # Case-insensitive match
                style_upper = cin7_product.style_code.upper()
                if style_upper in product_sku_iexact_map:
                    product = product_sku_iexact_map[style_upper]
                    return product, None, "sku_iexact (via Style_code)"

            # No match found
            return None, None, None

        # Process in chunks for progress updates
        chunk_size = 100
        matched_count = 0
        not_found_count = 0
        skipped_no_cost = 0

        products_to_update = []

        for i, cin7_product in enumerate(cin7_products.iterator(chunk_size=chunk_size)):
            # Update progress more frequently (every 10 products for better visibility)
            if i % 10 == 0:
                percentage = 10 + int((i / total_products) * 90)  # 10-100% range
                update_progress(percentage, f"Matching products... {i}/{total_products}")

            # Log every 500 for server-side visibility
            if i % 500 == 0 and i > 0:
                logger.info(f"Progress: Matched {i}/{total_products} products...")

            # Skip products without cost price
            if not cin7_product.cost_nzd or cin7_product.cost_nzd <= 0:
                skipped_no_cost += 1
                continue

            # Fast in-memory matching
            matched_product, matched_variation, match_method = fast_match(cin7_product)

            # Update Cin7Product record
            if matched_product:
                cin7_product.matched = True
                cin7_product.match_method = match_method
                cin7_product.matched_product_id = matched_product.id
                cin7_product.matched_variation_id = matched_variation.id if matched_variation else None
                matched_count += 1
            else:
                not_found_count += 1

            products_to_update.append(cin7_product)

            # Bulk update in chunks
            if len(products_to_update) >= chunk_size:
                Cin7Product.objects.bulk_update(
                    products_to_update,
                    ['matched', 'match_method', 'matched_product_id', 'matched_variation_id'],
                    batch_size=500
                )
                products_to_update = []

        # Update remaining products
        if products_to_update:
            Cin7Product.objects.bulk_update(
                products_to_update,
                ['matched', 'match_method', 'matched_product_id', 'matched_variation_id'],
                batch_size=500
            )

        elapsed = (timezone.now() - start_time).total_seconds()

        update_progress(100, "Matching complete!")

        logger.info(f"=== CIN7 MATCHING COMPLETE ===")
        logger.info(f"Price type: {price_type}")
        logger.info(f"Category: {category}")
        logger.info(f"Total processed: {total_products}")
        logger.info(f"Matched: {matched_count}")
        logger.info(f"Not found: {not_found_count}")
        logger.info(f"Skipped (no cost): {skipped_no_cost}")
        logger.info(f"Duration: {elapsed:.2f}s")

        # Prepare preview data for matched products
        # For standalone matching (session_id starts with 'match-'), get all matched products
        # For session-based matching, get only products from this session
        if session_id.startswith('match-'):
            matched_products = Cin7Product.objects.filter(matched=True)[:1000]
        else:
            matched_products = Cin7Product.objects.filter(
                fetch_session_id=session_id,
                matched=True
            )[:1000]  # Limit to first 1000 for preview

        # Build ID-based lookup maps for preview (reuse existing dictionaries)
        product_id_map = {p.id: p for p in all_products}
        variation_id_map = {v.id: v for v in all_variations}

        preview_data = []
        for cp in matched_products:
            # Get values from database
            cin7_rrp = float(cp.retail_price) if cp.retail_price else 0.0
            cost_nzd = float(cp.cost_nzd) if cp.cost_nzd else 0.0

            # Calculate 75% margin price if not saved or if cost exists
            # Always calculate to ensure we have values for old data
            if cost_nzd > 0:
                margin_75_price = cost_nzd / 0.25  # Cost is 25% of price
            else:
                margin_75_price = 0.0

            # Calculate discount percentage: (Margin - RRP) / Margin * 100
            # Positive % means Margin > RRP (we're offering a discount from our margin price)
            # Negative % means Margin < RRP (RRP is higher than our margin, markup needed)
            if margin_75_price > 0 and cin7_rrp > 0:
                discount_pct = ((margin_75_price - cin7_rrp) / margin_75_price) * 100
            else:
                discount_pct = 0.0

            preview_data.append({
                'cin7_id': cp.cin7_id,
                'sku': cp.code,
                'barcode': cp.barcode,
                'style_code': cp.style_code,
                'name': cp.name,
                'cost': cost_nzd,
                'rrp': cin7_rrp,  # Cin7 retailNZD from API
                'margin_75_price': margin_75_price,  # Calculated 75% margin price
                'discount_percentage': discount_pct,  # Calculated discount % with +/- sign
                'match_method': cp.match_method,
                'status': 'valid'
            })

        return JsonResponse({
            'success': True,
            'session_id': session_id,
            'summary': {
                'total_processed': total_products,
                'matched': matched_count,
                'not_found': not_found_count,
                'skipped_no_cost': skipped_no_cost,
                'duration_seconds': elapsed
            },
            'preview': preview_data
        })

    except Exception as e:
        logger.error(f"Cin7 matching failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Product matching failed: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def cin7_price_apply(request):
    """
    Stage 3: Apply Cin7 price updates to database

    This endpoint loads matched Cin7Product records and applies price updates
    using BulkPriceUpdater for efficient processing.
    """
    import json
    from django.core.cache import cache
    from schools.services.bulk_price_updater import BulkPriceUpdater
    from schools.services import ProductMatcherService
    from schools.models import Cin7Product

    logger = logging.getLogger(__name__)
    start_time = timezone.now()

    def update_progress(percentage, message):
        """Update progress in cache"""
        cache_key = f"cin7_price_update_progress_{session_id}"
        cache.set(cache_key, {
            'percentage': percentage,
            'message': message,
            'stage': 'applying'
        }, timeout=3600)

    try:
        # Parse request
        data = json.loads(request.body)
        session_id = data.get('session_id')
        price_type = data.get('price_type', 'Wholesale')

        if not session_id:
            return JsonResponse({
                'success': False,
                'error': 'session_id is required'
            }, status=400)

        logger.info(f"=== CIN7 PRICE APPLY STARTED ===")
        logger.info(f"Session ID: {session_id}")
        logger.info(f"Price type: {price_type}")

        update_progress(0, "Loading matched products from database...")

        # Load matched Cin7Product records
        # For standalone matching (session_id starts with 'match-'), get all matched unprocessed products
        # For session-based matching, get only products from this session
        if session_id.startswith('match-'):
            matched_products = Cin7Product.objects.filter(
                matched=True,
                processed=False
            ).select_related()
        else:
            matched_products = Cin7Product.objects.filter(
                fetch_session_id=session_id,
                matched=True,
                processed=False
            ).select_related()

        total_products = matched_products.count()
        logger.info(f"Total matched products to apply: {total_products}")

        if total_products == 0:
            return JsonResponse({
                'success': False,
                'error': 'No matched unprocessed products found'
            }, status=404)

        # Convert Cin7Product records to price update format
        # IMPORTANT: Field names must match what BulkPriceUpdater expects
        valid_items = []
        for cp in matched_products:
            valid_items.append({
                'cin7_id': cp.cin7_id,
                'product_code': cp.code,  # Changed from 'sku' to 'product_code' for BulkPriceUpdater
                'barcode': cp.barcode,
                'style_code': cp.style_code,
                'product_name': cp.name,  # Changed from 'name' to 'product_name' for BulkPriceUpdater
                'cost': float(cp.cost_nzd) if cp.cost_nzd else 0,
                'current_retail_nzd_incl': float(cp.retail_price) if cp.retail_price else 0,  # Changed from 'rrp' to match BulkPriceUpdater
                'margin_75_price': float(cp.margin_75_price) if cp.margin_75_price else 0,
                'discount_percentage': float(cp.discount_percentage) if cp.discount_percentage else 0,
                'match_method': cp.match_method,
                'product_id': cp.matched_product_id,
                'variation_id': cp.matched_variation_id,
                'status': 'valid'
            })

        logger.info(f"Valid items prepared: {len(valid_items)}")
        logger.info(f"Sample item fields: {list(valid_items[0].keys()) if valid_items else 'None'}")

        # Map price type to category
        category_map = {
            'TUS': 'retail-schools',
            'LOTTO': 'lotto-clubs',
            'SAS': 'sas-clubs',
            'Wholesale': 'wholesale-schools'
        }
        category = category_map.get(price_type, 'wholesale-schools')

        # Initialize services
        matcher = ProductMatcherService()
        bulk_updater = BulkPriceUpdater(category, matcher, session_id=session_id)

        update_progress(30, "Applying price updates...")

        # Execute bulk update with comprehensive error handling
        try:
            logger.info(f"Starting bulk_update_prices with {len(valid_items)} items...")
            results = bulk_updater.bulk_update_prices(valid_items, backup_prices=True)
            logger.info(f"Bulk update completed. Results: {results.get('successful_updates', 0)} successful, {results.get('failed_updates', 0)} failed")
        except Exception as bulk_error:
            logger.error(f"Bulk update failed with exception: {str(bulk_error)}", exc_info=True)
            raise

        update_progress(80, "Marking products as processed...")

        # Mark ONLY successfully updated Cin7Product records as processed
        # This ensures failed updates can be retried
        successful_cin7_ids = results.get('successful_cin7_ids', [])
        if successful_cin7_ids:
            processed_count = Cin7Product.objects.filter(
                cin7_id__in=successful_cin7_ids
            ).update(
                processed=True,
                processed_at=timezone.now()
            )
            logger.info(f"Marked {processed_count} successfully updated Cin7Product records as processed")
            logger.info(f"Failed updates ({results.get('failed_updates', 0)}) remain unprocessed for retry")
        else:
            logger.warning("No successful updates - no records marked as processed")
            processed_count = 0

        elapsed = (timezone.now() - start_time).total_seconds()

        update_progress(100, "Price updates complete!")

        logger.info(f"=== CIN7 PRICE APPLY COMPLETE ===")
        logger.info(f"Successful: {results['successful_updates']}")
        logger.info(f"Failed: {results['failed_updates']}")
        logger.info(f"Processed records: {processed_count}")
        logger.info(f"Duration: {elapsed:.2f}s")

        # Audit log
        try:
            from authentication.models import AuditLog
            user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
            AuditLog.log_action(
                user=user,
                action_type='cin7_price_update_applied',
                description=f"Applied Cin7 price updates for {price_type}: {results['successful_updates']} successful, {results['failed_updates']} failed",
                request=request
            )
        except Exception as e:
            logger.error(f"Failed to audit price update: {str(e)}")

        return JsonResponse({
            'success': True,
            'session_id': session_id,
            'results': results,
            'message': f"Updated {results['successful_updates']} products successfully"
        })

    except Exception as e:
        logger.error(f"Cin7 price apply failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Price update failed: {str(e)}'
        }, status=500)


@csrf_exempt
def cin7_price_progress(request, session_id):
    """
    Poll endpoint for Cin7 price update progress
    Returns current progress from Django cache
    """
    from django.core.cache import cache

    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    cache_key = f"cin7_price_update_progress_{session_id}"
    progress_data = cache.get(cache_key)

    if progress_data is None:
        return JsonResponse({
            'status': 'pending',
            'message': 'Waiting for price update to start...',
            'progress': {
                'current': 0,
                'total': 0,
                'percentage': 0,
                'phase': 'waiting',
                'message': 'Initializing...'
            }
        })

    return JsonResponse({
        'status': 'in_progress',
        'progress': progress_data
    })
