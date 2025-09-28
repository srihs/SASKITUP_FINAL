# Wholesale Price Calculation Engine

## Overview

The comprehensive price calculation engine provides a robust, reusable system for managing wholesale product pricing calculations. It supports multiple integration points and offers enhanced validation, batch processing, and reporting capabilities.

## Features

### Core Calculations
- **75% Margin Price**: Cost ÷ 0.25 (gives 75% profit margin)
- **Discount Percentage**: ((75% Margin Price - Actual RRP) ÷ 75% Margin Price) × 100
- **Profit Margin**: ((Selling Price - Cost Price) ÷ Cost Price) × 100

### Edge Case Handling
- Zero cost prices
- Negative values
- Invalid decimal inputs
- Division by zero scenarios
- Very large/small numbers
- Unicode input strings

### Validation & Error Handling
- Input validation with meaningful error messages
- Comprehensive logging
- Graceful error recovery
- Warning system for suspicious values

### Performance Features
- Batch processing with configurable chunk sizes
- Transaction safety with rollback capability
- Parallel processing optimization
- Memory-efficient operations
- Progress tracking for large operations

## Integration Points

### 1. Django Management Commands

#### Enhanced Management Command Usage

```bash
# Use legacy engine (existing behavior)
python manage.py update_wholesale_prices --csv-file /path/to/file.csv

# Use enhanced engine with batch processing
python manage.py update_wholesale_prices --csv-file /path/to/file.csv --use-enhanced-engine

# Generate comprehensive analysis report
python manage.py update_wholesale_prices --csv-file /path/to/file.csv --use-enhanced-engine --generate-analysis-report

# Dry run with enhanced engine and verbose output
python manage.py update_wholesale_prices --csv-file /path/to/file.csv --use-enhanced-engine --dry-run --verbose

# Save detailed reports
python manage.py update_wholesale_prices --csv-file /path/to/file.csv --use-enhanced-engine --report-file pricing_report.txt
```

#### Performance Comparison

| Feature | Legacy Engine | Enhanced Engine |
|---------|---------------|-----------------|
| Processing Method | Row-by-row | Batch processing |
| Validation | Basic | Comprehensive |
| Error Handling | Limited | Robust |
| Performance | ~100 products/min | ~500+ products/min |
| Transaction Safety | Per-row | Batch transactions |
| Reporting | Basic stats | Full analytics |

### 2. Django Admin Interface

#### New Admin Actions

1. **Update pricing (enhanced engine)**: Uses new calculation engine with enhanced validation
2. **Generate pricing analysis report**: Downloads comprehensive pricing report
3. **Analyze pricing issues**: Identifies and reports pricing problems

#### Usage in Admin

1. Navigate to Wholesale Products admin
2. Select products to process
3. Choose "Update pricing (enhanced engine)" from actions dropdown
4. Click "Go" to execute

#### Admin Action Features

- Real-time validation feedback
- Batch processing with progress indicators
- Detailed error and warning reporting
- Success rate calculations
- Processing time metrics

### 3. Programmatic Usage

#### Single Product Calculation

```python
from clubs.utils.price_calculation import calculate_product_pricing
from clubs.models_wholesale import WholesaleProduct

# Get a product
product = WholesaleProduct.objects.get(id=123)

# Calculate pricing
result = calculate_product_pricing(product, cost_price=Decimal('25.00'))

if result.success:
    print(f"Updated {product.name}")
    print(f"75% Margin Price: ${result.new_values.margin_75_price}")
    print(f"Discount: {result.new_values.discount_percentage}%")
else:
    print(f"Calculation failed: {result.errors}")
```

#### Batch Processing

```python
from clubs.utils.price_calculation import batch_calculate_pricing
from clubs.models_wholesale import WholesaleProduct
from decimal import Decimal

# Get products to process
products = WholesaleProduct.objects.filter(school__name__contains="Test School")

# Optional: specify new cost prices
cost_prices = {
    product.id: Decimal('20.00') for product in products[:5]
}

# Process batch
batch_result = batch_calculate_pricing(products, cost_prices=cost_prices)

print(f"Processed: {batch_result.total_processed}")
print(f"Successful: {batch_result.successful_updates}")
print(f"Failed: {batch_result.failed_updates}")
print(f"Success Rate: {batch_result.success_rate:.1f}%")
print(f"Processing Time: {batch_result.processing_time:.2f}s")
```

#### Analytics and Reporting

```python
from clubs.utils.price_calculation import generate_pricing_analysis, generate_pricing_report
from clubs.models_wholesale import WholesaleProduct

# Generate statistics for all products
stats = generate_pricing_analysis()

print(f"Total Products: {stats.total_products}")
print(f"Average Discount: {stats.avg_discount_percentage:.1f}%")
print(f"High Discount Products: {stats.high_discount_products}")
print(f"Negative Margin Products: {stats.negative_margin_products}")

# Generate detailed report
report = generate_pricing_report(format_type='text')
print(report)

# Save JSON report
json_report = generate_pricing_report(format_type='json')
with open('pricing_analysis.json', 'w') as f:
    f.write(json_report)
```

### 4. API-Ready Functions

The calculation engine is designed to be easily integrated into API endpoints:

```python
# views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response
from clubs.utils.price_calculation import ProductPriceManager, PriceAnalyzer
from decimal import Decimal

@api_view(['POST'])
def update_product_pricing(request, product_id):
    """API endpoint to update product pricing"""
    try:
        product = WholesaleProduct.objects.get(id=product_id)
        cost_price = Decimal(request.data.get('cost_price'))

        manager = ProductPriceManager()
        result = manager.update_product_pricing(product, cost_price=cost_price)

        if result.success:
            return Response({
                'success': True,
                'margin_75_price': float(result.new_values.margin_75_price),
                'discount_percentage': float(result.new_values.discount_percentage)
            })
        else:
            return Response({
                'success': False,
                'errors': result.errors
            }, status=400)

    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
def pricing_analytics(request):
    """API endpoint for pricing analytics"""
    analyzer = PriceAnalyzer()
    stats = analyzer.analyze_product_pricing()

    return Response({
        'total_products': stats.total_products,
        'products_with_cost': stats.products_with_cost,
        'avg_discount_percentage': float(stats.avg_discount_percentage) if stats.avg_discount_percentage else None,
        'high_discount_products': stats.high_discount_products,
        'negative_margin_products': stats.negative_margin_products
    })
```

## Core Components

### 1. PriceCalculator

Core calculation engine with comprehensive validation.

```python
from clubs.utils.price_calculation import PriceCalculator
from decimal import Decimal

calculator = PriceCalculator()

# Parse various input formats
cost = calculator.parse_decimal("$25.99")  # Decimal('25.99')
cost = calculator.parse_decimal("25,50")   # Decimal('25.50')

# Calculate 75% margin price
margin_75 = calculator.calculate_margin_75_price(Decimal('20.00'))  # Decimal('80.00')

# Calculate discount percentage
discount = calculator.calculate_discount_percentage(
    Decimal('100.00'),  # 75% margin price
    Decimal('85.00')    # actual price
)  # Decimal('15.00') - 15% discount

# Calculate all prices at once
price_data = calculator.calculate_all_prices(
    cost_price=Decimal('25.00'),
    wholesale_price=Decimal('80.00')
)

if price_data.is_valid:
    print(f"75% Margin: ${price_data.margin_75_price}")
    print(f"Discount: {price_data.discount_percentage}%")
    print(f"Profit Margin: {price_data.profit_margin}%")
else:
    print(f"Validation errors: {price_data.errors}")
```

### 2. ProductPriceManager

Manages product pricing updates with database integration.

```python
from clubs.utils.price_calculation import ProductPriceManager

manager = ProductPriceManager()

# Update single product
result = manager.update_product_pricing(product, cost_price=Decimal('30.00'))

# Batch update with transaction safety
batch_result = manager.batch_update_pricing(
    products,
    cost_prices=cost_mapping,
    use_transaction=True,
    chunk_size=100
)
```

### 3. PriceAnalyzer

Provides analytics and reporting capabilities.

```python
from clubs.utils.price_calculation import PriceAnalyzer

analyzer = PriceAnalyzer()

# Analyze pricing for specific products
stats = analyzer.analyze_product_pricing(products_queryset)

# Generate reports in different formats
text_report = analyzer.generate_pricing_report(format_type='text')
json_report = analyzer.generate_pricing_report(format_type='json')
```

### 4. Data Classes

#### PriceData
Holds price calculation inputs and results:
- `cost_price`: Product cost price
- `wholesale_price`: Wholesale selling price
- `retail_price`: Retail selling price
- `margin_75_price`: Calculated 75% margin price
- `discount_percentage`: Calculated discount percentage
- `profit_margin`: Calculated profit margin
- `is_valid`: Validation status
- `errors`: List of validation errors
- `warnings`: List of validation warnings

#### CalculationResult
Result of a single product calculation:
- `success`: Operation success status
- `product_id`: Product identifier
- `product_name`: Product name
- `old_values`: Previous price data
- `new_values`: Updated price data
- `errors`: List of errors
- `warnings`: List of warnings
- `calculation_time`: When calculation was performed

#### BatchResult
Result of batch processing operation:
- `total_processed`: Total products processed
- `successful_updates`: Successful updates count
- `failed_updates`: Failed updates count
- `skipped_updates`: Skipped updates count
- `results`: List of individual CalculationResults
- `errors`: List of batch-level errors
- `warnings`: List of batch-level warnings
- `processing_time`: Total processing time in seconds
- `success_rate`: Calculated success rate percentage

#### PricingStatistics
Comprehensive pricing analysis results:
- `total_products`: Total products analyzed
- `products_with_cost`: Products with valid cost prices
- `avg_cost_price`: Average cost price
- `avg_margin_75_price`: Average 75% margin price
- `avg_discount_percentage`: Average discount percentage
- `high_discount_products`: Count of products with >50% discount
- `low_margin_products`: Count of products with <10% profit margin
- `negative_margin_products`: Count of products with negative margins

## Configuration and Customization

### Validation Thresholds

Customize validation limits in PriceValidator:

```python
class PriceValidator:
    MIN_COST_PRICE = Decimal('0.01')     # Minimum valid cost price
    MAX_COST_PRICE = Decimal('100000.00') # Maximum valid cost price
    MAX_DISCOUNT_PERCENTAGE = Decimal('95.00') # Warning threshold for high discounts
    MIN_PROFIT_MARGIN = Decimal('-50.00')      # Warning threshold for low margins
```

### Performance Tuning

Adjust batch processing parameters:

```python
# Larger chunks for better performance, smaller for memory constraints
batch_result = manager.batch_update_pricing(
    products,
    chunk_size=200,        # Process 200 products per chunk
    use_transaction=True   # Use database transactions
)
```

### Error Handling

Configure logging levels:

```python
import logging

# Enable debug logging for detailed troubleshooting
logging.getLogger('clubs.utils.price_calculation').setLevel(logging.DEBUG)
```

## Error Handling and Troubleshooting

### Common Issues

1. **Invalid Cost Prices**
   - Error: "Cost price must be at least $0.01"
   - Solution: Ensure cost prices are positive decimals

2. **Division by Zero**
   - Error: Calculation returns None
   - Solution: Validate cost prices before calculation

3. **Batch Processing Failures**
   - Error: "Batch processing failed"
   - Solution: Check database constraints and memory limits

4. **High Discount Warnings**
   - Warning: "Very high discount percentage: 75%"
   - Action: Review pricing strategy for affected products

### Performance Optimization

1. **Use Batch Processing**: Always prefer batch operations for multiple products
2. **Configure Chunk Sizes**: Adjust based on available memory and database performance
3. **Use Transactions**: Enable transaction safety for data integrity
4. **Monitor Processing Time**: Track performance metrics for optimization

### Best Practices

1. **Always Validate Inputs**: Use the validation system before calculations
2. **Handle Errors Gracefully**: Check success status and handle errors appropriately
3. **Log Operations**: Enable appropriate logging for troubleshooting
4. **Test Performance**: Benchmark batch operations with realistic data sizes
5. **Monitor Results**: Use analytics to identify pricing issues

## Testing

Run the comprehensive test suite:

```bash
# Run all price calculation tests
python manage.py test clubs.tests.test_price_calculation

# Run specific test classes
python manage.py test clubs.tests.test_price_calculation.PriceCalculatorTestCase
python manage.py test clubs.tests.test_price_calculation.BatchProcessingTestCase

# Run with coverage
coverage run --source='.' manage.py test clubs.tests.test_price_calculation
coverage report
```

## Migration from Legacy System

### Step 1: Test with Enhanced Engine

```bash
# Test new engine with dry run
python manage.py update_wholesale_prices --use-enhanced-engine --dry-run --verbose
```

### Step 2: Compare Results

```bash
# Generate comparison report
python manage.py update_wholesale_prices --use-enhanced-engine --generate-analysis-report
```

### Step 3: Gradual Migration

```python
# Use both systems in parallel for validation
legacy_result = product.update_calculated_pricing()  # Legacy method
enhanced_result = calculate_product_pricing(product)  # Enhanced method

# Compare results for consistency
```

### Step 4: Full Migration

```bash
# Switch to enhanced engine for all operations
python manage.py update_wholesale_prices --use-enhanced-engine
```

## Support and Maintenance

### Monitoring

- Monitor batch processing performance
- Track error rates and types
- Review pricing analytics regularly
- Validate calculation accuracy

### Updates

- Keep validation thresholds current
- Update performance parameters as needed
- Enhance error handling based on usage patterns
- Add new features as requirements evolve

### Documentation

This documentation should be updated when:
- New features are added
- Performance characteristics change
- Error handling is enhanced
- Integration points are modified

For technical support or feature requests, consult the development team or create an issue in the project repository.