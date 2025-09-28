"""
API URL patterns for wholesale price update system.

This module defines the REST API endpoints for:
1. File upload and processing
2. Price update operations
3. Data retrieval and export
4. Reporting and analytics
5. Sync job monitoring

Author: Claude Code SuperClaude
"""

from django.urls import path, include
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token

from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

from .api_views import (
    # File upload views
    CSVFileUploadView,

    # Price update views
    PriceUpdateView,

    # Data retrieval viewsets
    WholesaleProductViewSet,
    WholesaleSchoolViewSet,

    # Analytics views
    PricingAnalyticsView,

    # Sync job viewsets
    WholesaleSyncJobViewSet,
)

# =============================================================================
# API Documentation Schema
# =============================================================================

schema_view = get_schema_view(
    openapi.Info(
        title="Wholesale Price Update API",
        default_version='v1',
        description="""
        Comprehensive REST API for wholesale school price update system.

        ## Features

        ### File Upload & Processing
        - Upload CSV files with product pricing data
        - Validate file format and structure
        - Preview pricing changes before applying
        - Support for various CSV formats and delimiters

        ### Price Update Operations
        - Preview mode (dry-run) to see changes without saving
        - Batch price updates with transaction safety
        - Automatic 75% margin price calculations
        - Real-time progress tracking
        - Comprehensive error handling and validation

        ### Data Retrieval & Export
        - List and filter wholesale products and schools
        - Advanced search capabilities
        - Export data to CSV format
        - Pagination for large datasets
        - Related data with optimized queries

        ### Reporting & Analytics
        - Pricing statistics and analysis
        - Issue identification (high discounts, negative margins)
        - Comprehensive pricing reports
        - Performance metrics and trends

        ### Sync Job Monitoring
        - Real-time sync job status
        - Progress tracking with percentage completion
        - Job history and error reporting
        - Active job monitoring

        ## Authentication

        API uses session-based authentication and token authentication.
        Include your session cookies or provide an Authorization header:

        ```
        Authorization: Token your-api-token-here
        ```

        ## Rate Limiting

        Standard rate limits apply:
        - 100 requests per minute for authenticated users
        - 20 requests per minute for file uploads
        - 10 requests per minute for large exports

        ## Error Handling

        All endpoints return consistent error responses:

        ```json
        {
            "success": false,
            "message": "Error description",
            "errors": ["Detailed error messages"],
            "timestamp": "2024-01-01T12:00:00Z"
        }
        ```

        ## Pagination

        List endpoints support pagination with query parameters:
        - `page`: Page number (default: 1)
        - `page_size`: Items per page (default: 20, max: 100)

        Response format:
        ```json
        {
            "count": 150,
            "next": "http://api/endpoint/?page=2",
            "previous": null,
            "results": [...]
        }
        ```
        """,
        terms_of_service="https://www.saskitup.co.za/terms/",
        contact=openapi.Contact(email="support@saskitup.co.za"),
        license=openapi.License(name="Proprietary License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
    authentication_classes=[],
)

# =============================================================================
# API Router Configuration
# =============================================================================

# Create the main API router
router = DefaultRouter()

# Register viewsets with the router
router.register(
    r'products',
    WholesaleProductViewSet,
    basename='wholesale-product'
)

router.register(
    r'schools',
    WholesaleSchoolViewSet,
    basename='wholesale-school'
)

router.register(
    r'sync-jobs',
    WholesaleSyncJobViewSet,
    basename='wholesale-sync-job'
)

# =============================================================================
# URL Patterns
# =============================================================================

app_name = 'api'

urlpatterns = [
    # =================================================================
    # API Documentation
    # =================================================================

    path(
        'swagger<format>/',
        schema_view.without_ui(cache_timeout=0),
        name='schema-json'
    ),
    path(
        'swagger/',
        schema_view.with_ui('swagger', cache_timeout=0),
        name='schema-swagger-ui'
    ),
    path(
        'redoc/',
        schema_view.with_ui('redoc', cache_timeout=0),
        name='schema-redoc'
    ),

    # =================================================================
    # Authentication
    # =================================================================

    path('auth/token/', obtain_auth_token, name='api-token-auth'),

    # =================================================================
    # File Upload & Processing
    # =================================================================

    path(
        'upload/csv/',
        CSVFileUploadView.as_view(),
        name='csv-upload'
    ),

    # =================================================================
    # Price Update Operations
    # =================================================================

    path(
        'price-updates/',
        PriceUpdateView.as_view(),
        name='price-updates'
    ),

    # Alternative endpoints for different update types
    path(
        'price-updates/preview/',
        PriceUpdateView.as_view(),
        {'dry_run': True},
        name='price-updates-preview'
    ),

    path(
        'price-updates/execute/',
        PriceUpdateView.as_view(),
        {'dry_run': False},
        name='price-updates-execute'
    ),

    # =================================================================
    # Analytics & Reporting
    # =================================================================

    path(
        'analytics/',
        PricingAnalyticsView.as_view(),
        name='pricing-analytics'
    ),

    path(
        'analytics/pricing/',
        PricingAnalyticsView.as_view(),
        name='pricing-analysis'
    ),

    # =================================================================
    # Router-based URLs (ViewSets)
    # =================================================================

    # Include all router URLs
    path('', include(router.urls)),

    # =================================================================
    # Custom Nested Endpoints
    # =================================================================

    # Product-specific endpoints
    path(
        'products/<int:product_id>/pricing/',
        PriceUpdateView.as_view(),
        name='product-pricing-update'
    ),

    # School-specific endpoints
    path(
        'schools/<int:school_id>/products/',
        WholesaleProductViewSet.as_view({'get': 'list'}),
        name='school-products'
    ),

    # Bulk operations
    path(
        'bulk/price-updates/',
        PriceUpdateView.as_view(),
        name='bulk-price-updates'
    ),

    # =================================================================
    # Status & Health Endpoints
    # =================================================================

    path(
        'health/',
        lambda request: JsonResponse({
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'version': 'v1'
        }),
        name='api-health'
    ),
]

# =============================================================================
# API Version Support (Future Enhancement)
# =============================================================================

# Versioned URL patterns for future API versions
v1_patterns = [
    path('v1/', include(urlpatterns)),
]

# You can add additional URL patterns here for different API versions
# For example:
# v2_patterns = [...]

# Combined patterns
api_patterns = urlpatterns + v1_patterns