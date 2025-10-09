import logging
import json
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from clubs.models import SyncJob
from schools.models_tus import (
    TUSLocation, TUSSchool, TUSGeneralCategory, TUSSchoolCategory,
    TUSProduct, TUSProductVariation, TUSProductCategoryAssignment
)
from schools.services.tus_woocommerce import TUSWooCommerceService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync TUS schools, categories and products from WooCommerce API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--job-id',
            type=str,
            help='UUID of existing SyncJob to use (passed from view)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without saving to database',
        )
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Force update existing records even if unchanged',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit the number of schools to process',
        )
        parser.add_argument(
            '--school',
            type=str,
            help='Sync only a specific school by name or slug',
        )
        parser.add_argument(
            '--analyze-only',
            action='store_true',
            help='Only analyze the category structure without syncing',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose logging',
        )

    def handle(self, *args, **options):
        """Main command handler"""
        # Configure logging
        if options['verbose']:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.INFO)

        self.dry_run = options['dry_run']
        self.force_update = options['force_update']
        self.limit = options.get('limit')
        self.specific_school = options.get('school')
        self.analyze_only = options['analyze_only']

        # Initialize service
        try:
            self.woo_service = TUSWooCommerceService()
        except ValueError as e:
            raise CommandError(f"Failed to initialize TUS WooCommerce service: {e}")

        # Test connection
        if not self.woo_service.test_connection():
            raise CommandError("Failed to connect to TUS WooCommerce API")

        self.stdout.write(self.style.SUCCESS("Successfully connected to TUS WooCommerce API"))

        # Analyze only mode
        if self.analyze_only:
            self.analyze_category_structure()
            return

        # Use existing sync job if provided (from view), otherwise create new one
        job_id = options.get('job_id')
        if job_id and not self.dry_run:
            try:
                self.sync_job = SyncJob.objects.get(id=job_id)
                logger.info(f"Using existing sync job {job_id}")
            except SyncJob.DoesNotExist:
                logger.warning(f"Sync job {job_id} not found, creating new one")
                self.sync_job = SyncJob.objects.create(
                    sync_type='tus',
                    status='pending',
                    current_step='Initializing sync'
                )
                self.sync_job.start()
        elif not self.dry_run:
            # Create new job only if running standalone (no job_id provided)
            self.sync_job = SyncJob.objects.create(
                sync_type='tus',
                status='pending',
                current_step='Initializing sync'
            )
            self.sync_job.start()
        else:
            self.sync_job = None

        try:
            # Run the sync
            self.run_sync()

            # Complete sync job
            if self.sync_job:
                self.sync_job.complete()
                self.stdout.write(self.style.SUCCESS(
                    f"Sync completed successfully! Job ID: {self.sync_job.id}"
                ))

        except Exception as e:
            logger.error(f"Sync failed: {e}", exc_info=True)
            if self.sync_job:
                self.sync_job.fail(str(e))
            raise CommandError(f"Sync failed: {e}")

    def analyze_category_structure(self):
        """Analyze and display the category structure"""
        self.stdout.write("Analyzing TUS category structure...")

        analysis = self.woo_service.analyze_category_hierarchy()

        # Display analysis
        self.stdout.write(f"\nTotal categories: {analysis['total_categories']}")
        self.stdout.write(f"Root categories: {len(analysis['root_categories'])}")

        # Show root categories
        self.stdout.write("\nRoot Categories:")
        for cat in analysis['root_categories']:
            self.stdout.write(f"  - {cat['name']} (ID: {cat['id']}, Products: {cat['count']})")

        # Identify locations and schools
        locations, schools = self.woo_service.identify_locations_and_schools()

        self.stdout.write(f"\nIdentified Locations: {len(locations)}")
        for loc in locations[:10]:  # Show first 10
            self.stdout.write(f"  - {loc['name']} (ID: {loc['id']})")

        self.stdout.write(f"\nIdentified Schools: {len(schools)}")
        for school in schools[:10]:  # Show first 10
            if 'location_name' in school:
                self.stdout.write(f"  - {school['name']} in {school['location_name']} (ID: {school['id']}, Products: {school['count']})")
            else:
                self.stdout.write(f"  - {school['name']} (ID: {school['id']}, Products: {school['count']})")

    def run_sync(self):
        """Run the main sync process with Phase 1 optimizations"""
        self.stdout.write("Starting TUS schools sync with bulk operations...")

        # Statistics
        self.stats = {
            'locations': {'created': 0, 'updated': 0, 'skipped': 0},
            'schools': {'created': 0, 'updated': 0, 'skipped': 0},
            'general_categories': {'created': 0, 'updated': 0, 'skipped': 0},
            'school_categories': {'created': 0, 'updated': 0, 'skipped': 0},
            'products': {'created': 0, 'updated': 0, 'skipped': 0},
            'variations': {'created': 0, 'updated': 0, 'skipped': 0},
        }

        # PHASE 1: PRE-LOAD EXISTING DATA FOR FAST LOOKUPS
        self.stdout.write("Pre-loading existing data for optimization...")

        # Pre-load all existing products by WooCommerce ID
        self.existing_products = {
            p.woo_product_id: p
            for p in TUSProduct.objects.all()
        }
        self.stdout.write(f"Loaded {len(self.existing_products)} existing products")

        # Pre-load all existing variations
        # Key must match the database unique constraint: (product_id, variation_type, variation_value)
        self.existing_variations = {}
        for v in TUSProductVariation.objects.select_related('product').all():
            key = (v.product.woo_product_id, v.variation_type, v.variation_value)
            self.existing_variations[key] = v
        self.stdout.write(f"Loaded {len(self.existing_variations)} existing variations")

        # Pre-load existing SKUs for fast duplicate checking
        self.existing_skus = set(
            TUSProduct.objects.exclude(sku='').exclude(sku__isnull=True)
            .values_list('sku', flat=True)
        )
        self.stdout.write(f"Loaded {len(self.existing_skus)} existing SKUs")

        # Initialize batches for bulk operations
        self.products_to_create = []
        self.products_to_update = []
        self.variations_to_create = []
        self.variations_to_update = []
        self.assignments_to_create = []

        # Track products being created in this batch (by woo_product_id)
        self.products_being_created = {}

        # Get all categories
        all_categories = self.woo_service.get_all_categories()
        category_map = {cat['id']: cat for cat in all_categories}

        # Wrap in transaction
        try:
            with transaction.atomic():
                # Process categories hierarchically
                self.process_locations(all_categories, category_map)
                self.process_general_categories(all_categories, category_map)

                # FINAL BATCH SAVE - Save any remaining items
                self.stdout.write("\nSaving final batch...")
                self.save_batches(force=True)

                # Update product counts for all categories
                self.stdout.write("Updating category product counts...")
                self.update_all_category_counts()

                # Rollback if dry run
                if self.dry_run:
                    self.stdout.write(self.style.WARNING("DRY RUN - Rolling back transaction"))
                    transaction.set_rollback(True)

        except Exception as e:
            logger.error(f"Sync failed: {e}", exc_info=True)
            raise

        # Display statistics
        self.display_statistics()

    def process_locations(self, categories: List[Dict], category_map: Dict):
        """Process location categories"""
        self.stdout.write("\nProcessing locations...")

        # Identify location categories
        location_keywords = [
            # Actual TUS store locations
            'manukau', 'papakura', 'pukekohe', 'avondale', 'penrose',
            'kerikeri', 'pakuranga', 'rotorua', 'cambridge', 'helensville',
            'kaitaia', 'long bay', 'matamata', 'mt albert', 'north harbour'
        ]

        locations_processed = 0

        for category in categories:
            if category['parent'] == 0:  # Root level category
                name_lower = category['name'].lower()
                slug_lower = category['slug'].lower()

                # Check if it's a location
                is_location = any(
                    keyword in name_lower or keyword in slug_lower
                    for keyword in location_keywords
                )

                if is_location:
                    location = self.process_location(category)
                    if location:
                        locations_processed += 1
                        # Process schools under this location
                        self.process_schools_for_location(location, categories, category_map)

                    if self.limit and locations_processed >= self.limit:
                        break

    def process_location(self, category_data: Dict) -> Optional[TUSLocation]:
        """Process a single location category"""
        try:
            if self.dry_run:
                self.stdout.write(f"[DRY RUN] Would process location: {category_data['name']}")
                return None

            with transaction.atomic():
                defaults = {
                    'name': category_data['name'],
                    'description': category_data.get('description', ''),
                    'image_url': category_data.get('image', {}).get('src', '') if category_data.get('image') else '',
                    'is_active': True,
                }

                location, created = TUSLocation.objects.update_or_create(
                    woo_category_id=category_data['id'],
                    defaults=defaults
                )

                if created:
                    self.stats['locations']['created'] += 1
                    self.stdout.write(self.style.SUCCESS(f"Created location: {location.name}"))
                    if self.sync_job:
                        self.sync_job.add_log_message(f"Created location: {location.name}")
                else:
                    self.stats['locations']['updated'] += 1
                    logger.debug(f"Updated location: {location.name}")

                return location

        except Exception as e:
            logger.error(f"Error processing location {category_data['name']}: {e}")
            self.stats['locations']['skipped'] += 1
            return None

    def process_schools_for_location(self, location: TUSLocation, categories: List[Dict], category_map: Dict):
        """Process schools under a specific location"""
        school_keywords = [
            'college', 'school', 'high', 'primary', 'intermediate',
            'academy', 'grammar', 'preparatory', 'kindergarten', 'kura'
        ]

        for category in categories:
            if category['parent'] == location.woo_category_id:
                name_lower = category['name'].lower()

                # Check if it's a school
                is_school = any(keyword in name_lower for keyword in school_keywords)

                if is_school or category['count'] > 0:  # Has products, likely a school
                    school = self.process_school(category, location)
                    if school:
                        # Process categories under this school
                        self.process_school_categories(school, categories, category_map)

                        # IMPORTANT: Also process products directly assigned to the school category
                        # Many schools have products directly in the school category without subcategories
                        if category['count'] > 0:
                            # Create a default school category for products directly in the school
                            self.process_products_directly_in_school(school, category)

    def process_school(self, category_data: Dict, location: TUSLocation) -> Optional[TUSSchool]:
        """Process a single school category"""
        try:
            if self.specific_school:
                # Check if this is the specific school requested
                if (self.specific_school.lower() not in category_data['name'].lower() and
                    self.specific_school.lower() not in category_data['slug'].lower()):
                    return None

            if self.dry_run:
                self.stdout.write(f"[DRY RUN] Would process school: {category_data['name']} in {location.name}")
                return None

            with transaction.atomic():
                # Determine school type based on name
                school_type = self.determine_school_type(category_data['name'])

                defaults = {
                    'name': category_data['name'],
                    'location': location,
                    'school_type': school_type,
                    'logo_url': category_data.get('image', {}).get('src', '') if category_data.get('image') else '',
                    'is_active': True,
                }

                school, created = TUSSchool.objects.update_or_create(
                    woo_category_id=category_data['id'],
                    defaults=defaults
                )

                if created:
                    self.stats['schools']['created'] += 1
                    self.stdout.write(self.style.SUCCESS(f"Created school: {school.name} in {location.name}"))
                    if self.sync_job:
                        self.sync_job.add_log_message(f"Created school: {school.name}")
                else:
                    self.stats['schools']['updated'] += 1
                    logger.debug(f"Updated school: {school.name}")

                return school

        except Exception as e:
            logger.error(f"Error processing school {category_data['name']}: {e}")
            self.stats['schools']['skipped'] += 1
            return None

    def determine_school_type(self, school_name: str) -> str:
        """Determine school type based on name"""
        name_lower = school_name.lower()

        if 'primary' in name_lower:
            return 'Primary'
        elif 'intermediate' in name_lower:
            return 'Intermediate'
        elif 'college' in name_lower or 'high' in name_lower or 'grammar' in name_lower:
            return 'Secondary'
        elif 'kindergarten' in name_lower or 'early' in name_lower:
            return 'Early Childhood'
        elif 'tertiary' in name_lower or 'university' in name_lower or 'polytechnic' in name_lower:
            return 'Tertiary'
        else:
            return 'Secondary'  # Default to secondary

    def process_school_categories(self, school: TUSSchool, categories: List[Dict], category_map: Dict):
        """Process categories under a school with parallel product fetching"""

        # Collect all category IDs for this school
        school_category_ids = []
        school_categories_map = {}

        for category in categories:
            if category['parent'] == school.woo_category_id:
                school_category = self.process_school_category(category, school)
                if school_category:
                    school_category_ids.append(category['id'])
                    school_categories_map[category['id']] = school_category

        # Fetch products for all categories in parallel
        if school_category_ids:
            self.stdout.write(f"Fetching products for {len(school_category_ids)} categories in parallel...")
            products_by_category = self.woo_service.get_products_by_categories_parallel(
                school_category_ids,
                max_workers=5
            )

            # Process products for each category
            for cat_id, products in products_by_category.items():
                school_category = school_categories_map[cat_id]
                self.stdout.write(f"Processing {len(products)} products for {school_category.name}")

                for product_data in products:
                    self.process_product(product_data, school_category, is_school_category=True)

                # Save batch after each category
                self.save_batches(force=False)

    def process_products_directly_in_school(self, school: TUSSchool, school_category_data: Dict):
        """
        Process products that are directly assigned to the school category (no subcategories)
        Creates a default category for the school and assigns products to it
        """
        try:
            # Check if we already have a general category for this school
            default_category_name = "General"

            # Check if we already have a school category using the school's WooCommerce ID
            # (this handles the case where products are directly in the school category)
            existing_category = TUSSchoolCategory.objects.filter(
                school=school,
                woo_category_id=school.woo_category_id
            ).first()

            if existing_category:
                # Update existing category
                school_category = existing_category
                school_category.product_count = school_category_data.get('count', 0)
                school_category.save()
                created = False
                self.stats['school_categories']['updated'] += 1
                logger.debug(f"Updated existing category for school: {school.name}")
            else:
                # Create new category using school's WooCommerce ID
                school_category, created = TUSSchoolCategory.objects.get_or_create(
                    school=school,
                    name=default_category_name,
                    defaults={
                        'woo_category_id': school.woo_category_id,  # Use school's WooCommerce ID
                        'description': f'General products for {school.name}',
                        'product_count': school_category_data.get('count', 0),
                    }
                )

            if created:
                self.stats['school_categories']['created'] += 1
                self.stdout.write(self.style.SUCCESS(f"Created default category for school: {school.name}"))
                if self.sync_job:
                    self.sync_job.add_log_message(f"Created default category for school: {school.name}")
            else:
                # Update product count
                school_category.product_count = school_category_data.get('count', 0)
                school_category.save()
                self.stats['school_categories']['updated'] += 1
                logger.debug(f"Updated default category for school: {school.name}")

            # Now process products directly in the school category
            self.process_products_for_category(school_category, is_school_category=True)

        except Exception as e:
            logger.error(f"Error processing products directly in school {school.name}: {e}")
            return None

    def process_school_category(self, category_data: Dict, school: TUSSchool) -> Optional[TUSSchoolCategory]:
        """Process a single school category"""
        try:
            if self.dry_run:
                self.stdout.write(f"[DRY RUN] Would process category: {category_data['name']} for {school.name}")
                return None

            with transaction.atomic():
                defaults = {
                    'name': category_data['name'],
                    'school': school,
                    'description': category_data.get('description', ''),
                    'image_url': category_data.get('image', {}).get('src', '') if category_data.get('image') else '',
                    'product_count': category_data.get('count', 0),
                }

                category, created = TUSSchoolCategory.objects.update_or_create(
                    woo_category_id=category_data['id'],
                    defaults=defaults
                )

                if created:
                    self.stats['school_categories']['created'] += 1
                    logger.info(f"Created category: {category.name} for {school.name}")
                else:
                    self.stats['school_categories']['updated'] += 1
                    logger.debug(f"Updated category: {category.name}")

                return category

        except Exception as e:
            logger.error(f"Error processing category {category_data['name']}: {e}")
            self.stats['school_categories']['skipped'] += 1
            return None

    def process_general_categories(self, categories: List[Dict], category_map: Dict):
        """Process general categories (not location/school specific)"""
        self.stdout.write("\nProcessing general categories...")

        # Keywords that indicate general categories
        general_keywords = [
            'accessories', 'bags', 'footwear', 'sports', 'uniform',
            'general', 'all schools', 'stationery', 'equipment'
        ]

        for category in categories:
            if category['parent'] == 0:  # Root level
                name_lower = category['name'].lower()

                # Check if it's a general category
                is_general = any(keyword in name_lower for keyword in general_keywords)

                # Also check if it's not a location or school
                is_location = 'auckland' in name_lower or 'wellington' in name_lower  # etc.
                is_school = 'college' in name_lower or 'school' in name_lower

                if is_general and not is_location and not is_school:
                    general_category = self.process_general_category(category, parent=None)
                    if general_category:
                        # Process subcategories
                        self.process_general_subcategories(general_category, categories, category_map)

    def process_general_category(self, category_data: Dict, parent: Optional[TUSGeneralCategory]) -> Optional[TUSGeneralCategory]:
        """Process a single general category"""
        try:
            if self.dry_run:
                self.stdout.write(f"[DRY RUN] Would process general category: {category_data['name']}")
                return None

            with transaction.atomic():
                defaults = {
                    'name': category_data['name'],
                    'parent_category': parent,
                    'description': category_data.get('description', ''),
                    'image_url': category_data.get('image', {}).get('src', '') if category_data.get('image') else '',
                    'product_count': category_data.get('count', 0),
                    'is_active': True,
                }

                category, created = TUSGeneralCategory.objects.update_or_create(
                    woo_category_id=category_data['id'],
                    defaults=defaults
                )

                if created:
                    self.stats['general_categories']['created'] += 1
                    logger.info(f"Created general category: {category.name}")
                else:
                    self.stats['general_categories']['updated'] += 1
                    logger.debug(f"Updated general category: {category.name}")

                # Process products in this category
                if category.product_count > 0:
                    self.process_products_for_category(category, is_school_category=False)

                return category

        except Exception as e:
            logger.error(f"Error processing general category {category_data['name']}: {e}")
            self.stats['general_categories']['skipped'] += 1
            return None

    def process_general_subcategories(self, parent: TUSGeneralCategory, categories: List[Dict], category_map: Dict):
        """Process subcategories under a general category"""
        for category in categories:
            if category['parent'] == parent.woo_category_id:
                self.process_general_category(category, parent=parent)

    def process_products_for_category(self, category, is_school_category: bool):
        """Process products in a category with batch operations"""
        try:
            woo_category_id = category.woo_category_id
            products = self.woo_service.get_products_by_category(woo_category_id)

            self.stdout.write(f"Processing {len(products)} products for category {category.name}")

            for product_data in products:
                self.process_product(product_data, category, is_school_category)

            # Save batch after each category
            self.save_batches(force=False)  # Will save if batch size reached

        except Exception as e:
            logger.error(f"Error processing products for category {category.name}: {e}")

    def process_product(self, product_data: Dict, category, is_school_category: bool) -> Optional[TUSProduct]:
        """Process a single product - prepare for batch save"""
        try:
            if self.dry_run:
                self.stdout.write(f"[DRY RUN] Would process product: {product_data['name']}")
                return None

            woo_product_id = product_data['id']

            # Parse prices
            price = self.woo_service.parse_price(product_data.get('price', '0'))
            regular_price = self.woo_service.parse_price(product_data.get('regular_price'))
            sale_price = self.woo_service.parse_price(product_data.get('sale_price'))

            # Validate stock quantity to prevent database errors
            stock_quantity = product_data.get('stock_quantity')
            if stock_quantity is not None:
                if isinstance(stock_quantity, str):
                    try:
                        stock_quantity = int(stock_quantity)
                    except (ValueError, TypeError):
                        stock_quantity = None
                # Ensure stock quantity is within valid range
                if stock_quantity is not None:
                    if stock_quantity < 0:
                        stock_quantity = 0
                    elif stock_quantity > 2147483647:
                        stock_quantity = 2147483647

            # Prepare product data
            product_defaults = {
                'name': product_data['name'],
                'slug': product_data.get('slug', ''),
                'type': product_data.get('type', 'simple'),
                'featured': product_data.get('featured', False),
                'price': price,
                'regular_price': regular_price,
                'sale_price': sale_price,
                'on_sale': product_data.get('on_sale', False),
                'description': product_data.get('description', ''),
                'short_description': product_data.get('short_description', ''),
                'sku': product_data.get('sku', ''),
                'stock_status': product_data.get('stock_status', 'instock'),
                'manage_stock': product_data.get('manage_stock', False),
                'stock_quantity': stock_quantity,
                'weight': product_data.get('weight', ''),
                'dimensions': product_data.get('dimensions'),
                'image_url': product_data['images'][0]['src'] if product_data.get('images') else '',
                'gallery_urls': [img['src'] for img in product_data.get('images', [])[1:]],
                'tags': product_data.get('tags', []),
                'attributes': product_data.get('attributes', []),
                'woo_categories': product_data.get('categories', []),
                'meta_data': product_data.get('meta_data', []),
            }

            # Check if product exists in database (pre-loaded) or already queued for creation
            existing_product = self.existing_products.get(woo_product_id)
            queued_product = self.products_being_created.get(woo_product_id)

            if existing_product and existing_product.pk:
                # Update existing product (has PK from database)
                product = existing_product
                for field, value in product_defaults.items():
                    setattr(product, field, value)
                if product not in self.products_to_update:
                    self.products_to_update.append(product)
                    self.stats['products']['updated'] += 1
            elif queued_product:
                # Product already queued for creation, reuse it
                product = queued_product
            else:
                # Create new product
                product = TUSProduct(
                    woo_product_id=woo_product_id,
                    **product_defaults
                )
                self.products_to_create.append(product)
                self.products_being_created[woo_product_id] = product
                self.stats['products']['created'] += 1

            # Prepare category assignment (will be processed in batch)
            self.assignments_to_create.append({
                'product': product,
                'category': category,
                'is_school_category': is_school_category
            })

            # Note: Variations will be processed in parallel batch later
            # No longer processing variations individually here

            return product

        except Exception as e:
            logger.error(f"Error processing product {product_data.get('name', 'Unknown')}: {e}")
            self.stats['products']['skipped'] += 1
            return None

    def process_product_variations(self, product: TUSProduct, woo_product_id: int):
        """Process variations for a variable product"""
        try:
            variations = self.woo_service.get_product_variations(woo_product_id)

            for variation_data in variations:
                self.process_variation(product, variation_data)

        except Exception as e:
            logger.error(f"Error processing variations for product {product.name}: {e}")

    def process_variation(self, product: TUSProduct, variation_data: Dict) -> Optional[TUSProductVariation]:
        """Process a single product variation"""
        try:
            if self.dry_run:
                return None

            # Extract variation attributes
            variation_type, variation_value = self.extract_variation_info(variation_data)

            # Parse prices
            price = self.woo_service.parse_price(variation_data.get('price', '0'))
            regular_price = self.woo_service.parse_price(variation_data.get('regular_price'))
            sale_price = self.woo_service.parse_price(variation_data.get('sale_price'))

            # Validate stock quantity to prevent database errors
            stock_quantity = variation_data.get('stock_quantity') or 0
            if isinstance(stock_quantity, str):
                try:
                    stock_quantity = int(stock_quantity)
                except (ValueError, TypeError):
                    stock_quantity = 0

            # Ensure stock quantity is within valid range (0 to 2147483647 for MySQL INT)
            if stock_quantity < 0:
                stock_quantity = 0
            elif stock_quantity > 2147483647:
                stock_quantity = 2147483647

            defaults = {
                'product': product,
                'variation_type': variation_type,
                'variation_value': variation_value,
                'price': price,
                'regular_price': regular_price,
                'sale_price': sale_price,
                'stock_quantity': stock_quantity,
                'stock_status': variation_data.get('stock_status', 'instock'),
                'sku': variation_data.get('sku', ''),
                'is_active': variation_data.get('status', 'publish') == 'publish',
                'attributes': variation_data.get('attributes', []),
                'image_url': variation_data.get('image', {}).get('src', '') if variation_data.get('image') else '',
                'weight': variation_data.get('weight', ''),
                'dimensions': variation_data.get('dimensions'),
                'menu_order': variation_data.get('menu_order', 0),
            }

            # Use get_or_create to handle unique constraint
            variation, created = TUSProductVariation.objects.get_or_create(
                product=product,
                variation_type=variation_type,
                variation_value=variation_value,
                defaults={'woo_variation_id': variation_data['id'], **defaults}
            )

            if not created:
                # Update existing variation
                for key, value in defaults.items():
                    setattr(variation, key, value)
                variation.woo_variation_id = variation_data['id']
                variation.save()

            if created:
                self.stats['variations']['created'] += 1
            else:
                self.stats['variations']['updated'] += 1

            return variation

        except Exception as e:
            logger.error(f"Error processing variation for product {product.name}: {e}")
            self.stats['variations']['skipped'] += 1
            return None

    def extract_variation_info(self, variation_data: Dict) -> Tuple[str, str]:
        """Extract variation type and value from variation data"""
        attributes = variation_data.get('attributes', [])

        if not attributes:
            return 'other', 'Unknown'

        # Map common attribute names to our variation types
        type_mapping = {
            'size': 'size',
            'sizes': 'size',
            'colour': 'color',
            'color': 'color',
            'colors': 'color',
            'gender': 'gender',
            'style': 'style',
            'length': 'length',
            'fit': 'fit',
        }

        # Process attributes
        variation_parts = []
        main_type = 'other'

        for attr in attributes:
            attr_name = attr.get('name', '').lower()
            attr_value = attr.get('option', '')

            # Map to our variation type
            for key, mapped_type in type_mapping.items():
                if key in attr_name:
                    if main_type == 'other':  # First mapped type becomes main type
                        main_type = mapped_type
                    break

            if attr_value:
                variation_parts.append(attr_value)

        # Combine all variation values
        variation_value = ' - '.join(variation_parts) if variation_parts else 'Standard'

        return main_type, variation_value

    def process_product_variations_batch(self, product: TUSProduct, woo_product_id: int):
        """Process variations for a product - prepare for batch save (sequential)"""
        try:
            variations_data = self.woo_service.get_product_variations(woo_product_id)

            for var_data in variations_data:
                woo_variation_id = var_data['id']
                variation_sku = var_data.get('sku', '')

                # Prepare variation data
                variation_defaults = {
                    'sku': variation_sku,
                    'price': self.woo_service.parse_price(var_data.get('price', '0')),
                    'regular_price': self.woo_service.parse_price(var_data.get('regular_price', '0')),
                    'sale_price': self.woo_service.parse_price(var_data.get('sale_price', '')),
                    'stock_status': var_data.get('stock_status', 'instock'),
                    'stock_quantity': var_data.get('stock_quantity', 0),
                }

                # Extract variation attributes
                attributes = var_data.get('attributes', [])
                if attributes:
                    variation_defaults['variation_type'] = attributes[0].get('name', '')
                    variation_defaults['variation_value'] = attributes[0].get('option', '')

                # Check if variation exists using the same key as the database unique constraint
                key = (woo_product_id, variation_defaults.get('variation_type', ''), variation_defaults.get('variation_value', ''))
                existing_variation = self.existing_variations.get(key)

                if existing_variation and existing_variation.pk:
                    # Update existing variation (has PK from database)
                    variation = existing_variation
                    for field, value in variation_defaults.items():
                        setattr(variation, field, value)
                    if variation not in self.variations_to_update:
                        self.variations_to_update.append(variation)
                        self.stats['variations']['updated'] += 1
                elif existing_variation:
                    # Variation already queued for creation, skip it
                    continue
                else:
                    # Create new variation
                    variation = TUSProductVariation(
                        product=product,
                        woo_variation_id=woo_variation_id,
                        **variation_defaults
                    )
                    self.variations_to_create.append(variation)
                    self.existing_variations[key] = variation
                    self.stats['variations']['created'] += 1

        except Exception as e:
            logger.error(f"Error processing variations for product {woo_product_id}: {str(e)}")

    def batch_process_all_variations(self):
        """Process variations for all variable products in parallel"""

        # Collect all variable products that need variation fetching
        variable_product_ids = [
            p.woo_product_id for p in (self.products_to_create + self.products_to_update)
            if p.type == 'variable'
        ]

        if not variable_product_ids:
            return

        self.stdout.write(f"Fetching variations for {len(variable_product_ids)} variable products in parallel...")

        # Fetch all variations in parallel
        variations_by_product = self.woo_service.get_variations_parallel(
            variable_product_ids,
            max_workers=5
        )

        # Process variations
        for woo_product_id, variations_data in variations_by_product.items():
            product = self.existing_products.get(woo_product_id)
            if not product:
                continue

            for var_data in variations_data:
                woo_variation_id = var_data['id']
                variation_sku = var_data.get('sku', '')

                # Validate stock quantity to prevent database errors
                stock_quantity = var_data.get('stock_quantity', 0)

                # Handle None values
                if stock_quantity is None:
                    stock_quantity = 0
                elif isinstance(stock_quantity, str):
                    try:
                        stock_quantity = int(stock_quantity)
                    except (ValueError, TypeError):
                        stock_quantity = 0

                # Ensure stock quantity is within valid range (0 to 2147483647 for MySQL INT)
                if stock_quantity < 0:
                    stock_quantity = 0
                elif stock_quantity > 2147483647:
                    stock_quantity = 2147483647

                # Prepare variation data (same logic as before)
                variation_defaults = {
                    'sku': variation_sku,
                    'price': self.woo_service.parse_price(var_data.get('price', '0')),
                    'regular_price': self.woo_service.parse_price(var_data.get('regular_price', '0')),
                    'sale_price': self.woo_service.parse_price(var_data.get('sale_price', '')),
                    'stock_status': var_data.get('stock_status', 'instock'),
                    'stock_quantity': stock_quantity,
                    'weight': var_data.get('weight', ''),
                    'dimensions': var_data.get('dimensions'),
                    'image_url': var_data.get('image', {}).get('src', '') if var_data.get('image') else '',
                    'menu_order': var_data.get('menu_order', 0),
                }

                # Extract variation attributes
                attributes = var_data.get('attributes', [])
                if attributes:
                    # Store full attributes JSON for frontend access
                    variation_defaults['attributes'] = attributes
                    # Also store first attribute for backward compatibility
                    variation_defaults['variation_type'] = attributes[0].get('name', '')
                    variation_defaults['variation_value'] = attributes[0].get('option', '')

                # Check if variation exists using the same key as the database unique constraint
                key = (woo_product_id, variation_defaults.get('variation_type', ''), variation_defaults.get('variation_value', ''))
                existing_variation = self.existing_variations.get(key)

                if existing_variation and existing_variation.pk:
                    # Update existing variation (has PK from database)
                    variation = existing_variation
                    for field, value in variation_defaults.items():
                        setattr(variation, field, value)
                    if variation not in self.variations_to_update:
                        self.variations_to_update.append(variation)
                        self.stats['variations']['updated'] += 1
                elif existing_variation:
                    # Variation already queued for creation, skip it
                    continue
                else:
                    # Create new variation
                    variation = TUSProductVariation(
                        product=product,
                        woo_variation_id=woo_variation_id,
                        **variation_defaults
                    )
                    self.variations_to_create.append(variation)
                    self.existing_variations[key] = variation
                    self.stats['variations']['created'] += 1

        self.stdout.write(f"✓ Processed {len(variations_by_product)} product variations")

    def save_batches(self, force=False):
        """Save accumulated batches to database"""
        batch_size = 500

        # Only save if we have enough items or force is True
        total_items = (len(self.products_to_create) + len(self.products_to_update) +
                       len(self.variations_to_create) + len(self.variations_to_update))

        if not force and total_items < batch_size:
            return

        self.stdout.write(f"Saving batch: {len(self.products_to_create)} new products, "
                        f"{len(self.products_to_update)} updates, "
                        f"{len(self.variations_to_create)} new variations, "
                        f"{len(self.variations_to_update)} variation updates")

        # Bulk create new products
        if self.products_to_create:
            # Bulk create with PKs returned (Django 4.2+ supports this)
            created_products = TUSProduct.objects.bulk_create(
                self.products_to_create,
                batch_size=batch_size
            )
            self.stdout.write(f"✓ Created {len(created_products)} products")

            # Refresh products from DB to get their PKs
            woo_ids = [p.woo_product_id for p in created_products]
            refreshed_products = {
                p.woo_product_id: p
                for p in TUSProduct.objects.filter(woo_product_id__in=woo_ids)
            }

            # Update existing_products with refreshed versions that have PKs
            self.existing_products.update(refreshed_products)

            # Update product references in assignments to use refreshed products with PKs
            for assignment in self.assignments_to_create:
                woo_id = assignment['product'].woo_product_id
                if woo_id in refreshed_products:
                    assignment['product'] = refreshed_products[woo_id]

        # Bulk update existing products
        if self.products_to_update:
            TUSProduct.objects.bulk_update(
                self.products_to_update,
                fields=['name', 'slug', 'type', 'featured', 'price', 'regular_price', 'sale_price',
                        'on_sale', 'description', 'short_description', 'sku', 'stock_status',
                        'manage_stock', 'stock_quantity', 'weight', 'dimensions', 'image_url',
                        'gallery_urls', 'tags', 'attributes', 'woo_categories', 'meta_data'],
                batch_size=batch_size
            )
            self.stdout.write(f"✓ Updated {len(self.products_to_update)} products")

        # Process variations for both created and updated products
        # IMPORTANT: Process variations for ALL batches, not just force=True
        # to ensure all variable products get their variations synced
        if self.products_to_create or self.products_to_update:
            self.batch_process_all_variations()

        # NOW clear the lists after variation processing
        if self.products_to_create:
            self.products_to_create = []
            self.products_being_created = {}

        if self.products_to_update:
            self.products_to_update = []

        # Bulk create variations
        if self.variations_to_create:
            TUSProductVariation.objects.bulk_create(self.variations_to_create, batch_size=batch_size)
            self.stdout.write(f"✓ Created {len(self.variations_to_create)} variations")
            self.variations_to_create = []

        # Bulk update variations
        if self.variations_to_update:
            TUSProductVariation.objects.bulk_update(
                self.variations_to_update,
                fields=['sku', 'price', 'regular_price', 'sale_price', 'stock_status',
                        'stock_quantity', 'variation_type', 'variation_value', 'attributes',
                        'weight', 'dimensions', 'image_url', 'menu_order'],
                batch_size=batch_size
            )
            self.stdout.write(f"✓ Updated {len(self.variations_to_update)} variations")
            self.variations_to_update = []

        # Process category assignments
        if self.assignments_to_create:
            self.batch_create_assignments()

    def batch_create_assignments(self):
        """Batch create category assignments"""
        for assignment_data in self.assignments_to_create:
            product = assignment_data['product']
            category = assignment_data['category']
            is_school_category = assignment_data['is_school_category']

            try:
                # Create or update category assignment
                if is_school_category:
                    # Check if product already has a primary school category assignment
                    existing_primary = TUSProductCategoryAssignment.objects.filter(
                        product=product,
                        school_category__isnull=False,
                        is_primary=True
                    ).first()

                    TUSProductCategoryAssignment.objects.update_or_create(
                        product=product,
                        school_category=category,
                        defaults={
                            'woo_category_id': category.woo_category_id,
                            'is_primary': existing_primary is None,
                        }
                    )
                else:
                    # Check if product already has a primary general category assignment
                    existing_primary = TUSProductCategoryAssignment.objects.filter(
                        product=product,
                        general_category__isnull=False,
                        is_primary=True
                    ).first()

                    TUSProductCategoryAssignment.objects.update_or_create(
                        product=product,
                        general_category=category,
                        defaults={
                            'woo_category_id': category.woo_category_id,
                            'is_primary': existing_primary is None,
                        }
                    )
            except Exception as e:
                logger.error(f"Error creating assignment for product {product.name}: {e}")

        self.assignments_to_create = []

    def update_all_category_counts(self):
        """Update product counts for all categories at once"""
        from django.db.models import Count

        # Update school categories
        for category in TUSSchoolCategory.objects.all():
            category.update_product_count()

        # Update general categories
        for category in TUSGeneralCategory.objects.all():
            category.update_product_count()

        self.stdout.write("✓ Category counts updated")

    def display_statistics(self):
        """Display sync statistics"""
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("SYNC STATISTICS")
        self.stdout.write("=" * 50)

        for entity, counts in self.stats.items():
            self.stdout.write(f"\n{entity.replace('_', ' ').title()}:")
            self.stdout.write(f"  Created: {counts['created']}")
            self.stdout.write(f"  Updated: {counts['updated']}")
            self.stdout.write(f"  Skipped: {counts['skipped']}")
            self.stdout.write(f"  Total: {sum(counts.values())}")

        # Update sync job statistics
        if self.sync_job:
            self.sync_job.clubs_created = self.stats['schools']['created']
            self.sync_job.clubs_updated = self.stats['schools']['updated']
            self.sync_job.categories_created = (
                self.stats['school_categories']['created'] +
                self.stats['general_categories']['created']
            )
            self.sync_job.categories_updated = (
                self.stats['school_categories']['updated'] +
                self.stats['general_categories']['updated']
            )
            self.sync_job.products_created = self.stats['products']['created']
            self.sync_job.products_updated = self.stats['products']['updated']
            self.sync_job.save()