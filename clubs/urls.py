from django.urls import path
from . import views

app_name = 'clubs'

urlpatterns = [
    # Dashboard and main views
    path('', views.ClubListView.as_view(), name='club-list'),  # /clubs/ will show the club list
    path('dashboard/', views.ClubDashboardView.as_view(), name='dashboard'),  # /clubs/dashboard/
    
    # Club type specific views
    path('lotto/', views.LottoClubsView.as_view(), name='lotto-clubs'),
    path('sas/', views.SASClubsView.as_view(), name='sas-clubs'),
    
    # Detail views
    path('club/<slug:slug>/', views.ClubDetailView.as_view(), name='club-detail'),
    path('category/<slug:slug>/', views.ClubCategoryDetailView.as_view(), name='category-detail'),
    
    # AJAX endpoints
    path('ajax/search/', views.club_search_ajax, name='club-search-ajax'),
    
    # Image proxy endpoint
    path('proxy-image/', views.proxy_image_view, name='proxy-image'),
    
    # Sync endpoints
    path('sync/lotto/', views.sync_lotto_clubs_page, name='sync-lotto-clubs-page'),
    path('sync/lotto/execute/', views.sync_lotto_clubs, name='sync-lotto-clubs'),
    path('sync/status/<uuid:job_id>/', views.sync_status, name='sync-status'),
    path('sync/jobs/', views.sync_jobs_list, name='sync-jobs-list'),
    path('sync/clear-locks/', views.clear_sync_locks, name='clear-sync-locks'),
    
    # Test/Debug endpoints
    path('sync/test/', views.test_sync_endpoint, name='test-sync-endpoint'),
    
    # Settings endpoints
    path('settings/sync-management/', views.sync_management_page, name='sync-management'),
]