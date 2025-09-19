"""
Wholesale utilities for TUS school data integration

This module provides helper functions for the wholesale section
to work with TUS school data from the clubs app.
"""

from django.db.models import Q, Count, Sum, Prefetch
from django.core.paginator import Paginator
from typing import List, Dict, Optional, Tuple, Any

# Import TUS models from clubs app
try:
    from clubs.models_tus import (
        TUSLocation, TUSSchool, TUSSchoolCategory, TUSGeneralCategory,
        TUSProduct, TUSProductVariation, TUSProductCategoryAssignment
    )
    TUS_AVAILABLE = True
except ImportError:
    TUS_AVAILABLE = False


def is_tus_available():
    """Check if TUS models are available"""
    return TUS_AVAILABLE


def get_wholesale_dashboard_stats():
    """Get dashboard statistics for wholesale view"""
    if not TUS_AVAILABLE:
        return {
            'total_locations': 0,
            'total_schools': 0,
            'total_products': 0,
            'total_categories': 0,
            'tus_available': False
        }

    return {
        'total_locations': TUSLocation.objects.filter(is_active=True).count(),
        'total_schools': TUSSchool.objects.filter(is_active=True).count(),
        'total_products': TUSProduct.objects.filter(
            stock_status__in=['instock', 'onbackorder']
        ).count(),
        'total_categories': TUSSchoolCategory.objects.filter(
            product_count__gt=0
        ).count() + TUSGeneralCategory.objects.filter(
            product_count__gt=0
        ).count(),
        'tus_available': True
    }


def get_wholesale_locations_with_stats(search_query=None, limit=None):
    """Get locations with school and product statistics for wholesale"""
    if not TUS_AVAILABLE:
        return TUSLocation.objects.none()

    queryset = TUSLocation.objects.filter(is_active=True).annotate(
        schools_count=Count('schools', filter=Q(schools__is_active=True)),
        products_count=Count(
            'schools__categories__product_assignments__product',
            filter=Q(
                schools__is_active=True,
                schools__categories__product_assignments__product__stock_status__in=['instock', 'onbackorder']
            ),
            distinct=True
        )
    ).filter(schools_count__gt=0).order_by('name')

    if search_query:
        queryset = queryset.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    if limit:
        queryset = queryset[:limit]

    return queryset


def get_wholesale_schools_in_location(location_slug, search_query=None, school_type=None):
    """Get schools within a location for wholesale view"""
    if not TUS_AVAILABLE:
        return None, TUSSchool.objects.none()

    try:
        location = TUSLocation.objects.get(slug=location_slug, is_active=True)
    except TUSLocation.DoesNotExist:
        return None, TUSSchool.objects.none()

    schools = TUSSchool.objects.filter(
        location=location,
        is_active=True
    ).annotate(
        categories_count=Count('categories', filter=Q(categories__product_count__gt=0)),
        products_count=Count(
            'categories__product_assignments__product',
            filter=Q(
                categories__product_assignments__product__stock_status__in=['instock', 'onbackorder']
            ),
            distinct=True
        )
    ).order_by('name')

    if search_query:
        schools = schools.filter(
            Q(name__icontains=search_query) |
            Q(contact_person__icontains=search_query)
        )

    if school_type:
        schools = schools.filter(school_type=school_type)

    return location, schools


def get_wholesale_school_detail(school_slug):
    """Get detailed school information for wholesale view"""
    if not TUS_AVAILABLE:
        return None, TUSSchoolCategory.objects.none(), TUSProduct.objects.none()

    try:
        school = TUSSchool.objects.select_related('location').get(
            slug=school_slug,
            is_active=True
        )
    except TUSSchool.DoesNotExist:
        return None, TUSSchoolCategory.objects.none(), TUSProduct.objects.none()

    # Get categories with product counts
    categories = TUSSchoolCategory.objects.filter(
        school=school,
        product_count__gt=0
    ).order_by('display_order', 'name')

    # Get featured/recent products
    products = TUSProduct.objects.filter(
        category_assignments__school_category__school=school,
        stock_status__in=['instock', 'onbackorder']
    ).distinct().order_by('-created_at')

    return school, categories, products


def get_wholesale_school_categories(school_slug):
    """Get categories for a specific school in wholesale"""
    if not TUS_AVAILABLE:
        return None, TUSSchoolCategory.objects.none()

    try:
        school = TUSSchool.objects.get(slug=school_slug, is_active=True)
    except TUSSchool.DoesNotExist:
        return None, TUSSchoolCategory.objects.none()

    categories = TUSSchoolCategory.objects.filter(
        school=school,
        product_count__gt=0
    ).order_by('display_order', 'name')

    return school, categories


def get_wholesale_products_in_category(category_id, search_query=None, price_range=None, sort_by='name'):
    """Get products within a category for wholesale"""
    if not TUS_AVAILABLE:
        return TUSProduct.objects.none()

    try:
        category = TUSSchoolCategory.objects.get(id=category_id)
    except TUSSchoolCategory.DoesNotExist:
        return TUSProduct.objects.none()

    products = TUSProduct.objects.filter(
        category_assignments__school_category=category,
        stock_status__in=['instock', 'onbackorder']
    ).distinct()

    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(sku__icontains=search_query)
        )

    # Price filtering
    if price_range:
        if price_range == 'under_50':
            products = products.filter(price__lt=50)
        elif price_range == '50_100':
            products = products.filter(price__gte=50, price__lt=100)
        elif price_range == '100_200':
            products = products.filter(price__gte=100, price__lt=200)
        elif price_range == 'over_200':
            products = products.filter(price__gte=200)

    # Sorting
    if sort_by == 'price_low':
        products = products.order_by('price')
    elif sort_by == 'price_high':
        products = products.order_by('-price')
    elif sort_by == 'newest':
        products = products.order_by('-created_at')
    else:
        products = products.order_by('name')

    return products


def search_wholesale_entities(query, entity_type='all'):
    """Search across TUS entities for wholesale"""
    if not TUS_AVAILABLE or len(query) < 2:
        return {
            'locations': TUSLocation.objects.none(),
            'schools': TUSSchool.objects.none(),
            'products': TUSProduct.objects.none(),
        }

    results = {}

    if entity_type in ['all', 'locations']:
        results['locations'] = TUSLocation.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query),
            is_active=True
        ).annotate(
            schools_count=Count('schools', filter=Q(schools__is_active=True))
        ).filter(schools_count__gt=0)

    if entity_type in ['all', 'schools']:
        results['schools'] = TUSSchool.objects.filter(
            Q(name__icontains=query) | Q(contact_person__icontains=query),
            is_active=True
        ).select_related('location')

    if entity_type in ['all', 'products']:
        results['products'] = TUSProduct.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query) | Q(sku__icontains=query),
            stock_status__in=['instock', 'onbackorder']
        )

    return results


def get_wholesale_featured_content():
    """Get featured content for wholesale dashboard"""
    if not TUS_AVAILABLE:
        return {
            'featured_locations': TUSLocation.objects.none(),
            'featured_schools': TUSSchool.objects.none(),
            'popular_categories': TUSSchoolCategory.objects.none()
        }

    # Featured locations (those with most schools)
    featured_locations = TUSLocation.objects.filter(
        is_active=True
    ).annotate(
        schools_count=Count('schools', filter=Q(schools__is_active=True))
    ).filter(schools_count__gt=0).order_by('-schools_count')[:6]

    # Featured schools (those with most products)
    featured_schools = TUSSchool.objects.filter(
        is_active=True
    ).annotate(
        products_count=Count(
            'categories__product_assignments__product',
            filter=Q(
                categories__product_assignments__product__stock_status__in=['instock', 'onbackorder']
            ),
            distinct=True
        )
    ).filter(products_count__gt=0).order_by('-products_count')[:6]

    # Popular categories (highest product count)
    popular_categories = TUSSchoolCategory.objects.filter(
        product_count__gt=0
    ).select_related('school', 'school__location').order_by('-product_count')[:6]

    return {
        'featured_locations': featured_locations,
        'featured_schools': featured_schools,
        'popular_categories': popular_categories
    }


def get_wholesale_school_types():
    """Get available school types for filtering"""
    if not TUS_AVAILABLE:
        return []

    return TUSSchool.objects.filter(
        is_active=True
    ).values_list('school_type', flat=True).distinct().order_by('school_type')


def get_wholesale_breadcrumbs(location_slug=None, school_slug=None, category_slug=None):
    """Generate breadcrumbs for wholesale navigation"""
    breadcrumbs = [
        {'name': 'Home', 'url': '/'},
        {'name': 'Schools', 'url': '/schools/'},
        {'name': 'Wholesale', 'url': '/schools/wholesale/'}
    ]

    if not TUS_AVAILABLE:
        return breadcrumbs

    try:
        if location_slug:
            location = TUSLocation.objects.get(slug=location_slug, is_active=True)
            breadcrumbs.append({
                'name': location.name,
                'url': f'/schools/wholesale/location/{location.slug}/'
            })

            if school_slug:
                school = TUSSchool.objects.get(
                    slug=school_slug,
                    location=location,
                    is_active=True
                )
                breadcrumbs.append({
                    'name': school.name,
                    'url': f'/schools/wholesale/school/{school.slug}/'
                })

                if category_slug:
                    category = TUSSchoolCategory.objects.get(
                        slug=category_slug,
                        school=school
                    )
                    breadcrumbs.append({
                        'name': category.name,
                        'url': f'/schools/wholesale/school/{school.slug}/category/{category.slug}/'
                    })

    except (TUSLocation.DoesNotExist, TUSSchool.DoesNotExist, TUSSchoolCategory.DoesNotExist):
        pass

    return breadcrumbs


def get_wholesale_product_detail(product_id):
    """Get detailed product information for wholesale"""
    if not TUS_AVAILABLE:
        return None

    try:
        product = TUSProduct.objects.select_related().prefetch_related(
            'variations',
            'category_assignments__school_category__school__location',
            'category_assignments__general_category'
        ).get(
            id=product_id,
            stock_status__in=['instock', 'onbackorder']
        )
        return product
    except TUSProduct.DoesNotExist:
        return None


def validate_wholesale_access(request):
    """Validate if user has access to wholesale section"""
    # Add authentication/authorization logic here if needed
    # For now, return True to allow all access
    return True


def get_wholesale_location_stats(location):
    """Get statistics for a specific location"""
    if not TUS_AVAILABLE or not location:
        return {
            'total_schools': 0,
            'total_products': 0,
            'total_categories': 0,
            'school_types': []
        }

    school_types = TUSSchool.objects.filter(
        location=location,
        is_active=True
    ).values('school_type').annotate(
        count=Count('id')
    ).order_by('school_type')

    return {
        'total_schools': location.schools.filter(is_active=True).count(),
        'total_products': TUSProduct.objects.filter(
            category_assignments__school_category__school__location=location,
            stock_status__in=['instock', 'onbackorder']
        ).distinct().count(),
        'total_categories': TUSSchoolCategory.objects.filter(
            school__location=location,
            product_count__gt=0
        ).count(),
        'school_types': list(school_types)
    }