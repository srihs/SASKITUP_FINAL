# SKU vs Style Code - Visual Comparison

**Quick Reference Guide**

---

## The Difference

### SKU (Stock Keeping Unit)
- **Source:** WooCommerce `sku` field
- **Purpose:** Inventory tracking, unique product identifier
- **Format:** Usually numeric (e.g., "74706", "33656")
- **Current Status:** 5% populated (18/357 products)
- **Django Field:** `SASProduct.sku`

### Style Code
- **Source:** Extracted from WooCommerce `short_description` HTML
- **Purpose:** Product design/style identification
- **Format:** Alphanumeric with spaces (e.g., "JKT 605 REG AKA GRY")
- **Current Status:** Present in ~3-4% of products' descriptions
- **Django Field:** Not currently stored (optional enhancement)

---

## Side-by-Side Comparison

### Example 1: Product with BOTH SKU and Style Code

**Product:** Athletics Auckland Sun visor

| Field | Value | Where It Comes From |
|-------|-------|---------------------|
| **SKU** | `74706` | WooCommerce API → `product['sku']` |
| **Style Code** | `VISOR 4060 NAVY AKA` | WooCommerce API → `product['short_description']` (HTML) |

**WooCommerce API Response:**
```json
{
  "id": 27597,
  "name": "Athletics Auckland Staff and Team Managers Sun visor",
  "sku": "74706",  ← SKU field
  "short_description": "<p>Style Code &#8211; VISOR 4060 NAVY AKA<br />Sun visor with logo printed on the front</p>"
                                      ↑ Style Code in HTML
}
```

**Database Storage (Current):**
```python
product.sku = "74706"  # ✓ Stored
product.short_description = "<p>Style Code &#8211; VISOR 4060 NAVY AKA..."  # ✓ Stored
# Style Code NOT extracted (could be optional enhancement)
```

---

### Example 2: Product with Style Code but NO SKU

**Product:** Athletics Auckland Staff jacket

| Field | Value | Where It Comes From |
|-------|-------|---------------------|
| **SKU** | `(empty)` | WooCommerce API → `product['sku']` = "" |
| **Style Code** | `JKT 1513 ROYAL AKA` | WooCommerce API → `product['short_description']` (HTML) |

**WooCommerce API Response:**
```json
{
  "id": 27509,
  "name": "Athletics Auckland Staff and Team Managers jacket",
  "sku": "",  ← Empty SKU field
  "short_description": "<p>Style Code &#8211; JKT 1513 ROYAL AKA<br />Royal jacket with logos</p>"
                                      ↑ Style Code in HTML
}
```

**Database Storage (Current):**
```python
product.sku = ""  # ✓ Stored (but empty)
product.short_description = "<p>Style Code &#8211; JKT 1513 ROYAL AKA..."  # ✓ Stored
# Style Code NOT extracted (could be optional enhancement)
```

---

### Example 3: Product with NEITHER SKU nor Style Code

**Product:** Tamaki Lightning Royal blue tee

| Field | Value | Where It Comes From |
|-------|-------|---------------------|
| **SKU** | `(empty)` | WooCommerce API → `product['sku']` = "" |
| **Style Code** | `(none)` | Not present in `short_description` |

**WooCommerce API Response:**
```json
{
  "id": 7699,
  "name": "Tamaki Lightning Royal blue long sleeve tee",
  "sku": "",  ← Empty SKU field
  "short_description": "<p>Tamaki Lightening Royal blue long sleeve tee with club HT on front.</p>"
                             ↑ No Style Code mentioned
}
```

**Database Storage (Current):**
```python
product.sku = ""  # ✓ Stored (but empty)
product.short_description = "<p>Tamaki Lightening Royal blue..."  # ✓ Stored
# No Style Code to extract
```

---

## Visual Data Flow

### Current Sync Process (Correct)

```
WooCommerce API
     │
     ├─── product['sku'] ────────────────────────► SASProduct.sku
     │                                              (stored as-is)
     │
     └─── product['short_description'] ──────────► SASProduct.short_description
                                                    (stored as HTML)

                                                    Style Code (if present)
                                                    is INSIDE the HTML
                                                    but NOT extracted
```

### Optional Enhancement (Add style_code field)

```
WooCommerce API
     │
     ├─── product['sku'] ────────────────────────► SASProduct.sku
     │                                              (stored as-is)
     │
     ├─── product['short_description'] ──────────► SASProduct.short_description
     │                                              (stored as HTML)
     │
     └─── product['short_description'] ──────────► extract_style_code()
                    ↓                                      ↓
          Parse HTML & Extract                    SASProduct.style_code
          "Style Code – XXX"                      (stored separately)
```

---

## HTML Extraction Examples

### Style Code HTML Patterns

**Pattern 1: HTML Entity Dash**
```html
<p>Style Code &#8211; JKT 605 REG AKA GRY</p>
```
**Extracted:** `JKT 605 REG AKA GRY`

**Pattern 2: Em Dash Character**
```html
<p>Style Code – POLO 01 LSCF CL AKA NVY</p>
```
**Extracted:** `POLO 01 LSCF CL AKA NVY`

**Pattern 3: Regular Hyphen**
```html
<p>Style Code - CAP U15618 NAVY AKA</p>
```
**Extracted:** `CAP U15618 NAVY AKA`

**Pattern 4: Lowercase "code"**
```html
<p>Style code &#8211; USO BEANIE BLK TNZ</p>
```
**Extracted:** `USO BEANIE BLK TNZ`

**Pattern 5: Numeric Only**
```html
<p>Style Code &#8211; 4078</p>
```
**Extracted:** `4078`

---

## Distribution Statistics

### SKU Field Population

```
Total Products: 357
├─ With SKU:    18 (5.0%)  ███
└─ Without SKU: 339 (95.0%) ███████████████████████████████████████████████████
```

### Style Code in short_description

```
Total Products: 357
├─ With Style Code: ~12 (3.4%)  ██
└─ Without:         ~345 (96.6%) ████████████████████████████████████████████████
```

### Overlap Analysis

```
Products with SKU ONLY:        ~6 products   (Both fields different values)
Products with Style Code ONLY: ~6 products   (SKU empty, Style Code in HTML)
Products with BOTH:            ~12 products  (SKU populated, Style Code in HTML)
Products with NEITHER:         ~333 products (Most common - neither field populated)
```

---

## Data Integrity Rules

### Current Rules (Enforced)

✅ **Rule 1:** SKU comes from WooCommerce `sku` field ONLY
✅ **Rule 2:** short_description stores HTML as-is from WooCommerce
✅ **Rule 3:** No extraction or parsing during sync (correct behavior)

### Proposed Rules (If Adding style_code Field)

✅ **Rule 1:** SKU comes from WooCommerce `sku` field (unchanged)
✅ **Rule 2:** short_description stores HTML as-is (unchanged)
✅ **Rule 3:** style_code extracted from short_description HTML (new)
✅ **Rule 4:** SKU ≠ Style Code (separate identifiers, separate purposes)
✅ **Rule 5:** If Style Code not found, leave field empty (don't copy from SKU)

---

## Use Cases

### When to Use SKU

- **Inventory Management:** Track stock levels
- **Order Processing:** Link orders to specific products
- **Barcode Scanning:** Unique identifier for POS systems
- **Integration:** Connect with external inventory systems

### When to Use Style Code

- **Product Categorization:** Group similar designs
- **Design Reference:** Identify product style/variant
- **Manufacturing:** Link to production specifications
- **Customer Service:** Help identify products by design code

---

## Quick Decision Guide

### Should I Extract Style Code?

**✅ YES, if you need to:**
- Search products by Style Code
- Group products by design/style
- Generate reports by Style Code
- Provide Style Code in customer-facing interfaces

**❌ NO, if:**
- You only need inventory tracking (use SKU)
- WooCommerce will populate SKU field soon
- Style Code information not used in business logic
- Minimizing database fields is priority

---

## FAQ

### Q: Can I use Style Code as SKU if SKU is empty?

**A:** **NO** - Style Code and SKU serve different purposes. Keep them separate.

**Why?**
- Style Code format incompatible with inventory systems (has spaces)
- Multiple products may share same Style Code (different sizes/colors)
- SKU should be unique per variant

---

### Q: Why are SKUs mostly empty?

**A:** WooCommerce administrators have not populated the SKU field in WooCommerce.

**Solution:** Contact WooCommerce admin to populate SKU field for all products.

---

### Q: Is the sync process broken?

**A:** **NO** - Sync process is working correctly.

**Evidence:**
- Products with SKU in WooCommerce → SKU stored in database ✓
- Products without SKU in WooCommerce → Empty string in database ✓
- All API responses verified

---

### Q: Should I modify the sync to extract SKU from short_description?

**A:** **NO** - Don't extract Style Code as SKU.

**Instead:**
1. Option A: Request SKU population in WooCommerce (recommended)
2. Option B: Add separate `style_code` field (optional enhancement)

---

## File Locations

| File | Purpose |
|------|---------|
| `/Users/sas/Repos/SASKITUP/clubs/models_sas.py` | Model definition (line 429: sku field) |
| `/Users/sas/Repos/SASKITUP/clubs/management/commands/sync_sas_clubs.py` | Sync logic (line 583: sku mapping) |
| `/Users/sas/Repos/SASKITUP/style_code_extraction_utils.py` | Style Code extraction library |
| `/Users/sas/Repos/SASKITUP/SKU_ANALYSIS_REPORT.md` | Full technical analysis |
| `/Users/sas/Repos/SASKITUP/STYLE_CODE_IMPLEMENTATION_GUIDE.md` | Implementation guide for style_code field |

---

**Last Updated:** 2025-10-05
