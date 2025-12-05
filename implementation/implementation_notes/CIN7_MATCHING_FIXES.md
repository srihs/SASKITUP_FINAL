# Cin7 Matching Critical Fixes

## Overview
Fixed two critical errors in the Cin7 product matching implementation that prevented matching from working for TUS, SAS, and LOTTO price types.

## Error 1: AttributeError - Incorrect Field Names Across Models

### Problem
The matching logic assumed all product models use `cin7_sku` and `cin7_barcode` fields, but only WholesaleProduct/WholesaleProductVariation have these fields. Other models use different field names.

### Field Name Mapping

| Model Type | Product SKU Field | Product Barcode Field | Variation SKU Field |
|------------|-------------------|----------------------|---------------------|
| **TUSProduct/TUSProductVariation** | `sku` | `barcode` | `sku` |
| **SASProduct/SASProductVariation** | `sku` | `barcode` | `sku_suffix` |
| **LottoProduct/LottoProductVariation** | `sku` | `barcode` | `sku_suffix` |
| **WholesaleProduct/WholesaleProductVariation** | `cin7_sku` | `cin7_barcode` | `cin7_sku` |

### Solution
Updated the dictionary-building logic in `cin7_match_products` function (lines 3750-3865) to use the correct field names for each model type:

**TUS (retail-schools)**:
- Changed `product.cin7_sku` → `product.sku`
- Changed `product.cin7_barcode` → `product.barcode`
- Changed `variation.cin7_sku` → `variation.sku`

**SAS (sas-clubs)**:
- Changed `product.cin7_sku` → `product.sku`
- Changed `product.cin7_barcode` → `product.barcode`
- Kept `variation.sku_suffix` (already correct)

**LOTTO (lotto-clubs)**:
- Changed `product.cin7_sku` → `product.sku`
- Changed `product.cin7_barcode` → `product.barcode`
- Kept `variation.sku_suffix` (already correct)

**Wholesale (wholesale-schools)**:
- No changes needed (already using `cin7_sku` and `cin7_barcode`)

## Error 2: IntegrityError - match_method Cannot Be Null

### Problem
The reset logic sets `match_method=None`, but the Cin7Product model has a `NOT NULL` constraint on the `match_method` field (line 698 in models.py):

```python
match_method = models.CharField(max_length=100, blank=True, help_text="How product was matched")
```

CharField with `blank=True` but no `null=True` means the field cannot be NULL in the database.

### Error Message
```
(1048, "Column 'match_method' cannot be null")
```

### Solution
Changed the reset logic in line 3679 from:
```python
match_method=None,  # WRONG - causes IntegrityError
```

To:
```python
match_method='',  # CORRECT - empty string for CharField
```

## Files Modified
- `/Users/sas/Repos/SASKITUP/schools/views.py`
  - Lines 3679: Fixed reset logic to use empty string instead of None
  - Lines 3756-3776: Fixed TUS field names
  - Lines 3784-3804: Fixed SAS field names
  - Lines 3812-3832: Fixed LOTTO field names

## Testing Recommendations

### 1. Test Reset Functionality
```bash
# Test that reset no longer causes database errors
curl -X POST http://localhost:8000/schools/wholesale/cin7-match-products/ \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test", "reset_only": true}'
```

### 2. Test Matching for Each Price Type

**TUS Testing**:
```bash
curl -X POST http://localhost:8000/schools/wholesale/cin7-match-products/ \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-tus", "price_type": "TUS"}'
```

**SAS Testing**:
```bash
curl -X POST http://localhost:8000/schools/wholesale/cin7-match-products/ \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-sas", "price_type": "SAS"}'
```

**LOTTO Testing**:
```bash
curl -X POST http://localhost:8000/schools/wholesale/cin7-match-products/ \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-lotto", "price_type": "LOTTO"}'
```

**Wholesale Testing**:
```bash
curl -X POST http://localhost:8000/schools/wholesale/cin7-match-products/ \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-wholesale", "price_type": "Wholesale"}'
```

### 3. Verify Matching Results
After running matching, check the logs for:
- Number of products loaded into memory dictionaries
- Number of successful matches
- Match methods used (should see "sku_exact", "sku_iexact", etc.)
- No AttributeError exceptions

### 4. Database Verification
```sql
-- Check that matches were created successfully
SELECT price_type, COUNT(*), SUM(CASE WHEN matched THEN 1 ELSE 0 END) as matched_count
FROM cin7_products
GROUP BY price_type;

-- Verify match_method field has no NULL values
SELECT COUNT(*) FROM cin7_products WHERE match_method IS NULL;  -- Should return 0

-- Check reset functionality
SELECT COUNT(*) FROM cin7_products WHERE matched = 1 AND match_method = '';  -- Should return 0 after reset
```

## Expected Behavior After Fixes

1. **Reset works without errors**: Setting `match_method=''` prevents IntegrityError
2. **TUS matching works**: Products and variations are found using `sku` and `barcode` fields
3. **SAS matching works**: Products use `sku`/`barcode`, variations use `sku_suffix`
4. **LOTTO matching works**: Products use `sku`/`barcode`, variations use `sku_suffix`
5. **Wholesale matching still works**: No changes to existing `cin7_sku`/`cin7_barcode` logic

## Performance Impact
No performance impact. The fixes only correct field name references - the dictionary-based matching algorithm remains unchanged and highly performant.

## Root Cause Analysis

### Why This Happened
The original implementation was designed for Wholesale products (which have `cin7_sku` and `cin7_barcode` fields) and was later extended to support TUS, SAS, and LOTTO without updating the field name references.

### Prevention
1. Add model field validation in tests
2. Create a field mapping configuration at the top of the function
3. Consider adding a base product interface or mixin to standardize field names across all models in the future

## Related Files
- `/Users/sas/Repos/SASKITUP/schools/models_tus.py` - TUS model definitions
- `/Users/sas/Repos/SASKITUP/clubs/models_sas.py` - SAS model definitions
- `/Users/sas/Repos/SASKITUP/clubs/models_lotto.py` - LOTTO model definitions
- `/Users/sas/Repos/SASKITUP/schools/models.py` - Wholesale and Cin7Product model definitions

## Date
2025-10-10
