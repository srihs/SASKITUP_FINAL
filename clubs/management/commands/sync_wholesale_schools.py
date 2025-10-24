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
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from clubs.services.cin7_service import CIN7Service
from schools.models import (
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
        parser.add_argument(
            '--sync-job-id',
            type=str,
            help='Sync job ID for progress tracking (internal use)'
        )

    def handle(self, *args, **options):
        """Main command handler"""
        self.dry_run = options.get('dry_run', False)
        self.force_update = options.get('force_update', False)
        self.limit = options.get('limit')
        self.school_filter = options.get('school_filter')
        self.verbosity = options.get('verbosity', 1)
        sync_job_id = options.get('sync_job_id')

        # Initialize sync job
        if not self.dry_run:
            if sync_job_id:
                # Use existing sync job
                try:
                    self.sync_job = WholesaleSyncJob.objects.get(id=sync_job_id)
                    self.sync_job.status = 'running'
                    self.sync_job.started_at = timezone.now()
                    self.sync_job.save()
                except WholesaleSyncJob.DoesNotExist:
                    # Fall back to creating new job
                    self.sync_job = WholesaleSyncJob.objects.create(
                        status='running',
                        started_at=timezone.now()
                    )
            else:
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

            # Update progress: Connecting to API
            if self.sync_job:
                self.sync_job.progress_percentage = 5
                self.sync_job.current_step = 'Connecting to Cin7 API...'
                self.sync_job.save()

            # Initialize CIN7 service
            cin7_service = CIN7Service()

            # Test connection
            if not cin7_service.test_connection():
                raise CommandError('Failed to connect to CIN7 API')

            # Update progress: Fetching data
            if self.sync_job:
                self.sync_job.progress_percentage = 10
                self.sync_job.current_step = 'Fetching wholesale products from Cin7...'
                self.sync_job.save()

            # Fetch all wholesale products
            self.stdout.write('Fetching wholesale products from CIN7...')
            products = cin7_service.get_all_wholesale_products()

            if not products:
                self.stdout.write(self.style.WARNING('No wholesale products found'))
                return

            # Apply limit if specified
            if self.limit:
                products = products[:self.limit]
                self.stdout.write(f'Limited to {len(products)} products for testing')

            # Update progress: Organizing data
            if self.sync_job:
                self.sync_job.progress_percentage = 30
                self.sync_job.current_step = 'Organizing products by school...'
                self.sync_job.save()

            # Organize products by school
            self.stdout.write('Organizing products by school...')
            schools_data = cin7_service.organize_products_by_school(products)

            # Fetch school logos from Cin7 ProductCategories
            self.stdout.write('Fetching school logos from Cin7...')
            school_logos = cin7_service.get_wholesale_school_categories()
            if school_logos:
                self.stdout.write(f'Found {len(school_logos)} school logos')
            else:
                self.stdout.write(self.style.WARNING('No school logos found, continuing without logos'))
                school_logos = {}

            # Apply school filter if specified
            if self.school_filter:
                filtered_schools = {
                    name: data for name, data in schools_data.items()
                    if self.school_filter.lower() in name.lower()
                }
                schools_data = filtered_schools
                self.stdout.write(f'Filtered to {len(schools_data)} schools matching "{self.school_filter}"')

            # Process each school with progress updates
            total_schools = len(schools_data)
            for i, (school_name, school_data) in enumerate(schools_data.items(), 1):
                # Calculate progress: 40-95% for processing schools
                progress = 40 + int((i / total_schools) * 55)

                if self.sync_job:
                    self.sync_job.progress_percentage = progress
                    self.sync_job.current_step = f'Processing school {i}/{total_schools}: {school_name}'
                    self.sync_job.save()

                self.stdout.write(f'\nProcessing school {i}/{total_schools}: {school_name}')

                try:
                    with transaction.atomic():
                        self._process_school(school_name, school_data, cin7_service, school_logos)
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

            # Update final progress
            if self.sync_job:
                self.sync_job.progress_percentage = 100
                self.sync_job.current_step = 'Sync completed successfully'
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

    def _process_school(self, school_name: str, school_data: dict, cin7_service: CIN7Service, school_logos: dict = None):
        """Process a single school and its products"""
        school_info = school_data['info']
        products = school_data['products']

        if school_logos is None:
            school_logos = {}

        if self.verbosity >= 2:
            self.stdout.write(f'  School info: {school_info}')
            self.stdout.write(f'  Products: {len(products)}')

        # Get logo URL for this school (match by name)
        logo_url = school_logos.get(school_name, '')
        if logo_url and self.verbosity >= 2:
            self.stdout.write(f'  Logo URL: {logo_url}')

        # Create or get school
        school, school_created = self._process_school_record(school_name, school_info, logo_url)

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

                # Process product variations
                if not self.dry_run:
                    self._process_product_variations(product, product_data, cin7_service)

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

        # Note: We don't create a "General" category automatically
        # If there are no categories from Cin7, the school will show products directly

        # Update school statistics
        if not self.dry_run:
            # total_products is a computed property, no need to set it
            school.last_synced_at = timezone.now()
            school.save()

        if self.verbosity >= 1:
            action = "Would create" if self.dry_run else "Created" if school_created else "Updated"
            self.stdout.write(f"  {action} school: {school_name} ({len(products)} products)")

    def _process_school_record(self, school_name: str, school_info: dict, logo_url: str = ''):
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
            # Even if not forcing update, always update the logo if provided
            if logo_url and school.logo != logo_url and not self.dry_run:
                school.logo = logo_url
                school.save(update_fields=['logo'])
                if self.verbosity >= 2:
                    self.stdout.write(f"  Updated logo for existing school: {school_name}")
            return school, school_created

        # Ensure school name is never empty - use fallback if needed
        if not school_name or school_name.strip() == '':
            school_name = 'Wholesale Schools'
            if self.verbosity >= 2:
                self.stdout.write(f"  Warning: Empty school name, using default: {school_name}")

        # Prepare school data
        school_data = {
            'name': school_name,
            'description': school_info.get('description', ''),
            'school_code': school_code,
            'cin7_brand': school_info.get('brand', ''),
            'cin7_category_path': school_info.get('category_path', ''),
            'logo': logo_url,
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

    def _process_product_variations(self, product: WholesaleProduct, product_data: dict, cin7_service: CIN7Service):
        """
        Process variations for a product from Cin7 productOptions

        Args:
            product: WholesaleProduct instance
            product_data: Original Cin7 product data
            cin7_service: CIN7Service instance
        """
        from schools.models import WholesaleProductVariation

        # Get productOptions from the Cin7 data
        product_options = product_data.get('productOptions', [])

        if not product_options:
            if self.verbosity >= 2:
                self.stdout.write(f"    No variations found for product {product.cin7_id}")
            return

        variations_created = 0
        variations_updated = 0

        for option in product_options:
            try:
                # Skip inactive options
                option_status = option.get('status', '').lower()
                if option_status not in ['active', 'primary']:
                    continue

                # Extract variation attributes from option1, option2, option3
                # Handle None values by converting to empty string before strip()
                option1 = (option.get('option1') or '').strip()
                option2 = (option.get('option2') or '').strip()
                option3 = (option.get('option3') or '').strip()

                # Determine variation type and value
                variation_type, variation_value = self._parse_variation_type(option1, option2, option3)

                # Extract prices from priceColumns
                price_columns = option.get('priceColumns', {})
                cost_price = self._extract_decimal(price_columns.get('costNZD'))
                retail_price = self._extract_decimal(price_columns.get('retailNZD') or option.get('retailPrice'))

                # Calculate derived prices
                margin_75_price = None
                discount_percentage = None
                if cost_price and cost_price > 0:
                    try:
                        margin_75_price = cost_price / Decimal('0.25')
                        margin_75_price = margin_75_price.quantize(Decimal('0.01'))

                        if retail_price and margin_75_price > 0:
                            discount = ((margin_75_price - retail_price) / margin_75_price) * 100
                            discount_percentage = max(Decimal('0'), discount)
                            discount_percentage = discount_percentage.quantize(Decimal('0.01'))
                    except Exception:
                        pass

                # Prepare variation data
                variation_data = {
                    'product': product,
                    'variation_type': variation_type,
                    'variation_value': variation_value,
                    'variation_description': f"{option1} {option2} {option3}".strip(),
                    'cin7_sku': (option.get('code') or '').strip(),
                    'cin7_barcode': (option.get('barcode') or '').strip(),
                    'wholesale_price': retail_price,
                    'retail_price': retail_price,
                    'cost_price': cost_price,
                    'margin_75_price': margin_75_price,
                    'discount_percentage': discount_percentage,
                    'quantity_available': option.get('stockAvailable', 0),
                    'quantity_on_hand': option.get('stockOnHand', 0),
                    'quantity_committed': option.get('stockCommitted', 0),
                    'weight': self._extract_decimal(option.get('weight')),
                    'image_url': option.get('image', {}).get('src', '') if option.get('image') else '',
                    'is_active': True,
                    'last_synced_at': timezone.now(),
                }

                if not self.dry_run:
                    # Update or create variation using the actual unique constraint fields
                    # (product, variation_type, variation_value)
                    cin7_id = str(option.get('id', ''))

                    # Add cin7_id to variation_data
                    variation_data['cin7_id'] = cin7_id

                    variation, created = WholesaleProductVariation.objects.update_or_create(
                        product=product,
                        variation_type=variation_type,
                        variation_value=variation_value,
                        defaults=variation_data
                    )

                    if created:
                        variations_created += 1
                    else:
                        variations_updated += 1

                    if self.verbosity >= 2:
                        action = "Created" if created else "Updated"
                        self.stdout.write(f"    {action} variation: {variation_value}")

            except Exception as e:
                error_msg = f"Error processing variation for product {product.cin7_id}: {e}"
                self.stdout.write(f"    {self.style.ERROR(error_msg)}")
                logger.error(error_msg, exc_info=True)

                if self.sync_job:
                    self.sync_job.errors_count += 1
                    if not hasattr(self.sync_job, 'error_messages'):
                        self.sync_job.error_messages = []
                    self.sync_job.error_messages.append(error_msg)

        # Update sync job counters
        if self.sync_job and not self.dry_run:
            if not hasattr(self.sync_job, 'variations_created'):
                self.sync_job.variations_created = 0
            if not hasattr(self.sync_job, 'variations_updated'):
                self.sync_job.variations_updated = 0
            self.sync_job.variations_created += variations_created
            self.sync_job.variations_updated += variations_updated
            self.sync_job.save()

        if self.verbosity >= 1:
            self.stdout.write(f"  Variations: {variations_created} created, {variations_updated} updated")

    def _parse_variation_type(self, option1: str, option2: str, option3: str):
        """
        Determine variation type and create composite value from option fields

        Args:
            option1: First option (usually size)
            option2: Second option (usually color)
            option3: Third option (other attributes)

        Returns:
            Tuple of (variation_type, variation_value)
        """
        parts = [p for p in [option1, option2, option3] if p]

        if not parts:
            return ('other', 'Default')

        # Determine primary type based on first non-empty option
        if option1:
            if self._is_size_value(option1):
                variation_type = 'size'
            elif self._is_color_value(option1):
                variation_type = 'color'
            else:
                variation_type = 'style'
        else:
            variation_type = 'other'

        # Create composite value
        variation_value = ' - '.join(parts)

        return (variation_type, variation_value)

    def _is_size_value(self, value: str) -> bool:
        """Check if value appears to be a clothing size"""
        size_indicators = [
            'XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL', '4XL', '5XL',
            'YOUTH', 'ADULT', 'JUNIOR', 'SENIOR', 'KIDS',
            'SMALL', 'MEDIUM', 'LARGE',
        ]
        value_upper = value.upper()
        return any(ind in value_upper for ind in size_indicators)

    def _is_color_value(self, value: str) -> bool:
        """Check if value appears to be a color"""
        color_names = [
            'BLACK', 'WHITE', 'RED', 'BLUE', 'GREEN', 'YELLOW',
            'ORANGE', 'PURPLE', 'PINK', 'GREY', 'GRAY', 'NAVY',
            'MAROON', 'TEAL', 'LIME', 'CYAN', 'BROWN', 'GOLD'
        ]
        value_upper = value.upper()
        return any(color in value_upper for color in color_names)

    def _extract_decimal(self, value) -> Decimal:
        """Safely extract decimal value from API response"""
        if value is None:
            return None
        try:
            from decimal import InvalidOperation
            decimal_value = Decimal(str(value))
            return decimal_value if decimal_value >= 0 else None
        except (InvalidOperation, ValueError):
            return None

    def _process_category_path(self, category_path: str, categories_processed: set):
        """
        Process category hierarchy from category path with improved depth handling

        Args:
            category_path: Full category path like "Wholesale Schools > School Name > Uniforms > Jerseys"
            categories_processed: Set of already processed category hierarchy keys

        Returns:
            List of category objects representing the hierarchy
        """
        categories = []

        if not category_path:
            return categories

        # Split category path and clean parts
        parts = [part.strip() for part in category_path.split('>') if part.strip()]

        if not parts:
            return categories

        parent_category = None

        for level, category_name in enumerate(parts):
            # Generate unique hierarchy key for this category position
            if parent_category:
                hierarchy_key = f"{parent_category.cin7_id}::{category_name}"
            else:
                hierarchy_key = f"root::{category_name}"

            # Check if already processed in this hierarchy position
            if hierarchy_key in categories_processed:
                # Find existing category
                if parent_category:
                    parent_category = WholesaleCategory.objects.filter(
                        name=category_name,
                        parent=parent_category
                    ).first()
                else:
                    parent_category = WholesaleCategory.objects.filter(
                        name=category_name,
                        parent__isnull=True
                    ).first()
                continue

            # Create or get category at this level
            category, created = self._create_category(
                name=category_name,
                parent=parent_category,
                level=level
            )

            if created and self.sync_job:
                self.sync_job.categories_created += 1
            elif not created and self.sync_job:
                self.sync_job.categories_updated += 1

            categories.append(category)
            categories_processed.add(hierarchy_key)
            parent_category = category

            if self.verbosity >= 2:
                indent = "  " * (level + 1)
                action = "Created" if created else "Found"
                self.stdout.write(f"{indent}{action} category: {category_name} (level {level})")

        return categories

    def _create_category(self, name: str, parent: WholesaleCategory = None, level: int = 0):
        """
        Create or get a category with improved cin7_id generation

        Args:
            name: Category name
            parent: Parent category (None for root)
            level: Hierarchy level (0 = root)

        Returns:
            Tuple of (category, created)
        """
        import hashlib

        # Build full path for this category
        path_parts = []
        current = parent
        while current:
            path_parts.insert(0, current.name)
            current = current.parent
        path_parts.append(name)

        path_str = ' > '.join(path_parts)

        # Generate stable cin7_id based on full path
        category_hash = hashlib.md5(path_str.encode('utf-8')).hexdigest()[:10]
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
            # Use get_or_create with name and parent as unique constraint
            category, created = WholesaleCategory.objects.get_or_create(
                name=name,
                parent=parent,
                defaults=category_data
            )

            # Update fields if exists but data changed
            if not created:
                updated = False
                for field, value in category_data.items():
                    if field not in ['name', 'parent'] and getattr(category, field) != value:
                        setattr(category, field, value)
                        updated = True
                if updated:
                    category.save()
        else:
            # Dry run mode
            existing = WholesaleCategory.objects.filter(
                name=name,
                parent=parent
            ).exists()
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

            # Show variation statistics if available
            if hasattr(self.sync_job, 'variations_created') and hasattr(self.sync_job, 'variations_updated'):
                self.stdout.write(f'  Variations created: {self.sync_job.variations_created}')
                self.stdout.write(f'  Variations updated: {self.sync_job.variations_updated}')

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