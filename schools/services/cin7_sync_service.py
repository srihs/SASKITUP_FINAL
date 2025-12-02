"""
CIN7 Product Sync Service

Handles intelligent sync operations for CIN7 products with two modes:
1. Initial Sync: Fetch and save ALL products from CIN7 API (one-time operation per price_type)
2. Incremental Sync: Fetch all products but only update changed records in database

Since CIN7 API doesn't support incremental queries (no modifiedSince parameter),
we implement application-level change detection using data hashing.

Author: Claude Code
Date: 2025-12-02
"""

import logging
import hashlib
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.db import transaction
from schools.models import Cin7Product
from schools.services.cin7_api_service import Cin7ApiService

logger = logging.getLogger(__name__)


class Cin7SyncService:
    """
    Service for intelligent CIN7 product synchronization.

    Provides two sync modes:
    - Initial: Full fetch and save (for empty database or forced refresh)
    - Incremental: Fetch all but only update changed records (efficient database operations)
    """

    def __init__(self):
        """Initialize sync service with CIN7 API service"""
        self.cin7_api = Cin7ApiService()

    def determine_sync_mode(self, price_type: str, force_initial: bool = False) -> str:
        """
        Determine whether to perform initial or incremental sync.

        Args:
            price_type: Price type (TUS, LOTTO, SAS, Wholesale, etc.)
            force_initial: Force initial sync even if records exist

        Returns:
            'initial' or 'incremental'
        """
        if force_initial:
            logger.info(f"Sync mode: INITIAL (forced by user)")
            return 'initial'

        # Check if records exist at all (PRIMARY check)
        record_count = Cin7Product.objects.filter(price_type=price_type).count()

        if record_count == 0:
            logger.info(f"Sync mode: INITIAL (no records found for {price_type})")
            return 'initial'

        # SAFETY CHECK: If more than 10,000 records exist, NEVER do initial sync unless forced
        # This prevents accidental data loss from clearing large datasets
        if record_count > 10000:
            logger.warning(
                f"Sync mode: INCREMENTAL (safety override - {record_count} existing records > 10,000 threshold). "
                f"Initial sync would clear {record_count} records - use force_initial=True if this is intentional."
            )
            return 'incremental'

        # Check if initial sync flag is set (SECONDARY check for small datasets)
        has_initial_sync = Cin7Product.is_initial_sync_complete(price_type)

        if not has_initial_sync:
            logger.warning(
                f"Sync mode: INCREMENTAL (no is_initial_sync flag but {record_count} records exist). "
                f"This may indicate a database migration reset. Using incremental to prevent data loss."
            )
            return 'incremental'

        logger.info(f"Sync mode: INCREMENTAL ({record_count} existing records for {price_type})")
        return 'incremental'

    def calculate_product_hash(self, cost_nzd, retail_price, stock_available) -> str:
        """
        Calculate hash of product pricing data for change detection.

        Args:
            cost_nzd: Cost price in NZD
            retail_price: Retail price
            stock_available: Available stock quantity

        Returns:
            SHA-256 hash of the data
        """
        data_string = f"{cost_nzd}|{retail_price}|{stock_available}"
        return hashlib.sha256(data_string.encode()).hexdigest()

    def perform_initial_sync(
        self,
        price_type: str,
        session_id: str,
        progress_callback=None,
        log_callback=None
    ) -> Dict:
        """
        Perform initial sync: fetch ALL products from CIN7 and save to database.

        This is a one-time operation per price_type that:
        1. Clears all existing records for this price_type
        2. Fetches all products from CIN7 API
        3. Saves all products to database
        4. Marks records with is_initial_sync=True
        5. Sets last_api_fetch timestamp

        Args:
            price_type: Price type to sync
            session_id: Unique session identifier
            progress_callback: Optional callback(current, total, message)
            log_callback: Optional callback(level, message, details)

        Returns:
            Dict with sync results
        """
        start_time = timezone.now()

        logger.info(f"=== INITIAL SYNC STARTED for {price_type} ===")
        if log_callback:
            log_callback('info', f'🆕 Starting INITIAL SYNC for {price_type} products', {
                'sync_mode': 'initial',
                'price_type': price_type
            })

        # Clear all existing records for this price_type
        old_count = Cin7Product.objects.filter(price_type=price_type).count()
        if old_count > 0:
            # SAFETY CHECK: Warn about large deletions
            if old_count > 10000:
                logger.warning(
                    f"⚠️ LARGE DELETION WARNING: About to clear {old_count} existing {price_type} records. "
                    f"This is a significant operation that should only happen during initial setup or forced refresh."
                )
                if log_callback:
                    log_callback('warning',
                        f'⚠️ Large deletion: Clearing {old_count} existing records (this is expected for initial sync)',
                        {'old_count': old_count, 'price_type': price_type}
                    )

            logger.info(f"Clearing {old_count} existing {price_type} records...")
            if log_callback:
                log_callback('info', f'Clearing {old_count} existing records', {
                    'old_count': old_count
                })

            Cin7Product.objects.filter(price_type=price_type).delete()

            logger.info(f"✓ Cleared {old_count} old records")
            if log_callback:
                log_callback('success', f'✓ Cleared {old_count} old records', None)

        # Fetch all products from CIN7 API
        if progress_callback:
            progress_callback(0, 100, "Fetching products from CIN7 API...")

        if log_callback:
            log_callback('info', f'📡 Fetching ALL {price_type} products from CIN7 API...', None)

        products, fetched, total = self.cin7_api.fetch_all_products(
            price_type=price_type,
            where_clause=None,
            progress_callback=progress_callback
        )

        logger.info(f"✓ Fetched {fetched} products from CIN7")
        if log_callback:
            log_callback('success', f'✓ Fetched {fetched} products from CIN7', {
                'fetched': fetched,
                'total': total
            })

        # Process and save products
        if progress_callback:
            progress_callback(0, len(products), "Processing and saving products...")

        if log_callback:
            log_callback('info', f'💾 Processing and saving {len(products)} products...', {
                'product_count': len(products)
            })

        cin7_products = []
        skipped_no_id = 0
        skipped_no_options = 0
        skipped_bs_products = 0
        total_options = 0
        current_time = timezone.now()

        for index, cin7_product in enumerate(products, 1):
            if index % 500 == 0 and progress_callback:
                progress_callback(index, len(products), f"Processing {index}/{len(products)}...")

            # Extract all product options (variants)
            product_options = self.cin7_api.extract_product_options(cin7_product)

            if not product_options:
                skipped_no_options += 1
                continue

            # Create a Cin7Product record for each variant
            for option_data in product_options:
                # Skip options without cin7_id
                if not option_data.get('cin7_id'):
                    logger.warning(f"Skipping option without cin7_id: {option_data.get('sku', 'unknown')}")
                    skipped_no_id += 1
                    continue

                # Skip BS products (except for Bespoke price_type)
                sku = option_data.get('sku') or ''
                style_code = option_data.get('style_code') or ''
                if price_type != 'Bespoke' and (sku.upper().startswith('BS') or style_code.upper().startswith('BS')):
                    skipped_bs_products += 1
                    continue

                # Skip BESPOKE ADDON products
                category_path = option_data.get('category', '').upper()
                product_name = option_data.get('product_name', '').upper()
                sku_upper = sku.upper()

                is_bespoke_addon = 'QUOTATION BASE LIBRARY' in category_path and any([
                    'SCREEN PRINT' in product_name or 'SCREEN PRINT' in sku_upper,
                    'HEAT TRANSFER' in product_name or 'HEAT TRANSFER' in sku_upper,
                    ('EMB' in sku_upper and ('EMBROIDERY' in product_name or 'APPLIQUE' in product_name)),
                ])

                if is_bespoke_addon:
                    skipped_bs_products += 1
                    continue

                # Get pricing data
                cost = option_data.get('cost')
                rrp = option_data.get('current_retail_nzd_incl')
                stock = option_data.get('stock_available')

                # Calculate data hash for change detection
                data_hash = self.calculate_product_hash(cost, rrp, stock)

                # Create Cin7Product instance
                cin7_products.append(Cin7Product(
                    cin7_id=option_data.get('cin7_id'),
                    code=sku,
                    style_code=style_code,
                    barcode=option_data.get('barcode') or '',
                    name=option_data.get('product_name') or '',
                    category=option_data.get('category') or '',
                    brand=option_data.get('brand') or '',
                    cost_nzd=cost,
                    retail_price=rrp,
                    stock_available=stock,
                    price_type=price_type,
                    fetch_session_id=session_id,
                    last_api_fetch=current_time,
                    data_hash=data_hash,
                    is_initial_sync=True,  # Mark as initial sync
                    raw_data=cin7_product
                ))
                total_options += 1

        # Bulk create all products (much faster than individual saves)
        logger.info(f"Bulk creating {len(cin7_products)} Cin7Product records...")
        if log_callback:
            log_callback('info', f'💾 Saving {len(cin7_products)} products to database...', {
                'product_count': len(cin7_products)
            })

        with transaction.atomic():
            Cin7Product.objects.bulk_create(cin7_products, batch_size=500)

        elapsed = (timezone.now() - start_time).total_seconds()

        # Prepare results
        results = {
            'success': True,
            'sync_mode': 'initial',
            'session_id': session_id,
            'total_fetched': len(products),
            'total_variants': total_options,
            'saved_to_db': len(cin7_products),
            'skipped_no_options': skipped_no_options,
            'skipped_bs_products': skipped_bs_products,
            'skipped_no_id': skipped_no_id,
            'duration_seconds': round(elapsed, 2),
            'price_type': price_type
        }

        logger.info(f"=== INITIAL SYNC COMPLETE for {price_type} ===")
        logger.info(f"Total parent products: {len(products)}")
        logger.info(f"Total product variants: {total_options}")
        logger.info(f"Saved to database: {len(cin7_products)}")
        logger.info(f"Duration: {elapsed:.2f}s")

        if log_callback:
            log_callback('success', f'✅ INITIAL SYNC Complete: Saved {len(cin7_products)} products', results)

        return results

    def perform_incremental_sync(
        self,
        price_type: str,
        session_id: str,
        progress_callback=None,
        log_callback=None
    ) -> Dict:
        """
        Perform incremental sync: fetch all products but only update changed records.

        Since CIN7 API doesn't support incremental queries, this method:
        1. Fetches ALL products from CIN7 API (same as initial)
        2. Compares data hashes to detect changes
        3. Only updates/inserts records that have changed
        4. Marks obsolete records (products removed from CIN7)
        5. Much more efficient database operations

        Args:
            price_type: Price type to sync
            session_id: Unique session identifier
            progress_callback: Optional callback(current, total, message)
            log_callback: Optional callback(level, message, details)

        Returns:
            Dict with sync results
        """
        start_time = timezone.now()

        logger.info(f"=== INCREMENTAL SYNC STARTED for {price_type} ===")
        if log_callback:
            log_callback('info', f'🔄 Starting INCREMENTAL SYNC for {price_type} products', {
                'sync_mode': 'incremental',
                'price_type': price_type
            })

        # Get last sync time
        last_sync = Cin7Product.get_last_sync_time(price_type)
        if log_callback and last_sync:
            log_callback('info', f'Last sync was {timezone.now() - last_sync} ago', {
                'last_sync': last_sync.isoformat()
            })

        # Fetch all products from CIN7 API
        if progress_callback:
            progress_callback(0, 100, "Fetching products from CIN7 API...")

        if log_callback:
            log_callback('info', f'📡 Fetching {price_type} products from CIN7 API...', None)

        products, fetched, total = self.cin7_api.fetch_all_products(
            price_type=price_type,
            where_clause=None,
            progress_callback=progress_callback
        )

        logger.info(f"✓ Fetched {fetched} products from CIN7")
        if log_callback:
            log_callback('success', f'✓ Fetched {fetched} products from CIN7', {
                'fetched': fetched,
                'total': total
            })

        # Build lookup of existing products by cin7_id
        if log_callback:
            log_callback('info', '🔍 Building existing product lookup...', None)

        existing_products = {}
        for product in Cin7Product.objects.filter(price_type=price_type):
            key = (product.cin7_id, product.code)  # Use both cin7_id and code as key
            existing_products[key] = product

        logger.info(f"Found {len(existing_products)} existing products in database")
        if log_callback:
            log_callback('info', f'Found {len(existing_products)} existing products in database', {
                'existing_count': len(existing_products)
            })

        # Process products and detect changes
        if progress_callback:
            progress_callback(0, len(products), "Detecting changes...")

        if log_callback:
            log_callback('info', f'🔍 Comparing {len(products)} products with database...', {
                'product_count': len(products)
            })

        products_to_create = []
        products_to_update = []
        seen_cin7_ids = set()
        skipped_no_id = 0
        skipped_no_options = 0
        skipped_bs_products = 0
        unchanged_count = 0
        current_time = timezone.now()

        for index, cin7_product in enumerate(products, 1):
            if index % 500 == 0 and progress_callback:
                progress_callback(index, len(products), f"Processing {index}/{len(products)}...")

            # Extract all product options (variants)
            product_options = self.cin7_api.extract_product_options(cin7_product)

            if not product_options:
                skipped_no_options += 1
                continue

            # Process each variant
            for option_data in product_options:
                # Skip options without cin7_id
                if not option_data.get('cin7_id'):
                    skipped_no_id += 1
                    continue

                # Skip BS products (except for Bespoke)
                sku = option_data.get('sku') or ''
                style_code = option_data.get('style_code') or ''
                if price_type != 'Bespoke' and (sku.upper().startswith('BS') or style_code.upper().startswith('BS')):
                    skipped_bs_products += 1
                    continue

                # Skip BESPOKE ADDON products
                category_path = option_data.get('category', '').upper()
                product_name = option_data.get('product_name', '').upper()
                sku_upper = sku.upper()

                is_bespoke_addon = 'QUOTATION BASE LIBRARY' in category_path and any([
                    'SCREEN PRINT' in product_name or 'SCREEN PRINT' in sku_upper,
                    'HEAT TRANSFER' in product_name or 'HEAT TRANSFER' in sku_upper,
                    ('EMB' in sku_upper and ('EMBROIDERY' in product_name or 'APPLIQUE' in product_name)),
                ])

                if is_bespoke_addon:
                    skipped_bs_products += 1
                    continue

                # Get pricing data
                cost = option_data.get('cost')
                rrp = option_data.get('current_retail_nzd_incl')
                stock = option_data.get('stock_available')
                cin7_id = option_data.get('cin7_id')

                # Calculate data hash
                data_hash = self.calculate_product_hash(cost, rrp, stock)

                # Track that we've seen this cin7_id
                key = (cin7_id, sku)
                seen_cin7_ids.add(key)

                # Check if product exists
                existing = existing_products.get(key)

                if existing:
                    # Product exists - check if data has changed
                    if existing.data_hash != data_hash:
                        # Data changed - update record
                        existing.cost_nzd = cost
                        existing.retail_price = rrp
                        existing.stock_available = stock
                        existing.name = option_data.get('product_name') or ''
                        existing.category = option_data.get('category') or ''
                        existing.brand = option_data.get('brand') or ''
                        existing.barcode = option_data.get('barcode') or ''
                        existing.style_code = style_code
                        existing.data_hash = data_hash
                        existing.last_api_fetch = current_time
                        existing.fetch_session_id = session_id
                        existing.raw_data = cin7_product
                        products_to_update.append(existing)
                    else:
                        # Data unchanged - just update timestamps
                        existing.last_api_fetch = current_time
                        existing.fetch_session_id = session_id
                        products_to_update.append(existing)
                        unchanged_count += 1
                else:
                    # New product - create record
                    products_to_create.append(Cin7Product(
                        cin7_id=cin7_id,
                        code=sku,
                        style_code=style_code,
                        barcode=option_data.get('barcode') or '',
                        name=option_data.get('product_name') or '',
                        category=option_data.get('category') or '',
                        brand=option_data.get('brand') or '',
                        cost_nzd=cost,
                        retail_price=rrp,
                        stock_available=stock,
                        price_type=price_type,
                        fetch_session_id=session_id,
                        last_api_fetch=current_time,
                        data_hash=data_hash,
                        is_initial_sync=False,
                        raw_data=cin7_product
                    ))

        # Identify obsolete products (exist in DB but not in CIN7 response)
        obsolete_keys = set(existing_products.keys()) - seen_cin7_ids
        obsolete_count = len(obsolete_keys)

        # Perform database operations
        if log_callback:
            log_callback('info', f'💾 Applying changes to database...', {
                'new': len(products_to_create),
                'updated': len(products_to_update) - unchanged_count,
                'unchanged': unchanged_count,
                'obsolete': obsolete_count
            })

        with transaction.atomic():
            # Create new products
            if products_to_create:
                Cin7Product.objects.bulk_create(products_to_create, batch_size=500)
                logger.info(f"Created {len(products_to_create)} new products")

            # Update existing products
            if products_to_update:
                Cin7Product.objects.bulk_update(
                    products_to_update,
                    ['cost_nzd', 'retail_price', 'stock_available', 'name', 'category',
                     'brand', 'barcode', 'style_code', 'data_hash', 'last_api_fetch',
                     'fetch_session_id', 'raw_data'],
                    batch_size=500
                )
                logger.info(f"Updated {len(products_to_update)} existing products")

            # Delete obsolete products (optional - could mark as inactive instead)
            if obsolete_count > 0:
                obsolete_ids = [existing_products[key].id for key in obsolete_keys]
                Cin7Product.objects.filter(id__in=obsolete_ids).delete()
                logger.info(f"Deleted {obsolete_count} obsolete products")

        elapsed = (timezone.now() - start_time).total_seconds()

        # Prepare results
        results = {
            'success': True,
            'sync_mode': 'incremental',
            'session_id': session_id,
            'total_fetched': len(products),
            'new_products': len(products_to_create),
            'updated_products': len(products_to_update) - unchanged_count,
            'unchanged_products': unchanged_count,
            'obsolete_products': obsolete_count,
            'skipped_no_options': skipped_no_options,
            'skipped_bs_products': skipped_bs_products,
            'skipped_no_id': skipped_no_id,
            'duration_seconds': round(elapsed, 2),
            'price_type': price_type
        }

        logger.info(f"=== INCREMENTAL SYNC COMPLETE for {price_type} ===")
        logger.info(f"Total fetched: {len(products)}")
        logger.info(f"New: {len(products_to_create)}, Updated: {len(products_to_update) - unchanged_count}, Unchanged: {unchanged_count}, Obsolete: {obsolete_count}")
        logger.info(f"Duration: {elapsed:.2f}s")

        if log_callback:
            log_callback('success', f'✅ INCREMENTAL SYNC Complete', results)

        return results

    def sync(
        self,
        price_type: str,
        session_id: str,
        force_initial: bool = False,
        progress_callback=None,
        log_callback=None
    ) -> Dict:
        """
        Smart sync that automatically chooses initial or incremental mode.

        Args:
            price_type: Price type to sync
            session_id: Unique session identifier
            force_initial: Force initial sync even if records exist
            progress_callback: Optional callback(current, total, message)
            log_callback: Optional callback(level, message, details)

        Returns:
            Dict with sync results
        """
        # Determine sync mode
        sync_mode = self.determine_sync_mode(price_type, force_initial)

        # Perform appropriate sync
        if sync_mode == 'initial':
            return self.perform_initial_sync(
                price_type=price_type,
                session_id=session_id,
                progress_callback=progress_callback,
                log_callback=log_callback
            )
        else:
            return self.perform_incremental_sync(
                price_type=price_type,
                session_id=session_id,
                progress_callback=progress_callback,
                log_callback=log_callback
            )
