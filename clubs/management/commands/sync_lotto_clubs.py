import logging
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone
from clubs.models import Club, ClubCategory, Product, ProductVariation
from clubs.services.woocommerce_service import WooCommerceService


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync LOTTO clubs data from WooCommerce API'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--store-type',
            type=str,
            default='LOTTO',
            choices=['LOTTO', 'SAS'],
            help='Store type to sync (LOTTO or SAS)'
        )
        parser.add_argument(
            '--parent-category-id',
            type=int,
            default=23,
            help='Parent category ID for Club Shops (default: 23)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making changes to database'
        )
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Force update all records regardless of changes'
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Show what would be updated without making changes'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed change information'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of clubs to process'
        )
    
    def handle(self, *args, **options):
        store_type = options['store_type']
        parent_category_id = options['parent_category_id']
        dry_run = options['dry_run']
        force_update = options['force_update']
        check_only = options['check_only']
        verbose = options['verbose']
        limit = options['limit']
        
        # Store options for use in helper methods
        self.verbose = verbose
        self.check_only = check_only
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Starting {store_type} clubs sync from WooCommerce...'
            )
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        elif check_only:
            self.stdout.write(self.style.WARNING('CHECK ONLY MODE - Showing changes without applying them'))
        
        try:
            # Initialize WooCommerce service
            woo_service = WooCommerceService(store_type=store_type)
            
            # Test connection
            if not woo_service.test_connection():
                raise CommandError(f'Failed to connect to {store_type} WooCommerce API')
            
            # Get categories with products
            self.stdout.write('Fetching categories with products...')
            categories = woo_service.get_categories_with_products(parent_id=parent_category_id)
            
            if not categories:
                self.stdout.write(self.style.WARNING('No categories with products found'))
                return
            
            # Apply limit if specified
            if limit:
                categories = categories[:limit]
            
            self.stdout.write(f'Found {len(categories)} categories to process')
            
            # Process each category as a club
            clubs_created = 0
            clubs_updated = 0
            clubs_skipped = 0
            categories_created = 0
            categories_updated = 0
            categories_skipped = 0
            products_created = 0
            products_updated = 0
            products_skipped = 0
            variations_created = 0
            variations_updated = 0
            variations_skipped = 0
            
            for i, category_data in enumerate(categories, 1):
                self.stdout.write(f'\nProcessing club {i}/{len(categories)}: {category_data["name"]}')
                
                try:
                    with transaction.atomic():
                        # Process club
                        club, club_result = self._process_club(
                            category_data, store_type, woo_service, dry_run or check_only, force_update
                        )
                        
                        if club_result == 'created':
                            clubs_created += 1
                        elif club_result == 'updated':
                            clubs_updated += 1
                        elif club_result == 'skipped':
                            clubs_skipped += 1
                        
                        if not dry_run and not check_only and club:
                            # Get subcategories for this club
                            subcategories = woo_service.get_categories(parent_id=category_data['id'])
                            
                            for subcategory_data in subcategories:
                                if subcategory_data.get('count', 0) > 0:  # Only process categories with products
                                    category, category_result = self._process_club_category(
                                        club, subcategory_data, woo_service, dry_run or check_only, force_update
                                    )
                                    
                                    if category_result == 'created':
                                        categories_created += 1
                                    elif category_result == 'updated':
                                        categories_updated += 1
                                    elif category_result == 'skipped':
                                        categories_skipped += 1
                                    
                                    # Get products for this category
                                    products = woo_service.get_products_by_category(subcategory_data['id'])
                                    
                                    for product_data in products:
                                        product, product_result = self._process_product(
                                            category, product_data, woo_service, dry_run or check_only, force_update
                                        )
                                        
                                        if product_result == 'created':
                                            products_created += 1
                                        elif product_result == 'updated':
                                            products_updated += 1
                                        elif product_result == 'skipped':
                                            products_skipped += 1
                                        
                                        # Process variations if product is variable
                                        if not (dry_run or check_only) and product and woo_service.is_variable_product(product_data):
                                            var_created, var_updated, var_skipped = self._process_product_variations(
                                                product, product_data, woo_service, force_update
                                            )
                                            variations_created += var_created
                                            variations_updated += var_updated
                                            variations_skipped += var_skipped
                            
                            # If no subcategories, process products directly under the main category
                            if not subcategories:
                                category, category_result = self._process_club_category(
                                    club, category_data, woo_service, dry_run or check_only, force_update
                                )
                                
                                if category_result == 'created':
                                    categories_created += 1
                                elif category_result == 'updated':
                                    categories_updated += 1
                                elif category_result == 'skipped':
                                    categories_skipped += 1
                                
                                products = woo_service.get_products_by_category(category_data['id'])
                                
                                for product_data in products:
                                    product, product_result = self._process_product(
                                        category, product_data, woo_service, dry_run or check_only, force_update
                                    )
                                    
                                    if product_result == 'created':
                                        products_created += 1
                                    elif product_result == 'updated':
                                        products_updated += 1
                                    elif product_result == 'skipped':
                                        products_skipped += 1
                                    
                                    # Process variations if product is variable
                                    if not (dry_run or check_only) and product and woo_service.is_variable_product(product_data):
                                        var_created, var_updated, var_skipped = self._process_product_variations(
                                            product, product_data, woo_service, force_update
                                        )
                                        variations_created += var_created
                                        variations_updated += var_updated
                                        variations_skipped += var_skipped
                
                except Exception as e:
                    logger.error(f"Error processing club {category_data['name']}: {str(e)}")
                    self.stdout.write(
                        self.style.ERROR(f'Error processing club {category_data["name"]}: {str(e)}')
                    )
                    continue
            
            # Print summary
            self.stdout.write(self.style.SUCCESS('\n=== SYNC SUMMARY ==='))
            self.stdout.write(f'Clubs created: {clubs_created}')
            self.stdout.write(f'Clubs updated: {clubs_updated}')
            self.stdout.write(f'Clubs skipped (no changes): {clubs_skipped}')
            self.stdout.write(f'Categories created: {categories_created}')
            self.stdout.write(f'Categories updated: {categories_updated}')
            self.stdout.write(f'Categories skipped (no changes): {categories_skipped}')
            self.stdout.write(f'Products created: {products_created}')
            self.stdout.write(f'Products updated: {products_updated}')
            self.stdout.write(f'Products skipped (no changes): {products_skipped}')
            self.stdout.write(f'Variations created: {variations_created}')
            self.stdout.write(f'Variations updated: {variations_updated}')
            self.stdout.write(f'Variations skipped (no changes): {variations_skipped}')
            
            total_operations = clubs_created + clubs_updated + categories_created + categories_updated + products_created + products_updated + variations_created + variations_updated
            total_skipped = clubs_skipped + categories_skipped + products_skipped + variations_skipped
            
            if total_skipped > 0:
                efficiency = (total_skipped / (total_operations + total_skipped)) * 100 if (total_operations + total_skipped) > 0 else 0
                self.stdout.write(f'\nSync efficiency: {efficiency:.1f}% of items skipped (no changes needed)')
            
            if dry_run:
                self.stdout.write(self.style.WARNING('DRY RUN COMPLETED - No changes were made'))
            elif check_only:
                self.stdout.write(self.style.WARNING('CHECK ONLY COMPLETED - No changes were made'))
            else:
                self.stdout.write(self.style.SUCCESS('Sync completed successfully!'))
                
        except Exception as e:
            logger.error(f"Command failed: {str(e)}")
            raise CommandError(f'Sync failed: {str(e)}')
    
    def _process_club(self, category_data, store_type, woo_service, dry_run, force_update):
        """Process a club from category data with intelligent change detection"""
        woo_category_id = category_data['id']
        
        if dry_run:
            self.stdout.write(f'  [DRY RUN] Would process club: {category_data["name"]}')
            return None, 'created'
        
        # Check if club already exists
        existing_club = Club.objects.filter(woo_category_id=woo_category_id).first()
        
        # Prepare new club data
        new_club_data = {
            'name': category_data['name'],
            'club_type': store_type,
            'woo_category_id': woo_category_id,
            'is_active': True,
        }
        
        # Handle image URL for comparison
        image_url = category_data.get('image', {}).get('src') if category_data.get('image') else None
        
        if existing_club:
            if not force_update:
                # Detect changes
                changes = self._detect_club_changes(existing_club, new_club_data, image_url)
                
                if not changes:
                    if self.verbose:
                        self.stdout.write(f'  Club unchanged: {existing_club.name}')
                    return existing_club, 'skipped'
                
                if self.verbose:
                    self.stdout.write(f'  Club changes detected for {existing_club.name}:')
                    for field, (old_val, new_val) in changes.items():
                        self.stdout.write(f'    - {field}: "{old_val}" → "{new_val}"')
            
            # Update existing club
            updated = self._update_club_if_changed(existing_club, new_club_data, image_url, woo_service)
            
            if updated or force_update:
                self.stdout.write(f'  Updated club: {existing_club.name}')
                return existing_club, 'updated'
            else:
                self.stdout.write(f'  Club unchanged: {existing_club.name}')
                return existing_club, 'skipped'
        else:
            # Create new club
            if image_url:
                image_result = woo_service.download_image(
                    image_url,
                    'clubs',
                    f"{slugify(category_data['name'])}-logo.jpg"
                )
                if image_result:
                    filename, content_file = image_result
                    new_club_data['logo'] = content_file
            
            club = Club.objects.create(**new_club_data)
            self.stdout.write(f'  Created club: {club.name}')
            return club, 'created'
    
    def _process_club_category(self, club, category_data, woo_service, dry_run, force_update):
        """Process a club category with intelligent change detection"""
        woo_category_id = category_data['id']
        
        if dry_run:
            self.stdout.write(f'    [DRY RUN] Would process category: {category_data["name"]}')
            return None, 'created'
        
        # Check if category already exists
        existing_category = ClubCategory.objects.filter(woo_category_id=woo_category_id).first()
        
        # Prepare new category data
        new_category_data = {
            'club': club,
            'name': category_data['name'],
            'woo_category_id': woo_category_id,
            'description': category_data.get('description', ''),
            'product_count': category_data.get('count', 0),
        }
        
        # Handle image URL for comparison
        image_url = category_data.get('image', {}).get('src') if category_data.get('image') else None
        
        if existing_category:
            if not force_update:
                # Detect changes
                changes = self._detect_category_changes(existing_category, new_category_data, image_url)
                
                if not changes:
                    if self.verbose:
                        self.stdout.write(f'    Category unchanged: {existing_category.name}')
                    return existing_category, 'skipped'
                
                if self.verbose:
                    self.stdout.write(f'    Category changes detected for {existing_category.name}:')
                    for field, (old_val, new_val) in changes.items():
                        self.stdout.write(f'      - {field}: "{old_val}" → "{new_val}"')
            
            # Update existing category
            updated = self._update_category_if_changed(existing_category, new_category_data, image_url, woo_service)
            
            if updated or force_update:
                self.stdout.write(f'    Updated category: {existing_category.name}')
                return existing_category, 'updated'
            else:
                self.stdout.write(f'    Category unchanged: {existing_category.name}')
                return existing_category, 'skipped'
        else:
            # Create new category
            if image_url:
                image_result = woo_service.download_image(
                    image_url,
                    'categories',
                    f"{slugify(f'{club.name}-{category_data['name']}')}category.jpg"
                )
                if image_result:
                    filename, content_file = image_result
                    new_category_data['image'] = content_file
            
            category = ClubCategory.objects.create(**new_category_data)
            self.stdout.write(f'    Created category: {category.name}')
            return category, 'created'
    
    def _process_product(self, category, product_data, woo_service, dry_run, force_update):
        """Process a product with intelligent change detection"""
        woo_product_id = product_data['id']
        
        if dry_run:
            self.stdout.write(f'      [DRY RUN] Would process product: {product_data["name"]}')
            return None, 'created'
        
        # Check if product already exists
        existing_product = Product.objects.filter(woo_product_id=woo_product_id).first()
        
        # Parse prices with proper decimal handling
        price_data = self._parse_product_prices(product_data)
        
        # Prepare new product data
        new_product_data = {
            'category': category,
            'name': product_data['name'],
            'woo_product_id': woo_product_id,
            'price': price_data['price'],
            'regular_price': price_data['regular_price'],
            'sale_price': price_data['sale_price'],
            'description': product_data.get('description', ''),
            'short_description': product_data.get('short_description', ''),
            'sku': product_data.get('sku', ''),
            'stock_status': product_data.get('stock_status', 'instock'),
            'weight': product_data.get('weight', ''),
            'dimensions': product_data.get('dimensions', {}),
            'tags': [tag['name'] for tag in product_data.get('tags', [])],
            'attributes': product_data.get('attributes', []),
        }
        
        # Handle image URL for comparison
        images = product_data.get('images', [])
        image_url = images[0]['src'] if images else None
        
        if existing_product:
            if not force_update:
                # Detect changes
                changes = self._detect_product_changes(existing_product, new_product_data, image_url)
                
                if not changes:
                    if self.verbose:
                        self.stdout.write(f'      Product unchanged: {existing_product.name}')
                    return existing_product, 'skipped'
                
                if self.verbose:
                    self.stdout.write(f'      Product changes detected for {existing_product.name}:')
                    for field, (old_val, new_val) in changes.items():
                        if field in ['price', 'regular_price', 'sale_price']:
                            self.stdout.write(f'        - {field}: {old_val} → {new_val}')
                        else:
                            old_str = str(old_val)[:50] + '...' if len(str(old_val)) > 50 else str(old_val)
                            new_str = str(new_val)[:50] + '...' if len(str(new_val)) > 50 else str(new_val)
                            self.stdout.write(f'        - {field}: "{old_str}" → "{new_str}"')
            
            # Update existing product
            updated = self._update_product_if_changed(existing_product, new_product_data, image_url, woo_service)
            
            if updated or force_update:
                self.stdout.write(f'      Updated product: {existing_product.name}')
                return existing_product, 'updated'
            else:
                if self.verbose:
                    self.stdout.write(f'      Product unchanged: {existing_product.name}')
                return existing_product, 'skipped'
        else:
            # Create new product
            if image_url:
                image_result = woo_service.download_image(
                    image_url,
                    'products',
                    f"{slugify(f'{category.club.name}-{product_data['name']}')}product.jpg"
                )
                if image_result:
                    filename, content_file = image_result
                    new_product_data['image'] = content_file
            
            product = Product.objects.create(**new_product_data)
            self.stdout.write(f'      Created product: {product.name}')
            return product, 'created'
    
    def _parse_product_prices(self, product_data):
        """Parse and validate product prices from WooCommerce data"""
        try:
            # Get the main price from WooCommerce (this is the actual selling price)
            woo_price = product_data.get('price', '0') or '0'
            price = Decimal(woo_price) if woo_price else Decimal('0')
            
            # Parse regular_price (original price before discount)
            woo_regular_price = product_data.get('regular_price', '') or '0'
            regular_price = Decimal(woo_regular_price) if woo_regular_price else price
            
            # Parse sale_price (discounted price)
            woo_sale_price = product_data.get('sale_price', '')
            sale_price = Decimal(woo_sale_price) if woo_sale_price else None
            
            # If we still don't have a valid price, use regular_price as fallback
            if price == 0 and regular_price > 0:
                price = regular_price
                
        except (InvalidOperation, ValueError):
            regular_price = Decimal('0')
            sale_price = None
            price = Decimal('0')
        
        return {
            'price': price,
            'regular_price': regular_price,
            'sale_price': sale_price,
        }
    
    def _detect_club_changes(self, existing_club, new_data, new_image_url):
        """Detect changes in club data"""
        changes = {}
        
        # Check basic fields
        if existing_club.name != new_data['name']:
            changes['name'] = (existing_club.name, new_data['name'])
        
        if existing_club.club_type != new_data['club_type']:
            changes['club_type'] = (existing_club.club_type, new_data['club_type'])
        
        if existing_club.is_active != new_data['is_active']:
            changes['is_active'] = (existing_club.is_active, new_data['is_active'])
        
        # Check image URL change
        if new_image_url:
            current_image_name = existing_club.logo.name if existing_club.logo else None
            if self._has_image_changed(current_image_name, new_image_url):
                changes['logo'] = ('current image', 'new image from WooCommerce')
        elif existing_club.logo:
            changes['logo'] = ('current image', 'no image')
        
        return changes
    
    def _detect_category_changes(self, existing_category, new_data, new_image_url):
        """Detect changes in category data"""
        changes = {}
        
        # Check basic fields
        if existing_category.name != new_data['name']:
            changes['name'] = (existing_category.name, new_data['name'])
        
        if existing_category.description != new_data['description']:
            changes['description'] = (existing_category.description or '', new_data['description'])
        
        if existing_category.product_count != new_data['product_count']:
            changes['product_count'] = (existing_category.product_count, new_data['product_count'])
        
        # Check image URL change
        if new_image_url:
            current_image_name = existing_category.image.name if existing_category.image else None
            if self._has_image_changed(current_image_name, new_image_url):
                changes['image'] = ('current image', 'new image from WooCommerce')
        elif existing_category.image:
            changes['image'] = ('current image', 'no image')
        
        return changes
    
    def _detect_product_changes(self, existing_product, new_data, new_image_url):
        """Detect changes in product data"""
        changes = {}
        
        # Check basic fields
        if existing_product.name != new_data['name']:
            changes['name'] = (existing_product.name, new_data['name'])
        
        if existing_product.sku != new_data['sku']:
            changes['sku'] = (existing_product.sku or '', new_data['sku'])
        
        if existing_product.stock_status != new_data['stock_status']:
            changes['stock_status'] = (existing_product.stock_status, new_data['stock_status'])
        
        if existing_product.weight != new_data['weight']:
            changes['weight'] = (existing_product.weight or '', new_data['weight'])
        
        # Check prices with proper decimal comparison
        if existing_product.price != new_data['price']:
            changes['price'] = (existing_product.price, new_data['price'])
        
        if existing_product.regular_price != new_data['regular_price']:
            changes['regular_price'] = (existing_product.regular_price, new_data['regular_price'])
        
        # Handle sale_price - both could be None
        if existing_product.sale_price != new_data['sale_price']:
            changes['sale_price'] = (existing_product.sale_price, new_data['sale_price'])
        
        # Check descriptions
        if existing_product.description != new_data['description']:
            changes['description'] = (existing_product.description or '', new_data['description'])
        
        if existing_product.short_description != new_data['short_description']:
            changes['short_description'] = (existing_product.short_description or '', new_data['short_description'])
        
        # Check JSON fields
        if existing_product.dimensions != new_data['dimensions']:
            changes['dimensions'] = (existing_product.dimensions or {}, new_data['dimensions'])
        
        if existing_product.tags != new_data['tags']:
            changes['tags'] = (existing_product.tags or [], new_data['tags'])
        
        if existing_product.attributes != new_data['attributes']:
            changes['attributes'] = (existing_product.attributes or [], new_data['attributes'])
        
        # Check image URL change
        if new_image_url:
            current_image_name = existing_product.image.name if existing_product.image else None
            if self._has_image_changed(current_image_name, new_image_url):
                changes['image'] = ('current image', 'new image from WooCommerce')
        elif existing_product.image:
            changes['image'] = ('current image', 'no image')
        
        return changes
    
    def _has_image_changed(self, current_image_name, new_image_url):
        """Check if image has changed by comparing URL components"""
        if not current_image_name and not new_image_url:
            return False
        if not current_image_name or not new_image_url:
            return True
        
        # Extract filename from new URL for comparison
        import os
        from urllib.parse import urlparse
        
        try:
            parsed_url = urlparse(new_image_url)
            new_filename = os.path.basename(parsed_url.path)
            current_filename = os.path.basename(current_image_name)
            
            # Simple heuristic: if filenames are very different, assume change
            # This is imperfect but better than always re-downloading
            return new_filename not in current_filename and current_filename not in new_filename
        except:
            # If we can't parse, assume it changed to be safe
            return True
    
    def _update_club_if_changed(self, existing_club, new_data, new_image_url, woo_service):
        """Update club only if there are actual changes"""
        updated = False
        
        # Update basic fields
        for field, value in new_data.items():
            if field != 'logo' and getattr(existing_club, field) != value:
                setattr(existing_club, field, value)
                updated = True
        
        # Handle logo update
        if new_image_url and self._has_image_changed(
            existing_club.logo.name if existing_club.logo else None, new_image_url
        ):
            image_result = woo_service.download_image(
                new_image_url,
                'clubs',
                f"{slugify(new_data['name'])}-logo.jpg"
            )
            if image_result:
                filename, content_file = image_result
                existing_club.logo = content_file
                updated = True
        
        if updated:
            existing_club.save()
        
        return updated
    
    def _update_category_if_changed(self, existing_category, new_data, new_image_url, woo_service):
        """Update category only if there are actual changes"""
        updated = False
        
        # Update basic fields
        for field, value in new_data.items():
            if field != 'image' and getattr(existing_category, field) != value:
                setattr(existing_category, field, value)
                updated = True
        
        # Handle image update
        if new_image_url and self._has_image_changed(
            existing_category.image.name if existing_category.image else None, new_image_url
        ):
            image_result = woo_service.download_image(
                new_image_url,
                'categories',
                f"{slugify(f'{existing_category.club.name}-{new_data['name']}')}category.jpg"
            )
            if image_result:
                filename, content_file = image_result
                existing_category.image = content_file
                updated = True
        
        if updated:
            existing_category.save()
        
        return updated
    
    def _update_product_if_changed(self, existing_product, new_data, new_image_url, woo_service):
        """Update product only if there are actual changes"""
        updated = False
        
        # Update basic fields
        for field, value in new_data.items():
            if field != 'image' and getattr(existing_product, field) != value:
                setattr(existing_product, field, value)
                updated = True
        
        # Handle image update
        if new_image_url and self._has_image_changed(
            existing_product.image.name if existing_product.image else None, new_image_url
        ):
            image_result = woo_service.download_image(
                new_image_url,
                'products',
                f"{slugify(f'{existing_product.category.club.name}-{new_data['name']}')}product.jpg"
            )
            if image_result:
                filename, content_file = image_result
                existing_product.image = content_file
                updated = True
        
        if updated:
            # Only update the timestamp if we actually made changes
            existing_product.save()
        
        return updated
    
    def _process_product_variations(self, product, product_data, woo_service, force_update):
        """Process variations for a variable product"""
        variations_created = 0
        variations_updated = 0
        variations_skipped = 0
        
        try:
            # Get variations from WooCommerce
            variations_data = woo_service.get_product_variations(product_data['id'])
            
            if not variations_data:
                if self.verbose:
                    self.stdout.write(f'        No variations found for product: {product.name}')
                return variations_created, variations_updated, variations_skipped
            
            self.stdout.write(f'        Processing {len(variations_data)} variations for: {product.name}')
            
            # Track processed variations to avoid duplicates
            processed_variations = set()
            
            for variation_data in variations_data:
                try:
                    # Extract variation data
                    extracted_data = woo_service.extract_variation_data(variation_data, product_data)
                    woo_variation_id = extracted_data['woo_variation_id']
                    
                    # Create unique key for deduplication
                    variation_key = (
                        extracted_data['variation_type'],
                        extracted_data['variation_value']
                    )
                    
                    # Skip if we've already processed this variation type/value combination
                    if variation_key in processed_variations:
                        if self.verbose:
                            self.stdout.write(f'          Skipping duplicate variation: {extracted_data["variation_type"]} = {extracted_data["variation_value"]}')
                        continue
                    
                    processed_variations.add(variation_key)
                    
                    # Check if variation already exists
                    existing_variation = ProductVariation.objects.filter(
                        woo_variation_id=woo_variation_id
                    ).first()
                    
                    # Prepare new variation data
                    new_variation_data = {
                        'product': product,
                        'variation_type': extracted_data['variation_type'],
                        'variation_value': extracted_data['variation_value'],
                        'price_modifier': extracted_data['price_modifier'],
                        'stock_quantity': extracted_data['stock_quantity'],
                        'sku_suffix': extracted_data['sku_suffix'],
                        'woo_variation_id': woo_variation_id,
                        'is_active': extracted_data['is_active'],
                        'attributes': extracted_data['attributes'],
                        'weight': extracted_data['weight'],
                        'dimensions': extracted_data['dimensions'],
                    }
                    
                    # Get image data using intelligent logic
                    image_data = extracted_data.get('image_data', {})
                    image_url = None
                    
                    # Use intelligent image selection from WooCommerce service
                    if image_data.get('should_use_variation_image') and image_data.get('variation_image_url'):
                        image_url = image_data['variation_image_url']
                    elif image_data.get('fallback_image_url'):
                        image_url = image_data['fallback_image_url']
                    
                    if self.verbose and image_data.get('image_strategy'):
                        strategy = image_data['image_strategy']
                        self.stdout.write(f'          Image strategy for {extracted_data["variation_value"]}: {strategy}')
                    
                    if existing_variation:
                        if not force_update:
                            # Detect changes
                            changes = self._detect_variation_changes(existing_variation, new_variation_data, image_url)
                            
                            if not changes:
                                if self.verbose:
                                    self.stdout.write(f'          Variation unchanged: {existing_variation.variation_value}')
                                variations_skipped += 1
                                continue
                            
                            if self.verbose:
                                self.stdout.write(f'          Variation changes detected for {existing_variation.variation_value}:')
                                for field, (old_val, new_val) in changes.items():
                                    self.stdout.write(f'            - {field}: "{old_val}" → "{new_val}"')
                        
                        # Update existing variation
                        updated = self._update_variation_if_changed(existing_variation, new_variation_data, image_url, woo_service)
                        
                        if updated or force_update:
                            self.stdout.write(f'          Updated variation: {existing_variation.variation_value}')
                            variations_updated += 1
                        else:
                            if self.verbose:
                                self.stdout.write(f'          Variation unchanged: {existing_variation.variation_value}')
                            variations_skipped += 1
                    else:
                        # Create new variation with intelligent image handling
                        if image_url:
                            # Use the WooCommerce service's intelligent variation image download
                            image_result = woo_service.download_variation_image(
                                variation_data,
                                product_data,
                                product.name,
                                extracted_data['variation_value']
                            )
                            if image_result:
                                filename, content_file = image_result
                                new_variation_data['image'] = content_file
                                if self.verbose:
                                    self.stdout.write(f'          Downloaded variation image: {filename}')
                        
                        variation = ProductVariation.objects.create(**new_variation_data)
                        self.stdout.write(f'          Created variation: {variation.variation_value}')
                        variations_created += 1
                
                except Exception as e:
                    logger.error(f"Error processing variation {variation_data.get('id', 'unknown')}: {str(e)}")
                    self.stdout.write(
                        self.style.ERROR(f'          Error processing variation: {str(e)}')
                    )
                    continue
        
        except Exception as e:
            logger.error(f"Error processing variations for product {product.name}: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'        Error processing variations for {product.name}: {str(e)}')
            )
        
        return variations_created, variations_updated, variations_skipped
    
    def _detect_variation_changes(self, existing_variation, new_data, new_image_url):
        """Detect changes in variation data"""
        changes = {}
        
        # Check basic fields
        if existing_variation.variation_type != new_data['variation_type']:
            changes['variation_type'] = (existing_variation.variation_type, new_data['variation_type'])
        
        if existing_variation.variation_value != new_data['variation_value']:
            changes['variation_value'] = (existing_variation.variation_value, new_data['variation_value'])
        
        if existing_variation.price_modifier != new_data['price_modifier']:
            changes['price_modifier'] = (existing_variation.price_modifier, new_data['price_modifier'])
        
        if existing_variation.stock_quantity != new_data['stock_quantity']:
            changes['stock_quantity'] = (existing_variation.stock_quantity, new_data['stock_quantity'])
        
        if existing_variation.sku_suffix != new_data['sku_suffix']:
            changes['sku_suffix'] = (existing_variation.sku_suffix or '', new_data['sku_suffix'])
        
        if existing_variation.is_active != new_data['is_active']:
            changes['is_active'] = (existing_variation.is_active, new_data['is_active'])
        
        if existing_variation.weight != new_data['weight']:
            changes['weight'] = (existing_variation.weight or '', new_data['weight'])
        
        # Check JSON fields
        if existing_variation.attributes != new_data['attributes']:
            changes['attributes'] = (existing_variation.attributes or {}, new_data['attributes'])
        
        if existing_variation.dimensions != new_data['dimensions']:
            changes['dimensions'] = (existing_variation.dimensions or {}, new_data['dimensions'])
        
        # Intelligent image change detection
        if new_image_url:
            current_image_name = existing_variation.image.name if existing_variation.image else None
            if self._has_variation_image_changed(existing_variation, current_image_name, new_image_url):
                changes['image'] = ('current image', 'new image from WooCommerce')
        elif existing_variation.image:
            changes['image'] = ('current image', 'no image')
        
        return changes
    
    def _update_variation_if_changed(self, existing_variation, new_data, new_image_url, woo_service):
        """Update variation only if there are actual changes"""
        updated = False
        
        # Update basic fields
        for field, value in new_data.items():
            if field != 'image' and getattr(existing_variation, field) != value:
                setattr(existing_variation, field, value)
                updated = True
        
        # Handle image update with intelligent logic
        if new_image_url and self._has_image_changed(
            existing_variation.image.name if existing_variation.image else None, new_image_url
        ):
            # Get the variation data from WooCommerce to use intelligent image handling
            # We need to reconstruct some data for the intelligent download method
            variation_data = {
                'image': {'src': new_image_url} if new_image_url else None,
                'attributes': new_data.get('attributes', {})
            }
            
            product_data = {
                'images': [{'src': existing_variation.product.image.url}] if existing_variation.product.image else []
            }
            
            image_result = woo_service.download_variation_image(
                variation_data,
                product_data,
                existing_variation.product.name,
                new_data['variation_value']
            )
            if image_result:
                filename, content_file = image_result
                existing_variation.image = content_file
                updated = True
        
        if updated:
            existing_variation.save()
        
        return updated
    
    def _has_variation_image_changed(self, existing_variation, current_image_name, new_image_url):
        """Check if variation image has changed with intelligent logic"""
        # For variation types that should have unique images (color, style, material),
        # be more sensitive to changes
        if existing_variation.variation_type in ['color', 'style', 'material']:
            return self._has_image_changed(current_image_name, new_image_url)
        
        # For size/gender variations, only update if significantly different
        if not current_image_name and new_image_url:
            return True  # No current image but new one available
        
        if current_image_name and not new_image_url:
            return True  # Had image but no longer available
        
        if not current_image_name and not new_image_url:
            return False  # No change
        
        # Both exist, check if different using more stringent criteria for size variations
        return self._has_image_changed(current_image_name, new_image_url)