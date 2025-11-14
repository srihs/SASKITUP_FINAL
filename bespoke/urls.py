from django.urls import path
from . import views

app_name = 'bespoke'

urlpatterns = [
    path('', views.category_list, name='category_list'),
    path('sync/', views.trigger_sync, name='trigger-sync'),
    path('sync/status/<uuid:job_id>/', views.bespoke_sync_status, name='bespoke-sync-status'),
    path('category/<slug:category_slug>/', views.category_detail, name='category_detail'),
    path('product/<slug:product_slug>/', views.product_detail, name='product_detail'),

    # Addon Pricing Management API endpoints
    path('api/pricing/price/add/', views.add_addon_price, name='add-addon-price'),
    path('api/pricing/price/<int:price_id>/edit/', views.edit_addon_price, name='edit-addon-price'),
    path('api/pricing/price/<int:price_id>/delete/', views.delete_addon_price, name='delete-addon-price'),
    path('api/pricing/bulk-edit/', views.bulk_edit_addon_prices, name='bulk-edit-addon-prices'),
    path('api/pricing/export/<str:addon_type>/', views.export_addon_pricing, name='export-addon-pricing'),
]
