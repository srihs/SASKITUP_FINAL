from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q, Count, Prefetch
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.management import call_command
import threading
import logging
from .models import BespokeCategory, BespokeProduct, BespokeProductVariation, BespokeSyncLog

logger = logging.getLogger(__name__)


def category_list(request):
    """Display Bespoke categories with product counts"""
    # Get only parent categories (no parent = top-level)
    categories = BespokeCategory.objects.filter(
        parent__isnull=True,
        is_active=True
    ).annotate(
        total_products=Count('product_assignments', filter=Q(product_assignments__product__is_active=True))
    ).order_by('name')

    # Also get child categories for display
    for category in categories:
        category.children_list = BespokeCategory.objects.filter(
            parent=category,
            is_active=True
        ).annotate(
            total_products=Count('product_assignments', filter=Q(product_assignments__product__is_active=True))
        ).order_by('name')

    context = {
        'categories': categories,
        'page_title': 'Bespoke Products',
    }

    return render(request, 'bespoke/category_list.html', context)


def category_detail(request, category_slug):
    """Display products in a specific Bespoke category - grouped by garment"""
    # Get the category
    category = get_object_or_404(
        BespokeCategory.objects.select_related('parent'),
        slug=category_slug,
        is_active=True
    )

    # Get search query
    search_query = request.GET.get('q', '').strip()

    # Base queryset - products in this category via assignments
    products = BespokeProduct.objects.filter(
        category_assignments__category=category,
        is_active=True
    ).prefetch_related(
        'category_assignments__category',
        Prefetch(
            'variations',
            queryset=BespokeProductVariation.objects.filter(is_active=True).order_by('option1_value', 'option2_value')
        )
    ).distinct()

    # Apply search filter
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Apply filters
    stock_filter = request.GET.get('stock', '')
    product_type_filter = request.GET.get('type', '')

    if stock_filter == 'instock':
        products = products.filter(stock_status='instock')
    elif stock_filter == 'outofstock':
        products = products.filter(stock_status='outofstock')

    if product_type_filter:
        products = products.filter(product_type=product_type_filter)

    # Order by name
    products = products.order_by('name')

    # Group products by base name (for garments with sizes)
    # This consolidates all size variations under one product card
    grouped_products = {}

    for product in products:
        if product.product_type == 'variable' and product.variations.all():
            # For variable products, show as a single card with all size variations
            grouped_products[product.id] = {
                'parent': product,
                'sizes': [],
                'is_grouped': False
            }
        else:
            # For simple products, check if they should be grouped by base name
            base_name = product.base_garment_name

            # Find existing group with same base name
            group_key = None
            for key, group in grouped_products.items():
                if group['parent'].base_garment_name == base_name:
                    group_key = key
                    break

            if group_key:
                # Add to existing group
                grouped_products[group_key]['sizes'].append(product)
                grouped_products[group_key]['is_grouped'] = True
            else:
                # Create new group with this product as parent
                grouped_products[product.id] = {
                    'parent': product,
                    'sizes': [product],
                    'is_grouped': False
                }

    # Convert to list and sort sizes within each group
    products_grouped = []
    for group in grouped_products.values():
        if group['is_grouped']:
            # Sort sizes: XS, S, M, L, XL, XXL, 2XL, 3XL, etc.
            size_order = {'XS': 0, 'S': 1, 'M': 2, 'L': 3, 'XL': 4, 'XXL': 5, '2XL': 5, '3XL': 6, '4XL': 7}
            group['sizes'].sort(key=lambda p: size_order.get(p.size_suffix or '', 99))
        products_grouped.append(group)

    products = products_grouped

    # Get child categories if parent
    child_categories = None
    if not category.parent:
        child_categories = BespokeCategory.objects.filter(
            parent=category,
            is_active=True
        ).annotate(
            total_products=Count('product_assignments', filter=Q(product_assignments__product__is_active=True))
        ).order_by('name')

    context = {
        'category': category,
        'products': products,
        'child_categories': child_categories,
        'search_query': search_query,
        'stock_filter': stock_filter,
        'product_type_filter': product_type_filter,
        'page_title': f'{category.name} - Bespoke Products',
    }

    return render(request, 'bespoke/category_detail.html', context)


def product_detail(request, product_slug):
    """Display detailed information about a Bespoke product"""
    # Get product with related data - use filter().first() to handle duplicate slugs
    product = BespokeProduct.objects.prefetch_related(
        'category_assignments__category',
        Prefetch(
            'variations',
            queryset=BespokeProductVariation.objects.filter(is_active=True).order_by('option1_value', 'option2_value')
        )
    ).filter(
        slug=product_slug,
        is_active=True
    ).first()

    if not product:
        from django.http import Http404
        raise Http404("Product not found")

    # Get categories
    categories = [assignment.category for assignment in product.category_assignments.all()]

    # Get size variations based on product type
    size_variations = []
    if product.product_type == 'variable':
        # For variable products, use the BespokeProductVariation objects
        size_variations = list(product.variations.all())
    elif product.product_type == 'simple' and product.size_suffix:
        # For simple products with size suffix, find other sizes with same base name
        base_name = product.base_garment_name
        size_variations = BespokeProduct.objects.filter(
            is_active=True
        ).exclude(id=product.id)

        # Filter by base name
        size_variations = [p for p in size_variations if p.base_garment_name == base_name]

        # Sort by size
        size_order = {'XS': 0, 'S': 1, 'M': 2, 'L': 3, 'XL': 4, 'XXL': 5, '2XL': 5, '3XL': 6, '4XL': 7}
        size_variations = sorted(size_variations, key=lambda p: size_order.get(p.size_suffix or '', 99))

    context = {
        'product': product,
        'categories': categories,
        'size_variations': size_variations,
        'page_title': product.base_garment_name,
    }

    return render(request, 'bespoke/product_detail.html', context)


def is_staff_user(user):
    """Check if user is staff/admin"""
    return user.is_authenticated and user.is_staff


def run_sync_in_background(sync_log):
    """
    Run the Bespoke sync operation in a background thread
    """
    try:
        # Mark sync as running
        sync_log.status = 'running'
        sync_log.save()

        logger.info(f"Starting Bespoke sync job {sync_log.id}")
        print(f"[BESPOKE SYNC] Starting sync job {sync_log.id}")

        # Execute sync command
        call_command(
            'sync_bespoke_products',
            verbosity=1
        )

        logger.info(f"Bespoke sync job {sync_log.id} completed successfully")
        print(f"[BESPOKE SYNC] Sync job {sync_log.id} completed successfully")

    except Exception as e:
        logger.error(f"Bespoke sync job {sync_log.id} failed: {e}", exc_info=True)
        print(f"[BESPOKE SYNC] Sync job {sync_log.id} failed: {e}")

        # Mark sync as failed
        sync_log.refresh_from_db()
        if sync_log.status != 'failed':
            sync_log.mark_failed(str(e))


@user_passes_test(is_staff_user, login_url='/auth/login/')
def trigger_sync(request):
    """
    Trigger Bespoke product sync from CIN7 API
    Runs in background thread and redirects back to category list
    """
    try:
        logger.info(f"Sync trigger requested by user {request.user.username}")
        print(f"[BESPOKE SYNC] Sync trigger requested by user {request.user.username}")

        # Check if there's already a running sync
        existing_sync = BespokeSyncLog.objects.filter(status='running').first()

        if existing_sync:
            logger.warning("Sync already running, rejecting new sync request")
            print("[BESPOKE SYNC] Sync already running, rejecting new sync request")
            messages.warning(
                request,
                'A sync is already running. Please wait for it to complete before starting another one.'
            )
            return redirect('bespoke:category_list')

        # Create new sync log entry
        sync_log = BespokeSyncLog.objects.create(
            sync_type='full',
            status='pending'
        )
        logger.info(f"Created sync log entry {sync_log.id}")
        print(f"[BESPOKE SYNC] Created sync log entry {sync_log.id}")

        # Start sync in background thread
        sync_thread = threading.Thread(
            target=run_sync_in_background,
            args=(sync_log,)
        )
        sync_thread.daemon = True
        sync_thread.start()

        logger.info(f"Background sync thread started for sync log {sync_log.id}")
        print(f"[BESPOKE SYNC] Background sync thread started for sync log {sync_log.id}")

        messages.success(
            request,
            'Product sync started successfully! This may take 5-10 minutes. You can continue browsing while the sync runs in the background.'
        )

        logger.info(f"Bespoke sync triggered by user {request.user.username}")
        print(f"[BESPOKE SYNC] Sync successfully triggered by user {request.user.username}")

    except Exception as e:
        logger.error(f"Failed to trigger Bespoke sync: {e}", exc_info=True)
        print(f"[BESPOKE SYNC] Failed to trigger sync: {e}")
        messages.error(
            request,
            f'Failed to start sync: {str(e)}'
        )

    return redirect('bespoke:category_list')
