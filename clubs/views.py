import json
import logging
import sys
import threading
import requests
from io import StringIO
from datetime import timedelta
from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.core.management import call_command
from django.http import JsonResponse, HttpResponse
from django.utils.decorators import method_decorator
from django.utils import timezone
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
        
        # Recent products - using many-to-many relationship
        context['recent_products'] = Product.objects.filter(
            categories__club=club,
            stock_status__in=['instock', 'onbackorder']
        ).distinct().order_by('-created_at')[:6]
        
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
        
        # Recent activity - updated for multi-category products
        context['recent_products'] = Product.objects.filter(
            stock_status__in=['instock', 'onbackorder']
        ).prefetch_related('categories__club').order_by('-created_at')[:8]
        
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
                categories__club__club_type='LOTTO',
                stock_status__in=['instock', 'onbackorder']
            ).distinct().count(),
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
                skip_images=True,  # Skip images due to bot detection
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
        
        # Auto-cleanup stale jobs before checking for running jobs
        cleaned_count = SyncJob.cleanup_stale_jobs(max_age_hours=2)
        if cleaned_count > 0:
            logger.info(f"Auto-cleaned {cleaned_count} stale sync jobs before starting new sync")
        
        # Check if there's already a running sync job (after cleanup)
        existing_job = SyncJob.objects.filter(
            sync_type='lotto',
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
                return JsonResponse({
                    'success': False,
                    'error': 'A LOTTO sync is already running. Please wait for it to complete.',
                    'error_code': 'SYNC_ALREADY_RUNNING',
                    'job_id': str(existing_job.id),
                    'age_hours': round(existing_job.get_age_hours() or 0, 2)
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
    Endpoint to list recent sync jobs with enhanced status info
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Get recent sync jobs
        jobs = SyncJob.objects.all()[:10]  # Last 10 jobs
        
        jobs_data = []
        current_time = timezone.now()
        
        for job in jobs:
            age_hours = None
            if job.started_at or job.created_at:
                age = current_time - (job.started_at or job.created_at)
                age_hours = age.total_seconds() / 3600
            
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
                'age_hours': round(age_hours, 2) if age_hours else None,
                'is_stale': job.status == 'running' and age_hours and age_hours > 2,  # Consider stale after 2 hours
                'error_message': job.error_message,
                'error_code': job.error_code,
            })
        
        # Check if there are any running jobs
        running_jobs_count = SyncJob.objects.filter(status='running').count()
        
        return JsonResponse({
            'success': True,
            'jobs': jobs_data,
            'running_jobs_count': running_jobs_count,
            'has_stale_jobs': any(job['is_stale'] for job in jobs_data)
        })
        
    except Exception as e:
        logger.error(f"Sync jobs list endpoint error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to get sync jobs: {str(e)}',
            'error_code': 'JOBS_LIST_FAILED'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def clear_sync_locks(request):
    """
    Endpoint to clear stuck sync locks (admin only)
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Authentication check removed - sync management is now publicly accessible
        
        # Get parameters from request
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        max_age_hours = data.get('max_age_hours', 2)
        force = data.get('force', False)
        
        # Find running sync jobs
        running_jobs = SyncJob.objects.filter(status='running')
        
        if not running_jobs.exists():
            return JsonResponse({
                'success': True,
                'message': 'No running sync jobs found',
                'cleared_count': 0
            })
        
        cutoff_time = timezone.now() - timedelta(hours=max_age_hours)
        cleared_count = 0
        cleared_jobs = []
        
        for job in running_jobs:
            age = timezone.now() - (job.started_at or job.created_at)
            age_hours = age.total_seconds() / 3600
            
            should_clear = force or (job.started_at and job.started_at < cutoff_time) or (not job.started_at and job.created_at < cutoff_time)
            
            if should_clear:
                # Mark job as failed with appropriate message
                username = request.user.username if request.user.is_authenticated else 'system'
                job.fail(
                    f'Job cleared by user ({username}) - was stuck in running state for {age_hours:.2f} hours',
                    'USER_CLEARED'
                )
                job.add_log_message(f'Job manually cleared by user {username} due to being stuck in running state', 'warning')
                
                cleared_jobs.append({
                    'job_id': str(job.id),
                    'sync_type': job.sync_type,
                    'age_hours': round(age_hours, 2)
                })
                cleared_count += 1
                logger.info(f"User {username} cleared stuck sync job {job.id} (age: {age_hours:.2f}h)")
        
        return JsonResponse({
            'success': True,
            'message': f'Cleared {cleared_count} stuck sync jobs',
            'cleared_count': cleared_count,
            'cleared_jobs': cleared_jobs,
            'remaining_running_jobs': SyncJob.objects.filter(status='running').count()
        })
        
    except Exception as e:
        logger.error(f"Clear sync locks endpoint error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to clear sync locks: {str(e)}',
            'error_code': 'CLEAR_LOCKS_FAILED'
        }, status=500)


def sync_lotto_clubs_page(request):
    """
    Page view for sync status and manual trigger
    """
    context = {
        'total_lotto_clubs': Club.objects.filter(is_active=True, club_type='LOTTO').count(),
        'total_lotto_categories': ClubCategory.objects.filter(club__club_type='LOTTO').count(),
        'total_lotto_products': Product.objects.filter(categories__club__club_type='LOTTO').distinct().count(),
    }
    
    return render(request, 'clubs/sync_lotto.html', context)


def sync_management_page(request):
    """
    Sync management page accessible without authentication
    Provides lock status checking and clearing functionality
    """
    context = {
        'total_lotto_clubs': Club.objects.filter(is_active=True, club_type='LOTTO').count(),
        'total_lotto_categories': ClubCategory.objects.filter(club__club_type='LOTTO').count(),
        'total_lotto_products': Product.objects.filter(categories__club__club_type='LOTTO').distinct().count(),
        'total_sas_clubs': Club.objects.filter(is_active=True, club_type='SAS').count(),
        'total_sas_categories': ClubCategory.objects.filter(club__club_type='SAS').count(),
        'total_sas_products': Product.objects.filter(categories__club__club_type='SAS').distinct().count(),
    }
    
    return render(request, 'clubs/sync_management.html', context)


def proxy_image_view(request):
    """
    Proxy external images to bypass bot protection and hotlinking restrictions
    """
    image_url = request.GET.get('url')
    if not image_url:
        return HttpResponse('Missing image URL parameter', status=400)
    
    # Validate URL to prevent abuse
    if not image_url.startswith(('http://', 'https://')):
        return HttpResponse('Invalid image URL', status=400)
    
    # Only allow certain domains to prevent abuse
    allowed_domains = [
        'www.lottosports.co.nz',
        'lottosports.co.nz',
        # Add more trusted domains as needed
    ]
    
    from urllib.parse import urlparse
    domain = urlparse(image_url).netloc.lower()
    if domain not in allowed_domains:
        return HttpResponse('Domain not allowed', status=403)
    
    try:
        # Advanced headers to mimic a real browser and avoid bot detection
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Referer': f'https://{domain}/',
            'Origin': f'https://{domain}',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'same-origin',
            'DNT': '1',
        }
        
        # Make request to external image
        response = requests.get(image_url, headers=headers, timeout=10, stream=True)
        
        # Check if we got redirected to a challenge page
        if response.status_code == 302 or 'challenge' in response.url:
            # Return a placeholder SVG image instead of 404
            placeholder_svg = """<svg width="64" height="64" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
                <rect width="64" height="64" fill="#3baeff" rx="8"/>
                <text x="32" y="40" text-anchor="middle" fill="white" font-size="20" font-family="Arial, sans-serif" font-weight="bold">?</text>
            </svg>"""
            return HttpResponse(placeholder_svg, content_type='image/svg+xml')
        
        response.raise_for_status()
        
        # Check content type
        content_type = response.headers.get('content-type', '').lower()
        if not content_type.startswith('image/'):
            return HttpResponse('Not an image', status=400)
        
        # Return the image with proper headers
        http_response = HttpResponse(
            response.content, 
            content_type=content_type
        )
        
        # Add cache headers for better performance
        http_response['Cache-Control'] = 'public, max-age=3600'  # 1 hour cache
        http_response['Access-Control-Allow-Origin'] = '*'
        
        return http_response
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to proxy image {image_url}: {str(e)}")
        # Return placeholder image for network errors
        placeholder_svg = """<svg width="64" height="64" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
            <rect width="64" height="64" fill="#e9ecef" rx="8"/>
            <text x="32" y="40" text-anchor="middle" fill="#6c757d" font-size="20" font-family="Arial, sans-serif" font-weight="bold">!</text>
        </svg>"""
        return HttpResponse(placeholder_svg, content_type='image/svg+xml')
    except Exception as e:
        logger.error(f"Error proxying image {image_url}: {str(e)}")
        # Return placeholder image for other errors
        placeholder_svg = """<svg width="64" height="64" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
            <rect width="64" height="64" fill="#dc3545" rx="8"/>
            <text x="32" y="40" text-anchor="middle" fill="white" font-size="16" font-family="Arial, sans-serif" font-weight="bold">ERR</text>
        </svg>"""
        return HttpResponse(placeholder_svg, content_type='image/svg+xml')
