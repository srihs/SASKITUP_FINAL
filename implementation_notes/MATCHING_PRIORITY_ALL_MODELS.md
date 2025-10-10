# Matching Priority for All 4 Models

## Excel File Columns
- **Style Code**: Base product identifier
- **Code**: Full product/variation code (may include size/color)
- **Barcode**: Product barcode

---

## 1. LOTTO (lotto-clubs)

### Models
- **LottoProduct**: `sku`, `barcode`
- **LottoProductVariation**: `sku_suffix`, `barcode`

### Matching Priority (HIGHEST → LOWEST)

| Priority | Excel Column | Database Field | Match Type | Notes |
|----------|--------------|----------------|------------|-------|
| **1** | Code | LottoProductVariation.sku_suffix | Exact | ✅ HIGHEST - Variation match |
| **2** | Code | LottoProductVariation.sku_suffix | Case-insensitive | Fallback for case mismatch |
| **3** | Code | LottoProductVariation.sku_suffix | Normalized (no spaces) | Handles "R9039 -4--7" vs "R9039-4--7" |
| **4** | Code | LottoProduct.sku | Exact | Product-level match |
| **5** | Code | LottoProduct.sku | Case-insensitive | Product fallback |
| **6** | Style Code | LottoProduct.sku | Exact | Alternative product match |
| **7** | Barcode | LottoProduct.barcode | Exact | Barcode fallback |
| **8** | Barcode | LottoProduct.barcode | Case-insensitive | Barcode case fallback |

**Example Match**:
```
Excel Row: Code = "R9039 -4--7"
Matches: LottoProductVariation with sku_suffix = "R9039 -4--7"
Method: sku_suffix_exact
```

---

## 2. SAS (sas-clubs)

### Models
- **SASProduct**: `sku`, `barcode`, `style_code`
- **SASProductVariation**: `sku_suffix`, `barcode`

### Matching Priority (HIGHEST → LOWEST)

| Priority | Excel Column | Database Field | Match Type | Notes |
|----------|--------------|----------------|------------|-------|
| **1** | Barcode | SASProductVariation.sku_suffix | Exact | ⚠️ Special: Barcode → Variation |
| **2** | Barcode | SASProductVariation.sku_suffix | Case-insensitive | Special variation match |
| **3** | Code | SASProductVariation.sku_suffix | Exact | ✅ PRIMARY - Variation match |
| **4** | Code | SASProductVariation.sku_suffix | Case-insensitive | Variation fallback |
| **5** | Code | SASProductVariation.sku_suffix | Normalized (no spaces) | Handles space differences |
| **6** | Code | SASProduct.sku | Exact | Product-level match |
| **7** | Code | SASProduct.sku | Case-insensitive | Product fallback |
| **8** | Barcode | SASProduct.barcode | Exact | Barcode product match |
| **9** | Barcode | SASProduct.barcode | Case-insensitive | Barcode fallback |
| **10** | Code | SASProduct.style_code | Exact | Style code match |
| **11** | Code | SASProduct.style_code | Case-insensitive | Style code fallback |
| **12** | Style Code | SASProduct.style_code | Exact | Alternative style match |

**Example Match**:
```
Excel Row: Code = "SAS-1234-XL-BLK"
Matches: SASProductVariation with sku_suffix = "SAS-1234-XL-BLK"
Method: sku_suffix_exact
```

---

## 3. TUS / Retail Schools (retail-schools)

### Models
- **TUSProduct**: `sku`, `barcode`
- **TUSProductVariation**: `sku`, `barcode`

### Matching Priority (HIGHEST → LOWEST)

| Priority | Excel Column | Database Field | Match Type | Notes |
|----------|--------------|----------------|------------|-------|
| **1** | Barcode | TUSProductVariation.sku | Exact | ⚠️ Special: Barcode → Variation SKU |
| **2** | Barcode | TUSProductVariation.sku | Case-insensitive | Variation barcode fallback |
| **3** | Code | TUSProductVariation.sku | Exact | ✅ PRIMARY - Variation match |
| **4** | Code | TUSProductVariation.sku | Case-insensitive | Variation fallback |
| **5** | Code | TUSProductVariation.sku | Normalized (no spaces) | Handles space differences |
| **6** | Barcode | TUSProduct.barcode | Exact | Product barcode match |
| **7** | Barcode | TUSProduct.barcode | Case-insensitive | Product barcode fallback |
| **8** | Code | TUSProduct.sku | Exact | Product SKU match |
| **9** | Code | TUSProduct.sku | Case-insensitive | Product SKU fallback |
| **10** | Style Code | TUSProduct.sku | Exact | Alternative product match |

**Example Match**:
```
Excel Row: Code = "TUS-SHIRT-M-RED"
Matches: TUSProductVariation with sku = "TUS-SHIRT-M-RED"
Method: sku_exact
```

**Note**: TUS variations use `sku` field (not `sku_suffix`)

---

## 4. Wholesale Schools (wholesale-schools)

### Models
- **WholesaleProduct**: `cin7_sku`, `cin7_barcode` (NO VARIATIONS)

### Matching Priority (HIGHEST → LOWEST)

| Priority | Excel Column | Database Field | Match Type | Notes |
|----------|--------------|----------------|------------|-------|
| **1** | Code | WholesaleProduct.cin7_sku | Exact | ✅ PRIMARY - SKU match |
| **2** | Code | WholesaleProduct.cin7_sku | Case-insensitive | SKU fallback |
| **3** | Style Code | WholesaleProduct.cin7_sku | Exact | Alternative SKU match |
| **4** | Style Code | WholesaleProduct.cin7_sku | Case-insensitive | Alternative fallback |
| **5** | Barcode | WholesaleProduct.cin7_barcode | Exact | Barcode match |
| **6** | Barcode | WholesaleProduct.cin7_barcode | Case-insensitive | Barcode fallback |

**Example Match**:
```
Excel Row: Code = "WS-12345"
Matches: WholesaleProduct with cin7_sku = "WS-12345"
Method: sku_exact
```

**Note**: Wholesale has NO variations - all matches at product level

---

## Comparison Table

| Category | Primary Match Field | Variation Field | Special Cases |
|----------|-------------------|-----------------|---------------|
| **LOTTO** | ProductVariation.sku_suffix | ✅ Yes | Code → sku_suffix |
| **SAS** | ProductVariation.sku_suffix | ✅ Yes | Barcode can match sku_suffix |
| **TUS** | ProductVariation.sku | ✅ Yes | Uses `sku` not `sku_suffix` |
| **Wholesale** | ProductVariation.cin7_sku | ✅ Yes | Code → cin7_sku |

---

## Normalized Matching

All categories support **normalized matching** to handle spacing differences:

### Examples
```
Excel: "R9039 -4--7"     → Database: "R9039-4--7"     ✅ MATCHES
Excel: "SAS 1234 XL"     → Database: "SAS1234XL"      ✅ MATCHES
Excel: "TUS SHIRT M"     → Database: "TUS-SHIRT-M"    ✅ MATCHES
```

### Normalization Rules
1. Strip leading/trailing whitespace
2. Convert to uppercase
3. Remove all spaces for comparison
4. Original data unchanged in database

---

## Match Methods (Log Codes)

| Code | Meaning |
|------|---------|
| `sku_suffix_exact` | Exact match on variation sku_suffix |
| `sku_suffix_iexact` | Case-insensitive match on variation sku_suffix |
| `sku_suffix_normalized` | Normalized match (spaces removed) |
| `sku_exact` | Exact match on product sku |
| `sku_iexact` | Case-insensitive match on product sku |
| `barcode_exact` | Exact match on barcode |
| `barcode_iexact` | Case-insensitive match on barcode |
| `variation_sku_from_barcode_exact` | Barcode matched to variation SKU (TUS) |
| `variation_sku_suffix_from_barcode_exact` | Barcode matched to variation sku_suffix (SAS) |
| `style_code_exact` | Exact match on style_code (SAS only) |

---

## Which Field Gets Updated?

### When Variation Matches
```python
# Update the VARIATION record
variation.cost_price = excel_cost
variation.margin_75_price = excel_cost / 0.25
variation.price = <calculated or existing>
variation.last_price_update = now()
```

### When Product Matches (No Variation)
```python
# Update the PRODUCT record
product.cost_price = excel_cost
product.margin_75_price = excel_cost / 0.25
product.price = <calculated or existing>
product.last_price_update = now()
```

### Wholesale (Always Product)
```python
# Wholesale has no variations
product.cost_price = excel_cost
product.retail_price = <existing - not changed>
product.last_price_update = now()
```

---

## Quick Reference

### Your Excel File
```csv
Style Code,Code,Barcode,Cost NZD Excl
R9039,R9039 -4--7,,5.50
```

### What Happens
1. **Try LOTTO**: Code "R9039 -4--7" → LottoProductVariation.sku_suffix
2. **Match Found**: LottoProductVariation #1234
3. **Update**: variation.cost_price = 5.50, margin_75_price = 22.00
4. **Log**: `[MATCH] Row 1: Matched "R9039 -4--7" to Variation #1234 via sku_suffix_exact`

---

## Priority Summary

**All 4 Categories**:
1. ✅ **Variations FIRST** (if exist) - highest specificity
2. Product SKU/Code - fallback
3. Barcode - last resort

**Exception**: Wholesale has no variations, goes straight to product

**Special Cases**:
- SAS & TUS: Barcode can match variation SKU field
- TUS: Uses `variation.sku` (not `sku_suffix`)
- Wholesale: Uses `cin7_sku` and `cin7_barcode`

---

**This is the exact matching logic in your code at**: `schools/services/product_matcher.py:374-589`
