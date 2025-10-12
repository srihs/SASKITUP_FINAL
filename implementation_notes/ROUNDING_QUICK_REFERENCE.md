# Margin Price Rounding - Quick Reference

## What Changed?

All 75% margin prices are now rounded to the nearest $5 increment before being displayed or used in calculations.

## Examples

| Original | Rounded | Change |
|----------|---------|--------|
| $78.50   | $80.00  | +$1.50 |
| $76.20   | $75.00  | -$1.20 |
| $163.84  | $165.00 | +$1.16 |
| $52.00   | $50.00  | -$2.00 |
| $50.00   | $50.00  | $0.00  |

## Rounding Rules

- **Values ending in .50**: Round UP (e.g., $7.50 → $10.00)
- **Values below midpoint**: Round DOWN (e.g., $76.20 → $75.00)
- **Values above midpoint**: Round UP (e.g., $78.50 → $80.00)
- **Already at $5 increment**: No change (e.g., $50.00 → $50.00)
- **Zero or null**: Remains zero (e.g., $0.00 → $0.00)

## Where It's Applied

1. **Cart View** - All items in the quotation cart
2. **Product Detail Page** - All product variations
3. **Session Storage** - Rounded values saved to session
4. **All Calculations** - Discount amounts and percentages use rounded values

## Code Location

**File:** `/Users/sas/Repos/SASKITUP/quotations/views.py`

### Helper Function (Line 45-65)
```python
def round_to_nearest_5(value):
    """Round a decimal value to the nearest $5 increment"""
    if not value or value == 0:
        return Decimal('0')
    return (value / Decimal('5')).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * Decimal('5')
```

### Cart View Implementation (Line ~608)
```python
rounded_margin_price = round_to_nearest_5(margin_price)
enriched_item['margin_75_price'] = rounded_margin_price
discount_percentage = int(((rounded_margin_price - unit_price_decimal) / rounded_margin_price) * 100)
```

### Product Detail Implementation (Line ~1450)
```python
rounded_margin_price = round_to_nearest_5(margin_price)
var_data['margin_75_price'] = str(rounded_margin_price)
discount_percentage = (discount_amount / rounded_margin_price * 100).quantize(Decimal('0'))
```

## Testing

Run the Python test to verify rounding logic:
```bash
python3 test_rounding.py
```

Expected output: All tests pass ✅

## Impact

### User-Facing Changes
- Cleaner, more professional pricing
- Easier mental math for customers
- Retail-style rounded prices

### Technical Changes
- Discount percentages recalculated using rounded values
- Session storage contains rounded values
- All downstream calculations use rounded values

### No Impact On
- Database structure (no migrations needed)
- Existing saved quotations
- Unit prices (only margin prices are rounded)
- Total prices (unit prices remain exact)

## Browser Testing Checklist

- [ ] Load cart page - verify margin prices are rounded
- [ ] Check discount percentages are correct
- [ ] Load product detail page - verify variation prices are rounded
- [ ] Add item to cart - verify rounded price persists
- [ ] Update quantity - verify rounded price remains
- [ ] Check cart totals calculation
- [ ] Save quotation - verify rounded values save correctly
- [ ] Load saved quotation - verify rounded values display
- [ ] Generate PDF (if applicable) - verify rounded prices appear

## Rollback

If needed, revert these changes:
1. Remove `ROUND_HALF_UP` from imports (line 12)
2. Remove `round_to_nearest_5()` function (lines 45-65)
3. Restore original cart view calculation (line ~608)
4. Restore original product detail calculation (line ~1450)

## Support

For questions or issues:
- Review: `/Users/sas/Repos/SASKITUP/ROUNDING_IMPLEMENTATION_SUMMARY.md`
- Visual examples: `/Users/sas/Repos/SASKITUP/ROUNDING_VISUAL_COMPARISON.md`
- Git diff: `git diff quotations/views.py`
