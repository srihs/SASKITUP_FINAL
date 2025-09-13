import logging
import time
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from clubs.models import Club, ClubCategory, Product, ProductCategoryAssignment, ProductVariation
from clubs.services.woocommerce_service import WooCommerceService


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Advanced multi-category sync of products from WooCommerce API'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--store-type',
            type=str,
            default='LOTTO',
            choices=['LOTTO', 'SAS'],
            help='Store type to sync (default: LOTTO)'
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
            '--verbose',
            action='store_true',
            help='Show detailed information'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of products to process'
        )
    
    def handle(self, *args, **options):
        """Main synchronization workflow for multi-category products"""
        self.store_type = options['store_type']
        self.dry_run = options['dry_run']
        self.force_update = options['force_update']
        self.verbose = options['verbose']
        self.limit = options['limit']
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Starting multi-category product sync from {self.store_type} WooCommerce...'
            )
        )
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        start_time = time.time()
        
        try:
            # Initialize WooCommerce service
            self.woo_service = WooCommerceService(store_type=self.store_type)
            
            if not self.woo_service.test_connection():
                raise CommandError(f'Failed to connect to {self.store_type} WooCommerce API')
            
            self.stdout.write(self.style.SUCCESS('✓ Connected to WooCommerce API'))
            
            # Fetch all products with their complete category information
            products_data = self._fetch_all_products_with_categories()
            
            if not products_data:
                self.stdout.write(self.style.WARNING('No products found'))
                return
            
            # Apply limit if specified
            if self.limit:
                products_data = products_data[:self.limit]
                self.stdout.write(f'Limited to first {self.limit} products')
            
            # Process products with multi-category support
            stats = self._process_multi_category_products(products_data)
            
            # Generate summary
            self._generate_summary(stats, start_time)
            
        except Exception as e:
            logger.error(f"Multi-category sync failed: {str(e)}")
            raise CommandError(f'Sync failed: {str(e)}')
    
    def _fetch_all_products_with_categories(self):
        """Fetch all products with complete category information from WooCommerce"""
        self.stdout.write('Fetching all products with category information...')
        
        all_products = []
        page = 1
        per_page = 100  # WooCommerce API limit
        
        while True:
            try:
                # Fetch products page
                products = self.woo_service._make_request(
                    'products',
                    params={
                        'page': page,
                        'per_page': per_page,
                        'status': 'publish',
                        'stock_status': ['instock', 'onbackorder']
                    }
                )
                
                if not products or len(products) == 0:
                    break
                
                self.stdout.write(f'  Fetched page {page}: {len(products)} products')
                all_products.extend(products)
                
                # Break if we got fewer products than requested (last page)
                if len(products) < per_page:
                    break
                
                page += 1
                
            except Exception as e:
                logger.error(f"Error fetching products page {page}: {str(e)}")
                break
        
        self.stdout.write(self.style.SUCCESS(f'✓ Fetched {len(all_products)} total products'))
        return all_products
    
    def _process_multi_category_products(self, products_data):
        """Process products with multi-category assignments"""
        self.stdout.write('Processing products with multi-category support...')
        
        stats = {
            'products_created': 0,
            'products_updated': 0,
            'products_skipped': 0,
            'assignments_created': 0,
            'assignments_updated': 0,
            'assignments_skipped': 0,
            'errors': 0
        }
        
        # Group products by categories to optimize database queries
        category_product_map = defaultdict(list)
        
        for product_data in products_data:
            # Extract all categories this product belongs to
            woo_categories = product_data.get('categories', [])
            
            for woo_category in woo_categories:
                woo_category_id = woo_category['id']
                category_product_map[woo_category_id].append(product_data)
        
        self.stdout.write(f'Found products across {len(category_product_map)} categories')
        
        # Process each category and its products
        for woo_category_id, category_products in category_product_map.items():
            try:
                # Find or skip this category
                category = ClubCategory.objects.filter(woo_category_id=woo_category_id).first()
                
                if not category:
                    if self.verbose:
                        self.stdout.write(f'  Skipping unknown category {woo_category_id}')
                    continue
                
                self.stdout.write(f'\\nProcessing {len(category_products)} products in category: {category.name}')
                
                # Process each product in this category
                for product_data in category_products:
                    try:
                        product_stats = self._process_product_with_categories(product_data, category)
                        
                        # Update statistics
                        for key in ['products_created', 'products_updated', 'products_skipped',
                                   'assignments_created', 'assignments_updated', 'assignments_skipped']:
                            if key in product_stats:
                                stats[key] += product_stats[key]
                    
                    except Exception as e:
                        stats['errors'] += 1
                        logger.error(f"Error processing product {product_data.get('name', 'unknown')}: {str(e)}")
                        self.stdout.write(
                            self.style.ERROR(f'  Error processing product: {str(e)}')
                        )
                        continue
            
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"Error processing category {woo_category_id}: {str(e)}")
                continue
        
        return stats
    
    def _process_product_with_categories(self, product_data, current_category):
        """Process a single product with all its category assignments"""
        woo_product_id = product_data['id']
        product_name = product_data['name']
        
        stats = {
            'products_created': 0,
            'products_updated': 0,
            'products_skipped': 0,
            'assignments_created': 0,
            'assignments_updated': 0,
            'assignments_skipped': 0
        }
        
        if self.dry_run:
            if self.verbose:
                self.stdout.write(f'    [DRY RUN] Would process product: {product_name}')
            stats['products_skipped'] = 1
            return stats
        
        try:
            # Check if product already exists
            existing_product = Product.objects.filter(woo_product_id=woo_product_id).first()
            
            # Parse product data
            product_data_parsed = self._parse_product_data(product_data)
            
            if existing_product:
                # Update existing product if needed
                if self.force_update or self._product_needs_update(existing_product, product_data_parsed):
                    self._update_product(existing_product, product_data_parsed)
                    stats['products_updated'] = 1
                    
                    if self.verbose:
                        self.stdout.write(f'    ✓ Updated product: {product_name}')
                else:
                    stats['products_skipped'] = 1
                
                product = existing_product
            else:
                # Create new product
                product = Product.objects.create(**product_data_parsed)
                stats['products_created'] = 1
                
                if self.verbose:
                    self.stdout.write(f'    ✓ Created product: {product_name}')
            
            # Process all category assignments for this product
            assignment_stats = self._process_category_assignments(product, product_data)
            
            # Add assignment stats
            for key in ['assignments_created', 'assignments_updated', 'assignments_skipped']:
                if key in assignment_stats:
                    stats[key] += assignment_stats[key]
        
        except Exception as e:
            logger.error(f"Error processing product {product_name}: {str(e)}")
            raise
        
        return stats
    
    def _process_category_assignments(self, product, product_data):
        """Process all category assignments for a product"""
        stats = {
            'assignments_created': 0,
            'assignments_updated': 0,
            'assignments_skipped': 0
        }
        
        # Get all WooCommerce categories for this product
        woo_categories = product_data.get('categories', [])
        
        # Track processed categories
        processed_category_ids = []
        
        for i, woo_category in enumerate(woo_categories):
            woo_category_id = woo_category['id']
            
            # Find Django category
            category = ClubCategory.objects.filter(woo_category_id=woo_category_id).first()
            
            if not category:
                if self.verbose:
                    self.stdout.write(f'      Warning: Category {woo_category_id} not found in Django')
                continue
            
            processed_category_ids.append(category.id)
            
            # Check if assignment already exists
            assignment, created = ProductCategoryAssignment.objects.get_or_create(
                product=product,
                category=category,
                defaults={
                    'woo_category_id': woo_category_id,
                    'is_primary': i == 0,  # First category is primary
                    'sort_order': i,
                }
            )
            
            if created:
                stats['assignments_created'] += 1
                if self.verbose:
                    primary_text = " (Primary)" if assignment.is_primary else ""
                    self.stdout.write(f'      ✓ Assigned to category: {category.name}{primary_text}')
            else:
                # Update assignment if needed
                needs_update = False
                
                if assignment.sort_order != i:
                    assignment.sort_order = i
                    needs_update = True
                
                if assignment.is_primary != (i == 0):
                    assignment.is_primary = (i == 0)
                    needs_update = True
                
                if needs_update or self.force_update:
                    assignment.save()
                    stats['assignments_updated'] += 1
                    
                    if self.verbose:
                        self.stdout.write(f'      ✓ Updated assignment: {category.name}')
                else:
                    stats['assignments_skipped'] += 1
        
        # Remove assignments that are no longer valid
        if not self.dry_run:
            removed_assignments = ProductCategoryAssignment.objects.filter(
                product=product
            ).exclude(category_id__in=processed_category_ids)
            
            removed_count = removed_assignments.count()
            if removed_count > 0:
                removed_assignments.delete()
                if self.verbose:
                    self.stdout.write(f'      ✓ Removed {removed_count} obsolete assignments')
        
        return stats
    
    def _parse_product_data(self, product_data):
        """Parse product data for Django Product model"""
        # Parse pricing
        price_data = self._parse_product_prices(product_data)
        
        # Handle product image
        images = product_data.get('images', [])
        image_url = images[0]['src'] if images else None
        if image_url:
            validated_image_url = self.woo_service.get_image_url(image_url)
        else:
            validated_image_url = None
        
        return {
            'name': product_data['name'],
            'slug': slugify(f"{product_data['name']}-{product_data['id']}"),
            'woo_product_id': product_data['id'],
            'price': price_data['price'],
            'regular_price': price_data['regular_price'],
            'sale_price': price_data['sale_price'],
            'description': product_data.get('description', ''),
            'short_description': product_data.get('short_description', ''),
            'sku': product_data.get('sku', ''),
            'stock_status': product_data.get('stock_status', 'instock'),
            'weight': product_data.get('weight', ''),
            'dimensions': product_data.get('dimensions', {}),
            'tags': product_data.get('tags', []),
            'attributes': product_data.get('attributes', []),
            'image': validated_image_url,
        }
    
    def _parse_product_prices(self, product_data):
        """Parse and validate product prices"""
        try:
            # Get the main price from WooCommerce
            woo_price = product_data.get('price', '0') or '0'
            price = Decimal(str(woo_price))
            
            # Parse regular_price
            woo_regular_price = product_data.get('regular_price', '') or '0'
            regular_price = Decimal(str(woo_regular_price)) if woo_regular_price else price
            
            # Parse sale_price
            woo_sale_price = product_data.get('sale_price', '')
            sale_price = Decimal(str(woo_sale_price)) if woo_sale_price else None
            
            # Validate pricing logic
            if price == 0 and regular_price > 0:
                price = regular_price
            
            # Ensure sale price is valid
            if sale_price and regular_price and sale_price >= regular_price:
                sale_price = None
                
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
    
    def _product_needs_update(self, existing_product, new_data):
        """Check if product needs updating"""
        # Compare key fields
        comparable_fields = [
            'name', 'price', 'regular_price', 'sale_price', 'description',
            'short_description', 'sku', 'stock_status', 'weight', 'image'
        ]
        
        for field in comparable_fields:
            if field in new_data:
                current_value = getattr(existing_product, field, None)
                new_value = new_data[field]
                
                # Special handling for decimal fields
                if field in ['price', 'regular_price', 'sale_price']:
                    try:
                        if current_value != new_value:
                            return True
                    except Exception:
                        return True
                elif current_value != new_value:
                    return True
        
        # Check JSON fields
        json_fields = ['dimensions', 'tags', 'attributes']
        for field in json_fields:
            if field in new_data:
                current_value = getattr(existing_product, field, None)
                new_value = new_data[field]
                
                if str(current_value) != str(new_value):
                    return True
        
        return False
    
    def _update_product(self, product, new_data):
        """Update product with new data"""
        for field, value in new_data.items():
            if hasattr(product, field):
                setattr(product, field, value)
        
        product.save()
    
    def _generate_summary(self, stats, start_time):
        """Generate comprehensive summary"""
        end_time = time.time()
        duration = end_time - start_time
        
        self.stdout.write(self.style.SUCCESS('\\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('MULTI-CATEGORY SYNC SUMMARY'))
        self.stdout.write(self.style.SUCCESS('='*60))
        
        self.stdout.write(f'Duration: {duration:.2f} seconds')
        self.stdout.write('')
        
        # Product statistics
        self.stdout.write('PRODUCTS:')
        self.stdout.write(f'  Created: {stats["products_created"]}')
        self.stdout.write(f'  Updated: {stats["products_updated"]}')
        self.stdout.write(f'  Skipped: {stats["products_skipped"]}')
        
        # Assignment statistics
        self.stdout.write('\\nCATEGORY ASSIGNMENTS:')
        self.stdout.write(f'  Created: {stats["assignments_created"]}')
        self.stdout.write(f'  Updated: {stats["assignments_updated"]}')
        self.stdout.write(f'  Skipped: {stats["assignments_skipped"]}')
        
        # Error statistics
        if stats["errors"] > 0:
            self.stdout.write(f'\\nERRORS: {stats["errors"]}')
        
        # Final status
        self.stdout.write('')
        if self.dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN COMPLETED - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('✅ MULTI-CATEGORY SYNC COMPLETED SUCCESSFULLY!'))
        
        self.stdout.write(self.style.SUCCESS('='*60))