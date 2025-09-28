"""
Django REST Framework serializers for the wholesale price update API.

This module provides comprehensive serializers for:
1. File upload and validation
2. Price update operations
3. Data retrieval and export
4. Reporting and analytics

Author: Claude Code SuperClaude
"""

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from schools.models import (
    WholesaleSchool, WholesaleCategory, WholesaleProduct,
    WholesaleProductVariation, WholesaleSyncJob
)
from schools.utils.price_calculation import (
    PriceCalculator, ProductPriceManager, PriceAnalyzer,
    PriceData, CalculationResult, BatchResult
)


# =============================================================================
# File Upload Serializers
# =============================================================================

class CSVFileUploadSerializer(serializers.Serializer):
    """Serializer for CSV file upload and validation."""

    file = serializers.FileField(
        help_text="CSV file containing product pricing data",
        required=True
    )

    # Optional parameters for validation
    validate_products = serializers.BooleanField(
        default=True,
        help_text="Whether to validate product existence"
    )

    allow_partial_matches = serializers.BooleanField(
        default=False,
        help_text="Allow partial product matches"
    )

    delimiter = serializers.CharField(
        default=',',
        max_length=1,
        help_text="CSV delimiter character"
    )

    def validate_file(self, value: UploadedFile) -> UploadedFile:
        """Validate uploaded CSV file."""

        # Check file size (50MB limit to accommodate large product catalogs)
        if value.size > 50 * 1024 * 1024:
            raise ValidationError("File size cannot exceed 50MB")

        # Check file extension - support both CSV and Excel files
        allowed_extensions = ('.csv', '.xlsx', '.xls')
        if not value.name.lower().endswith(allowed_extensions):
            raise ValidationError("File must be a CSV or Excel file (.csv, .xlsx, .xls)")

        # Check if file is readable
        try:
            value.seek(0)
            content = value.read().decode('utf-8')
            value.seek(0)  # Reset file pointer
        except UnicodeDecodeError:
            raise ValidationError("File must be UTF-8 encoded")

        # Basic CSV structure validation
        try:
            reader = csv.reader(io.StringIO(content))
            headers = next(reader, None)

            if not headers:
                raise ValidationError("CSV file appears to be empty")

            # Check for required columns - match actual CSV column names
            required_columns = {'code', 'cost nzd excl', 'retail nzd incl'}
            header_lower = [h.lower().strip() for h in headers]
            missing_columns = required_columns - set(header_lower)

            if missing_columns:
                raise ValidationError(
                    f"Missing required columns: {', '.join(missing_columns)}"
                )

        except csv.Error as e:
            raise ValidationError(f"Invalid CSV format: {e}")

        return value


class CSVValidationResultSerializer(serializers.Serializer):
    """Serializer for CSV validation results."""

    total_rows = serializers.IntegerField(read_only=True)
    valid_rows = serializers.IntegerField(read_only=True)
    invalid_rows = serializers.IntegerField(read_only=True)
    duplicate_rows = serializers.IntegerField(read_only=True)

    validation_errors = serializers.ListField(
        child=serializers.DictField(),
        read_only=True,
        help_text="List of validation errors with row numbers"
    )

    warnings = serializers.ListField(
        child=serializers.DictField(),
        read_only=True,
        help_text="List of warnings with row numbers"
    )

    preview_data = serializers.ListField(
        child=serializers.DictField(),
        read_only=True,
        help_text="First 10 rows of processed data"
    )


# =============================================================================
# Product and Pricing Serializers
# =============================================================================

class WholesaleSchoolSerializer(serializers.ModelSerializer):
    """Serializer for wholesale schools."""

    total_products = serializers.IntegerField(read_only=True)
    total_categories = serializers.IntegerField(read_only=True)

    class Meta:
        model = WholesaleSchool
        fields = [
            'id', 'name', 'slug', 'cin7_id', 'school_code',
            'contact_person', 'email', 'phone', 'address',
            'city', 'region', 'is_active', 'created_at', 'updated_at',
            'total_products', 'total_categories'
        ]
        read_only_fields = ['slug', 'created_at', 'updated_at']


class WholesaleCategorySerializer(serializers.ModelSerializer):
    """Serializer for wholesale categories."""

    school_name = serializers.CharField(source='school.name', read_only=True)
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = WholesaleCategory
        fields = [
            'id', 'name', 'slug', 'cin7_id', 'school', 'school_name',
            'description', 'level', 'parent', 'product_count',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['slug', 'created_at', 'updated_at']


class WholesaleProductVariationSerializer(serializers.ModelSerializer):
    """Serializer for wholesale product variations."""

    class Meta:
        model = WholesaleProductVariation
        fields = [
            'id', 'product', 'variation_type', 'variation_value',
            'cin7_id', 'cost_price', 'wholesale_price', 'retail_price',
            'margin_75_price', 'discount_percentage', 'sku',
            'stock_status', 'is_active'
        ]


class WholesaleProductSerializer(serializers.ModelSerializer):
    """Serializer for wholesale products with pricing information."""

    school_name = serializers.CharField(source='school.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    variations = WholesaleProductVariationSerializer(many=True, read_only=True)

    # Calculated fields
    current_discount_percentage = serializers.SerializerMethodField()
    current_profit_margin = serializers.SerializerMethodField()
    pricing_status = serializers.SerializerMethodField()

    class Meta:
        model = WholesaleProduct
        fields = [
            'id', 'name', 'slug', 'cin7_id', 'sku', 'school', 'school_name',
            'category', 'category_name', 'description', 'cost_price',
            'wholesale_price', 'retail_price', 'margin_75_price',
            'discount_percentage', 'stock_status', 'image',
            'is_active', 'created_at', 'updated_at', 'variations',
            'current_discount_percentage', 'current_profit_margin',
            'pricing_status'
        ]
        read_only_fields = ['slug', 'created_at', 'updated_at']

    def get_current_discount_percentage(self, obj) -> Optional[float]:
        """Calculate current discount percentage."""
        if obj.margin_75_price and obj.wholesale_price:
            calculator = PriceCalculator()
            return float(calculator.calculate_discount_percentage(
                obj.margin_75_price, obj.wholesale_price
            ))
        return None

    def get_current_profit_margin(self, obj) -> Optional[float]:
        """Calculate current profit margin."""
        if obj.cost_price and obj.wholesale_price:
            calculator = PriceCalculator()
            return float(calculator.calculate_profit_margin(
                obj.wholesale_price, obj.cost_price
            ))
        return None

    def get_pricing_status(self, obj) -> str:
        """Get pricing status for the product."""
        if not obj.cost_price:
            return 'missing_cost_price'
        if not obj.wholesale_price:
            return 'missing_wholesale_price'
        if not obj.margin_75_price:
            return 'missing_margin_75'

        discount = self.get_current_discount_percentage(obj)
        if discount and discount > 50:
            return 'high_discount'

        margin = self.get_current_profit_margin(obj)
        if margin and margin < 10:
            return 'low_margin'
        if margin and margin < 0:
            return 'negative_margin'

        return 'normal'


# =============================================================================
# Price Update Operation Serializers
# =============================================================================

class PriceUpdateItemSerializer(serializers.Serializer):
    """Serializer for individual price update items."""

    product_id = serializers.IntegerField(
        help_text="Product ID to update"
    )

    sku = serializers.CharField(
        required=False,
        help_text="Product SKU (alternative to product_id)"
    )

    cost_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        help_text="New cost price"
    )

    wholesale_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        help_text="New wholesale price"
    )

    retail_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        help_text="New retail price"
    )

    def validate(self, data):
        """Validate price update item."""
        if not data.get('product_id') and not data.get('sku'):
            raise ValidationError("Either product_id or sku must be provided")

        if not any([data.get('cost_price'), data.get('wholesale_price'), data.get('retail_price')]):
            raise ValidationError("At least one price field must be provided")

        return data


class PriceUpdateRequestSerializer(serializers.Serializer):
    """Serializer for batch price update requests."""

    items = PriceUpdateItemSerializer(many=True)

    # Operation parameters
    dry_run = serializers.BooleanField(
        default=True,
        help_text="Preview changes without saving"
    )

    force_update = serializers.BooleanField(
        default=False,
        help_text="Force update even with warnings"
    )

    calculate_margin_75 = serializers.BooleanField(
        default=True,
        help_text="Auto-calculate 75% margin prices"
    )

    update_variations = serializers.BooleanField(
        default=True,
        help_text="Update product variations as well"
    )

    def validate_items(self, items):
        """Validate price update items."""
        if not items:
            raise ValidationError("At least one item must be provided")

        if len(items) > 1000:
            raise ValidationError("Maximum 1000 items per batch")

        return items


class PriceCalculationResultSerializer(serializers.Serializer):
    """Serializer for price calculation results."""

    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    sku = serializers.CharField()

    # Old values
    old_cost_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    old_wholesale_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    old_margin_75_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )

    # New values
    new_cost_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    new_wholesale_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    new_margin_75_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    new_discount_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, allow_null=True
    )
    new_profit_margin = serializers.DecimalField(
        max_digits=5, decimal_places=2, allow_null=True
    )

    # Status and messages
    success = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())

    # Changes summary
    changes_applied = serializers.DictField()


class BatchUpdateResultSerializer(serializers.Serializer):
    """Serializer for batch update results."""

    total_processed = serializers.IntegerField()
    successful_updates = serializers.IntegerField()
    failed_updates = serializers.IntegerField()
    skipped_updates = serializers.IntegerField()

    success_rate = serializers.FloatField()
    processing_time = serializers.FloatField(allow_null=True)

    results = PriceCalculationResultSerializer(many=True)

    # Summary statistics
    total_cost_price_updates = serializers.IntegerField()
    total_wholesale_price_updates = serializers.IntegerField()
    total_margin_75_calculations = serializers.IntegerField()

    # Global errors and warnings
    errors = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())


# =============================================================================
# Analytics and Reporting Serializers
# =============================================================================

class PricingStatisticsSerializer(serializers.Serializer):
    """Serializer for pricing statistics."""

    total_products = serializers.IntegerField()
    products_with_cost = serializers.IntegerField()
    products_with_wholesale = serializers.IntegerField()
    products_with_margin_75 = serializers.IntegerField()

    # Average prices
    avg_cost_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    avg_wholesale_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    avg_margin_75_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    avg_discount_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, allow_null=True
    )
    avg_profit_margin = serializers.DecimalField(
        max_digits=5, decimal_places=2, allow_null=True
    )

    # Price ranges
    min_cost_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    max_cost_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )

    # Issue counts
    high_discount_products = serializers.IntegerField()
    low_margin_products = serializers.IntegerField()
    negative_margin_products = serializers.IntegerField()
    missing_cost_price = serializers.IntegerField()
    missing_wholesale_price = serializers.IntegerField()


class ProductIssueSerializer(serializers.Serializer):
    """Serializer for product pricing issues."""

    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    school_name = serializers.CharField()
    sku = serializers.CharField()

    issue_type = serializers.ChoiceField(choices=[
        ('missing_cost_price', 'Missing Cost Price'),
        ('missing_wholesale_price', 'Missing Wholesale Price'),
        ('high_discount', 'High Discount (>50%)'),
        ('low_margin', 'Low Margin (<10%)'),
        ('negative_margin', 'Negative Margin'),
        ('zero_cost', 'Zero Cost Price'),
        ('invalid_pricing', 'Invalid Pricing Data'),
    ])

    severity = serializers.ChoiceField(choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ])

    current_cost_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    current_wholesale_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, allow_null=True
    )
    current_discount_percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, allow_null=True
    )
    current_profit_margin = serializers.DecimalField(
        max_digits=5, decimal_places=2, allow_null=True
    )

    description = serializers.CharField()
    recommended_action = serializers.CharField()


class PricingReportSerializer(serializers.Serializer):
    """Serializer for comprehensive pricing reports."""

    report_type = serializers.ChoiceField(choices=[
        ('summary', 'Summary Report'),
        ('detailed', 'Detailed Report'),
        ('issues', 'Issues Report'),
        ('export', 'Data Export'),
    ])

    generated_at = serializers.DateTimeField()
    generated_by = serializers.CharField()

    statistics = PricingStatisticsSerializer()
    issues = ProductIssueSerializer(many=True)

    # Filters applied
    filters_applied = serializers.DictField()

    # Export metadata
    total_records = serializers.IntegerField()
    export_format = serializers.CharField()


# =============================================================================
# Sync Job Serializers
# =============================================================================

class WholesaleSyncJobSerializer(serializers.ModelSerializer):
    """Serializer for wholesale sync jobs."""

    progress_percentage = serializers.SerializerMethodField()
    estimated_completion = serializers.SerializerMethodField()

    class Meta:
        model = WholesaleSyncJob
        fields = [
            'id', 'job_type', 'status', 'progress_current', 'progress_total',
            'message', 'error_details', 'result_data', 'started_at',
            'completed_at', 'created_by', 'progress_percentage',
            'estimated_completion'
        ]
        read_only_fields = ['id', 'started_at', 'completed_at']

    def get_progress_percentage(self, obj) -> float:
        """Calculate progress percentage."""
        if obj.progress_total and obj.progress_total > 0:
            return (obj.progress_current / obj.progress_total) * 100
        return 0.0

    def get_estimated_completion(self, obj) -> Optional[str]:
        """Estimate completion time."""
        if obj.status in ['completed', 'failed', 'cancelled']:
            return None

        if obj.started_at and obj.progress_total and obj.progress_current > 0:
            elapsed = timezone.now() - obj.started_at
            rate = obj.progress_current / elapsed.total_seconds()
            remaining = obj.progress_total - obj.progress_current

            if rate > 0:
                eta_seconds = remaining / rate
                eta = timezone.now() + timezone.timedelta(seconds=eta_seconds)
                return eta.isoformat()

        return None


# =============================================================================
# Generic Response Serializers
# =============================================================================

class APIResponseSerializer(serializers.Serializer):
    """Generic API response serializer."""

    success = serializers.BooleanField()
    message = serializers.CharField()
    data = serializers.JSONField(required=False)
    errors = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
    timestamp = serializers.DateTimeField()


class PaginatedResponseSerializer(serializers.Serializer):
    """Paginated response serializer."""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = serializers.ListField()