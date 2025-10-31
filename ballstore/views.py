from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count, Prefetch
from .models import BallStoreCategory, BallStoreProduct, BallStoreProductVariation


def category_list(request):
    """
    Display all top-level categories with product counts
    """
    # Get only parent categories (no parent = top-level) that are active
    categories = BallStoreCategory.objects.filter(
        parent__isnull=True,
        is_active=True
    ).annotate(
        total_products=Count('products', filter=Q(products__is_active=True))
    ).order_by('name')

    context = {
        'categories': categories,
        'page_title': 'BallStore - Browse Categories',
    }

    return render(request, 'ballstore/category_list.html', context)


def category_detail(request, category_slug):
    """
    Display products in a specific category (handles both parent and child categories)
    """
    # Get the category
    category = get_object_or_404(
        BallStoreCategory.objects.select_related('parent'),
        slug=category_slug,
        is_active=True
    )

    # Get search query
    search_query = request.GET.get('q', '').strip()

    # Base queryset - products in this category
    products = BallStoreProduct.objects.filter(
        categories=category,
        is_active=True
    ).prefetch_related(
        'categories',
        Prefetch(
            'variations',
            queryset=BallStoreProductVariation.objects.filter(is_active=True)
        )
    ).distinct()

    # Apply search filter if provided
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(short_description__icontains=search_query)
        )

    # Get filter parameters
    stock_filter = request.GET.get('stock', '')
    product_type_filter = request.GET.get('type', '')
    sale_filter = request.GET.get('sale', '')

    # Apply filters
    if stock_filter == 'instock':
        products = products.filter(stock_status='instock')
    elif stock_filter == 'outofstock':
        products = products.filter(stock_status='outofstock')

    if product_type_filter:
        products = products.filter(product_type=product_type_filter)

    if sale_filter == 'true':
        products = products.filter(on_sale=True)

    # Order by name
    products = products.order_by('name')

    # Get child categories if this is a parent category
    child_categories = None
    if not category.parent:
        child_categories = BallStoreCategory.objects.filter(
            parent=category,
            is_active=True
        ).annotate(
            total_products=Count('products', filter=Q(products__is_active=True))
        ).order_by('name')

    context = {
        'category': category,
        'products': products,
        'child_categories': child_categories,
        'search_query': search_query,
        'stock_filter': stock_filter,
        'product_type_filter': product_type_filter,
        'sale_filter': sale_filter,
        'page_title': f'{category.full_path} - BallStore',
    }

    return render(request, 'ballstore/category_detail.html', context)
