"""
Excel Export Service for Bespoke Quotations

Generates Excel files in SAS FORMAT for quotations containing bespoke products
with player customization details.
"""
import os
from io import BytesIO
from typing import List, Dict, Optional
from datetime import datetime
from decimal import Decimal

import openpyxl
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from django.conf import settings

import logging

logger = logging.getLogger(__name__)


class BespokeQuotationExcelGenerator:
    """
    Generates Excel export for quotations with bespoke products and player details.

    NEW FORMAT (Single Sheet):
    - All products on ONE sheet (Summary) laid out vertically
    - Order details at top (rows 1-14)
    - Products listed sequentially below with dynamic spacing
    - Each product has: Title → Variations → Players
    """

    # Template configuration
    TEMPLATE_PATH = os.path.join(settings.BASE_DIR, 'static', 'excel_templates', 'Finalized_one.xlsx')

    # Order details section (rows 1-14)
    ORDER_DETAILS_START_ROW = 1
    ORDER_HEADER_ROW = 1  # "SAS KITUP ORDER FORM" in B1
    ORDER_CUSTOMER_ROW = 3  # "Customer name:" in B3
    ORDER_TEAM_ROW = 4  # "Team name:" in B4
    ORDER_SOP_ROW = 5  # "SOP No:" in B5
    ORDER_DATE_ROW = 6  # "Ordered date:" in B6
    ORDER_REQUIRED_ROW = 7  # "Required date:" in B7
    ORDER_DETAILS_END_ROW = 14

    # Products start after order details
    PRODUCTS_START_ROW = 15

    # Column configuration (NEW LAYOUT)
    # Column B: Wide labels/names (width 68.33)
    # Column C: Narrow spacing (width 10.83)
    # Column D: Numbers (width 22.33)
    # Column E: Initials (width 10.83)
    LABEL_COL = 'B'
    VALUE_COL = 'C'  # For order detail values
    PLAYER_NAME_COL = 'B'  # Changed from C
    PLAYER_NUMBER_COL = 'D'  # Changed from E
    PLAYER_INITIALS_COL = 'E'  # Changed from F

    # Column widths (exact values from template)
    COLUMN_WIDTHS = {
        'B': 68.33,
        'C': 10.83,
        'D': 22.33,
        'E': 10.83,
    }

    # Font sizes (NEW SPEC)
    FONT_SIZE_HEADER = 36  # "SAS KITUP ORDER FORM"
    FONT_SIZE_ORDER_DETAILS = 18  # Order detail labels/values
    FONT_SIZE_PRODUCT_DATA = 20  # Products, variations, players

    # Product title styling
    PRODUCT_TITLE_FONT_SIZE = 20
    PRODUCT_TITLE_BOLD = False  # NOT bold in new format
    PRODUCT_TITLE_COLOR = '2B2E3B'  # Dark blue (no FF prefix)

    # Row heights
    ROW_HEIGHT_PRODUCT = 26  # Consistent for all product rows

    def __init__(self, quotation):
        """
        Initialize generator with a quotation instance.

        Args:
            quotation: Quotation model instance
        """
        self.quotation = quotation
        self.workbook: Optional[Workbook] = None

    def generate(self) -> bytes:
        """
        Generate Excel file and return as bytes.

        NEW FORMAT: Single-sheet layout with all products vertically stacked.

        Returns:
            bytes: Excel file content

        Raises:
            FileNotFoundError: If template file not found
            ValueError: If quotation has no bespoke items
        """
        # Validate template exists
        if not os.path.exists(self.TEMPLATE_PATH):
            raise FileNotFoundError(f"Excel template not found at {self.TEMPLATE_PATH}")

        # Load template
        self.workbook = openpyxl.load_workbook(self.TEMPLATE_PATH)

        try:
            # Get bespoke items
            bespoke_items = self._get_bespoke_items()

            if not bespoke_items:
                raise ValueError("No player customizations found for bespoke items in this quotation")

            # Get the Summary sheet (the only sheet in new format)
            if 'Summary' not in self.workbook.sheetnames:
                raise ValueError("Template missing 'Summary' sheet")

            sheet = self.workbook['Summary']

            # Unmerge all cells to avoid write conflicts
            merged_ranges = list(sheet.merged_cells.ranges)
            for merged_range in merged_ranges:
                sheet.unmerge_cells(str(merged_range))

            # Clear all data from products section onwards (row 15+)
            # Template has sample data that needs to be removed
            for row_num in range(self.PRODUCTS_START_ROW, sheet.max_row + 1):
                for col in ['B', 'C', 'D', 'E', 'F']:
                    sheet[f'{col}{row_num}'].value = None

            # Set column widths
            self._set_column_widths(sheet)

            # Populate order details at top (rows 1-14)
            self._populate_order_details(sheet)

            # Group items by base product SKU
            product_groups = self._group_items_by_base_product(bespoke_items)

            # Write all products sequentially on one sheet with dynamic row tracking
            current_row = self.PRODUCTS_START_ROW
            for base_sku, items in product_groups.items():
                current_row = self._write_product_section(sheet, base_sku, items, current_row)

            # Save to BytesIO
            output = BytesIO()
            self.workbook.save(output)
            output.seek(0)

            return output.getvalue()

        finally:
            if self.workbook:
                self.workbook.close()

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

        Multiple QuotationItems with the same base SKU (different sizes) should
        be combined into ONE sheet with multiple variation blocks.

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

    def _set_column_widths(self, sheet: Worksheet):
        """Set column widths according to new format spec."""
        for col, width in self.COLUMN_WIDTHS.items():
            sheet.column_dimensions[col].width = width

    def _populate_order_details(self, sheet: Worksheet):
        """
        Populate order details at top of sheet (rows 1-14).

        NEW FORMAT: Order details are now in column B with values in column C.
        """
        from openpyxl.styles import Font

        # Customer name (row 3)
        institution_name = ''
        if self.quotation.institution:
            institution_name = self.quotation.institution.name
        sheet[f'{self.VALUE_COL}{self.ORDER_CUSTOMER_ROW}'] = institution_name

        # Team name (row 4)
        sheet[f'{self.VALUE_COL}{self.ORDER_TEAM_ROW}'] = institution_name

        # S.O.P No (row 5)
        sheet[f'{self.VALUE_COL}{self.ORDER_SOP_ROW}'] = self.quotation.quotation_number

        # Ordered date (row 6)
        if self.quotation.created_at:
            sheet[f'{self.VALUE_COL}{self.ORDER_DATE_ROW}'] = self.quotation.created_at.strftime('%Y-%m-%d')

        # Required date (row 7)
        if hasattr(self.quotation, 'delivery_date') and self.quotation.delivery_date:
            sheet[f'{self.VALUE_COL}{self.ORDER_REQUIRED_ROW}'] = self.quotation.delivery_date.strftime('%Y-%m-%d')

    def _write_product_section(self, sheet: Worksheet, base_sku: str, items: List, start_row: int) -> int:
        """
        Write a complete product section (title + all variations + players).

        Args:
            sheet: Worksheet instance
            base_sku: Base product SKU
            items: List of QuotationItem instances for this product
            start_row: Row to start writing from

        Returns:
            int: Next available row after this product section
        """
        from openpyxl.styles import Font

        current_row = start_row

        # Write product title
        sheet[f'{self.LABEL_COL}{current_row}'] = base_sku
        sheet[f'{self.LABEL_COL}{current_row}'].font = Font(
            size=self.PRODUCT_TITLE_FONT_SIZE,
            bold=self.PRODUCT_TITLE_BOLD,
            color=self.PRODUCT_TITLE_COLOR
        )
        sheet.row_dimensions[current_row].height = self.ROW_HEIGHT_PRODUCT
        current_row += 2  # Title + 1 blank row

        # Get all variation groups for this product
        variation_groups = self._get_variation_groups_for_product_group(items, base_sku)

        # Write each variation block
        for variation_data in variation_groups:
            current_row = self._write_variation_block(sheet, variation_data, current_row)
            current_row += 3  # 3 rows spacing between variations

        return current_row

    def _write_variation_block(self, sheet: Worksheet, variation_data: Dict, start_row: int) -> int:
        """
        Write a single variation block (variation info + player table).

        Args:
            sheet: Worksheet instance
            variation_data: Dict with variation_code, size, players, total_qty
            start_row: Row to start writing from

        Returns:
            int: Next available row after this variation block
        """
        from openpyxl.styles import Font, Alignment

        current_row = start_row

        # Write variation info (3 rows)
        sheet[f'{self.LABEL_COL}{current_row}'] = 'Variation style code'
        sheet[f'{self.VALUE_COL}{current_row}'] = variation_data['variation_code']
        sheet[f'{self.LABEL_COL}{current_row}'].font = Font(size=self.FONT_SIZE_PRODUCT_DATA, bold=True)
        sheet[f'{self.VALUE_COL}{current_row}'].font = Font(size=self.FONT_SIZE_PRODUCT_DATA, bold=True)
        sheet[f'{self.LABEL_COL}{current_row}'].alignment = Alignment(horizontal='left')
        sheet[f'{self.VALUE_COL}{current_row}'].alignment = Alignment(horizontal='left')
        current_row += 1

        sheet[f'{self.LABEL_COL}{current_row}'] = 'Size'
        sheet[f'{self.VALUE_COL}{current_row}'] = variation_data['size']
        sheet[f'{self.LABEL_COL}{current_row}'].font = Font(size=self.FONT_SIZE_PRODUCT_DATA, bold=True)
        sheet[f'{self.VALUE_COL}{current_row}'].font = Font(size=self.FONT_SIZE_PRODUCT_DATA, bold=True)
        sheet[f'{self.LABEL_COL}{current_row}'].alignment = Alignment(horizontal='left')
        sheet[f'{self.VALUE_COL}{current_row}'].alignment = Alignment(horizontal='left')
        current_row += 1

        sheet[f'{self.LABEL_COL}{current_row}'] = 'Total qty'
        sheet[f'{self.VALUE_COL}{current_row}'] = variation_data['total_qty']
        sheet[f'{self.LABEL_COL}{current_row}'].font = Font(size=self.FONT_SIZE_PRODUCT_DATA, bold=True)
        sheet[f'{self.VALUE_COL}{current_row}'].font = Font(size=self.FONT_SIZE_PRODUCT_DATA, bold=True)
        sheet[f'{self.LABEL_COL}{current_row}'].alignment = Alignment(horizontal='left')
        sheet[f'{self.VALUE_COL}{current_row}'].alignment = Alignment(horizontal='left')
        current_row += 1  # Move past Total qty row
        current_row += 1  # Add 1 blank row after variation info

        # Write player header
        player_header_row = current_row
        sheet[f'{self.PLAYER_NAME_COL}{current_row}'] = 'Name'
        sheet[f'{self.PLAYER_NUMBER_COL}{current_row}'] = 'Number'
        sheet[f'{self.PLAYER_INITIALS_COL}{current_row}'] = 'Initials'
        for col in [self.PLAYER_NAME_COL, self.PLAYER_NUMBER_COL, self.PLAYER_INITIALS_COL]:
            sheet[f'{col}{current_row}'].font = Font(size=self.FONT_SIZE_PRODUCT_DATA, bold=True)
            sheet[f'{col}{current_row}'].alignment = Alignment(horizontal='center')
        sheet.row_dimensions[current_row].height = self.ROW_HEIGHT_PRODUCT

        # Merge "Name" header across columns B:C (matches template)
        sheet.merge_cells(f'{self.PLAYER_NAME_COL}{player_header_row}:{self.VALUE_COL}{player_header_row}')
        current_row += 1

        # Write players
        for player in variation_data['players']:
            sheet[f'{self.PLAYER_NAME_COL}{current_row}'] = player.get('player_name', '')
            sheet[f'{self.PLAYER_NUMBER_COL}{current_row}'] = player.get('player_number', '')
            sheet[f'{self.PLAYER_INITIALS_COL}{current_row}'] = player.get('player_initial', '')

            # Set alignment for player data
            sheet[f'{self.PLAYER_NAME_COL}{current_row}'].alignment = Alignment(horizontal='left')
            sheet[f'{self.PLAYER_NUMBER_COL}{current_row}'].alignment = Alignment(horizontal='general')
            sheet[f'{self.PLAYER_INITIALS_COL}{current_row}'].alignment = Alignment(horizontal='center')

            for col in [self.PLAYER_NAME_COL, self.PLAYER_NUMBER_COL, self.PLAYER_INITIALS_COL]:
                sheet[f'{col}{current_row}'].font = Font(size=self.FONT_SIZE_PRODUCT_DATA)
            sheet.row_dimensions[current_row].height = self.ROW_HEIGHT_PRODUCT
            current_row += 1

        return current_row

    def _get_variation_groups_for_product_group(self, items: List, base_sku: str) -> List[Dict]:
        """
        Group players by variation (size) across ALL items for a base product.

        Args:
            items: List of QuotationItem instances for the same base product
            base_sku: Base product SKU (without size suffix)

        Returns:
            List of dicts with variation data and players grouped by size:
            [
                {
                    'variation_code': 'PROD-M',
                    'size': 'M',
                    'players': [{player_name, player_number, player_initial}, ...]
                },
                ...
            ]
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


def generate_bespoke_quotation_excel(quotation) -> bytes:
    """
    Convenience function to generate Excel for a quotation.

    Args:
        quotation: Quotation model instance

    Returns:
        bytes: Excel file content
    """
    generator = BespokeQuotationExcelGenerator(quotation)
    return generator.generate()
