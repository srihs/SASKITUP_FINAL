"""
TUS Retail Schools Utility Functions

This module contains utility functions for TUS retail schools operations,
keeping them separate from the existing school database functions.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from django.db.models import QuerySet, Q, Count, Prefetch
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import Http404
from django.shortcuts import get_object_or_404

from schools.models_tus import (
    TUSLocation, TUSSchool, TUSGeneralCategory, TUSSchoolCategory,
    TUSProduct, TUSProductVariation, TUSProductCategoryAssignment
)

logger = logging.getLogger(__name__)


def get_tus_locations_with_stats() -> QuerySet:
    """
    Get all TUS locations with annotated statistics

    Returns:
        QuerySet of TUSLocation objects with school counts and product counts
    """
    return TUSLocation.objects.filter(is_active=True).annotate(
        school_count=Count('schools', filter=Q(schools__is_active=True)),
        product_count=Count(
            'schools__categories__product_assignments__product',
            filter=Q(
                schools__is_active=True,
                schools__categories__product_assignments__product__stock_status__in=['instock', 'onbackorder']
            ),
            distinct=True
        )
    ).prefetch_related(
        Prefetch(
            'schools',
            queryset=TUSSchool.objects.filter(is_active=True).select_related('location')
        )
    ).order_by('name')


def get_tus_schools_in_location(location_slug: str, search_query: str = None,
                                school_type: str = None) -> Tuple[TUSLocation, QuerySet]:
    """
    Get schools in a specific location with optional filtering

    Args:
        location_slug: Location slug to filter by
        search_query: Optional search query for school names
        school_type: Optional school type filter

    Returns:
        Tuple of (location, schools_queryset)
    """
    location = get_object_or_404(
        TUSLocation.objects.annotate(
            school_count=Count('schools', filter=Q(schools__is_active=True)),
            product_count=Count(
                'schools__categories__product_assignments__product',
                filter=Q(
                    schools__is_active=True,
                    schools__categories__product_assignments__product__stock_status__in=['instock', 'onbackorder']
                ),
                distinct=True
            )
        ),
        slug=location_slug,
        is_active=True
    )

    schools = TUSSchool.objects.filter(
        location=location,
        is_active=True
    ).select_related('location').annotate(
        category_count=Count('categories'),
        product_count_annotation=Count(
            'categories__product_assignments__product',
            filter=Q(categories__product_assignments__product__stock_status__in=['instock', 'onbackorder']),
            distinct=True
        )
    )

    # Apply search filter
    if search_query:
        schools = schools.filter(
            Q(name__icontains=search_query) |
            Q(contact_person__icontains=search_query) |
            Q(address__icontains=search_query)
        )

    # Apply school type filter
    if school_type:
        schools = schools.filter(school_type=school_type)

    return location, schools.order_by('name')


def get_tus_school_with_categories(school_slug: str) -> Tuple[TUSSchool, QuerySet, QuerySet]:
    """
    Get a TUS school with its categories and featured products

    Args:
        school_slug: School slug to retrieve

    Returns:
        Tuple of (school, categories, featured_products)
    """
    school = get_object_or_404(
        TUSSchool.objects.select_related('location').annotate(
            category_count=Count('categories'),
            product_count_annotation=Count(
                'categories__product_assignments__product',
                filter=Q(categories__product_assignments__product__stock_status__in=['instock', 'onbackorder']),
                distinct=True
            )
        ),
        slug=school_slug,
        is_active=True
    )

    categories = TUSSchoolCategory.objects.filter(
        school=school
    ).order_by('display_order', 'name')

    # Get featured products for this school
    featured_products = TUSProduct.objects.filter(
        category_assignments__school_category__school=school,
        featured=True
    ).select_related().prefetch_related(
        'category_assignments__school_category',
        'variations'
    ).distinct()[:6]

    return school, categories, featured_products


def get_tus_school_category_products(school_slug: str, category_slug: str,
                                     page: int = 1, per_page: int = 12) -> Dict[str, Any]:
    """
    Get products in a specific school category with pagination

    Args:
        school_slug: School slug
        category_slug: Category slug
        page: Page number for pagination
        per_page: Items per page

    Returns:
        Dictionary with school, category, products, and pagination info
    """
    school = get_object_or_404(TUSSchool, slug=school_slug, is_active=True)
    category = get_object_or_404(
        TUSSchoolCategory.objects.select_related('school'),
        school=school,
        slug=category_slug
    )

    products = TUSProduct.objects.filter(
        category_assignments__school_category=category
    ).select_related().prefetch_related(
        'variations',
        'category_assignments__school_category'
    ).distinct().order_by('name')

    # Pagination
    paginator = Paginator(products, per_page)
    try:
        products_page = paginator.page(page)
    except PageNotAnInteger:
        products_page = paginator.page(1)
    except EmptyPage:
        products_page = paginator.page(paginator.num_pages)

    return {
        'school': school,
        'category': category,
        'products': products_page,
        'paginator': paginator,
    }


def get_tus_general_category_products(category_slug: str, page: int = 1,
                                      per_page: int = 12) -> Dict[str, Any]:
    """
    Get products in a general category with pagination

    Args:
        category_slug: Category slug
        page: Page number for pagination
        per_page: Items per page

    Returns:
        Dictionary with category, products, and pagination info
    """
    category = get_object_or_404(
        TUSGeneralCategory,
        slug=category_slug,
        is_active=True
    )

    products = TUSProduct.objects.filter(
        category_assignments__general_category=category
    ).select_related().prefetch_related(
        'variations',
        'category_assignments__general_category'
    ).distinct().order_by('name')

    # Pagination
    paginator = Paginator(products, per_page)
    try:
        products_page = paginator.page(page)
    except PageNotAnInteger:
        products_page = paginator.page(1)
    except EmptyPage:
        products_page = paginator.page(paginator.num_pages)

    return {
        'category': category,
        'products': products_page,
        'paginator': paginator,
    }


def get_tus_product_with_variations(product_id: int) -> Tuple[TUSProduct, QuerySet]:
    """
    Get a TUS product with its variations and category information

    Args:
        product_id: Product ID to retrieve

    Returns:
        Tuple of (product, variations)
    """
    product = get_object_or_404(
        TUSProduct.objects.prefetch_related(
            'category_assignments__school_category__school__location',
            'category_assignments__general_category',
            'variations'
        ),
        id=product_id
    )

    variations = TUSProductVariation.objects.filter(
        product=product,
        is_active=True
    ).order_by('menu_order', 'variation_type', 'variation_value')

    return product, variations


def search_tus_entities(query: str, entity_type: str = 'all') -> Dict[str, QuerySet]:
    """
    Search across TUS entities (locations, schools, products)

    Args:
        query: Search query string
        entity_type: Type of entity to search ('all', 'locations', 'schools', 'products')

    Returns:
        Dictionary with search results by entity type
    """
    results = {}

    if entity_type in ['all', 'locations']:
        results['locations'] = TUSLocation.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query),
            is_active=True
        ).annotate(
            school_count=Count('schools', filter=Q(schools__is_active=True))
        )[:5]

    if entity_type in ['all', 'schools']:
        results['schools'] = TUSSchool.objects.filter(
            Q(name__icontains=query) |
            Q(contact_person__icontains=query) |
            Q(address__icontains=query),
            is_active=True
        ).select_related('location')[:10]

    if entity_type in ['all', 'products']:
        results['products'] = TUSProduct.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(short_description__icontains=query) |
            Q(sku__icontains=query)
        ).prefetch_related(
            'category_assignments__school_category__school',
            'category_assignments__general_category'
        )[:10]

    return results


def get_tus_dashboard_stats() -> Dict[str, Any]:
    """
    Get dashboard statistics for TUS retail schools

    Returns:
        Dictionary with various statistics
    """
    return {
        'total_locations': TUSLocation.objects.filter(is_active=True).count(),
        'total_schools': TUSSchool.objects.filter(is_active=True).count(),
        'total_general_categories': TUSGeneralCategory.objects.filter(is_active=True).count(),
        'total_school_categories': TUSSchoolCategory.objects.count(),
        'total_products': TUSProduct.objects.count(),
        'total_variations': TUSProductVariation.objects.filter(is_active=True).count(),
        'featured_products_count': TUSProduct.objects.filter(featured=True).count(),
        'on_sale_products_count': TUSProduct.objects.filter(on_sale=True).count(),
    }


def get_tus_featured_locations(limit: int = 6) -> QuerySet:
    """
    Get featured locations with the most schools

    Args:
        limit: Number of locations to return

    Returns:
        QuerySet of featured locations
    """
    return TUSLocation.objects.filter(
        is_active=True
    ).annotate(
        school_count=Count('schools', filter=Q(schools__is_active=True))
    ).filter(school_count__gt=0).order_by('-school_count', 'name')[:limit]


def get_tus_featured_categories(limit: int = 8) -> QuerySet:
    """
    Get featured general categories

    Args:
        limit: Number of categories to return

    Returns:
        QuerySet of featured general categories
    """
    return TUSGeneralCategory.objects.filter(
        is_active=True,
        is_featured=True,
        product_count__gt=0
    ).order_by('display_order', 'name')[:limit]


def get_tus_product_variations_by_type(product_id: int, variation_type: str) -> QuerySet:
    """
    Get product variations filtered by type

    Args:
        product_id: Product ID
        variation_type: Type of variation (size, color, etc.)

    Returns:
        QuerySet of variations
    """
    return TUSProductVariation.objects.filter(
        product_id=product_id,
        variation_type=variation_type,
        is_active=True
    ).order_by('menu_order', 'variation_value')


def check_tus_variation_availability(product_id: int, **attributes) -> Dict[str, Any]:
    """
    Check availability of a specific variation combination

    Args:
        product_id: Product ID
        **attributes: Variation attributes (e.g., size='Large', color='Red')

    Returns:
        Dictionary with availability information
    """
    variations = TUSProductVariation.objects.filter(
        product_id=product_id,
        is_active=True
    )

    # Filter by attributes
    for attr_type, attr_value in attributes.items():
        if attr_value:
            variations = variations.filter(
                variation_type=attr_type,
                variation_value=attr_value
            )

    total_stock = sum(var.stock_quantity for var in variations)

    return {
        'available': total_stock > 0,
        'stock_quantity': total_stock,
        'variations': list(variations.values('id', 'variation_type', 'variation_value', 'stock_quantity')),
        'price_range': {
            'min': min((var.price for var in variations), default=0),
            'max': max((var.price for var in variations), default=0)
        }
    }


def get_tus_available_options(product_id: int, attribute_type: str, **current_selection) -> List[Dict[str, Any]]:
    """
    Get available options for a specific attribute type based on current selection

    Args:
        product_id: Product ID
        attribute_type: Attribute type to get options for
        **current_selection: Current variation selection

    Returns:
        List of available options with stock information
    """
    variations = TUSProductVariation.objects.filter(
        product_id=product_id,
        is_active=True,
        stock_quantity__gt=0
    )

    # Apply current selection filters (excluding the attribute we're getting options for)
    for attr_type, attr_value in current_selection.items():
        if attr_type != attribute_type and attr_value:
            variations = variations.filter(
                variation_type=attr_type,
                variation_value=attr_value
            )

    # Get unique options for the requested attribute type
    options = variations.filter(
        variation_type=attribute_type
    ).values('variation_value').annotate(
        total_stock=Count('stock_quantity')
    ).order_by('variation_value')

    return [
        {
            'value': option['variation_value'],
            'stock': option['total_stock'],
            'available': option['total_stock'] > 0
        }
        for option in options
    ]


def get_tus_school_types() -> List[Tuple[str, str]]:
    """
    Get available school types for filtering

    Returns:
        List of (value, label) tuples
    """
    return TUSSchool.SCHOOL_TYPES


def filter_tus_products(queryset: QuerySet, **filters) -> QuerySet:
    """
    Apply filters to a TUS product queryset

    Args:
        queryset: Base product queryset
        **filters: Filter parameters

    Returns:
        Filtered queryset
    """
    if filters.get('search'):
        search_query = filters['search']
        queryset = queryset.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(sku__icontains=search_query)
        )

    if filters.get('featured'):
        queryset = queryset.filter(featured=True)

    if filters.get('on_sale'):
        queryset = queryset.filter(on_sale=True)

    if filters.get('price_min'):
        try:
            price_min = float(filters['price_min'])
            queryset = queryset.filter(price__gte=price_min)
        except (ValueError, TypeError):
            pass

    if filters.get('price_max'):
        try:
            price_max = float(filters['price_max'])
            queryset = queryset.filter(price__lte=price_max)
        except (ValueError, TypeError):
            pass

    if filters.get('sort'):
        sort_options = {
            'name': 'name',
            'name_desc': '-name',
            'price': 'price',
            'price_desc': '-price',
            'featured': '-featured',
            'newest': '-created_at',
        }
        sort_field = sort_options.get(filters['sort'], 'name')
        queryset = queryset.order_by(sort_field)

    return queryset


def get_tus_breadcrumbs(school: TUSSchool = None, category: TUSSchoolCategory = None,
                        location: TUSLocation = None, product: TUSProduct = None) -> List[Dict[str, str]]:
    """
    Generate breadcrumb navigation for TUS pages

    Args:
        school: Current school (optional)
        category: Current category (optional)
        location: Current location (optional)
        product: Current product (optional)

    Returns:
        List of breadcrumb items with 'name' and 'url' keys
    """
    breadcrumbs = [
        {'name': 'Retail Schools', 'url': 'schools:retail_schools'}
    ]

    if location:
        breadcrumbs.append({
            'name': location.name,
            'url': f'schools:retail_location_detail:{location.slug}'
        })

    if school:
        if not location:
            breadcrumbs.append({
                'name': school.location.name,
                'url': f'schools:retail_location_detail:{school.location.slug}'
            })
        breadcrumbs.append({
            'name': school.name,
            'url': f'schools:retail_school_detail:{school.slug}'
        })

    if category:
        if not school:
            school = category.school
            breadcrumbs.append({
                'name': school.location.name,
                'url': f'schools:retail_location_detail:{school.location.slug}'
            })
            breadcrumbs.append({
                'name': school.name,
                'url': f'schools:retail_school_detail:{school.slug}'
            })
        breadcrumbs.append({
            'name': category.name,
            'url': f'schools:retail_school_category_detail:{school.slug}:{category.slug}'
        })

    if product:
        primary_category = product.primary_category
        if hasattr(primary_category, 'school'):  # School category
            school_cat = primary_category
            if not school:
                school = school_cat.school
                breadcrumbs.append({
                    'name': school.location.name,
                    'url': f'schools:retail_location_detail:{school.location.slug}'
                })
                breadcrumbs.append({
                    'name': school.name,
                    'url': f'schools:retail_school_detail:{school.slug}'
                })
            if not category:
                breadcrumbs.append({
                    'name': school_cat.name,
                    'url': f'schools:retail_school_category_detail:{school.slug}:{school_cat.slug}'
                })
        breadcrumbs.append({'name': product.name, 'url': None})

    return breadcrumbs