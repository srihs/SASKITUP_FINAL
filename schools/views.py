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

# Import wholesale models from schools app
from .models import WholesaleSyncJob

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
        logger.info(f"Category filter: {category}")

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
                products_by_variation = {}

                # Load all products at once
                all_products = model_class.objects.all()
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

                # Load variations based on category
                if category == 'retail-schools':
                    from clubs.models_tus import TUSProductVariation
                    variations = TUSProductVariation.objects.select_related('product').all()
                    for variation in variations:
                        if variation.sku:
                            # TUS uses 'sku' field
                            products_by_variation[str(variation.sku).strip().upper()] = variation.product

                elif category == 'sas-clubs':
                    from clubs.models_sas import SASProductVariation
                    variations = SASProductVariation.objects.select_related('product').all()
                    for variation in variations:
                        if variation.sku_suffix:
                            # SAS uses 'sku_suffix' field
                            products_by_variation[str(variation.sku_suffix).strip().upper()] = variation.product

                elif category == 'lotto-clubs':
                    from clubs.models_lotto import LottoProductVariation
                    variations = LottoProductVariation.objects.select_related('product').all()
                    for variation in variations:
                        if variation.sku_suffix:
                            # LOTTO uses 'sku_suffix' field
                            products_by_variation[str(variation.sku_suffix).strip().upper()] = variation.product

                logger.info(f"Pre-loaded {len(all_products)} products: "
                           f"{len(products_by_sku)} indexed by SKU, "
                           f"{len(products_by_barcode)} indexed by barcode, "
                           f"{len(products_by_variation)} indexed by variation")
            except Exception as e:
                logger.error(f"Error pre-loading products: {str(e)}", exc_info=True)
                return JsonResponse({
                    'success': False,
                    'error': f'Failed to load products from database: {str(e)}',
                    'traceback': traceback.format_exc(),
                    'category': category
                }, status=500)

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
                        # Extract data from row - handle multiple possible field names
                        # Support common variations of column names (case-insensitive)
                        product_code = str(
                            row.get('product_code', '') or
                            row.get('Code', '') or
                            row.get('Style Code', '') or
                            row.get('SKU', '') or
                            row.get('sku', '') or
                            row.get('Product Code', '') or
                            row.get('Item Code', '') or
                            row.get('Style', '') or
                            row.get('code', '') or
                            row.get('style_code', '') or
                            row.get('item_code', '')
                        ).strip()

                        barcode = str(
                            row.get('barcode', '') or
                            row.get('Barcode', '') or
                            row.get('UPC', '') or
                            row.get('EAN', '') or
                            row.get('GTIN', '') or
                            row.get('upc', '') or
                            row.get('ean', '')
                        ).strip()

                        product_name = str(
                            row.get('product_name', '') or
                            row.get('Product Name', '') or
                            row.get('Name', '') or
                            row.get('Description', '') or
                            row.get('Product', '') or
                            row.get('name', '') or
                            row.get('product', '')
                        ).strip()

                        if not product_code and not barcode:
                            error_msg = f"Row {row_num}: Missing product code and barcode. Available columns: {', '.join(row.keys())}"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue

                        # Fast lookup using pre-loaded dictionaries with proper priority per category
                        product = None
                        match_method = None

                        # TUS (retail-schools): Variation SKU → Product SKU → Barcode
                        # Note: Excel "barcode" column contains variation SKU values for TUS products
                        if category == 'retail-schools':
                            # DEBUG: Log to verify new code is running
                            logger.debug(f"[TUS MATCHING v2.0] Row {row_num}: barcode={barcode}, product_code={product_code}, variations_dict_size={len(products_by_variation)}")

                            # Priority 1: Try barcode value against variation SKU first (Excel barcode = TUS variation.sku)
                            if barcode:
                                product = products_by_variation.get(barcode.upper())
                                if product:
                                    match_method = 'variation_sku_from_barcode'
                                    logger.debug(f"[TUS MATCHING v2.0] ✅ Matched barcode {barcode} to product {product.id}: {product.name}")
                                else:
                                    logger.debug(f"[TUS MATCHING v2.0] ❌ Barcode {barcode} not in variation dict")

                            # Priority 2: Try product_code against variation SKU
                            if not product and product_code:
                                product = products_by_variation.get(product_code.upper())
                                if product:
                                    match_method = 'variation_sku_exact'

                            # Priority 3: Try product_code against product SKU
                            if not product and product_code:
                                product = products_by_sku.get(product_code.upper())
                                if product:
                                    match_method = 'sku_exact'

                            # Priority 4: Fallback to product barcode (rarely used for TUS)
                            if not product and barcode:
                                product = products_by_barcode.get(barcode.upper())
                                if product:
                                    match_method = 'barcode_exact'

                        # SAS (sas-clubs): Barcode as sku_suffix → Variation → Product SKU → Product Barcode
                        elif category == 'sas-clubs':
                            # Priority 1: Try barcode value against variation sku_suffix first
                            if barcode:
                                product = products_by_variation.get(barcode.upper())
                                if product:
                                    match_method = 'variation_sku_suffix_from_barcode'

                            # Priority 2: Try product_code against variation sku_suffix
                            if not product and product_code:
                                product = products_by_variation.get(product_code.upper())
                                if product:
                                    match_method = 'variation_sku_suffix_exact'

                            # Priority 3: Try product_code against product SKU
                            if not product and product_code:
                                product = products_by_sku.get(product_code.upper())
                                if product:
                                    match_method = 'sku_exact'

                            # Priority 4: Try barcode against product barcode field (fallback)
                            if not product and barcode:
                                product = products_by_barcode.get(barcode.upper())
                                if product:
                                    match_method = 'barcode_exact'

                        # LOTTO (lotto-clubs): Variation → Product SKU → Barcode
                        elif category == 'lotto-clubs':
                            if product_code:
                                product = products_by_variation.get(product_code.upper())
                                if product:
                                    match_method = 'variation_sku_suffix_exact'

                            if not product and product_code:
                                product = products_by_sku.get(product_code.upper())
                                if product:
                                    match_method = 'sku_exact'

                            if not product and barcode:
                                product = products_by_barcode.get(barcode.upper())
                                if product:
                                    match_method = 'barcode_exact'

                        # Wholesale (default): SKU → Barcode
                        else:
                            if product_code:
                                product = products_by_sku.get(product_code.upper())
                                if product:
                                    match_method = 'sku_exact'

                            if not product and barcode:
                                product = products_by_barcode.get(barcode.upper())
                                if product:
                                    match_method = 'barcode_exact'

                        # Get price field name for this category
                        price_field = matcher.get_price_field(category)

                        # Get cost from CSV - support multiple column name variations
                        cost_raw = (
                            row.get('cost', '') or
                            row.get('Cost NZD Excl', '') or
                            row.get('Cost', '') or
                            row.get('Price', '') or
                            row.get('Unit Cost', '') or
                            row.get('cost_nzd_excl', '') or
                            row.get('unit_cost', '') or
                            row.get('price', '')
                        )

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

                                    # Get current retail price using the correct field name for this category
                                    price_field = matcher.get_price_field(category)
                                    current_price = None

                                    if product and price_field and hasattr(product, price_field):
                                        current_price = getattr(product, price_field)
                                        if current_price:
                                            rrp = float(current_price)

                                            # Calculate discount percentage: ((margin_75 - retail) / margin_75) × 100
                                            # Negative values indicate RRP is higher than 75% margin price
                                            if margin_75_price > 0:
                                                discount_calc = ((Decimal(str(margin_75_price)) - Decimal(str(current_price))) / Decimal(str(margin_75_price))) * 100
                                                discount_percentage = float(discount_calc)  # Allow negative discounts
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
                                'current_retail_nzd_incl': row.get('current_retail_nzd_incl', '') or row.get('Retail NZD Incl', ''),
                                'current_cost_price': float(product.cost_price) if product and hasattr(product, 'cost_price') and product.cost_price else None,
                                'current_margin_75_price': float(product.margin_75_price) if product and hasattr(product, 'margin_75_price') and product.margin_75_price else None,
                                'stock_quantity': stock_quantity,  # Add stock info for display/debugging
                            }

                            # Add school_name for wholesale products
                            if category == 'wholesale-schools' and product:
                                preview_item['school_name'] = product.school.name if hasattr(product, 'school') else None

                            # Add current retail price using the correct field name
                            if product and price_field:
                                current_price = getattr(product, price_field, None)
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
            logger.info(f"CSV processing complete: {row_count} rows processed, "
                       f"{valid_rows} valid products found, "
                       f"{filtered_count} filtered out (stock=0 & cost=0, or not found)")

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


@csrf_exempt
@require_http_methods(["POST"])
def wholesale_price_apply(request):
    """
    Apply price changes to ALL valid items from preview data.
    Automatically processes items with status='valid', skipping items with
    status='above_margin', 'no_cost', or 'error'.
    Supports multiple product categories via ProductMatcherService.
    Enhanced with comprehensive logging to debug the 25/1701 update issue.
    """
    import json
    from decimal import Decimal
    from django.db import transaction
    from django.utils import timezone
    from .models import WholesaleProduct
    from .services import ProductMatcherService

    logger = logging.getLogger(__name__)

    try:
        # Parse request data
        data = json.loads(request.body)
        all_items = data.get('preview_items', [])  # Changed from selected_items to preview_items
        backup_prices = data.get('backup_prices', True)
        category = data.get('category_filter', 'wholesale-schools')

        logger.info(f"=== WHOLESALE PRICE APPLY STARTED ===")
        logger.info(f"Category: {category}")
        logger.info(f"Total items received: {len(all_items)}")
        logger.info(f"Backup prices enabled: {backup_prices}")

        # Filter for only valid items
        valid_items = [item for item in all_items if item.get('status') == 'valid']

        logger.info(f"Valid items to process: {len(valid_items)} out of {len(all_items)} total items")
        logger.info(f"Skipped items: {len(all_items) - len(valid_items)}")

        # Initialize product matcher service
        matcher = ProductMatcherService()
        category_info = matcher.get_category_info(category)
        price_field = matcher.get_price_field(category)
        logger.info(f"Category info: {category_info}")
        logger.info(f"Price field for updates: {price_field}")

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

        # Process each selected item
        logger.info("=== PROCESSING ITEMS ===")
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

                        product, search_method = matcher.find_product(category, product_code_clean, barcode_clean)

                        # Update statistics based on match method
                        if product:
                            if 'sku' in search_method:
                                found_by_sku_count += 1
                            elif 'barcode' in search_method:
                                found_by_barcode_count += 1

                            logger.info(f"  ✅ Product found by {search_method}: {product.name} (ID: {product.id})")
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
                            continue

                        # Log current product state
                        logger.info(f"  - Current product state:")
                        logger.info(f"    * Cost price: {getattr(product, 'cost_price', 'N/A')}")
                        logger.info(f"    * Margin 75% price: {getattr(product, 'margin_75_price', 'N/A')}")
                        logger.info(f"    * {price_field}: {getattr(product, price_field, 'N/A')}")
                        logger.info(f"    * Discount percentage: {getattr(product, 'discount_percentage', 'N/A')}")

                        # Create backup if requested
                        backup_data = {}
                        if backup_prices:
                            cost_price = getattr(product, 'cost_price', None)
                            margin_75 = getattr(product, 'margin_75_price', None)
                            current_price = getattr(product, price_field, None) if price_field else None
                            discount_pct = getattr(product, 'discount_percentage', None)

                            backup_data = {
                                'original_cost_price': float(cost_price) if cost_price else None,
                                'original_margin_75_price': float(margin_75) if margin_75 else None,
                                'original_retail_price': float(current_price) if current_price else None,
                                'original_discount_percentage': float(discount_pct) if discount_pct else None,
                            }
                            logger.debug(f"  - Backup created: {backup_data}")

                        # Track what fields will be updated
                        updates_to_apply = {}

                        # Update product pricing fields using new structure
                        if item.get('cost'):
                            new_cost = Decimal(str(item['cost']))
                            updates_to_apply['cost_price'] = new_cost
                            product.cost_price = new_cost
                            logger.info(f"  - Updating cost price: {new_cost}")

                        if item.get('margin_75_price'):
                            new_margin = Decimal(str(item['margin_75_price']))
                            updates_to_apply['margin_75_price'] = new_margin
                            product.margin_75_price = new_margin
                            logger.info(f"  - Updating margin 75% price: {new_margin}")

                        if item.get('discount_percentage'):
                            new_discount = Decimal(str(item['discount_percentage']))
                            if hasattr(product, 'discount_percentage'):
                                updates_to_apply['discount_percentage'] = new_discount
                                product.discount_percentage = new_discount
                                logger.info(f"  - Updating discount percentage: {new_discount}")
                            else:
                                logger.warning(f"  - Product model doesn't have discount_percentage field")

                        # Also update retail price if provided (using correct field name for category)
                        if item.get('current_retail_nzd_incl') and price_field:
                            new_retail = Decimal(str(item['current_retail_nzd_incl']))
                            updates_to_apply[price_field] = new_retail
                            setattr(product, price_field, new_retail)
                            logger.info(f"  - Updating {price_field}: {new_retail}")

                        if not updates_to_apply:
                            logger.warning(f"  ⚠️ No price fields to update for {product_name}")
                            logger.warning(f"  - Available item fields: {list(item.keys())}")
                            results['skipped_products'].append({
                                'product_name': product_name,
                                'reason': 'No price fields provided',
                                'available_fields': list(item.keys())
                            })
                            continue

                        product.last_price_update = timezone.now()

                        # Save with explicit field list
                        update_fields = list(updates_to_apply.keys()) + ['last_price_update']
                        logger.debug(f"  - Saving with update_fields: {update_fields}")

                        try:
                            product.save(update_fields=update_fields)
                            logger.debug(f"  - Database save successful")
                        except Exception as save_error:
                            logger.error(f"  - Database save failed: {save_error}")
                            raise save_error

                        results['successful_updates'] += 1

                        # Build updated product info with category-aware field access
                        updated_info = {
                            'product_name': product.name,
                            'product_id': product.id,
                            'search_method': search_method,
                            'updates_applied': {k: float(v) for k, v in updates_to_apply.items()},
                            'backup_data': backup_data,
                            'new_cost_price': float(getattr(product, 'cost_price', 0)) if hasattr(product, 'cost_price') and getattr(product, 'cost_price') else None,
                            'new_margin_price': float(getattr(product, 'margin_75_price', 0)) if hasattr(product, 'margin_75_price') and getattr(product, 'margin_75_price') else None,
                        }

                        # Add school_name for wholesale products
                        if category == 'wholesale-schools' and hasattr(product, 'school'):
                            updated_info['school_name'] = product.school.name

                        results['updated_products'].append(updated_info)

                        logger.info(f"  ✅ Successfully updated {product.name}")

                    except Exception as e:
                        update_failed_count += 1
                        error_msg = f"Failed to update {product_name}: {str(e)}"
                        logger.error(f"  ❌ {error_msg}", exc_info=True)
                        results['failed_updates'] += 1
                        results['errors'].append(error_msg)

            logger.info("Database transaction completed successfully")

        except Exception as transaction_error:
            logger.error(f"Database transaction failed: {transaction_error}", exc_info=True)
            raise transaction_error

        # Log comprehensive summary
        logger.info("=== WHOLESALE PRICE APPLY SUMMARY ===")
        logger.info(f"Total items processed: {processed_count}")
        logger.info(f"Successfully updated: {results['successful_updates']}")
        logger.info(f"Failed updates: {results['failed_updates']}")
        logger.info(f"Products found by SKU: {found_by_sku_count}")
        logger.info(f"Products found by barcode: {found_by_barcode_count}")
        logger.info(f"Products not found: {not_found_count}")
        logger.info(f"Update failures: {update_failed_count}")

        if results['errors']:
            logger.warning("=== ERRORS ENCOUNTERED ===")
            for error in results['errors']:
                logger.warning(f"  - {error}")

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


def wholesale_price_update_settings(request):
    """
    Wholesale price update settings page
    """
    # Log settings access
    try:
        from authentication.models import AuditLog
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        AuditLog.log_action(
            user=user,
            action_type='wholesale_price_settings_accessed',
            description="Accessed wholesale price update settings",
            request=request
        )
    except Exception as e:
        logger.error(f"Failed to audit settings access: {str(e)}")

    context = {
        'page_title': 'Wholesale Price Update Settings',
    }
    return render(request, 'schools/wholesale/price_update_settings.html', context)
