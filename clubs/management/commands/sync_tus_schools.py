import logging
import json
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from clubs.models import SyncJob
from clubs.models_tus import (
    TUSLocation, TUSSchool, TUSGeneralCategory, TUSSchoolCategory,
    TUSProduct, TUSProductVariation, TUSProductCategoryAssignment
)
from clubs.services.tus_woocommerce import TUSWooCommerceService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync TUS schools, categories and products from WooCommerce API'

    def add_arguments(self, parser):
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

        # Create sync job
        if not self.dry_run:
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
        """Run the main sync process"""
        self.stdout.write("Starting TUS schools sync...")

        # Statistics
        self.stats = {
            'locations': {'created': 0, 'updated': 0, 'skipped': 0},
            'schools': {'created': 0, 'updated': 0, 'skipped': 0},
            'general_categories': {'created': 0, 'updated': 0, 'skipped': 0},
            'school_categories': {'created': 0, 'updated': 0, 'skipped': 0},
            'products': {'created': 0, 'updated': 0, 'skipped': 0},
            'variations': {'created': 0, 'updated': 0, 'skipped': 0},
        }

        # Get all categories
        all_categories = self.woo_service.get_all_categories()
        category_map = {cat['id']: cat for cat in all_categories}

        # Process categories hierarchically
        self.process_locations(all_categories, category_map)
        self.process_general_categories(all_categories, category_map)

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
        """Process categories under a school"""
        for category in categories:
            if category['parent'] == school.woo_category_id:
                school_category = self.process_school_category(category, school)
                if school_category:
                    # Process products in this category
                    self.process_products_for_category(school_category, is_school_category=True)

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
        """Process products in a category"""
        try:
            woo_category_id = category.woo_category_id
            products = self.woo_service.get_products_by_category(woo_category_id)

            for product_data in products:
                self.process_product(product_data, category, is_school_category)

        except Exception as e:
            logger.error(f"Error processing products for category {category.name}: {e}")

    def process_product(self, product_data: Dict, category, is_school_category: bool) -> Optional[TUSProduct]:
        """Process a single product"""
        try:
            if self.dry_run:
                self.stdout.write(f"[DRY RUN] Would process product: {product_data['name']}")
                return None

            with transaction.atomic():
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

                defaults = {
                    'name': product_data['name'],
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

                product, created = TUSProduct.objects.update_or_create(
                    woo_product_id=product_data['id'],
                    defaults=defaults
                )

                # Create or update category assignment
                if is_school_category:
                    # Check if product already has a primary school category assignment
                    existing_primary = TUSProductCategoryAssignment.objects.filter(
                        product=product,
                        school_category__isnull=False,
                        is_primary=True
                    ).first()

                    assignment, assignment_created = TUSProductCategoryAssignment.objects.update_or_create(
                        product=product,
                        school_category=category,
                        defaults={
                            'woo_category_id': category.woo_category_id,
                            'is_primary': existing_primary is None,  # Only set as primary if no other primary exists
                        }
                    )
                else:
                    # Check if product already has a primary general category assignment
                    existing_primary = TUSProductCategoryAssignment.objects.filter(
                        product=product,
                        general_category__isnull=False,
                        is_primary=True
                    ).first()

                    assignment, assignment_created = TUSProductCategoryAssignment.objects.update_or_create(
                        product=product,
                        general_category=category,
                        defaults={
                            'woo_category_id': category.woo_category_id,
                            'is_primary': existing_primary is None,
                        }
                    )

                if created:
                    self.stats['products']['created'] += 1
                    logger.debug(f"Created product: {product.name}")
                else:
                    self.stats['products']['updated'] += 1

                # Process variations if it's a variable product
                if product_data.get('type') == 'variable':
                    self.process_product_variations(product, product_data['id'])

                return product

        except Exception as e:
            logger.error(f"Error processing product {product_data['name']}: {e}")
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