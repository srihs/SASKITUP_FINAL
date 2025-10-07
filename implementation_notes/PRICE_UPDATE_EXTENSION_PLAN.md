# Wholesale Price Update Feature Extension Plan
## Extending to Support TUS, SAS, and LOTTO Products

**Date**: 2025-10-06
**Status**: Design Phase
**Database**: Fresh (Breaking changes allowed)

---

## 1. MODEL ANALYSIS

### 1.1 Current Pricing Fields Comparison

| Field | WholesaleProduct | TUSProduct | SASProduct | LottoProduct |
|-------|-----------------|------------|------------|--------------|
| **SKU** | `cin7_sku` (CharField) | `sku` (CharField) | `sku` (CharField) | `sku` (CharField) |
| **Barcode** | `cin7_barcode` (CharField) | ❌ None | ❌ None | ❌ None |
| **Cost Price** | `cost_price` (Decimal) | ❌ None | ❌ None | ❌ None |
| **Regular Price** | `retail_price` (Decimal) | `regular_price` (Decimal) | `regular_price` (Decimal) | `regular_price` (Decimal) |
| **Sale Price** | ❌ None | `sale_price` (Decimal) | `sale_price` (Decimal) | `sale_price` (Decimal) |
| **Current Price** | `wholesale_price` (Decimal) | `price` (Decimal) | `price` (Decimal) | `price` (Decimal) |
| **75% Margin** | `margin_75_price` (Decimal) | ❌ None | ❌ None | ❌ None |
| **Discount %** | `discount_percentage` (Decimal) | ❌ None | ❌ None | ❌ None |
| **Last Update** | `last_price_update` (DateTime) | ❌ None | ❌ None | ❌ None |
| **Stock Status** | `stock_status` (CharField) | `stock_status` (CharField) | `stock_status` (CharField) | `stock_status` (CharField) |

### 1.2 Key Observations

**Common Fields Across All Models**:
- `sku` - Product identifier (but different field names: cin7_sku vs sku)
- `price` or `wholesale_price` - Current selling price
- `regular_price` - Regular price (except Wholesale)
- `stock_status` - Inventory status

**Missing in TUS/SAS/LOTTO**:
- `cost_price` - Base cost from supplier
- `margin_75_price` - Calculated 75% margin price
- `discount_percentage` - Discount from margin price
- `last_price_update` - Timestamp for last price change
- Barcode field for alternative product matching

**Wholesale-Specific Fields**:
- `cin7_sku`, `cin7_barcode` - CIN7 integration fields
- `cin7_brand`, `cin7_supplier` - Additional CIN7 metadata
- `quantity_available`, `quantity_on_hand`, `quantity_committed` - Advanced stock tracking

---

## 2. SCHEMA DESIGN

### 2.1 Recommended Unified Pricing Fields

Add the following fields to **TUSProduct**, **SASProduct**, and **LottoProduct** models:

```python
# Pricing enhancement fields
cost_price = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    null=True,
    blank=True,
    help_text="Cost price from supplier"
)

margin_75_price = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    null=True,
    blank=True,
    help_text="75% margin price (Cost ÷ 0.25)"
)

discount_percentage = models.DecimalField(
    max_digits=5,
    decimal_places=2,
    null=True,
    blank=True,
    help_text="Discount percentage from 75% margin price"
)

last_price_update = models.DateTimeField(
    null=True,
    blank=True,
    help_text="When prices were last updated"
)

# Optional: Barcode for product matching
barcode = models.CharField(
    max_length=100,
    blank=True,
    help_text="Product barcode for CSV matching"
)
```

### 2.2 Migration Strategy

**Step 1**: Create migrations for each model
```bash
# TUS Products
python manage.py makemigrations clubs --name add_pricing_fields_to_tus

# SAS Products
python manage.py makemigrations clubs --name add_pricing_fields_to_sas

# LOTTO Products
python manage.py makemigrations clubs --name add_pricing_fields_to_lotto
```

**Step 2**: Run migrations
```bash
python manage.py migrate clubs
```

**Step 3**: Model enhancements - Add calculated properties

```python
# Add to TUSProduct, SASProduct, LottoProduct models

def calculate_margin_75_price(self):
    """Calculate the 75% margin price (Cost ÷ 0.25)"""
    if self.cost_price and self.cost_price > 0:
        return self.cost_price / Decimal('0.25')
    return None

def calculate_discount_percentage(self):
    """Calculate discount percentage from 75% margin price"""
    if self.margin_75_price and self.regular_price and self.margin_75_price > 0:
        discount = ((self.margin_75_price - self.regular_price) / self.margin_75_price) * 100
        return max(Decimal('0'), discount)
    return None

def update_calculated_pricing(self):
    """Update all calculated pricing fields"""
    from django.utils import timezone

    self.margin_75_price = self.calculate_margin_75_price()
    self.discount_percentage = self.calculate_discount_percentage()
    self.last_price_update = timezone.now()
    self.save(update_fields=['margin_75_price', 'discount_percentage', 'last_price_update'])
```

### 2.3 Database Indexes

Add indexes for price update queries:

```python
# In Meta class for each model
indexes = [
    # Existing indexes...
    models.Index(fields=['sku']),  # For CSV matching
    models.Index(fields=['barcode']),  # For CSV matching
    models.Index(fields=['cost_price']),
    models.Index(fields=['margin_75_price']),
    models.Index(fields=['discount_percentage']),
    models.Index(fields=['last_price_update']),
]
```

---

## 3. API DESIGN

### 3.1 URL Structure Recommendation

**Option A: Unified Endpoint with Type Parameter** ✅ RECOMMENDED
```
POST /api/price-update/preview/?type=wholesale|tus|sas|lotto
POST /api/price-update/apply/?type=wholesale|tus|sas|lotto
GET  /price-update/settings/?type=wholesale|tus|sas|lotto
```

**Advantages**:
- Single codebase for price update logic
- Consistent UI/UX across product types
- Easier maintenance and testing
- Type-specific logic handled via strategy pattern

**Option B: Separate Endpoints per Type**
```
POST /wholesale/api/price-preview/
POST /tus/api/price-preview/
POST /sas/api/price-preview/
POST /lotto/api/price-preview/
```

**Advantages**:
- Clear separation of concerns
- Type-specific customization easier
- Independent deployment of features

### 3.2 Recommended Approach: Unified with Strategy Pattern

**URL Configuration**:
```python
# schools/urls.py or create api/urls.py
urlpatterns = [
    # Unified price update endpoints
    path('api/price-update/preview/', views.price_update_preview, name='price-update-preview'),
    path('api/price-update/apply/', views.price_update_apply, name='price-update-apply'),
    path('settings/price-update/', views.price_update_settings, name='price-update-settings'),
]
```

### 3.3 Request/Response Format

**Preview Request**:
```json
{
  "product_type": "tus|sas|lotto|wholesale",
  "csv_data": "base64_encoded_csv_content"
}
```

**Preview Response**:
```json
{
  "success": true,
  "product_type": "tus",
  "preview_data": [
    {
      "row_number": 1,
      "product_code": "TUS-123",
      "barcode": "9421012345678",
      "product_name": "School Uniform - Navy Blazer",
      "product_found": true,
      "database_product_name": "School Uniform - Navy Blazer",
      "school_name": "Auckland Grammar School",
      "current_cost_price": 45.00,
      "current_margin_75_price": 180.00,
      "current_regular_price": 150.00,
      "new_cost": 50.00,
      "new_margin_75_price": 200.00,
      "new_discount_percentage": 25.00,
      "new_retail_price": 150.00
    }
  ],
  "summary": {
    "total_rows": 100,
    "valid_products": 95,
    "invalid_products": 5,
    "errors": ["Row 3: Product not found", "Row 7: Invalid price format"]
  }
}
```

**Apply Request**:
```json
{
  "product_type": "tus|sas|lotto|wholesale",
  "selected_items": [
    {
      "product_code": "TUS-123",
      "barcode": "9421012345678",
      "cost": 50.00,
      "margin_75_price": 200.00,
      "discount_percentage": 25.00,
      "current_retail_price": 150.00
    }
  ],
  "backup_prices": true
}
```

---

## 4. CSV FORMAT SPECIFICATION

### 4.1 Universal CSV Format

**Recommended Headers** (case-insensitive, flexible matching):
```csv
Product Code,Barcode,Product Name,Cost,75% Margin Price,Discount %,Retail Price
```

**Alternative Header Names** (for backwards compatibility):
- `Product Code`: `sku`, `product_sku`, `code`, `style_code`, `cin7_sku`
- `Barcode`: `product_barcode`, `cin7_barcode`
- `Cost`: `cost_price`, `cost_nzd_excl`, `unit_cost`
- `75% Margin Price`: `margin_price`, `margin_75_price`, `wholesale_excl_gst`
- `Retail Price`: `retail_nzd_incl`, `selling_price`, `regular_price`

### 4.2 Product Matching Strategy

**Priority Order**:
1. **Exact SKU Match** (case-sensitive)
2. **Case-Insensitive SKU Match**
3. **Exact Barcode Match** (if barcode field exists)
4. **Case-Insensitive Barcode Match**
5. **Partial SKU Match** (for variations like "TUS-123-XL" matching "TUS-123")

**Product Type Detection**:
- Explicit `product_type` parameter in request
- Or auto-detect from SKU prefix:
  - `TUS-*` → TUSProduct
  - `SAS-*` → SASProduct
  - `LOTTO-*` → LottoProduct
  - `US *`, `CIN7:*` → WholesaleProduct

### 4.3 Sample CSV Templates

**TUS Products CSV**:
```csv
Product Code,Barcode,Product Name,Cost,75% Margin Price,Discount %,Retail Price
TUS-001,9421001,Navy Blazer - Size 10,45.00,180.00,16.67,150.00
TUS-002,9421002,Navy Blazer - Size 12,45.00,180.00,16.67,150.00
```

**SAS Products CSV**:
```csv
Product Code,Barcode,Product Name,Cost,75% Margin Price,Discount %,Retail Price
SAS-001,9422001,Cricket Jersey - M,35.00,140.00,21.43,110.00
SAS-002,9422002,Cricket Jersey - L,35.00,140.00,21.43,110.00
```

**LOTTO Products CSV**:
```csv
Product Code,Barcode,Product Name,Cost,75% Margin Price,Discount %,Retail Price
LOTTO-001,9423001,Training Top - Black,40.00,160.00,18.75,130.00
```

**Wholesale Products CSV** (existing format):
```csv
Code,Barcode,Product Name,Cost NZD Excl,WholesaleExGST NZD Excl,Retail NZD Incl
US FLC 789 CGS,123456,Fleece Jacket,50.00,200.00,175.00
```

---

## 5. IMPLEMENTATION PLAN

### 5.1 Phase 1: Database Schema (Week 1)

**Files to Modify**:
- `/Users/sas/Repos/SASKITUP/clubs/models_tus.py` (TUSProduct model)
- `/Users/sas/Repos/SASKITUP/clubs/models_sas.py` (SASProduct model)
- `/Users/sas/Repos/SASKITUP/clubs/models_lotto.py` (LottoProduct model)

**Tasks**:
1. Add pricing fields to TUSProduct model
2. Add pricing fields to SASProduct model
3. Add pricing fields to LottoProduct model
4. Add calculated property methods
5. Create and run migrations
6. Add database indexes

**Testing**:
- Create test products with pricing data
- Verify calculated properties work correctly
- Test migration rollback

### 5.2 Phase 2: Product Matcher Service (Week 1)

**New File**: `/Users/sas/Repos/SASKITUP/schools/services/product_matcher.py`

```python
class ProductMatcherService:
    """
    Universal product matcher for price updates across all product types
    """

    PRODUCT_MODELS = {
        'wholesale': WholesaleProduct,
        'tus': TUSProduct,
        'sas': SASProduct,
        'lotto': LottoProduct,
    }

    SKU_FIELDS = {
        'wholesale': 'cin7_sku',
        'tus': 'sku',
        'sas': 'sku',
        'lotto': 'sku',
    }

    BARCODE_FIELDS = {
        'wholesale': 'cin7_barcode',
        'tus': 'barcode',
        'sas': 'barcode',
        'lotto': 'barcode',
    }

    def find_product(self, product_type, product_code=None, barcode=None):
        """Find product by code or barcode with fallback strategies"""
        model = self.PRODUCT_MODELS[product_type]
        sku_field = self.SKU_FIELDS[product_type]
        barcode_field = self.BARCODE_FIELDS.get(product_type)

        # Strategy 1: Exact SKU match
        if product_code:
            product = model.objects.filter(**{sku_field: product_code}).first()
            if product:
                return product, 'sku_exact'

        # Strategy 2: Case-insensitive SKU match
        if product_code:
            product = model.objects.filter(**{f'{sku_field}__iexact': product_code}).first()
            if product:
                return product, 'sku_iexact'

        # Strategy 3: Barcode match (if supported)
        if barcode and barcode_field:
            product = model.objects.filter(**{barcode_field: barcode}).first()
            if product:
                return product, 'barcode_exact'

        return None, 'not_found'
```

### 5.3 Phase 3: Unified Price Update Service (Week 2)

**New File**: `/Users/sas/Repos/SASKITUP/schools/services/price_updater.py`

```python
class PriceUpdaterService:
    """
    Universal price updater for all product types
    """

    def __init__(self, product_type):
        self.product_type = product_type
        self.matcher = ProductMatcherService()

    def preview_csv(self, csv_file):
        """Generate preview of price updates"""
        preview_data = []
        errors = []

        reader = self._parse_csv(csv_file)

        for row_num, row in enumerate(reader, 1):
            try:
                product_code = self._extract_field(row, ['product_code', 'sku', 'code'])
                barcode = self._extract_field(row, ['barcode'])

                product, match_type = self.matcher.find_product(
                    self.product_type,
                    product_code=product_code,
                    barcode=barcode
                )

                preview_item = {
                    'row_number': row_num,
                    'product_code': product_code,
                    'barcode': barcode,
                    'product_found': product is not None,
                    'match_type': match_type,
                    # ... extract pricing fields
                }

                preview_data.append(preview_item)

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        return {
            'preview_data': preview_data,
            'errors': errors,
            'summary': self._generate_summary(preview_data, errors)
        }

    def apply_updates(self, selected_items, backup=True):
        """Apply price updates with optional backup"""
        results = {
            'successful_updates': 0,
            'failed_updates': 0,
            'errors': []
        }

        with transaction.atomic():
            for item in selected_items:
                try:
                    product, _ = self.matcher.find_product(
                        self.product_type,
                        product_code=item['product_code'],
                        barcode=item.get('barcode')
                    )

                    if not product:
                        results['errors'].append(f"Product not found: {item['product_code']}")
                        results['failed_updates'] += 1
                        continue

                    # Backup current prices
                    if backup:
                        backup_data = self._backup_prices(product)

                    # Apply updates
                    self._update_product_prices(product, item)

                    results['successful_updates'] += 1

                except Exception as e:
                    results['errors'].append(str(e))
                    results['failed_updates'] += 1

        return results
```

### 5.4 Phase 4: Views and URLs (Week 2)

**Files to Modify**:
- `/Users/sas/Repos/SASKITUP/schools/views.py`
- `/Users/sas/Repos/SASKITUP/schools/urls.py`

**New Views**:
```python
@csrf_exempt
@require_http_methods(["POST"])
def price_update_preview(request):
    """Universal price update preview endpoint"""
    product_type = request.GET.get('type', 'wholesale')

    if product_type not in ['wholesale', 'tus', 'sas', 'lotto']:
        return JsonResponse({'success': False, 'error': 'Invalid product type'})

    service = PriceUpdaterService(product_type)
    result = service.preview_csv(request.FILES.get('csv_file'))

    return JsonResponse({'success': True, **result})

@csrf_exempt
@require_http_methods(["POST"])
def price_update_apply(request):
    """Universal price update apply endpoint"""
    data = json.loads(request.body)
    product_type = data.get('product_type', 'wholesale')

    service = PriceUpdaterService(product_type)
    result = service.apply_updates(
        data.get('selected_items', []),
        backup=data.get('backup_prices', True)
    )

    return JsonResponse({'success': True, **result})

def price_update_settings(request):
    """Universal price update settings page"""
    product_type = request.GET.get('type', 'wholesale')

    context = {
        'product_type': product_type,
        'page_title': f'{product_type.upper()} Price Update Settings',
    }

    return render(request, 'schools/price_update_settings.html', context)
```

### 5.5 Phase 5: Frontend Templates (Week 3)

**New Template**: `/Users/sas/Repos/SASKITUP/schools/templates/schools/price_update_settings.html`

**Features**:
- Product type selector (Wholesale, TUS, SAS, LOTTO)
- CSV upload area
- Preview table with:
  - Product matching status
  - Current vs new prices comparison
  - Calculated margin and discount
- Bulk select/deselect
- Apply changes button
- Download sample CSV template

**Template Structure**:
```django
{% extends "frontend/base.html" %}

{% block content %}
<div class="price-update-container">
    <div class="type-selector">
        <button data-type="wholesale" class="active">Wholesale</button>
        <button data-type="tus">TUS Retail</button>
        <button data-type="sas">SAS Sports</button>
        <button data-type="lotto">LOTTO</button>
    </div>

    <div class="csv-upload">
        <form id="csv-upload-form" enctype="multipart/form-data">
            <input type="file" name="csv_file" accept=".csv">
            <button type="submit">Preview Updates</button>
        </form>
        <a href="{% url 'download-csv-template' %}?type={{ product_type }}"
           class="download-template">
            Download CSV Template
        </a>
    </div>

    <div id="preview-table" style="display:none;">
        <!-- Preview table rendered via JavaScript -->
    </div>

    <div class="actions">
        <button id="apply-selected" disabled>Apply Selected Updates</button>
        <button id="cancel">Cancel</button>
    </div>
</div>
{% endblock %}
```

### 5.6 Phase 6: Testing (Week 3)

**Test Files to Create**:
- `/Users/sas/Repos/SASKITUP/schools/tests/test_product_matcher.py`
- `/Users/sas/Repos/SASKITUP/schools/tests/test_price_updater.py`
- `/Users/sas/Repos/SASKITUP/schools/tests/test_price_update_views.py`

**Test Coverage**:
1. Model field additions and calculations
2. Product matching strategies (SKU, barcode, variations)
3. CSV parsing and preview generation
4. Price update application with rollback
5. API endpoints (preview, apply)
6. Error handling and validation
7. Cross-product-type consistency

**Sample Test**:
```python
class PriceUpdateTestCase(TestCase):
    def setUp(self):
        # Create test products for each type
        self.tus_product = TUSProduct.objects.create(
            sku='TUS-001',
            barcode='9421001',
            name='Test Product',
            price=150.00,
            regular_price=150.00
        )

    def test_tus_price_update(self):
        """Test TUS product price update"""
        service = PriceUpdaterService('tus')

        updates = [{
            'product_code': 'TUS-001',
            'cost': 45.00,
            'margin_75_price': 180.00,
            'current_retail_price': 150.00
        }]

        result = service.apply_updates(updates)

        self.assertEqual(result['successful_updates'], 1)
        self.assertEqual(result['failed_updates'], 0)

        # Verify product was updated
        self.tus_product.refresh_from_db()
        self.assertEqual(self.tus_product.cost_price, Decimal('45.00'))
        self.assertEqual(self.tus_product.margin_75_price, Decimal('180.00'))
```

---

## 6. FILE PATHS AND LINE NUMBERS

### Models (Phase 1)
| File | Model | Line Number | Action |
|------|-------|-------------|--------|
| `/Users/sas/Repos/SASKITUP/clubs/models_tus.py` | TUSProduct | ~449-555 | Add pricing fields after line 505 |
| `/Users/sas/Repos/SASKITUP/clubs/models_sas.py` | SASProduct | ~389-569 | Add pricing fields after line 455 |
| `/Users/sas/Repos/SASKITUP/clubs/models_lotto.py` | LottoProduct | ~152-899 | Add pricing fields after line 287 |

### Services (Phase 2-3)
| File | Purpose | Status |
|------|---------|--------|
| `/Users/sas/Repos/SASKITUP/schools/services/product_matcher.py` | Product matching logic | Create new |
| `/Users/sas/Repos/SASKITUP/schools/services/price_updater.py` | Price update logic | Create new |
| `/Users/sas/Repos/SASKITUP/schools/services/__init__.py` | Service exports | Create new |

### Views (Phase 4)
| File | Function | Line Number | Action |
|------|----------|-------------|--------|
| `/Users/sas/Repos/SASKITUP/schools/views.py` | `price_update_preview` | End of file | Add new view |
| `/Users/sas/Repos/SASKITUP/schools/views.py` | `price_update_apply` | End of file | Add new view |
| `/Users/sas/Repos/SASKITUP/schools/views.py` | `price_update_settings` | ~2406 | Refactor existing |

### URLs (Phase 4)
| File | Path | Line Number | Action |
|------|------|-------------|--------|
| `/Users/sas/Repos/SASKITUP/schools/urls.py` | Unified endpoints | ~68-72 | Replace existing wholesale-specific URLs |

### Templates (Phase 5)
| File | Purpose | Status |
|------|---------|--------|
| `/Users/sas/Repos/SASKITUP/schools/templates/schools/price_update_settings.html` | Main UI | Create new (unified) |
| `/Users/sas/Repos/SASKITUP/schools/templates/schools/partials/price_preview_table.html` | Preview table | Create new |

---

## 7. MIGRATION COMMANDS

```bash
# Step 1: Create migrations
python manage.py makemigrations clubs --name add_pricing_fields_to_tus
python manage.py makemigrations clubs --name add_pricing_fields_to_sas
python manage.py makemigrations clubs --name add_pricing_fields_to_lotto

# Step 2: Review migrations
python manage.py sqlmigrate clubs <migration_number>

# Step 3: Apply migrations
python manage.py migrate clubs

# Step 4: Verify migrations
python manage.py showmigrations clubs
```

---

## 8. API SPECIFICATIONS

### 8.1 Preview Endpoint

**URL**: `POST /api/price-update/preview/?type={product_type}`

**Request Headers**:
```
Content-Type: multipart/form-data
```

**Request Body**:
```
csv_file: <binary file data>
```

**Response** (200 OK):
```json
{
  "success": true,
  "product_type": "tus",
  "preview_data": [...],
  "summary": {
    "total_rows": 100,
    "valid_products": 95,
    "invalid_products": 5,
    "errors": []
  }
}
```

### 8.2 Apply Endpoint

**URL**: `POST /api/price-update/apply/`

**Request Headers**:
```
Content-Type: application/json
```

**Request Body**:
```json
{
  "product_type": "tus",
  "selected_items": [...],
  "backup_prices": true
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "results": {
    "successful_updates": 95,
    "failed_updates": 0,
    "errors": [],
    "updated_products": [...]
  }
}
```

---

## 9. TESTING CHECKLIST

- [ ] TUSProduct pricing fields added and migrated
- [ ] SASProduct pricing fields added and migrated
- [ ] LottoProduct pricing fields added and migrated
- [ ] ProductMatcherService finds products by SKU (exact)
- [ ] ProductMatcherService finds products by SKU (case-insensitive)
- [ ] ProductMatcherService finds products by barcode
- [ ] PriceUpdaterService generates preview correctly
- [ ] PriceUpdaterService applies updates with transaction
- [ ] PriceUpdaterService backs up original prices
- [ ] Preview endpoint returns valid data for TUS
- [ ] Preview endpoint returns valid data for SAS
- [ ] Preview endpoint returns valid data for LOTTO
- [ ] Apply endpoint updates TUS products
- [ ] Apply endpoint updates SAS products
- [ ] Apply endpoint updates LOTTO products
- [ ] CSV template downloads correctly for each type
- [ ] Frontend type selector works
- [ ] Frontend preview table displays correctly
- [ ] Frontend apply button works
- [ ] Error handling for missing products
- [ ] Error handling for invalid CSV format
- [ ] Error handling for database errors

---

## 10. ROLLOUT STRATEGY

### 10.1 Development Environment
1. Create feature branch: `feature/unified-price-update`
2. Implement Phase 1 (models + migrations)
3. Implement Phase 2-3 (services)
4. Implement Phase 4 (views + URLs)
5. Implement Phase 5 (templates)
6. Implement Phase 6 (tests)
7. Code review and testing

### 10.2 Staging Environment
1. Deploy feature branch
2. Run migrations on staging database
3. Test with sample CSV files for each product type
4. Verify price updates don't affect production data
5. Performance testing with large CSV files

### 10.3 Production Deployment
1. Database backup
2. Run migrations during low-traffic window
3. Deploy code changes
4. Verify endpoints are accessible
5. Monitor for errors in first 24 hours
6. Rollback plan: revert migrations and code

---

## 11. DOCUMENTATION

### 11.1 User Documentation
- CSV format guide for each product type
- Step-by-step price update workflow
- Troubleshooting common errors
- Sample CSV templates

### 11.2 Developer Documentation
- API specifications
- Service architecture diagram
- Database schema changes
- Testing guide

---

## 12. RECOMMENDATIONS

1. **Start with TUSProduct** - Largest model, most complex pricing
2. **Use strategy pattern** - Easier to extend to new product types
3. **Comprehensive logging** - Debug CSV parsing and matching issues
4. **Backup mechanism** - Store original prices before updates
5. **Batch processing** - Handle large CSV files efficiently
6. **Validation layer** - Prevent invalid price updates
7. **Audit trail** - Track who updated prices and when
8. **Error recovery** - Rollback on partial failures

---

## NEXT STEPS

1. Review this plan with team
2. Estimate effort for each phase
3. Create Jira tickets for implementation
4. Set up development environment
5. Begin Phase 1: Database schema changes

---

**End of Plan**
