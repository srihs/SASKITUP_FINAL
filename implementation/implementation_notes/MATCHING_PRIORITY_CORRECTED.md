# ✅ CORRECTED: Matching Priority for All 4 Models

**IMPORTANT**: Wholesale DOES have variations!

---

## All 4 Models - Matching Priority

### 1. **LOTTO** (lotto-clubs)

| Priority | Excel → Database | Match Type |
|----------|------------------|------------|
| **1** ⭐ | Code → **LottoProductVariation.sku_suffix** | Exact |
| 2 | Code → LottoProductVariation.sku_suffix | Normalized (no spaces) |
| 3 | Code → LottoProduct.sku | Exact |
| 4 | Barcode → LottoProduct.barcode | Exact |

**Field**: `sku_suffix`
**Example**: "R9039 -4--7"

---

### 2. **SAS** (sas-clubs)

| Priority | Excel → Database | Match Type |
|----------|------------------|------------|
| **1** ⭐ | Code → **SASProductVariation.sku_suffix** | Exact |
| 2 | Code → SASProductVariation.sku_suffix | Normalized |
| 3 | Code → SASProduct.sku | Exact |
| 4 | Code → SASProduct.style_code | Exact |
| 5 | Barcode → SASProduct.barcode | Exact |

**Field**: `sku_suffix`
**Example**: "SAS-1234-XL-BLK"

---

### 3. **TUS** / Retail Schools (retail-schools)

| Priority | Excel → Database | Match Type |
|----------|------------------|------------|
| **1** ⭐ | Code → **TUSProductVariation.sku** | Exact |
| 2 | Code → TUSProductVariation.sku | Normalized |
| 3 | Code → TUSProduct.sku | Exact |
| 4 | Barcode → TUSProduct.barcode | Exact |

**Field**: `sku` (NOT sku_suffix!)
**Example**: "TUS-SHIRT-M-RED"

---

### 4. **WHOLESALE** (wholesale-schools) ⚠️ CORRECTED

| Priority | Excel → Database | Match Type |
|----------|------------------|------------|
| **1** ⭐ | Code → **WholesaleProductVariation.cin7_sku** | Exact |
| 2 | Code → WholesaleProductVariation.cin7_sku | Normalized |
| 3 | Code → WholesaleProduct.cin7_sku | Exact |
| 4 | Barcode → WholesaleProduct.cin7_barcode | Exact |

**Field**: `cin7_sku`
**Example**: "WS-12345-L-BLU"
**✅ HAS VARIATIONS**: Yes! (WholesaleProductVariation model exists)

---

## Quick Comparison

| Model | Variation Field | Has Variations? | Notes |
|-------|----------------|-----------------|-------|
| **LOTTO** | `sku_suffix` | ✅ Yes | Standard |
| **SAS** | `sku_suffix` | ✅ Yes | Has style_code too |
| **TUS** | `sku` | ✅ Yes | Uses `sku` not `sku_suffix` |
| **WHOLESALE** | `cin7_sku` | ✅ Yes | CIN7 integration fields |

**ALL 4 categories support variations!**

---

## Excel File Structure

Your CSV must have these columns:
```
Style Code, Code, Barcode, Cost NZD Excl
```

### Matching Strategy
1. **Priority 1**: Try "Code" → Variation field (HIGHEST specificity)
2. **Priority 2**: Try "Code" → Product SKU
3. **Priority 3**: Try "Barcode" → Product barcode

---

## Updated Fields

When variation matches:
```python
variation.cost_price = Excel "Cost NZD Excl"
variation.margin_75_price = cost_price / 0.25
variation.last_price_update = now()
```

When product matches (no variation):
```python
product.cost_price = Excel "Cost NZD Excl"
product.margin_75_price = cost_price / 0.25
product.last_price_update = now()
```

---

## What Was Fixed

### Before (INCORRECT):
```
Wholesale: NO variations ❌
Priority: Product.cin7_sku only
```

### After (CORRECT):
```
Wholesale: HAS variations ✅
Priority: WholesaleProductVariation.cin7_sku → Product.cin7_sku
```

---

## Code Changes Made

### 1. `schools/services/product_matcher.py`
- ✅ Added wholesale variation matching (lines 571-593)
- ✅ Added wholesale variation with instance (lines 718-735)

### 2. `schools/services/bulk_price_updater.py`
- ✅ Added `_preload_wholesale_variations()` method (lines 179-190)
- ✅ Added wholesale preload call (line 125-126)

---

## Summary

**ALL 4 categories now correctly support variations:**
1. LOTTO → LottoProductVariation.sku_suffix
2. SAS → SASProductVariation.sku_suffix
3. TUS → TUSProductVariation.sku
4. WHOLESALE → WholesaleProductVariation.cin7_sku ✅ FIXED

**Your 86,671 row file will now correctly match wholesale variations!**

---

**Status**: ✅ FIXED
**Date**: 2025-10-10
**Files Modified**: 2 (product_matcher.py, bulk_price_updater.py)
