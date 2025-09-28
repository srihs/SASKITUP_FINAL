"""
Django REST Framework API views for wholesale price update system.

This module provides comprehensive API endpoints for:
1. File upload and CSV processing
2. Price update operations (preview and execute)
3. Data retrieval and export
4. Reporting and analytics
5. Real-time sync status monitoring

Author: Claude Code SuperClaude
"""

import csv
import io
import logging
import tempfile
import time
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db import models
from django.db.models import Q, Count, Sum, Avg, Min, Max, F
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status, permissions, parsers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from schools.models import (
    WholesaleSchool, WholesaleCategory, WholesaleProduct,
    WholesaleProductVariation, WholesaleSyncJob
)
from .serializers import (
    # File upload serializers
    CSVFileUploadSerializer, CSVValidationResultSerializer,

    # Product serializers
    WholesaleSchoolSerializer, WholesaleCategorySerializer,
    WholesaleProductSerializer, WholesaleProductVariationSerializer,

    # Price update serializers
    PriceUpdateRequestSerializer, PriceCalculationResultSerializer,
    BatchUpdateResultSerializer,

    # Analytics serializers
    PricingStatisticsSerializer, ProductIssueSerializer,
    PricingReportSerializer,

    # Sync job serializers
    WholesaleSyncJobSerializer,

    # Generic response serializers
    APIResponseSerializer
)
from .utils.price_calculation import (
    PriceCalculator, ProductPriceManager, PriceAnalyzer,
    calculate_product_pricing, batch_calculate_pricing,
    generate_pricing_analysis, generate_pricing_report
)

logger = logging.getLogger(__name__)


# =============================================================================
# Custom Pagination Classes
# =============================================================================

class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination for API results."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class LargeResultsSetPagination(PageNumberPagination):
    """Pagination for large datasets."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 500


# =============================================================================
# File Upload and Processing API
# =============================================================================

class CSVFileUploadView(APIView):
    """
    API endpoint for uploading and validating CSV files for price updates.

    Supports:
    - File validation (size, format, structure)
    - CSV parsing and validation
    - Preview of data changes
    - Error reporting
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Upload CSV file for price updates",
        operation_description="Upload and validate a CSV file containing product pricing data",
        request_body=CSVFileUploadSerializer,
        responses={
            200: CSVValidationResultSerializer,
            400: "Bad Request - Invalid file or format",
            413: "File too large"
        },
        tags=['File Upload']
    )
    def post(self, request, *args, **kwargs):
        """Upload and validate CSV file."""
        serializer = CSVFileUploadSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        uploaded_file = serializer.validated_data['file']
        validate_products = serializer.validated_data['validate_products']
        allow_partial_matches = serializer.validated_data['allow_partial_matches']
        delimiter = serializer.validated_data['delimiter']

        try:
            # Process the CSV file
            validation_result = self._process_csv_file(
                uploaded_file,
                validate_products=validate_products,
                allow_partial_matches=allow_partial_matches,
                delimiter=delimiter
            )

            return Response(validation_result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"CSV processing error: {e}")
            return Response(
                {
                    'success': False,
                    'message': 'Failed to process CSV file',
                    'errors': [str(e)]
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _process_csv_file(self, uploaded_file, validate_products=True,
                         allow_partial_matches=False, delimiter=',') -> Dict[str, Any]:
        """Process and validate CSV file content."""

        # Read file content
        content = uploaded_file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)

        results = {
            'total_rows': 0,
            'valid_rows': 0,
            'invalid_rows': 0,
            'duplicate_rows': 0,
            'validation_errors': [],
            'warnings': [],
            'preview_data': []
        }

        seen_skus = set()
        preview_count = 0

        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 for header
            results['total_rows'] += 1

            # Clean row data
            clean_row = {k.lower().strip(): v.strip() for k, v in row.items()}

            # Validate row
            validation_result = self._validate_csv_row(
                clean_row, row_num, validate_products, allow_partial_matches
            )

            if validation_result['is_valid']:
                results['valid_rows'] += 1

                # Check for duplicates
                sku = clean_row.get('sku', '')
                if sku in seen_skus:
                    results['duplicate_rows'] += 1
                    results['warnings'].append({
                        'row': row_num,
                        'message': f'Duplicate SKU: {sku}',
                        'severity': 'warning'
                    })
                else:
                    seen_skus.add(sku)

                # Add to preview (first 10 valid rows)
                if preview_count < 10:
                    results['preview_data'].append({
                        'row': row_num,
                        'data': clean_row,
                        'calculated_changes': validation_result.get('calculated_changes', {})
                    })
                    preview_count += 1

            else:
                results['invalid_rows'] += 1
                results['validation_errors'].extend(validation_result['errors'])

            # Add any warnings
            if validation_result.get('warnings'):
                results['warnings'].extend(validation_result['warnings'])

        return results

    def _validate_csv_row(self, row: Dict[str, str], row_num: int,
                         validate_products=True, allow_partial_matches=False) -> Dict[str, Any]:
        """Validate a single CSV row."""

        result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'calculated_changes': {}
        }

        # Required fields validation
        required_fields = ['sku']
        for field in required_fields:
            if not row.get(field):
                result['errors'].append({
                    'row': row_num,
                    'field': field,
                    'message': f'Required field "{field}" is missing or empty',
                    'severity': 'error'
                })
                result['is_valid'] = False

        # Validate numeric fields
        numeric_fields = ['cost_price', 'wholesale_price', 'retail_price']
        for field in numeric_fields:
            value = row.get(field)
            if value:  # Only validate if provided
                try:
                    decimal_value = Decimal(value.replace(',', '').replace('$', ''))
                    if decimal_value < 0:
                        result['warnings'].append({
                            'row': row_num,
                            'field': field,
                            'message': f'Negative value for {field}: {value}',
                            'severity': 'warning'
                        })
                    row[field] = str(decimal_value)  # Normalize the value
                except (InvalidOperation, ValueError):
                    result['errors'].append({
                        'row': row_num,
                        'field': field,
                        'message': f'Invalid decimal value for {field}: {value}',
                        'severity': 'error'
                    })
                    result['is_valid'] = False

        # Product existence validation
        if validate_products and result['is_valid']:
            sku = row.get('sku')
            if sku:
                product = WholesaleProduct.objects.filter(sku=sku).first()
                if not product:
                    if allow_partial_matches:
                        # Try partial match
                        products = WholesaleProduct.objects.filter(
                            sku__icontains=sku
                        )[:5]
                        if products:
                            result['warnings'].append({
                                'row': row_num,
                                'field': 'sku',
                                'message': f'Exact SKU not found. Possible matches: {[p.sku for p in products]}',
                                'severity': 'warning'
                            })
                        else:
                            result['errors'].append({
                                'row': row_num,
                                'field': 'sku',
                                'message': f'Product with SKU "{sku}" not found',
                                'severity': 'error'
                            })
                            result['is_valid'] = False
                    else:
                        result['errors'].append({
                            'row': row_num,
                            'field': 'sku',
                            'message': f'Product with SKU "{sku}" not found',
                            'severity': 'error'
                        })
                        result['is_valid'] = False
                else:
                    # Calculate potential changes
                    if row.get('cost_price'):
                        calculator = PriceCalculator()
                        new_cost = Decimal(row['cost_price'])
                        margin_75 = calculator.calculate_margin_75_price(new_cost)

                        result['calculated_changes'] = {
                            'old_cost_price': str(product.cost_price) if product.cost_price else None,
                            'new_cost_price': str(new_cost),
                            'old_margin_75_price': str(product.margin_75_price) if product.margin_75_price else None,
                            'new_margin_75_price': str(margin_75)
                        }

        return result


# =============================================================================
# Price Update Operations API
# =============================================================================

class PriceUpdateView(APIView):
    """
    API endpoint for price update operations.

    Supports:
    - Preview mode (dry run)
    - Actual price updates
    - Batch operations
    - Progress tracking
    """

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Preview or execute price updates",
        operation_description="Preview price changes or execute batch price updates",
        request_body=PriceUpdateRequestSerializer,
        responses={
            200: BatchUpdateResultSerializer,
            400: "Bad Request - Invalid data",
            500: "Internal Server Error"
        },
        tags=['Price Updates']
    )
    def post(self, request, *args, **kwargs):
        """Execute price update operations."""
        serializer = PriceUpdateRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data
        items = data['items']
        dry_run = data['dry_run']
        force_update = data['force_update']
        calculate_margin_75 = data['calculate_margin_75']
        update_variations = data['update_variations']

        try:
            start_time = time.time()

            # Process the price updates
            result = self._process_price_updates(
                items=items,
                dry_run=dry_run,
                force_update=force_update,
                calculate_margin_75=calculate_margin_75,
                update_variations=update_variations
            )

            result['processing_time'] = time.time() - start_time

            logger.info(f"Price update completed: {result['successful_updates']}/{result['total_processed']} successful")

            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Price update error: {e}")
            return Response(
                {
                    'success': False,
                    'message': 'Price update failed',
                    'errors': [str(e)]
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _process_price_updates(self, items, dry_run=True, force_update=False,
                              calculate_margin_75=True, update_variations=True) -> Dict[str, Any]:
        """Process batch price updates."""

        result = {
            'total_processed': 0,
            'successful_updates': 0,
            'failed_updates': 0,
            'skipped_updates': 0,
            'results': [],
            'errors': [],
            'warnings': [],
            'total_cost_price_updates': 0,
            'total_wholesale_price_updates': 0,
            'total_margin_75_calculations': 0
        }

        manager = ProductPriceManager()

        for item in items:
            result['total_processed'] += 1

            try:
                # Find the product
                product = self._find_product(item)

                if not product:
                    error_msg = f"Product not found: {item.get('product_id') or item.get('sku')}"
                    result['failed_updates'] += 1
                    result['errors'].append(error_msg)
                    result['results'].append({
                        'product_id': item.get('product_id'),
                        'product_name': 'Unknown',
                        'sku': item.get('sku', 'Unknown'),
                        'success': False,
                        'errors': [error_msg],
                        'warnings': [],
                        'changes_applied': {}
                    })
                    continue

                # Prepare update data
                update_data = {}
                if 'cost_price' in item:
                    update_data['cost_price'] = item['cost_price']
                if 'wholesale_price' in item:
                    update_data['wholesale_price'] = item['wholesale_price']
                if 'retail_price' in item:
                    update_data['retail_price'] = item['retail_price']

                # Process the update
                update_result = manager.update_product_pricing(
                    product=product,
                    save=not dry_run,
                    force_update=force_update,
                    calculate_margin_75=calculate_margin_75,
                    **update_data
                )

                if update_result.success:
                    result['successful_updates'] += 1

                    # Count specific update types
                    if 'cost_price' in item:
                        result['total_cost_price_updates'] += 1
                    if 'wholesale_price' in item:
                        result['total_wholesale_price_updates'] += 1
                    if update_result.new_values and update_result.new_values.margin_75_price:
                        result['total_margin_75_calculations'] += 1

                else:
                    result['failed_updates'] += 1

                # Format result for response
                formatted_result = self._format_calculation_result(update_result)
                result['results'].append(formatted_result)

                # Collect warnings
                if update_result.warnings:
                    result['warnings'].extend(update_result.warnings)

            except Exception as e:
                result['failed_updates'] += 1
                error_msg = f"Error processing product {item.get('product_id') or item.get('sku')}: {e}"
                result['errors'].append(error_msg)

                result['results'].append({
                    'product_id': item.get('product_id'),
                    'product_name': 'Unknown',
                    'sku': item.get('sku', 'Unknown'),
                    'success': False,
                    'errors': [str(e)],
                    'warnings': [],
                    'changes_applied': {}
                })

        # Calculate success rate
        if result['total_processed'] > 0:
            result['success_rate'] = (result['successful_updates'] / result['total_processed']) * 100
        else:
            result['success_rate'] = 0.0

        return result

    def _find_product(self, item: Dict[str, Any]) -> Optional[WholesaleProduct]:
        """Find product by ID or SKU."""
        if item.get('product_id'):
            return WholesaleProduct.objects.filter(id=item['product_id']).first()
        elif item.get('sku'):
            return WholesaleProduct.objects.filter(sku=item['sku']).first()
        return None

    def _format_calculation_result(self, calc_result) -> Dict[str, Any]:
        """Format calculation result for API response."""
        return {
            'product_id': calc_result.product_id,
            'product_name': calc_result.product_name or 'Unknown',
            'sku': getattr(calc_result, 'sku', 'Unknown'),

            # Old values
            'old_cost_price': calc_result.old_values.cost_price if calc_result.old_values else None,
            'old_wholesale_price': calc_result.old_values.wholesale_price if calc_result.old_values else None,
            'old_margin_75_price': calc_result.old_values.margin_75_price if calc_result.old_values else None,

            # New values
            'new_cost_price': calc_result.new_values.cost_price if calc_result.new_values else None,
            'new_wholesale_price': calc_result.new_values.wholesale_price if calc_result.new_values else None,
            'new_margin_75_price': calc_result.new_values.margin_75_price if calc_result.new_values else None,
            'new_discount_percentage': calc_result.new_values.discount_percentage if calc_result.new_values else None,
            'new_profit_margin': calc_result.new_values.profit_margin if calc_result.new_values else None,

            # Status
            'success': calc_result.success,
            'errors': calc_result.errors,
            'warnings': calc_result.warnings,

            # Changes summary
            'changes_applied': self._get_changes_summary(calc_result)
        }

    def _get_changes_summary(self, calc_result) -> Dict[str, Any]:
        """Get summary of changes applied."""
        changes = {}

        if calc_result.old_values and calc_result.new_values:
            old = calc_result.old_values
            new = calc_result.new_values

            if old.cost_price != new.cost_price:
                changes['cost_price'] = {
                    'old': str(old.cost_price) if old.cost_price else None,
                    'new': str(new.cost_price) if new.cost_price else None
                }

            if old.wholesale_price != new.wholesale_price:
                changes['wholesale_price'] = {
                    'old': str(old.wholesale_price) if old.wholesale_price else None,
                    'new': str(new.wholesale_price) if new.wholesale_price else None
                }

            if old.margin_75_price != new.margin_75_price:
                changes['margin_75_price'] = {
                    'old': str(old.margin_75_price) if old.margin_75_price else None,
                    'new': str(new.margin_75_price) if new.margin_75_price else None
                }

        return changes


# =============================================================================
# Data Retrieval and Export API
# =============================================================================

class WholesaleProductViewSet(ReadOnlyModelViewSet):
    """
    API viewset for wholesale products with pricing data.

    Provides:
    - List and detail views
    - Filtering and searching
    - Export capabilities
    """

    queryset = WholesaleProduct.objects.select_related(
        'school', 'category'
    ).prefetch_related('variations')
    serializer_class = WholesaleProductSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['name', 'sku', 'school__name']
    ordering_fields = ['name', 'cost_price', 'wholesale_price', 'created_at']
    ordering = ['name']

    filterset_fields = {
        'school': ['exact'],
        'category': ['exact'],
        'stock_status': ['exact'],
        'is_active': ['exact'],
        'cost_price': ['isnull', 'gte', 'lte'],
        'wholesale_price': ['isnull', 'gte', 'lte'],
        'margin_75_price': ['isnull'],
    }

    @swagger_auto_schema(
        operation_summary="Export products to CSV",
        operation_description="Export filtered products to CSV format",
        responses={
            200: "CSV file download",
            400: "Bad Request"
        },
        tags=['Data Export']
    )
    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        """Export products to CSV."""
        queryset = self.filter_queryset(self.get_queryset())

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="wholesale_products_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

        writer = csv.writer(response)

        # Write header
        writer.writerow([
            'ID', 'Name', 'SKU', 'School', 'Category', 'Cost Price',
            'Wholesale Price', 'Retail Price', '75% Margin Price',
            'Discount %', 'Stock Status', 'Created'
        ])

        # Write data
        for product in queryset:
            writer.writerow([
                product.id,
                product.name,
                product.sku or '',
                product.school.name,
                product.category.name if product.category else '',
                product.cost_price or '',
                product.wholesale_price or '',
                product.retail_price or '',
                product.margin_75_price or '',
                product.discount_percentage or '',
                product.stock_status,
                product.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])

        return response

    @swagger_auto_schema(
        operation_summary="Get pricing statistics",
        operation_description="Get pricing statistics for filtered products",
        responses={
            200: PricingStatisticsSerializer,
        },
        tags=['Analytics']
    )
    @action(detail=False, methods=['get'])
    def pricing_statistics(self, request):
        """Get pricing statistics for filtered products."""
        queryset = self.filter_queryset(self.get_queryset())

        stats = queryset.aggregate(
            total_products=Count('id'),
            products_with_cost=Count('id', filter=Q(cost_price__isnull=False)),
            products_with_wholesale=Count('id', filter=Q(wholesale_price__isnull=False)),
            products_with_margin_75=Count('id', filter=Q(margin_75_price__isnull=False)),
            avg_cost_price=Avg('cost_price'),
            avg_wholesale_price=Avg('wholesale_price'),
            avg_margin_75_price=Avg('margin_75_price'),
            min_cost_price=Min('cost_price'),
            max_cost_price=Max('cost_price'),
        )

        # Calculate additional statistics
        stats.update({
            'high_discount_products': queryset.filter(discount_percentage__gt=50).count(),
            'low_margin_products': queryset.filter(
                cost_price__isnull=False,
                wholesale_price__isnull=False
            ).extra(
                where=["((wholesale_price - cost_price) / wholesale_price * 100) < 10"]
            ).count(),
            'negative_margin_products': queryset.filter(
                cost_price__gt=models.F('wholesale_price')
            ).count(),
            'missing_cost_price': queryset.filter(cost_price__isnull=True).count(),
            'missing_wholesale_price': queryset.filter(wholesale_price__isnull=True).count(),
        })

        # Calculate average discount and profit margin
        if stats['products_with_margin_75'] > 0:
            products_with_discount = queryset.filter(
                margin_75_price__isnull=False,
                wholesale_price__isnull=False
            )
            if products_with_discount.exists():
                stats['avg_discount_percentage'] = products_with_discount.aggregate(
                    avg_discount=Avg('discount_percentage')
                )['avg_discount']

        if stats['products_with_cost'] > 0 and stats['products_with_wholesale'] > 0:
            # This would need a more complex calculation in a real scenario
            stats['avg_profit_margin'] = None  # Placeholder

        serializer = PricingStatisticsSerializer(data=stats)
        serializer.is_valid(raise_exception=True)

        return Response(serializer.data)


class WholesaleSchoolViewSet(ReadOnlyModelViewSet):
    """API viewset for wholesale schools."""

    queryset = WholesaleSchool.objects.annotate(
        total_products=Count('products'),
        total_categories=Count('products__categories', distinct=True)
    )
    serializer_class = WholesaleSchoolSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['name', 'school_code', 'contact_person', 'city']
    ordering_fields = ['name', 'created_at', 'total_products']
    ordering = ['name']

    filterset_fields = {
        'is_active': ['exact'],
        'city': ['exact', 'icontains'],
        'region': ['exact', 'icontains'],
    }


# =============================================================================
# Reporting and Analytics API
# =============================================================================

class PricingAnalyticsView(APIView):
    """
    Advanced pricing analytics and reporting API.

    Provides:
    - Comprehensive pricing analysis
    - Issue identification
    - Custom reports
    - Trend analysis
    """

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Generate comprehensive pricing analysis",
        operation_description="Generate detailed pricing analysis with issue identification",
        responses={
            200: PricingReportSerializer,
            500: "Internal Server Error"
        },
        tags=['Analytics']
    )
    def get(self, request, *args, **kwargs):
        """Generate comprehensive pricing analysis."""
        try:
            # Generate analysis using the price calculation engine
            analysis = generate_pricing_analysis()

            # Identify pricing issues
            issues = self._identify_pricing_issues()

            # Prepare report data
            report_data = {
                'report_type': 'summary',
                'generated_at': timezone.now(),
                'generated_by': request.user.username,
                'statistics': {
                    'total_products': analysis.total_products,
                    'products_with_cost': analysis.products_with_cost,
                    'products_with_wholesale': analysis.products_with_wholesale,
                    'products_with_margin_75': analysis.products_with_margin_75,
                    'avg_cost_price': analysis.avg_cost_price,
                    'avg_wholesale_price': analysis.avg_wholesale_price,
                    'avg_margin_75_price': analysis.avg_margin_75_price,
                    'avg_discount_percentage': analysis.avg_discount_percentage,
                    'avg_profit_margin': analysis.avg_profit_margin,
                    'min_cost_price': analysis.min_cost_price,
                    'max_cost_price': analysis.max_cost_price,
                    'high_discount_products': analysis.high_discount_products,
                    'low_margin_products': analysis.low_margin_products,
                    'negative_margin_products': analysis.negative_margin_products,
                    'missing_cost_price': analysis.missing_cost_price,
                    'missing_wholesale_price': analysis.missing_wholesale_price,
                },
                'issues': issues,
                'filters_applied': dict(request.GET),
                'total_records': analysis.total_products,
                'export_format': 'json'
            }

            serializer = PricingReportSerializer(data=report_data)
            serializer.is_valid(raise_exception=True)

            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Analytics generation error: {e}")
            return Response(
                {
                    'success': False,
                    'message': 'Failed to generate analytics',
                    'errors': [str(e)]
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _identify_pricing_issues(self) -> List[Dict[str, Any]]:
        """Identify products with pricing issues."""
        issues = []

        # Missing cost prices
        products_missing_cost = WholesaleProduct.objects.filter(
            cost_price__isnull=True,
            is_active=True
        ).select_related('school')[:50]

        for product in products_missing_cost:
            issues.append({
                'product_id': product.id,
                'product_name': product.name,
                'school_name': product.school.name,
                'sku': product.sku or '',
                'issue_type': 'missing_cost_price',
                'severity': 'high',
                'current_cost_price': None,
                'current_wholesale_price': product.wholesale_price,
                'current_discount_percentage': None,
                'current_profit_margin': None,
                'description': 'Product is missing cost price information',
                'recommended_action': 'Add cost price to enable margin calculations'
            })

        # High discount products (>50%)
        high_discount_products = WholesaleProduct.objects.filter(
            discount_percentage__gt=50,
            is_active=True
        ).select_related('school')[:50]

        for product in high_discount_products:
            issues.append({
                'product_id': product.id,
                'product_name': product.name,
                'school_name': product.school.name,
                'sku': product.sku or '',
                'issue_type': 'high_discount',
                'severity': 'medium',
                'current_cost_price': product.cost_price,
                'current_wholesale_price': product.wholesale_price,
                'current_discount_percentage': product.discount_percentage,
                'current_profit_margin': None,  # Would need calculation
                'description': f'Product has high discount of {product.discount_percentage}%',
                'recommended_action': 'Review pricing strategy or cost structure'
            })

        # Negative margin products
        negative_margin_products = WholesaleProduct.objects.filter(
            cost_price__gt=models.F('wholesale_price'),
            is_active=True
        ).select_related('school')[:50]

        for product in negative_margin_products:
            issues.append({
                'product_id': product.id,
                'product_name': product.name,
                'school_name': product.school.name,
                'sku': product.sku or '',
                'issue_type': 'negative_margin',
                'severity': 'critical',
                'current_cost_price': product.cost_price,
                'current_wholesale_price': product.wholesale_price,
                'current_discount_percentage': product.discount_percentage,
                'current_profit_margin': None,  # Would be negative
                'description': 'Product cost exceeds wholesale price (negative margin)',
                'recommended_action': 'Urgent: Review cost or increase wholesale price'
            })

        return issues


# =============================================================================
# Sync Job Monitoring API
# =============================================================================

class WholesaleSyncJobViewSet(ReadOnlyModelViewSet):
    """
    API viewset for monitoring wholesale sync jobs.

    Provides:
    - Job status monitoring
    - Progress tracking
    - Real-time updates
    """

    queryset = WholesaleSyncJob.objects.all()
    serializer_class = WholesaleSyncJobSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['created_at', 'started_at', 'completed_at']
    ordering = ['-created_at']

    filterset_fields = {
        'job_type': ['exact'],
        'status': ['exact'],
        'created_by': ['exact'],
    }

    @swagger_auto_schema(
        operation_summary="Get real-time job status",
        operation_description="Get real-time status of a specific sync job",
        responses={
            200: WholesaleSyncJobSerializer,
            404: "Job not found"
        },
        tags=['Sync Jobs']
    )
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Get real-time job status."""
        job = self.get_object()
        serializer = self.get_serializer(job)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_summary="Get active jobs",
        operation_description="Get all currently active (running) sync jobs",
        responses={
            200: WholesaleSyncJobSerializer(many=True),
        },
        tags=['Sync Jobs']
    )
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get all active sync jobs."""
        active_jobs = self.get_queryset().filter(
            status__in=['pending', 'running']
        )
        serializer = self.get_serializer(active_jobs, many=True)
        return Response(serializer.data)