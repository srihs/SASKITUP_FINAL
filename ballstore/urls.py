from django.urls import path
from . import views

app_name = 'ballstore'

urlpatterns = [
    # Category list - all top-level categories
    path('', views.category_list, name='category-list'),

    # Sync trigger - start product sync from WooCommerce
    path('sync/', views.trigger_sync, name='trigger-sync'),

    # Category detail - products in specific category
    path('<slug:category_slug>/', views.category_detail, name='category-detail'),
]
