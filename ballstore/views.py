from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q, Count, Prefetch
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.management import call_command
from django.utils import timezone
import threading
import logging
import json
from .models import BallStoreCategory, BallStoreProduct, BallStoreProductVariation, BallStoreSyncLog

logger = logging.getLogger(__name__)


def category_list(request):
    """
    Display all top-level categories with product counts and sample product images
    """
    # Prefetch products with their images (without slice - will limit in template)
    products_prefetch = Prefetch(
        'products',
        queryset=BallStoreProduct.objects.filter(is_active=True).prefetch_related('images')
    )

    # Get only parent categories (no parent = top-level) that are active
    categories = BallStoreCategory.objects.filter(
        parent__isnull=True,
        is_active=True
    ).annotate(
        total_products=Count('products', filter=Q(products__is_active=True))
    ).prefetch_related(products_prefetch).order_by('name')

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


def is_staff_user(user):
    """Check if user is staff/admin"""
    return user.is_authenticated and user.is_staff


def run_sync_in_background(sync_log):
    """
    Run the BallStore sync operation in a background thread
    """
    try:
        # Mark sync as running
        sync_log.status = 'running'
        sync_log.save()

        logger.info(f"Starting BallStore sync job {sync_log.id}")

        # Execute sync command
        call_command(
            'sync_ballstore',
            verbosity=1
        )

        logger.info(f"BallStore sync job {sync_log.id} completed successfully")

    except Exception as e:
        logger.error(f"BallStore sync job {sync_log.id} failed: {e}", exc_info=True)

        # Mark sync as failed
        sync_log.refresh_from_db()
        if sync_log.status != 'failed':
            sync_log.mark_failed(str(e))


@user_passes_test(is_staff_user, login_url='/auth/login/')
def trigger_sync(request):
    """
    Trigger BallStore product sync from WooCommerce API
    Runs in background thread and redirects back to category list
    """
    try:
        # Check if there's already a running sync
        existing_sync = BallStoreSyncLog.objects.filter(status='running').first()

        if existing_sync:
            messages.warning(
                request,
                'A sync is already running. Please wait for it to complete before starting another one.'
            )
            return redirect('ballstore:category-list')

        # Create new sync log entry
        sync_log = BallStoreSyncLog.objects.create(
            sync_type='full',
            status='pending'
        )

        # Start sync in background thread
        sync_thread = threading.Thread(
            target=run_sync_in_background,
            args=(sync_log,)
        )
        sync_thread.daemon = True
        sync_thread.start()

        messages.success(
            request,
            'Product sync started successfully! This may take 5-10 minutes. You can continue browsing while the sync runs in the background.'
        )

        logger.info(f"BallStore sync triggered by user {request.user.username}")

    except Exception as e:
        logger.error(f"Failed to trigger BallStore sync: {e}", exc_info=True)
        messages.error(
            request,
            f'Failed to start sync: {str(e)}'
        )

    return redirect('ballstore:category-list')


def product_detail(request, category_slug, product_slug):
    """
    Display detailed product information with variations and pricing
    """
    # Get the category
    category = get_object_or_404(
        BallStoreCategory.objects.select_related('parent'),
        slug=category_slug,
        is_active=True
    )

    # Get the product
    product = get_object_or_404(
        BallStoreProduct.objects.prefetch_related(
            'images',
            Prefetch(
                'variations',
                queryset=BallStoreProductVariation.objects.filter(is_active=True).order_by('wc_id')
            ),
            'categories'
        ),
        slug=product_slug,
        categories=category,
        is_active=True
    )

    # Get all product images
    product_images = product.images.all().order_by('position')

    # Prepare variation data for JavaScript
    variations_data = []
    if product.product_type == 'variable':
        for variation in product.variations.all():
            # Build variation attributes string (e.g., "Large - Red")
            attr_parts = [attr['option'] for attr in variation.attributes]
            variation_name = " - ".join(attr_parts) if attr_parts else str(variation.wc_id)

            # Determine stock status class
            if variation.stock_status == 'instock':
                if variation.stock_quantity and variation.stock_quantity > 10:
                    stock_class = 'in-stock'
                elif variation.stock_quantity and variation.stock_quantity > 0:
                    stock_class = 'low-stock'
                else:
                    stock_class = 'in-stock'  # Default for instock without quantity
            elif variation.stock_status == 'onbackorder':
                stock_class = 'on-backorder'
            else:
                stock_class = 'out-of-stock'

            variations_data.append({
                'id': variation.wc_id,
                'name': variation_name,
                'sku': variation.sku,
                'display_price': str(variation.display_price) if variation.display_price else None,
                'price': float(variation.display_price) if variation.display_price else None,
                'regular_price': float(variation.regular_price) if variation.regular_price else None,
                'sale_price': float(variation.sale_price) if variation.sale_price else None,
                'on_sale': variation.on_sale,
                'stock_status': variation.stock_status,
                'stock_quantity': variation.stock_quantity,
                'manage_stock': variation.manage_stock,
                'stock_class': stock_class,
                'image_url': variation.image_url,
                'attributes': variation.attributes,
            })

    # Convert variations_data to JSON for safe JavaScript consumption
    variations_data_json = json.dumps(variations_data)

    # Get related products from same category (exclude current product)
    related_products = BallStoreProduct.objects.filter(
        categories=category,
        is_active=True
    ).exclude(
        id=product.id
    ).prefetch_related('images')[:4]

    context = {
        'category': category,
        'product': product,
        'product_images': product_images,
        'variations_data': variations_data,
        'variations_data_json': variations_data_json,
        'related_products': related_products,
        'page_title': f'{product.name} - BallStore',
    }

    return render(request, 'ballstore/product_detail.html', context)
