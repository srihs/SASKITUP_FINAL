import logging
import time
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone as dt_timezone
from dateutil import parser as date_parser
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone
from clubs.models import Club, ClubCategory, Product, ProductVariation, ProductCategoryAssignment
from clubs.services.woocommerce_service import WooCommerceService


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Comprehensive sync of LOTTO clubs data from WooCommerce API with intelligent change detection'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--store-type',
            type=str,
            default='LOTTO',
            choices=['LOTTO', 'SAS'],
            help='Store type to sync (default: LOTTO)'
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
        parser.add_argument(
            '--skip-images',
            action='store_true',
            help='Skip image URL storage (deprecated - URLs are now stored directly)'
        )
    
    def handle(self, *args, **options):
        """Main synchronization workflow with comprehensive error handling"""
        self.store_type = options['store_type']
        self.parent_category_id = options['parent_category_id']
        self.dry_run = options['dry_run']
        self.force_update = options['force_update']
        self.check_only = options['check_only']
        self.verbose = options['verbose']
        self.limit = options['limit']
        self.skip_images = options['skip_images']
        
        # Ensure we're only working with LOTTO for this command
        if self.store_type != 'LOTTO':
            raise CommandError("This command only supports LOTTO store type. Use 'LOTTO' for --store-type.")
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Starting {self.store_type} clubs comprehensive sync from WooCommerce...'
            )
        )
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        elif self.check_only:
            self.stdout.write(self.style.WARNING('CHECK ONLY MODE - Showing changes without applying them'))
        
        start_time = time.time()
        
        try:
            # Phase 1: Initialization
            self._phase_1_initialization()
            
            # Phase 2: Data Retrieval
            categories = self._phase_2_data_retrieval()
            
            if not categories:
                self.stdout.write(self.style.WARNING('No categories with products found'))
                return
            
            # Apply limit if specified
            if self.limit:
                categories = categories[:self.limit]
                self.stdout.write(f'Limited to first {self.limit} clubs')
            
            self.stdout.write(f'Found {len(categories)} categories to process')
            
            # Phase 3: Processing with comprehensive statistics
            stats = self._phase_3_processing(categories)
            
            # Generate comprehensive sync summary
            self._generate_sync_summary(stats, start_time)
            
        except Exception as e:
            logger.error(f"Command failed: {str(e)}")
            raise CommandError(f'Sync failed: {str(e)}')
    
    def _phase_1_initialization(self):
        """Phase 1: Initialize WooCommerce service and test connection"""
        self.stdout.write('Phase 1: Initializing WooCommerce service...')
        
        try:
            self.woo_service = WooCommerceService(store_type=self.store_type)
            
            # Test API connection
            if not self.woo_service.test_connection():
                raise CommandError(f'Failed to connect to {self.store_type} WooCommerce API')
            
            self.stdout.write(self.style.SUCCESS('✓ Successfully connected to WooCommerce API'))
            
        except Exception as e:
            logger.error(f"Phase 1 failed: {str(e)}")
            raise CommandError(f'Initialization failed: {str(e)}')
    
    def _phase_2_data_retrieval(self):
        """Phase 2: Retrieve categories with products from WooCommerce"""
        self.stdout.write('Phase 2: Fetching categories with products...')
        
        try:
            categories = self.woo_service.get_categories_with_products(parent_id=self.parent_category_id)
            self.stdout.write(self.style.SUCCESS(f'✓ Retrieved {len(categories)} categories with products'))
            return categories
            
        except Exception as e:
            logger.error(f"Phase 2 failed: {str(e)}")
            raise CommandError(f'Data retrieval failed: {str(e)}')
    
    def _phase_3_processing(self, categories):
        """Phase 3: Process all clubs, categories, products, and variations"""
        self.stdout.write('Phase 3: Processing clubs, categories, products, and variations...')
        
        # Initialize comprehensive statistics
        stats = {
            'clubs_created': 0, 'clubs_updated': 0, 'clubs_skipped': 0,
            'categories_created': 0, 'categories_updated': 0, 'categories_skipped': 0,
            'products_created': 0, 'products_updated': 0, 'products_skipped': 0,
            'variations_created': 0, 'variations_updated': 0, 'variations_skipped': 0,
            'errors': 0
        }
        
        for i, category_data in enumerate(categories, 1):
            self.stdout.write(f'\nProcessing club {i}/{len(categories)}: {category_data["name"]}')
            
            try:
                with transaction.atomic():
                    # Process club (atomic per club for error recovery)
                    club_stats = self._process_club(category_data)
                    self._update_stats(stats, club_stats, 'clubs')
                    
                    # Only proceed if we have a club to work with
                    if club_stats['club'] and not (self.dry_run or self.check_only):
                        # Process categories and products for this club
                        club_processing_stats = self._process_club_content(club_stats['club'], category_data)
                        self._update_stats(stats, club_processing_stats, 'all')
                
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"Error processing club {category_data['name']}: {str(e)}")
                self.stdout.write(
                    self.style.ERROR(f'Error processing club {category_data["name"]}: {str(e)}')
                )
                # Continue processing other clubs despite individual failures
                continue
        
        return stats
    
    def _process_club(self, category_data):
        """Process WooCommerce category as Club with comprehensive change detection"""
        woo_category_id = category_data['id']
        club_name = category_data['name']
        
        if self.dry_run:
            self.stdout.write(f'  [DRY RUN] Would process club: {club_name}')
            return {'result': 'created', 'club': None}
        
        # Check if club already exists
        existing_club = Club.objects.filter(woo_category_id=woo_category_id).first()
        
        # Prepare comprehensive club data
        new_club_data = {
            'name': club_name,
            'slug': slugify(club_name),
            'club_type': 'LOTTO',  # Always LOTTO for this model
            'sport_tag': self._determine_sport_tag(club_name),
            'woo_category_id': woo_category_id,
            'is_active': True,
        }
        
        # Extract additional data if available
        if category_data.get('description'):
            new_club_data['contact_person'] = category_data['description'][:100]  # Limit length
        
        # Handle logo image URL
        image_url = category_data.get('image', {}).get('src') if category_data.get('image') else None
        if image_url:
            new_club_data['logo'] = self.woo_service.get_image_url(image_url)
        
        if existing_club:
            if not self.force_update:
                # Intelligent change detection
                changes = self._detect_club_changes(existing_club, new_club_data, image_url)
                
                if not changes:
                    if self.verbose:
                        self.stdout.write(f'  Club unchanged: {existing_club.name}')
                    return {'result': 'skipped', 'club': existing_club}
                
                if self.verbose or self.check_only:
                    self.stdout.write(f'  Club changes detected for {existing_club.name}:')
                    for field, (old_val, new_val) in changes.items():
                        self.stdout.write(f'    - {field}: "{old_val}" → "{new_val}"')
                
                if self.check_only:
                    return {'result': 'would_update', 'club': existing_club}
            
            # Update existing club
            updated = self._update_club_if_changed(existing_club, new_club_data, image_url)
            
            if updated or self.force_update:
                self.stdout.write(f'  ✓ Updated club: {existing_club.name}')
                return {'result': 'updated', 'club': existing_club}
            else:
                return {'result': 'skipped', 'club': existing_club}
        else:
            # Create new club
            if self.check_only:
                self.stdout.write(f'  [CHECK] Would create club: {club_name}')
                return {'result': 'would_create', 'club': None}
            
            # Handle logo URL for new clubs
            if image_url:
                validated_url = self.woo_service.get_image_url(image_url)
                if validated_url:
                    new_club_data['logo'] = validated_url
                    self.stdout.write(f'    ✓ Set logo URL: {validated_url}')
                else:
                    self.stdout.write(f'    ⚠ Invalid logo URL for {club_name}')
            
            club = Club.objects.create(**new_club_data)
            self.stdout.write(f'  ✓ Created club: {club.name}')
            return {'result': 'created', 'club': club}
    
    def _process_club_content(self, club, category_data):
        """Process categories and products for a club"""
        stats = {
            'categories_created': 0, 'categories_updated': 0, 'categories_skipped': 0,
            'products_created': 0, 'products_updated': 0, 'products_skipped': 0,
            'variations_created': 0, 'variations_updated': 0, 'variations_skipped': 0
        }
        
        try:
            # Get subcategories for this club
            subcategories = self.woo_service.get_categories(parent_id=category_data['id'])
            
            if subcategories:
                # Process each subcategory
                for subcategory_data in subcategories:
                    if subcategory_data.get('count', 0) > 0:  # Only categories with products
                        category_stats = self._process_club_category(club, subcategory_data)
                        self._update_stats(stats, category_stats, 'categories')
                        
                        if category_stats['category']:
                            product_stats = self._process_category_products(
                                category_stats['category'], subcategory_data['id']
                            )
                            # Update product and variation statistics directly
                            for key in ['products_created', 'products_updated', 'products_skipped',
                                       'variations_created', 'variations_updated', 'variations_skipped']:
                                if key in product_stats:
                                    stats[key] += product_stats[key]
            else:
                # No subcategories - process products directly under main category
                category_stats = self._process_club_category(club, category_data)
                self._update_stats(stats, category_stats, 'categories')
                
                if category_stats['category']:
                    product_stats = self._process_category_products(
                        category_stats['category'], category_data['id']
                    )
                    # Update product and variation statistics directly
                    for key in ['products_created', 'products_updated', 'products_skipped',
                               'variations_created', 'variations_updated', 'variations_skipped']:
                        if key in product_stats:
                            stats[key] += product_stats[key]
        
        except Exception as e:
            logger.error(f"Error processing content for club {club.name}: {str(e)}")
            raise
        
        return stats
    
    def _process_club_category(self, club, category_data):
        """Process subcategory as ClubCategory with comprehensive change detection"""
        woo_category_id = category_data['id']
        category_name = category_data['name']
        
        # Check if category already exists
        existing_category = ClubCategory.objects.filter(woo_category_id=woo_category_id).first()
        
        # Prepare comprehensive category data
        new_category_data = {
            'club': club,
            'name': category_name,
            'slug': slugify(f"{club.name}-{category_name}"),
            'woo_category_id': woo_category_id,
            'description': category_data.get('description', ''),
            'product_count': category_data.get('count', 0),
        }
        
        # Handle category image URL
        image_url = category_data.get('image', {}).get('src') if category_data.get('image') else None
        if image_url:
            new_category_data['image'] = self.woo_service.get_image_url(image_url)
        
        if existing_category:
            if not self.force_update:
                # Intelligent change detection
                changes = self._detect_category_changes(existing_category, new_category_data, image_url)
                
                if not changes:
                    if self.verbose:
                        self.stdout.write(f'    Category unchanged: {existing_category.name}')
                    return {'result': 'skipped', 'category': existing_category}
                
                if self.verbose or self.check_only:
                    self.stdout.write(f'    Category changes detected for {existing_category.name}:')
                    for field, (old_val, new_val) in changes.items():
                        self.stdout.write(f'      - {field}: "{old_val}" → "{new_val}"')
                
                if self.check_only:
                    return {'result': 'would_update', 'category': existing_category}
            
            # Update existing category
            updated = self._update_category_if_changed(existing_category, new_category_data, image_url)
            
            if updated or self.force_update:
                self.stdout.write(f'    ✓ Updated category: {existing_category.name}')
                return {'result': 'updated', 'category': existing_category}
            else:
                return {'result': 'skipped', 'category': existing_category}
        else:
            # Create new category
            if self.check_only:
                self.stdout.write(f'    [CHECK] Would create category: {category_name}')
                return {'result': 'would_create', 'category': None}
            
            # Handle category image URL for new categories
            if image_url:
                validated_url = self.woo_service.get_image_url(image_url)
                if validated_url:
                    new_category_data['image'] = validated_url
                    self.stdout.write(f'      ✓ Set category image URL: {validated_url}')
                else:
                    self.stdout.write(f'      ⚠ Invalid category image URL for {category_name}')
            
            category = ClubCategory.objects.create(**new_category_data)
            self.stdout.write(f'    ✓ Created category: {category.name}')
            return {'result': 'created', 'category': category}
    
    def _process_category_products(self, category, category_id):
        """Process all products for a category"""
        stats = {
            'products_created': 0, 'products_updated': 0, 'products_skipped': 0,
            'variations_created': 0, 'variations_updated': 0, 'variations_skipped': 0
        }
        
        try:
            # Get products for this category
            products = self.woo_service.get_products_by_category(category_id)
            
            if not products:
                if self.verbose:
                    self.stdout.write(f'      No products found for category: {category.name}')
                return stats
            
            self.stdout.write(f'      Processing {len(products)} products for category: {category.name}')
            
            for product_data in products:
                try:
                    # Process individual product
                    product_stats = self._process_product(category, product_data)
                    self._update_stats(stats, product_stats, 'products')
                    
                    # Process variations if product is variable and we have a product
                    if (product_stats['product'] and 
                        self.woo_service.is_variable_product(product_data) and 
                        not (self.dry_run or self.check_only)):
                        
                        variation_stats = self._process_product_variations(
                            product_stats['product'], product_data
                        )
                        # Update variation statistics directly since _process_product_variations returns count dict
                        stats['variations_created'] += variation_stats['variations_created']
                        stats['variations_updated'] += variation_stats['variations_updated']
                        stats['variations_skipped'] += variation_stats['variations_skipped']
                
                except Exception as e:
                    logger.error(f"Error processing product {product_data.get('name', 'unknown')}: {str(e)}")
                    self.stdout.write(
                        self.style.ERROR(f'        Error processing product: {str(e)}')
                    )
                    continue
        
        except Exception as e:
            logger.error(f"Error processing products for category {category.name}: {str(e)}")
            raise
        
        return stats
    
    def _process_product(self, category, product_data):
        """Process product with multi-category support and comprehensive change detection"""
        woo_product_id = product_data['id']
        product_name = product_data['name']
        
        if self.dry_run:
            self.stdout.write(f'        [DRY RUN] Would process product: {product_name}')
            return {'result': 'created', 'product': None}
        
        # Check if product already exists (by WooCommerce ID)
        existing_product = Product.objects.filter(woo_product_id=woo_product_id).first()
        
        # Parse comprehensive product data (without category field)
        new_product_data = self._parse_comprehensive_product_data(product_data)
        
        # Handle primary product image URL
        images = product_data.get('images', [])
        image_url = images[0]['src'] if images else None
        if image_url:
            new_product_data['image'] = self.woo_service.get_image_url(image_url)
        
        if existing_product:
            if not self.force_update:
                # Comprehensive change detection for ALL fields
                changes = self._detect_product_changes(existing_product, new_product_data, image_url)
                
                if not changes:
                    if self.verbose:
                        self.stdout.write(f'        Product unchanged: {existing_product.name}')
                    # Still need to ensure category assignment exists
                    self._ensure_product_category_assignment(existing_product, category, product_data)
                    return {'result': 'skipped', 'product': existing_product}
                
                if self.verbose or self.check_only:
                    self.stdout.write(f'        Product changes detected for {existing_product.name}:')
                    for field, (old_val, new_val) in changes.items():
                        if field in ['price', 'regular_price', 'sale_price']:
                            self.stdout.write(f'          - {field}: {old_val} → {new_val}')
                        else:
                            old_str = str(old_val)[:50] + '...' if len(str(old_val)) > 50 else str(old_val)
                            new_str = str(new_val)[:50] + '...' if len(str(new_val)) > 50 else str(new_val)
                            self.stdout.write(f'          - {field}: "{old_str}" → "{new_str}"')
                
                if self.check_only:
                    return {'result': 'would_update', 'product': existing_product}
            
            # Update existing product
            updated = self._update_product_if_changed(existing_product, new_product_data, image_url)
            
            # Ensure category assignment exists
            self._ensure_product_category_assignment(existing_product, category, product_data)
            
            if updated or self.force_update:
                self.stdout.write(f'        ✓ Updated product: {existing_product.name}')
                return {'result': 'updated', 'product': existing_product}
            else:
                if self.verbose:
                    self.stdout.write(f'        Product unchanged: {existing_product.name}')
                return {'result': 'skipped', 'product': existing_product}
        else:
            # Create new product
            if self.check_only:
                self.stdout.write(f'        [CHECK] Would create product: {product_name}')
                return {'result': 'would_create', 'product': None}
            
            # Handle product image URL for new products  
            if image_url:
                validated_url = self.woo_service.get_image_url(image_url)
                if validated_url:
                    new_product_data['image'] = validated_url
                    if self.verbose:
                        self.stdout.write(f'          ✓ Set product image URL: {validated_url}')
                else:
                    if self.verbose:
                        self.stdout.write(f'          ⚠ Invalid product image URL for {product_name}')
            
            # Create product without categories first
            product = Product.objects.create(**new_product_data)
            
            # Create category assignment
            self._create_product_category_assignment(product, category, product_data, is_primary=True)
            
            self.stdout.write(f'        ✓ Created product: {product.name}')
            return {'result': 'created', 'product': product}
    
    def _parse_comprehensive_product_data(self, product_data):
        """Parse product data for regular Product model fields only (no category field)"""
        # Parse comprehensive pricing
        price_data = self._parse_product_prices(product_data)
        
        # Build product data with only fields that exist in regular Product model
        return {
            # Core fields
            'name': product_data['name'],
            'slug': slugify(f"{product_data['name']}-{product_data['id']}"),
            'woo_product_id': product_data['id'],
            
            # Pricing
            'price': price_data['price'],
            'regular_price': price_data['regular_price'],
            'sale_price': price_data['sale_price'],
            
            # Content
            'description': product_data.get('description', ''),
            'short_description': product_data.get('short_description', ''),
            'sku': product_data.get('sku', ''),
            
            # Inventory
            'stock_status': product_data.get('stock_status', 'instock'),
            
            # Shipping
            'weight': product_data.get('weight', ''),
            'dimensions': product_data.get('dimensions', {}),
            
            # Enhanced fields (JSON fields that exist in regular model)
            'tags': product_data.get('tags', []),
            'attributes': product_data.get('attributes', []),
        }
    
    def _parse_product_prices(self, product_data):
        """Parse and validate product prices from WooCommerce data with comprehensive error handling"""
        try:
            # Get the main price from WooCommerce (this is the actual selling price)
            woo_price = product_data.get('price', '0') or '0'
            price = Decimal(str(woo_price)) if woo_price else Decimal('0')
            
            # Parse regular_price (original price before discount)
            woo_regular_price = product_data.get('regular_price', '') or '0'
            regular_price = Decimal(str(woo_regular_price)) if woo_regular_price else price
            
            # Parse sale_price (discounted price)
            woo_sale_price = product_data.get('sale_price', '')
            sale_price = Decimal(str(woo_sale_price)) if woo_sale_price else None
            
            # Validate and correct pricing logic
            if price == 0 and regular_price > 0:
                price = regular_price
            
            # Ensure sale price is valid
            if sale_price and regular_price and sale_price >= regular_price:
                sale_price = None  # Invalid sale price
                
        except (InvalidOperation, ValueError, TypeError) as e:
            logger.warning(f"Price parsing error for product {product_data.get('name', 'unknown')}: {e}")
            regular_price = Decimal('0')
            sale_price = None
            price = Decimal('0')
        
        return {
            'price': price,
            'regular_price': regular_price,
            'sale_price': sale_price,
        }
    
    def _parse_woo_date(self, date_string):
        """Parse WooCommerce date with multiple methods and proper error handling"""
        if not date_string:
            return None
        
        try:
            # Try parsing with dateutil (handles most ISO formats)
            parsed_date = date_parser.parse(date_string)
            
            # Ensure timezone awareness
            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(tzinfo=dt_timezone.utc)
            
            return parsed_date
            
        except (ValueError, TypeError) as e:
            logger.warning(f"Date parsing failed for '{date_string}': {e}")
            return None
    
    def _dates_significantly_different(self, date1, date2, tolerance_seconds=60):
        """Check if two dates are significantly different (accounting for minor time differences)"""
        if date1 is None and date2 is None:
            return False
        if date1 is None or date2 is None:
            return True
        
        try:
            # Convert to timestamp for comparison
            timestamp1 = date1.timestamp() if hasattr(date1, 'timestamp') else 0
            timestamp2 = date2.timestamp() if hasattr(date2, 'timestamp') else 0
            
            return abs(timestamp1 - timestamp2) > tolerance_seconds
        except (AttributeError, TypeError):
            return True
    
    def _process_product_variations(self, product, product_data):
        """Process variations with deduplication and intelligent image selection"""
        stats = {
            'variations_created': 0, 'variations_updated': 0, 'variations_skipped': 0
        }
        
        try:
            # Get variations from WooCommerce
            variations_data = self.woo_service.get_product_variations(product_data['id'])
            
            if not variations_data:
                if self.verbose:
                    self.stdout.write(f'          No variations found for product: {product.name}')
                return stats
            
            self.stdout.write(f'          Processing {len(variations_data)} variations for: {product.name}')
            
            # Track processed variations by woo_variation_id to avoid true duplicates
            processed_variation_ids = set()
            
            for variation_data in variations_data:
                try:
                    # Skip if this WooCommerce variation ID has already been processed
                    woo_variation_id = variation_data.get('id', 0)
                    if woo_variation_id in processed_variation_ids:
                        if self.verbose:
                            self.stdout.write(f'            Skipping duplicate WooCommerce variation ID: {woo_variation_id}')
                        stats['variations_skipped'] += 1
                        continue
                    
                    processed_variation_ids.add(woo_variation_id)
                    
                    # Extract comprehensive variation data with multi-dimensional support
                    extracted_data = self._extract_multi_dimensional_variation_data(variation_data, product_data)
                    
                    # Process individual variation
                    variation_stats = self._process_individual_variation(
                        product, variation_data, product_data, extracted_data
                    )
                    # Update variation statistics directly
                    result = variation_stats['result']
                    if result in ['created', 'would_create']:
                        stats['variations_created'] += 1
                    elif result in ['updated', 'would_update']:
                        stats['variations_updated'] += 1
                    elif result == 'skipped':
                        stats['variations_skipped'] += 1
                
                except Exception as e:
                    # Handle case where variation_data is not a dict
                    if isinstance(variation_data, dict):
                        variation_id = variation_data.get('id', 'unknown')
                    else:
                        variation_id = f"invalid_data_type_{type(variation_data).__name__}"
                    
                    logger.error(f"Error processing variation {variation_id}: {str(e)}")
                    self.stdout.write(
                        self.style.ERROR(f'            Error processing variation {variation_id}: {str(e)}')
                    )
                    stats['variations_skipped'] += 1
                    continue
        
        except Exception as e:
            logger.error(f"Error processing variations for product {product.name}: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'          Error processing variations for {product.name}: {str(e)}')
            )
        
        return stats
    
    def _extract_multi_dimensional_variation_data(self, variation_data, product_data=None):
        """
        Extract variation data with proper multi-dimensional support.
        Creates consistent composite variation_value for variations with multiple attributes.
        """
        # Get the base extraction from WooCommerce service
        base_data = self.woo_service.extract_variation_data(variation_data, product_data)
        
        # Get all attributes for this variation
        attributes = base_data.get('attributes', {})
        
        if not attributes:
            # No attributes, return base data as-is but ensure we have valid variation_value
            if not base_data.get('variation_value'):
                base_data['variation_value'] = f"variation-{base_data.get('woo_variation_id', 'unknown')}"
                base_data['variation_type'] = 'other'
            return base_data
        
        # Filter out empty/None attribute values for consistency
        valid_attributes = {}
        for attr_name, attr_value in attributes.items():
            if attr_value and str(attr_value).strip():
                valid_attributes[attr_name] = str(attr_value).strip()
        
        if not valid_attributes:
            # No valid attributes, use fallback
            base_data['variation_value'] = f"variation-{base_data.get('woo_variation_id', 'unknown')}"
            base_data['variation_type'] = 'other'
            return base_data
        
        # Sort attributes by priority for consistent ordering
        attribute_priority = ['size', 'color', 'material', 'style', 'gender', 'age_group']
        
        # Sort attributes by priority, then alphabetically for unknown types
        sorted_attrs = []
        for priority_attr in attribute_priority:
            if priority_attr in valid_attributes:
                sorted_attrs.append((priority_attr, valid_attributes[priority_attr]))
        
        # Add any remaining attributes not in priority list (sorted alphabetically)
        remaining_attrs = [(k, v) for k, v in valid_attributes.items() if k not in attribute_priority]
        remaining_attrs.sort()  # Sort alphabetically for consistency
        sorted_attrs.extend(remaining_attrs)
        
        if sorted_attrs:
            # Create composite variation_value with consistent formatting
            if len(sorted_attrs) == 1:
                # Single attribute - use the value directly
                variation_value = sorted_attrs[0][1]
            else:
                # Multiple attributes - create composite (e.g., "3XL - Turquoise")
                variation_value = ' - '.join([attr_value for attr_name, attr_value in sorted_attrs])
            
            # Use the primary attribute type (first in priority order) as variation_type
            primary_type = sorted_attrs[0][0]
            
            # Update the extracted data with consistent formatting
            base_data['variation_type'] = primary_type
            base_data['variation_value'] = variation_value
            
            if self.verbose and len(sorted_attrs) > 1:
                attr_summary = ', '.join([f"{name}={value}" for name, value in sorted_attrs])
                self.stdout.write(f'            Multi-dimensional variation: {variation_value} ({attr_summary})')
        else:
            # Fallback case
            base_data['variation_value'] = f"variation-{base_data.get('woo_variation_id', 'unknown')}"
            base_data['variation_type'] = 'other'
        
        return base_data
    
    def _ensure_product_category_assignment(self, product, category, product_data):
        """Ensure product is assigned to category with proper metadata"""
        # Check if assignment already exists
        assignment, created = ProductCategoryAssignment.objects.get_or_create(
            product=product,
            category=category,
            defaults={
                'woo_category_id': category.woo_category_id,
                'is_primary': not product.categories.exists(),  # First category becomes primary
                'sort_order': 0,
            }
        )
        
        if created and self.verbose:
            primary_text = " (Primary)" if assignment.is_primary else ""
            self.stdout.write(f'          ✓ Assigned to category: {category.name}{primary_text}')
        
        return assignment
    
    def _create_product_category_assignment(self, product, category, product_data, is_primary=False):
        """Create a new product-category assignment"""
        assignment = ProductCategoryAssignment.objects.create(
            product=product,
            category=category,
            woo_category_id=category.woo_category_id,
            is_primary=is_primary,
            sort_order=0,
        )
        
        if self.verbose:
            primary_text = " (Primary)" if is_primary else ""
            self.stdout.write(f'          ✓ Assigned to category: {category.name}{primary_text}')
        
        return assignment
    
    def _process_individual_variation(self, product, variation_data, product_data, extracted_data):
        """Process individual product variation with intelligent change detection and duplicate prevention"""
        woo_variation_id = extracted_data['woo_variation_id']
        variation_type = extracted_data['variation_type']
        variation_value = extracted_data['variation_value']
        
        # Check if variation already exists by WooCommerce ID first
        existing_variation = ProductVariation.objects.filter(
            woo_variation_id=woo_variation_id
        ).first()
        
        # If not found by WooCommerce ID, check by unique constraint to handle duplicates
        if not existing_variation:
            existing_variation = ProductVariation.objects.filter(
                product=product,
                variation_type=variation_type,
                variation_value=variation_value
            ).first()
        
        # Prepare comprehensive variation data
        new_variation_data = {
            'product': product,
            'variation_type': variation_type,
            'variation_value': variation_value,
            'price_modifier': extracted_data['price_modifier'],
            'stock_quantity': extracted_data['stock_quantity'],
            'sku_suffix': extracted_data['sku_suffix'],
            'woo_variation_id': woo_variation_id,
            'is_active': extracted_data['is_active'],
            'attributes': extracted_data['attributes'],
            'weight': extracted_data['weight'],
            'dimensions': extracted_data['dimensions'],
        }
        
        # Get intelligent image data
        image_data = extracted_data.get('image_data', {})
        image_url = None
        
        # Use intelligent image selection from WooCommerce service
        if image_data.get('should_use_variation_image') and image_data.get('variation_image_url'):
            image_url = image_data['variation_image_url']
        elif image_data.get('fallback_image_url'):
            image_url = image_data['fallback_image_url']
        
        if self.verbose and image_data.get('image_strategy'):
            strategy = image_data['image_strategy']
            self.stdout.write(f'            Image strategy for {extracted_data["variation_value"]}: {strategy}')
        
        if existing_variation:
            if not self.force_update:
                # Intelligent change detection
                changes = self._detect_variation_changes(existing_variation, new_variation_data, image_url)
                
                if not changes:
                    if self.verbose:
                        self.stdout.write(f'            Variation unchanged: {existing_variation.variation_value}')
                    return {'result': 'skipped', 'variation': existing_variation}
                
                if self.verbose or self.check_only:
                    self.stdout.write(f'            Variation changes detected for {existing_variation.variation_value}:')
                    for field, (old_val, new_val) in changes.items():
                        self.stdout.write(f'              - {field}: "{old_val}" → "{new_val}"')
                
                if self.check_only:
                    return {'result': 'would_update', 'variation': existing_variation}
            
            # Update existing variation
            updated = self._update_variation_if_changed(existing_variation, new_variation_data, image_url)
            
            if updated or self.force_update:
                self.stdout.write(f'            ✓ Updated variation: {existing_variation.variation_value}')
                return {'result': 'updated', 'variation': existing_variation}
            else:
                if self.verbose:
                    self.stdout.write(f'            Variation unchanged: {existing_variation.variation_value}')
                return {'result': 'skipped', 'variation': existing_variation}
        else:
            # Create new variation with intelligent image handling and duplicate prevention
            if self.check_only:
                self.stdout.write(f'            [CHECK] Would create variation: {extracted_data["variation_value"]}')
                return {'result': 'would_create', 'variation': None}
            
            if image_url:
                validated_url = self.woo_service.get_image_url(image_url)
                if validated_url:
                    new_variation_data['image'] = validated_url
                    if self.verbose:
                        self.stdout.write(f'            ✓ Set variation image URL: {validated_url}')
                else:
                    if self.verbose:
                        self.stdout.write(f'            ⚠ Invalid variation image URL for {extracted_data["variation_value"]}')
            
            # Use get_or_create to avoid duplicate entries based on unique constraint
            try:
                variation, created = ProductVariation.objects.get_or_create(
                    product=product,
                    variation_type=variation_type,
                    variation_value=variation_value,
                    defaults=new_variation_data
                )
                
                if created:
                    self.stdout.write(f'            ✓ Created variation: {variation.variation_value}')
                    return {'result': 'created', 'variation': variation}
                else:
                    # Found existing variation by unique constraint, update WooCommerce ID if different
                    if variation.woo_variation_id != woo_variation_id:
                        if self.verbose:
                            self.stdout.write(f'            ⚠ Found existing variation with different WooCommerce ID: {variation.woo_variation_id} vs {woo_variation_id}')
                        
                        # Check if the new WooCommerce ID is already taken by another variation
                        conflicting_variation = ProductVariation.objects.filter(
                            woo_variation_id=woo_variation_id
                        ).exclude(id=variation.id).first()
                        
                        if conflicting_variation:
                            if self.verbose:
                                self.stdout.write(f'            ⚠ WooCommerce ID {woo_variation_id} already taken by variation: {conflicting_variation.variation_value}')
                            # Use a temporary high ID to avoid conflict (will be resolved in future syncs)
                            temp_id = 9999990000 + conflicting_variation.id  # Unique temporary ID
                            conflicting_variation.woo_variation_id = temp_id
                            conflicting_variation.save(update_fields=['woo_variation_id'])
                            if self.verbose:
                                self.stdout.write(f'            ⚠ Assigned temporary ID {temp_id} to conflicting variation')
                        
                        variation.woo_variation_id = woo_variation_id
                        variation.save(update_fields=['woo_variation_id'])
                    
                    # Check for other changes and update if needed
                    updated = self._update_variation_if_changed(variation, new_variation_data, image_url)
                    
                    if updated:
                        self.stdout.write(f'            ✓ Updated existing variation: {variation.variation_value}')
                        return {'result': 'updated', 'variation': variation}
                    else:
                        if self.verbose:
                            self.stdout.write(f'            Variation unchanged: {variation.variation_value}')
                        return {'result': 'skipped', 'variation': variation}
                        
            except Exception as e:
                logger.error(f"Error creating/updating variation {variation_value}: {str(e)}")
                self.stdout.write(
                    self.style.ERROR(f'            Error creating/updating variation {variation_value}: {str(e)}')
                )
                return {'result': 'skipped', 'variation': None}
    
    def _determine_sport_tag(self, club_name):
        """Intelligently determine sport tag from club name"""
        club_name_lower = club_name.lower()
        
        # Sport keywords mapping
        sport_keywords = {
            'Football': ['fc', 'football', 'united', 'city', 'town', 'rovers', 'wanderers', 'athletic'],
            'Rugby': ['rugby', 'rfc', 'bulls', 'stormers', 'sharks'],
            'Cricket': ['cricket', 'cc', 'eagles', 'cobras'],
            'Basketball': ['basketball', 'giants', 'suns'],
            'Tennis': ['tennis', 'tc'],
            'Hockey': ['hockey', 'hc'],
            'Netball': ['netball', 'nc'],
        }
        
        for sport, keywords in sport_keywords.items():
            if any(keyword in club_name_lower for keyword in keywords):
                return sport
        
        return 'Football'  # Default fallback
    
    def _detect_club_changes(self, existing_club, new_data, new_image_url):
        """Intelligent change detection for club data"""
        changes = {}
        
        # Check basic fields
        comparable_fields = ['name', 'sport_tag', 'contact_person', 'email', 'website', 'address', 'is_active']
        
        for field in comparable_fields:
            if field in new_data:
                current_value = getattr(existing_club, field, None)
                new_value = new_data[field]
                
                if current_value != new_value:
                    changes[field] = (current_value, new_value)
        
        # Check image URL change
        if new_image_url:
            current_image_url = existing_club.logo if existing_club.logo else None
            if current_image_url != new_image_url:
                changes['logo'] = (current_image_url, new_image_url)
        elif existing_club.logo:
            changes['logo'] = (existing_club.logo, None)
        
        return changes
    
    def _detect_category_changes(self, existing_category, new_data, new_image_url):
        """Intelligent change detection for category data"""
        changes = {}
        
        # Check basic fields
        comparable_fields = ['name', 'description', 'product_count']
        
        for field in comparable_fields:
            if field in new_data:
                current_value = getattr(existing_category, field, None)
                new_value = new_data[field]
                
                if current_value != new_value:
                    changes[field] = (current_value, new_value)
        
        # Check image URL change
        if new_image_url:
            current_image_url = existing_category.image if existing_category.image else None
            if current_image_url != new_image_url:
                changes['image'] = (current_image_url, new_image_url)
        elif existing_category.image:
            changes['image'] = (existing_category.image, None)
        
        return changes
    
    def _detect_product_changes(self, existing_product, new_data, new_image_url):
        """Change detection for regular Product model fields only"""
        changes = {}
        
        # Define comparable fields that exist in regular Product model
        comparable_fields = [
            'name', 'price', 'regular_price', 'sale_price', 'description', 
            'short_description', 'sku', 'stock_status', 'weight'
        ]
        
        for field in comparable_fields:
            if field in new_data:
                current_value = getattr(existing_product, field, None)
                new_value = new_data[field]
                
                # Special handling for decimal fields
                if field in ['price', 'regular_price', 'sale_price']:
                    try:
                        if current_value != new_value:
                            changes[field] = (current_value, new_value)
                    except Exception:
                        # If comparison fails, assume changed
                        changes[field] = (current_value, new_value)
                # Standard comparison for other fields
                elif current_value != new_value:
                    changes[field] = (current_value, new_value)
        
        # Check JSON fields that exist in regular model
        json_fields = ['dimensions', 'tags', 'attributes']
        
        for field in json_fields:
            if field in new_data:
                current_value = getattr(existing_product, field, None)
                new_value = new_data[field]
                
                # Simple comparison for JSON fields
                if str(current_value) != str(new_value):
                    changes[field] = (current_value, new_value)
        
        # Check image URL change
        if new_image_url:
            current_image_url = existing_product.image if existing_product.image else None
            if current_image_url != new_image_url:
                changes['image'] = (current_image_url, new_image_url)
        elif existing_product.image:
            changes['image'] = (existing_product.image, None)
        
        return changes
    
    def _detect_variation_changes(self, existing_variation, new_data, new_image_url):
        """Intelligent change detection for variation data"""
        changes = {}
        
        # Check basic fields
        comparable_fields = ['variation_type', 'variation_value', 'price_modifier', 'stock_quantity',
                           'sku_suffix', 'is_active', 'weight']
        
        for field in comparable_fields:
            if field in new_data:
                current_value = getattr(existing_variation, field, None)
                new_value = new_data[field]
                
                # Special handling for decimal fields
                if field == 'price_modifier':
                    try:
                        if current_value != new_value:
                            changes[field] = (current_value, new_value)
                    except Exception:
                        changes[field] = (current_value, new_value)
                elif current_value != new_value:
                    changes[field] = (current_value, new_value)
        
        # Check JSON fields
        json_fields = ['attributes', 'dimensions']
        for field in json_fields:
            if field in new_data:
                current_value = getattr(existing_variation, field, None)
                new_value = new_data[field]
                
                if str(current_value) != str(new_value):
                    changes[field] = (current_value, new_value)
        
        # Check variation image URL change
        if new_image_url:
            current_image_url = existing_variation.image if existing_variation.image else None
            if current_image_url != new_image_url:
                changes['image'] = (current_image_url, new_image_url)
        elif existing_variation.image:
            changes['image'] = (existing_variation.image, None)
        
        return changes
    
    # Image change detection methods removed - URLs are compared directly
    
    def _update_club_if_changed(self, existing_club, new_data, new_image_url):
        """Update club only if there are actual changes"""
        updated = False
        
        # Update basic fields
        for field, value in new_data.items():
            if field != 'logo' and hasattr(existing_club, field) and getattr(existing_club, field) != value:
                setattr(existing_club, field, value)
                updated = True
        
        # Handle logo URL update
        current_logo_url = existing_club.logo if existing_club.logo else None
        if new_image_url and current_logo_url != new_image_url:
            validated_url = self.woo_service.get_image_url(new_image_url)
            if validated_url:
                existing_club.logo = validated_url
                updated = True
                if self.verbose:
                    self.stdout.write(f'    ✓ Updated logo URL: {validated_url}')
            else:
                if self.verbose:
                    self.stdout.write(f'    ⚠ Invalid logo URL for {existing_club.name}')
        
        if updated:
            existing_club.save()
        
        return updated
    
    def _update_category_if_changed(self, existing_category, new_data, new_image_url):
        """Update category only if there are actual changes"""
        updated = False
        
        # Update basic fields
        for field, value in new_data.items():
            if field != 'image' and hasattr(existing_category, field) and getattr(existing_category, field) != value:
                setattr(existing_category, field, value)
                updated = True
        
        # Handle category image URL update
        current_image_url = existing_category.image if existing_category.image else None
        if new_image_url and current_image_url != new_image_url:
            validated_url = self.woo_service.get_image_url(new_image_url)
            if validated_url:
                existing_category.image = validated_url
                updated = True
                if self.verbose:
                    self.stdout.write(f'      ✓ Updated category image URL: {validated_url}')
            else:
                if self.verbose:
                    self.stdout.write(f'      ⚠ Invalid category image URL for {existing_category.name}')
        
        if updated:
            existing_category.save()
        
        return updated
    
    def _update_product_if_changed(self, existing_product, new_data, new_image_url):
        """Update product only if there are actual changes"""
        updated = False
        
        # Update basic fields
        for field, value in new_data.items():
            if field != 'image' and hasattr(existing_product, field) and getattr(existing_product, field) != value:
                setattr(existing_product, field, value)
                updated = True
        
        # Handle product image URL update
        current_image_url = existing_product.image if existing_product.image else None
        if new_image_url and current_image_url != new_image_url:
            validated_url = self.woo_service.get_image_url(new_image_url)
            if validated_url:
                existing_product.image = validated_url
                updated = True
                if self.verbose:
                    self.stdout.write(f'          ✓ Updated product image URL: {validated_url}')
            else:
                if self.verbose:
                    self.stdout.write(f'          ⚠ Invalid product image URL for {existing_product.name}')
        
        if updated:
            existing_product.save()
        
        return updated
    
    def _update_variation_if_changed(self, existing_variation, new_data, new_image_url):
        """Update variation only if there are actual changes"""
        updated = False
        
        # Update basic fields
        for field, value in new_data.items():
            if field != 'image' and hasattr(existing_variation, field) and getattr(existing_variation, field) != value:
                setattr(existing_variation, field, value)
                updated = True
        
        # Handle variation image URL update
        current_image_url = existing_variation.image if existing_variation.image else None
        if new_image_url and current_image_url != new_image_url:
            validated_url = self.woo_service.get_image_url(new_image_url)
            if validated_url:
                existing_variation.image = validated_url
                updated = True
                if self.verbose:
                    self.stdout.write(f'            ✓ Updated variation image URL: {validated_url}')
            else:
                if self.verbose:
                    self.stdout.write(f'            ⚠ Invalid variation image URL for {existing_variation.variation_value}')
        
        if updated:
            existing_variation.save()
        
        return updated
    
    def _update_stats(self, main_stats, operation_stats, operation_type):
        """Update main statistics with operation results"""
        if operation_type == 'clubs':
            result = operation_stats['result']
            if result in ['created', 'would_create']:
                main_stats['clubs_created'] += 1
            elif result in ['updated', 'would_update']:
                main_stats['clubs_updated'] += 1
            elif result == 'skipped':
                main_stats['clubs_skipped'] += 1
        
        elif operation_type == 'categories':
            result = operation_stats['result']
            if result in ['created', 'would_create']:
                main_stats['categories_created'] += 1
            elif result in ['updated', 'would_update']:
                main_stats['categories_updated'] += 1
            elif result == 'skipped':
                main_stats['categories_skipped'] += 1
        
        elif operation_type == 'products':
            result = operation_stats['result']
            if result in ['created', 'would_create']:
                main_stats['products_created'] += 1
            elif result in ['updated', 'would_update']:
                main_stats['products_updated'] += 1
            elif result == 'skipped':
                main_stats['products_skipped'] += 1
    
    def _generate_sync_summary(self, stats, start_time):
        """Generate comprehensive sync summary with efficiency metrics"""
        end_time = time.time()
        duration = end_time - start_time
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*50))
        self.stdout.write(self.style.SUCCESS('COMPREHENSIVE SYNC SUMMARY'))
        self.stdout.write(self.style.SUCCESS('='*50))
        
        # Basic statistics
        self.stdout.write(f'Duration: {duration:.2f} seconds')
        self.stdout.write('')
        
        # Club statistics
        self.stdout.write('CLUBS:')
        self.stdout.write(f'  Created: {stats["clubs_created"]}')
        self.stdout.write(f'  Updated: {stats["clubs_updated"]}')
        self.stdout.write(f'  Skipped (no changes): {stats["clubs_skipped"]}')
        
        # Category statistics
        self.stdout.write('\nCATEGORIES:')
        self.stdout.write(f'  Created: {stats["categories_created"]}')
        self.stdout.write(f'  Updated: {stats["categories_updated"]}')
        self.stdout.write(f'  Skipped (no changes): {stats["categories_skipped"]}')
        
        # Product statistics
        self.stdout.write('\nPRODUCTS:')
        self.stdout.write(f'  Created: {stats["products_created"]}')
        self.stdout.write(f'  Updated: {stats["products_updated"]}')
        self.stdout.write(f'  Skipped (no changes): {stats["products_skipped"]}')
        
        # Variation statistics
        self.stdout.write('\nVARIATIONS:')
        self.stdout.write(f'  Created: {stats["variations_created"]}')
        self.stdout.write(f'  Updated: {stats["variations_updated"]}')
        self.stdout.write(f'  Skipped (no changes): {stats["variations_skipped"]}')
        
        # Error statistics
        if stats["errors"] > 0:
            self.stdout.write(f'\nERRORS: {stats["errors"]}')
        
        # Calculate efficiency metrics
        total_operations = (stats["clubs_created"] + stats["clubs_updated"] + 
                           stats["categories_created"] + stats["categories_updated"] +
                           stats["products_created"] + stats["products_updated"] +
                           stats["variations_created"] + stats["variations_updated"])
        
        total_skipped = (stats["clubs_skipped"] + stats["categories_skipped"] + 
                        stats["products_skipped"] + stats["variations_skipped"])
        
        total_items = total_operations + total_skipped
        
        if total_items > 0:
            efficiency = (total_skipped / total_items) * 100
            self.stdout.write(f'\nEFFICIENCY METRICS:')
            self.stdout.write(f'  Total items processed: {total_items}')
            self.stdout.write(f'  Items requiring changes: {total_operations}')
            self.stdout.write(f'  Items unchanged (skipped): {total_skipped}')
            self.stdout.write(f'  Sync efficiency: {efficiency:.1f}% of items required no changes')
            
            if efficiency > 80:
                self.stdout.write(self.style.SUCCESS('  📊 Excellent sync efficiency! Most data was up-to-date.'))
            elif efficiency > 60:
                self.stdout.write(self.style.WARNING('  📊 Good sync efficiency. Some updates were needed.'))
            else:
                self.stdout.write('  📊 Major updates were performed. Consider running syncs more frequently.')
        
        # Final status message
        self.stdout.write('')
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN COMPLETED - No changes were made'))
        elif self.check_only:
            self.stdout.write(self.style.WARNING('CHECK ONLY COMPLETED - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('✅ COMPREHENSIVE SYNC COMPLETED SUCCESSFULLY!'))
        
        self.stdout.write(self.style.SUCCESS('='*50))