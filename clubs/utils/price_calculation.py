"""
Comprehensive Price Calculation Engine for Wholesale School Products

This module provides a robust, reusable price calculation engine that can be used by:
1. Django Management Commands
2. Admin Interface
3. API Endpoints
4. Bulk Operations

The engine handles:
- 75% Margin Price calculations (Cost ÷ 0.25)
- Discount Percentage calculations
- Edge case handling (zero cost, negative values, etc.)
- Validation and error handling
- Batch processing with transaction safety
- Performance optimization
- Comprehensive logging and reporting

Author: Claude Code SuperClaude
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict
import re

from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q, F, Sum, Count, Avg, Min, Max

from schools.models import WholesaleProduct

logger = logging.getLogger(__name__)


class CalculationError(Exception):
    """Custom exception for price calculation errors."""
    pass


class ErrorSeverity(Enum):
    """Error severity levels for calculation issues."""
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class PriceData:
    """Data class for holding price calculation inputs and results."""
    cost_price: Optional[Decimal] = None
    wholesale_price: Optional[Decimal] = None
    retail_price: Optional[Decimal] = None
    margin_75_price: Optional[Decimal] = None
    discount_percentage: Optional[Decimal] = None
    profit_margin: Optional[Decimal] = None

    # Validation flags
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class CalculationResult:
    """Result of a price calculation operation."""
    success: bool
    product_id: Optional[int]
    product_name: Optional[str]
    old_values: Optional[PriceData]
    new_values: Optional[PriceData]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    calculation_time: Optional[datetime] = None


@dataclass
class BatchResult:
    """Result of a batch price calculation operation."""
    total_processed: int = 0
    successful_updates: int = 0
    failed_updates: int = 0
    skipped_updates: int = 0
    results: List[CalculationResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    processing_time: Optional[float] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_processed == 0:
            return 0.0
        return (self.successful_updates / self.total_processed) * 100


@dataclass
class PricingStatistics:
    """Statistics for pricing analysis and reporting."""
    total_products: int = 0
    products_with_cost: int = 0
    products_with_margin_75: int = 0
    products_with_discount: int = 0

    avg_cost_price: Optional[Decimal] = None
    avg_margin_75_price: Optional[Decimal] = None
    avg_discount_percentage: Optional[Decimal] = None
    avg_profit_margin: Optional[Decimal] = None

    min_cost_price: Optional[Decimal] = None
    max_cost_price: Optional[Decimal] = None
    min_discount_percentage: Optional[Decimal] = None
    max_discount_percentage: Optional[Decimal] = None

    high_discount_products: int = 0  # >50% discount
    low_margin_products: int = 0     # <10% profit margin
    negative_margin_products: int = 0 # Negative profit margin


class PriceValidator:
    """Validates price inputs and calculations."""

    # Validation thresholds
    MIN_COST_PRICE = Decimal('0.01')
    MAX_COST_PRICE = Decimal('100000.00')
    MAX_DISCOUNT_PERCENTAGE = Decimal('95.00')
    MIN_PROFIT_MARGIN = Decimal('-50.00')  # Allow some negative margin for analysis

    @classmethod
    def validate_cost_price(cls, cost_price: Optional[Decimal]) -> Tuple[bool, List[str]]:
        """
        Validate cost price input.

        Args:
            cost_price: Cost price to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        if cost_price is None:
            errors.append("Cost price is required")
            return False, errors

        if not isinstance(cost_price, Decimal):
            errors.append("Cost price must be a Decimal")
            return False, errors

        if cost_price < cls.MIN_COST_PRICE:
            errors.append(f"Cost price must be at least ${cls.MIN_COST_PRICE}")

        if cost_price > cls.MAX_COST_PRICE:
            errors.append(f"Cost price cannot exceed ${cls.MAX_COST_PRICE}")

        return len(errors) == 0, errors

    @classmethod
    def validate_price_data(cls, price_data: PriceData) -> Tuple[bool, List[str], List[str]]:
        """
        Validate complete price data.

        Args:
            price_data: PriceData object to validate

        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        errors = []
        warnings = []

        # Validate cost price
        cost_valid, cost_errors = cls.validate_cost_price(price_data.cost_price)
        errors.extend(cost_errors)

        # Check for suspicious values
        if price_data.discount_percentage and price_data.discount_percentage > cls.MAX_DISCOUNT_PERCENTAGE:
            warnings.append(f"Very high discount percentage: {price_data.discount_percentage}%")

        if price_data.profit_margin and price_data.profit_margin < cls.MIN_PROFIT_MARGIN:
            warnings.append(f"Very low profit margin: {price_data.profit_margin}%")

        # Check for logical inconsistencies
        if (price_data.wholesale_price and price_data.cost_price and
            price_data.wholesale_price < price_data.cost_price):
            warnings.append("Wholesale price is less than cost price (negative margin)")

        return len(errors) == 0, errors, warnings


class PriceCalculator:
    """Core price calculation engine with comprehensive validation and error handling."""

    def __init__(self, precision: int = 2):
        """
        Initialize the price calculator.

        Args:
            precision: Decimal precision for calculations (default: 2)
        """
        self.precision = precision
        self.validator = PriceValidator()

    def parse_decimal(self, value: Union[str, int, float, Decimal]) -> Optional[Decimal]:
        """
        Parse various input types to Decimal with error handling.

        Args:
            value: Value to parse (string, int, float, or Decimal)

        Returns:
            Parsed Decimal value or None if parsing fails
        """
        if value is None:
            return None

        if isinstance(value, Decimal):
            return value

        if isinstance(value, (int, float)):
            try:
                return Decimal(str(value))
            except (InvalidOperation, ValueError):
                return None

        if isinstance(value, str):
            if not value.strip():
                return None

            # Clean the value (remove currency symbols, commas, extra spaces)
            cleaned = re.sub(r'[^\d.-]', '', value.strip())

            try:
                return Decimal(cleaned)
            except (InvalidOperation, ValueError):
                return None

        return None

    def calculate_margin_75_price(self, cost_price: Decimal) -> Optional[Decimal]:
        """
        Calculate 75% margin price (Cost ÷ 0.25).

        Formula: margin_75_price = cost_price / 0.25
        This gives a 75% profit margin: (selling_price - cost) / selling_price = 0.75

        Args:
            cost_price: Cost price

        Returns:
            Calculated 75% margin price or None if calculation fails
        """
        if not cost_price or cost_price <= 0:
            return None

        try:
            result = cost_price / Decimal('0.25')
            return result.quantize(Decimal('0.01'))  # Round to 2 decimal places
        except (InvalidOperation, ZeroDivisionError):
            return None

    def calculate_discount_percentage(self, margin_75_price: Decimal, actual_price: Decimal) -> Optional[Decimal]:
        """
        Calculate discount percentage from 75% margin price.

        Formula: discount% = ((margin_75_price - actual_price) / margin_75_price) × 100

        Args:
            margin_75_price: 75% margin price
            actual_price: Actual selling price (wholesale_price or retail_price)

        Returns:
            Discount percentage or None if calculation fails
        """
        if not margin_75_price or not actual_price or margin_75_price <= 0:
            return None

        try:
            discount = ((margin_75_price - actual_price) / margin_75_price) * 100
            # Don't allow negative discounts (indicates price is above 75% margin)
            result = max(Decimal('0'), discount)
            return result.quantize(Decimal('0.01'))
        except (InvalidOperation, ZeroDivisionError):
            return None

    def calculate_profit_margin(self, selling_price: Decimal, cost_price: Decimal) -> Optional[Decimal]:
        """
        Calculate profit margin percentage.

        Formula: profit_margin% = ((selling_price - cost_price) / cost_price) × 100

        Args:
            selling_price: Selling price
            cost_price: Cost price

        Returns:
            Profit margin percentage or None if calculation fails
        """
        if not selling_price or not cost_price or cost_price <= 0:
            return None

        try:
            margin = ((selling_price - cost_price) / cost_price) * 100
            return margin.quantize(Decimal('0.01'))
        except (InvalidOperation, ZeroDivisionError):
            return None

    def calculate_all_prices(self, cost_price: Union[str, Decimal],
                           wholesale_price: Optional[Union[str, Decimal]] = None,
                           retail_price: Optional[Union[str, Decimal]] = None) -> PriceData:
        """
        Calculate all price-related fields from cost price.

        Args:
            cost_price: Product cost price
            wholesale_price: Current wholesale price (optional)
            retail_price: Current retail price (optional)

        Returns:
            PriceData object with calculated values and validation results
        """
        result = PriceData()

        # Parse input prices
        result.cost_price = self.parse_decimal(cost_price)
        result.wholesale_price = self.parse_decimal(wholesale_price)
        result.retail_price = self.parse_decimal(retail_price)

        # Validate cost price
        is_valid, errors = self.validator.validate_cost_price(result.cost_price)
        if not is_valid:
            result.is_valid = False
            result.errors.extend(errors)
            return result

        # Calculate 75% margin price
        result.margin_75_price = self.calculate_margin_75_price(result.cost_price)

        # Calculate discount percentage (prefer wholesale over retail)
        price_for_discount = result.wholesale_price or result.retail_price
        if result.margin_75_price and price_for_discount:
            result.discount_percentage = self.calculate_discount_percentage(
                result.margin_75_price, price_for_discount
            )

        # Calculate profit margin (prefer wholesale over retail)
        if price_for_discount and result.cost_price:
            result.profit_margin = self.calculate_profit_margin(
                price_for_discount, result.cost_price
            )

        # Validate complete data
        is_valid, errors, warnings = self.validator.validate_price_data(result)
        result.is_valid = is_valid
        result.errors.extend(errors)
        result.warnings.extend(warnings)

        return result


class ProductPriceManager:
    """Manages price calculations and updates for WholesaleProduct instances."""

    def __init__(self):
        self.calculator = PriceCalculator()

    def update_product_pricing(self, product: WholesaleProduct,
                             cost_price: Optional[Decimal] = None,
                             save: bool = True) -> CalculationResult:
        """
        Update pricing fields for a single product.

        Args:
            product: WholesaleProduct instance to update
            cost_price: New cost price (if None, uses existing product.cost_price)
            save: Whether to save changes to database

        Returns:
            CalculationResult with operation details
        """
        start_time = timezone.now()

        # Store old values for comparison
        old_values = PriceData(
            cost_price=product.cost_price,
            wholesale_price=product.wholesale_price,
            retail_price=product.retail_price,
            margin_75_price=product.margin_75_price,
            discount_percentage=product.discount_percentage
        )

        # Use provided cost_price or existing one
        effective_cost_price = cost_price or product.cost_price

        # Calculate new prices
        price_data = self.calculator.calculate_all_prices(
            cost_price=effective_cost_price,
            wholesale_price=product.wholesale_price,
            retail_price=product.retail_price
        )

        result = CalculationResult(
            success=price_data.is_valid,
            product_id=product.id,
            product_name=product.name,
            old_values=old_values,
            new_values=price_data,
            errors=price_data.errors,
            warnings=price_data.warnings,
            calculation_time=start_time
        )

        if not price_data.is_valid:
            logger.warning(f"Price calculation failed for product {product.id}: {price_data.errors}")
            return result

        # Update product fields
        if cost_price is not None:
            product.cost_price = price_data.cost_price
        product.margin_75_price = price_data.margin_75_price
        product.discount_percentage = price_data.discount_percentage
        product.last_price_update = timezone.now()

        # Save if requested
        if save:
            try:
                update_fields = ['margin_75_price', 'discount_percentage', 'last_price_update']
                if cost_price is not None:
                    update_fields.append('cost_price')

                product.save(update_fields=update_fields)

            except Exception as e:
                result.success = False
                result.errors.append(f"Failed to save product: {str(e)}")
                logger.error(f"Failed to save product {product.id}: {e}")

        return result

    def batch_update_pricing(self, products: Union[models.QuerySet, List[WholesaleProduct]],
                           cost_prices: Optional[Dict[int, Decimal]] = None,
                           use_transaction: bool = True,
                           chunk_size: int = 100) -> BatchResult:
        """
        Update pricing for multiple products efficiently.

        Args:
            products: QuerySet or list of WholesaleProduct instances
            cost_prices: Optional mapping of product_id to new cost_price
            use_transaction: Whether to wrap in database transaction
            chunk_size: Number of products to process per batch

        Returns:
            BatchResult with detailed operation statistics
        """
        start_time = timezone.now()
        batch_result = BatchResult()

        # Convert to list if QuerySet
        if hasattr(products, '__iter__') and not isinstance(products, list):
            products = list(products)

        batch_result.total_processed = len(products)

        def _process_batch():
            for i in range(0, len(products), chunk_size):
                chunk = products[i:i + chunk_size]

                for product in chunk:
                    cost_price = None
                    if cost_prices and product.id in cost_prices:
                        cost_price = cost_prices[product.id]

                    try:
                        result = self.update_product_pricing(
                            product,
                            cost_price=cost_price,
                            save=False  # We'll bulk save later
                        )

                        batch_result.results.append(result)

                        if result.success:
                            batch_result.successful_updates += 1
                        else:
                            batch_result.failed_updates += 1
                            batch_result.errors.extend(result.errors)

                        batch_result.warnings.extend(result.warnings)

                    except Exception as e:
                        batch_result.failed_updates += 1
                        batch_result.errors.append(f"Product {product.id}: {str(e)}")
                        logger.error(f"Error processing product {product.id}: {e}")

                # Bulk save successful updates in chunks
                successful_products = [
                    products[j] for j in range(i, min(i + chunk_size, len(products)))
                    if j < len(batch_result.results) and batch_result.results[j].success
                ]

                if successful_products:
                    WholesaleProduct.objects.bulk_update(
                        successful_products,
                        ['cost_price', 'margin_75_price', 'discount_percentage', 'last_price_update'],
                        batch_size=chunk_size
                    )

        # Execute with or without transaction
        try:
            if use_transaction:
                with transaction.atomic():
                    _process_batch()
            else:
                _process_batch()

        except Exception as e:
            batch_result.errors.append(f"Batch processing failed: {str(e)}")
            logger.error(f"Batch price update failed: {e}")

        # Calculate processing time
        end_time = timezone.now()
        batch_result.processing_time = (end_time - start_time).total_seconds()

        return batch_result


class PriceAnalyzer:
    """Analyzes pricing data and generates reports."""

    def __init__(self):
        self.calculator = PriceCalculator()

    def analyze_product_pricing(self, products: Optional[models.QuerySet] = None) -> PricingStatistics:
        """
        Analyze pricing statistics for products.

        Args:
            products: Optional QuerySet to analyze (defaults to all active products)

        Returns:
            PricingStatistics with comprehensive analysis
        """
        if products is None:
            products = WholesaleProduct.objects.filter(is_active=True)

        stats = PricingStatistics()
        stats.total_products = products.count()

        if stats.total_products == 0:
            return stats

        # Basic counts
        stats.products_with_cost = products.filter(cost_price__isnull=False, cost_price__gt=0).count()
        stats.products_with_margin_75 = products.filter(margin_75_price__isnull=False).count()
        stats.products_with_discount = products.filter(discount_percentage__isnull=False).count()

        # Aggregate statistics
        aggregates = products.filter(
            cost_price__isnull=False,
            cost_price__gt=0
        ).aggregate(
            avg_cost=Avg('cost_price'),
            min_cost=Min('cost_price'),
            max_cost=Max('cost_price'),
            avg_margin_75=Avg('margin_75_price'),
            avg_discount=Avg('discount_percentage'),
            min_discount=Min('discount_percentage'),
            max_discount=Max('discount_percentage')
        )

        stats.avg_cost_price = aggregates['avg_cost']
        stats.min_cost_price = aggregates['min_cost']
        stats.max_cost_price = aggregates['max_cost']
        stats.avg_margin_75_price = aggregates['avg_margin_75']
        stats.avg_discount_percentage = aggregates['avg_discount']
        stats.min_discount_percentage = aggregates['min_discount']
        stats.max_discount_percentage = aggregates['max_discount']

        # Calculate average profit margin for products with both cost and wholesale price
        products_with_profit_data = products.filter(
            cost_price__isnull=False,
            cost_price__gt=0,
            wholesale_price__isnull=False,
            wholesale_price__gt=0
        )

        if products_with_profit_data.exists():
            # Calculate profit margins dynamically
            profit_margins = []
            for product in products_with_profit_data:
                margin = self.calculator.calculate_profit_margin(
                    product.wholesale_price, product.cost_price
                )
                if margin is not None:
                    profit_margins.append(margin)

            if profit_margins:
                stats.avg_profit_margin = sum(profit_margins) / len(profit_margins)

        # Special case counts
        stats.high_discount_products = products.filter(
            discount_percentage__gt=50
        ).count()

        stats.low_margin_products = products_with_profit_data.extra(
            where=[
                "((wholesale_price - cost_price) / cost_price * 100) < %s"
            ],
            params=[10]
        ).count()

        stats.negative_margin_products = products_with_profit_data.extra(
            where=[
                "wholesale_price < cost_price"
            ]
        ).count()

        return stats

    def generate_pricing_report(self, products: Optional[models.QuerySet] = None,
                              format_type: str = 'text') -> str:
        """
        Generate a comprehensive pricing report.

        Args:
            products: Optional QuerySet to analyze
            format_type: Format for report ('text', 'html', 'json')

        Returns:
            Formatted report string
        """
        stats = self.analyze_product_pricing(products)

        if format_type == 'text':
            return self._generate_text_report(stats)
        elif format_type == 'html':
            return self._generate_html_report(stats)
        elif format_type == 'json':
            return self._generate_json_report(stats)
        else:
            raise ValueError(f"Unsupported format_type: {format_type}")

    def _generate_text_report(self, stats: PricingStatistics) -> str:
        """Generate a text-based pricing report."""
        report_lines = [
            "WHOLESALE PRICING ANALYSIS REPORT",
            "=" * 50,
            f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "OVERVIEW",
            "-" * 20,
            f"Total Products: {stats.total_products:,}",
            f"Products with Cost Price: {stats.products_with_cost:,} ({stats.products_with_cost/stats.total_products*100:.1f}%)" if stats.total_products > 0 else "Products with Cost Price: 0",
            f"Products with 75% Margin Price: {stats.products_with_margin_75:,}",
            f"Products with Discount %: {stats.products_with_discount:,}",
            "",
            "PRICING STATISTICS",
            "-" * 20,
        ]

        if stats.avg_cost_price:
            report_lines.extend([
                f"Average Cost Price: ${stats.avg_cost_price:.2f}",
                f"Cost Price Range: ${stats.min_cost_price:.2f} - ${stats.max_cost_price:.2f}",
            ])

        if stats.avg_margin_75_price:
            report_lines.append(f"Average 75% Margin Price: ${stats.avg_margin_75_price:.2f}")

        if stats.avg_discount_percentage is not None:
            report_lines.extend([
                f"Average Discount: {stats.avg_discount_percentage:.1f}%",
                f"Discount Range: {stats.min_discount_percentage:.1f}% - {stats.max_discount_percentage:.1f}%",
            ])

        if stats.avg_profit_margin is not None:
            report_lines.append(f"Average Profit Margin: {stats.avg_profit_margin:.1f}%")

        report_lines.extend([
            "",
            "ALERTS",
            "-" * 20,
            f"High Discount Products (>50%): {stats.high_discount_products:,}",
            f"Low Margin Products (<10%): {stats.low_margin_products:,}",
            f"Negative Margin Products: {stats.negative_margin_products:,}",
        ])

        return "\n".join(report_lines)

    def _generate_html_report(self, stats: PricingStatistics) -> str:
        """Generate an HTML-based pricing report."""
        # Implementation for HTML report would go here
        return "<html><body>HTML report not implemented yet</body></html>"

    def _generate_json_report(self, stats: PricingStatistics) -> str:
        """Generate a JSON-based pricing report."""
        import json
        from decimal import Decimal

        def decimal_serializer(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError

        report_data = {
            'generated_at': timezone.now().isoformat(),
            'total_products': stats.total_products,
            'products_with_cost': stats.products_with_cost,
            'products_with_margin_75': stats.products_with_margin_75,
            'products_with_discount': stats.products_with_discount,
            'avg_cost_price': stats.avg_cost_price,
            'avg_margin_75_price': stats.avg_margin_75_price,
            'avg_discount_percentage': stats.avg_discount_percentage,
            'avg_profit_margin': stats.avg_profit_margin,
            'min_cost_price': stats.min_cost_price,
            'max_cost_price': stats.max_cost_price,
            'min_discount_percentage': stats.min_discount_percentage,
            'max_discount_percentage': stats.max_discount_percentage,
            'high_discount_products': stats.high_discount_products,
            'low_margin_products': stats.low_margin_products,
            'negative_margin_products': stats.negative_margin_products
        }

        return json.dumps(report_data, indent=2, default=decimal_serializer)


# Convenience functions for common operations
def calculate_product_pricing(product: WholesaleProduct, cost_price: Optional[Decimal] = None) -> CalculationResult:
    """
    Convenience function to calculate pricing for a single product.

    Args:
        product: WholesaleProduct instance
        cost_price: Optional new cost price

    Returns:
        CalculationResult
    """
    manager = ProductPriceManager()
    return manager.update_product_pricing(product, cost_price)


def batch_calculate_pricing(products: Union[models.QuerySet, List[WholesaleProduct]],
                          cost_prices: Optional[Dict[int, Decimal]] = None) -> BatchResult:
    """
    Convenience function for batch price calculations.

    Args:
        products: Products to process
        cost_prices: Optional mapping of product_id to new cost_price

    Returns:
        BatchResult
    """
    manager = ProductPriceManager()
    return manager.batch_update_pricing(products, cost_prices)


def generate_pricing_analysis(products: Optional[models.QuerySet] = None) -> PricingStatistics:
    """
    Convenience function to generate pricing analysis.

    Args:
        products: Optional QuerySet to analyze

    Returns:
        PricingStatistics
    """
    analyzer = PriceAnalyzer()
    return analyzer.analyze_product_pricing(products)


def generate_pricing_report(products: Optional[models.QuerySet] = None, format_type: str = 'text') -> str:
    """
    Convenience function to generate pricing report.

    Args:
        products: Optional QuerySet to analyze
        format_type: Report format ('text', 'html', 'json')

    Returns:
        Formatted report string
    """
    analyzer = PriceAnalyzer()
    return analyzer.generate_pricing_report(products, format_type)