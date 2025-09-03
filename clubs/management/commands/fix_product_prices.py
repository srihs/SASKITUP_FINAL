import logging
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from clubs.models import Product
from clubs.services.woocommerce_service import WooCommerceService


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix product prices by re-syncing from WooCommerce API'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--store-type',
            type=str,
            default='LOTTO',
            choices=['LOTTO', 'SAS'],
            help='Store type to sync (LOTTO or SAS)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making changes to database'
        )
        parser.add_argument(
            '--zero-prices-only',
            action='store_true',
            help='Only fix products with zero or null prices'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of products to process'
        )
    
    def handle(self, *args, **options):
        store_type = options['store_type']
        dry_run = options['dry_run']
        zero_prices_only = options['zero_prices_only']
        limit = options['limit']
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Starting price fix for {store_type} products...'
            )
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        try:
            # Initialize WooCommerce service
            woo_service = WooCommerceService(store_type=store_type)
            
            # Test connection
            if not woo_service.test_connection():
                raise CommandError(f'Failed to connect to {store_type} WooCommerce API')
            
            # Get products to fix
            if zero_prices_only:
                products = Product.objects.filter(
                    category__club__club_type=store_type,
                    price__lte=0
                ).select_related('category__club')
            else:
                products = Product.objects.filter(
                    category__club__club_type=store_type
                ).select_related('category__club')
            
            if limit:
                products = products[:limit]
            
            self.stdout.write(f'Found {products.count()} products to process')
            
            # Process products
            products_updated = 0
            products_failed = 0
            
            for i, product in enumerate(products, 1):
                self.stdout.write(f'\nProcessing product {i}/{products.count()}: {product.name}')
                
                try:
                    # Get product data from WooCommerce
                    product_data = woo_service._make_request(f'products/{product.woo_product_id}')
                    
                    if not product_data:
                        self.stdout.write(self.style.ERROR(f'  Failed to fetch data from WooCommerce'))
                        products_failed += 1
                        continue
                    
                    # Parse prices using the same logic as the sync command
                    try:
                        # Get the main price from WooCommerce (this is the actual selling price)
                        woo_price = product_data.get('price', '0') or '0'
                        new_price = Decimal(woo_price) if woo_price else Decimal('0')
                        
                        # Parse regular_price (original price before discount)
                        woo_regular_price = product_data.get('regular_price', '') or '0'
                        new_regular_price = Decimal(woo_regular_price) if woo_regular_price else new_price
                        
                        # Parse sale_price (discounted price)
                        woo_sale_price = product_data.get('sale_price', '')
                        new_sale_price = Decimal(woo_sale_price) if woo_sale_price else None
                        
                        # If we still don't have a valid price, use regular_price as fallback
                        if new_price == 0 and new_regular_price > 0:
                            new_price = new_regular_price
                            
                    except (InvalidOperation, ValueError):
                        self.stdout.write(self.style.ERROR(f'  Failed to parse price data'))
                        products_failed += 1
                        continue
                    
                    # Show before/after
                    self.stdout.write(f'  Current price: ${product.price}')
                    self.stdout.write(f'  New price: ${new_price}')
                    self.stdout.write(f'  Regular price: ${new_regular_price}')
                    if new_sale_price:
                        self.stdout.write(f'  Sale price: ${new_sale_price}')
                    
                    if not dry_run:
                        # Update product
                        product.price = new_price
                        product.regular_price = new_regular_price
                        product.sale_price = new_sale_price
                        product.save()
                        
                        self.stdout.write(self.style.SUCCESS(f'  Updated product price'))
                        products_updated += 1
                    else:
                        self.stdout.write(f'  [DRY RUN] Would update product price')
                        products_updated += 1
                
                except Exception as e:
                    logger.error(f"Error processing product {product.name}: {str(e)}")
                    self.stdout.write(
                        self.style.ERROR(f'Error processing product {product.name}: {str(e)}')
                    )
                    products_failed += 1
                    continue
            
            # Print summary
            self.stdout.write(self.style.SUCCESS('\n=== PRICE FIX SUMMARY ==='))
            self.stdout.write(f'Products processed: {products.count()}')
            self.stdout.write(f'Products updated: {products_updated}')
            self.stdout.write(f'Products failed: {products_failed}')
            
            if dry_run:
                self.stdout.write(self.style.WARNING('DRY RUN COMPLETED - No changes were made'))
            else:
                self.stdout.write(self.style.SUCCESS('Price fix completed successfully!'))
                
        except Exception as e:
            logger.error(f"Command failed: {str(e)}")
            raise CommandError(f'Price fix failed: {str(e)}')