from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q, Count, Prefetch
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.management import call_command
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import threading
import logging
from .models import BespokeCategory, BespokeProduct, BespokeProductVariation, BespokeSyncLog
from clubs.models import SyncJob

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

    # Only add addons if this is a base garment product (not an addon product itself)
    is_base_garment = False
    for category in categories:
        # Check if product is in base-garment category (not in addon category)
        if 'base' in category.slug.lower() or 'garment' in category.slug.lower():
            is_base_garment = True
            break
        if 'addon' in category.slug.lower():
            is_base_garment = False
            break

    if is_base_garment:
        # Fetch addon products
        try:
            addon_category = BespokeCategory.objects.filter(
                slug__icontains='addon',
                is_active=True
            ).first()

            if addon_category:
                addon_products = BespokeProduct.objects.filter(
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
        except BespokeCategory.DoesNotExist:
            pass  # No addon category found

    return render(request, 'bespoke/product_detail.html', context)


def is_staff_user(user):
    """Check if user is staff/admin"""
    return user.is_authenticated and user.is_staff


def run_sync_in_background(sync_job):
    """
    Run the Bespoke sync operation in a background thread
    """
    try:
        # Mark sync as started
        sync_job.start()
        sync_job.add_log_message('Bespoke sync process started', 'info')

        logger.info(f"Starting Bespoke sync job {sync_job.id}")
        print(f"[BESPOKE SYNC] Starting sync job {sync_job.id}")

        # Update progress - Initializing
        sync_job.update_progress(10, 'Fetching categories from CIN7...')

        # Execute sync command with job_id parameter
        call_command(
            'sync_bespoke_products',
            job_id=str(sync_job.id),
            verbosity=1
        )

        # Mark as completed
        sync_job.complete()
        sync_job.add_log_message('Bespoke sync completed successfully', 'success')

        logger.info(f"Bespoke sync job {sync_job.id} completed successfully")
        print(f"[BESPOKE SYNC] Sync job {sync_job.id} completed successfully")

    except Exception as e:
        error_message = f"Bespoke sync failed: {str(e)}"
        logger.error(f"Bespoke sync job {sync_job.id} failed: {e}", exc_info=True)
        print(f"[BESPOKE SYNC] Sync job {sync_job.id} failed: {e}")

        # Mark sync as failed
        sync_job.fail(error_message, 'SYNC_COMMAND_FAILED')
        sync_job.add_log_message(error_message, 'error')


@csrf_exempt
@user_passes_test(is_staff_user, login_url='/auth/login/')
def trigger_sync(request):
    """
    Trigger Bespoke product sync from CIN7 API
    Returns JSON response with job_id for progress monitoring
    """
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Only POST method is allowed',
            'error_code': 'METHOD_NOT_ALLOWED'
        }, status=405)

    try:
        logger.info(f"Bespoke sync trigger requested by user {request.user.username}")
        print(f"[BESPOKE SYNC] Sync trigger requested by user {request.user.username}")

        # Auto-cleanup stale jobs before checking for running jobs
        cleaned_count = SyncJob.cleanup_stale_jobs(max_age_hours=2)
        if cleaned_count > 0:
            logger.info(f"Auto-cleaned {cleaned_count} stale sync jobs before starting new sync")

        # Check if there's already a running sync job (after cleanup)
        existing_job = SyncJob.objects.filter(
            sync_type='bespoke',
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
                logger.info(f"Bespoke sync already in progress (job {existing_job.id})")
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
            sync_type='bespoke',
            status='pending',
            current_step='Initializing Bespoke sync...',
            progress_percentage=0
        )

        logger.info(f"Created sync job {sync_job.id}")
        print(f"[BESPOKE SYNC] Created sync job {sync_job.id}")

        # Start sync in background thread
        sync_thread = threading.Thread(
            target=run_sync_in_background,
            args=(sync_job,)
        )
        sync_thread.daemon = True
        sync_thread.start()

        logger.info(f"Bespoke sync job {sync_job.id} started successfully")
        print(f"[BESPOKE SYNC] Background sync thread started for job {sync_job.id}")

        return JsonResponse({
            'success': True,
            'message': 'Bespoke sync started successfully',
            'job_id': str(sync_job.id),
            'status': sync_job.status,
            'progress_percentage': sync_job.progress_percentage,
            'current_step': sync_job.current_step,
            'sync_type': sync_job.sync_type,
        })

    except Exception as e:
        logger.error(f"Failed to start Bespoke sync: {str(e)}", exc_info=True)
        print(f"[BESPOKE SYNC] Failed to trigger sync: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to start Bespoke sync: {str(e)}',
            'error_code': 'SYNC_START_FAILED'
        }, status=500)


def bespoke_sync_status(request, job_id):
    """
    Endpoint to check the status of a bespoke sync job
    """
    try:
        sync_job = get_object_or_404(SyncJob, id=job_id)

        return JsonResponse({
            'success': True,
            'job_id': str(sync_job.id),
            'sync_type': sync_job.sync_type,
            'status': sync_job.status,
            'progress_percentage': sync_job.progress_percentage,
            'current_step': sync_job.current_step,
            'stats': {
                'clubs_created': sync_job.clubs_created,
                'clubs_updated': sync_job.clubs_updated,
                'categories_created': sync_job.categories_created,
                'categories_updated': sync_job.categories_updated,
                'products_created': sync_job.products_created,
                'products_updated': sync_job.products_updated,
                'total_created': sync_job.total_items_created,
                'total_updated': sync_job.total_items_updated,
            },
            'log_messages': sync_job.log_messages[-20:],  # Last 20 messages
            'error_message': sync_job.error_message,
            'error_code': sync_job.error_code,
            'started_at': sync_job.started_at.isoformat() if sync_job.started_at else None,
            'completed_at': sync_job.completed_at.isoformat() if sync_job.completed_at else None,
            'duration': str(sync_job.duration) if sync_job.duration else None,
            'is_finished': sync_job.is_finished,
        })

    except SyncJob.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Sync job not found',
            'error_code': 'JOB_NOT_FOUND'
        }, status=404)
    except Exception as e:
        logger.error(f"Bespoke sync status endpoint error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to get sync status: {str(e)}',
            'error_code': 'STATUS_CHECK_FAILED'
        }, status=500)
