"""
CIN7 Sync Service for Bespoke Products

Syncs products from CIN7 "Quotation Base Library" category
Maintains structure:
- Parent Category: Quotation Base Library (displayed as "Bespoke")
- Subcategories: 1. Addon, 2. Base Garment

Author: Claude Code
Date: 2025-11-11
"""

import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from django.utils.text import slugify
from django.db import transaction

from ..models import (
    BespokeCategory,
    BespokeProduct,
    BespokeProductCategoryAssignment,
    BespokeProductVariation,
    BespokeSyncLog
)
from schools.services.cin7_api_service import Cin7ApiService

logger = logging.getLogger(__name__)


class BespokeCin7SyncService:
    """Service for syncing Bespoke products from CIN7 API"""

    # CIN7 category names to sync
    TARGET_CATEGORY = "Quotation Base Library"
    DISPLAY_NAME = "Bespoke"

    def __init__(self):
        """Initialize sync service with CIN7 API"""
        self.cin7_api = Cin7ApiService()
        self.sync_log = None
        self.stats = {
            'categories_synced': 0,
            'products_synced': 0,
            'variations_synced': 0,
            'errors': []
        }

    def sync_all(self) -> BespokeSyncLog:
        """
        Full sync of Bespoke products from CIN7

        Returns:
            BespokeSyncLog instance
        """
        logger.info("=" * 80)
        logger.info("BESPOKE SYNC STARTED")
        logger.info("=" * 80)

        # Create sync log
        self.sync_log = BespokeSyncLog.objects.create(
            sync_type='full',
            status='running',
            started_at=timezone.now()
        )

        try:
            # Step 1: Fetch products from CIN7 with category filter
            logger.info(f"Step 1: Fetching products from CIN7 (category: '{self.TARGET_CATEGORY}')...")
            where_clause = f"category = '{self.TARGET_CATEGORY}'"
            bespoke_products, total_fetched, total_available = self.cin7_api.fetch_all_products(where_clause=where_clause)
            logger.info(f"Fetched {total_fetched} products from '{self.TARGET_CATEGORY}' category")

            # Step 2: Extract and sync categories
            logger.info("Step 2: Syncing categories...")
            category_map = self._sync_categories(bespoke_products)
            logger.info(f"Synced {self.stats['categories_synced']} categories")

            # Step 3: Sync products
            logger.info("Step 3: Syncing products...")
            self._sync_products(bespoke_products, category_map)
            logger.info(f"Synced {self.stats['products_synced']} products, {self.stats['variations_synced']} variations")

            # Mark as completed
            self.sync_log.categories_synced = self.stats['categories_synced']
            self.sync_log.products_synced = self.stats['products_synced']
            self.sync_log.variations_synced = self.stats['variations_synced']
            self.sync_log.errors_count = len(self.stats['errors'])
            self.sync_log.details = {
                'errors': self.stats['errors'],
                'target_category': self.TARGET_CATEGORY,
                'total_cin7_products': total_fetched
            }
            self.sync_log.mark_completed()

            logger.info("=" * 80)
            logger.info("BESPOKE SYNC COMPLETED SUCCESSFULLY")
            logger.info(f"Categories: {self.stats['categories_synced']}")
            logger.info(f"Products: {self.stats['products_synced']}")
            logger.info(f"Variations: {self.stats['variations_synced']}")
            logger.info(f"Errors: {len(self.stats['errors'])}")
            logger.info("=" * 80)

        except Exception as e:
            error_msg = f"Sync failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.sync_log.mark_failed(error_msg)
            raise

        return self.sync_log

    def _sync_categories(self, products: List[Dict]) -> Dict[str, BespokeCategory]:
        """
        Extract and sync categories from products

        Args:
            products: Bespoke products from CIN7

        Returns:
            Dictionary mapping category names to BespokeCategory instances
        """
        category_map = {}

        # Create parent category: "Bespoke" (from "Quotation Base Library")
        parent_category, created = BespokeCategory.objects.update_or_create(
            cin7_id='quotation-base-library',
            defaults={
                'name': self.DISPLAY_NAME,
                'slug': slugify(self.DISPLAY_NAME),
                'description': f'Products from CIN7 "{self.TARGET_CATEGORY}" category',
                'last_synced': timezone.now(),
                'is_active': True
            }
        )

        if created:
            self.stats['categories_synced'] += 1
            logger.info(f"Created parent category: {self.DISPLAY_NAME}")

        category_map[self.DISPLAY_NAME] = parent_category

        # Extract subcategories from products
        subcategory_names = set()
        for product in products:
            # CIN7 may have subcategory in different fields
            subcategory = (
                product.get('subCategory') or
                product.get('productSubCategory') or
                product.get('option1') or
                ''
            )

            if subcategory and subcategory.strip():
                subcategory_names.add(subcategory.strip())

        # Create subcategories
        for subcategory_name in subcategory_names:
            subcategory, created = BespokeCategory.objects.update_or_create(
                cin7_id=f'{parent_category.cin7_id}-{slugify(subcategory_name)}',
                defaults={
                    'name': subcategory_name,
                    'slug': slugify(subcategory_name),
                    'parent': parent_category,
                    'description': f'{subcategory_name} products',
                    'last_synced': timezone.now(),
                    'is_active': True
                }
            )

            if created:
                self.stats['categories_synced'] += 1
                logger.info(f"Created subcategory: {subcategory_name}")

            category_map[subcategory_name] = subcategory

        return category_map

    def _sync_products(self, products: List[Dict], category_map: Dict[str, BespokeCategory]):
        """
        Sync products and their variations

        Groups CIN7 products by base SKU (styleCode) to create parent-child structure:
        - One parent BespokeProduct per styleCode (e.g., "JKT 604 REG")
        - Multiple BespokeProductVariation per size (e.g., "JKT 604 REG -XS")

        Args:
            products: Bespoke products from CIN7
            category_map: Mapping of category names to BespokeCategory instances
        """
        # Group products by base SKU (styleCode)
        grouped_products = self._group_products_by_style_code(products)

        logger.info(f"Grouped {len(products)} CIN7 products into {len(grouped_products)} parent products")

        for style_code, product_group in grouped_products.items():
            try:
                with transaction.atomic():
                    self._sync_grouped_product(style_code, product_group, category_map)
            except Exception as e:
                error_msg = f"Error syncing product group {style_code}: {str(e)}"
                logger.error(error_msg)
                self.stats['errors'].append(error_msg)

    def _group_products_by_style_code(self, products: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group CIN7 products by base SKU (styleCode) by removing size suffixes.

        Examples:
            "JKT 604 REG -XS" -> "JKT 604 REG"
            "TOP 0015SW AOT OC23 -2XL" -> "TOP 0015SW AOT OC23"

        Args:
            products: List of CIN7 products

        Returns:
            Dictionary mapping base SKU to list of CIN7 products
        """
        import re
        grouped = {}

        # Pattern to match size suffixes: -XS, -S, -M, -L, -XL, -2XL, -3XL, etc.
        size_pattern = r'\s*-\s*(\d*X*[SML]|SMALL|MEDIUM|LARGE)$'

        for product in products:
            # Get productOptions to extract SKU from first option
            product_options = product.get('productOptions', [])

            if not product_options:
                # No options - use product code directly
                sku = product.get('code', '')
            else:
                # Use first option's code as representative SKU
                sku = product_options[0].get('code', '')

            # Extract base SKU by removing size suffix
            base_sku = re.sub(size_pattern, '', sku, flags=re.IGNORECASE).strip()

            # Group by base SKU
            if base_sku not in grouped:
                grouped[base_sku] = []
            grouped[base_sku].append(product)

            logger.debug(f"Grouped: {sku} -> {base_sku}")

        return grouped

    def _sync_grouped_product(self, style_code: str, product_group: List[Dict], category_map: Dict[str, BespokeCategory]):
        """
        Sync a grouped product (parent + variations)

        Args:
            style_code: Base SKU without size suffix (e.g., "JKT 604 REG")
            product_group: List of CIN7 products with same styleCode
            category_map: Mapping of category names to BespokeCategory instances
        """
        if not product_group:
            return

        # Use first product as template for parent product
        template_product = product_group[0]

        # Determine if this is a variable product (multiple sizes)
        is_variable = len(product_group) > 1

        logger.info(f"Syncing {'variable' if is_variable else 'simple'} product: {style_code} ({len(product_group)} size(s))")

        # Extract data from template product
        cin7_id = str(template_product.get('id', ''))
        name = template_product.get('name', f'Product {cin7_id}')

        # Get pricing from first active option
        product_options = template_product.get('productOptions', [])
        active_options = [opt for opt in product_options if opt.get('status', '').lower() in ['active', 'primary']]

        primary_option = None
        if active_options:
            primary_option = next((opt for opt in active_options if opt.get('status', '').lower() == 'primary'), active_options[0])

        cost_price = None
        retail_price = None

        if primary_option:
            price_columns = primary_option.get('priceColumns', {})
            cost_price = self._extract_decimal(price_columns.get('costNZD'))
            retail_price = self._extract_decimal(price_columns.get('retailNZD') or primary_option.get('retailPrice'))

        # Create or update parent product with base SKU (NO size suffix)
        product, created = BespokeProduct.objects.update_or_create(
            sku=style_code,  # Use base SKU as unique identifier
            defaults={
                'cin7_id': cin7_id,  # Use first product's CIN7 ID
                'name': name,
                'slug': slugify(name),
                'product_type': 'variable' if is_variable else 'simple',
                'barcode': template_product.get('barcode') or '',
                'description': template_product.get('description') or '',
                'short_description': template_product.get('shortDescription') or '',
                'cost_price': cost_price,
                'retail_price': retail_price,
                'price': retail_price,
                'stock_status': self._determine_stock_status(template_product),
                'stock_quantity': self._extract_int(template_product.get('stockOnHand', 0)),
                'stock_on_hand': self._extract_int(template_product.get('stockOnHand', 0)),
                'stock_available': self._extract_int(template_product.get('availableStock', 0)),
                'cin7_brand': template_product.get('brand', ''),
                'cin7_supplier': template_product.get('supplier', ''),
                'cin7_category_path': template_product.get('category', ''),
                'cin7_option1': template_product.get('option1', ''),
                'cin7_option2': template_product.get('option2', ''),
                'cin7_option3': template_product.get('option3', ''),
                'last_synced': timezone.now(),
                'is_active': True
            }
        )

        if created:
            self.stats['products_synced'] += 1
            logger.info(f"Created parent product: {name} (SKU: {style_code})")
        else:
            logger.debug(f"Updated parent product: {name} (SKU: {style_code})")

        # Assign to categories
        self._assign_product_categories(product, template_product, category_map)

        # Create variations for variable products
        if is_variable:
            self._sync_variations_from_group(product, product_group)

    def _sync_variations_from_group(self, parent_product: BespokeProduct, product_group: List[Dict]):
        """
        Create variations from grouped CIN7 products

        Args:
            parent_product: Parent BespokeProduct instance
            product_group: List of CIN7 products representing different sizes
        """
        for cin7_product in product_group:
            # Get the productOption (should have one option per CIN7 product record)
            product_options = cin7_product.get('productOptions', [])

            if not product_options:
                logger.warning(f"CIN7 product {cin7_product.get('id')} has no productOptions, skipping variation")
                continue

            for option in product_options:
                try:
                    # Extract option data
                    option_id = str(option.get('id') or option.get('optionId', ''))
                    if not option_id:
                        logger.warning(f"Option for product {cin7_product.get('id')} has no ID, skipping")
                        continue

                    # Extract SKU (with size suffix)
                    sku = option.get('code') or ''

                    # Extract size from option or SKU
                    size = option.get('option1') or self._extract_size_from_sku(sku)

                    # Extract pricing
                    price_columns = option.get('priceColumns', {})
                    cost_price = self._extract_decimal(price_columns.get('costNZD'))
                    retail_price = self._extract_decimal(price_columns.get('retailNZD') or option.get('retailPrice'))

                    # Create or update variation
                    variation, created = BespokeProductVariation.objects.update_or_create(
                        cin7_id=option_id,
                        defaults={
                            'parent_product': parent_product,
                            'sku': sku,
                            'barcode': option.get('barcode') or '',
                            'description': option.get('description') or '',
                            'option1_value': size,
                            'option2_value': option.get('option2') or '',
                            'option3_value': option.get('option3') or '',
                            'cost_price': cost_price,
                            'retail_price': retail_price,
                            'price': retail_price,
                            'stock_status': self._determine_stock_status_option(option),
                            'stock_quantity': self._extract_int(option.get('stockOnHand', 0)),
                            'stock_on_hand': self._extract_int(option.get('stockOnHand', 0)),
                            'stock_available': self._extract_int(option.get('availableStock', 0)),
                            'last_synced': timezone.now(),
                            'is_active': True
                        }
                    )

                    if created:
                        self.stats['variations_synced'] += 1
                        logger.debug(f"Created variation: {sku} (Size: {size})")

                except Exception as e:
                    error_msg = f"Error syncing variation for product {cin7_product.get('id')}: {str(e)}"
                    logger.error(error_msg)
                    self.stats['errors'].append(error_msg)

    def _extract_size_from_sku(self, sku: str) -> str:
        """
        Extract size from SKU using regex pattern

        Examples:
            "JKT 604 REG -XS" -> "XS"
            "TOP 0015SW AOT OC23 -2XL" -> "2XL"

        Args:
            sku: SKU with size suffix

        Returns:
            Size string or empty string if not found
        """
        import re
        size_pattern = r'\s*-\s*(\d*X*[SML]|SMALL|MEDIUM|LARGE)$'
        match = re.search(size_pattern, sku, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
        return ''

    def _sync_single_product(self, cin7_product: Dict, category_map: Dict[str, BespokeCategory]):
        """
        [DEPRECATED] Legacy method - now using _sync_grouped_product

        Sync a single product with its variations

        Args:
            cin7_product: Product data from CIN7
            category_map: Mapping of category names to BespokeCategory instances
        """
        # This method is deprecated and kept for backward compatibility only
        # The new approach uses _group_products_by_style_code and _sync_grouped_product
        cin7_id = str(cin7_product.get('id', ''))
        if not cin7_id:
            logger.warning("Product has no ID, skipping")
            return

        # Extract product options (variations)
        product_options = cin7_product.get('productOptions', [])

        # Determine if variable or simple
        active_options = [opt for opt in product_options if opt.get('status', '').lower() in ['active', 'primary']]
        product_type = 'variable' if len(active_options) > 1 else 'simple'

        # Get primary option for main product data
        primary_option = None
        for option in active_options:
            if option.get('status', '').lower() == 'primary':
                primary_option = option
                break

        if not primary_option and active_options:
            primary_option = active_options[0]

        # Extract pricing and SKU from primary option
        cost_price = None
        retail_price = None
        sku_code = ''

        if primary_option:
            price_columns = primary_option.get('priceColumns', {})
            cost_price = self._extract_decimal(price_columns.get('costNZD'))
            retail_price = self._extract_decimal(price_columns.get('retailNZD') or primary_option.get('retailPrice'))
            # Get SKU from primary option (this contains size info like "JKT 604 REG -XS")
            sku_code = primary_option.get('code') or cin7_product.get('code') or ''

        # Create or update product
        product, created = BespokeProduct.objects.update_or_create(
            cin7_id=cin7_id,
            defaults={
                'name': cin7_product.get('name', f'Product {cin7_id}'),
                'slug': slugify(cin7_product.get('name', f'product-{cin7_id}')),
                'product_type': product_type,
                'sku': sku_code,
                'barcode': cin7_product.get('barcode') or '',
                'description': cin7_product.get('description') or '',
                'short_description': cin7_product.get('shortDescription') or '',
                'cost_price': cost_price,
                'retail_price': retail_price,
                'price': retail_price,  # Use retail as default price
                'stock_status': self._determine_stock_status(cin7_product),
                'stock_quantity': self._extract_int(cin7_product.get('stockOnHand', 0)),
                'stock_on_hand': self._extract_int(cin7_product.get('stockOnHand', 0)),
                'stock_available': self._extract_int(cin7_product.get('availableStock', 0)),
                'cin7_brand': cin7_product.get('brand', ''),
                'cin7_supplier': cin7_product.get('supplier', ''),
                'cin7_category_path': cin7_product.get('category', ''),
                'cin7_option1': cin7_product.get('option1', ''),
                'cin7_option2': cin7_product.get('option2', ''),
                'cin7_option3': cin7_product.get('option3', ''),
                'last_synced': timezone.now(),
                'is_active': True
            }
        )

        if created:
            self.stats['products_synced'] += 1
            logger.info(f"Created product: {product.name} ({cin7_id})")

        # Assign to categories
        self._assign_product_categories(product, cin7_product, category_map)

        # Sync variations for variable products
        if product_type == 'variable' and len(active_options) > 1:
            self._sync_product_variations(product, active_options)

    def _assign_product_categories(self, product: BespokeProduct, cin7_product: Dict, category_map: Dict[str, BespokeCategory]):
        """Assign product to appropriate categories"""
        # Clear existing assignments
        product.category_assignments.all().delete()

        # Get subcategory from CIN7 product
        subcategory_name = (
            cin7_product.get('subCategory') or
            cin7_product.get('productSubCategory') or
            cin7_product.get('option1') or
            ''
        ).strip()

        # Assign to subcategory if found
        if subcategory_name and subcategory_name in category_map:
            BespokeProductCategoryAssignment.objects.create(
                product=product,
                category=category_map[subcategory_name]
            )
        else:
            # Assign to parent category as fallback
            parent_category = category_map.get(self.DISPLAY_NAME)
            if parent_category:
                BespokeProductCategoryAssignment.objects.create(
                    product=product,
                    category=parent_category
                )

    def _sync_product_variations(self, product: BespokeProduct, product_options: List[Dict]):
        """
        Sync product variations from CIN7 productOptions

        Args:
            product: BespokeProduct instance
            product_options: List of productOption dictionaries from CIN7
        """
        for option in product_options:
            try:
                # Extract option ID (use id or optionId)
                option_id = str(option.get('id') or option.get('optionId', ''))
                if not option_id:
                    logger.warning(f"Option for product {product.cin7_id} has no ID, skipping")
                    continue

                # Extract pricing
                price_columns = option.get('priceColumns', {})
                cost_price = self._extract_decimal(price_columns.get('costNZD'))
                retail_price = self._extract_decimal(price_columns.get('retailNZD') or option.get('retailPrice'))

                # Create or update variation
                variation, created = BespokeProductVariation.objects.update_or_create(
                    cin7_id=option_id,
                    defaults={
                        'parent_product': product,
                        'sku': option.get('code') or '',
                        'barcode': option.get('barcode') or '',
                        'description': option.get('description') or '',
                        'option1_value': option.get('option1') or '',
                        'option2_value': option.get('option2') or '',
                        'option3_value': option.get('option3') or '',
                        'cost_price': cost_price,
                        'retail_price': retail_price,
                        'price': retail_price,
                        'stock_status': self._determine_stock_status_option(option),
                        'stock_quantity': self._extract_int(option.get('stockOnHand', 0)),
                        'stock_on_hand': self._extract_int(option.get('stockOnHand', 0)),
                        'stock_available': self._extract_int(option.get('availableStock', 0)),
                        'last_synced': timezone.now(),
                        'is_active': True
                    }
                )

                if created:
                    self.stats['variations_synced'] += 1
                    logger.debug(f"Created variation: {variation.variation_name}")

            except Exception as e:
                error_msg = f"Error syncing variation for product {product.cin7_id}: {str(e)}"
                logger.error(error_msg)
                self.stats['errors'].append(error_msg)

    def _determine_stock_status(self, product: Dict) -> str:
        """Determine stock status from CIN7 product data"""
        stock_on_hand = self._extract_int(product.get('stockOnHand', 0))
        available_stock = self._extract_int(product.get('availableStock', 0))

        if available_stock and available_stock > 0:
            return 'instock'
        elif stock_on_hand and stock_on_hand > 0:
            return 'onbackorder'
        else:
            return 'outofstock'

    def _determine_stock_status_option(self, option: Dict) -> str:
        """Determine stock status from CIN7 productOption data"""
        stock_on_hand = self._extract_int(option.get('stockOnHand', 0))
        available_stock = self._extract_int(option.get('availableStock', 0))

        if available_stock and available_stock > 0:
            return 'instock'
        elif stock_on_hand and stock_on_hand > 0:
            return 'onbackorder'
        else:
            return 'outofstock'

    def _extract_decimal(self, value) -> Optional[Decimal]:
        """Safely extract decimal value"""
        if value is None or value == '':
            return None

        try:
            decimal_val = Decimal(str(value))
            return decimal_val if decimal_val >= 0 else None
        except (InvalidOperation, ValueError):
            return None

    def _extract_int(self, value) -> Optional[int]:
        """Safely extract integer value"""
        if value is None or value == '':
            return None

        try:
            return int(value)
        except (ValueError, TypeError):
            return None
