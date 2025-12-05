# Wholesale Price Update Implementation Analysis
**Date**: 2025-10-06
**Analyzed by**: Claude Code
**Purpose**: Complete analysis of current wholesale price update implementation

---

## Executive Summary

The wholesale price update system is **fully functional** with a sophisticated UI and backend already in place. The implementation includes:

- ✅ Category Filter (TUS, SAS, LOTTO, Wholesale) - **Already exists** (Line 30 in template)
- ✅ CSV Upload with drag-and-drop
- ✅ Preview generation with DataTable display
- ✅ Product matching by SKU and Barcode
- ✅ Apply mechanism with transaction safety
- ✅ Comprehensive logging and error handling

**Key Finding**: The category filter is **UI-only** currently - it doesn't affect backend matching logic. Backend uses hard-coded `WholesaleProduct` model.

---

## 1. File Structure and Locations

### Core Files

| File | Path | Lines | Purpose |
|------|------|-------|---------|
| **Views** | `/Users/sas/Repos/SASKITUP/schools/views.py` | 2427 | Backend logic for price updates |
| **URLs** | `/Users/sas/Repos/SASKITUP/schools/urls.py` | 76 | URL routing |
| **Template** | `/Users/sas/Repos/SASKITUP/schools/templates/schools/wholesale/price_update_settings.html` | 2321 | Complete UI with JavaScript |
| **Models** | `/Users/sas/Repos/SASKITUP/schools/models.py` | - | WholesaleProduct, WholesaleCategory, etc. |

### API Endpoints (Already Implemented)

| Endpoint | Method | View Function | Line |
|----------|--------|---------------|------|
| `/schools/wholesale/settings/price-update/` | GET | `wholesale_price_update_settings` | 2406 |
| `/schools/wholesale/api/price-preview/` | POST | `wholesale_price_preview` | 1933 |
| `/schools/wholesale/api/price-apply/` | POST | `wholesale_price_apply` | 2087 |

---

## 2. Current Implementation Flow

### 2.1 User Flow

```
1. User selects category filter (wholesale/tus/sas/lotto) [Line 30-37]
   ↓
2. User uploads CSV file via drag-drop or browse [Line 80-133]
   ↓
3. JavaScript validates file and stores in window.selectedValidFiles [Line 1172-1217]
   ↓
4. User clicks "Process Files" button [Line 1276-1308]
   ↓
5. JavaScript calls /schools/wholesale/api/price-preview/ [Line 1384]
   ↓
6. Backend processes CSV and returns preview data [Line 1933-2083]
   ↓
7. JavaScript displays preview in DataTable [Line 1636-1791]
   ↓
8. User selects items and clicks "Apply Changes" [Line 1985-2086]
   ↓
9. Backend applies selected price updates [Line 2087-2403]
   ↓
10. Results displayed to user [Line 2044-2076]
```

### 2.2 Technical Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (JavaScript)                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. File Selection & Validation                              │
│     └─> handleFiles() [Line 1172]                            │
│         └─> validateFile() [Line 1310]                       │
│             └─> showFilesReadyState() [Line 1219]            │
│                                                               │
│  2. Preview Processing                                        │
│     └─> processFilesForPreview() [Line 1344]                 │
│         └─> FormData + category_filter [Line 1371-1378]      │
│             └─> fetch('/api/price-preview/') [Line 1384]     │
│                                                               │
│  3. Preview Display                                           │
│     └─> populatePreviewDataFromAPI() [Line 1636]             │
│         └─> DataTable initialization [Line 1734-1758]        │
│                                                               │
│  4. Apply Changes                                             │
│     └─> applyPreviewChanges() [Line 1985]                    │
│         └─> fetch('/api/price-apply/') [Line 2026]           │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    BACKEND (Django Views)                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Preview Generation                                        │
│     └─> wholesale_price_preview() [Line 1933]                │
│         └─> CSV parsing with csv.DictReader [Line 1997-2010] │
│             └─> Product matching:                             │
│                 • By cin7_sku (exact) [Line 2026]             │
│                 • By cin7_barcode (fallback) [Line 2030]      │
│                 └─> Build preview_item [Line 2032-2047]       │
│                                                               │
│  2. Apply Updates                                             │
│     └─> wholesale_price_apply() [Line 2087]                  │
│         └─> JSON body parsing [Line 2102]                     │
│             └─> Transaction-wrapped updates [Line 2192-2368]  │
│                 • Find product by SKU/barcode [Line 2207-2256]│
│                 • Backup prices [Line 2277-2286]              │
│                 • Update fields [Line 2292-2318]              │
│                 • Save with update_fields [Line 2332-2341]    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Category Filter Analysis

### 3.1 Current UI Implementation (Line 30-37)

```html
<select class="form-select" id="category-filter">
    <option value="all">All Categories (Warning: May cause browser freeze with large files)</option>
    <option value="lotto-clubs">LOTTO Clubs</option>
    <option value="sas-clubs">SAS Clubs</option>
    <option value="retail-schools">Retail Schools</option>
    <option value="wholesale-schools" selected>Wholesale Schools</option>
</select>
```

**Purpose**:
- Shows estimated item counts per category
- Warns users about performance implications
- **Currently**: Only updates UI text, doesn't filter backend queries

### 3.2 Category Filter JavaScript (Line 1073-1085)

```javascript
// Category filter change
const categoryFilter = document.getElementById('category-filter');
if (categoryFilter) {
    categoryFilter.addEventListener('change', function(e) {
        const selectedCategory = e.target.value;
        console.log('[DEBUG] Category filter changed to:', selectedCategory);
        updateCategoryItemCount(selectedCategory);  // Only updates display text
        addLogEntry(`Category filter set to: ${selectedCategory}`, 'info');
    });
}
```

**Current Behavior**:
- Updates displayed item count estimate
- Logs the selection
- **Does NOT** send category to backend

### 3.3 Category Being Sent to Backend (Line 1371-1378)

```javascript
// Add category filter
const categoryFilter = document.getElementById('category-filter');
if (categoryFilter) {
    formData.append('category_filter', categoryFilter.value);
    console.log('[DEBUG] Added category filter:', categoryFilter.value);
}
```

**Status**: ✅ **Category IS being sent** but **backend ignores it**

---

## 4. Backend Product Matching Logic

### 4.1 Current Matching Strategy (wholesale_price_preview)

**Location**: `/Users/sas/Repos/SASKITUP/schools/views.py` Line 2024-2030

```python
# Try to find the product
product = None
if product_code:
    product = WholesaleProduct.objects.filter(cin7_sku=product_code).first()

if not product and barcode:
    product = WholesaleProduct.objects.filter(cin7_barcode=barcode).first()
```

**Current Behavior**:
- ❌ Hard-coded to `WholesaleProduct` model
- ✅ Searches by SKU first (exact match)
- ✅ Falls back to barcode if SKU not found
- ❌ No category filter logic
- ❌ No case-insensitive matching
- ❌ No support for TUS/SAS/LOTTO products

### 4.2 Apply Matching Strategy (wholesale_price_apply)

**Location**: Line 2207-2256

```python
# Find product by code or barcode
product = None
search_method = None

# Try to find by SKU first with multiple search strategies
if product_code:
    product_code_clean = str(product_code).strip()

    # Try exact match first
    product = WholesaleProduct.objects.filter(cin7_sku=product_code_clean).first()
    if product:
        search_method = "SKU (exact)"
        found_by_sku_count += 1
    else:
        # Try case-insensitive match
        product = WholesaleProduct.objects.filter(cin7_sku__iexact=product_code_clean).first()
        if product:
            search_method = "SKU (case-insensitive)"
            found_by_sku_count += 1

# Try barcode if not found by SKU
if not product and barcode:
    # Similar logic for barcode matching...
```

**Current Behavior**:
- ❌ Hard-coded to `WholesaleProduct` model
- ✅ Exact SKU match
- ✅ Case-insensitive SKU match
- ✅ Exact barcode match
- ✅ Case-insensitive barcode match
- ❌ No category filter logic

---

## 5. CSV Field Mapping

### 5.1 Preview Parsing (Line 2015-2019)

```python
# Extract data from row - handle multiple possible field names
product_code = str(row.get('product_code', '') or row.get('Code', '') or row.get('Style Code', '')).strip()
barcode = str(row.get('barcode', '') or row.get('Barcode', '')).strip()
product_name = str(row.get('product_name', '') or row.get('Product Name', '')).strip()
```

**Supported CSV Headers**:
- Product Code: `product_code`, `Code`, `Style Code`
- Barcode: `barcode`, `Barcode`
- Product Name: `product_name`, `Product Name`

### 5.2 Price Fields (Line 2040-2043)

```python
'cost': row.get('cost', '') or row.get('Cost NZD Excl', ''),
'margin_75_price': row.get('margin_75_price', '') or row.get('WholesaleExGST NZD Excl', ''),
'discount_percentage': row.get('discount_percentage', ''),
'current_retail_nzd_incl': row.get('current_retail_nzd_incl', '') or row.get('Retail NZD Incl', ''),
```

**Supported CSV Headers**:
- Cost: `cost`, `Cost NZD Excl`
- 75% Margin: `margin_75_price`, `WholesaleExGST NZD Excl`
- Discount: `discount_percentage`
- Retail Price: `current_retail_nzd_incl`, `Retail NZD Incl`

---

## 6. Database Models

### 6.1 WholesaleProduct Model (Current)

**Location**: `/Users/sas/Repos/SASKITUP/schools/models.py` Line 322

```python
class WholesaleProduct(models.Model):
    # Identifiers
    cin7_id = models.CharField(max_length=50, unique=True)
    cin7_sku = models.CharField(max_length=100, db_index=True)  # ✅ Used for matching
    cin7_barcode = models.CharField(max_length=100, blank=True)  # ✅ Used for matching

    # Pricing
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    wholesale_price = models.DecimalField(max_digits=10, decimal_places=2)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    margin_75_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    last_price_update = models.DateTimeField(null=True, blank=True)
```

### 6.2 TUS/SAS/LOTTO Models (Need Updates)

According to `/Users/sas/Repos/SASKITUP/PRICE_UPDATE_EXTENSION_PLAN.md`:

**Missing Fields**:
- ❌ `cost_price`
- ❌ `margin_75_price`
- ❌ `discount_percentage`
- ❌ `last_price_update`
- ❌ `barcode` (for matching)

**Existing Fields**:
- ✅ `sku`
- ✅ `price`
- ✅ `regular_price`
- ✅ `sale_price`
- ✅ `stock_status`

---

## 7. Preview Data Structure

### 7.1 Preview Item Format (Line 2032-2047)

```python
preview_item = {
    'row_number': row_num,
    'product_code': product_code,
    'barcode': barcode,
    'product_name': product_name,
    'product_found': product is not None,
    'database_product_name': product.name if product else None,
    'school_name': product.school.name if product else None,
    'cost': row.get('cost', ''),
    'margin_75_price': row.get('margin_75_price', ''),
    'discount_percentage': row.get('discount_percentage', ''),
    'current_retail_nzd_incl': row.get('current_retail_nzd_incl', ''),
    'current_cost_price': float(product.cost_price) if product and product.cost_price else None,
    'current_margin_75_price': float(product.margin_75_price) if product and product.margin_75_price else None,
    'current_retail_price': float(product.retail_price) if product and product.retail_price else None,
}
```

### 7.2 Frontend Preview Display (Line 1680-1724)

```javascript
// Format prices safely using new structure
const cost = item.cost !== null ? `$${item.cost.toFixed(2)}` : 'N/A';
const currentRetail = item.current_retail_nzd_incl !== null ? `$${item.current_retail_nzd_incl.toFixed(2)}` : 'N/A';
const marginPrice = item.margin_75_price !== null ? `$${item.margin_75_price.toFixed(2)}` : 'N/A';
const rrp = item.rrp !== null ? `$${item.rrp.toFixed(2)}` : 'N/A';
const discount = item.discount_percentage !== null ? `${item.discount_percentage.toFixed(1)}%` : 'N/A';
```

---

## 8. Apply Logic

### 8.1 Transaction Wrapper (Line 2192-2368)

```python
try:
    with transaction.atomic():
        for index, item in enumerate(selected_items, 1):
            # Product matching
            # Backup creation
            # Price updates
            # Save with update_fields
except Exception as transaction_error:
    logger.error(f"Database transaction failed: {transaction_error}", exc_info=True)
    raise transaction_error
```

**Safety Features**:
- ✅ Atomic transaction (all-or-nothing)
- ✅ Comprehensive logging
- ✅ Backup mechanism
- ✅ Error tracking
- ✅ Rollback on failure

### 8.2 Update Fields (Line 2288-2341)

```python
# Track what fields will be updated
updates_to_apply = {}

# Update product pricing fields using new structure
if item.get('cost'):
    new_cost = Decimal(str(item['cost']))
    updates_to_apply['cost_price'] = new_cost
    product.cost_price = new_cost

if item.get('margin_75_price'):
    new_margin = Decimal(str(item['margin_75_price']))
    updates_to_apply['margin_75_price'] = new_margin
    product.margin_75_price = new_margin

if item.get('discount_percentage'):
    new_discount = Decimal(str(item['discount_percentage']))
    if hasattr(product, 'discount_percentage'):
        updates_to_apply['discount_percentage'] = new_discount
        product.discount_percentage = new_discount

if item.get('current_retail_nzd_incl'):
    new_retail = Decimal(str(item['current_retail_nzd_incl']))
    updates_to_apply['retail_price'] = new_retail
    product.retail_price = new_retail

product.last_price_update = timezone.now()

# Save with explicit field list
update_fields = list(updates_to_apply.keys()) + ['last_price_update']
product.save(update_fields=update_fields)
```

---

## 9. UI Components

### 9.1 Category Filter Section (Line 20-60)

```html
<!-- Category Selection - Top Priority -->
<div class="row mb-3">
    <div class="col-12">
        <div class="card border-0 shadow-sm">
            <div class="card-body py-3">
                <div class="row align-items-center">
                    <div class="col-lg-6">
                        <label class="form-label fw-semibold mb-2">
                            <i class="uil-filter text-primary me-2"></i>Category Filter
                        </label>
                        <select class="form-select" id="category-filter">
                            <option value="all">All Categories (Warning: May cause browser freeze)</option>
                            <option value="lotto-clubs">LOTTO Clubs</option>
                            <option value="sas-clubs">SAS Clubs</option>
                            <option value="retail-schools">Retail Schools</option>
                            <option value="wholesale-schools" selected>Wholesale Schools</option>
                        </select>
                    </div>
                    <!-- Expected item count and processing mode -->
                </div>
            </div>
        </div>
    </div>
</div>
```

**Features**:
- ✅ Visual prominence (top of page)
- ✅ Item count estimates per category
- ✅ Warning for large datasets
- ✅ Processing mode selector
- ❌ Not connected to backend logic

### 9.2 File Upload Section (Line 63-190)

**Features**:
- ✅ Drag-and-drop upload zone
- ✅ Browse button
- ✅ File validation (CSV, XLS, XLSX)
- ✅ 50MB size limit
- ✅ Multiple file support
- ✅ Visual feedback
- ✅ Template download link

### 9.3 Preview Section (Line 192-315)

**Features**:
- ✅ DataTable with pagination
- ✅ Status indicators (valid/warning/error)
- ✅ School and product names
- ✅ Current vs new price comparison
- ✅ Calculated margins and discounts
- ✅ Bulk selection controls
- ✅ Export to CSV
- ✅ Apply/Reject buttons

### 9.4 Progress Section (Line 317-396)

**Features**:
- ✅ Real-time progress bars
- ✅ File processing counter
- ✅ Record update counter
- ✅ Current operation display
- ✅ Cancel button
- ✅ Spinner animations

### 9.5 Results Section (Line 398-478)

**Features**:
- ✅ Success/failure summary
- ✅ Processing time
- ✅ Detailed results table
- ✅ Download report
- ✅ View changes history

### 9.6 Activity Log (Line 480-510)

**Features**:
- ✅ Timestamped entries
- ✅ Color-coded by severity
- ✅ Auto-scroll
- ✅ Download log
- ✅ Clear log
- ✅ Refresh

---

## 10. Gap Analysis

### 10.1 What's Missing for Multi-Category Support

| Component | Current State | Required Changes |
|-----------|--------------|------------------|
| **Backend Models** | Only WholesaleProduct | Add pricing fields to TUS/SAS/LOTTO models |
| **Product Matching** | Hard-coded WholesaleProduct | Dynamic model selection based on category |
| **SKU Field Names** | cin7_sku | Handle 'sku' vs 'cin7_sku' |
| **CSV Parsing** | Wholesale-specific headers | Flexible header mapping per category |
| **Preview Logic** | WholesaleProduct queries | Strategy pattern for model selection |
| **Apply Logic** | WholesaleProduct updates | Universal updater service |
| **URL Routing** | Wholesale-specific paths | Unified endpoints with type parameter |

### 10.2 Implementation Recommendations

#### Option A: Extend Current Implementation (Minimal Changes)
**Pros**:
- Preserves existing functionality
- Lower risk
- Faster implementation

**Cons**:
- Code duplication
- Harder to maintain
- Inconsistent patterns

#### Option B: Refactor to Unified System (RECOMMENDED)
**Pros**:
- Single codebase
- Strategy pattern for flexibility
- Easier to test and maintain
- Consistent UX across categories

**Cons**:
- More initial work
- Need comprehensive testing
- Potential breaking changes

---

## 11. Recommended Implementation Strategy

Based on the analysis and `/Users/sas/Repos/SASKITUP/PRICE_UPDATE_EXTENSION_PLAN.md`:

### Phase 1: Add Model Fields (Week 1)
- Add pricing fields to TUSProduct, SASProduct, LottoProduct
- Add barcode fields for matching
- Add calculated property methods
- Run migrations

### Phase 2: Create Product Matcher Service (Week 1)
- Create `/schools/services/product_matcher.py`
- Implement multi-strategy matching:
  1. Exact SKU match
  2. Case-insensitive SKU match
  3. Barcode match
  4. Partial SKU match (variations)
- Handle different SKU field names

### Phase 3: Create Unified Price Updater Service (Week 2)
- Create `/schools/services/price_updater.py`
- Implement CSV parsing with flexible headers
- Implement preview generation
- Implement price application with transactions

### Phase 4: Update Views (Week 2)
- Modify `wholesale_price_preview` to use new service
- Modify `wholesale_price_apply` to use new service
- Add category parameter handling
- Maintain backward compatibility

### Phase 5: No Template Changes Needed (Week 2)
- ✅ Template already has category filter
- ✅ Template already sends category to backend
- Only need to ensure backend uses it

### Phase 6: Testing (Week 3)
- Unit tests for product matcher
- Unit tests for price updater
- Integration tests for full flow
- Test with sample CSVs for each category

---

## 12. Key Implementation Points

### 12.1 Product Matcher Service Structure

```python
# /Users/sas/Repos/SASKITUP/schools/services/product_matcher.py

class ProductMatcherService:
    PRODUCT_MODELS = {
        'wholesale-schools': WholesaleProduct,
        'retail-schools': TUSProduct,
        'sas-clubs': SASProduct,
        'lotto-clubs': LottoProduct,
    }

    SKU_FIELDS = {
        'wholesale-schools': 'cin7_sku',
        'retail-schools': 'sku',
        'sas-clubs': 'sku',
        'lotto-clubs': 'sku',
    }

    BARCODE_FIELDS = {
        'wholesale-schools': 'cin7_barcode',
        'retail-schools': 'barcode',  # After migration
        'sas-clubs': 'barcode',       # After migration
        'lotto-clubs': 'barcode',     # After migration
    }

    def find_product(self, category, product_code=None, barcode=None):
        """Multi-strategy product matching"""
        # Strategy 1: Exact SKU
        # Strategy 2: Case-insensitive SKU
        # Strategy 3: Exact barcode
        # Strategy 4: Case-insensitive barcode
        # Return (product, match_method)
```

### 12.2 Modified View Logic

```python
# In wholesale_price_preview() at Line 1933

def wholesale_price_preview(request):
    # Get category from request
    category = request.POST.get('category_filter', 'wholesale-schools')

    # Validate category
    if category not in ['wholesale-schools', 'retail-schools', 'sas-clubs', 'lotto-clubs']:
        category = 'wholesale-schools'

    # Use product matcher service
    matcher = ProductMatcherService()

    for row in csv_reader:
        product_code = extract_field(row, ['product_code', 'Code', 'Style Code'])
        barcode = extract_field(row, ['barcode', 'Barcode'])

        # Use matcher instead of hard-coded WholesaleProduct
        product, match_method = matcher.find_product(
            category=category,
            product_code=product_code,
            barcode=barcode
        )
```

---

## 13. File Paths for Implementation

### Files to Create
```
/Users/sas/Repos/SASKITUP/schools/services/
├── __init__.py
├── product_matcher.py    (NEW - Product matching logic)
└── price_updater.py      (NEW - Price update logic)
```

### Files to Modify
```
/Users/sas/Repos/SASKITUP/clubs/
├── models_tus.py         (Add pricing fields)
├── models_sas.py         (Add pricing fields)
└── models_lotto.py       (Add pricing fields)

/Users/sas/Repos/SASKITUP/schools/
├── views.py              (Modify Line 1933, 2087)
└── urls.py               (Optional - keep current URLs)
```

### Files Unchanged
```
/Users/sas/Repos/SASKITUP/schools/templates/schools/wholesale/
└── price_update_settings.html    (NO CHANGES NEEDED - Already perfect!)
```

---

## 14. Summary and Next Steps

### Current State
✅ **Fully functional** wholesale price update system
✅ **Complete UI** with category filter already in place
✅ **Robust backend** with transaction safety and logging
✅ **Category filter sends data** to backend (Line 1371-1378)

### What Needs to Change
❌ Backend ignores category parameter
❌ Hard-coded to WholesaleProduct model
❌ TUS/SAS/LOTTO models missing pricing fields
❌ No flexible product matching strategy

### Recommended Next Steps
1. **Phase 1**: Add pricing fields to TUS/SAS/LOTTO models (1 week)
2. **Phase 2**: Create ProductMatcherService (1 week)
3. **Phase 3**: Create PriceUpdaterService (1 week)
4. **Phase 4**: Update views to use new services (3 days)
5. **Phase 5**: Testing and validation (1 week)

### Total Estimated Effort
**3-4 weeks** for complete implementation

---

## 15. References

- Template: `/Users/sas/Repos/SASKITUP/schools/templates/schools/wholesale/price_update_settings.html`
- Views: `/Users/sas/Repos/SASKITUP/schools/views.py` (Lines 1933-2427)
- URLs: `/Users/sas/Repos/SASKITUP/schools/urls.py` (Lines 68-72)
- Extension Plan: `/Users/sas/Repos/SASKITUP/PRICE_UPDATE_EXTENSION_PLAN.md`

---

**End of Analysis**
