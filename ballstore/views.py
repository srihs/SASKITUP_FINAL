from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q, Count, Prefetch
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.management import call_command
from django.utils import timezone
import threading
import logging
from .models import BallStoreCategory, BallStoreProduct, BallStoreProductVariation, BallStoreSyncLog

logger = logging.getLogger(__name__)


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
