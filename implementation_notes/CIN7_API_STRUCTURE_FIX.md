# Cin7 API Structure Fix

## Problem

The initial implementation was based on incorrect assumptions about the Cin7 API structure. The actual API returns products with a nested `productOptions` array, where each option represents a variant (size/color) with its own SKU, barcode, and prices.

### Original Assumptions (Incorrect)
```json
{
  "Id": 12345,
  "Code": "SKU123",
  "Name": "Product Name",
  "Barcode": "123456789",
  "AvgCost": 10.50,
  "SellPrice1": 42.00
}
```

### Actual Cin7 API Structure
```json
{
  "id": 26107,                    // Lowercase 'id', parent product
  "styleCode": "USL HO GLDN LDY BLK",
  "name": "Intimissima Cotton Tights",
  "brand": "",
  "category": "Generic",
  "productOptions": [              // Array of variants
    {
      "id": 142838,                // Variant ID (unique)
      "code": "USL HO GLDN LDY BLK -2-4",  // Variant SKU
      "barcode": "93038",          // Variant barcode
      "option1": "2--4",           // Size
      "status": "Active",
      "retailPrice": 24.00,
      "priceColumns": {
        "costNZD": 11.66,          // Cost price
        "retailNZD": 24.00         // Retail price
      },
      "stockAvailable": 0.0
    },
    {
      "id": 142839,
      "code": "USL HO GLDN LDY BLK -4-6",
      "barcode": "93039",
      "option1": "4--6",
      // ... more variants
    }
  ]
}
```

## Key Differences

1. **Field Names**: Lowercase (`id`, `styleCode`, `name`) instead of PascalCase (`Id`, `StyleCode`, `Name`)
2. **Product Variants**: Products have `productOptions[]` array with multiple variants
3. **Price Location**: Prices are in `productOptions[].priceColumns.{costNZD, retailNZD}`
4. **Multiple Records**: Each variant becomes a separate database record (1 product → 5 variants = 5 Cin7Product records)
5. **SKU/Barcode**: Each variant has its own unique SKU and barcode

## Solution

### 1. Created New Method: `extract_product_options()`

**File**: `schools/services/cin7_api_service.py`

Replaced the old `extract_price_data()` method with `extract_product_options()` that:
- Iterates through `productOptions[]` array
- Extracts each variant's SKU, barcode, and prices
- Calculates 75% margin price and discount percentage for each variant
- Returns a list of extracted options (one per variant)
- Skips inactive options (status != "Active")

**Key Code**:
```python
def extract_product_options(self, product: Dict) -> list:
    """Extract all product options (variants) from a Cin7 product."""
    extracted_options = []
    product_options = product.get('productOptions', [])

    for option in product_options:
        if option.get('status') != 'Active':
            continue

        price_columns = option.get('priceColumns', {})
        cost_price = price_columns.get('costNZD')
        rrp = price_columns.get('retailNZD') or option.get('retailPrice')

        # Calculate margins...

        extracted_options.append({
            'cin7_id': option.get('id'),  # Variant ID
            'sku': option.get('code'),
            'barcode': option.get('barcode'),
            'style_code': product.get('styleCode'),
            'product_name': f"{product.get('name')} - {option.get('option1')}",
            # ... more fields
        })

    return extracted_options
```

### 2. Updated View: `cin7_price_fetch()`

**File**: `schools/views.py` (lines 3519-3558)

Changed from:
- Processing 1 product → 1 database record
- Using `extract_price_data()` method

To:
- Processing 1 product → N database records (one per variant)
- Using `extract_product_options()` method
- Looping through returned options array

**Key Changes**:
```python
# OLD (incorrect):
price_data = cin7_service.extract_price_data(cin7_product)
cin7_products.append(Cin7Product(...))

# NEW (correct):
product_options = cin7_service.extract_product_options(cin7_product)
for option_data in product_options:
    cin7_products.append(Cin7Product(...))
```

### 3. Enhanced Statistics Tracking

Added new counters:
- `skipped_no_options`: Products with no productOptions array
- `total_options`: Total number of variants processed
- `skipped_no_id`: Variants without an ID

**Response Structure**:
```json
{
  "success": true,
  "session_id": "uuid",
  "summary": {
    "total_fetched": 15995,        // Parent products fetched
    "total_variants": 79975,       // Total variants (15995 × 5 avg)
    "saved_to_db": 79975,          // Records saved
    "skipped_no_options": 0,       // Products with no variants
    "skipped_no_id": 0,            // Variants without ID
    "duration_seconds": 299.22
  }
}
```

## Impact

### Database Records
- **Before**: 1 product = 1 Cin7Product record
- **After**: 1 product with 5 sizes = 5 Cin7Product records

### Example
Product: "Intimissima Cotton Tights"
- Parent Product ID: 26107
- Variants:
  1. SKU: `USL HO GLDN LDY BLK -2-4`, Barcode: `93038`, Size: 2-4 → Cin7Product record
  2. SKU: `USL HO GLDN LDY BLK -4-6`, Barcode: `93039`, Size: 4-6 → Cin7Product record
  3. SKU: `USL HO GLDN LDY BLK -6-8`, Barcode: `93040`, Size: 6-8 → Cin7Product record
  4. SKU: `USL HO GLDN LDY BLK -8-10`, Barcode: `93041`, Size: 8-10 → Cin7Product record
  5. SKU: `USL HO GLDN LDY BLK -10-13`, Barcode: `93042`, Size: 10-13 → Cin7Product record

**Result**: 5 separate records with unique cin7_id, SKU, barcode, and prices

### Matching Benefits
Each variant can now match independently:
- Size 2-4 might match a TUSProductVariation with SKU `USL HO GLDN LDY BLK -2-4`
- Size 4-6 might match a different variation
- Each size has its own cost/retail prices

## Testing

### Expected Results
```
Stage 1 (Fetch):
- Total parent products: 15,995
- Total product variants: ~79,975 (assuming 5 variants per product)
- Saved to database: ~79,975
- Skipped (no options): 0
- Skipped (no ID): 0
- Duration: ~5 minutes

Stage 2 (Match):
- Total processed: 79,975
- Matched: ~40,000 (estimated)
- Not found: ~38,000
- Skipped (no cost): ~1,975
- Duration: ~2-3 minutes

Stage 3 (Apply):
- Successful updates: ~40,000
- Failed updates: 0
- Duration: ~3-4 minutes
```

## Files Changed

1. **schools/services/cin7_api_service.py**
   - Replaced `extract_price_data()` with `extract_product_options()`
   - Handles productOptions array
   - Extracts variant-level data (SKU, barcode, prices)

2. **schools/views.py** (cin7_price_fetch view)
   - Loop through product options array
   - Create multiple Cin7Product records per parent product
   - Enhanced statistics tracking

## Verification

✅ Django check passed (no errors)
✅ Field mappings correct (id → cin7_id, styleCode → style_code)
✅ Price extraction from priceColumns.{costNZD, retailNZD}
✅ Variant naming: "Product Name - Size"
✅ Status filtering: Only "Active" variants processed
