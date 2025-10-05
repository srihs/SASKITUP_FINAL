# Style Code Implementation Guide

**Optional Enhancement:** Add separate `style_code` field to SASProduct model

**Note:** This is an optional enhancement if Style Code information is valuable for your business logic. The SKU field should still be populated from WooCommerce's SKU field.

---

## Why Add style_code Field?

### Current Situation:
- SKU field: 5% populated (from WooCommerce SKU)
- Style Code: Present in short_description for many products
- Style Code ≠ SKU (different identifiers)

### Benefits of Separate style_code Field:
1. **Preserve Product Information**: Capture Style Code without overwriting SKU
2. **Better Search**: Search by Style Code separately from SKU
3. **Data Integrity**: Keep SKU for inventory, Style Code for product identification
4. **Reporting**: Generate reports using Style Code grouping

---

## Implementation Steps

### Step 1: Create Django Migration

**File:** `/Users/sas/Repos/SASKITUP/clubs/migrations/XXXX_add_style_code_to_sas_product.py`

```python
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clubs', 'PREVIOUS_MIGRATION_NAME'),  # Update with actual previous migration
    ]

    operations = [
        migrations.AddField(
            model_name='sasproduct',
            name='style_code',
            field=models.CharField(
                max_length=100,
                blank=True,
                help_text="Product style code extracted from description"
            ),
        ),
        migrations.AddIndex(
            model_name='sasproduct',
            index=models.Index(fields=['style_code'], name='sas_prod_style_idx'),
        ),
    ]
```

**Run Migration:**
```bash
python manage.py makemigrations clubs
python manage.py migrate clubs
```

---

### Step 2: Update SASProduct Model

**File:** `/Users/sas/Repos/SASKITUP/clubs/models_sas.py`

**Add field after line 429 (after sku field):**

```python
class SASProduct(models.Model):
    # ... existing fields ...

    # Stock Keeping Unit
    sku = models.CharField(max_length=100, blank=True, help_text="Stock Keeping Unit")

    # NEW: Style Code field
    style_code = models.CharField(
        max_length=100,
        blank=True,
        help_text="Product style code extracted from description"
    )

    # ... rest of fields ...
```

**Add index in Meta class (around line 502):**

```python
class Meta:
    db_table = 'sas_products'
    verbose_name = 'SAS Product'
    verbose_name_plural = 'SAS Products'
    ordering = ['club__sport__name', 'club__name', 'name']
    indexes = [
        # ... existing indexes ...
        models.Index(fields=['sku']),
        models.Index(fields=['style_code']),  # NEW
        # ... rest of indexes ...
    ]
```

---

### Step 3: Update Sync Command

**File:** `/Users/sas/Repos/SASKITUP/clubs/management/commands/sync_sas_clubs.py`

**Add import at top (line 30):**

```python
from clubs.models_sas import SASSport, SASClub, SASProduct
from clubs.services.woocommerce_service import WooCommerceService
# NEW: Import extraction utility
import sys
import os
sys.path.insert(0, '/Users/sas/Repos/SASKITUP')
from style_code_extraction_utils import extract_style_code
```

**Update _process_sas_product method (around line 572):**

```python
def _process_sas_product(self, product_data, club_obj, force_update) -> Tuple[SASProduct, bool]:
    """Create or update SASProduct model"""
    woo_product_id = product_data['id']

    # Check if product already exists
    existing_product = SASProduct.objects.filter(woo_product_id=woo_product_id).first()

    # Parse pricing information
    try:
        # ... existing pricing code ...
    except (InvalidOperation, ValueError) as e:
        # ... existing error handling ...

    # NEW: Extract style code from short_description
    style_code = extract_style_code(product_data.get('short_description', ''))

    # Prepare product data
    product_data_obj = {
        'club': club_obj,
        'name': product_data['name'],
        'woo_product_id': woo_product_id,
        'slug': product_data.get('slug', slugify(product_data['name'])),
        'price': price,
        'regular_price': regular_price,
        'sale_price': sale_price,
        'description': product_data.get('description', ''),
        'short_description': product_data.get('short_description', ''),
        'sku': product_data.get('sku', ''),  # Keep existing SKU from WooCommerce
        'style_code': style_code,  # NEW: Add extracted style code
        'stock_status': product_data.get('stock_status', 'instock'),
        'weight': product_data.get('weight', ''),
        'dimensions': product_data.get('dimensions', {}),
        'tags': [tag['name'] for tag in product_data.get('tags', [])],
        'attributes': product_data.get('attributes', []),
    }

    # ... rest of existing code ...
```

**Update _product_needs_update method (around line 651):**

```python
def _product_needs_update(self, existing_product, new_data) -> bool:
    """Check if product needs updating"""
    fields_to_check = ['name', 'price', 'regular_price', 'sale_price', 'stock_status', 'sku', 'style_code']  # Added style_code

    for field in fields_to_check:
        # ... existing comparison code ...
```

---

### Step 4: One-Time Update for Existing Products

**File:** `/Users/sas/Repos/SASKITUP/update_existing_style_codes.py`

```python
#!/usr/bin/env python3
"""
One-time script to extract and populate style_code for existing SAS products
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, '/Users/sas/Repos/SASKITUP')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kitup.settings')
django.setup()

from clubs.models_sas import SASProduct
from style_code_extraction_utils import extract_style_code
from django.db import transaction


def update_style_codes(dry_run=False):
    """Extract and update style codes for all products with short_description"""

    print("="*80)
    print("STYLE CODE UPDATE - EXISTING PRODUCTS")
    print("="*80)
    print()

    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be saved")
        print()

    # Get products with short_description
    products = SASProduct.objects.filter(
        short_description__isnull=False
    ).exclude(
        short_description=''
    ).select_related('club', 'club__sport')

    total = products.count()
    print(f"Found {total} products with short_description")
    print()

    updated = 0
    skipped = 0
    errors = 0

    print("-" * 80)
    print("Processing products...")
    print("-" * 80)

    with transaction.atomic():
        for idx, product in enumerate(products, 1):
            try:
                # Extract style code
                style_code = extract_style_code(product.short_description)

                if style_code:
                    # Check if style_code is different from current value
                    if product.style_code != style_code:
                        old_value = product.style_code or '(empty)'

                        if not dry_run:
                            product.style_code = style_code
                            product.save(update_fields=['style_code', 'updated_at'])

                        print(f"{idx}. {product.name}")
                        print(f"   Club: {product.club.name}")
                        print(f"   Old Style Code: {old_value}")
                        print(f"   New Style Code: {style_code}")
                        print(f"   Status: {'Would update' if dry_run else 'Updated'}")
                        print()

                        updated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1

            except Exception as e:
                errors += 1
                print(f"❌ Error processing product {product.id}: {str(e)}")
                print()

    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total products processed: {total}")
    print(f"Products updated: {updated}")
    print(f"Products skipped: {skipped}")
    print(f"Errors: {errors}")
    print()

    if dry_run:
        print("This was a DRY RUN - no changes were saved to the database")
        print("Run again without --dry-run to apply changes")
    else:
        print("✅ Update complete!")


if __name__ == '__main__':
    import sys

    dry_run = '--dry-run' in sys.argv

    update_style_codes(dry_run=dry_run)
```

**Run the script:**

```bash
# Dry run first to preview changes
source /Users/sas/Repos/SASKITUP/env/bin/activate
python update_existing_style_codes.py --dry-run

# Apply changes if preview looks good
python update_existing_style_codes.py
```

---

### Step 5: Update Admin Interface

**File:** `/Users/sas/Repos/SASKITUP/clubs/admin.py`

**Update SASProduct admin:**

```python
from django.contrib import admin
from clubs.models_sas import SASProduct, SASClub, SASSport

@admin.register(SASProduct)
class SASProductAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'club',
        'sku',
        'style_code',  # NEW
        'price',
        'stock_status',
        'is_active'
    ]

    list_filter = [
        'club__sport',
        'stock_status',
        'is_active'
    ]

    search_fields = [
        'name',
        'sku',
        'style_code',  # NEW
        'club__name',
        'club__sport__name'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('club', 'name', 'slug', 'woo_product_id')
        }),
        ('Product Identifiers', {
            'fields': ('sku', 'style_code')  # NEW: Grouped together
        }),
        ('Pricing', {
            'fields': ('price', 'regular_price', 'sale_price')
        }),
        ('Inventory', {
            'fields': ('stock_status', 'manage_stock', 'stock_quantity')
        }),
        ('Content', {
            'fields': ('description', 'short_description')
        }),
        ('Media', {
            'fields': ('image_url', 'gallery_urls')
        }),
        ('Status', {
            'fields': ('is_active', 'last_sync_at')
        }),
    )
```

---

## Testing Checklist

After implementation, test the following:

### 1. Migration Tests
- [ ] Migration runs successfully: `python manage.py migrate clubs`
- [ ] Database table has `style_code` column
- [ ] Index on `style_code` created

### 2. Sync Tests
```bash
# Test sync with small dataset
python manage.py sync_sas_clubs --sport-filter "Athletics" --dry-run

# Check if style_code is extracted
python manage.py sync_sas_clubs --sport-filter "Athletics"
```

- [ ] Products sync successfully
- [ ] `style_code` field populated from short_description
- [ ] `sku` field still populated from WooCommerce SKU (not overwritten)

### 3. Update Script Tests
```bash
# Dry run to preview
python update_existing_style_codes.py --dry-run

# Apply changes
python update_existing_style_codes.py
```

- [ ] Existing products get style_code populated
- [ ] No errors during update
- [ ] Correct count of updated products

### 4. Admin Interface Tests
- [ ] Open Django admin: http://localhost:8000/admin/clubs/sasproduct/
- [ ] `style_code` visible in list display
- [ ] Can search by style_code
- [ ] Can filter products

### 5. Data Validation
```python
# Django shell
python manage.py shell

from clubs.models_sas import SASProduct

# Check products with style_code
products = SASProduct.objects.exclude(style_code='')
print(f"Products with style_code: {products.count()}")

# Sample verification
sample = products.first()
print(f"Product: {sample.name}")
print(f"SKU: {sample.sku}")
print(f"Style Code: {sample.style_code}")
print(f"Short Desc: {sample.short_description[:100]}")
```

---

## Rollback Plan

If you need to rollback the changes:

### 1. Remove style_code Field

**Create reverse migration:**

```python
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('clubs', 'XXXX_add_style_code_to_sas_product'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='sasproduct',
            name='sas_prod_style_idx',
        ),
        migrations.RemoveField(
            model_name='sasproduct',
            name='style_code',
        ),
    ]
```

### 2. Revert Code Changes

```bash
git revert <commit-hash>
```

---

## Performance Considerations

### Database Impact:
- **Storage**: VARCHAR(100) per product (~100-500 bytes per row)
- **Index**: B-tree index on style_code (~5-10% table size increase)
- **Query Performance**: Minimal impact, indexed searches remain fast

### Sync Performance:
- **Extraction**: Regex parsing adds ~1-2ms per product
- **Total Impact**: Negligible for typical sync operations

---

## Future Enhancements

Once style_code field is implemented:

1. **API Endpoints**: Add style_code to product API responses
2. **Search Integration**: Add style_code to product search
3. **Reporting**: Create reports grouped by style_code
4. **Validation**: Add style_code format validation
5. **Barcode Support**: Extract and store barcode similarly

---

## Files Modified Summary

| File | Changes | Lines |
|------|---------|-------|
| `clubs/models_sas.py` | Add style_code field, index | ~430, ~502 |
| `clubs/migrations/XXXX_add_style_code.py` | Migration file | New |
| `clubs/management/commands/sync_sas_clubs.py` | Extract and save style_code | ~30, ~572, ~651 |
| `clubs/admin.py` | Update admin interface | N/A |
| `update_existing_style_codes.py` | One-time update script | New |

---

## Support

**Files Created:**
- `/Users/sas/Repos/SASKITUP/SKU_ANALYSIS_REPORT.md` - Full analysis
- `/Users/sas/Repos/SASKITUP/style_code_extraction_utils.py` - Extraction library
- `/Users/sas/Repos/SASKITUP/STYLE_CODE_IMPLEMENTATION_GUIDE.md` - This guide

**Utilities Available:**
- `check_sas_sku_data.py` - Database analysis script
- `check_existing_skus.py` - SKU verification script
- `style_code_extraction_utils.py` - Style code extraction with tests

---

**Last Updated:** 2025-10-05
**Django Expert:** Backend Development Team
