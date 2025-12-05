# Variation Pricing Update - Product Detail Page

## Summary
Updated the quotation product detail page to dynamically display variation-specific SKU and pricing when users select product variations (size/color).

## Changes Made

### 1. Backend - `/quotations/views.py`
**Location:** `ProductDetailForQuotationView.get_context_data()` method (lines 1169-1219)

**Enhancement:** Added comprehensive pricing information to variation data with fallback logic matching the cart implementation.

**Pricing Fallback Priority:**
1. `variation.margin_75_price` (variation-specific margin price)
2. `product.margin_75_price` (parent product margin price) ← **Fallback**
3. Calculated from `variation.cost_price` (cost / 0.25)
4. Calculated from `product.cost_price` (cost / 0.25)
5. `variation.retail_price`
6. `product.retail_price`
7. `variation.regular_price`
8. `product.regular_price`

**Added Fields to Variation Data:**
- `sku`: Variation-specific SKU
- `margin_75_price`: Original price (for strikethrough display)
- `discount_amount`: Dollar amount saved
- `discount_percentage`: Percentage discount
- `price`: Selling price

### 2. Frontend - `/quotations/templates/quotations/product_detail.html`

#### Template Changes (lines 894-932)
1. **SKU Display** (line 899):
   - Added `id="productSku"` to make it dynamically updatable
   - Wrapped SKU value in `<span>` for JavaScript targeting

2. **Price Container** (line 911):
   - Added `id="priceContainer"` for dynamic price updates
   - Added `id="discountBadge"` to discount badge
   - Added `id="marginPrice"` to original price element
   - Added `id="productPrice"` to selling price element

#### JavaScript Changes (lines 1186-1313)

**New Function: `updateProductDisplay(variation)` (lines 1228-1269)**
- Updates SKU display with variation SKU
- Updates pricing display with margin and selling prices
- Shows/hides discount badge based on pricing
- Formats prices with proper comma separation
- Handles both discount and regular pricing scenarios

**Enhanced Function: `selectColor(color, variationMap, buttonElement)` (lines 1186-1231)**
- Auto-updates pricing when only one size available for selected color
- Calls `updateProductDisplay()` for single-size color variations

**Enhanced Function: `addVariationToQuote(size, variation, buttonElement)` (lines 1271-1313)**
- Added call to `updateProductDisplay(variation)` after size selection (line 1297)
- Updates SKU and pricing immediately when size selected

## User Experience Flow

### Without Variations
- Shows main product SKU and pricing
- No dynamic updates

### With Size-Only Variations
1. User clicks size button
2. **SKU updates** to variation SKU (e.g., 29990)
3. **Pricing updates** to show:
   - Strikethrough margin price: ~~$71.09~~
   - Bold selling price: **$59.95**
   - Discount badge: -16%

### With Color + Size Variations
1. User clicks color swatch
2. Main image updates to color variation
3. Size buttons populate for selected color
4. User clicks size button
5. **SKU and pricing update** as above

## Example Display

**Before Selection:**
```
SKU: GENERIC-001
$59.95
```

**After Selecting "Size: 10":**
```
SKU: 29990
-16%  ~~$71.09~~  $59.95
```

## Fallback Logic Example

### Scenario 1: Variation has margin_75_price
```python
variation.margin_75_price = $75.00
variation.price = $59.95
# Display: ~~$75.00~~ $59.95 (-20%)
```

### Scenario 2: Variation missing margin_75_price, use product's
```python
variation.margin_75_price = None
product.margin_75_price = $71.09
variation.price = $59.95
# Display: ~~$71.09~~ $59.95 (-16%)
```

### Scenario 3: Calculate from cost_price
```python
variation.margin_75_price = None
product.margin_75_price = None
variation.cost_price = $14.99
# Calculated: $14.99 / 0.25 = $59.96
variation.price = $59.95
# Display: ~~$59.96~~ $59.95 (0%)
```

## Testing Recommendations

1. **Products without variations:**
   - Verify main product SKU and pricing display correctly
   - No dynamic updates should occur

2. **Products with size-only variations:**
   - Click different sizes
   - Verify SKU updates to variation SKU
   - Verify pricing updates with correct discount calculation
   - Test variations with and without margin_75_price

3. **Products with color + size variations:**
   - Select color, then size
   - Verify image, SKU, and pricing all update
   - Test single-size colors (auto-update pricing on color selection)

4. **Edge cases:**
   - Variation without SKU (should keep main product SKU)
   - Variation without margin price (should use product fallback)
   - Variation without discount (should show single price)
   - Out-of-stock variations (should be disabled)

## Browser Compatibility
- Modern browsers with ES6+ support
- Uses `toLocaleString()` for price formatting
- Fallback price formatting if locale not supported

## Performance Notes
- No additional AJAX calls needed (all data loaded on page load)
- Minimal DOM manipulation (only updating specific elements)
- Smooth transitions with CSS opacity changes

## Files Modified
1. `/Users/sas/Repos/SASKITUP/quotations/views.py`
2. `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/product_detail.html`

## Deployment Notes
- No database migrations required
- No new dependencies
- Clear browser cache to see template changes
- Test in development before production deployment
