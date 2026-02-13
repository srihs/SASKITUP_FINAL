from django.urls import path
from . import views, period_views

app_name = 'stores'

urlpatterns = [
    path('', views.StoreListView.as_view(), name='store_list'),
    path('opening-hours/', views.OpeningHoursManagementView.as_view(), name='opening_hours_management'),
    path('add/', views.StoreCreateView.as_view(), name='store_create'),
    path('<int:pk>/', views.StoreDetailView.as_view(), name='store_detail'),
    path('<int:pk>/edit/', views.StoreUpdateView.as_view(), name='store_edit'),
    path('<int:pk>/delete/', views.StoreDeleteView.as_view(), name='store_delete'),
    path('<int:pk>/assign-periods/', views.StorePeriodAssignmentView.as_view(), name='store_assign_periods'),

    # Period management URLs (global, not store-specific)
    path('periods/', period_views.StorePeriodListView.as_view(), name='period_list'),
    path('periods/add/', period_views.StorePeriodCreateView.as_view(), name='period_create'),
    path('periods/<int:pk>/edit/', period_views.StorePeriodUpdateView.as_view(), name='period_edit'),
    path('periods/<int:pk>/delete/', period_views.StorePeriodDeleteView.as_view(), name='period_delete'),
]
