"""
Django Management Command to Import Wholesale Schools Data from CSV
"""

import csv
import logging
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from schools.models import WholesaleSchool, WholesaleCategory, WholesaleProduct, WholesaleProductVariation

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import wholesale schools data from CSV file'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Path to the CSV file to import'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview import without making changes'
        )
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Force update existing records'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of rows to process (for testing)'
        )
        parser.add_argument(
            '--skip-keywords',
            type=str,
            nargs='*',
            default=['sample', 'samples', 'name', 'names', 'promotion', 'promotions',
                     'test', 'demo', 'template', 'example', 'placeholder', 'dummy',
                     'display', 'misc', 'miscellaneous', 'other', 'bulk', 'wholesale only',
                     'ohs - embroidery', 'embroidery'],
            help='Keywords to skip when found in product names (case-insensitive)'
        )

    def handle(self, *args, **options):
        csv_file_path = options['csv_file']
        dry_run = options['dry_run']
        force_update = options['force_update']
        limit = options['limit']
        skip_keywords = options['skip_keywords']

        self.stdout.write(
            self.style.SUCCESS(f'Starting CSV import from: {csv_file_path}')
        )
        self.stdout.write(f'Skip keywords: {", ".join(skip_keywords)}')

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )

        # Statistics
        stats = {
            'schools_created': 0,
            'schools_updated': 0,
            'categories_created': 0,
            'categories_updated': 0,
            'products_created': 0,
            'products_updated': 0,
            'variations_created': 0,
            'variations_updated': 0,
            'errors': [],
            'rows_processed': 0
        }

        try:
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                # Use csv.DictReader to automatically handle headers
                reader = csv.DictReader(file)

                # Verify we have the expected columns
                required_columns = [
                    'Sub Category', 'Product Name', 'Code', 'Option 1', 'Option 2', 'Option 3',
                    'Barcode', 'WholesaleExGST NZD Excl', 'Retail NZD Incl', 'Cost NZD Excl', 'Virtual Stock'
                ]

                missing_columns = [col for col in required_columns if col not in reader.fieldnames]
                if missing_columns:
                    raise CommandError(f'Missing required columns: {missing_columns}')

                # Process each row
                for row_num, row in enumerate(reader, start=2):  # Start at 2 since header is row 1
                    if limit and stats['rows_processed'] >= limit:
                        break

                    try:
                        with transaction.atomic():
                            if not dry_run:
                                self._process_row(row, stats, force_update, skip_keywords)
                            else:
                                self._preview_row(row, stats, skip_keywords)

                            stats['rows_processed'] += 1

                            # Progress indicator
                            if stats['rows_processed'] % 50 == 0:
                                self.stdout.write(f'Processed {stats["rows_processed"]} rows...')

                    except Exception as e:
                        error_msg = f'Row {row_num}: {str(e)}'
                        stats['errors'].append(error_msg)
                        self.stdout.write(
                            self.style.ERROR(error_msg)
                        )
                        continue

        except FileNotFoundError:
            raise CommandError(f'CSV file not found: {csv_file_path}')
        except Exception as e:
            raise CommandError(f'Error reading CSV file: {str(e)}')

        # Print summary
        self._print_summary(stats, dry_run)

    def _process_row(self, row, stats, force_update, skip_keywords):
        """Process a single CSV row and create/update database records"""

        # Extract and clean data - using the correct column mapping
        school_name = row.get('Sub Category', '').strip()  # School name is in Sub Category column
        category_name = row.get('Category', '').strip()
        product_name = row.get('Product Name', '').strip()
        variant_code = row.get('Code', '').strip()

        # Variations from Option columns
        option1 = row.get('Option 1', '').strip()  # Size, color, etc.
        option2 = row.get('Option 2', '').strip()  # Additional variation
        option3 = row.get('Option 3', '').strip()  # Additional variation

        # Additional fields to save
        barcode = row.get('Barcode', '').strip()

        # Skip if essential data is missing
        if not all([school_name, product_name, variant_code]):
            raise ValueError('Missing essential data: school name, product name, or variant code')

        # Skip products with unwanted keywords in product name (case-insensitive)
        # Only check product name for skip keywords
        product_name_lower = product_name.lower()

        for keyword in skip_keywords:
            if keyword in product_name_lower:
                stats['skipped'] = stats.get('skipped', 0) + 1
                self.stdout.write(f'Skipped product with keyword "{keyword}" in name: {product_name}')
                return  # Skip this row entirely

        # Clean school name - remove any prefixes if present
        if school_name.startswith('Wholesale Schools,'):
            school_name = school_name.replace('Wholesale Schools,', '').strip()

        # Create or get school
        school = self._get_or_create_school(school_name, stats, force_update)

        # For wholesale CSV, we don't have separate category column, using 'General' as default
        category = self._get_or_create_category(
            'General', '', stats, force_update
        )

        # Create or get product
        product = self._get_or_create_product(
            school, category, product_name, variant_code, row, stats, force_update
        )

        # Create or get variations for all option columns
        if option1:
            self._get_or_create_variation(
                product, option1, variant_code, barcode, row, stats, force_update
            )
        if option2:
            self._get_or_create_variation(
                product, option2, variant_code, barcode, row, stats, force_update
            )
        if option3:
            self._get_or_create_variation(
                product, option3, variant_code, barcode, row, stats, force_update
            )

    def _preview_row(self, row, stats, skip_keywords):
        """Preview what would be created/updated without making changes"""
        school_name = row.get('Sub Category', '').strip()  # Updated to use correct column
        category_name = row.get('Category', '').strip()
        product_name = row.get('Product Name', '').strip()
        variant_code = row.get('Code', '').strip()

        if not all([school_name, product_name, variant_code]):
            stats['errors'].append('Missing essential data')
            return

        # Skip products with unwanted keywords in product name (case-insensitive)
        # Only check product name for skip keywords
        product_name_lower = product_name.lower()

        for keyword in skip_keywords:
            if keyword in product_name_lower:
                stats['skipped'] = stats.get('skipped', 0) + 1
                self.stdout.write(f'Would skip product with keyword "{keyword}" in name: {product_name}')
                return  # Skip this row entirely

        self.stdout.write(f'Would process: {school_name} - {product_name} ({variant_code})')

    def _get_or_create_school(self, school_name, stats, force_update):
        """Create or get wholesale school"""
        school_slug = slugify(school_name)
        cin7_id = f'SCHOOL_{school_slug.upper()}'

        school, created = WholesaleSchool.objects.get_or_create(
            slug=school_slug,
            defaults={
                'cin7_id': cin7_id,
                'name': school_name,
                'is_active': True,
                'last_synced_at': timezone.now()
            }
        )

        if created:
            stats['schools_created'] += 1
            self.stdout.write(f'Created school: {school_name}')
        elif force_update:
            school.name = school_name
            school.last_synced_at = timezone.now()
            school.save()
            stats['schools_updated'] += 1

        return school

    def _get_or_create_category(self, category_name, sub_category_name, stats, force_update):
        """Create or get wholesale category"""
        # Use sub-category as the main category if available, otherwise use main category
        final_category_name = sub_category_name if sub_category_name else category_name

        if not final_category_name:
            final_category_name = 'General'

        category_slug = slugify(final_category_name)
        cin7_id = f'CAT_{category_slug.upper()}'

        category, created = WholesaleCategory.objects.get_or_create(
            slug=category_slug,
            defaults={
                'cin7_id': cin7_id,
                'name': final_category_name,
                'is_active': True,
                'last_synced_at': timezone.now()
            }
        )

        if created:
            stats['categories_created'] += 1
            self.stdout.write(f'Created category: {final_category_name}')
        elif force_update:
            category.name = final_category_name
            category.last_synced_at = timezone.now()
            category.save()
            stats['categories_updated'] += 1

        return category

    def _get_or_create_product(self, school, category, product_name, variant_code, row, stats, force_update):
        """Create or get wholesale product"""
        # Use variant code as the unique identifier
        cin7_id = variant_code if variant_code else f'PROD_{slugify(product_name)}'
        product_slug = slugify(f'{product_name}-{cin7_id}')

        # Extract pricing and other data with correct column names
        wholesale_price = self._parse_decimal(row.get('WholesaleExGST NZD Excl', ''))
        cost_price = self._parse_decimal(row.get('Cost NZD Excl', ''))
        retail_price = self._parse_decimal(row.get('Retail NZD Incl', ''))
        description = row.get('Description', '').strip() if 'Description' in row else ''

        # Determine stock status using Virtual Stock column
        stock_avail = self._parse_int(row.get('Virtual Stock', '0'))
        stock_status = 'in_stock' if stock_avail > 0 else 'out_of_stock'

        product, created = WholesaleProduct.objects.get_or_create(
            cin7_id=cin7_id,
            defaults={
                'name': product_name,
                'slug': product_slug,
                'school': school,
                'description': description,
                'cin7_sku': variant_code,
                'wholesale_price': wholesale_price,
                'cost_price': cost_price,
                'retail_price': retail_price,
                'stock_status': stock_status,
                'quantity_available': stock_avail,
                'quantity_on_hand': stock_avail,
                'is_active': True,
                'last_synced_at': timezone.now()
            }
        )

        if created:
            # Associate with category
            product.categories.add(category)
            stats['products_created'] += 1
            self.stdout.write(f'Created product: {product_name}')
        elif force_update:
            product.name = product_name
            product.description = description
            product.wholesale_price = wholesale_price
            product.cost_price = cost_price
            product.retail_price = retail_price
            product.stock_status = stock_status
            product.quantity_available = max(product.quantity_available, stock_avail)
            product.quantity_on_hand = max(product.quantity_on_hand, stock_avail)
            product.last_synced_at = timezone.now()
            product.save()

            # Ensure category association
            if category not in product.categories.all():
                product.categories.add(category)

            stats['products_updated'] += 1

        return product

    def _get_or_create_variation(self, product, size, variant_code, barcode, row, stats, force_update):
        """Create or get product variation"""
        # Extract variation-specific data with correct column names
        wholesale_price = self._parse_decimal(row.get('WholesaleExGST NZD Excl', ''))
        cost_price = self._parse_decimal(row.get('Cost NZD Excl', ''))
        retail_price = self._parse_decimal(row.get('Retail NZD Incl', ''))
        stock_avail = self._parse_int(row.get('Virtual Stock', '0'))

        # Create unique variation ID that includes product and size to avoid conflicts
        variation_cin7_id = f'{variant_code}_{slugify(size)}'

        variation, created = WholesaleProductVariation.objects.get_or_create(
            cin7_id=variation_cin7_id,
            defaults={
                'product': product,
                'variation_type': 'size',
                'variation_value': size,
                'cin7_sku': variant_code,
                'cin7_barcode': barcode,
                'wholesale_price': wholesale_price,
                'cost_price': cost_price,
                'retail_price': retail_price,
                'quantity_available': stock_avail,
                'quantity_on_hand': stock_avail,
                'is_active': True,
                'last_synced_at': timezone.now()
            }
        )

        if created:
            stats['variations_created'] += 1
        elif force_update:
            variation.variation_value = size
            variation.cin7_barcode = barcode
            variation.wholesale_price = wholesale_price
            variation.cost_price = cost_price
            variation.retail_price = retail_price
            variation.quantity_available = stock_avail
            variation.quantity_on_hand = stock_avail
            variation.last_synced_at = timezone.now()
            variation.save()
            stats['variations_updated'] += 1

        return variation

    def _parse_decimal(self, value):
        """Safely parse decimal value"""
        if not value or value == '0':
            return None
        try:
            return Decimal(str(value).replace(',', ''))
        except (InvalidOperation, ValueError):
            return None

    def _parse_int(self, value):
        """Safely parse integer value"""
        if not value:
            return 0
        try:
            return int(float(str(value).replace(',', '')))
        except (ValueError, TypeError):
            return 0

    def _print_summary(self, stats, dry_run):
        """Print import summary"""
        mode = "DRY RUN" if dry_run else "IMPORT"

        self.stdout.write(
            self.style.SUCCESS(f'\n=== {mode} SUMMARY ===')
        )
        self.stdout.write(f'Rows processed: {stats["rows_processed"]}')
        self.stdout.write(f'Schools created: {stats["schools_created"]}')
        self.stdout.write(f'Schools updated: {stats["schools_updated"]}')
        self.stdout.write(f'Categories created: {stats["categories_created"]}')
        self.stdout.write(f'Categories updated: {stats["categories_updated"]}')
        self.stdout.write(f'Products created: {stats["products_created"]}')
        self.stdout.write(f'Products updated: {stats["products_updated"]}')
        self.stdout.write(f'Variations created: {stats["variations_created"]}')
        self.stdout.write(f'Variations updated: {stats["variations_updated"]}')
        self.stdout.write(f'Products skipped: {stats.get("skipped", 0)}')

        if stats['errors']:
            self.stdout.write(
                self.style.ERROR(f'\nErrors encountered: {len(stats["errors"])}')
            )
            for error in stats['errors'][:10]:  # Show first 10 errors
                self.stdout.write(self.style.ERROR(f'  - {error}'))

            if len(stats['errors']) > 10:
                self.stdout.write(
                    self.style.ERROR(f'  ... and {len(stats["errors"]) - 10} more errors')
                )