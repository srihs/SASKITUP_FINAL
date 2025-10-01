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
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import SyncJob
# TODO: Update views to use separate LOTTO/SAS models
# from .models import Club, ClubCategory, Product
from .models_sas import SASSport, SASClub, SASProduct
from .models_lotto import LottoClub, LottoClubCategory, LottoProduct, LottoProductVariation
from schools.models import (
    WholesaleSchool, WholesaleCategory, WholesaleProduct,
    WholesaleProductVariation, WholesaleSyncJob
)
from authentication.permissions import (
    AdminRequiredMixin, SalesRepRequiredMixin, ClubAccessMixin,
    filter_clubs_for_user, can_user_manage_assignments
)
from authentication.models import AuditLog
from .mixins import (
    ClubViewAuditMixin, ClubCategoryAuditMixin, ClubProductAuditMixin,
    ClubSearchAuditMixin, ClubSyncAuditMixin, AjaxAuditMixin
)

# Initialize logger
logger = logging.getLogger(__name__)


# TODO: Update to use separate LOTTO/SAS models
# class ClubListView(LoginRequiredMixin, ClubViewAuditMixin, ClubSearchAuditMixin, ListView):
#     """List all clubs with filtering and search functionality"""
#     model = Club
#     template_name = 'clubs/club_list.html'
#     context_object_name = 'clubs'
#     paginate_by = 12
#     login_url = '/auth/login/'
#
#     def get_queryset(self):
#         # Filter clubs based on user permissions
#         base_queryset = Club.objects.filter(is_active=True).prefetch_related('categories')
#         queryset = filter_clubs_for_user(self.request.user, base_queryset)
#
#         # Filter by club type
#         club_type = self.request.GET.get('type')
#         if club_type and club_type in ['LOTTO', 'SAS']:
#             queryset = queryset.filter(club_type=club_type)
#
#         # Search functionality
#         search_query = self.request.GET.get('search')
#         if search_query:
#             queryset = queryset.filter(
#                 Q(name__icontains=search_query) |
#                 Q(contact_person__icontains=search_query) |
#                 Q(sport_tag__icontains=search_query)
#             )
#
#         # Filter by sport tag
#         sport = self.request.GET.get('sport')
#         if sport:
#             queryset = queryset.filter(sport_tag=sport)
#
#         return queryset.order_by('name')
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context['club_types'] = Club.CLUB_TYPES
#         context['sport_tags'] = Club.SPORT_TAGS
#         context['current_type'] = self.request.GET.get('type', '')
#         context['current_search'] = self.request.GET.get('search', '')
#         context['current_sport'] = self.request.GET.get('sport', '')
#
#         # Stats for dashboard
#         context['total_clubs'] = Club.objects.filter(is_active=True).count()
#         context['lotto_clubs'] = Club.objects.filter(is_active=True, club_type='LOTTO').count()
#         context['sas_clubs'] = Club.objects.filter(is_active=True, club_type='SAS').count()
#
#         return context


# TODO: Update to use separate LOTTO/SAS models
# class ClubDetailView(LoginRequiredMixin, ClubAccessMixin, ClubViewAuditMixin, DetailView):
#     """Detailed view of a specific club showing categories and products"""
#     model = Club
#     template_name = 'clubs/club_detail.html'
#     context_object_name = 'club'
#     slug_field = 'slug'
#     slug_url_kwarg = 'slug'
#     login_url = '/auth/login/'
#
#     def get_queryset(self):
#         return Club.objects.filter(is_active=True).prefetch_related(
#             'categories__products'
#         )
#
#     def get_club_object(self):
#         """Required by ClubAccessMixin"""
#         return self.get_object()
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         club = self.get_object()
#
#         # Get categories with product counts (using the existing product_count field)
#         context['categories'] = club.categories.filter(product_count__gt=0).order_by('name')
#
#         # Recent products - using many-to-many relationship
#         context['recent_products'] = Product.objects.filter(
#             categories__club=club,
#             stock_status__in=['instock', 'onbackorder']
#         ).distinct().order_by('-created_at')[:6]
#
#         return context


# TODO: Update to use separate LOTTO/SAS models
# class ClubDashboardView(LoginRequiredMixin, ListView):
#     """Dashboard view showing club statistics and overview"""
#     login_url = '/auth/login/'
#     model = Club
#     template_name = 'clubs/dashboard.html'
#     context_object_name = 'clubs'
#
#     def get_queryset(self):
#         return Club.objects.filter(is_active=True).annotate(
#             total_categories=Count('categories', filter=Q(categories__product_count__gt=0)),
#             available_products=Count('categories__products', filter=Q(categories__products__stock_status__in=['instock', 'onbackorder']))
#         ).order_by('-available_products', 'name')[:15]
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#
#         # Dashboard statistics
#         context['total_clubs'] = Club.objects.filter(is_active=True).count()
#         context['total_lotto_clubs'] = Club.objects.filter(is_active=True, club_type='LOTTO').count()
#         context['total_sas_clubs'] = Club.objects.filter(is_active=True, club_type='SAS').count()
#         context['total_categories'] = ClubCategory.objects.filter(product_count__gt=0).count()
#         context['total_products'] = Product.objects.filter(stock_status__in=['instock', 'onbackorder']).count()
#
#         # Top performing clubs
#         context['top_clubs'] = self.get_queryset()
#
#         # Recent activity - updated for multi-category products
#         context['recent_products'] = Product.objects.filter(
#             stock_status__in=['instock', 'onbackorder']
#         ).prefetch_related('categories__club').order_by('-created_at')[:8]
#
#         return context


class LottoClubsView(ListView):
    """List view specifically for LOTTO clubs"""
    # model is set in get_queryset() using LottoClub
    template_name = 'clubs/lotto_clubs.html'
    context_object_name = 'clubs'
    paginate_by = 12

    def get_queryset(self):
        from .models_lotto import LottoClub
        queryset = LottoClub.objects.filter(is_active=True).prefetch_related('categories')

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
        from .models_lotto import LottoClub, LottoClubCategory, LottoProduct
        context = super().get_context_data(**kwargs)
        context['sport_tags'] = LottoClub.SPORT_TAGS
        context['current_search'] = self.request.GET.get('search', '')
        context['current_sport'] = self.request.GET.get('sport', '')
        context['club_type'] = 'LOTTO'

        # LOTTO Statistics for dashboard tiles
        context['stats'] = {
            'total_clubs': LottoClub.objects.filter(is_active=True).count(),
            'total_categories': LottoClubCategory.objects.filter(product_count__gt=0).count(),
            'total_products': LottoProduct.objects.filter(
                stock_status__in=['instock', 'onbackorder']
            ).count(),
            'active_clubs': LottoClub.objects.filter(
                is_active=True
            ).annotate(
                active_products=Count('categories__products', filter=Q(
                    categories__products__stock_status__in=['instock', 'onbackorder']
                ))
            ).filter(active_products__gt=0).count(),
            'sports_count': LottoClub.objects.filter(
                is_active=True
            ).values('sport_tag').distinct().count(),
        }

        return context


class LottoClubDetailView(DetailView):
    """Detailed view of a specific LOTTO club showing categories and products"""
    template_name = 'clubs/club_detail.html'  # Use existing template
    context_object_name = 'club'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        from .models_lotto import LottoClub
        return LottoClub.objects.filter(is_active=True).prefetch_related('categories__products')

    def get_context_data(self, **kwargs):
        from .models_lotto import LottoProduct
        context = super().get_context_data(**kwargs)
        club = self.get_object()

        # Get categories with product counts (using the existing product_count field)
        context['categories'] = club.categories.filter(product_count__gt=0).order_by('name')

        # Recent products - matching old ClubDetailView logic
        recent_products = LottoProduct.objects.filter(
            category__club=club,
            stock_status__in=['instock', 'onbackorder']
        ).order_by('-created_at')[:6]

        context['recent_products'] = recent_products

        return context


class LottoCategoryDetailView(DetailView):
    """Detailed view of a LOTTO club category showing all products"""
    template_name = 'clubs/category_detail.html'  # Use existing template
    context_object_name = 'category'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        from .models_lotto import LottoClubCategory
        return LottoClubCategory.objects.select_related('club').prefetch_related('products')

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


# TODO: Update to use separate LOTTO/SAS models
# class ClubCategoryDetailView(ClubCategoryAuditMixin, DetailView):
#     """Detailed view of a club category showing all products"""
#     model = ClubCategory
#     template_name = 'clubs/category_detail.html'
#     context_object_name = 'category'
#     slug_field = 'slug'
#     slug_url_kwarg = 'slug'
#
#     def get_queryset(self):
#         return ClubCategory.objects.select_related('club').prefetch_related('products')
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         category = self.get_object()
#
#         # Get products in this category
#         products = category.products.filter(
#             stock_status__in=['instock', 'onbackorder']
#         ).order_by('name')
#         context['products'] = products
#
#         # Calculate average price for products with valid prices
#         products_with_prices = products.filter(price__gt=0)
#         if products_with_prices.exists():
#             total_price = sum(product.price for product in products_with_prices)
#             context['average_price'] = total_price / products_with_prices.count()
#             context['price_range'] = {
#                 'min': min(product.price for product in products_with_prices),
#                 'max': max(product.price for product in products_with_prices),
#             }
#         else:
#             context['average_price'] = 0
#             context['price_range'] = {'min': 0, 'max': 0}
#
#         return context


def club_search_ajax(request):
    """AJAX endpoint for club search suggestions"""
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'results': []})

    # Search across both LOTTO and SAS clubs
    lotto_clubs = LottoClub.objects.filter(
        Q(name__icontains=query) & Q(is_active=True)
    ).values('slug', 'name')[:5]

    sas_clubs = SASClub.objects.filter(
        Q(name__icontains=query) & Q(is_active=True)
    ).values('slug', 'name')[:5]

    # Combine results and add club_type
    results = []
    for club in lotto_clubs:
        club['club_type'] = 'LOTTO'
        club['sport_tag'] = ''  # LottoClub doesn't have sport_tag
        results.append(club)

    for club in sas_clubs:
        club['club_type'] = 'SAS'
        club['sport_tag'] = ''  # SASClub uses SASSport relationship
        results.append(club)

    # Log AJAX search
    try:
        AuditLog.log_action(
            user=request.user if request.user.is_authenticated else None,
            action_type='club_searched',
            description=f"AJAX search performed: '{query}' ({len(results)} results)",
            request=request,
            search_query=query,
            results_count=len(results),
            is_ajax=True
        )
    except Exception as e:
        logger.error(f"Failed to log AJAX search: {str(e)}")

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


def run_sas_sync_in_background(sync_job):
    """
    Run the actual SAS sync operation in a background thread
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Start the job
        sync_job.start()
        sync_job.add_log_message("Starting SAS clubs synchronization", "info")
        sync_job.update_progress(5, "Validating environment settings")
        
        # Validate environment variables
        required_settings = ['SAS_WOO_URL', 'SAS_WOO_KEY', 'SAS_WOO_SECRET']
        missing_settings = []
        
        for setting in required_settings:
            if not hasattr(settings, setting) or not getattr(settings, setting):
                missing_settings.append(setting)
        
        if missing_settings:
            sync_job.fail(
                f'Missing required SAS WooCommerce API settings: {", ".join(missing_settings)}',
                'MISSING_SETTINGS'
            )
            sync_job.add_log_message(f"Missing SAS settings: {', '.join(missing_settings)}", "error")
            return
        
        sync_job.update_progress(10, "Testing SAS WooCommerce connection")
        
        # Test WooCommerce connection
        try:
            from clubs.services.woocommerce_service import WooCommerceService
            woo_service = WooCommerceService(store_type='SAS')
            if not woo_service.test_connection():
                sync_job.fail(
                    'Failed to connect to SAS WooCommerce API. Please check API credentials.',
                    'CONNECTION_FAILED'
                )
                sync_job.add_log_message("SAS WooCommerce API connection test failed", "error")
                return
            
            sync_job.add_log_message("SAS WooCommerce API connection successful", "success")
            
        except Exception as connection_error:
            logger.error(f"SAS WooCommerce service initialization failed: {str(connection_error)}")
            sync_job.fail(
                f'Failed to initialize SAS WooCommerce service: {str(connection_error)}',
                'SERVICE_INIT_FAILED'
            )
            sync_job.add_log_message(f"SAS service initialization failed: {str(connection_error)}", "error")
            return
        
        sync_job.update_progress(20, "Executing SAS sync command")
        
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
                    self.sync_job.update_progress(30, "Fetching SAS clubs from WooCommerce")
                elif "Processing club:" in text:
                    self.progress = min(70, self.progress + 2)
                    self.sync_job.update_progress(self.progress, f"Processing SAS clubs")
                elif "Fetching categories" in text:
                    self.sync_job.update_progress(75, "Fetching SAS categories")
                elif "Processing products" in text:
                    self.sync_job.update_progress(85, "Processing SAS products")
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
                'sync_sas_clubs',
                force_update=True,
                verbose=True,
                verbosity=2
            )
            
            sync_job.update_progress(90, "Processing SAS sync results")
            
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
                logger.warning(f"Could not parse SAS sync statistics: {parse_error}")
                sync_job.add_log_message(f"Warning: Could not parse SAS statistics: {parse_error}", "warning")
            
            # Complete the job
            sync_job.add_log_message("SAS clubs synchronization completed successfully", "success")
            sync_job.add_log_message(
                f"Results: {sync_job.clubs_created} clubs created, {sync_job.clubs_updated} updated",
                "info"
            )
            sync_job.complete()
            
            logger.info(f"SAS sync job {sync_job.id} completed successfully")
            
        except Exception as command_error:
            logger.error(f"SAS management command failed: {str(command_error)}")
            sync_job.fail(
                f'SAS sync command failed: {str(command_error)}',
                'COMMAND_FAILED'
            )
            sync_job.add_log_message(f"SAS sync command failed: {str(command_error)}", "error")
            
        finally:
            sys.stdout = old_stdout
            
    except Exception as e:
        logger.error(f"SAS background sync error: {str(e)}")
        sync_job.fail(f'SAS background sync failed: {str(e)}', 'BACKGROUND_SYNC_FAILED')
        sync_job.add_log_message(f"SAS background sync error: {str(e)}", "error")



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

        # Log sync start
        try:
            AuditLog.log_action(
                user=request.user if request.user.is_authenticated else None,
                action_type='lotto_sync_started',
                description=f"Started LOTTO clubs synchronization",
                request=request,
                sync_job_id=str(sync_job.id),
                sync_type='lotto'
            )
        except Exception as e:
            logger.error(f"Failed to log sync start: {str(e)}")

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
@require_http_methods(["POST"])
def sync_sas_clubs(request):
    """
    Async endpoint to trigger SAS clubs synchronization from WooCommerce API
    Returns immediate response with job ID for polling
    """
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Starting async sync request for SAS clubs")
        
        # Auto-cleanup stale jobs before checking for running jobs
        cleaned_count = SyncJob.cleanup_stale_jobs(max_age_hours=2)
        if cleaned_count > 0:
            logger.info(f"Auto-cleaned {cleaned_count} stale sync jobs before starting new sync")
        
        # Check if there's already a running sync job (after cleanup)
        existing_job = SyncJob.objects.filter(
            sync_type='sas',
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
                    'error': 'A SAS sync is already running. Please wait for it to complete.',
                    'error_code': 'SYNC_ALREADY_RUNNING',
                    'job_id': str(existing_job.id),
                    'age_hours': round(existing_job.get_age_hours() or 0, 2)
                }, status=409)
        
        # Create new sync job
        sync_job = SyncJob.objects.create(
            sync_type='sas',
            status='pending'
        )
        
        logger.info(f"Created SAS sync job {sync_job.id}")

        # Log sync start
        try:
            AuditLog.log_action(
                user=request.user if request.user.is_authenticated else None,
                action_type='sas_sync_started',
                description=f"Started SAS clubs synchronization",
                request=request,
                sync_job_id=str(sync_job.id),
                sync_type='sas'
            )
        except Exception as e:
            logger.error(f"Failed to log SAS sync start: {str(e)}")

        # Start background sync in a separate thread
        sync_thread = threading.Thread(
            target=run_sas_sync_in_background,
            args=(sync_job,),
            daemon=True
        )
        sync_thread.start()
        
        return JsonResponse({
            'success': True,
            'message': 'SAS clubs synchronization started',
            'job_id': str(sync_job.id),
            'status_url': f'/clubs/sync/status/{sync_job.id}/'
        })
        
    except Exception as e:
        logger.error(f"SAS async sync endpoint error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to start SAS sync: {str(e)}',
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
        
        # Database stats - using separate models
        db_stats = {
            'total_clubs': LottoClub.objects.filter(is_active=True).count() + SASClub.objects.filter(is_active=True).count(),
            'lotto_clubs': LottoClub.objects.filter(is_active=True).count(),
            'sas_clubs': SASClub.objects.filter(is_active=True).count(),
            'total_categories': LottoClubCategory.objects.count(),
            'total_products': LottoProduct.objects.count() + SASProduct.objects.count(),
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
        'total_lotto_clubs': LottoClub.objects.filter(is_active=True).count(),
        'total_lotto_categories': LottoClubCategory.objects.count(),
        'total_lotto_products': LottoProduct.objects.count(),
    }

    return render(request, 'clubs/sync_lotto.html', context)


def sync_management_page(request):
    """
    Sync management page accessible without authentication
    Provides lock status checking and clearing functionality
    """
    context = {
        'total_lotto_clubs': LottoClub.objects.filter(is_active=True).count(),
        'total_lotto_categories': LottoClubCategory.objects.count(),
        'total_lotto_products': LottoProduct.objects.count(),
        'total_sas_clubs': SASClub.objects.filter(is_active=True).count(),
        'total_sas_categories': 0,  # TODO: Add SASClubCategory model if needed
        'total_sas_products': SASProduct.objects.count(),
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
        'dev-lottosports.it.sas.co.nz',  # LOTTO dev environment
        'd1zjzw7jbxeyd4.cloudfront.net',  # SAS CloudFront CDN
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


# ===============================
# SAS VIEWS - Using SAS Models
# ===============================

class SASDashboardView(ListView):
    """Dashboard view for SAS showing sports, clubs, and products statistics"""
    model = SASSport
    template_name = 'clubs/sas_dashboard.html'
    context_object_name = 'sports'

    def get_queryset(self):
        return SASSport.objects.active_with_clubs().by_club_count()[:10]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Dashboard statistics
        context['total_sports'] = SASSport.objects.filter(is_active=True).count()
        context['total_clubs'] = SASClub.objects.filter(is_active=True).count()
        context['clubs_only'] = SASClub.objects.clubs_only().count()  # Excludes schools and generic categories
        context['total_products'] = SASProduct.objects.available().count()
        context['in_stock_products'] = SASProduct.objects.in_stock().count()
        context['featured_products'] = SASProduct.objects.filter(featured=True, stock_status__in=['instock', 'onbackorder']).count()
        
        # Top performing clubs by product count
        context['top_clubs'] = SASClub.objects.filter(
            is_active=True, 
            product_count__gt=0
        ).select_related('sport').order_by('-product_count')[:10]
        
        # Recent products
        context['recent_products'] = SASProduct.objects.filter(
            stock_status__in=['instock', 'onbackorder']
        ).select_related('club__sport').order_by('-created_at')[:8]
        
        # Sports with most clubs
        context['top_sports'] = SASSport.objects.annotate(
            active_clubs=Count('clubs', filter=Q(clubs__is_active=True, clubs__is_school=False, clubs__is_generic_category=False))
        ).filter(active_clubs__gt=0).order_by('-active_clubs')[:5]
        
        return context


class SASClubListView(ListView):
    """List all SAS clubs with filtering by sport and search functionality"""
    model = SASClub
    template_name = 'clubs/sas_clubs.html'
    context_object_name = 'clubs'
    paginate_by = 12

    def get_queryset(self):
        # Use clubs_only() manager to automatically exclude schools and generic categories
        queryset = SASClub.objects.clubs_only().select_related('sport')
        
        # Toggle for showing/hiding schools (optional override)
        include_schools = self.request.GET.get('include_schools', 'false').lower() == 'true'
        if include_schools:
            # If schools are requested, use broader filter but still exclude generic categories
            queryset = SASClub.objects.filter(is_active=True, is_generic_category=False).select_related('sport')
        
        # Filter by sport
        sport_slug = self.request.GET.get('sport')
        if sport_slug:
            queryset = queryset.filter(sport__slug=sport_slug)
        
        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(sport__name__icontains=search_query) |
                Q(contact_person__icontains=search_query) |
                Q(city__icontains=search_query)
            )
        
        return queryset.order_by('sport__name', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get the same queryset for accurate counts
        base_queryset = self.get_queryset()
        
        # Available sports (from filtered results)
        context['sports'] = SASSport.objects.filter(is_active=True, club_count__gt=0).order_by('name')
        context['current_sport'] = self.request.GET.get('sport', '')
        context['current_search'] = self.request.GET.get('search', '')
        context['include_schools'] = self.request.GET.get('include_schools', 'false').lower() == 'true'
        
        # Statistics based on FILTERED results (what's actually shown)
        total_filtered_clubs = base_queryset.count()
        
        # Get accurate statistics for SAS clubs only
        context['stats'] = {
            'total_clubs': total_filtered_clubs,  # Use filtered count for display
            'total_categories': SASProduct.objects.filter(
                club__in=base_queryset,
                stock_status__in=['instock', 'onbackorder']
            ).values('club').distinct().count(),
            'total_products': SASProduct.objects.filter(
                club__in=base_queryset,
                stock_status__in=['instock', 'onbackorder']
            ).count(),
            'active_clubs': base_queryset.filter(product_count__gt=0).count(),
            'clubs_only': SASClub.objects.clubs_only().count(),  # Overall system stats
            'schools_only': SASClub.objects.filter(is_active=True, is_school=True).count(),
            'with_products': SASClub.objects.with_products().count(),
        }
        
        return context


class SASClubDetailView(DetailView):
    """Detailed view of a specific SAS club showing products"""
    model = SASClub
    template_name = 'clubs/sas_club_detail.html'
    context_object_name = 'club'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return SASClub.objects.filter(is_active=True).select_related('sport')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        club = self.get_object()
        
        # Get products for this club
        context['products'] = club.products.filter(
            stock_status__in=['instock', 'onbackorder']
        ).order_by('-featured', 'name')
        
        # Product statistics
        context['product_stats'] = {
            'total': club.products.available().count(),
            'in_stock': club.products.in_stock().count(),
            'featured': club.products.filter(featured=True, stock_status__in=['instock', 'onbackorder']).count(),
            'on_sale': club.products.on_sale().count(),
        }
        
        # Price range
        products_with_prices = context['products'].filter(price__gt=0)
        if products_with_prices.exists():
            prices = [p.effective_price for p in products_with_prices]
            context['price_range'] = {
                'min': min(prices),
                'max': max(prices),
                'avg': sum(prices) / len(prices),
            }
        
        return context


class SASSportListView(ListView):
    """List all SAS sports with club counts and filtering"""
    model = SASSport
    template_name = 'clubs/sas_sports.html'
    context_object_name = 'sports'
    paginate_by = 20

    def get_queryset(self):
        queryset = SASSport.objects.filter(is_active=True).annotate(
            active_clubs_count=Count('clubs', filter=Q(clubs__is_active=True, clubs__is_school=False, clubs__is_generic_category=False)),
            total_products_count=Count('clubs__products', filter=Q(
                clubs__is_active=True, 
                clubs__products__stock_status__in=['instock', 'onbackorder']
            ))
        )
        
        # Filter to only sports with clubs
        show_empty = self.request.GET.get('show_empty', 'false').lower() == 'true'
        if not show_empty:
            queryset = queryset.filter(active_clubs_count__gt=0)
        
        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(name__icontains=search_query)
        
        # Ordering
        order_by = self.request.GET.get('order_by', 'clubs')
        if order_by == 'name':
            queryset = queryset.order_by('name')
        elif order_by == 'products':
            queryset = queryset.order_by('-total_products_count', 'name')
        else:  # default to clubs
            queryset = queryset.order_by('-active_clubs_count', 'name')
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_search'] = self.request.GET.get('search', '')
        context['current_order'] = self.request.GET.get('order_by', 'clubs')
        context['show_empty'] = self.request.GET.get('show_empty', 'false').lower() == 'true'
        
        # Statistics
        context['stats'] = {
            'total_sports': SASSport.objects.filter(is_active=True).count(),
            'sports_with_clubs': SASSport.objects.filter(is_active=True, club_count__gt=0).count(),
            'total_clubs': SASClub.objects.filter(is_active=True, is_school=False, is_generic_category=False).count(),
            'total_products': SASProduct.objects.available().count(),
        }
        
        return context


class SASProductListView(ListView):
    """List all SAS products with comprehensive filtering"""
    model = SASProduct
    template_name = 'clubs/sas_products.html'
    context_object_name = 'products'
    paginate_by = 24

    def get_queryset(self):
        from django.db.models import F, Min, Max, Avg
        
        queryset = SASProduct.objects.filter(
            stock_status__in=['instock', 'onbackorder']
        ).select_related('club__sport')
        
        # Filter by sport
        sport_slug = self.request.GET.get('sport')
        if sport_slug:
            queryset = queryset.filter(club__sport__slug=sport_slug)
        
        # Filter by club
        club_slug = self.request.GET.get('club')
        if club_slug:
            queryset = queryset.filter(club__slug=club_slug)
        
        # Filter by stock status
        stock_status = self.request.GET.get('stock_status')
        if stock_status and stock_status in ['instock', 'outofstock', 'onbackorder']:
            queryset = queryset.filter(stock_status=stock_status)
        
        # Filter by price range
        min_price = self.request.GET.get('min_price')
        max_price = self.request.GET.get('max_price')
        if min_price:
            try:
                queryset = queryset.filter(price__gte=float(min_price))
            except ValueError:
                pass
        if max_price:
            try:
                queryset = queryset.filter(price__lte=float(max_price))
            except ValueError:
                pass
        
        # Filter featured products
        featured_only = self.request.GET.get('featured', 'false').lower() == 'true'
        if featured_only:
            queryset = queryset.filter(featured=True)
        
        # Filter on sale products
        on_sale_only = self.request.GET.get('on_sale', 'false').lower() == 'true'
        if on_sale_only:
            queryset = queryset.filter(
                sale_price__isnull=False,
                sale_price__gt=0,
                sale_price__lt=F('regular_price')
            )
        
        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(short_description__icontains=search_query) |
                Q(sku__icontains=search_query) |
                Q(club__name__icontains=search_query)
            )
        
        # Ordering
        order_by = self.request.GET.get('order_by', 'name')
        if order_by == 'price_asc':
            queryset = queryset.order_by('price')
        elif order_by == 'price_desc':
            queryset = queryset.order_by('-price')
        elif order_by == 'newest':
            queryset = queryset.order_by('-created_at')
        elif order_by == 'oldest':
            queryset = queryset.order_by('created_at')
        elif order_by == 'club':
            queryset = queryset.order_by('club__name', 'name')
        elif order_by == 'sport':
            queryset = queryset.order_by('club__sport__name', 'club__name', 'name')
        else:  # default to name
            queryset = queryset.order_by('name')
        
        return queryset

    def get_context_data(self, **kwargs):
        from django.db.models import F, Min, Max, Avg
        
        context = super().get_context_data(**kwargs)
        
        # Filter options
        context['sports'] = SASSport.objects.filter(is_active=True, club_count__gt=0).order_by('name')
        context['clubs'] = SASClub.objects.filter(is_active=True, product_count__gt=0).select_related('sport').order_by('sport__name', 'name')
        
        # Current filter values
        context['current_sport'] = self.request.GET.get('sport', '')
        context['current_club'] = self.request.GET.get('club', '')
        context['current_search'] = self.request.GET.get('search', '')
        context['current_stock_status'] = self.request.GET.get('stock_status', '')
        context['current_order'] = self.request.GET.get('order_by', 'name')
        context['featured_only'] = self.request.GET.get('featured', 'false').lower() == 'true'
        context['on_sale_only'] = self.request.GET.get('on_sale', 'false').lower() == 'true'
        context['min_price'] = self.request.GET.get('min_price', '')
        context['max_price'] = self.request.GET.get('max_price', '')
        
        # Statistics
        all_products = SASProduct.objects.available()
        context['stats'] = {
            'total_products': all_products.count(),
            'in_stock': SASProduct.objects.in_stock().count(),
            'featured': all_products.filter(featured=True).count(),
            'on_sale': SASProduct.objects.on_sale().count(),
        }
        
        # Price range for the entire dataset
        products_with_prices = all_products.filter(price__gt=0)
        if products_with_prices.exists():
            prices = products_with_prices.aggregate(
                min_price=Min('price'),
                max_price=Max('price'),
                avg_price=Avg('price')
            )
            context['price_stats'] = prices
            # Add average_price for template compatibility with LOTTO design
            context['average_price'] = prices['avg_price'] or 0
        else:
            context['average_price'] = 0
        
        return context


def sas_club_search_ajax(request):
    """AJAX endpoint for SAS club search suggestions"""
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    # Use clubs_only() to filter out schools and generic categories
    clubs = SASClub.objects.clubs_only().filter(
        Q(name__icontains=query) |
        Q(sport__name__icontains=query) |
        Q(contact_person__icontains=query) |
        Q(city__icontains=query)
    ).select_related('sport').values(
        'slug', 'name', 'sport__name', 'sport__slug', 'product_count'
    )[:10]
    
    results = list(clubs)
    return JsonResponse({'results': results})


def sas_product_search_ajax(request):
    """AJAX endpoint for SAS product search suggestions"""
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    products = SASProduct.objects.filter(
        Q(name__icontains=query) & Q(stock_status__in=['instock', 'onbackorder'])
    ).select_related('club__sport').values(
        'slug', 'name', 'club__name', 'club__sport__name', 'price', 'featured'
    )[:10]
    
    results = list(products)
    return JsonResponse({'results': results})


class LottoProductDetailView(ClubProductAuditMixin, DetailView):
    """Detail view for LOTTO products with Stanley-inspired layout"""
    # model is set in get_queryset() using LottoProduct
    template_name = 'clubs/lotto_product_detail.html'
    context_object_name = 'product'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        # Only show LOTTO products that are published
        return LottoProduct.objects.filter(
            stock_status__in=['instock', 'outofstock', 'onbackorder']
        ).prefetch_related('variations')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        
        # Get the category for this product (for breadcrumbs and navigation)
        # LottoProduct has a single category (ForeignKey), not multiple categories
        primary_category = product.category
        context['primary_category'] = primary_category
        
        # Add product variations with stock information
        context['variations'] = product.variations.all()
        
        # Add stock quantity information for single-variant products
        # Try to find corresponding LottoProduct with detailed stock data
        stock_quantity = 0
        manage_stock = False
        
        try:
            from .models_lotto import LottoProduct
            lotto_product = LottoProduct.objects.get(woo_product_id=product.woo_product_id)
            if lotto_product.manage_stock and lotto_product.stock_quantity is not None:
                stock_quantity = lotto_product.stock_quantity
                manage_stock = True
            elif not product.has_variations and product.stock_status == 'instock':
                # For single-variant products without specific stock data, provide a default quantity
                stock_quantity = 25  # Default stock for simple products
                manage_stock = True
        except LottoProduct.DoesNotExist:
            # Fallback for products not in LottoProduct model
            if not product.has_variations and product.stock_status == 'instock':
                # Provide reasonable default for single-variant products
                stock_quantity = 25  # Default stock for simple products
                manage_stock = True
        
        context['stock_quantity'] = stock_quantity
        context['manage_stock'] = manage_stock
        
        # Add available sizes and colors from variations
        variations = product.variations.all()
        context['available_sizes'] = list(set(
            var.variation_value.split(' - ')[0] if ' - ' in var.variation_value 
            else var.variation_value for var in variations
            if var.variation_type in ['size', 'Size']
        ))
        context['available_colors'] = list(set(
            var.variation_value.split(' - ')[-1] if ' - ' in var.variation_value 
            else var.variation_value for var in variations
            if var.variation_type in ['color', 'Color']
        ))
        
        # Determine if this is a size-only product (has sizes but no colors or other variations)
        variation_types = set(var.variation_type.lower() for var in variations)
        has_size_variations = any(vtype in ['size', 'sizing'] for vtype in variation_types)
        has_color_variations = any(vtype in ['color', 'colour'] for vtype in variation_types)
        has_other_variations = any(vtype not in ['size', 'sizing', 'color', 'colour'] for vtype in variation_types)
        
        is_size_only_product = has_size_variations and not has_color_variations and not has_other_variations
        context['is_size_only_product'] = is_size_only_product
        
        # For size-only products, get size-specific stock information from LottoProduct
        if is_size_only_product:
            size_stock_info = []
            try:
                from .models_lotto import LottoProduct
                lotto_product = LottoProduct.objects.get(woo_product_id=product.woo_product_id)
                
                # Get size variations with stock data
                for size in context['available_sizes']:
                    # Try to find stock data for this size
                    size_variation = variations.filter(
                        variation_type__iexact='size',
                        variation_value__icontains=size
                    ).first()
                    
                    if size_variation and hasattr(size_variation, 'stock_quantity'):
                        stock_quantity = size_variation.stock_quantity or 0
                    else:
                        # Default stock for available sizes
                        stock_quantity = 25  # Default stock amount
                    
                    size_stock_info.append({
                        'size': size,
                        'stock_quantity': stock_quantity,
                        'is_available': stock_quantity > 0
                    })
                        
            except LottoProduct.DoesNotExist:
                # Fallback with default stock for all sizes
                for size in context['available_sizes']:
                    size_stock_info.append({
                        'size': size,
                        'stock_quantity': 25,  # Default stock
                        'is_available': True
                    })
            
            context['size_stock_info'] = size_stock_info
        
        # Add related products from same club
        if primary_category and primary_category.club:
            context['related_products'] = LottoProduct.objects.filter(
                category__club=primary_category.club,
                stock_status__in=['instock', 'onbackorder']
            ).exclude(id=product.id).select_related('category')[:4]
        else:
            context['related_products'] = []
        
        # Add breadcrumbs
        breadcrumbs = [
            {'name': 'Home', 'url': '/'},
            {'name': 'LOTTO Clubs', 'url': '/clubs/lotto/'},
        ]
        
        if primary_category and primary_category.club:
            breadcrumbs.extend([
                {'name': primary_category.club.name, 'url': f'/clubs/club/{primary_category.club.slug}/'},
                {'name': primary_category.name, 'url': f'/clubs/category/{primary_category.slug}/'},
            ])
        
        breadcrumbs.append({'name': product.name})
        context['breadcrumbs'] = breadcrumbs
        
        return context


class SASProductDetailView(ClubProductAuditMixin, DetailView):
    """Detail view for SAS products with comprehensive inventory management"""
    model = SASProduct
    template_name = 'clubs/sas_product_detail.html'
    context_object_name = 'product'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    
    def get_queryset(self):
        # Show SAS products that are published with related data
        return SASProduct.objects.filter(
            stock_status__in=['instock', 'outofstock', 'onbackorder']
        ).select_related('club__sport').prefetch_related('variations')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        
        # Add product variations with stock information
        context['variations'] = product.variations.all()
        
        # Add stock quantity information for single-variant products
        stock_quantity = 0
        manage_stock = False
        
        # For SAS products, provide stock management similar to LOTTO
        # Use calculated_stock_status for variable products to ensure consistency
        effective_stock_status = product.calculated_stock_status if product.has_variations else product.stock_status

        if not product.has_variations and effective_stock_status == 'instock':
            # For single-variant products without specific stock data, provide a default quantity
            stock_quantity = 25  # Default stock for simple products
            manage_stock = True
        elif hasattr(product, 'stock_quantity') and product.stock_quantity is not None:
            stock_quantity = product.stock_quantity
            manage_stock = True

        context['stock_quantity'] = stock_quantity
        context['manage_stock'] = manage_stock
        context['effective_stock_status'] = effective_stock_status  # Pass calculated status to template

        # Add available sizes and colors from variations
        variations = product.variations.all()
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
        
        # Determine if this is a size-only product (has sizes but no colors or other variations)
        variation_types = set(var.variation_type.lower() for var in variations)
        has_size_variations = any(vtype in ['size', 'sizing'] for vtype in variation_types)
        has_color_variations = any(vtype in ['color', 'colour'] for vtype in variation_types)
        has_other_variations = any(vtype not in ['size', 'sizing', 'color', 'colour'] for vtype in variation_types)
        
        is_size_only_product = has_size_variations and not has_color_variations and not has_other_variations
        context['is_size_only_product'] = is_size_only_product
        
        # For size-only products, get size-specific stock information
        if is_size_only_product:
            size_stock_info = []
            
            # Get size variations with stock data
            for size in context['available_sizes']:
                # Try to find stock data for this size
                size_variation = variations.filter(
                    variation_type__iexact='size',
                    variation_value__icontains=size
                ).first()
                
                if size_variation and hasattr(size_variation, 'stock_quantity'):
                    stock_quantity_size = size_variation.stock_quantity or 0
                else:
                    # Default stock for available sizes
                    stock_quantity_size = 25  # Default stock amount
                
                size_stock_info.append({
                    'size': size,
                    'stock_quantity': stock_quantity_size,
                    'is_available': stock_quantity_size > 0
                })
            
            context['size_stock_info'] = size_stock_info
        
        # Add related products from same club
        context['related_products'] = SASProduct.objects.filter(
            club=product.club,
            stock_status__in=['instock', 'onbackorder']
        ).exclude(id=product.id).select_related('club__sport')[:4]
        
        # Add breadcrumbs with SAS-specific navigation
        breadcrumbs = [
            {'name': 'Home', 'url': '/'},
            {'name': 'SAS Clubs', 'url': '/clubs/sas/'},
        ]
        
        if product.club and product.club.sport:
            breadcrumbs.extend([
                {'name': product.club.sport.name, 'url': f'/clubs/sas/sports/'},
                {'name': product.club.name, 'url': f'/clubs/sas/club/{product.club.slug}/'},
            ])
        
        breadcrumbs.append({'name': product.name})
        context['breadcrumbs'] = breadcrumbs
        
        return context


# ===============================
# PRODUCT VARIATION API ENDPOINTS
# ===============================

def _parse_lotto_combination_attributes(attributes):
    """
    Parse LOTTO product attributes that may contain combination variations 
    like "2XL - Black" and split them into separate size and color variations.
    
    Args:
        attributes: Product attributes from WooCommerce (list of dicts)
        
    Returns:
        dict: Parsed variations with grouped_variations structure
    """
    if not attributes or not isinstance(attributes, list):
        return None
    
    parsed_variations = {
        'variations': [],
        'grouped_variations': {}
    }
    
    # Known size patterns to help identify sizes in combinations
    size_patterns = [
        'XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL', 
        '6', '8', '10', '12', '14', '16', '18', '20',
        '0', '2', '4', '6', '8', '10', '12', '14',
        'SMALL', 'MEDIUM', 'LARGE', 'EXTRA LARGE'
    ]
    
    # Known color patterns
    color_patterns = [
        'BLACK', 'WHITE', 'RED', 'BLUE', 'GREEN', 'YELLOW', 'ORANGE', 
        'PURPLE', 'PINK', 'GREY', 'GRAY', 'NAVY', 'MAROON', 'TURQUOISE',
        'FLURO YELLOW', 'ROYAL', 'LIME', 'TEAL', 'BROWN', 'SILVER', 'GOLD'
    ]
    
    unique_sizes = set()
    unique_colors = set()
    variation_id_counter = 1
    
    for attr in attributes:
        if not isinstance(attr, dict) or 'options' not in attr:
            continue
            
        attr_name = attr.get('name', '').lower()
        options = attr.get('options', [])
        
        # Check if this is a size attribute with combination values
        if 'size' in attr_name and options:
            for option in options:
                if not isinstance(option, str):
                    continue
                    
                # Check if this option contains a combination pattern (e.g., "2XL - Black")
                if ' - ' in option:
                    parts = [part.strip() for part in option.split(' - ')]
                    if len(parts) == 2:
                        # Try to identify which part is size and which is color
                        part1_upper = parts[0].upper()
                        part2_upper = parts[1].upper()
                        
                        # Check if first part looks like a size
                        is_part1_size = any(size in part1_upper for size in size_patterns)
                        is_part2_color = any(color in part2_upper for color in color_patterns)
                        
                        if is_part1_size and is_part2_color:
                            # parts[0] is size, parts[1] is color
                            unique_sizes.add(parts[0])
                            unique_colors.add(parts[1])
                        elif any(color in part1_upper for color in color_patterns) and any(size in part2_upper for size in size_patterns):
                            # parts[0] is color, parts[1] is size
                            unique_colors.add(parts[0])
                            unique_sizes.add(parts[1])
                        else:
                            # Fallback: assume first is size, second is color
                            unique_sizes.add(parts[0])
                            unique_colors.add(parts[1])
                            
                        # Create individual variation records for tracking
                        parsed_variations['variations'].append({
                            'id': f'size-color-{variation_id_counter}',
                            'type': 'combination',
                            'value': option,
                            'size': parts[0] if is_part1_size and is_part2_color else parts[1] if any(size in part2_upper for size in size_patterns) else parts[0],
                            'color': parts[1] if is_part1_size and is_part2_color else parts[0] if any(color in part1_upper for color in color_patterns) else parts[1],
                            'is_in_stock': True,  # Default to available
                            'is_available': True
                        })
                        variation_id_counter += 1
                else:
                    # Single size value
                    unique_sizes.add(option)
                    parsed_variations['variations'].append({
                        'id': f'size-{variation_id_counter}',
                        'type': 'size',
                        'value': option,
                        'is_in_stock': True,
                        'is_available': True
                    })
                    variation_id_counter += 1
        
        # Handle explicit color attributes
        elif 'color' in attr_name or 'colour' in attr_name:
            for option in options:
                if isinstance(option, str):
                    unique_colors.add(option)
                    parsed_variations['variations'].append({
                        'id': f'color-{variation_id_counter}',
                        'type': 'color',
                        'value': option,
                        'is_in_stock': True,
                        'is_available': True
                    })
                    variation_id_counter += 1
    
    # Create grouped variations if we found combinations
    if unique_sizes or unique_colors:
        if unique_sizes:
            parsed_variations['grouped_variations']['size'] = []
            for size in sorted(unique_sizes):
                parsed_variations['grouped_variations']['size'].append({
                    'id': f'size-{size.lower().replace(" ", "-")}',
                    'value': size,
                    'is_available': True,
                    'type': 'size'
                })
        
        if unique_colors:
            parsed_variations['grouped_variations']['color'] = []
            for color in sorted(unique_colors):
                parsed_variations['grouped_variations']['color'].append({
                    'id': f'color-{color.lower().replace(" ", "-")}',
                    'value': color,
                    'is_available': True,
                    'type': 'color'
                })
        
        return parsed_variations
    
    return None


def _parse_lotto_combination_variations(variations_data):
    """
    Parse LOTTO product variations that may contain combination variation_values 
    like "2XL - Black" and split them into separate size and color grouped variations.
    
    Args:
        variations_data: Product variations data with variations array
        
    Returns:
        dict: Enhanced variations data with properly grouped combinations
    """
    if not variations_data or not isinstance(variations_data, dict):
        return variations_data
    
    variations = variations_data.get('variations', [])
    if not variations:
        return variations_data
    
    # Known size patterns to help identify sizes in combinations
    size_patterns = [
        'XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL', 
        '6', '8', '10', '12', '14', '16', '18', '20',
        '0', '2', '4', '6', '8', '10', '12', '14',
        'SMALL', 'MEDIUM', 'LARGE', 'EXTRA LARGE'
    ]
    
    # Known color patterns
    color_patterns = [
        'BLACK', 'WHITE', 'RED', 'BLUE', 'GREEN', 'YELLOW', 'ORANGE', 
        'PURPLE', 'PINK', 'GREY', 'GRAY', 'NAVY', 'MAROON', 'TURQUOISE',
        'FLURO YELLOW', 'ROYAL', 'LIME', 'TEAL', 'BROWN', 'SILVER', 'GOLD'
    ]
    
    unique_sizes = set()
    unique_colors = set()
    has_combinations = False
    
    # Analyze variations to see if any contain combinations
    for variation in variations:
        variation_value = variation.get('value', '')
        variation_type = variation.get('type', '')
        
        # Check if this variation contains a combination pattern
        if ' - ' in variation_value and variation_type in ['size', 'combination']:
            has_combinations = True
            parts = [part.strip() for part in variation_value.split(' - ')]
            if len(parts) == 2:
                # Try to identify which part is size and which is color
                part1_upper = parts[0].upper()
                part2_upper = parts[1].upper()
                
                # Check if first part looks like a size
                is_part1_size = any(size in part1_upper for size in size_patterns)
                is_part2_color = any(color in part2_upper for color in color_patterns)
                
                if is_part1_size and is_part2_color:
                    # parts[0] is size, parts[1] is color
                    unique_sizes.add(parts[0])
                    unique_colors.add(parts[1])
                elif any(color in part1_upper for color in color_patterns) and any(size in part2_upper for size in size_patterns):
                    # parts[0] is color, parts[1] is size
                    unique_colors.add(parts[0])
                    unique_sizes.add(parts[1])
                else:
                    # Fallback: assume first is size, second is color
                    unique_sizes.add(parts[0])
                    unique_colors.add(parts[1])
        elif variation_type == 'size':
            unique_sizes.add(variation_value)
        elif variation_type == 'color':
            unique_colors.add(variation_value)
    
    # If we found combinations, create proper grouped variations
    if has_combinations and (unique_sizes or unique_colors):
        grouped_variations = {}
        
        if unique_sizes:
            grouped_variations['size'] = []
            for size in sorted(unique_sizes):
                grouped_variations['size'].append({
                    'id': f'size-{size.lower().replace(" ", "-")}',
                    'value': size,
                    'is_available': True,
                    'type': 'size'
                })
        
        if unique_colors:
            grouped_variations['color'] = []
            for color in sorted(unique_colors):
                grouped_variations['color'].append({
                    'id': f'color-{color.lower().replace(" ", "-")}',
                    'value': color,
                    'is_available': True,
                    'type': 'color'
                })
        
        # Return enhanced data with proper groupings
        enhanced_data = variations_data.copy()
        enhanced_data['grouped_variations'] = grouped_variations
        return enhanced_data
    
    # If no combinations found, return original data
    return variations_data

@csrf_exempt
@require_http_methods(["GET"])
def product_variations_api(request, product_id, store_type=None):
    """
    API endpoint to get all variation data for a product.
    
    URL: /api/products/{product_id}/variations/ or /api/{store_type}/product/{product_id}/variations/
    """
    try:
        # Validate product_id is positive integer
        if product_id <= 0:
            return JsonResponse({
                'success': False,
                'error': 'Invalid product ID',
                'error_code': 'INVALID_PRODUCT_ID'
            }, status=400)
        
        # Try to get product based on store_type or fallback to generic lookup
        product = None
        
        if store_type and store_type.upper() == 'SAS':
            # Look for SAS product - try Django ID first, then WooCommerce ID
            try:
                from .models_sas import SASProduct
                try:
                    product = SASProduct.objects.get(id=product_id)
                except SASProduct.DoesNotExist:
                    product = SASProduct.objects.get(woo_product_id=product_id)
            except SASProduct.DoesNotExist:
                pass
        
        if not product and (not store_type or store_type.upper() == 'LOTTO'):
            # Look for LOTTO product - try Django ID first, then WooCommerce ID
            try:
                try:
                    product = LottoProduct.objects.get(id=product_id)
                except LottoProduct.DoesNotExist:
                    product = LottoProduct.objects.get(woo_product_id=product_id)
            except LottoProduct.DoesNotExist:
                pass
        
        if not product:
            # No product found in either LOTTO or SAS models
            return JsonResponse({
                'success': False,
                'error': 'Product not found in LOTTO or SAS stores',
                'error_code': 'PRODUCT_NOT_FOUND'
            }, status=404)
        
        # Check if product has variations
        has_variations = getattr(product, 'has_variations', False)
        
        # Special handling for LOTTO products that might have combination attributes
        if not has_variations and (store_type is None or store_type.upper() == 'LOTTO'):
            # Check if this is a regular Product with attributes that might contain combination variations
            if hasattr(product, 'attributes') and product.attributes:
                # Parse attributes for LOTTO combination variations
                parsed_variations = _parse_lotto_combination_attributes(product.attributes)
                if parsed_variations:
                    # Return parsed combination variations
                    return JsonResponse({
                        'success': True,
                        'product_id': product_id,
                        'product_name': getattr(product, 'name', 'Unknown Product'),
                        'base_price': float(getattr(product, 'price', 0)),
                        'variations': parsed_variations['variations'],
                        'grouped_variations': parsed_variations['grouped_variations'],
                        'total_variations': len(parsed_variations['variations'])
                    })
        
        if not has_variations:
            # For single-variant products, include stock information
            stock_status = getattr(product, 'stock_status', 'instock')
            stock_quantity = getattr(product, 'stock_quantity', 0)
            manage_stock = getattr(product, 'manage_stock', False)
            is_in_stock = stock_status == 'instock'
            
            return JsonResponse({
                'success': True,
                'product_id': product_id,
                'variations': [],
                'grouped_variations': {},
                'base_price': float(getattr(product, 'price', 0)),
                'data': {
                    'product_id': product_id,
                    'has_variations': False,
                    'stock_status': stock_status,
                    'stock_quantity': stock_quantity if manage_stock else 0,
                    'is_in_stock': is_in_stock,
                    'manage_stock': manage_stock,
                    'message': 'This product does not have variations'
                }
            })
        
        # Get variation data
        if hasattr(product, 'get_variation_data_for_frontend'):
            variation_data = product.get_variation_data_for_frontend()
        else:
            # Fallback for products without variation support
            variation_data = {
                'product_id': product_id,
                'variations': [],
                'grouped_variations': {},
                'base_price': float(getattr(product, 'price', 0)),
                'has_variations': False
            }
        
        # Apply LOTTO combination parsing if this is a LOTTO product or no store type specified
        if (store_type is None or store_type.upper() == 'LOTTO') and variation_data.get('variations'):
            variation_data = _parse_lotto_combination_variations(variation_data)
        
        # Ensure the response has the structure the frontend expects
        response_data = {
            'success': True,
            'product_id': product_id,
            'variations': variation_data.get('variations', []),
            'grouped_variations': variation_data.get('grouped_variations', {}),
            'base_price': float(getattr(product, 'price', 0)),
        }
        
        # If grouped_variations is empty, create it from variations array (backward compatibility)
        if not response_data['grouped_variations'] and response_data['variations']:
            response_data['grouped_variations'] = {}
            for variation in response_data['variations']:
                var_type = variation.get('type')
                if var_type:
                    if var_type not in response_data['grouped_variations']:
                        response_data['grouped_variations'][var_type] = []
                    
                    # Format variation for frontend
                    # For SAS products, colors should always be selectable regardless of stock
                    # Stock information is shown in the size tiles instead
                    is_available = variation.get('is_in_stock', True)
                    if var_type in ['color', 'colour'] and store_type == 'sas':
                        is_available = True  # Always allow color selection for SAS

                    response_data['grouped_variations'][var_type].append({
                        'id': variation.get('id'),
                        'value': variation.get('value'),
                        'is_available': is_available,
                        'type': var_type
                    })
        
        # Also include the original data structure for backward compatibility
        response_data['data'] = variation_data
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Failed to get product variations: {str(e)}',
            'error_code': 'VARIATIONS_FETCH_FAILED'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def check_variation_availability(request, product_id, store_type=None):
    """
    API endpoint to check availability for specific variation selection.
    
    URL: /api/products/{product_id}/check-availability/ or /api/{store_type}/product/{product_id}/check-availability/
    POST data: JSON with selected attributes
    """
    try:
        # Try to get product based on store_type or fallback to generic lookup
        product = None
        
        if store_type and store_type.upper() == 'SAS':
            # Look for SAS product - try Django ID first, then WooCommerce ID
            try:
                from .models_sas import SASProduct
                try:
                    product = SASProduct.objects.get(id=product_id)
                except SASProduct.DoesNotExist:
                    product = SASProduct.objects.get(woo_product_id=product_id)
            except SASProduct.DoesNotExist:
                pass
        
        if not product and (not store_type or store_type.upper() == 'LOTTO'):
            # Look for LOTTO product - try Django ID first, then WooCommerce ID
            try:
                try:
                    product = LottoProduct.objects.get(id=product_id)
                except LottoProduct.DoesNotExist:
                    product = LottoProduct.objects.get(woo_product_id=product_id)
            except LottoProduct.DoesNotExist:
                pass
        
        if not product:
            # No product found in either LOTTO or SAS models
            return JsonResponse({
                'success': False,
                'error': 'Product not found in LOTTO or SAS stores',
                'error_code': 'PRODUCT_NOT_FOUND'
            }, status=404)
        
        # Parse request data
        try:
            selection = json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data',
                'error_code': 'INVALID_JSON'
            }, status=400)
        
        # Get available variations for current selection
        available_variations = product.get_available_variations_for_selection(**selection)
        
        # Get stock for current combination
        combination_stock = product.get_variation_combination_stock(**selection)
        is_available = product.is_variation_combination_available(**selection)
        
        return JsonResponse({
            'success': True,
            'product_id': product_id,
            'selection': selection,
            'combination_stock': combination_stock,
            'is_available': is_available,
            'available_variations': available_variations
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Failed to check availability: {str(e)}',
            'error_code': 'AVAILABILITY_CHECK_FAILED'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def get_variation_details(request, product_id, store_type=None):
    """
    API endpoint to get detailed info for a specific variation combination.
    
    URL: /api/products/{product_id}/variation-details/ or /api/{store_type}/product/{product_id}/variation-details/
    POST data: JSON with complete attribute selection
    """
    try:
        # Try to get product based on store_type or fallback to generic lookup
        product = None
        variation_model = None
        
        if store_type and store_type.upper() == 'SAS':
            # Look for SAS product
            try:
                from .models_sas import SASProduct, SASProductVariation
                product = SASProduct.objects.get(woo_product_id=product_id)
                variation_model = SASProductVariation
            except SASProduct.DoesNotExist:
                pass
        
        if not product and (not store_type or store_type.upper() == 'LOTTO'):
            # Look for LOTTO product
            try:
                product = LottoProduct.objects.get(woo_product_id=product_id)
                variation_model = LottoProductVariation
            except LottoProduct.DoesNotExist:
                pass
        
        if not product:
            # No product found in either LOTTO or SAS models
            return JsonResponse({
                'success': False,
                'error': 'Product not found in LOTTO or SAS stores',
                'error_code': 'PRODUCT_NOT_FOUND'
            }, status=404)
        
        # Parse request data
        try:
            combination = json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data',
                'error_code': 'INVALID_JSON'
            }, status=400)
        
        # Get variation details for this combination
        variations = product.variations.filter(is_active=True)
        
        for attr_type, attr_value in combination.items():
            if attr_value:
                variations = variations.filter(
                    variation_type=attr_type,
                    variation_value=attr_value
                )
        
        if variations.exists():
            # Get the first matching variation
            variation = variations.first()
            from django.db.models import Sum
            
            total_stock = variations.aggregate(
                total=Sum('stock_quantity')
            )['total'] or 0
            
            variation_details = {
                'variation_id': variation.id,
                'stock': total_stock,
                'price_modifier': float(variation.price_modifier),
                'final_price': float(variation.final_price),
                'sku_suffix': variation.sku_suffix,
                'full_sku': variation.full_sku,
                'is_available': total_stock > 0,
                'image': variation.effective_image_url,
                'attributes': variation.attributes or {},
                'combination': combination
            }
            
            return JsonResponse({
                'success': True,
                'product_id': product_id,
                'data': variation_details
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'No matching variation found',
                'error_code': 'VARIATION_NOT_FOUND',
                'combination': combination
            }, status=404)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Failed to get variation details: {str(e)}',
            'error_code': 'VARIATION_DETAILS_FAILED'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_available_options(request, product_id, attribute_type, store_type=None):
    """
    API endpoint to get available options for a specific attribute type.
    
    URL: /api/products/{product_id}/options/{attribute_type}/
    Query params: Current selection as GET parameters
    """
    try:
        # Try to get LOTTO product
        product = None
        try:
            product = LottoProduct.objects.get(id=product_id)
        except LottoProduct.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Product not found in LOTTO store',
                'error_code': 'PRODUCT_NOT_FOUND'
            }, status=404)
        
        # Validate attribute type
        valid_types = ['size', 'color', 'material', 'style', 'gender', 'age_group']
        if attribute_type not in valid_types:
            return JsonResponse({
                'success': False,
                'error': f'Invalid attribute type. Must be one of: {", ".join(valid_types)}',
                'error_code': 'INVALID_ATTRIBUTE_TYPE'
            }, status=400)
        
        # Get current selection from query parameters
        selection = {}
        for attr_type in valid_types:
            value = request.GET.get(attr_type)
            if value:
                selection[attr_type] = value
        
        # Get available variations
        available_variations = product.get_available_variations_for_selection(**selection)
        
        # Extract options for the requested attribute type
        options = available_variations.get(attribute_type, [])
        
        return JsonResponse({
            'success': True,
            'product_id': product_id,
            'attribute_type': attribute_type,
            'current_selection': selection,
            'options': options
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Failed to get available options: {str(e)}',
            'error_code': 'OPTIONS_FETCH_FAILED'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def check_stock_api(request):
    """
    API endpoint to check stock for a specific variation combination.
    
    URL: /api/product/check-stock/
    POST data: JSON with product_id, product_type, and variations
    """
    try:
        # Parse request data
        try:
            data = json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data',
                'error_code': 'INVALID_JSON'
            }, status=400)
        
        product_id = data.get('product_id')
        product_type = data.get('product_type', '').lower()
        variations = data.get('variations', {})
        
        if not product_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing product_id',
                'error_code': 'MISSING_PRODUCT_ID'
            }, status=400)
        
        # Get product based on type
        product = None
        
        if product_type == 'sas':
            try:
                from .models_sas import SASProduct
                product = SASProduct.objects.get(woo_product_id=product_id)
            except SASProduct.DoesNotExist:
                pass
        
        if not product and product_type == 'lotto':
            try:
                product = LottoProduct.objects.get(woo_product_id=product_id)
            except LottoProduct.DoesNotExist:
                pass
        
        if not product:
            # No product found in either LOTTO or SAS models
            return JsonResponse({
                'success': False,
                'error': 'Product not found in LOTTO or SAS stores',
                'error_code': 'PRODUCT_NOT_FOUND'
            }, status=404)
        
        # Check stock for variation combination
        is_available = True
        stock_status = 'instock'
        stock_quantity = 0
        
        # If product has variation checking methods, use them
        if hasattr(product, 'is_variation_combination_available') and variations:
            is_available = product.is_variation_combination_available(**variations)
            
        if hasattr(product, 'get_variation_combination_stock') and variations:
            stock_info = product.get_variation_combination_stock(**variations)
            if isinstance(stock_info, dict):
                stock_status = stock_info.get('status', 'instock')
                stock_quantity = stock_info.get('quantity', 0)
            elif isinstance(stock_info, (int, float)):
                stock_quantity = stock_info
                stock_status = 'instock' if stock_quantity > 0 else 'outofstock'
            elif stock_info is None:
                # Handle None case - no specific quantity tracked but status-based availability
                stock_status = product.stock_status
                is_available = stock_status in ['instock', 'onbackorder']
                # For SAS products without specific stock tracking, show status-only availability
                stock_quantity = None  # Use None to indicate status-only (not zero)
        elif variations:
            # Fallback: if product doesn't have variation checking, assume unavailable
            is_available = False
            stock_status = 'outofstock'
            stock_quantity = 0
        else:
            # No variations specified - check overall product stock status
            if hasattr(product, 'calculated_stock_status'):
                stock_status = product.calculated_stock_status
                is_available = stock_status in ['instock', 'onbackorder']
            else:
                stock_status = product.stock_status
                is_available = stock_status in ['instock', 'onbackorder']
            stock_quantity = getattr(product, 'total_stock', 0) or getattr(product, 'stock_quantity', 0) or 0
        
        return JsonResponse({
            'success': True,
            'is_available': is_available,
            'stock_status': stock_status,
            'stock_quantity': stock_quantity,
            'product_id': product_id,
            'variations': variations
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Failed to check stock: {str(e)}',
            'error_code': 'STOCK_CHECK_FAILED'
        }, status=500)


# =============================================================================
# API Endpoints for Product Variations and Stock Checking
# =============================================================================

@csrf_exempt
@require_http_methods(["GET"])
def lotto_product_variations_api(request, product_id):
    """
    API endpoint to get product variations with stock information for LOTTO products
    """
    try:
        from .models_lotto import LottoProduct, LottoProductVariation
        
        product = get_object_or_404(LottoProduct, id=product_id)
        variations = LottoProductVariation.objects.filter(
            product=product, 
            is_active=True
        ).select_related('product')
        
        variations_data = []
        for variation in variations:
            variations_data.append({
                'id': variation.id,
                'type': variation.variation_type,
                'value': variation.variation_value,
                'price_modifier': float(variation.price_modifier),
                'final_price': float(variation.final_price),
                'stock_quantity': variation.stock_quantity,
                'stock_status': variation.stock_status,
                'sku': variation.full_sku,
                'image_url': variation.effective_image if variation.effective_image else None,
                'is_available': variation.stock_status in ['instock', 'onbackorder'],
                'attributes': variation.attributes or {}
            })
        
        # Group variations by type for easier frontend handling
        grouped_variations = {}
        for variation in variations_data:
            var_type = variation['type']
            if var_type not in grouped_variations:
                grouped_variations[var_type] = []
            grouped_variations[var_type].append(variation)
        
        return JsonResponse({
            'success': True,
            'product_id': product_id,
            'product_name': product.name,
            'base_price': float(product.price),
            'variations': variations_data,
            'grouped_variations': grouped_variations,
            'total_variations': len(variations_data)
        })
        
    except Exception as e:
        logger.error(f"Error fetching LOTTO product variations: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch product variations',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def sas_product_variations_api(request, product_id):
    """
    API endpoint to get product variations with stock information for SAS products
    Enhanced with proper ordering and filtering support
    """
    try:
        product = get_object_or_404(SASProduct, id=product_id)
        
        # Use the new variation methods for SAS products
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
                stock_quantity = variation.get('stock', 0) or 0  # Ensure we have a number, not None
                is_in_stock = variation.get('is_in_stock', stock_quantity > 0)

                # Calculate stock_status like LOTTO does
                if not variation.get('is_active', True):
                    stock_status = 'discontinued'
                elif stock_quantity and stock_quantity > 0:  # Handle None values
                    stock_status = 'instock'
                else:
                    stock_status = 'outofstock'

                # For SAS products, colors and categories should always be selectable regardless of stock
                # Stock information is shown in the size tiles instead
                is_available = is_in_stock
                if var_type in ['color', 'colour', 'age_group', 'gender']:
                    is_available = True  # Always allow color and category selection for SAS

                enhanced_variation = {
                    'id': variation['id'],
                    'type': var_type,
                    'value': variation['value'],
                    'is_available': is_available,
                    'stock_quantity': stock_quantity,
                    'stock_status': stock_status,  # Add stock_status field like LOTTO
                    'price_modifier': variation.get('price_modifier', 0.0),
                    'final_price': variation.get('final_price', float(product.effective_price)),
                    'sku_suffix': variation.get('sku_suffix', ''),
                    'image': variation.get('image', product.image_url),
                    'attributes': variation.get('attributes', {})
                }
                
                grouped_variations[var_type].append(enhanced_variation)
            
            # Sort variations in SAS-specific order: age_group/gender -> size -> color -> others
            # This matches the original site behavior where Main Category comes first
            ordered_grouped_variations = {}
            
            # Define the preferred order for SAS products - Main Category (age_group/gender) FIRST
            sas_order = ['age_group', 'gender', 'size', 'color', 'colour', 'material', 'style']
            
            # Add variations in the preferred order
            for var_type in sas_order:
                if var_type in grouped_variations:
                    ordered_grouped_variations[var_type] = _sort_variation_values(
                        grouped_variations[var_type], var_type
                    )
            
            # Add any remaining variations not in the preferred order
            for var_type, variations in grouped_variations.items():
                if var_type not in ordered_grouped_variations:
                    ordered_grouped_variations[var_type] = _sort_variation_values(variations, var_type)
            
            grouped_variations = ordered_grouped_variations
        else:
            # No variations
            variations_data = []
            grouped_variations = {}
        
        return JsonResponse({
            'success': True,
            'product_id': product_id,
            'product_name': product.name,
            'base_price': float(product.effective_price),
            'variations': variations_data,
            'grouped_variations': grouped_variations,
            'total_variations': len(variations_data),
            'variation_order': list(grouped_variations.keys())  # For frontend reference
        })
        
    except Exception as e:
        logger.error(f"Error fetching SAS product variations: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch product variations',
            'message': str(e)
        }, status=500)


def _sort_variation_values(variations, var_type):
    """
    Helper function to sort variation values in logical order for SAS products
    """
    def sort_key(variation):
        value = variation['value'].lower()
        
        if var_type == 'size':
            # Adult sizes order
            adult_order = ['xs', 's', 'm', 'l', 'xl', '2xl', '3xl', '4xl', '5xl']
            # Kids sizes order  
            kids_order = ['4k', '6k', '8k', '10k', '12k', '14k', '16k']
            
            if value in adult_order:
                return (0, adult_order.index(value))
            elif value in kids_order:
                return (1, kids_order.index(value))
            else:
                return (2, value)  # Unknown sizes last, alphabetical
        
        elif var_type in ['age_group', 'gender']:
            # Age group/gender order: Adults first, then Kids, then others alphabetically
            age_order = ['adults', 'adult', 'kids', 'children', 'child']
            if value in age_order:
                return (0, age_order.index(value))
            else:
                return (1, value)
        
        elif var_type in ['color', 'colour']:
            # Color order: alphabetical but with common colors first
            common_colors = ['black', 'white', 'red', 'blue', 'green', 'yellow', 'navy', 'grey', 'gray']
            if value in common_colors:
                return (0, common_colors.index(value))
            else:
                return (1, value)
        
        else:
            # Default alphabetical sorting for other types
            return (0, value)
    
    return sorted(variations, key=sort_key)


@csrf_exempt
@require_http_methods(["POST"])
def check_variation_stock_api(request):
    """
    API endpoint to check stock availability for specific variation combinations
    """
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
        product_type = data.get('product_type', 'lotto')  # 'lotto' or 'sas'
        variations = data.get('variations', {})  # Dict of variation_type: value
        
        if not product_id:
            return JsonResponse({
                'success': False,
                'error': 'Product ID is required'
            }, status=400)
        
        if product_type == 'lotto':
            from .models_lotto import LottoProduct, LottoProductVariation
            
            product = get_object_or_404(LottoProduct, id=product_id)
            
            # Find matching variation
            variation_filters = Q(product=product, is_active=True)
            for var_type, var_value in variations.items():
                variation_filters &= Q(variation_type=var_type, variation_value=var_value)
            
            matching_variation = LottoProductVariation.objects.filter(variation_filters).first()
            
            if matching_variation:
                return JsonResponse({
                    'success': True,
                    'product_id': product_id,
                    'variation_id': matching_variation.id,
                    'stock_status': matching_variation.stock_status,
                    'stock_quantity': matching_variation.stock_quantity,
                    'is_available': matching_variation.stock_status in ['instock', 'onbackorder'],
                    'price': float(matching_variation.final_price),
                    'sku': matching_variation.full_sku
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Variation combination not found',
                    'stock_status': 'outofstock',
                    'is_available': False
                })
        
        elif product_type == 'sas':
            product = get_object_or_404(SASProduct, id=product_id)
            
            # Use the new variation checking methods
            if variations and product.has_variations:
                # Check for specific variation combination
                is_available = product.is_variation_combination_available(**variations)
                stock_quantity = product.get_variation_combination_stock(**variations)
                stock_status = 'instock' if stock_quantity > 0 else 'outofstock'
            else:
                # Standard product stock check - use calculated status for variable products
                if hasattr(product, 'calculated_stock_status'):
                    stock_status = product.calculated_stock_status
                    is_available = stock_status in ['instock', 'onbackorder']
                else:
                    stock_status = product.stock_status
                    is_available = stock_status in ['instock', 'onbackorder']
                stock_quantity = getattr(product, 'stock_quantity', 0) or 0
            
            return JsonResponse({
                'success': True,
                'product_id': product_id,
                'stock_status': stock_status,
                'stock_quantity': stock_quantity,
                'is_available': is_available,
                'price': float(product.effective_price),
                'sku': product.sku,
                'variations': variations
            })
        
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid product type'
            }, status=400)
    
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error checking variation stock: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to check stock',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def product_color_swatches_api(request, product_id):
    """
    API endpoint to get color swatches for a product
    """
    try:
        product_type = request.GET.get('type', 'lotto')
        
        if product_type == 'lotto':
            from .models_lotto import LottoProduct, LottoProductVariation
            
            product = get_object_or_404(LottoProduct, id=product_id)
            color_variations = LottoProductVariation.objects.filter(
                product=product,
                variation_type='color',
                is_active=True
            )
            
            colors = []
            for variation in color_variations:
                # Map color names to hex codes for swatches
                color_map = {
                    'red': '#dc3545',
                    'blue': '#007bff', 
                    'green': '#28a745',
                    'yellow': '#ffc107',
                    'black': '#343a40',
                    'white': '#ffffff',
                    'navy': '#001f3f',
                    'grey': '#6c757d',
                    'gray': '#6c757d',
                    'orange': '#fd7e14',
                    'purple': '#6f42c1',
                    'pink': '#e83e8c',
                    'brown': '#795548'
                }
                
                color_value = variation.variation_value.lower()
                hex_color = color_map.get(color_value, '#6c757d')  # Default to gray
                
                colors.append({
                    'id': variation.id,
                    'name': variation.variation_value,
                    'hex': hex_color,
                    'stock_status': variation.stock_status,
                    'is_available': variation.stock_status in ['instock', 'onbackorder'],
                    'image_url': variation.effective_image if variation.effective_image else None
                })
        
        elif product_type == 'sas':
            product = get_object_or_404(SASProduct, id=product_id)
            colors = []
            
            # Use the new variation methods
            if product.has_variations:
                # Check if product has actual SAS variations
                if hasattr(product, 'variations') and product.variations.filter(is_active=True).exists():
                    color_variations = product.variations.filter(
                        variation_type__in=['color', 'colour'],
                        is_active=True
                    )
                    
                    for variation in color_variations:
                        # Map color names to hex codes for swatches
                        color_map = {
                            'red': '#dc3545',
                            'blue': '#007bff', 
                            'green': '#28a745',
                            'yellow': '#ffc107',
                            'black': '#343a40',
                            'white': '#ffffff',
                            'navy': '#001f3f',
                            'grey': '#6c757d',
                            'gray': '#6c757d',
                            'orange': '#fd7e14',
                            'purple': '#6f42c1',
                            'pink': '#e83e8c',
                            'brown': '#795548'
                        }
                        
                        color_value = variation.variation_value.lower()
                        hex_color = color_map.get(color_value, '#6c757d')
                        
                        colors.append({
                            'id': variation.id,
                            'name': variation.variation_value,
                            'hex': hex_color,
                            'stock_status': variation.stock_status,
                            'is_available': variation.stock_quantity > 0,
                            'image_url': variation.effective_image_url
                        })
                
                else:
                    # Use attribute-based color variations
                    available_colors = product.available_colors
                    color_map = {
                        'red': '#dc3545',
                        'blue': '#007bff', 
                        'green': '#28a745',
                        'yellow': '#ffc107',
                        'black': '#343a40',
                        'white': '#ffffff',
                        'navy': '#001f3f',
                        'grey': '#6c757d',
                        'gray': '#6c757d',
                        'orange': '#fd7e14',
                        'purple': '#6f42c1',
                        'pink': '#e83e8c',
                        'brown': '#795548'
                    }
                    
                    for color in available_colors:
                        color_value = color.lower()
                        hex_color = color_map.get(color_value, '#6c757d')
                        
                        colors.append({
                            'id': f"{product_id}_color_{color}".replace(' ', '_').lower(),
                            'name': color,
                            'hex': hex_color,
                            'stock_status': product.stock_status,
                            'is_available': product.stock_status in ['instock', 'onbackorder'],
                            'image_url': product.image_url
                        })
        
        return JsonResponse({
            'success': True,
            'product_id': product_id,
            'colors': colors
        })
        
    except Exception as e:
        logger.error(f"Error fetching color swatches: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch color swatches',
            'message': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def product_color_size_stock_api(request):
    """
    API endpoint to get stock information for all sizes in a specific color.
    
    POST data:
        {
            "product_id": int,
            "product_type": "lotto" or "sas",
            "color": "color_value"
        }
    
    Returns:
        {
            "success": true,
            "color": "Black",
            "sizes": [
                {"size": "S", "stock_quantity": 5, "stock_status": "instock", "is_available": true},
                {"size": "M", "stock_quantity": 0, "stock_status": "outofstock", "is_available": false},
                ...
            ]
        }
    """
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
        product_type = data.get('product_type', 'lotto').lower()
        color_value = data.get('color')
        
        if not product_id or not color_value:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters: product_id and color',
                'error_code': 'MISSING_PARAMETERS'
            }, status=400)
        
        # Get the product based on type
        product = None
        
        if product_type == 'sas':
            try:
                from .models_sas import SASProduct
                product = SASProduct.objects.get(woo_product_id=product_id)
            except SASProduct.DoesNotExist:
                pass
        elif product_type == 'lotto':
            try:
                from .models_lotto import LottoProduct
                product = LottoProduct.objects.get(woo_product_id=product_id)
            except LottoProduct.DoesNotExist:
                pass
        
        # Fallback to generic Product model
        if not product:
            # No product found in either LOTTO or SAS models
            return JsonResponse({
                'success': False,
                'error': 'Product not found in LOTTO or SAS stores',
                'error_code': 'PRODUCT_NOT_FOUND'
            }, status=404)
        
        # Get stock information for the selected color using existing variation data
        color_stock_info = {
            'color': color_value,
            'sizes': []
        }
        
        # Try to get variation data using the same method as the working variations API
        try:
            if product_type == 'lotto':
                # For LOTTO products, use the LottoProduct model if available
                if hasattr(product, 'get_variation_data_for_frontend'):
                    variation_data = product.get_variation_data_for_frontend()
                    variations = variation_data.get('variations', [])
                    
                    # Extract variations that match the selected color
                    color_sizes = {}
                    
                    for variation in variations:
                        attributes = variation.get('attributes', {})
                        var_color = attributes.get('color', '').strip()
                        var_size = attributes.get('size', '').strip()
                        
                        if var_color.lower() == color_value.lower() and var_size:
                            stock = variation.get('stock', 0)
                            is_in_stock = variation.get('is_in_stock', False)
                            
                            color_sizes[var_size] = {
                                'size': var_size,
                                'stock_quantity': stock,
                                'stock_status': 'instock' if is_in_stock else 'outofstock',
                                'is_available': is_in_stock
                            }
                    
                    # Convert to list and sort by size
                    size_order = ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL']
                    
                    # Add sizes in order
                    for size_key in size_order:
                        if size_key in color_sizes:
                            color_stock_info['sizes'].append(color_sizes[size_key])
                    
                    # Add any remaining sizes not in the standard order
                    for size_key, size_data in color_sizes.items():
                        if size_key not in size_order:
                            color_stock_info['sizes'].append(size_data)
                            
        except Exception as e:
            # Fallback to parsing attributes if variation data method fails
            if hasattr(product, 'attributes') and product.attributes:
                parsed_variations = _parse_lotto_combination_attributes(product.attributes)
                if parsed_variations and parsed_variations.get('variations'):
                    # Extract size-stock data for the selected color
                    color_sizes = {}
                    
                    for variation in parsed_variations['variations']:
                        if (variation.get('type') == 'combination' and 
                            variation.get('color') and 
                            variation.get('color').lower() == color_value.lower()):
                            
                            size = variation.get('size')
                            if size:
                                stock_quantity = 10 if variation.get('is_available', True) else 0
                                
                                color_sizes[size] = {
                                    'size': size,
                                    'stock_quantity': stock_quantity,
                                    'stock_status': 'instock' if stock_quantity > 0 else 'outofstock',
                                    'is_available': stock_quantity > 0
                                }
                    
                    # Convert to list and sort by size
                    size_order = ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL']
                    
                    # Add sizes in order
                    for size_key in size_order:
                        if size_key in color_sizes:
                            color_stock_info['sizes'].append(color_sizes[size_key])
                    
                    # Add any remaining sizes not in the standard order
                    for size_key, size_data in color_sizes.items():
                        if size_key not in size_order:
                            color_stock_info['sizes'].append(size_data)
        
        return JsonResponse({
            'success': True,
            'product_id': product_id,
            'product_type': product_type,
            'color': color_stock_info['color'],
            'sizes': color_stock_info['sizes'],
            'total_sizes': len(color_stock_info['sizes'])
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data',
            'error_code': 'INVALID_JSON'
        }, status=400)
    except Exception as e:
        logger.error(f"Error fetching color size stock: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to fetch color size stock information',
            'message': str(e),
            'error_code': 'SERVER_ERROR'
        }, status=500)


# ============================================
# WHOLESALE SCHOOLS VIEWS
# ============================================

def wholesale_dashboard(request):
    """
    Wholesale dashboard with statistics and sync management
    """
    # Basic statistics
    total_schools = WholesaleSchool.objects.filter(is_active=True).count()
    total_categories = WholesaleCategory.objects.filter(is_active=True).count()
    total_products = WholesaleProduct.objects.filter(is_active=True).count()
    in_stock_products = WholesaleProduct.objects.filter(
        is_active=True,
        stock_status='in_stock'
    ).count()

    # Top schools by product count
    top_schools = WholesaleSchool.objects.filter(is_active=True).order_by('-total_products')[:10]

    # Last sync information
    last_sync_job = WholesaleSyncJob.objects.filter(status='completed').order_by('-completed_at').first()
    last_sync = last_sync_job.completed_at if last_sync_job else None

    # Current running sync
    running_sync = WholesaleSyncJob.objects.filter(status='running').first()

    # Recent sync stats
    recent_sync_stats = {}
    if last_sync_job:
        recent_sync_stats = {
            'schools_created': last_sync_job.schools_created,
            'schools_updated': last_sync_job.schools_updated,
            'products_created': last_sync_job.products_created,
            'products_updated': last_sync_job.products_updated,
            'categories_created': last_sync_job.categories_created,
            'categories_updated': last_sync_job.categories_updated,
        }

    context = {
        'total_schools': total_schools,
        'total_categories': total_categories,
        'total_products': total_products,
        'in_stock_products': in_stock_products,
        'top_schools': top_schools,
        'last_sync': last_sync,
        'sync_job': running_sync,
        'recent_sync_stats': recent_sync_stats,
    }

    return render(request, 'clubs/wholesale/dashboard.html', context)


class WholesaleSchoolListView(ListView):
    """
    List all wholesale schools with filtering and search
    """
    model = WholesaleSchool
    template_name = 'clubs/wholesale/school_list.html'
    context_object_name = 'schools'
    paginate_by = 18

    def get_queryset(self):
        queryset = WholesaleSchool.objects.filter(is_active=True)

        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(school_code__icontains=search_query) |
                Q(contact_person__icontains=search_query) |
                Q(email__icontains=search_query)
            )

        # Filter by city
        city = self.request.GET.get('city')
        if city:
            queryset = queryset.filter(city=city)

        # Filter by region
        region = self.request.GET.get('region')
        if region:
            queryset = queryset.filter(region=region)

        return queryset.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get distinct cities and regions for filters
        context['cities'] = WholesaleSchool.objects.filter(
            is_active=True,
            city__isnull=False
        ).exclude(city='').values_list('city', flat=True).distinct().order_by('city')

        context['regions'] = WholesaleSchool.objects.filter(
            is_active=True,
            region__isnull=False
        ).exclude(region='').values_list('region', flat=True).distinct().order_by('region')

        context['total_schools'] = WholesaleSchool.objects.filter(is_active=True).count()

        return context


class WholesaleSchoolDetailView(DetailView):
    """
    Detailed view of a wholesale school with categories and products
    """
    model = WholesaleSchool
    template_name = 'clubs/wholesale/school_detail.html'
    context_object_name = 'school'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return WholesaleSchool.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = self.get_object()

        # Get categories for this school through products
        categories_with_products = WholesaleCategory.objects.filter(
            products__school=school,
            is_active=True
        ).distinct().order_by('name')

        context['categories'] = categories_with_products

        # Get products for this school
        products = WholesaleProduct.objects.filter(
            school=school,
            is_active=True
        ).select_related('school').prefetch_related('categories').order_by('name')

        context['products'] = products

        return context


class WholesaleCategoryListView(ListView):
    """
    List all wholesale categories with filtering
    """
    model = WholesaleCategory
    template_name = 'clubs/wholesale/category_list.html'
    context_object_name = 'categories'
    paginate_by = 24

    def get_queryset(self):
        queryset = WholesaleCategory.objects.filter(is_active=True).prefetch_related('subcategories')

        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        # Filter by level
        level = self.request.GET.get('level')
        if level is not None and level.isdigit():
            queryset = queryset.filter(level=int(level))

        # Filter by minimum products
        min_products = self.request.GET.get('min_products')
        if min_products and min_products.isdigit():
            queryset = queryset.filter(product_count__gte=int(min_products))

        return queryset.order_by('level', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_categories'] = WholesaleCategory.objects.filter(is_active=True).count()
        return context


class WholesaleCategoryDetailView(DetailView):
    """
    Detailed view of a wholesale category with products
    """
    model = WholesaleCategory
    template_name = 'clubs/wholesale/category_detail.html'
    context_object_name = 'category'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return WholesaleCategory.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
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

        # Stock statistics
        context['in_stock_products'] = products.filter(stock_status='in_stock').count()
        context['out_of_stock_products'] = products.filter(stock_status='out_of_stock').count()

        return context


class WholesaleProductDetailView(DetailView):
    """
    Detailed view of a wholesale product with variations
    """
    model = WholesaleProduct
    template_name = 'clubs/wholesale/product_detail.html'
    context_object_name = 'product'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_queryset(self):
        return WholesaleProduct.objects.filter(is_active=True).select_related('school')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()

        # Get product variations
        context['variations'] = product.variations.filter(is_active=True).order_by('variation_type', 'variation_value')

        return context


@csrf_exempt
@require_http_methods(["POST"])
def wholesale_sync_execute(request):
    """
    Execute wholesale data sync from CIN7
    """
    try:
        # Check if there's already a sync running
        running_sync = WholesaleSyncJob.objects.filter(status='running').first()
        if running_sync:
            return JsonResponse({
                'success': False,
                'error': 'A sync is already running',
                'job_id': str(running_sync.id)
            })

        # Create new sync job
        sync_job = WholesaleSyncJob.objects.create(
            status='pending',
            current_step='Initializing sync...'
        )

        # Start sync in background thread
        def run_sync():
            try:
                from .services.cin7_service import CIN7Service
                from django.db import transaction
                from django.utils.text import slugify

                sync_job.status = 'running'
                sync_job.started_at = timezone.now()
                sync_job.save()

                # Initialize CIN7 service
                sync_job.current_step = 'Connecting to CIN7 API...'
                sync_job.progress_percentage = 5
                sync_job.save()

                cin7_service = CIN7Service()

                # Test connection
                if not cin7_service.test_connection():
                    raise Exception("Failed to connect to CIN7 API")

                sync_job.current_step = 'Fetching wholesale products from CIN7...'
                sync_job.progress_percentage = 15
                sync_job.save()

                # Get all wholesale products
                all_products = cin7_service.get_all_wholesale_products()
                if not all_products:
                    raise Exception("No wholesale products found in CIN7")

                sync_job.current_step = f'Processing {len(all_products)} products...'
                sync_job.progress_percentage = 30
                sync_job.save()

                # Organize products by school
                schools_data = cin7_service.organize_products_by_school(all_products)

                sync_job.current_step = f'Creating/updating {len(schools_data)} schools...'
                sync_job.progress_percentage = 50
                sync_job.save()

                # Process each school and its products
                schools_created = 0
                schools_updated = 0
                products_created = 0
                products_updated = 0
                categories_created = 0
                categories_updated = 0

                for school_name, school_data in schools_data.items():
                    with transaction.atomic():
                        # Create or update school
                        school_info = school_data['info']
                        school, created = WholesaleSchool.objects.get_or_create(
                            name=school_name,
                            defaults={
                                'slug': slugify(school_name),
                                'school_code': school_info.get('code', ''),
                                'description': school_info.get('description', ''),
                                'cin7_brand': school_info.get('brand', ''),
                                'cin7_category_path': school_info.get('category_path', ''),
                                'is_active': True,
                                'last_synced_at': timezone.now()
                            }
                        )

                        if created:
                            schools_created += 1
                        else:
                            schools_updated += 1
                            school.last_synced_at = timezone.now()
                            school.save()

                        # Process products for this school
                        for product_data in school_data['products']:
                            product, created = WholesaleProduct.objects.get_or_create(
                                cin7_id=product_data['cin7_id'],
                                defaults={
                                    'school': school,
                                    'name': product_data['name'],
                                    'slug': slugify(f"{product_data['name']}-{product_data['cin7_sku']}"),
                                    'description': product_data['description'],
                                    'short_description': product_data['short_description'],
                                    'cin7_sku': product_data['cin7_sku'],
                                    'cin7_barcode': product_data['cin7_barcode'],
                                    'cin7_brand': product_data['cin7_brand'],
                                    'cin7_supplier': product_data['cin7_supplier'],
                                    'cin7_unit_of_measure': product_data['cin7_unit_of_measure'],
                                    'wholesale_price': product_data['wholesale_price'],
                                    'retail_price': product_data['retail_price'],
                                    'cost_price': product_data['cost_price'],
                                    'stock_status': product_data['stock_status'],
                                    'quantity_available': product_data['quantity_available'],
                                    'quantity_on_hand': product_data['quantity_on_hand'],
                                    'quantity_committed': product_data['quantity_committed'],
                                    'weight': product_data['weight'],
                                    'dimensions': product_data['dimensions'],
                                    'attributes': product_data['attributes'],
                                    'image_url': product_data['image_url'],
                                    'is_active': True,
                                    'last_synced_at': timezone.now()
                                }
                            )

                            if created:
                                products_created += 1
                            else:
                                products_updated += 1
                                # Update existing product
                                for field, value in {
                                    'name': product_data['name'],
                                    'description': product_data['description'],
                                    'short_description': product_data['short_description'],
                                    'cin7_sku': product_data['cin7_sku'],
                                    'cin7_barcode': product_data['cin7_barcode'],
                                    'cin7_brand': product_data['cin7_brand'],
                                    'cin7_supplier': product_data['cin7_supplier'],
                                    'cin7_unit_of_measure': product_data['cin7_unit_of_measure'],
                                    'wholesale_price': product_data['wholesale_price'],
                                    'retail_price': product_data['retail_price'],
                                    'cost_price': product_data['cost_price'],
                                    'stock_status': product_data['stock_status'],
                                    'quantity_available': product_data['quantity_available'],
                                    'quantity_on_hand': product_data['quantity_on_hand'],
                                    'quantity_committed': product_data['quantity_committed'],
                                    'weight': product_data['weight'],
                                    'dimensions': product_data['dimensions'],
                                    'attributes': product_data['attributes'],
                                    'image_url': product_data['image_url'],
                                    'last_synced_at': timezone.now()
                                }.items():
                                    setattr(product, field, value)
                                product.save()

                sync_job.current_step = 'Creating product categories...'
                sync_job.progress_percentage = 80
                sync_job.save()

                # Get categories from CIN7
                categories_data = cin7_service.get_product_categories()
                if categories_data:
                    for category_data in categories_data:
                        # Only process wholesale school categories
                        if 'Wholesale Schools' in category_data.get('CategoryPath', ''):
                            category, created = WholesaleCategory.objects.get_or_create(
                                cin7_id=str(category_data.get('CategoryId', '')),
                                defaults={
                                    'name': category_data.get('CategoryName', ''),
                                    'slug': slugify(category_data.get('CategoryName', '')),
                                    'description': category_data.get('CategoryDescription', ''),
                                    'path': category_data.get('CategoryPath', ''),
                                    'is_active': True,
                                    'last_synced_at': timezone.now()
                                }
                            )

                            if created:
                                categories_created += 1
                            else:
                                categories_updated += 1

                sync_job.current_step = 'Finalizing sync...'
                sync_job.progress_percentage = 95
                sync_job.save()

                # Update school statistics
                for school in WholesaleSchool.objects.filter(is_active=True):
                    school.total_products = WholesaleProduct.objects.filter(
                        school=school, is_active=True
                    ).count()
                    school.active_categories = WholesaleCategory.objects.filter(
                        products__school=school, is_active=True
                    ).distinct().count()
                    school.save(update_fields=['total_products', 'active_categories'])

                # Complete sync
                sync_job.status = 'completed'
                sync_job.progress_percentage = 100
                sync_job.current_step = 'Sync completed successfully'
                sync_job.completed_at = timezone.now()

                # Update statistics with real numbers
                sync_job.schools_created = schools_created
                sync_job.schools_updated = schools_updated
                sync_job.products_created = products_created
                sync_job.products_updated = products_updated
                sync_job.categories_created = categories_created
                sync_job.categories_updated = categories_updated

                sync_job.save()

            except Exception as e:
                logger.error(f"Wholesale sync failed: {str(e)}")
                sync_job.status = 'failed'
                sync_job.current_step = f'Sync failed: {str(e)}'
                sync_job.completed_at = timezone.now()
                sync_job.errors_count = 1
                sync_job.error_messages = [str(e)]
                sync_job.save()

        # Start sync thread
        sync_thread = threading.Thread(target=run_sync)
        sync_thread.daemon = True
        sync_thread.start()

        return JsonResponse({
            'success': True,
            'message': 'Sync started successfully',
            'job_id': str(sync_job.id)
        })

    except Exception as e:
        logger.error(f"Error starting wholesale sync: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to start sync',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def wholesale_sync_status(request):
    """
    Get current wholesale sync status
    """
    try:
        # Get the most recent sync job
        sync_job = WholesaleSyncJob.objects.filter(
            status__in=['running', 'pending']
        ).order_by('-created_at').first()

        if not sync_job:
            # No running sync, get the last completed one for status
            last_sync = WholesaleSyncJob.objects.filter(
                status__in=['completed', 'failed']
            ).order_by('-created_at').first()

            if last_sync:
                return JsonResponse({
                    'status': last_sync.status,
                    'progress': 100 if last_sync.status == 'completed' else 0,
                    'current_step': last_sync.current_step,
                    'job_id': str(last_sync.id)
                })
            else:
                return JsonResponse({
                    'status': 'none',
                    'progress': 0,
                    'current_step': 'No sync jobs found'
                })

        return JsonResponse({
            'status': sync_job.status,
            'progress': sync_job.progress_percentage,
            'current_step': sync_job.current_step,
            'job_id': str(sync_job.id),
            'started_at': sync_job.started_at.isoformat() if sync_job.started_at else None
        })

    except Exception as e:
        logger.error(f"Error getting wholesale sync status: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'progress': 0,
            'current_step': f'Error: {str(e)}'
        }, status=500)


# ============================================
# WHOLESALE AJAX ENDPOINTS
# ============================================

@require_http_methods(["GET"])
def wholesale_school_search_ajax(request):
    """
    AJAX endpoint for wholesale school search
    """
    try:
        query = request.GET.get('q', '').strip()
        if len(query) < 2:
            return JsonResponse({'schools': []})

        schools = WholesaleSchool.objects.filter(
            Q(name__icontains=query) |
            Q(school_code__icontains=query) |
            Q(contact_person__icontains=query) |
            Q(email__icontains=query) |
            Q(city__icontains=query),
            is_active=True
        ).order_by('name')[:20]

        results = []
        for school in schools:
            results.append({
                'id': school.id,
                'name': school.name,
                'school_code': school.school_code,
                'contact_person': school.contact_person,
                'email': school.email,
                'city': school.city,
                'total_products': school.total_products,
                'url': school.get_absolute_url()
            })

        return JsonResponse({'schools': results})

    except Exception as e:
        logger.error(f"Error in wholesale school search: {str(e)}")
        return JsonResponse({'error': 'Search failed'}, status=500)


@require_http_methods(["GET"])
def wholesale_product_search_ajax(request):
    """
    AJAX endpoint for wholesale product search
    """
    try:
        query = request.GET.get('q', '').strip()
        school_id = request.GET.get('school_id')

        if len(query) < 2:
            return JsonResponse({'products': []})

        # Base queryset
        products = WholesaleProduct.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(cin7_sku__icontains=query) |
            Q(cin7_barcode__icontains=query),
            is_active=True
        ).select_related('school')

        # Filter by school if provided
        if school_id:
            try:
                products = products.filter(school_id=int(school_id))
            except (ValueError, TypeError):
                pass

        products = products.order_by('name')[:20]

        results = []
        for product in products:
            results.append({
                'id': product.id,
                'name': product.name,
                'school_name': product.school.name,
                'cin7_sku': product.cin7_sku,
                'wholesale_price': str(product.wholesale_price) if product.wholesale_price else None,
                'retail_price': str(product.retail_price) if product.retail_price else None,
                'stock_status': product.stock_status,
                'quantity_available': product.quantity_available,
                'is_in_stock': product.is_in_stock,
                'image_url': product.image_url,
                'slug': product.slug
            })

        return JsonResponse({'products': results})

    except Exception as e:
        logger.error(f"Error in wholesale product search: {str(e)}")
        return JsonResponse({'error': 'Search failed'}, status=500)


def api_demo_view(request):
    """
    Display API demo page for wholesale price update system.

    This view renders an interactive demo page that showcases all the API
    endpoints and provides a user-friendly interface for testing the API.
    """
    return render(request, 'clubs/api_demo.html', {
        'title': 'Wholesale Price Update API Demo',
        'api_base_url': '/api'
    })
