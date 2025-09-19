"""
Django management command to sync wholesale schools from CIN7 API

Usage:
    python manage.py sync_wholesale_schools [OPTIONS]

Examples:
    python manage.py sync_wholesale_schools --dry-run
    python manage.py sync_wholesale_schools --limit 10 --verbosity 2
    python manage.py sync_wholesale_schools --force-update
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from clubs.services.cin7_service import CIN7Service
from clubs.models_wholesale import (
    WholesaleSchool, WholesaleCategory, WholesaleProduct,
    WholesaleProductVariation, WholesaleProductCategoryAssignment, WholesaleSyncJob
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync wholesale schools data from CIN7 API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without saving to database'
        )
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Force update existing records'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of products to process (for testing)'
        )
        parser.add_argument(
            '--school-filter',
            type=str,
            help='Filter schools by name (partial match)'
        )

    def handle(self, *args, **options):
        """Main command handler"""
        self.dry_run = options.get('dry_run', False)
        self.force_update = options.get('force_update', False)
        self.limit = options.get('limit')
        self.school_filter = options.get('school_filter')
        self.verbosity = options.get('verbosity', 1)

        # Initialize sync job
        if not self.dry_run:
            self.sync_job = WholesaleSyncJob.objects.create(
                status='running',
                started_at=timezone.now()
            )
        else:
            self.sync_job = None

        try:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Starting wholesale schools sync from CIN7 API'
                    f'{" (DRY RUN)" if self.dry_run else ""}'
                )
            )

            # Initialize CIN7 service
            cin7_service = CIN7Service()

            # Test connection
            if not cin7_service.test_connection():
                raise CommandError('Failed to connect to CIN7 API')

            # Fetch all wholesale products
            self.stdout.write('Fetching wholesale products from CIN7...')
            if self.sync_job:
                self.sync_job.current_step = 'Fetching products from CIN7'
                self.sync_job.save()

            products = cin7_service.get_all_wholesale_products()

            if not products:
                self.stdout.write(self.style.WARNING('No wholesale products found'))
                return

            # Apply limit if specified
            if self.limit:
                products = products[:self.limit]
                self.stdout.write(f'Limited to {len(products)} products for testing')

            # Organize products by school
            self.stdout.write('Organizing products by school...')
            schools_data = cin7_service.organize_products_by_school(products)

            # Apply school filter if specified
            if self.school_filter:
                filtered_schools = {
                    name: data for name, data in schools_data.items()
                    if self.school_filter.lower() in name.lower()
                }
                schools_data = filtered_schools
                self.stdout.write(f'Filtered to {len(schools_data)} schools matching "{self.school_filter}"')

            # Process each school
            total_schools = len(schools_data)
            for i, (school_name, school_data) in enumerate(schools_data.items(), 1):
                progress = int((i / total_schools) * 100)

                if self.sync_job:
                    self.sync_job.progress_percentage = progress
                    self.sync_job.current_step = f'Processing school: {school_name}'
                    self.sync_job.save()

                self.stdout.write(f'\nProcessing school {i}/{total_schools}: {school_name}')

                try:
                    with transaction.atomic():
                        self._process_school(school_name, school_data, cin7_service)
                except Exception as e:
                    error_msg = f"Error processing school {school_name}: {e}"
                    self.stdout.write(self.style.ERROR(error_msg))
                    logger.error(error_msg, exc_info=True)

                    if self.sync_job:
                        self.sync_job.errors_count += 1
                        self.sync_job.error_messages.append(error_msg)
                        self.sync_job.save()

            # Complete sync job
            if self.sync_job:
                self.sync_job.status = 'completed'
                self.sync_job.progress_percentage = 100
                self.sync_job.current_step = 'Sync completed'
                self.sync_job.completed_at = timezone.now()
                self.sync_job.save()

            # Print summary
            self._print_summary()

        except Exception as e:
            error_msg = f"Sync failed: {e}"
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg, exc_info=True)

            if self.sync_job:
                self.sync_job.status = 'failed'
                self.sync_job.current_step = 'Sync failed'
                self.sync_job.error_messages.append(error_msg)
                self.sync_job.completed_at = timezone.now()
                self.sync_job.save()

            raise CommandError(error_msg)

    def _process_school(self, school_name: str, school_data: dict, cin7_service: CIN7Service):
        """Process a single school and its products"""
        school_info = school_data['info']
        products = school_data['products']

        if self.verbosity >= 2:
            self.stdout.write(f'  School info: {school_info}')
            self.stdout.write(f'  Products: {len(products)}')

        # Create or get school
        school, school_created = self._process_school_record(school_name, school_info)

        if school_created:
            if self.sync_job:
                self.sync_job.schools_created += 1
        else:
            if self.sync_job:
                self.sync_job.schools_updated += 1

        # Process categories for this school
        categories_processed = set()

        # Process each product
        for product_data in products:
            try:
                # Process product
                product, product_created = self._process_product(school, product_data)

                if product_created:
                    if self.sync_job:
                        self.sync_job.products_created += 1
                else:
                    if self.sync_job:
                        self.sync_job.products_updated += 1

                # Process categories from category path
                category_path = product_data.get('category_path', '')
                if category_path:
                    categories = self._process_category_path(category_path, categories_processed)

                    # Assign product to categories
                    for category in categories:
                        self._assign_product_to_category(product, category)

            except Exception as e:
                error_msg = f"Error processing product {product_data.get('name', 'Unknown')}: {e}"
                self.stdout.write(f"    {self.style.ERROR(error_msg)}")
                logger.error(error_msg, exc_info=True)

        # Update school statistics
        if not self.dry_run:
            school.total_products = school.products.count()
            school.last_synced_at = timezone.now()
            school.save()

        if self.verbosity >= 1:
            action = "Would create" if self.dry_run else "Created" if school_created else "Updated"
            self.stdout.write(f"  {action} school: {school_name} ({len(products)} products)")

    def _process_school_record(self, school_name: str, school_info: dict):
        """Create or update a school record"""
        # Try to find existing school by name or code
        school = None
        school_code = school_info.get('code', '')

        if school_code:
            school = WholesaleSchool.objects.filter(school_code=school_code).first()

        if not school:
            school = WholesaleSchool.objects.filter(name=school_name).first()

        school_created = False

        if school and not self.force_update:
            return school, school_created

        # Prepare school data
        school_data = {
            'name': school_name,
            'description': school_info.get('description', ''),
            'school_code': school_code,
            'cin7_brand': school_info.get('brand', ''),
            'cin7_category_path': school_info.get('category_path', ''),
            'is_active': True,
        }

        if not self.dry_run:
            if school:
                # Update existing school
                for key, value in school_data.items():
                    setattr(school, key, value)
                school.save()
            else:
                # Create new school
                # Generate a unique cin7_id for the school (using school name hash)
                import hashlib
                school_hash = hashlib.md5(school_name.encode()).hexdigest()[:10]
                school_data['cin7_id'] = f"school_{school_hash}"

                school = WholesaleSchool.objects.create(**school_data)
                school_created = True
        else:
            # In dry run mode, create a temporary object
            school = WholesaleSchool(**school_data)
            school.id = 1  # Temporary ID for dry run
            if not WholesaleSchool.objects.filter(name=school_name).exists():
                school_created = True

        return school, school_created

    def _process_product(self, school: WholesaleSchool, product_data: dict):
        """Create or update a product record"""
        cin7_id = product_data['cin7_id']

        if not cin7_id:
            # Generate a temporary ID if missing
            import hashlib
            temp_id = hashlib.md5(f"{school.name}_{product_data['name']}".encode()).hexdigest()[:10]
            cin7_id = f"temp_{temp_id}"

        product = None
        if cin7_id:
            product = WholesaleProduct.objects.filter(cin7_id=cin7_id).first()

        product_created = False

        if product and not self.force_update:
            return product, product_created

        # Prepare product data
        product_data_clean = {
            'cin7_id': cin7_id,
            'school': school,
            'name': product_data['name'],
            'description': product_data.get('description', ''),
            'short_description': product_data.get('short_description', ''),
            'cin7_sku': product_data.get('cin7_sku', ''),
            'cin7_barcode': product_data.get('cin7_barcode', ''),
            'cin7_brand': product_data.get('cin7_brand', ''),
            'cin7_supplier': product_data.get('cin7_supplier', ''),
            'cin7_unit_of_measure': product_data.get('cin7_unit_of_measure', ''),
            'wholesale_price': product_data.get('wholesale_price'),
            'retail_price': product_data.get('retail_price'),
            'cost_price': product_data.get('cost_price'),
            'stock_status': product_data.get('stock_status', 'in_stock'),
            'quantity_available': product_data.get('quantity_available', 0),
            'quantity_on_hand': product_data.get('quantity_on_hand', 0),
            'quantity_committed': product_data.get('quantity_committed', 0),
            'weight': product_data.get('weight'),
            'dimensions': product_data.get('dimensions', {}),
            'attributes': product_data.get('attributes', {}),
            'image_url': product_data.get('image_url', ''),
            'is_active': True,
        }

        if not self.dry_run:
            if product:
                # Update existing product
                for key, value in product_data_clean.items():
                    setattr(product, key, value)
                product.save()
            else:
                # Create new product
                product = WholesaleProduct.objects.create(**product_data_clean)
                product_created = True
        else:
            # In dry run mode, create a temporary object
            product = WholesaleProduct(**product_data_clean)
            product.id = 1  # Temporary ID for dry run
            if not WholesaleProduct.objects.filter(cin7_id=cin7_id).exists():
                product_created = True

        return product, product_created

    def _process_category_path(self, category_path: str, categories_processed: set):
        """Process category hierarchy from category path"""
        categories = []

        # Split category path: "Wholesale Schools > School Name > Sub Category"
        parts = [part.strip() for part in category_path.split('>')]

        if not parts:
            return categories

        parent_category = None

        for i, category_name in enumerate(parts):
            if category_name in categories_processed:
                # Find existing category
                if parent_category:
                    parent_category = WholesaleCategory.objects.filter(
                        name=category_name, parent=parent_category
                    ).first()
                else:
                    parent_category = WholesaleCategory.objects.filter(
                        name=category_name, parent__isnull=True
                    ).first()
                continue

            # Create category if not exists
            category, created = self._create_category(category_name, parent_category, i)

            if created and self.sync_job:
                self.sync_job.categories_created += 1
            elif not created and self.sync_job:
                self.sync_job.categories_updated += 1

            categories.append(category)
            categories_processed.add(category_name)
            parent_category = category

        return categories

    def _create_category(self, name: str, parent: WholesaleCategory = None, level: int = 0):
        """Create or get a category"""
        # Generate cin7_id for category
        import hashlib
        path_parts = []
        if parent:
            path_parts.append(parent.name)
        path_parts.append(name)
        path_str = ' > '.join(path_parts)
        category_hash = hashlib.md5(path_str.encode()).hexdigest()[:10]
        cin7_id = f"cat_{category_hash}"

        category_data = {
            'cin7_id': cin7_id,
            'name': name,
            'parent': parent,
            'level': level,
            'path': path_str,
            'is_active': True,
        }

        if not self.dry_run:
            category, created = WholesaleCategory.objects.get_or_create(
                name=name,
                parent=parent,
                defaults=category_data
            )
        else:
            # Check if exists for dry run
            existing = WholesaleCategory.objects.filter(name=name, parent=parent).exists()
            category = WholesaleCategory(**category_data)
            category.id = 1  # Temporary ID
            created = not existing

        return category, created

    def _assign_product_to_category(self, product: WholesaleProduct, category: WholesaleCategory):
        """Assign product to category"""
        if not self.dry_run:
            assignment, created = WholesaleProductCategoryAssignment.objects.get_or_create(
                product=product,
                category=category,
                defaults={
                    'is_primary': not WholesaleProductCategoryAssignment.objects.filter(product=product).exists(),
                    'sort_order': 0,
                    'last_synced_at': timezone.now()
                }
            )

    def _print_summary(self):
        """Print sync summary"""
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS('WHOLESALE SCHOOLS SYNC SUMMARY'))
        self.stdout.write('='*50)

        if self.sync_job:
            self.stdout.write(f'Sync Job ID: {self.sync_job.id}')
            self.stdout.write(f'Status: {self.sync_job.status}')
            self.stdout.write(f'Duration: {self.sync_job.duration}')
            self.stdout.write('')
            self.stdout.write('Statistics:')
            self.stdout.write(f'  Schools created: {self.sync_job.schools_created}')
            self.stdout.write(f'  Schools updated: {self.sync_job.schools_updated}')
            self.stdout.write(f'  Products created: {self.sync_job.products_created}')
            self.stdout.write(f'  Products updated: {self.sync_job.products_updated}')
            self.stdout.write(f'  Categories created: {self.sync_job.categories_created}')
            self.stdout.write(f'  Categories updated: {self.sync_job.categories_updated}')
            self.stdout.write(f'  Errors: {self.sync_job.errors_count}')

            if self.sync_job.error_messages:
                self.stdout.write('\nErrors encountered:')
                for error in self.sync_job.error_messages:
                    self.stdout.write(f'  - {error}')

        self.stdout.write('')

        if not self.dry_run:
            total_schools = WholesaleSchool.objects.filter(is_active=True).count()
            total_products = WholesaleProduct.objects.filter(is_active=True).count()
            total_categories = WholesaleCategory.objects.filter(is_active=True).count()

            self.stdout.write('Current totals in database:')
            self.stdout.write(f'  Active wholesale schools: {total_schools}')
            self.stdout.write(f'  Active wholesale products: {total_products}')
            self.stdout.write(f'  Active wholesale categories: {total_categories}')
        else:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes were made to the database'))

        self.stdout.write('='*50)