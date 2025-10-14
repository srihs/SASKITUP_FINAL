"""
URL patterns for quotations app.

Workflow:
1. /select-institution/ - User selects institution (school/club)
2. /products/<type>/<id>/ - Browse products for institution
3. /cart/ - View quotation cart
4. /add/ - AJAX: Add product to quotation
5. /update/<index>/ - AJAX: Update item quantity
6. /remove/<index>/ - AJAX: Remove item
7. /clear/ - AJAX: Clear all items
8. /save/ - Save quotation to database
9. /my-quotations/ - List user's quotations
10. /detail/<pk>/ - View quotation details
"""

from django.urls import path
from . import views

app_name = 'quotations'

urlpatterns = [
    # NEW: Tab-based product selection (simplified workflow)
    path('new/', views.NewQuotationView.as_view(), name='new-quotation'),

    # Product Detail Page for Quotation
    path('product/<str:product_type>/<slug:product_slug>/',
         views.ProductDetailForQuotationView.as_view(),
         name='product-detail-for-quote'),

    # Step 1: Institution Selection
    path('select-institution/', views.InstitutionSelectionView.as_view(), name='select-institution'),

    # Step 2: Product Listing (for selected institution)
    path(
        'products/<str:institution_type>/<slug:institution_slug>/',
        views.ProductListingView.as_view(),
        name='product-listing'
    ),

    # Step 3: Quotation Cart
    path('cart/', views.QuotationCartView.as_view(), name='cart'),
    path('quotation-cart/', views.QuotationCartView.as_view(), name='quotation-cart'),

    # AJAX Endpoints
    path('add/', views.AddToQuotationView.as_view(), name='add-item'),
    path('update/', views.UpdateQuotationItemView.as_view(), name='update-item'),
    path('remove/', views.RemoveQuotationItemView.as_view(), name='remove-item'),
    path('clear/', views.ClearQuotationView.as_view(), name='clear'),

    # Step 4: Save Quotation
    path('save/', views.SaveQuotationView.as_view(), name='save'),

    # Step 5: My Quotations
    path('my-quotations/', views.MyQuotationsListView.as_view(), name='my-quotations'),

    # Quotation Detail
    path('detail/<uuid:pk>/', views.QuotationDetailView.as_view(), name='quotation-detail'),

    # Quotation Preview
    path('preview/<uuid:pk>/', views.QuotationPreviewView.as_view(), name='quotation-preview'),

    # Site Settings
    path('settings/', views.SiteSettingsView.as_view(), name='site-settings'),

    # Approve Quotation
    path('approve/<uuid:pk>/', views.ApproveQuotationView.as_view(), name='approve-quotation'),

    # Reports
    path('reports/products/missing-cost/', views.ProductsMissingCostView.as_view(), name='products-missing-cost'),
    path('reports/products/price-anomaly/', views.ProductsPriceAnomalyView.as_view(), name='products-price-anomaly'),
    path('reports/products/low-margin/', views.ProductsLowMarginView.as_view(), name='products-low-margin'),
]
