# Price Update Feature - Flexible Identifier Matching

**Date**: 2025-10-06
**Update**: Support for multiple identifier types (Code, Style Code, SKU, Barcode)

## Problem Statement

Products across different systems use different identifier types:
- **Wholesale**: `cin7_sku`, `cin7_barcode`
- **TUS/LOTTO**: `sku`
- **SAS**: `sku` + `style_code` (extracted from description)
- **Some products**: Only have barcode
- **Some products**: Only have style code

**Solution**: Single "Code" column in CSV that matches against ALL identifier fields.

---

## Updated CSV Format

### Single Identifier Column

```csv
Code,Product Name,Cost,75% Margin Price,Discount %,Retail Price
```

**"Code" column accepts ANY of these**:
- SKU (e.g., `ABC123`)
- Style Code (e.g., `JKT 1513 ROYAL`)
- Barcode (e.g., `9876543210`)
- Product Code (e.g., `US FLC 789`)

### Alternative Header Names

System recognizes these header variations:
- **Code**: `Product Code`, `SKU`, `Style Code`, `Barcode`, `Product Identifier`
- **Cost**: `Cost Price`, `Cost NZD Excl`, `Unit Cost`
- **75% Margin Price**: `Margin Price`, `RRP`, `WholesaleExGST NZD Excl`
- **Retail Price**: `Retail NZD Incl`, `Selling Price`, `Regular Price`, `Sale Price`

---

## Flexible Product Matching Strategy

### Multi-Field Search Algorithm

```python
def find_product_by_identifier(identifier, product_type):
    """
    Search product using single identifier across multiple fields

    Priority:
    1. sku (exact)
    2. sku (case-insensitive)
    3. style_code (exact) - SAS only
    4. style_code (case-insensitive) - SAS only
    5. barcode (exact) - if field exists
    6. barcode (case-insensitive)
    7. sku (partial/contains)
    8. name (exact)
    9. name (contains)
    """

    id_clean = identifier.strip()
    model = get_product_model(product_type)

    # 1. Exact SKU match
    product = model.objects.filter(sku=id_clean).first()
    if product:
        return product, "SKU (exact)"

    # 2. Case-insensitive SKU
    product = model.objects.filter(sku__iexact=id_clean).first()
    if product:
        return product, "SKU (case-insensitive)"

    # 3. SAS products: style_code field
    if product_type == 'sas' and hasattr(model, 'style_code'):
        product = model.objects.filter(style_code=id_clean).first()
        if product:
            return product, "Style Code (exact)"

        product = model.objects.filter(style_code__iexact=id_clean).first()
        if product:
            return product, "Style Code (case-insensitive)"

    # 4. Barcode (if field exists)
    if hasattr(model, 'barcode'):
        product = model.objects.filter(barcode=id_clean).first()
        if product:
            return product, "Barcode (exact)"

        product = model.objects.filter(barcode__iexact=id_clean).first()
        if product:
            return product, "Barcode (case-insensitive)"

    # Wholesale specific: cin7_barcode
    if product_type == 'wholesale' and hasattr(model, 'cin7_barcode'):
        product = model.objects.filter(cin7_barcode=id_clean).first()
        if product:
            return product, "CIN7 Barcode (exact)"

        product = model.objects.filter(cin7_barcode__iexact=id_clean).first()
        if product:
            return product, "CIN7 Barcode (case-insensitive)"

    # 5. Partial SKU match (for variations)
    product = model.objects.filter(sku__icontains=id_clean).first()
    if product:
        return product, "SKU (partial)"

    # 6. Name match (last resort)
    product = model.objects.filter(name__iexact=id_clean).first()
    if product:
        return product, "Name (exact)"

    product = model.objects.filter(name__icontains=id_clean).first()
    if product:
        return product, "Name (contains)"

    return None, None
```

---

## CSV Examples

### Example 1: SKU Identifiers
```csv
Code,Product Name,Cost,75% Margin Price,Discount %,Retail Price
ABC123,Navy Blazer Size 10,45.00,180.00,16.67,150.00
DEF456,Navy Blazer Size 12,45.00,180.00,16.67,150.00
```

### Example 2: Style Code Identifiers (SAS)
```csv
Code,Product Name,Cost,75% Margin Price,Discount %,Retail Price
JKT 1513 ROYAL,Royal Blue Jacket,25.00,100.00,15.00,85.00
JKT 1513 BLACK,Black Jacket,25.00,100.00,15.00,85.00
```

### Example 3: Barcode Identifiers
```csv
Code,Product Name,Cost,75% Margin Price,Discount %,Retail Price
9421001,Training Top Black,40.00,160.00,18.75,130.00
9421002,Training Top White,40.00,160.00,18.75,130.00
```

### Example 4: Mixed Identifiers (Single CSV)
```csv
Code,Product Name,Cost,75% Margin Price,Discount %,Retail Price
ABC123,Product with SKU,10.00,40.00,20.00,32.00
9876543210,Product with Barcode,15.00,60.00,10.00,54.00
JKT 1513,Product with Style Code,25.00,100.00,15.00,85.00
US FLC 789,Wholesale Product,50.00,200.00,12.50,175.00
```

**System automatically searches all identifier fields for each value.**

---

## Product Type Specific Identifiers

### TUS Products
- **Primary**: `sku` field
- **Fallback**: Product name

### SAS Products
- **Primary**: `sku` field
- **Secondary**: `style_code` field (extracted from short_description)
- **Fallback**: Product name

### LOTTO Products
- **Primary**: `sku` field
- **Fallback**: Product name

### Wholesale Products
- **Primary**: `cin7_sku` field
- **Secondary**: `cin7_barcode` field
- **Fallback**: Product name

---

## Implementation Requirements

### Model Updates

**Add to TUSProduct, SASProduct, LottoProduct**:
```python
# Optional barcode field for flexible matching
barcode = models.CharField(
    max_length=100,
    blank=True,
    null=True,
    db_index=True,
    help_text="Product barcode for CSV price updates"
)
```

**SAS already has**:
```python
style_code = models.CharField(
    max_length=100,
    blank=True,
    null=True,
    help_text="Product style code extracted from description"
)
```

### CSV Parser Updates

```python
def parse_csv_row(row, product_type):
    """
    Extract identifier from CSV row - accepts multiple header names
    """
    # Try all possible identifier column names
    identifier = (
        row.get('Code') or
        row.get('Product Code') or
        row.get('SKU') or
        row.get('Style Code') or
        row.get('Barcode') or
        row.get('Product Identifier')
    )

    if not identifier:
        raise ValueError("No product identifier found in CSV row")

    return identifier.strip()
```

### Preview API Updates

```python
def preview_price_update(csv_data, product_type):
    """
    Preview with flexible identifier matching
    """
    preview_items = []

    for row in csv_data:
        identifier = parse_csv_row(row, product_type)
        product, match_method = find_product_by_identifier(identifier, product_type)

        preview_items.append({
            'identifier': identifier,
            'product_found': product is not None,
            'match_method': match_method,  # Shows how product was found
            'product_name': product.name if product else 'Not Found',
            # ... other fields
        })

    return preview_items
```

---

## Benefits

1. **Flexibility**: Users can use ANY identifier type in CSV
2. **No Multiple Columns**: Single "Code" column instead of separate SKU/Barcode/StyleCode columns
3. **Backward Compatible**: Existing wholesale CSVs still work
4. **Robust Matching**: Multiple fallback strategies ensure products are found
5. **Clear Feedback**: Preview shows exactly how each product was matched

---

## Testing Scenarios

### Test Case 1: SKU Matching
```csv
Code,Product Name,Cost,Retail Price
ABC123,Test Product,10.00,40.00
```
Expected: Match by SKU (exact)

### Test Case 2: Style Code Matching (SAS)
```csv
Code,Product Name,Cost,Retail Price
JKT 1513 ROYAL,Royal Jacket,25.00,100.00
```
Expected: Match by Style Code (exact)

### Test Case 3: Barcode Matching
```csv
Code,Product Name,Cost,Retail Price
9876543210,Barcode Product,15.00,60.00
```
Expected: Match by Barcode (exact)

### Test Case 4: Case Insensitive
```csv
Code,Product Name,Cost,Retail Price
abc123,Lower Case SKU,10.00,40.00
```
Expected: Match by SKU (case-insensitive)

### Test Case 5: Partial Match
```csv
Code,Product Name,Cost,Retail Price
ABC,Partial SKU,10.00,40.00
```
Expected: Match by SKU (partial) if "ABC123" exists

### Test Case 6: Not Found
```csv
Code,Product Name,Cost,Retail Price
NOTFOUND123,Missing Product,10.00,40.00
```
Expected: No match, show warning in preview

---

## UI Updates

### Preview Table Updates

Show match method in preview:
```
| Status | Code      | Match Method        | Product Name  | Current | New  |
|--------|-----------|---------------------|---------------|---------|------|
| ✓      | ABC123    | SKU (exact)         | Test Product  | $32.00  | $40  |
| ✓      | JKT 1513  | Style Code (exact)  | Royal Jacket  | $85.00  | $100 |
| ⚠      | 9876543   | Barcode (partial)   | Bar Product   | $60.00  | $75  |
| ✗      | NOTFOUND  | Not found           | -             | -       | -    |
```

### Help Text Updates

```
CSV Format Help:
- Code column can contain: SKU, Style Code, Barcode, or Product Code
- System will automatically search all identifier fields
- Match method will be shown in preview
- Supported formats: .csv, .xlsx, .xls
```

---

## Implementation Files

**Backend**:
- `/Users/sas/Repos/SASKITUP/schools/services/product_matcher.py` (new)
- `/Users/sas/Repos/SASKITUP/schools/views.py` (update price_preview, price_apply)
- `/Users/sas/Repos/SASKITUP/clubs/models_tus.py` (add barcode field)
- `/Users/sas/Repos/SASKITUP/clubs/models_sas.py` (barcode field already has style_code)
- `/Users/sas/Repos/SASKITUP/clubs/models_lotto.py` (add barcode field)

**Frontend**:
- `/Users/sas/Repos/SASKITUP/schools/templates/schools/wholesale/price_update_settings.html`
- Update CSV format help text
- Update preview table to show match method

---

## Migration Plan

**Step 1**: Add barcode fields
```bash
python manage.py makemigrations clubs
python manage.py migrate clubs
```

**Step 2**: Create product matcher service

**Step 3**: Update price preview/apply views

**Step 4**: Update frontend templates

**Step 5**: Test with sample CSVs
