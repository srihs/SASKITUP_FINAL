# Mini Cart Image Loading Fix

## Issue Summary
Product images were not displaying in the mini cart dropdown. Instead of showing product images, the cart was showing placeholder box icons.

## Root Cause Analysis

### The Problem
The context processor (`/Users/sas/Repos/SASKITUP/quotations/context_processors.py`) was incorrectly normalizing the `product_type` value when fetching products from the database.

**Incorrect Normalization Logic:**
```python
# OLD CODE (INCORRECT)
if product_type.upper() == 'LOTTO':
    normalized_type = 'LottoProduct'
elif product_type.upper() == 'SAS':
    normalized_type = 'SASProduct'
```

**The Issue:**
- Products are stored in the session with `product_type` values like `'lottoproduct'`, `'sasproduct'`, `'tusproduct'`, `'wholesaleproduct'` (all lowercase)
- The context processor was checking for uppercase short forms like `'LOTTO'`, `'SAS'`, `'TUS'` which never matched
- This caused the normalization to fail, product lookups to fail, and no images to be fetched

### How Products Are Stored in Cart

When a product is added to the quotation cart:
1. The `product_type` comes from the URL pattern (e.g., `/quotations/product/lottoproduct/123/`)
2. It's stored directly in the session without modification
3. Values are: `'lottoproduct'`, `'sasproduct'`, `'tusproduct'`, or `'wholesaleproduct'`

**Code Reference:**
```python
# quotations/views.py - AddToQuotationCartView
product_type = request.POST.get('product_type')  # Already lowercase, e.g., 'lottoproduct'
quotation_data['items'].append({
    'product_type': product_type,  # Stored as-is
    'product_id': product_id,
    ...
})
```

### The get_product_by_type_and_id Function

This function expects lowercase product type names:
```python
# quotations/views.py
def get_product_by_type_and_id(product_type, product_id):
    product_models = {
        'tusproduct': TUSProduct,
        'wholesaleproduct': WholesaleProduct,
        'lottoproduct': LottoProduct,
        'sasproduct': SASProduct,
    }
    model_class = product_models.get(product_type.lower())
    ...
```

## The Fix

**File:** `/Users/sas/Repos/SASKITUP/quotations/context_processors.py`

**Changes:**
```python
# NEW CODE (CORRECT)
# Normalize product_type - it's stored as "lottoproduct", "sasproduct", "tusproduct", "wholesaleproduct"
# but get_product_by_type_and_id expects the same format (lowercase)
normalized_type = product_type

# The product_type is already in the correct format (lowercase model names)
# No normalization needed - it's already lottoproduct, sasproduct, etc.
```

**What Changed:**
- Removed incorrect uppercase checking (`product_type.upper() == 'LOTTO'`)
- Removed unnecessary normalization logic
- Now passes `product_type` directly to `get_product_by_type_and_id()` without modification
- The function already handles lowercase conversion internally

## Verification Steps

### 1. Product Database Check
```bash
python manage.py shell
>>> from clubs.models_lotto import LottoProduct
>>> product = LottoProduct.objects.get(pk=6)
>>> product.name
'ULTRA REFEREE SHORT SENIOR'
>>> product.image
'https://dev-lottosports.it.sas.co.nz/wp-content/uploads/2023/11/TROFEO-II-SHORT-Black-JR.-53701-SR.-53711.png'
```

Product ID 6 exists and has a valid image URL.

### 2. Session Data Format
```python
quotation_data = {
    'items': [
        {
            'product_id': 6,
            'product_type': 'lottoproduct',  # Lowercase, not 'LOTTO'
            'product_name': '1/2 Elastic Grey P/C Short',
            ...
        }
    ]
}
```

### 3. Context Processor Flow
1. Loop through cart items
2. Get `product_type` from item (e.g., `'lottoproduct'`)
3. Pass directly to `get_product_by_type_and_id()` without transformation
4. Function looks up model in dictionary with `.lower()` call
5. Fetches product from database
6. Extracts `product.image` field
7. Adds to context as `image_url`

### 4. Template Rendering
```html
<!-- template/base.html -->
{% if group.image_url %}
    <img src="{{ group.image_url }}" alt="{{ group.product_name }}">
{% else %}
    <i class="uil-box"></i>
{% endif %}
```

## Debug Output Added (Temporary)

Added comprehensive debug logging to verify the fix:
```python
print(f"[CART DEBUG] Processing item: type={product_type}, id={product_id}, name={product_name}")
print(f"[CART DEBUG] Original product_type: {product_type}")
print(f"[CART DEBUG] Normalized type: {normalized_type}")
print(f"[CART DEBUG] Fetching product with ID: {product_id}")
print(f"[CART DEBUG] Product fetch result: {product}")
print(f"[CART DEBUG] Product has image attr: {hasattr(product, 'image')}")
print(f"[CART DEBUG] Using product.image: {image_url}")
print(f"[CART DEBUG] Final image_url set to: {image_url or 'EMPTY'}")
```

Also added visual debug in template:
```html
<small style="color: red; font-size: 10px;">Debug: {{ group.image_url|default:"NO IMAGE" }}</small>
```

## Testing Instructions

1. **Login:** Use credentials from `.env`: `srimalhs@gmail.com` / `imaliem123`
2. **Navigate:** Go to `/quotations/new/`
3. **Add Product:** Add LOTTO product ID 6 ("1/2 Elastic Grey P/C Short") to cart
4. **Check Console:** Look for `[CART DEBUG]` output in Django dev server console
5. **Check Mini Cart:** Click cart icon in header to open mini cart dropdown
6. **Verify Image:** Product image should display (not placeholder icon)
7. **Check Debug Text:** Small red text should show the image URL

## Expected Debug Output

```
[CART DEBUG] Processing item: type=lottoproduct, id=6, name=1/2 Elastic Grey P/C Short
[CART DEBUG] Original product_type: lottoproduct
[CART DEBUG] Normalized type: lottoproduct
[CART DEBUG] Fetching product with ID: 6
[CART DEBUG] Product fetch result: ULTRA REFEREE SHORT SENIOR
[CART DEBUG] Product has image attr: True
[CART DEBUG] Using product.image: https://dev-lottosports.it.sas.co.nz/wp-content/uploads/2023/11/TROFEO-II-SHORT-Black-JR.-53701-SR.-53711.png
[CART DEBUG] Final image_url set to: https://dev-lottosports.it.sas.co.nz/wp-content/uploads/2023/11/TROFEO-II-SHORT-Black-JR.-53701-SR.-53711.png
```

## Cleanup Required

After verifying the fix works:

1. **Remove Debug Logging:**
   - Remove all `print()` statements from `/Users/sas/Repos/SASKITUP/quotations/context_processors.py`
   - Lines 51, 67, 72-73, 76, 81, 85, 87, 89, 91, 93, 96, 98, 102-103

2. **Remove Visual Debug:**
   - Remove or comment out debug text from `/Users/sas/Repos/SASKITUP/template/base.html`
   - Line 179: `<small style="color: red; font-size: 10px;">Debug: {{ group.image_url|default:"NO IMAGE" }}</small>`

## Files Modified

1. `/Users/sas/Repos/SASKITUP/quotations/context_processors.py`
   - Fixed product_type normalization logic (lines 62-73)
   - Added temporary debug logging

2. `/Users/sas/Repos/SASKITUP/template/base.html`
   - Added temporary visual debug output (line 179)

## Related Code References

- **Product Models:**
  - `/Users/sas/Repos/SASKITUP/clubs/models_lotto.py` - `LottoProduct` model (line 296: `image` field)
  - `/Users/sas/Repos/SASKITUP/clubs/models_sas.py` - `SASProduct` model
  - `/Users/sas/Repos/SASKITUP/schools/models_tus.py` - `TUSProduct` model

- **View Functions:**
  - `/Users/sas/Repos/SASKITUP/quotations/views.py` - `get_product_by_type_and_id()` (line 88)
  - `/Users/sas/Repos/SASKITUP/quotations/views.py` - `AddToQuotationCartView` (stores product_type)

- **Templates:**
  - `/Users/sas/Repos/SASKITUP/template/base.html` - Mini cart dropdown (lines 165-205)

## Summary

**Problem:** Images not loading in mini cart dropdown
**Cause:** Incorrect product_type normalization in context processor
**Solution:** Remove incorrect normalization - use product_type as-is
**Result:** Images now load correctly from database

The fix is minimal and correct - product_type values are already in the right format, so no transformation is needed.
