from django.urls import path
from . import views

app_name = 'schools'

urlpatterns = [
    # School Database main page
    path('', views.SchoolListView.as_view(), name='school_list'),

    # School detail page
    path('school/<str:school_id>/', views.SchoolDetailView.as_view(), name='school_detail'),

    # AJAX search endpoint
    path('search/', views.school_search_ajax, name='school_search_ajax'),

    # NZ Schools Sync endpoints
    path('sync/nz-schools/execute/', views.sync_nz_schools, name='sync-nz-schools'),
    path('sync/nz-schools/status/<uuid:job_id>/', views.nz_schools_sync_status, name='nz-schools-sync-status'),

    # TUS Retail Schools URLs - Main retail schools listing
    path('retail/', views.TUSRetailSchoolsView.as_view(), name='retail_schools'),
    path('retail/', views.TUSRetailSchoolsView.as_view(), name='tus_retail_schools'),  # Alternative name

    # TUS Retail Schools URLs - Location-based URLs
    path('retail/location/<slug:location_slug>/', views.TUSLocationDetailView.as_view(), name='retail_location_detail'),

    # TUS Retail Schools URLs - School-specific URLs
    path('retail/school/<slug:school_slug>/', views.TUSSchoolDetailView.as_view(), name='retail_school_detail'),
    path('retail/school/<slug:school_slug>/category/<slug:category_slug>/', views.TUSSchoolCategoryDetailView.as_view(), name='retail_school_category_detail'),

    # TUS Retail Schools URLs - General category URLs (not school-specific)
    path('retail/general/<slug:category_slug>/', views.TUSGeneralCategoryDetailView.as_view(), name='retail_general_category_detail'),

    # TUS Product detail views
    path('retail/product/<slug:slug>/', views.TUSProductDetailView.as_view(), name='retail_product_detail'),

    # TUS AJAX endpoints
    path('retail/ajax/search/', views.tus_search_ajax, name='tus_search_ajax'),
    path('retail/ajax/location-search/', views.tus_location_search_ajax, name='tus_location_search_ajax'),
    path('retail/ajax/school-search/', views.tus_school_search_ajax, name='tus_school_search_ajax'),

    # TUS Product Variation API endpoints
    path('retail/api/products/<int:product_id>/variations/', views.tus_product_variations_api, name='tus_product_variations_api'),
    path('retail/api/products/<int:product_id>/check-availability/', views.tus_check_variation_availability, name='tus_check_variation_availability'),
    path('retail/api/products/<int:product_id>/variation-details/', views.tus_get_variation_details, name='tus_get_variation_details'),
    path('retail/api/products/<int:product_id>/options/<str:attribute_type>/', views.tus_get_available_options, name='tus_get_available_options'),

    # TUS Sync endpoints
    path('retail/sync/tus/execute/', views.sync_tus_schools, name='sync-tus-schools'),
    path('retail/sync/status/<uuid:job_id>/', views.tus_sync_status, name='tus-sync-status'),

    # Wholesale Schools URLs - Main entry point
    path('wholesale/', views.WholesaleSchoolsView.as_view(), name='wholesale_schools'),

    # Wholesale school detail and related pages
    path('wholesale/school/<slug:slug>/', views.WholesaleSchoolDetailView.as_view(), name='wholesale_school_detail'),
    path('wholesale/category/<slug:slug>/', views.WholesaleCategoryDetailView.as_view(), name='wholesale_category_detail'),
    path('wholesale/product/<slug:slug>/', views.WholesaleProductDetailView.as_view(), name='wholesale_product_detail'),

    # Wholesale sync endpoints
    path('wholesale/sync/execute/', views.wholesale_sync_execute, name='wholesale-sync-execute'),
    path('wholesale/sync/status/', views.wholesale_sync_status, name='wholesale-sync-status'),

    # CSV upload endpoint
    path('wholesale/upload-csv/', views.wholesale_csv_upload, name='wholesale-csv-upload'),

    # Wholesale settings endpoints
    path('wholesale/settings/price-update/', views.wholesale_price_update_settings, name='wholesale-price-update-settings'),

    # Wholesale price update API endpoints
    path('wholesale/api/price-preview/', views.wholesale_price_preview, name='wholesale-price-preview'),
    path('wholesale/api/price-apply/', views.wholesale_price_apply, name='wholesale-price-apply'),

    # Legacy placeholder pages
    path('retail-legacy/', views.RetailSchoolsView.as_view(), name='retail_schools_legacy'),
]