import json
import logging
import sys
import threading
from io import StringIO
from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.core.management import call_command
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.conf import settings
from .models import Club, ClubCategory, Product, SyncJob


class ClubListView(ListView):
    """List all clubs with filtering and search functionality"""
    model = Club
    template_name = 'clubs/club_list.html'
    context_object_name = 'clubs'
    paginate_by = 12

    def get_queryset(self):
        queryset = Club.objects.filter(is_active=True).prefetch_related('categories')
        
        # Filter by club type
        club_type = self.request.GET.get('type')
        if club_type and club_type in ['LOTTO', 'SAS']:
            queryset = queryset.filter(club_type=club_type)
        
        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(contact_person__icontains=search_query) |
                Q(sport_tag__icontains=search_query)
            )
        
        # Filter by sport tag
        sport = self.request.GET.get('sport')
        if sport:
            queryset = queryset.filter(sport_tag=sport)
        
        return queryset.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['club_types'] = Club.CLUB_TYPES
        context['sport_tags'] = Club.SPORT_TAGS
        context['current_type'] = self.request.GET.get('type', '')
        context['current_search'] = self.request.GET.get('search', '')
        context['current_sport'] = self.request.GET.get('sport', '')
        
        # Stats for dashboard
        context['total_clubs'] = Club.objects.filter(is_active=True).count()
        context['lotto_clubs'] = Club.objects.filter(is_active=True, club_type='LOTTO').count()
        context['sas_clubs'] = Club.objects.filter(is_active=True, club_type='SAS').count()
        
        return context


class ClubDetailView(DetailView):
    """Detailed view of a specific club showing categories and products"""
    model = Club
    template_name = 'clubs/club_detail.html'
    context_object_name = 'club'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return Club.objects.filter(is_active=True).prefetch_related(
            'categories__products'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        club = self.get_object()
        
        # Get categories with product counts (using the existing product_count field)
        context['categories'] = club.categories.filter(product_count__gt=0).order_by('name')
        
        # Recent products
        context['recent_products'] = Product.objects.filter(
            category__club=club,
            stock_status__in=['instock', 'onbackorder']
        ).order_by('-created_at')[:6]
        
        return context


class ClubDashboardView(ListView):
    """Dashboard view showing club statistics and overview"""
    model = Club
    template_name = 'clubs/dashboard.html'
    context_object_name = 'clubs'

    def get_queryset(self):
        return Club.objects.filter(is_active=True).annotate(
            total_categories=Count('categories', filter=Q(categories__product_count__gt=0)),
            available_products=Count('categories__products', filter=Q(categories__products__stock_status__in=['instock', 'onbackorder']))
        ).order_by('-available_products', 'name')[:10]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Dashboard statistics
        context['total_clubs'] = Club.objects.filter(is_active=True).count()
        context['total_lotto_clubs'] = Club.objects.filter(is_active=True, club_type='LOTTO').count()
        context['total_sas_clubs'] = Club.objects.filter(is_active=True, club_type='SAS').count()
        context['total_categories'] = ClubCategory.objects.filter(product_count__gt=0).count()
        context['total_products'] = Product.objects.filter(stock_status__in=['instock', 'onbackorder']).count()
        
        # Top performing clubs
        context['top_clubs'] = self.get_queryset()
        
        # Recent activity
        context['recent_products'] = Product.objects.filter(
            stock_status__in=['instock', 'onbackorder']
        ).select_related('category__club').order_by('-created_at')[:8]
        
        return context


class LottoClubsView(ListView):
    """List view specifically for LOTTO clubs"""
    model = Club
    template_name = 'clubs/lotto_clubs.html'
    context_object_name = 'clubs'
    paginate_by = 12

    def get_queryset(self):
        queryset = Club.objects.filter(is_active=True, club_type='LOTTO').prefetch_related('categories')
        
        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(contact_person__icontains=search_query) |
                Q(sport_tag__icontains=search_query)
            )
        
        # Filter by sport tag
        sport = self.request.GET.get('sport')
        if sport:
            queryset = queryset.filter(sport_tag=sport)
        
        return queryset.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sport_tags'] = Club.SPORT_TAGS
        context['current_search'] = self.request.GET.get('search', '')
        context['current_sport'] = self.request.GET.get('sport', '')
        context['club_type'] = 'LOTTO'
        
        # LOTTO Statistics for dashboard tiles
        context['stats'] = {
            'total_clubs': Club.objects.filter(is_active=True, club_type='LOTTO').count(),
            'total_categories': ClubCategory.objects.filter(club__club_type='LOTTO', product_count__gt=0).count(),
            'total_products': Product.objects.filter(
                category__club__club_type='LOTTO',
                stock_status__in=['instock', 'onbackorder']
            ).count(),
            'active_clubs': Club.objects.filter(
                is_active=True, 
                club_type='LOTTO'
            ).annotate(
                active_products=Count('categories__products', filter=Q(
                    categories__products__stock_status__in=['instock', 'onbackorder']
                ))
            ).filter(active_products__gt=0).count(),
            'sports_count': Club.objects.filter(
                is_active=True, 
                club_type='LOTTO'
            ).values('sport_tag').distinct().count(),
        }
        
        return context


class SASClubsView(ListView):
    """List view specifically for SAS clubs"""
    model = Club
    template_name = 'clubs/sas_clubs.html'
    context_object_name = 'clubs'
    paginate_by = 12

    def get_queryset(self):
        queryset = Club.objects.filter(is_active=True, club_type='SAS').prefetch_related('categories')
        
        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(contact_person__icontains=search_query) |
                Q(sport_tag__icontains=search_query)
            )
        
        # Filter by sport tag
        sport = self.request.GET.get('sport')
        if sport:
            queryset = queryset.filter(sport_tag=sport)
        
        return queryset.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sport_tags'] = Club.SPORT_TAGS
        context['current_search'] = self.request.GET.get('search', '')
        context['current_sport'] = self.request.GET.get('sport', '')
        context['club_type'] = 'SAS'
        return context


class ClubCategoryDetailView(DetailView):
    """Detailed view of a club category showing all products"""
    model = ClubCategory
    template_name = 'clubs/category_detail.html'
    context_object_name = 'category'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return ClubCategory.objects.select_related('club').prefetch_related('products')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.get_object()
        
        # Get products in this category
        products = category.products.filter(
            stock_status__in=['instock', 'onbackorder']
        ).order_by('name')
        context['products'] = products
        
        # Calculate average price for products with valid prices
        products_with_prices = products.filter(price__gt=0)
        if products_with_prices.exists():
            total_price = sum(product.price for product in products_with_prices)
            context['average_price'] = total_price / products_with_prices.count()
            context['price_range'] = {
                'min': min(product.price for product in products_with_prices),
                'max': max(product.price for product in products_with_prices),
            }
        else:
            context['average_price'] = 0
            context['price_range'] = {'min': 0, 'max': 0}
        
        return context


def club_search_ajax(request):
    """AJAX endpoint for club search suggestions"""
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    clubs = Club.objects.filter(
        Q(name__icontains=query) & Q(is_active=True)
    ).values('slug', 'name', 'club_type', 'sport_tag')[:10]
    
    results = list(clubs)
    return JsonResponse({'results': results})


def run_sync_in_background(sync_job):
    """
    Run the actual sync operation in a background thread
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Start the job
        sync_job.start()
        sync_job.add_log_message("Starting LOTTO clubs synchronization", "info")
        sync_job.update_progress(5, "Validating environment settings")
        
        # Validate environment variables
        required_settings = ['LOTTO_WOO_URL', 'LOTTO_WOO_KEY', 'LOTTO_WOO_SECRET']
        missing_settings = []
        
        for setting in required_settings:
            if not hasattr(settings, setting) or not getattr(settings, setting):
                missing_settings.append(setting)
        
        if missing_settings:
            sync_job.fail(
                f'Missing required WooCommerce API settings: {", ".join(missing_settings)}',
                'MISSING_SETTINGS'
            )
            sync_job.add_log_message(f"Missing settings: {', '.join(missing_settings)}", "error")
            return
        
        sync_job.update_progress(10, "Testing WooCommerce connection")
        
        # Test WooCommerce connection
        try:
            from clubs.services.woocommerce_service import WooCommerceService
            woo_service = WooCommerceService(store_type='LOTTO')
            if not woo_service.test_connection():
                sync_job.fail(
                    'Failed to connect to WooCommerce API. Please check API credentials.',
                    'CONNECTION_FAILED'
                )
                sync_job.add_log_message("WooCommerce API connection test failed", "error")
                return
            
            sync_job.add_log_message("WooCommerce API connection successful", "success")
            
        except Exception as connection_error:
            logger.error(f"WooCommerce service initialization failed: {str(connection_error)}")
            sync_job.fail(
                f'Failed to initialize WooCommerce service: {str(connection_error)}',
                'SERVICE_INIT_FAILED'
            )
            sync_job.add_log_message(f"Service initialization failed: {str(connection_error)}", "error")
            return
        
        sync_job.update_progress(20, "Executing sync command")
        
        # Custom stdout capture to track progress
        class ProgressCapture:
            def __init__(self, sync_job):
                self.sync_job = sync_job
                self.output = []
                self.progress = 20
                
            def write(self, text):
                self.output.append(text)
                # Update progress based on sync command output
                if "Fetching clubs" in text:
                    self.sync_job.update_progress(30, "Fetching clubs from WooCommerce")
                elif "Processing club:" in text:
                    self.progress = min(70, self.progress + 2)
                    self.sync_job.update_progress(self.progress, f"Processing clubs")
                elif "Fetching categories" in text:
                    self.sync_job.update_progress(75, "Fetching categories")
                elif "Processing products" in text:
                    self.sync_job.update_progress(85, "Processing products")
                elif "created:" in text.lower() or "updated:" in text.lower():
                    self.sync_job.add_log_message(text.strip(), "info")
            
            def flush(self):
                pass
            
            def getvalue(self):
                return ''.join(self.output)
        
        # Execute the sync command with progress tracking
        old_stdout = sys.stdout
        progress_capture = ProgressCapture(sync_job)
        sys.stdout = progress_capture
        
        try:
            call_command(
                'sync_lotto_clubs',
                store_type='LOTTO',
                parent_category_id=23,
                force_update=True,
                verbosity=2
            )
            
            sync_job.update_progress(90, "Processing sync results")
            
            # Parse output for statistics
            output = progress_capture.getvalue()
            
            # Extract stats from command output
            try:
                if "Clubs created:" in output:
                    for line in output.split('\n'):
                        line = line.strip()
                        try:
                            if line.startswith('Clubs created:'):
                                sync_job.clubs_created = int(line.split(':')[1].strip())
                            elif line.startswith('Clubs updated:'):
                                sync_job.clubs_updated = int(line.split(':')[1].strip())
                            elif line.startswith('Categories created:'):
                                sync_job.categories_created = int(line.split(':')[1].strip())
                            elif line.startswith('Categories updated:'):
                                sync_job.categories_updated = int(line.split(':')[1].strip())
                            elif line.startswith('Products created:'):
                                sync_job.products_created = int(line.split(':')[1].strip())
                            elif line.startswith('Products updated:'):
                                sync_job.products_updated = int(line.split(':')[1].strip())
                        except (ValueError, IndexError):
                            continue
                
                sync_job.save(update_fields=[
                    'clubs_created', 'clubs_updated', 'categories_created',
                    'categories_updated', 'products_created', 'products_updated'
                ])
                
            except Exception as parse_error:
                logger.warning(f"Could not parse sync statistics: {parse_error}")
                sync_job.add_log_message(f"Warning: Could not parse statistics: {parse_error}", "warning")
            
            # Complete the job
            sync_job.add_log_message("LOTTO clubs synchronization completed successfully", "success")
            sync_job.add_log_message(
                f"Results: {sync_job.clubs_created} clubs created, {sync_job.clubs_updated} updated",
                "info"
            )
            sync_job.complete()
            
            logger.info(f"Sync job {sync_job.id} completed successfully")
            
        except Exception as command_error:
            logger.error(f"Management command failed: {str(command_error)}")
            sync_job.fail(
                f'Sync command failed: {str(command_error)}',
                'COMMAND_FAILED'
            )
            sync_job.add_log_message(f"Sync command failed: {str(command_error)}", "error")
            
        finally:
            sys.stdout = old_stdout
            
    except Exception as e:
        logger.error(f"Background sync error: {str(e)}")
        sync_job.fail(f'Background sync failed: {str(e)}', 'BACKGROUND_SYNC_FAILED')
        sync_job.add_log_message(f"Background sync error: {str(e)}", "error")



@csrf_exempt
@require_http_methods(["POST"])
def sync_lotto_clubs(request):
    """
    Async endpoint to trigger LOTTO clubs synchronization from WooCommerce API
    Returns immediate response with job ID for polling
    """
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Starting async sync request for LOTTO clubs")
        
        # Check if there's already a running sync job
        existing_job = SyncJob.objects.filter(
            sync_type='lotto',
            status='running'
        ).first()
        
        if existing_job:
            return JsonResponse({
                'success': False,
                'error': 'A LOTTO sync is already running. Please wait for it to complete.',
                'error_code': 'SYNC_ALREADY_RUNNING',
                'job_id': str(existing_job.id)
            }, status=409)
        
        # Create new sync job
        sync_job = SyncJob.objects.create(
            sync_type='lotto',
            status='pending'
        )
        
        logger.info(f"Created sync job {sync_job.id}")
        
        # Start background sync in a separate thread
        sync_thread = threading.Thread(
            target=run_sync_in_background,
            args=(sync_job,),
            daemon=True
        )
        sync_thread.start()
        
        return JsonResponse({
            'success': True,
            'message': 'LOTTO clubs synchronization started',
            'job_id': str(sync_job.id),
            'status_url': f'/clubs/sync/status/{sync_job.id}/'
        })
        
    except Exception as e:
        logger.error(f"Async sync endpoint error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to start sync: {str(e)}',
            'error_code': 'SYNC_START_FAILED'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def test_sync_endpoint(request):
    """
    Test endpoint to verify API connectivity and environment status
    Returns JSON response with debug information
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Check authentication with more details
        is_authenticated = request.user.is_authenticated and request.user.is_staff
        
        # Debug session information
        session_info = {
            'session_key': request.session.session_key,
            'session_data': dict(request.session) if request.user.is_authenticated else {},
            'has_session': hasattr(request, 'session'),
        }
        
        # Check environment variables
        woocommerce_settings = {
            'LOTTO_WOO_URL': getattr(settings, 'LOTTO_WOO_URL', None),
            'LOTTO_WOO_KEY': bool(getattr(settings, 'LOTTO_WOO_KEY', None)),
            'LOTTO_WOO_SECRET': bool(getattr(settings, 'LOTTO_WOO_SECRET', None)),
            'SAS_WOO_URL': getattr(settings, 'SAS_WOO_URL', None),
            'SAS_WOO_KEY': bool(getattr(settings, 'SAS_WOO_KEY', None)),
            'SAS_WOO_SECRET': bool(getattr(settings, 'SAS_WOO_SECRET', None)),
        }
        
        # Test WooCommerce connection if authenticated
        connection_test = None
        if is_authenticated:
            try:
                from clubs.services.woocommerce_service import WooCommerceService
                woo_service = WooCommerceService(store_type='LOTTO')
                connection_test = woo_service.test_connection()
            except Exception as e:
                connection_test = f"Connection failed: {str(e)}"
        
        # Database stats
        db_stats = {
            'total_clubs': Club.objects.filter(is_active=True).count(),
            'lotto_clubs': Club.objects.filter(is_active=True, club_type='LOTTO').count(),
            'sas_clubs': Club.objects.filter(is_active=True, club_type='SAS').count(),
            'total_categories': ClubCategory.objects.count(),
            'total_products': Product.objects.count(),
        }
        
        return JsonResponse({
            'success': True,
            'message': 'Test endpoint working correctly',
            'debug_info': {
                'authenticated': is_authenticated,
                'user': request.user.username if request.user.is_authenticated else 'anonymous',
                'user_is_staff': request.user.is_staff if request.user.is_authenticated else False,
                'user_is_superuser': request.user.is_superuser if request.user.is_authenticated else False,
                'method': request.method,
                'session_info': session_info,
                'woocommerce_settings': woocommerce_settings,
                'connection_test': connection_test,
                'database_stats': db_stats,
                'django_version': settings.DEBUG,
            }
        })
        
    except Exception as e:
        logger.error(f"Test endpoint error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Test endpoint failed: {str(e)}',
            'error_code': 'TEST_ENDPOINT_FAILED'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def sync_status(request, job_id):
    """
    Endpoint to check the status of a sync job
    """
    logger = logging.getLogger(__name__)
    
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
        logger.error(f"Sync status endpoint error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to get sync status: {str(e)}',
            'error_code': 'STATUS_CHECK_FAILED'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def sync_jobs_list(request):
    """
    Endpoint to list recent sync jobs
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Get recent sync jobs
        jobs = SyncJob.objects.all()[:10]  # Last 10 jobs
        
        jobs_data = []
        for job in jobs:
            jobs_data.append({
                'job_id': str(job.id),
                'sync_type': job.sync_type,
                'status': job.status,
                'progress_percentage': job.progress_percentage,
                'current_step': job.current_step,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'duration': str(job.duration) if job.duration else None,
                'is_finished': job.is_finished,
                'total_created': job.total_items_created,
                'total_updated': job.total_items_updated,
            })
        
        return JsonResponse({
            'success': True,
            'jobs': jobs_data
        })
        
    except Exception as e:
        logger.error(f"Sync jobs list endpoint error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to get sync jobs: {str(e)}',
            'error_code': 'JOBS_LIST_FAILED'
        }, status=500)


def sync_lotto_clubs_page(request):
    """
    Page view for sync status and manual trigger
    """
    context = {
        'total_lotto_clubs': Club.objects.filter(is_active=True, club_type='LOTTO').count(),
        'total_lotto_categories': ClubCategory.objects.filter(club__club_type='LOTTO').count(),
        'total_lotto_products': Product.objects.filter(category__club__club_type='LOTTO').count(),
    }
    
    return render(request, 'clubs/sync_lotto.html', context)
