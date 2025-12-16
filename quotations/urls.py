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
    # REMOVED: path('add-addon/') - Addons are now added together with the base product
    path('update/', views.UpdateQuotationItemView.as_view(), name='update-item'),
    path('update-with-players/', views.UpdateQuotationItemWithPlayersView.as_view(), name='update-item-with-players'),
    path('update-player-customizations/', views.UpdatePlayerCustomizationsView.as_view(), name='update-player-customizations'),
    path('get-player-customizations/<int:cart_index>/', views.GetPlayerCustomizationsView.as_view(), name='get-player-customizations'),
    path('remove-addon/', views.RemoveAddonView.as_view(), name='remove-addon'),
    path('remove/', views.RemoveQuotationItemView.as_view(), name='remove-item'),
    path('clear/', views.ClearQuotationView.as_view(), name='clear'),

    # Step 4: Save Quotation
    path('save/', views.SaveQuotationView.as_view(), name='save'),

    # Step 5: My Quotations
    path('my-quotations/', views.MyQuotationsListView.as_view(), name='my-quotations'),

    # Quotation Detail
    path('detail/<uuid:pk>/', views.QuotationDetailView.as_view(), name='quotation-detail'),

    # Edit Quotation
    path('edit/<uuid:pk>/', views.EditQuotationView.as_view(), name='edit-quotation'),

    # Quotation History
    path('history/<uuid:pk>/', views.QuotationHistoryView.as_view(), name='quotation-history'),

    # Quotation Preview
    path('preview/<uuid:pk>/', views.QuotationPreviewView.as_view(), name='quotation-preview'),

    # Quotation PDF Download
    path('<uuid:pk>/pdf/', views.QuotationPDFView.as_view(), name='quotation-pdf'),

    # Quotation Excel Export (Bespoke Products)
    path('<uuid:pk>/excel/', views.QuotationExcelExportView.as_view(), name='quotation-excel'),

    # Quotation Word Export (ORDER DETAILS - Bespoke Products)
    path('<uuid:pk>/word/', views.QuotationWordExportView.as_view(), name='quotation-word'),

    # Site Settings
    path('settings/', views.SiteSettingsView.as_view(), name='site-settings'),
    path('settings/shipping/', views.ShippingSettingsView.as_view(), name='shipping-settings'),

    # Approve Quotation
    path('approve/<uuid:pk>/', views.ApproveQuotationView.as_view(), name='approve-quotation'),

    # Reports
    path('reports/', views.QuotationsReportView.as_view(), name='quotations-report'),
    path('reports/products/missing-cost/', views.ProductsMissingCostView.as_view(), name='products-missing-cost'),
    path('reports/products/price-anomaly/', views.ProductsPriceAnomalyView.as_view(), name='products-price-anomaly'),
    path('reports/products/low-margin/', views.ProductsLowMarginView.as_view(), name='products-low-margin'),

    # API - Version History
    path('<uuid:quotation_id>/versions/', views.QuotationVersionsAPIView.as_view(), name='quotation-versions-api'),

    # Image Proxy - for password-protected WordPress images
    path('proxy-image/', views.proxy_image, name='proxy-image'),

    # Account Manager Approval Workflow
    path('pending-approvals/', views.PendingApprovalsListView.as_view(), name='pending-approvals'),
    path('pending-approvals/count/', views.PendingApprovalsCountView.as_view(), name='pending-approvals-count'),

    # Customer Approval (First Level - Two-Level Approval System)
    path('<uuid:pk>/customer-approve/', views.QuotationCustomerApproveView.as_view(), name='quotation-customer-approve'),

    # Account Manager Approval (Second Level - Two-Level Approval System)
    path('<uuid:pk>/approve/', views.QuotationApproveView.as_view(), name='quotation-approve'),
    path('<uuid:pk>/reject/', views.QuotationRejectView.as_view(), name='quotation-reject'),
    # DEPRECATED: Request changes functionality replaced by direct editing via edit-quotation
    # Account Managers can now edit pending quotations directly instead of requesting changes
    # path('<uuid:pk>/request-changes/', views.QuotationRequestChangesView.as_view(), name='quotation-request-changes'),

    # AJAX - Get Institute Details for Auto-Population
    path('api/get-institute-details/', views.GetInstituteDetailsView.as_view(), name='get-institute-details'),

    # AJAX - Calculate Shipping Cost
    path('api/calculate-shipping/', views.CalculateShippingView.as_view(), name='calculate-shipping'),
]
