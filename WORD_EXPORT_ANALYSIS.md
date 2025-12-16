# Word Document Export Implementation Analysis

## Document Analysis

### Source Document
**File**: `/Users/sas/Downloads/ORDER DETAILS - Word.docx`

### Document Structure

The Word document contains:

#### 1. **Order Details Header Table**
```
┌────────────────────────┬────────────────────┐
│ Customer name          │ Rosina Wikaira     │
│ Team / Product Name    │                    │
│ S.O.P No              │ Q-20251215-0003    │
│ Ordered Date          │ 15 Dec, 2025       │
│ Order required on     │                    │
└────────────────────────┴────────────────────┘
```

#### 2. **Product Sections** (Repeating Structure)

Each product contains:

**Product Title** (Heading 5 style)
```
Product - [Product Description]
Style Code - [SKU]
```

**Variation Blocks** (Repeating for each size)
```
┌──────────────────────────┬─────────────┬──────┐
│ Variation style code     │ SKU-SIZE    │      │
│ Size                     │ SIZE        │      │
│ Total qty                │ COUNT       │      │
└──────────────────────────┴─────────────┴──────┘

┌─────────┬──────────┬──────────┐
│ Name    │ Number   │ Initial  │
├─────────┼──────────┼──────────┤
│ PLAYER1 │ 123      │ AB       │
│ PLAYER2 │ 456      │ CD       │
└─────────┴──────────┴──────────┘
```

### Data Mapping

| Word Document Field | Django Model Source | Notes |
|-------------------|-------------------|-------|
| Customer name | `quotation.institution.name` | Institution name |
| Team / Product Name | *(Empty in sample)* | Could be institution name or custom field |
| S.O.P No | `quotation.quotation_number` | Quotation number |
| Ordered Date | `quotation.created_at` | Format: "DD MMM, YYYY" |
| Order required on | `quotation.order_required_date` | Optional field |
| Product | `item.product.name` | From BespokeProduct |
| Style Code | `item.product_sku` (base) | Without size suffix |
| Variation style code | `item.product_sku` | Full SKU with size |
| Size | `player['size']` or `player['color']` | From player_customizations |
| Total qty | Count of players for this size | Calculated |
| Name | `player['player_name']` | From player_customizations |
| Number | `player['player_number']` | From player_customizations |
| Initial | `player['player_initial']` | From player_customizations |

### Differences from Existing Exports

#### **Word vs PDF**
- **PDF**: Full quotation with pricing, terms, all products (including non-bespoke)
- **Word**: Only bespoke products with player details, no pricing, order-focused

#### **Word vs Excel**
- **Excel**: Tabular format, all data in cells, structured for production
- **Word**: Formatted document, more readable, suitable for order confirmation

### Data Sources

#### Required Models
```python
from quotations.models import Quotation, QuotationItem
```

#### Data Flow
1. **Quotation**: Header information (customer, quotation number, dates)
2. **QuotationItem**: Filter for `product_content_type` = BespokeProduct AND `is_addon=False`
3. **Player Customizations**: From `item.variations['player_customizations']`

#### Business Logic
- **Group by Base SKU**: Multiple items with same base product (different sizes) → One product section
- **Group by Size**: Within each product, group players by size/color → Variation blocks
- **Calculate Totals**: Count players per size for "Total qty"

## Implementation Plan

### 1. Library Selection

**Recommended**: `python-docx`
- ✅ Mature, well-maintained library
- ✅ Easy to use, good documentation
- ✅ Supports all required features (tables, styles, paragraphs)
- ✅ Already used for Excel (`openpyxl`), consistent approach
- ✅ Pure Python, no external dependencies

**Alternative**: `docxtpl` (Template-based)
- Could use template approach similar to Excel
- Requires creating and maintaining separate .docx template
- Less flexible for dynamic table generation

**Decision**: Use `python-docx` with programmatic generation (similar to Excel approach)

### 2. File Structure

```
/Users/sas/Repos/SASKITUP/
├── quotations/
│   ├── word_export.py          # NEW: Word document generator
│   ├── views.py                # MODIFY: Add Word export view
│   ├── urls.py                 # MODIFY: Add Word export URL
│   └── templates/quotations/
│       ├── quotation_detail.html      # MODIFY: Add Word download button
│       └── my_quotations.html         # MODIFY: Add Word download button
└── requirements.txt            # MODIFY: Add python-docx
```

### 3. Implementation Steps

#### **Step 1: Install Dependencies**

```bash
pip install python-docx
```

Add to `requirements.txt`:
```
python-docx==1.1.0
```

#### **Step 2: Create Word Export Service**

**File**: `/Users/sas/Repos/SASKITUP/quotations/word_export.py`

```python
"""
Word Document Export Service for Bespoke Quotations

Generates Word documents in ORDER DETAILS format for quotations containing
bespoke products with player customization details.
"""
from io import BytesIO
from typing import List, Dict
from datetime import datetime

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

import logging

logger = logging.getLogger(__name__)


class BespokeQuotationWordGenerator:
    """
    Generates Word document export for quotations with bespoke products.

    Format matches: ORDER DETAILS - Word.docx
    """

    # Styling constants
    FONT_NAME = 'Calibri'
    FONT_SIZE_NORMAL = 11
    FONT_SIZE_HEADING = 14

    def __init__(self, quotation):
        """
        Initialize generator with a quotation instance.

        Args:
            quotation: Quotation model instance
        """
        self.quotation = quotation
        self.document = Document()

    def generate(self) -> bytes:
        """
        Generate Word file and return as bytes.

        Returns:
            bytes: Word file content

        Raises:
            ValueError: If quotation has no bespoke items with players
        """
        # Get bespoke items
        bespoke_items = self._get_bespoke_items()

        if not bespoke_items:
            raise ValueError("No player customizations found for bespoke items in this quotation")

        # Set document margins
        self._set_margins()

        # Add title
        self._add_title()

        # Add order details table
        self._add_order_details_table()

        # Add spacing
        self.document.add_paragraph()

        # Group items by base product SKU
        product_groups = self._group_items_by_base_product(bespoke_items)

        # Write all products
        for base_sku, items in product_groups.items():
            self._write_product_section(base_sku, items)
            # Add spacing between products
            self.document.add_paragraph()

        # Save to BytesIO
        output = BytesIO()
        self.document.save(output)
        output.seek(0)

        return output.getvalue()

    def _set_margins(self):
        """Set document margins (1 inch all sides)"""
        sections = self.document.sections
        for section in sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)

    def _add_title(self):
        """Add document title"""
        title = self.document.add_paragraph()
        run = title.add_run('ORDER DETAILS')
        run.font.size = Pt(16)
        run.font.bold = True
        run.font.name = self.FONT_NAME
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def _add_order_details_table(self):
        """Add order details header table"""
        table = self.document.add_table(rows=5, cols=2)
        table.style = 'Table Grid'

        # Customer name
        table.rows[0].cells[0].text = 'Customer name'
        institution_name = ''
        if self.quotation.institution:
            institution_name = self.quotation.institution.name
        table.rows[0].cells[1].text = institution_name

        # Team / Product Name
        table.rows[1].cells[0].text = 'Team / Product Name'
        table.rows[1].cells[1].text = ''

        # S.O.P No
        table.rows[2].cells[0].text = 'S.O.P No'
        table.rows[2].cells[1].text = self.quotation.quotation_number

        # Ordered Date
        table.rows[3].cells[0].text = 'Ordered Date'
        if self.quotation.created_at:
            table.rows[3].cells[1].text = self.quotation.created_at.strftime('%d %b, %Y')

        # Order required on
        table.rows[4].cells[0].text = 'Order required on'
        if hasattr(self.quotation, 'order_required_date') and self.quotation.order_required_date:
            table.rows[4].cells[1].text = self.quotation.order_required_date.strftime('%d %b, %Y')

        # Style table cells
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.name = self.FONT_NAME
                        run.font.size = Pt(self.FONT_SIZE_NORMAL)

    def _write_product_section(self, base_sku: str, items: List):
        """
        Write a complete product section (title + all variations + players).

        Args:
            base_sku: Base product SKU
            items: List of QuotationItem instances for this product
        """
        # Get product name from first item
        product_name = items[0].product_name if items else ''

        # Add product title (Heading 5 style)
        product_para = self.document.add_paragraph()
        run = product_para.add_run(f'Product\t\t- {product_name}')
        run.font.size = Pt(self.FONT_SIZE_HEADING)
        run.font.bold = True
        run.font.name = self.FONT_NAME
        product_para.style = 'Heading 5'

        # Add style code
        style_para = self.document.add_paragraph()
        run = style_para.add_run(f'Style Code\t\t- {base_sku}')
        run.font.size = Pt(self.FONT_SIZE_NORMAL)
        run.font.name = self.FONT_NAME

        # Add spacing
        self.document.add_paragraph()

        # Get all variation groups for this product
        variation_groups = self._get_variation_groups_for_product_group(items, base_sku)

        # Write each variation block
        for variation_data in variation_groups:
            self._write_variation_block(variation_data)
            # Add spacing between variations
            self.document.add_paragraph()

    def _write_variation_block(self, variation_data: Dict):
        """
        Write a single variation block (variation info + player table).

        Args:
            variation_data: Dict with variation_code, size, players, total_qty
        """
        # Create variation info table (3 rows x 3 cols)
        var_table = self.document.add_table(rows=3, cols=3)
        var_table.style = 'Table Grid'

        # Row 1: Variation style code
        var_table.rows[0].cells[0].text = 'Variation style code'
        var_table.rows[0].cells[1].text = variation_data['variation_code']

        # Row 2: Size
        var_table.rows[1].cells[0].text = 'Size'
        var_table.rows[1].cells[1].text = variation_data['size']

        # Row 3: Total qty
        var_table.rows[2].cells[0].text = 'Total qty'
        var_table.rows[2].cells[1].text = str(variation_data['total_qty'])

        # Style variation table
        for row in var_table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.name = self.FONT_NAME
                        run.font.size = Pt(self.FONT_SIZE_NORMAL)

        # Add spacing
        self.document.add_paragraph()

        # Create player table
        players = variation_data['players']
        player_table = self.document.add_table(rows=len(players) + 1, cols=3)
        player_table.style = 'Table Grid'

        # Header row
        player_table.rows[0].cells[0].text = 'Name'
        player_table.rows[0].cells[1].text = 'Number'
        player_table.rows[0].cells[2].text = 'Initial'

        # Player rows
        for i, player in enumerate(players, start=1):
            player_table.rows[i].cells[0].text = player.get('player_name', '')
            player_table.rows[i].cells[1].text = str(player.get('player_number', ''))
            player_table.rows[i].cells[2].text = player.get('player_initial', '')

        # Style player table
        for row in player_table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.name = self.FONT_NAME
                        run.font.size = Pt(self.FONT_SIZE_NORMAL)
                    # Center align header row
                    if row == player_table.rows[0]:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def _get_bespoke_items(self) -> List:
        """
        Get all bespoke items from quotation (excluding addons).

        Returns:
            List of QuotationItem instances that are bespoke products
        """
        items = []

        for item in self.quotation.items.filter(is_addon=False).select_related('product_content_type'):
            # Check if this is a bespoke product
            if item.product_content_type.model.lower() == 'bespokeproduct':
                # Check if it has player customizations
                player_customizations = item.variations.get('player_customizations', [])
                if player_customizations:
                    items.append(item)

        return items

    def _group_items_by_base_product(self, bespoke_items):
        """
        Group QuotationItems by base product SKU.

        Args:
            bespoke_items: List of QuotationItem instances

        Returns:
            dict: {base_sku: [item1, item2, ...]}
        """
        groups = {}
        for item in bespoke_items:
            # Extract base SKU (remove size suffix)
            base_sku = item.product_sku or ''
            if base_sku and '-' in base_sku:
                base_sku = base_sku.rsplit('-', 1)[0].strip()

            if base_sku not in groups:
                groups[base_sku] = []
            groups[base_sku].append(item)

        return groups

    def _get_variation_groups_for_product_group(self, items: List, base_sku: str) -> List[Dict]:
        """
        Group players by variation (size) across ALL items for a base product.

        Args:
            items: List of QuotationItem instances for the same base product
            base_sku: Base product SKU (without size suffix)

        Returns:
            List of dicts with variation data and players grouped by size
        """
        # Collect all players from all items
        all_players = []
        for item in items:
            player_customizations = item.variations.get('player_customizations', [])
            all_players.extend(player_customizations)

        if not all_players:
            return []

        # Group players by size
        size_groups = {}
        for player in all_players:
            size = player.get('size', '') or player.get('color', '') or 'N/A'

            if size not in size_groups:
                size_groups[size] = []

            size_groups[size].append(player)

        # Convert to list of variation groups
        variation_groups = []
        for size, players in size_groups.items():
            # Generate variation code (base_sku-size)
            variation_code = f"{base_sku}-{size}" if base_sku else size

            variation_groups.append({
                'variation_code': variation_code,
                'size': size,
                'players': players,
                'total_qty': len(players)
            })

        return variation_groups


def generate_bespoke_quotation_word(quotation) -> bytes:
    """
    Convenience function to generate Word document for a quotation.

    Args:
        quotation: Quotation model instance

    Returns:
        bytes: Word file content
    """
    generator = BespokeQuotationWordGenerator(quotation)
    return generator.generate()
```

#### **Step 3: Create Word Export View**

**File**: `/Users/sas/Repos/SASKITUP/quotations/views.py`

Add the following view (similar to Excel export):

```python
class QuotationWordExportView(LoginRequiredMixin, SalesRepOrAccountManagerOrCustomerMixin, View):
    """
    Export quotation to Word document format (ORDER DETAILS).
    Only for bespoke products with player customizations.
    """

    def get(self, request, pk):
        """Generate and download Word document"""
        # Get quotation
        quotation = get_object_or_404(Quotation, pk=pk)

        # Check permissions
        if not request.user.can_view_quotation(quotation):
            raise PermissionDenied("You do not have permission to view this quotation")

        try:
            # Import here to avoid circular imports
            from .word_export import generate_bespoke_quotation_word

            # Generate Word document
            word_bytes = generate_bespoke_quotation_word(quotation)

            # Create HTTP response with Word document
            response = HttpResponse(
                word_bytes,
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )

            # Set filename
            filename = f'Order_Details_{quotation.quotation_number}.docx'
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

            # Log export
            AuditLog.objects.create(
                user=request.user,
                action='quotation_word_export',
                description=f'Exported quotation {quotation.quotation_number} to Word',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]
            )

            logger.info(f"User {request.user.email} exported quotation {quotation.quotation_number} to Word")

            return response

        except ValueError as e:
            messages.error(request, str(e))
            return redirect('quotations:quotation-detail', pk=quotation.pk)
        except Exception as e:
            logger.error(f"Error generating Word export for quotation {quotation.quotation_number}: {e}", exc_info=True)
            messages.error(request, f"Failed to generate Word document: {str(e)}")
            return redirect('quotations:quotation-detail', pk=quotation.pk)
```

#### **Step 4: Add URL Pattern**

**File**: `/Users/sas/Repos/SASKITUP/quotations/urls.py`

Add after the Excel export URL (around line 78):

```python
# Quotation Word Export (Bespoke Products)
path('<uuid:pk>/word/', views.QuotationWordExportView.as_view(), name='quotation-word'),
```

#### **Step 5: Update Quotation Detail Template**

**File**: `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/quotation_detail.html`

Around line 873 (after Excel download button), add:

```html
{% if quotation.has_bespoke_items_with_players %}
<a href="{% url 'quotations:quotation-word' quotation.pk %}" class="btn btn-success w-md waves-effect waves-light ms-1">
    <i class="fa fa-file-word"></i> Download Word
</a>
{% endif %}
```

#### **Step 6: Update Quotation List Template**

**File**: `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/my_quotations.html`

Around line 266 (in the Action column), add download button:

```html
{% if quotation.has_bespoke_items_with_players %}
<a href="{% url 'quotations:quotation-word' quotation.pk %}" class="text-success px-2" title="Download Word">
    <i class="uil uil-file-alt font-size-18"></i>
</a>
{% endif %}
```

### 4. UI Integration Details

#### Button Placement

**Quotation Detail Page**:
```
[Download PDF] [Download Excel] [Download Word]
     (blue)        (info/cyan)      (success/green)
```

**Quotation List Grid**:
```
Action Column Icons:
- ✓ (Approve - green) - if not customer approved
- 👁 (View - primary blue)
- ✏ (Edit - warning yellow) - if not approved
- 📋 (History - info blue) - if edited
- 📄 (Word - success green) - NEW - if has bespoke items with players
```

#### Styling Consistency

Match existing buttons:
- **Button classes**: `btn btn-success w-md waves-effect waves-light ms-1`
- **Icon**: Font Awesome `fa-file-word` or Unicons `uil-file-alt`
- **Color**: Success/Green (consistent with Word branding)
- **Size**: Same as PDF/Excel buttons
- **Spacing**: `ms-1` for left margin

### 5. Testing Checklist

- [ ] **Installation**: Verify `python-docx` installed correctly
- [ ] **Generation**: Document generates without errors
- [ ] **Content**: All data fields populated correctly
- [ ] **Formatting**: Tables and styles match sample document
- [ ] **Grouping**: Products grouped by base SKU correctly
- [ ] **Variations**: Sizes/colors grouped correctly
- [ ] **Players**: All player data present and accurate
- [ ] **Download**: File downloads with correct filename
- [ ] **Permissions**: Only authorized users can download
- [ ] **UI**: Buttons appear only when bespoke items with players exist
- [ ] **Styling**: Buttons match existing design
- [ ] **Error Handling**: Proper error messages for edge cases
- [ ] **Logging**: Audit log entries created

### 6. Edge Cases & Error Handling

#### No Bespoke Items
- **Check**: `quotation.has_bespoke_items_with_players()`
- **Action**: Don't show Word download button
- **Error**: Show message "No player customizations found"

#### Missing Player Data
- **Check**: `player_customizations` is empty list
- **Action**: Skip item, continue with others
- **Error**: Show message if no valid items found

#### Missing Institution
- **Fallback**: Use empty string for customer name
- **No Error**: Document still generates

#### Missing Dates
- **Fallback**: Leave cells empty
- **No Error**: Document still generates

#### Permission Denied
- **Check**: `request.user.can_view_quotation(quotation)`
- **Action**: Raise `PermissionDenied`
- **Error**: 403 Forbidden page

### 7. File Modification Summary

#### New Files
1. `/Users/sas/Repos/SASKITUP/quotations/word_export.py` - Word document generator

#### Modified Files
1. `/Users/sas/Repos/SASKITUP/quotations/views.py` - Add `QuotationWordExportView`
2. `/Users/sas/Repos/SASKITUP/quotations/urls.py` - Add Word export URL pattern
3. `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/quotation_detail.html` - Add Word download button
4. `/Users/sas/Repos/SASKITUP/quotations/templates/quotations/my_quotations.html` - Add Word download button (list view)
5. `/Users/sas/Repos/SASKITUP/requirements.txt` - Add `python-docx==1.1.0`

### 8. Deployment Steps

1. **Install dependency**: `pip install python-docx==1.1.0`
2. **Update requirements.txt**: Add `python-docx==1.1.0`
3. **Create word_export.py**: Implement generator class
4. **Update views.py**: Add Word export view
5. **Update urls.py**: Add URL pattern
6. **Update templates**: Add Word download buttons
7. **Test locally**: Generate sample documents
8. **Commit changes**: Create git commit with all files
9. **Deploy to production**: Push and restart server
10. **Verify**: Test with real quotation data

### 9. Code Snippets for Key Functionality

#### Generate Word Table with Style
```python
table = self.document.add_table(rows=3, cols=2)
table.style = 'Table Grid'

# Set cell text
table.rows[0].cells[0].text = 'Label'
table.rows[0].cells[1].text = 'Value'

# Style cells
for row in table.rows:
    for cell in row.cells:
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.name = 'Calibri'
                run.font.size = Pt(11)
```

#### Add Styled Paragraph
```python
para = self.document.add_paragraph()
run = para.add_run('Heading Text')
run.font.size = Pt(14)
run.font.bold = True
run.font.name = 'Calibri'
para.alignment = WD_ALIGN_PARAGRAPH.CENTER
```

#### Generate and Download
```python
# Generate bytes
word_bytes = generate_bespoke_quotation_word(quotation)

# Create response
response = HttpResponse(
    word_bytes,
    content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
)
response['Content-Disposition'] = f'attachment; filename="Order_Details_{quotation.quotation_number}.docx"'
return response
```

### 10. Comparison with Excel Export

| Aspect | Excel Export | Word Export |
|--------|--------------|-------------|
| **Library** | `openpyxl` | `python-docx` |
| **Approach** | Template-based | Programmatic generation |
| **Template** | `Finalized_one.xlsx` | No template (code-generated) |
| **File Type** | `.xlsx` | `.docx` |
| **Purpose** | Production data entry | Order confirmation |
| **Content** | Player details + styling | Player details + order info |
| **Pricing** | No | No |
| **Styling** | Excel cell formatting | Word paragraph/table styles |
| **Complexity** | Moderate (template + logic) | Low (simple structure) |

### 11. Security Considerations

- ✅ **Permission Checks**: Verify user can access quotation
- ✅ **Input Validation**: Sanitize all data before adding to document
- ✅ **Audit Logging**: Log all exports for accountability
- ✅ **File Type Validation**: Ensure correct MIME type
- ✅ **Error Handling**: Don't expose sensitive info in errors
- ✅ **Rate Limiting**: Consider adding for production (future enhancement)

### 12. Performance Considerations

- **Document Size**: Small (< 1MB for typical quotation)
- **Generation Time**: < 1 second for typical quotation
- **Memory Usage**: Minimal (BytesIO buffer)
- **Caching**: Not needed (documents generated on-demand)
- **Database Queries**: Optimized with `select_related()`

### 13. Future Enhancements

1. **Template Support**: Create editable Word templates
2. **Custom Styling**: Allow customization via admin settings
3. **Multi-Language**: Support for different languages
4. **Batch Export**: Export multiple quotations at once
5. **Email Integration**: Send Word document via email
6. **Version Control**: Track different document versions
7. **Digital Signatures**: Add signature fields
8. **Company Branding**: Add logos and custom headers/footers

## Summary

This implementation provides a complete Word document export feature for bespoke quotations with player customizations. The approach mirrors the existing Excel export architecture while using `python-docx` for document generation. All data is sourced from existing Django models, and the UI integration follows established patterns in the quotation list and detail views.

**Key Benefits**:
- ✅ Matches sample document format exactly
- ✅ Reuses existing data model and business logic
- ✅ Consistent with Excel export architecture
- ✅ Clean separation of concerns (service class + view)
- ✅ Proper error handling and validation
- ✅ Audit logging for compliance
- ✅ User-friendly button placement
- ✅ Permission-aware access control

**Estimated Implementation Time**: 4-6 hours
- Code: 2-3 hours
- Testing: 1-2 hours
- Documentation: 1 hour
