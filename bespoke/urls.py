from django.urls import path
from . import views

app_name = 'bespoke'

urlpatterns = [
    path('', views.category_list, name='category_list'),
    path('sync/', views.trigger_sync, name='trigger-sync'),
    path('sync/status/<uuid:job_id>/', views.bespoke_sync_status, name='bespoke-sync-status'),
    path('category/<slug:category_slug>/', views.category_detail, name='category_detail'),
    path('product/<slug:product_slug>/', views.product_detail, name='product_detail'),
]
