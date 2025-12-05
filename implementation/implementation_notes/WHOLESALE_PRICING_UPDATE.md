# Wholesale Product Pricing Update Feature

## Overview

Enhanced the WholesaleProduct model with new pricing calculation fields to support the price update feature. This allows for automatic calculation of 75% margin pricing and discount percentages.

## New Fields Added

### WholesaleProduct Model

1. **margin_75_price** (DecimalField)
   - Stores the 75% margin price calculated as `Cost ÷ 0.25`
   - Max digits: 10, decimal places: 2
   - Nullable and blank
   - Help text: "75% margin price (Cost ÷ 0.25)"

2. **discount_percentage** (DecimalField)
   - Stores the discount percentage from the 75% margin price
   - Max digits: 5, decimal places: 2
   - Nullable and blank
   - Help text: "Discount percentage from 75% margin price"

3. **last_price_update** (DateTimeField)
   - Tracks when prices were last updated
   - Nullable and blank
   - Help text: "When prices were last updated"

## New Methods Added

### Model Methods

1. **calculate_margin_75_price()**
   - Calculates the 75% margin price from cost_price
   - Returns: `cost_price / 0.25` if cost_price > 0, else None

2. **calculate_discount_percentage()**
   - Calculates discount percentage from 75% margin price
   - Formula: `((margin_75_price - wholesale_price) / margin_75_price) * 100`
   - Returns minimum of 0 (no negative discounts)

3. **update_calculated_pricing()**
   - Updates all calculated pricing fields
   - Sets last_price_update to current timestamp
   - Saves only the updated fields for efficiency

### Enhanced save() Method

The model's save method now automatically calculates `margin_75_price` when a `cost_price` is present.

## Admin Interface Updates

### New Display Fields

Added to WholesaleProductAdmin list_display:
- `margin_75_price`
- `discount_percentage`
- `last_price_update`

### New Admin Methods

1. **margin_75_price()** - Displays formatted 75% margin price
2. **discount_percentage()** - Displays color-coded discount percentage
3. **update_calculated_pricing()** - Admin action to bulk update pricing fields

### New Fieldsets

Added "Calculated Pricing" fieldset in the admin form containing:
- margin_75_price (readonly)
- discount_percentage (readonly)
- last_price_update (readonly)

## Database Changes

### Migrations Applied

1. **0007_add_wholesale_pricing_fields.py**
   - Added the three new pricing fields
   - Removed deprecated total_products field from WholesaleSchool

2. **0008_add_wholesale_pricing_indexes.py**
   - Added database indexes for performance:
     - Index on margin_75_price
     - Index on discount_percentage
     - Index on last_price_update

## Usage Examples

### Calculate Pricing Programmatically

```python
from clubs.models_wholesale import WholesaleProduct

# Get a product
product = WholesaleProduct.objects.get(cin7_id='PRODUCT_001')

# Update all calculated pricing fields
product.update_calculated_pricing()

# Access calculated values
print(f"75% Margin Price: ${product.margin_75_price}")
print(f"Discount: {product.discount_percentage}%")
print(f"Last Updated: {product.last_price_update}")
```

### Admin Interface

1. Navigate to Admin > Wholesale Products
2. Use the "Update calculated pricing fields" action to bulk update products
3. View pricing calculations in the list view
4. Access detailed pricing in the product edit form

## Validation and Testing

All new functionality has been tested for:
- ✅ Model field creation and validation
- ✅ Pricing calculation accuracy
- ✅ Database migration success
- ✅ Admin interface functionality
- ✅ Method functionality in Django shell
- ✅ Index creation for performance

## Performance Considerations

- Database indexes added for efficient filtering and sorting
- `update_calculated_pricing()` only saves modified fields
- Readonly fields in admin prevent accidental manual editing
- Calculations use Decimal for financial precision

## Integration Notes

The new pricing fields integrate seamlessly with:
- Existing CIN7 sync processes
- Current admin workflows
- Product filtering and reporting
- Price update automation features

## Future Enhancements

Consider adding:
- Bulk pricing update management commands
- Price history tracking
- Automated pricing alerts
- Integration with external pricing services