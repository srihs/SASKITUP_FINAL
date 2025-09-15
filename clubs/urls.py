from django.urls import path
from . import views

app_name = 'clubs'

urlpatterns = [
    # Dashboard and main views
    path('', views.ClubListView.as_view(), name='club-list'),  # /clubs/ will show the club list
    path('dashboard/', views.ClubDashboardView.as_view(), name='dashboard'),  # /clubs/dashboard/
    
    # Club type specific views - LOTTO
    path('lotto/', views.LottoClubsView.as_view(), name='lotto-clubs'),
    
    # SAS Management Section
    path('sas/', views.SASClubListView.as_view(), name='sas-clubs'),
    path('sas/dashboard/', views.SASDashboardView.as_view(), name='sas-dashboard'),
    path('sas/sports/', views.SASSportListView.as_view(), name='sas-sports'),
    path('sas/products/', views.SASProductListView.as_view(), name='sas-products'),
    path('sas/club/<slug:slug>/', views.SASClubDetailView.as_view(), name='sas-club-detail'),
    
    # Detail views
    path('club/<slug:slug>/', views.ClubDetailView.as_view(), name='club-detail'),
    path('category/<slug:slug>/', views.ClubCategoryDetailView.as_view(), name='category-detail'),
    
    # Product detail views
    path('lotto/product/<slug:slug>/', views.LottoProductDetailView.as_view(), name='lotto-product-detail'),
    path('sas/product/<slug:slug>/', views.SASProductDetailView.as_view(), name='sas-product-detail'),
    
    # AJAX endpoints
    path('ajax/search/', views.club_search_ajax, name='club-search-ajax'),
    path('ajax/sas-club-search/', views.sas_club_search_ajax, name='sas-club-search-ajax'),
    path('ajax/sas-product-search/', views.sas_product_search_ajax, name='sas-product-search-ajax'),
    
    # Product Variation API endpoints - Generic
    path('api/products/<int:product_id>/variations/', views.product_variations_api, name='product-variations-api'),
    path('api/products/<int:product_id>/check-availability/', views.check_variation_availability, name='check-variation-availability'),
    path('api/products/<int:product_id>/variation-details/', views.get_variation_details, name='get-variation-details'),
    path('api/products/<int:product_id>/options/<str:attribute_type>/', views.get_available_options, name='get-available-options'),
    
    # Product Variation API endpoints - Store Type Specific
    path('api/<str:store_type>/product/<int:product_id>/variations/', views.product_variations_api, name='store-product-variations-api'),
    path('api/<str:store_type>/product/<int:product_id>/check-availability/', views.check_variation_availability, name='store-check-variation-availability'),
    path('api/<str:store_type>/product/<int:product_id>/variation-details/', views.get_variation_details, name='store-get-variation-details'),
    path('api/<str:store_type>/product/<int:product_id>/options/<str:attribute_type>/', views.get_available_options, name='store-get-available-options'),
    
    # Stock checking endpoint
    path('api/product/check-stock/', views.check_stock_api, name='check-stock-api'),
    
    # Image proxy endpoint
    path('proxy-image/', views.proxy_image_view, name='proxy-image'),
    
    # Sync endpoints
    path('sync/lotto/', views.sync_lotto_clubs_page, name='sync-lotto-clubs-page'),
    path('sync/lotto/execute/', views.sync_lotto_clubs, name='sync-lotto-clubs'),
    path('sync/sas/execute/', views.sync_sas_clubs, name='sync-sas-clubs'),
    path('sync/status/<uuid:job_id>/', views.sync_status, name='sync-status'),
    path('sync/jobs/', views.sync_jobs_list, name='sync-jobs-list'),
    path('sync/clear-locks/', views.clear_sync_locks, name='clear-sync-locks'),
    
    # Test/Debug endpoints
    path('sync/test/', views.test_sync_endpoint, name='test-sync-endpoint'),
    
    # Settings endpoints
    path('settings/sync-management/', views.sync_management_page, name='sync-management'),
]