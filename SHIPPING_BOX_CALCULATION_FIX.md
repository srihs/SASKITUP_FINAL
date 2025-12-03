# Shipping Box Calculation Fix

## Issue Summary

**Problem**: Quotation shipping boxes were calculated incorrectly, resulting in 2 boxes when only 1 box was needed.

**Example**:
- Cart: 1 x Boys Shirt (qty: 1) + 1 x Goalie Top (qty: 1) + addons
- **Before**: 2 boxes, $33.00 shipping
- **After**: 1 box, $16.50 shipping (50% reduction!)

## Root Cause

The bug was in `/Users/sas/Repos/SASKITUP/quotations/models.py` in the `Quotation.calculate_shipping_cost()` method (lines 776-803).

### Original Logic (INCORRECT)
```python
for item in items:
    if item.is_addon:
        continue

    capacity_key = get_capacity_key_for_product(item.product)

    # Calculate boxes for EACH ITEM independently (BUG!)
    boxes = shipping_settings.calculate_boxes_needed(capacity_key, item.quantity)
    total_boxes += boxes
```

**Problem**: Each item calculated boxes independently:
- Item 1 (Boys Shirt, qty=1): `ceil(1 / 8) = 1 box`
- Item 2 (Goalie Top, qty=1): `ceil(1 / 8) = 1 box`
- **Total: 2 boxes** (WRONG!)

### Fixed Logic (CORRECT)
```python
# Step 1: Group items by capacity_key and accumulate quantities
capacity_groups = {}
for item in items:
    if item.is_addon:
        continue

    capacity_key = get_capacity_key_for_product(item.product)

    if capacity_key not in capacity_groups:
        capacity_groups[capacity_key] = {'total_quantity': 0, 'items': []}

    capacity_groups[capacity_key]['total_quantity'] += item.quantity

# Step 2: Calculate boxes for each capacity group's TOTAL quantity
total_boxes = 0
for capacity_key, group_data in capacity_groups.items():
    total_quantity = group_data['total_quantity']
    boxes = shipping_settings.calculate_boxes_needed(capacity_key, total_quantity)
    total_boxes += boxes
```

**Correct Calculation**:
- Capacity group 'sideline_jackets': 2 total units (Boys Shirt + Goalie Top)
- Boxes: `ceil(2 / 8) = 1 box`
- **Total: 1 box** (CORRECT!)

## Changes Made

### File: `/Users/sas/Repos/SASKITUP/quotations/models.py`

**Modified Function**: `Quotation.calculate_shipping_cost()` (lines 776-826)

**Changes**:
1. Added capacity grouping logic before box calculation
2. Items with the same `capacity_key` now have their quantities summed
3. Box calculation is performed on the total quantity per capacity group
4. Added detailed debug logging to trace the calculation

**Key Code Section**:
```python
# Line 776-807: Group items by capacity_key
capacity_groups = {}
items = self.items.select_related('product_content_type').all()

for item in items:
    if item.is_addon:
        logger.debug(f"Skipping addon item {item.id} ({item.product_name})")
        continue

    if not item.product:
        logger.warning(f"QuotationItem {item.id} has no product, skipping")
        continue

    capacity_key = get_capacity_key_for_product(item.product)

    if capacity_key not in capacity_groups:
        capacity_groups[capacity_key] = {
            'total_quantity': 0,
            'items': []
        }

    capacity_groups[capacity_key]['total_quantity'] += item.quantity
    capacity_groups[capacity_key]['items'].append({
        'id': item.id,
        'name': item.product_name,
        'quantity': item.quantity
    })

# Line 809-825: Calculate boxes per capacity group
total_boxes = 0
for capacity_key, group_data in capacity_groups.items():
    total_quantity = group_data['total_quantity']
    boxes = shipping_settings.calculate_boxes_needed(capacity_key, total_quantity)

    if boxes is None:
        logger.warning(f"Could not calculate boxes for capacity_key '{capacity_key}', using fallback")
        boxes = math.ceil(total_quantity / 8)

    total_boxes += boxes

    # Debug logging
    items_summary = ', '.join([f"{item['name']} (qty: {item['quantity']})" for item in group_data['items']])
    logger.debug(f"Capacity group '{capacity_key}': {total_quantity} total units = {boxes} boxes | Items: {items_summary}")
```

## Verification

### Session-Based Calculation (`calculate_session_shipping()`)
**Status**: ✓ Already correct

The session-based shipping calculation in `/Users/sas/Repos/SASKITUP/quotations/views.py` (lines 177-214) was already using the correct grouping logic and did not require changes.

### Testing Results

**Test Quotation**: Q-20251203-0003
- **Before Fix**: 2 boxes, $33.00 shipping
- **After Fix**: 1 box, $16.50 shipping

**Items**:
- Alfriston College Boys Junior Shirt - Medium (qty: 1, is_addon: False)
- Adults Goalie Top - S (qty: 1, is_addon: False)
- Heat Transfer (Small) - 3-4 colors (qty: 1, is_addon: True) ← Skipped
- Screen Print (Small) - 5-7 colors (qty: 1, is_addon: True) ← Skipped
- Emb Applique (Small) (LOW stitch) - EMB (qty: 1, is_addon: True) ← Skipped

**Calculation**:
- Capacity key: 'sideline_jackets' (8 units/box)
- Total quantity: 2 garments
- Boxes: `ceil(2 / 8) = 1 box`
- Shipping region: Nelson ($16.50/box)
- **Final cost**: $16.50 ✓

## Product Capacity Reference

| Product Type | Units per Box |
|-------------|---------------|
| Sideline Jackets | 8 |
| Jackets | 25 |
| Hoodies | 30 |
| Pants | 35 |
| Jerseys / Softball Tops | 60 |
| Polos / Tees / Singlets / Dresses | 70 |
| Netball / Touch / Tag Skirts / Shorts | 80 |
| Tights / Socks / Caps / Bucket Hats | 80-100 |

## Example Scenarios

### Scenario 1: Single product type, low quantity
**Cart**: 5 hoodies (qty: 5)
- Capacity: 30 units/box
- Calculation: `ceil(5 / 30) = 1 box`

### Scenario 2: Single product type, high quantity
**Cart**: 25 sweatshirts (qty: 25)
- Capacity: 8 units/box
- Calculation: `ceil(25 / 8) = 4 boxes`

### Scenario 3: Mixed product types
**Cart**:
- 3 jackets (qty: 3, capacity: 25 units/box)
- 5 hoodies (qty: 5, capacity: 30 units/box)

**Calculation**:
- Jackets: `ceil(3 / 25) = 1 box`
- Hoodies: `ceil(5 / 30) = 1 box`
- **Total: 2 boxes**

### Scenario 4: Multiple items, same capacity type (THE BUG CASE)
**Cart**:
- 1 Boys Shirt (qty: 1, capacity: 8 units/box)
- 1 Goalie Top (qty: 1, capacity: 8 units/box)

**Before Fix** (WRONG):
- Boys Shirt: `ceil(1 / 8) = 1 box`
- Goalie Top: `ceil(1 / 8) = 1 box`
- **Total: 2 boxes** ❌

**After Fix** (CORRECT):
- Group: Both items share capacity key 'sideline_jackets'
- Total quantity: 1 + 1 = 2
- Calculation: `ceil(2 / 8) = 1 box`
- **Total: 1 box** ✓

## Impact

### Benefits
1. **Accurate shipping costs** - No overcharging customers
2. **Correct box counts** - Proper inventory and logistics planning
3. **Better UX** - Customers see fair shipping charges
4. **Cost savings** - 50% reduction in example case (2 boxes → 1 box)

### Affected Areas
- Quotation creation and editing
- Shipping cost calculation
- CIN7 sync (shipping boxes field)
- PDF quotation generation
- Email quotations

## Debug Logging

The fix includes comprehensive debug logging to trace box calculations:

```
DEBUG: Skipping addon item <id> (<name>) for shipping calculation
DEBUG: Capacity group '<capacity_key>': <total_qty> total units = <boxes> boxes | Items: <item1>, <item2>, ...
INFO: Quotation <id>: <boxes> boxes to <region> = $<cost> (RD: <true/false>)
```

## Deployment Notes

1. **No database migrations required** - Logic fix only
2. **Existing quotations** - Run `quotation.calculate_shipping_cost()` to recalculate
3. **Testing** - Verify with various product type combinations
4. **Monitoring** - Check logs for capacity key fallbacks

## Date
2025-12-03

## Related Files
- `/Users/sas/Repos/SASKITUP/quotations/models.py` (Modified)
- `/Users/sas/Repos/SASKITUP/quotations/views.py` (Verified, no changes needed)
- `/Users/sas/Repos/SASKITUP/quotations/models_shipping.py` (Reference)
- `/Users/sas/Repos/SASKITUP/quotations/utils_shipping.py` (Reference)
