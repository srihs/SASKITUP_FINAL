# Cin7 Price Update - Two-Stage Architecture

## 🎯 Overview

**New Architecture**: Separate data fetching from processing using database storage.

### Why Two-Stage?

**Benefits**:
1. ✅ **Data persistence** - Cin7 data saved before processing
2. ✅ **Resumable** - Can retry matching/updates without re-fetching
3. ✅ **Auditable** - Complete history of Cin7 data
4. ✅ **Flexible matching** - Can adjust matching logic and re-run
5. ✅ **Batch control** - Process in smaller batches
6. ✅ **Data analysis** - Query Cin7 data independently

---

## 📊 Architecture Comparison

### OLD: Single-Stage (In-Memory)
```
Cin7 API → Extract → Match → Update → Done
           [Lost if error occurs]
```

### NEW: Two-Stage (Database-Backed)
```
Stage 1: Fetch
Cin7 API → Extract → Save to Cin7Product table → Done
                     [Persisted in database]

Stage 2: Match & Update
Cin7Product table → Match → Update → Mark processed
                    [Can retry if needed]
```

---

## 🗄️ Database Schema

### Cin7Product Model

**Table**: `cin7_products`

**Purpose**: Temporary staging table for Cin7 API data

#### Fields

| Field | Type | Purpose |
|-------|------|---------|
| **Identifiers** |||
| `cin7_id` | Integer | Cin7 product ID |
| `code` | String(100) | Product SKU/Code |
| `style_code` | String(100) | Product style code |
| `barcode` | String(100) | Product barcode |
| **Product Info** |||
| `name` | String(500) | Product name |
| `category` | String(200) | Cin7 category |
| `brand` | String(200) | Product brand |
| **Pricing** |||
| `cost_nzd` | Decimal(10,2) | Cost price |
| `retail_price` | Decimal(10,2) | Retail price (RRP) |
| `margin_75_price` | Decimal(10,2) | Auto-calculated |
| `discount_percentage` | Decimal(5,2) | Auto-calculated |
| **Stock** |||
| `stock_available` | Integer | Available quantity |
| **Matching** |||
| `matched` | Boolean | Matched to local product? |
| `matched_product_id` | Integer | Local product ID |
| `matched_variation_id` | Integer | Local variation ID |
| `match_method` | String(100) | How matched |
| `price_type` | String(50) | TUS/LOTTO/SAS/Wholesale |
| **Processing** |||
| `processed` | Boolean | Prices applied? |
| `processed_at` | DateTime | When applied |
| **Metadata** |||
| `fetch_session_id` | String(100) | Fetch batch ID |
| `created_at` | DateTime | When fetched |
| `updated_at` | DateTime | Last updated |
| `raw_data` | JSON | Raw Cin7 response |

#### Indexes

```python
# Performance indexes
- (fetch_session_id, matched)
- (price_type, processed)
- (created_at, fetch_session_id)
- cin7_id (db_index=True)
- code (db_index=True)
- style_code (db_index=True)
- barcode (db_index=True)
```

#### Auto-Calculations

```python
def save(self):
    # Auto-calculate on save
    if cost_nzd > 0:
        margin_75_price = cost_nzd / 0.25

    if margin_75_price and retail_price:
        discount_percentage = ((margin_75_price - retail_price) / margin_75_price) × 100
```

---

## 🔄 Three-Stage Workflow

### Stage 1: Fetch from Cin7

**Endpoint**: `POST /cin7-price-fetch/`

**Process**:
1. Fetch products from Cin7 API (with rate limiting)
2. Extract relevant fields
3. **Save to Cin7Product table** (bulk_create)
4. Return fetch statistics

**Response**:
```json
{
  "success": true,
  "session_id": "uuid-here",
  "summary": {
    "total_fetched": 15995,
    "saved_to_db": 15995,
    "duration_seconds": 300.47
  }
}
```

**Benefits**:
- ✅ Data persisted even if next stage fails
- ✅ Can review data before matching
- ✅ Can re-fetch specific products later

---

### Stage 2: Match Products

**Endpoint**: `POST /cin7-match-products/`

**Process**:
1. Load Cin7Product records (by session_id)
2. Try matching: SKU → Barcode → Style_code
3. Update `matched`, `matched_product_id`, `match_method`
4. Return match statistics

**Response**:
```json
{
  "success": true,
  "session_id": "uuid-here",
  "summary": {
    "total_products": 15995,
    "matched": 8500,
    "not_matched": 7495,
    "match_rate": "53.2%",
    "duration_seconds": 45.2
  },
  "match_breakdown": {
    "via_sku": 6000,
    "via_barcode": 1500,
    "via_style_code": 1000
  }
}
```

**Benefits**:
- ✅ Can retry with different matching logic
- ✅ Can manually review unmatched products
- ✅ Can adjust and re-run matching

---

### Stage 3: Apply Price Updates

**Endpoint**: `POST /cin7-price-apply/`

**Process**:
1. Load matched Cin7Product records
2. Apply price updates using BulkPriceUpdater
3. Mark as `processed=True`, `processed_at=now()`
4. Return update statistics

**Response**:
```json
{
  "success": true,
  "session_id": "uuid-here",
  "results": {
    "successful_updates": 8500,
    "failed_updates": 0,
    "skipped_no_cost": 500,
    "performance": {
      "total_time_seconds": 120.5,
      "items_per_second": 70
    }
  }
}
```

**Benefits**:
- ✅ Only update matched products with cost prices
- ✅ Can review before applying
- ✅ Can apply in smaller batches
- ✅ Full audit trail

---

## 💡 Advanced Features

### 1. Batch Processing

Process large datasets in smaller batches:

```python
# Fetch all at once (15,995 products)
POST /cin7-price-fetch/
→ session_id: "batch-001"

# Match in stages
POST /cin7-match-products/
{
  "session_id": "batch-001",
  "limit": 5000,  # Match first 5000
  "offset": 0
}

# Apply in batches
POST /cin7-price-apply/
{
  "session_id": "batch-001",
  "batch_size": 1000,  # Update 1000 at a time
  "auto_batch": true
}
```

### 2. Manual Review & Adjustment

```python
from schools.models import Cin7Product

# Review unmatched products
unmatched = Cin7Product.objects.filter(
    fetch_session_id='batch-001',
    matched=False
)

for product in unmatched:
    print(f"{product.code} | {product.barcode} | {product.style_code}")

# Manually match specific products
product = Cin7Product.objects.get(cin7_id=12345)
product.matched = True
product.matched_product_id = 999
product.match_method = 'manual_override'
product.save()
```

### 3. Selective Updates

```python
# Only update products with cost prices
Cin7Product.objects.filter(
    fetch_session_id='batch-001',
    matched=True,
    cost_nzd__gt=0,
    processed=False
).update(...)

# Only update specific price type
Cin7Product.objects.filter(
    price_type='LOTTO',
    matched=True,
    processed=False
).update(...)
```

### 4. Data Analysis

```python
# Analyze match rates by field
from django.db.models import Count, Q

Cin7Product.objects.filter(
    fetch_session_id='batch-001'
).aggregate(
    total=Count('id'),
    matched_sku=Count('id', filter=Q(match_method__contains='sku')),
    matched_barcode=Count('id', filter=Q(match_method__contains='barcode')),
    matched_style=Count('id', filter=Q(match_method__contains='style'))
)

# Find products missing cost prices
no_cost = Cin7Product.objects.filter(
    fetch_session_id='batch-001',
    cost_nzd__isnull=True
).values('code', 'name')
```

### 5. Cleanup Old Data

```python
from datetime import timedelta
from django.utils import timezone

# Delete processed data older than 30 days
old_date = timezone.now() - timedelta(days=30)
Cin7Product.objects.filter(
    processed=True,
    processed_at__lt=old_date
).delete()

# Or keep for audit trail
Cin7Product.objects.filter(
    created_at__lt=old_date
).update(archived=True)
```

---

## 🎨 Updated UI Flow

### Old Flow (Single Stage)
```
[Select Price Type] → [Fetch & Match & Update] → [Results]
```

### New Flow (Three Stages)
```
[Select Price Type]
    ↓
[Stage 1: Fetch from Cin7]
    → Progress bar
    → Statistics (15,995 fetched, saved to DB)
    ↓
[Stage 2: Match Products]
    → Review match statistics
    → See matched/unmatched breakdown
    → Option to adjust and re-match
    ↓
[Stage 3: Preview & Apply]
    → Preview matched products
    → Review price changes
    → Apply updates
    ↓
[Results & Cleanup]
```

### UI Screens

#### Screen 1: Fetch
```
┌─────────────────────────────────────┐
│ Cin7 Price Update                   │
├─────────────────────────────────────┤
│ Price Type: [Wholesale ▼]           │
│                                     │
│ [Fetch Prices from Cin7]            │
│                                     │
│ Status: Fetching... 10,000/15,995   │
│ Progress: [████████░░] 62%          │
└─────────────────────────────────────┘
```

#### Screen 2: Match
```
┌─────────────────────────────────────┐
│ Match Products                      │
├─────────────────────────────────────┤
│ ✓ Fetched: 15,995 products          │
│                                     │
│ [Run Matching]                      │
│                                     │
│ Results:                            │
│  • Matched: 8,500 (53.2%)           │
│  • Not Matched: 7,495               │
│                                     │
│ Match Breakdown:                    │
│  • Via SKU: 6,000                   │
│  • Via Barcode: 1,500               │
│  • Via Style Code: 1,000            │
│                                     │
│ [Re-run Matching] [View Unmatched]  │
│ [Continue to Update →]              │
└─────────────────────────────────────┘
```

#### Screen 3: Apply
```
┌─────────────────────────────────────┐
│ Apply Price Updates                 │
├─────────────────────────────────────┤
│ Ready to Update: 8,500 products     │
│  • With Cost: 8,000                 │
│  • No Cost: 500 (will skip)         │
│                                     │
│ [Preview 100 Items]                 │
│                                     │
│ Product | Old $ | New $ | Margin   │
│ --------|-------|-------|----------│
│ ABC-123 | $10   | $12   | $48      │
│ ...                                 │
│                                     │
│ [Apply Updates]                     │
└─────────────────────────────────────┘
```

---

## 🧪 Testing Workflow

### Test 1: Full Workflow
```bash
# 1. Fetch
curl -X POST /cin7-price-fetch/ \
  -H "Content-Type: application/json" \
  -d '{"price_type": "LOTTO"}'

# Response: {"session_id": "abc-123", ...}

# 2. Match
curl -X POST /cin7-match-products/ \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc-123"}'

# 3. Apply
curl -X POST /cin7-price-apply/ \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc-123"}'
```

### Test 2: Review Unmatched
```python
from schools.models import Cin7Product

# Find unmatched
unmatched = Cin7Product.objects.filter(
    fetch_session_id='abc-123',
    matched=False
).values('code', 'barcode', 'style_code', 'name')[:50]

for p in unmatched:
    print(p)
```

### Test 3: Incremental Updates
```python
# Update in batches
session_id = 'abc-123'
batch_size = 1000

matched_products = Cin7Product.objects.filter(
    fetch_session_id=session_id,
    matched=True,
    processed=False
)

total = matched_products.count()
for offset in range(0, total, batch_size):
    batch = matched_products[offset:offset+batch_size]
    # Process batch
    print(f"Processing {offset}-{offset+batch_size} of {total}")
```

---

## 📈 Performance Impact

### Fetch Stage
- **Before**: In-memory only
- **After**: + Database inserts
- **Impact**: +2-3 seconds for 15K records (bulk_create is fast)

### Match Stage
- **Before**: Immediate during fetch
- **After**: Separate operation
- **Impact**: Can be run multiple times without re-fetching

### Apply Stage
- **Before**: Immediate after match
- **After**: Separate operation
- **Impact**: Better error recovery, can retry

### Total Workflow
- **Before**: 300s (5 min) - all or nothing
- **After**: 300s fetch + 45s match + 120s apply = 465s (7.75 min)
- **Trade-off**: Slightly slower but MUCH more flexible

---

## 🎯 Migration Path

### Phase 1: Add Model (✅ DONE)
- Created Cin7Product model
- Ran migrations
- Table created in database

### Phase 2: Update Fetch Endpoint
- Modify `cin7_price_fetch` to save to database
- Return session_id for tracking

### Phase 3: Create Match Endpoint
- New `cin7_match_products` endpoint
- Implement matching logic
- Update Cin7Product records

### Phase 4: Update Apply Endpoint
- Modify `cin7_price_apply` to read from Cin7Product
- Use BulkPriceUpdater with database data

### Phase 5: Update UI
- Add three-stage workflow
- Show statistics at each stage
- Add review/retry options

---

## ✅ Benefits Summary

1. **Resilience** - Can retry any stage without re-fetching
2. **Auditability** - Complete history of Cin7 data
3. **Flexibility** - Can adjust matching logic
4. **Control** - Process in batches, review before applying
5. **Analysis** - Query Cin7 data for insights
6. **Debugging** - Raw data preserved for troubleshooting

---

**Next Steps**: Update views to implement three-stage workflow
