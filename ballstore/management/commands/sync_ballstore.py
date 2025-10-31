#!/usr/bin/env python3
"""
BallStore Product Synchronization Management Command

This command synchronizes BallStore products from WooCommerce API to Django models.
It handles categories, products, variations, and images with comprehensive error handling.

Usage:
    python manage.py sync_ballstore [options]

Options:
    --full              Force full sync of all products
    --incremental       Incremental sync (only modified products) - default
    --categories-only   Only sync categories

Features:
- Full and incremental sync modes
- Category hierarchy management (parent-child relationships)
- Simple and variable product support
- Product variation handling
- Multi-category product assignments
- Product image synchronization
- Skip specific category IDs (Bulk Deal, Uncategorized)
- Pagination support (100 products per page)
- Progress tracking and statistics
- Comprehensive error handling and logging
"""

import logging
import time
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.conf import settings
from requests.auth import HTTPBasicAuth

from ballstore.models import (
    BallStoreCategory,
    BallStoreProduct,
    BallStoreProductVariation,
    BallStoreProductImage,
    BallStoreSyncLog
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize BallStore products from WooCommerce API'

    # Category IDs to skip during sync
    SKIP_CATEGORY_IDS = [66, 104]  # Bulk Deal, Uncategorized

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_url = None
        self.consumer_key = None
        self.consumer_secret = None
        self.session = None
        self.sync_log = None
        self.stats = {
            'categories_synced': 0,
            'products_synced': 0,
            'variations_synced': 0,
            'images_synced': 0,
            'errors_count': 0,
        }

    def add_arguments(self, parser):
        """Add command line arguments"""
        parser.add_argument(
            '--full',
            action='store_true',
            help='Force full sync of all products'
        )

        parser.add_argument(
            '--incremental',
            action='store_true',
            help='Incremental sync (only modified products) - default'
        )

        parser.add_argument(
            '--categories-only',
            action='store_true',
            help='Only sync categories without products'
        )

        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )

    def handle(self, *args, **options):
        """Main command handler"""
        self.options = options
        start_time = time.time()

        # Set up logging level
        if options['verbose']:
            logger.setLevel(logging.DEBUG)

        try:
            # Initialize WooCommerce connection
            self._initialize_woocommerce()

            # Determine sync type
            if options['categories_only']:
                sync_type = 'categories'
            elif options['full']:
                sync_type = 'full'
            else:
                sync_type = 'incremental'

            # Create sync log entry
            self.sync_log = BallStoreSyncLog.objects.create(sync_type=sync_type)

            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write(self.style.SUCCESS(f'BallStore Sync - {sync_type.upper()} MODE'))
            self.stdout.write(self.style.SUCCESS('=' * 60))

            # Run synchronization
            if sync_type == 'categories':
                self._sync_categories()
            else:
                self._sync_all(full_sync=(sync_type == 'full'))

            # Complete sync log
            duration = time.time() - start_time
            self.sync_log.categories_synced = self.stats['categories_synced']
            self.sync_log.products_synced = self.stats['products_synced']
            self.sync_log.variations_synced = self.stats['variations_synced']
            self.sync_log.images_synced = self.stats['images_synced']
            self.sync_log.errors_count = self.stats['errors_count']
            self.sync_log.mark_completed()

            # Print summary
            self._print_summary(duration)

        except Exception as e:
            error_msg = f"BallStore sync failed: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg, exc_info=True)

            if self.sync_log:
                self.sync_log.mark_failed(error_msg)

            raise CommandError(error_msg)

    def _initialize_woocommerce(self):
        """Initialize WooCommerce API connection"""
        try:
            # Get BallStore credentials from environment
            self.api_url = settings.BS_WOO_URL
            self.consumer_key = settings.BS_WOO_KEY
            self.consumer_secret = settings.BS_WOO_SECRET

            # Create requests session with authentication
            self.session = requests.Session()
            self.session.auth = HTTPBasicAuth(self.consumer_key, self.consumer_secret)

            # Test connection
            self.stdout.write('Testing BallStore WooCommerce connection...')
            response = self.session.get(
                f"{self.api_url}products",
                params={'per_page': 1},
                timeout=30
            )
            response.raise_for_status()

            self.stdout.write(self.style.SUCCESS('✓ Connected to BallStore WooCommerce API'))

        except AttributeError as e:
            raise CommandError(
                f"BallStore WooCommerce settings not configured. "
                f"Please set BS_WOOCOMMERCE_API_URL, BS_WOOCOMMERCE_API_CONSUMER_KEY, "
                f"and BS_WOOCOMMERCE_API_SECRET in your .env file. Error: {str(e)}"
            )
        except requests.exceptions.RequestException as e:
            raise CommandError(f"Failed to connect to BallStore API: {str(e)}")

    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """
        Make authenticated request to WooCommerce API

        Args:
            endpoint: API endpoint (e.g., 'products', 'products/categories')
            params: Query parameters

        Returns:
            Response data or None if failed
        """
        url = f"{self.api_url}{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            logger.error(f"Request timeout for {url}")
            self.stats['errors_count'] += 1
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {url}: {str(e)}")
            self.stats['errors_count'] += 1
            return None

    def _sync_all(self, full_sync=False):
        """
        Main synchronization logic

        Args:
            full_sync: If True, sync all products. If False, only sync modified products.
        """
        # Step 1: Sync categories
        self.stdout.write(self.style.NOTICE('\n📂 Syncing categories...'))
        self._sync_categories()

        # Step 2: Sync products
        self.stdout.write(self.style.NOTICE('\n📦 Syncing products...'))
        self._sync_products(full_sync=full_sync)

    def _sync_categories(self):
        """Sync product categories from WooCommerce"""
        page = 1
        categories_processed = 0

        while True:
            params = {
                'per_page': 100,
                'page': page,
                'orderby': 'id',
                'order': 'asc'
            }

            categories = self._make_request('products/categories', params)

            if not categories:
                break

            for category_data in categories:
                try:
                    category_id = category_data.get('id')

                    # Skip excluded categories
                    if category_id in self.SKIP_CATEGORY_IDS:
                        if self.options['verbose']:
                            self.stdout.write(f"  Skipping category ID {category_id}: {category_data.get('name')}")
                        continue

                    self._process_category(category_data)
                    categories_processed += 1

                    if self.options['verbose']:
                        self.stdout.write(f"  ✓ Synced: {category_data.get('name')}")

                except Exception as e:
                    self.stats['errors_count'] += 1
                    logger.error(f"Error processing category {category_data.get('id')}: {str(e)}")
                    continue

            # Check if there are more pages
            if len(categories) < 100:
                break

            page += 1
            time.sleep(0.5)  # Rate limiting

        self.stats['categories_synced'] = categories_processed
        self.stdout.write(f"  Processed {categories_processed} categories")

    def _process_category(self, category_data: Dict):
        """
        Process and save a single category

        Args:
            category_data: Category data from WooCommerce API
        """
        wc_id = category_data.get('id')
        parent_id = category_data.get('parent', 0)

        # Find parent category if exists
        parent = None
        if parent_id > 0:
            parent = BallStoreCategory.objects.filter(wc_id=parent_id).first()

        # Prepare category data
        category_defaults = {
            'name': category_data.get('name', ''),
            'slug': category_data.get('slug', ''),
            'parent': parent,
            'description': category_data.get('description', ''),
            'display_type': category_data.get('display', 'default'),
            'product_count': category_data.get('count', 0),
            'last_synced': timezone.now(),
            'is_active': True,
        }

        # Create or update category
        BallStoreCategory.objects.update_or_create(
            wc_id=wc_id,
            defaults=category_defaults
        )

    def _sync_products(self, full_sync=False):
        """
        Sync products from WooCommerce

        Args:
            full_sync: If True, sync all products. If False, only sync modified products.
        """
        page = 1
        products_processed = 0

        # Get last sync time for incremental sync
        last_sync_time = None
        if not full_sync:
            last_log = BallStoreSyncLog.objects.filter(
                status='completed',
                sync_type__in=['full', 'incremental']
            ).order_by('-completed_at').first()

            if last_log:
                last_sync_time = last_log.completed_at

        while True:
            params = {
                'per_page': 100,
                'page': page,
                'orderby': 'id',
                'order': 'asc',
                'status': 'publish'
            }

            # Add date filter for incremental sync
            if last_sync_time and not full_sync:
                params['modified_after'] = last_sync_time.isoformat()

            products = self._make_request('products', params)

            if not products:
                break

            for product_data in products:
                try:
                    self._process_product(product_data)
                    products_processed += 1

                    if self.options['verbose']:
                        self.stdout.write(f"  ✓ Synced: {product_data.get('name')}")

                except Exception as e:
                    self.stats['errors_count'] += 1
                    logger.error(f"Error processing product {product_data.get('id')}: {str(e)}")
                    continue

            # Check if there are more pages
            if len(products) < 100:
                break

            page += 1
            time.sleep(0.5)  # Rate limiting

        self.stats['products_synced'] = products_processed
        self.stdout.write(f"  Processed {products_processed} products")

    def _process_product(self, product_data: Dict):
        """
        Process and save a single product

        Args:
            product_data: Product data from WooCommerce API
        """
        wc_id = product_data.get('id')
        product_type = product_data.get('type', 'simple')

        # Parse pricing
        price = self._parse_decimal(product_data.get('price'))
        regular_price = self._parse_decimal(product_data.get('regular_price'))
        sale_price = self._parse_decimal(product_data.get('sale_price'))

        # Parse dates
        date_created = self._parse_datetime(product_data.get('date_created'))
        date_modified = self._parse_datetime(product_data.get('date_modified'))

        # Get featured image
        featured_image_url = ''
        images = product_data.get('images', [])
        if images and len(images) > 0:
            featured_image_url = images[0].get('src', '')

        # Prepare product data
        product_defaults = {
            'name': product_data.get('name', ''),
            'slug': product_data.get('slug', ''),
            'permalink': product_data.get('permalink', ''),
            'product_type': product_type,
            'sku': product_data.get('sku', ''),
            'description': product_data.get('description', ''),
            'short_description': product_data.get('short_description', ''),
            'price': price,
            'regular_price': regular_price,
            'sale_price': sale_price,
            'on_sale': product_data.get('on_sale', False),
            'stock_status': product_data.get('stock_status', 'instock'),
            'stock_quantity': product_data.get('stock_quantity'),
            'manage_stock': product_data.get('manage_stock', False),
            'featured_image_url': featured_image_url,
            'date_created': date_created,
            'date_modified': date_modified,
            'last_synced': timezone.now(),
            'is_active': True,
        }

        # Create or update product
        product, created = BallStoreProduct.objects.update_or_create(
            wc_id=wc_id,
            defaults=product_defaults
        )

        # Handle categories (many-to-many)
        self._assign_categories(product, product_data.get('categories', []))

        # Handle images
        self._sync_product_images(product, images)

        # Handle variations for variable products
        if product_type == 'variable':
            self._sync_product_variations(product, wc_id)

    def _assign_categories(self, product: BallStoreProduct, category_data: List[Dict]):
        """
        Assign categories to product

        Args:
            product: BallStoreProduct instance
            category_data: List of category dictionaries from WooCommerce
        """
        category_ids = [cat.get('id') for cat in category_data if cat.get('id') not in self.SKIP_CATEGORY_IDS]

        # Get category objects
        categories = BallStoreCategory.objects.filter(wc_id__in=category_ids)

        # Assign categories
        product.categories.set(categories)

    def _sync_product_images(self, product: BallStoreProduct, images: List[Dict]):
        """
        Sync product images

        Args:
            product: BallStoreProduct instance
            images: List of image dictionaries from WooCommerce
        """
        # Clear existing images
        product.images.all().delete()

        for position, image_data in enumerate(images):
            try:
                wc_id = image_data.get('id')
                src = image_data.get('src', '')

                if not src:
                    continue

                BallStoreProductImage.objects.create(
                    wc_id=wc_id,
                    product=product,
                    src=src,
                    name=image_data.get('name', ''),
                    alt=image_data.get('alt', ''),
                    position=position
                )

                self.stats['images_synced'] += 1

            except Exception as e:
                logger.error(f"Error syncing image for product {product.wc_id}: {str(e)}")
                self.stats['errors_count'] += 1
                continue

    def _sync_product_variations(self, product: BallStoreProduct, product_wc_id: int):
        """
        Sync variations for a variable product

        Args:
            product: BallStoreProduct instance
            product_wc_id: WooCommerce product ID
        """
        page = 1

        while True:
            params = {
                'per_page': 100,
                'page': page
            }

            variations = self._make_request(f'products/{product_wc_id}/variations', params)

            if not variations:
                break

            for variation_data in variations:
                try:
                    self._process_variation(product, variation_data)

                    if self.options['verbose']:
                        self.stdout.write(f"    ✓ Variation: {variation_data.get('id')}")

                except Exception as e:
                    self.stats['errors_count'] += 1
                    logger.error(f"Error processing variation {variation_data.get('id')}: {str(e)}")
                    continue

            # Check if there are more pages
            if len(variations) < 100:
                break

            page += 1
            time.sleep(0.3)  # Rate limiting

    def _process_variation(self, product: BallStoreProduct, variation_data: Dict):
        """
        Process and save a single product variation

        Args:
            product: BallStoreProduct instance
            variation_data: Variation data from WooCommerce API
        """
        wc_id = variation_data.get('id')

        # Parse pricing
        price = self._parse_decimal(variation_data.get('price'))
        regular_price = self._parse_decimal(variation_data.get('regular_price'))
        sale_price = self._parse_decimal(variation_data.get('sale_price'))

        # Parse dates
        date_created = self._parse_datetime(variation_data.get('date_created'))
        date_modified = self._parse_datetime(variation_data.get('date_modified'))

        # Get variation image
        image_url = ''
        image_data = variation_data.get('image')
        if image_data:
            image_url = image_data.get('src', '')

        # Prepare variation data
        variation_defaults = {
            'sku': variation_data.get('sku', ''),
            'description': variation_data.get('description', ''),
            'price': price,
            'regular_price': regular_price,
            'sale_price': sale_price,
            'on_sale': variation_data.get('on_sale', False),
            'stock_status': variation_data.get('stock_status', 'instock'),
            'stock_quantity': variation_data.get('stock_quantity'),
            'manage_stock': variation_data.get('manage_stock', False),
            'attributes': variation_data.get('attributes', []),
            'image_url': image_url,
            'date_created': date_created,
            'date_modified': date_modified,
            'last_synced': timezone.now(),
            'is_active': True,
        }

        # Create or update variation
        BallStoreProductVariation.objects.update_or_create(
            wc_id=wc_id,
            parent_product=product,
            defaults=variation_defaults
        )

        self.stats['variations_synced'] += 1

    def _parse_decimal(self, value) -> Optional[Decimal]:
        """
        Parse string to Decimal

        Args:
            value: String or number to parse

        Returns:
            Decimal value or None
        """
        if not value:
            return None

        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def _parse_datetime(self, value: str) -> Optional[datetime]:
        """
        Parse ISO datetime string

        Args:
            value: ISO datetime string

        Returns:
            DateTime object or None
        """
        if not value:
            return None

        try:
            return parse_datetime(value)
        except (ValueError, TypeError):
            return None

    def _print_summary(self, duration: float):
        """
        Print synchronization summary

        Args:
            duration: Total sync duration in seconds
        """
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('🎉 BALLSTORE SYNC SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        # Statistics
        self.stdout.write(f'\n📊 Statistics:')
        self.stdout.write(f'  • Categories synced: {self.stats["categories_synced"]}')
        self.stdout.write(f'  • Products synced: {self.stats["products_synced"]}')
        self.stdout.write(f'  • Variations synced: {self.stats["variations_synced"]}')
        self.stdout.write(f'  • Images synced: {self.stats["images_synced"]}')
        self.stdout.write(f'  • Errors: {self.stats["errors_count"]}')

        # Summary
        total_items = (
            self.stats["categories_synced"] +
            self.stats["products_synced"] +
            self.stats["variations_synced"] +
            self.stats["images_synced"]
        )

        self.stdout.write(f'\n📈 Summary:')
        self.stdout.write(f'  • Total items synced: {total_items}')
        self.stdout.write(f'  • Duration: {duration:.2f} seconds')

        # Success rate
        if total_items > 0:
            success_rate = ((total_items - self.stats["errors_count"]) / total_items) * 100
            self.stdout.write(f'  • Success rate: {success_rate:.1f}%')

        self.stdout.write(self.style.SUCCESS('=' * 60))

        if self.stats["errors_count"] > 0:
            self.stdout.write(
                self.style.WARNING(f'\n⚠️  {self.stats["errors_count"]} errors occurred. Check logs for details.')
            )
        else:
            self.stdout.write(self.style.SUCCESS('\n✨ Sync completed successfully with no errors!'))
