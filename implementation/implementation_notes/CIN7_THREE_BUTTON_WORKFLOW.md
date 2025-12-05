# Cin7 Three-Button Workflow Implementation

## Overview

Implemented a clear 3-stage workflow with separate buttons for each stage, automatic data cleanup, and BS product filtering.

## Changes Implemented

### 1. ✅ Auto-Clear Old Data

**File**: `schools/views.py` (lines 3499-3504)

Before fetching new data, automatically clears all old Cin7Product records to ensure fresh data:

```python
# Clear old Cin7Product records to ensure fresh data
old_count = Cin7Product.objects.count()
if old_count > 0:
    logger.info(f"Clearing {old_count} old Cin7Product records...")
    Cin7Product.objects.all().delete()
    logger.info(f"✓ Cleared {old_count} old records")
```

**Benefit**: No duplicate records, always fresh data from Cin7

### 2. ✅ Skip BS Products

**File**: `schools/views.py` (lines 3562-3567)

Automatically skips products where SKU or Style Code starts with 'BS':

```python
# Skip products where code or style_code starts with 'BS'
sku = option_data.get('sku') or ''
style_code = option_data.get('style_code') or ''
if sku.upper().startswith('BS') or style_code.upper().startswith('BS'):
    skipped_bs_products += 1
    continue
```

**Tracking**: Added `skipped_bs_products` counter and reporting

### 3. ✅ Three-Button Workflow

**New UI Flow**:

```
Step 1: Click "Fetch Prices from Cin7"
    ↓
  [Progress Card] - Shows real-time fetch progress
    ↓
  [Fetch Results Card] - Shows summary with "Match Products" button
    ↓
Step 2: Click "Match Products with Database"
    ↓
  [Progress Card] - Shows real-time matching progress
    ↓
  [Preview Card] - Shows matched products with "Apply Updates" button
    ↓
Step 3: Click "Apply Updates"
    ↓
  [Progress Card] - Shows real-time update progress
    ↓
  [Results Card] - Shows final results
```

### 4. ✅ New Fetch Results Card

**File**: `schools/templates/schools/wholesale/cin7_price_update_settings.html` (lines 156-199)

Added intermediate card between fetch and match:

```html
<div class="row" id="fetchResultsCard" style="display: none;">
    <div class="card">
        <div class="alert alert-success">
            Fetch Complete! X product variants fetched and saved
        </div>

        <!-- Statistics -->
        <div class="row">
            - Product Variants Saved
            - Skipped (BS Products)
            - Duration
        </div>

        <!-- Buttons -->
        <button id="matchProductsBtn">Match Products with Database</button>
        <button id="cancelFetchBtn">Cancel</button>
    </div>
</div>
```

### 5. ✅ Updated JavaScript Flow

**File**: `schools/templates/schools/wholesale/cin7_price_update_settings.html`

**Fetch Handler** (lines 354-386):
- Removed automatic call to `matchProducts()`
- Now shows `fetchResultsCard` with statistics
- Shows success message

**Match Button Handler** (lines 510-522):
```javascript
$('#matchProductsBtn').click(function() {
    const priceType = $('#priceType').val();

    // Show progress
    $('#fetchResultsCard').hide();
    $('#progressCard').show();
    $('#progressTitle').text('Matching Products...');

    // Call Stage 2
    matchProducts(priceType, sessionId);
});
```

**Cancel Fetch Button** (lines 524-529):
```javascript
$('#cancelFetchBtn').click(function() {
    $('#fetchResultsCard').hide();
    $('#settingsCard').show();
    sessionId = null;
});
```

## Workflow Comparison

### Before (Automatic):
```
User clicks "Fetch"
  → Fetch (Stage 1)
  → Match (Stage 2 - automatic)
  → Show preview
  → User clicks "Apply"
  → Apply (Stage 3)
```

**Problems**:
- No control over matching
- Can't review fetch results before matching
- Can't re-match without re-fetching

### After (Manual 3-Button):
```
User clicks "Fetch Prices from Cin7"
  → Fetch (Stage 1)
  → Shows fetch results card with statistics
  → User reviews results

User clicks "Match Products with Database"
  → Match (Stage 2)
  → Shows preview table with match statistics
  → User reviews matches

User clicks "Apply Updates"
  → Apply (Stage 3)
  → Shows final results
```

**Benefits**:
- Full control over each stage
- Can review data between stages
- Can re-match without re-fetching
- Clear separation of concerns
- Better error handling per stage

## Data Flow

### Stage 1: Fetch
1. Clear all old Cin7Product records
2. Fetch products from Cin7 API (with pagination)
3. Filter out products starting with 'BS'
4. Save to Cin7Product table
5. Show summary statistics

**Response**:
```json
{
  "success": true,
  "session_id": "uuid",
  "summary": {
    "total_fetched": 15995,
    "total_variants": 80845,
    "saved_to_db": 75234,
    "skipped_no_options": 3336,
    "skipped_bs_products": 5611,
    "skipped_no_id": 0,
    "duration_seconds": 517.47
  }
}
```

### Stage 2: Match
1. Load Cin7Product records by session_id
2. Match against local database (SKU → Barcode → Style_code)
3. Update Cin7Product with match information
4. Show preview table

**Unchanged from before** - Still uses `find_product_with_variation()`

### Stage 3: Apply
1. Load matched Cin7Product records
2. Apply price updates via BulkPriceUpdater
3. Mark as processed
4. Show results

**Unchanged from before**

## Statistics Tracking

### New Metrics

**Stage 1 Response**:
- `skipped_bs_products`: Count of products filtered by BS rule

**Logging**:
```
=== CIN7 PRICE FETCH COMPLETE (Stage 1) ===
Total parent products: 15995
Total product variants: 80845
Saved to database: 75234
Skipped (no options): 3336
Skipped (starts with BS): 5611  ← NEW
Skipped (no ID): 0
Duration: 517.47s
```

## UI Screenshots

### 1. Settings Card (Initial)
- Price type dropdown
- "Fetch Prices from Cin7" button

### 2. Progress Card (During Fetch)
- Real-time progress bar
- Status messages

### 3. Fetch Results Card (After Fetch) ← NEW
- Success alert
- 3 statistics boxes:
  - Product Variants Saved
  - Skipped (BS Products)
  - Duration
- "Match Products with Database" button
- "Cancel" button

### 4. Progress Card (During Match)
- Real-time matching progress

### 5. Preview Card (After Match)
- Match statistics
- Preview table (first 1000)
- "Apply Updates" button
- "Cancel" button

### 6. Progress Card (During Apply)
- Real-time update progress

### 7. Results Card (After Apply)
- Final statistics
- "Start New Update" button

## Testing Checklist

- [ ] Stage 1: Fetch clears old data
- [ ] Stage 1: BS products are skipped
- [ ] Stage 1: Shows fetch results card
- [ ] Stage 1: Statistics are correct
- [ ] Stage 2: Match button triggers matching
- [ ] Stage 2: Shows progress during match
- [ ] Stage 2: Shows preview with matches
- [ ] Stage 3: Apply button triggers updates
- [ ] Cancel buttons work at each stage
- [ ] Session ID persists across stages

## Files Changed

1. **schools/views.py** (`cin7_price_fetch`):
   - Added auto-clear old records
   - Added BS product filtering
   - Updated statistics tracking
   - Updated response JSON

2. **schools/templates/schools/wholesale/cin7_price_update_settings.html**:
   - Added `fetchResultsCard` HTML
   - Updated fetch success handler
   - Added `matchProductsBtn` click handler
   - Added `cancelFetchBtn` click handler

## Migration Notes

### Database
No migration needed - uses existing Cin7Product model

### Backwards Compatibility
Fully backwards compatible - all existing APIs work the same

### User Impact
Users now have more control:
- Can review fetch results before matching
- Can cancel after fetch without wasting matches
- Better visibility into BS product filtering

## Performance Impact

### Before
- Fetch → Match (automatic): ~8-10 minutes total

### After
- Fetch: ~8 minutes
- (User reviews)
- Match: ~2 minutes
- (User reviews)
- Apply: ~3 minutes

**Total**: Same time, but with review steps

### Benefits
- Can stop after fetch if results look wrong
- Can retry match without re-fetching
- Better error isolation per stage
