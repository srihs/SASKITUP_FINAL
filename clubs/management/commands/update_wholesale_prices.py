"""
Django management command for updating wholesale product prices from CSV import.

This command processes a CSV file containing product pricing information and updates
the corresponding WholesaleProduct records with calculated pricing fields including
margin_75_price and discount_percentage.

Usage:
    python manage.py update_wholesale_prices [OPTIONS]

Author: Claude Code SuperClaude
"""

import csv
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import unicodedata
import re
import sys

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.db.models import Q

from schools.models import WholesaleProduct, WholesaleSchool
from schools.utils.price_calculation import (
    ProductPriceManager, PriceCalculator, batch_calculate_pricing,
    generate_pricing_analysis, generate_pricing_report
)

logger = logging.getLogger(__name__)


class ProductMatcher:
    """
    Handles product matching logic with multiple fallback strategies.
    """

    def __init__(self):
        self.match_stats = {
            'by_code': 0,
            'by_barcode': 0,
            'by_style_code': 0,
            'no_match': 0,
            'multiple_matches': 0
        }

    def match_product(self, csv_row: Dict[str, str]) -> Tuple[Optional[WholesaleProduct], str]:
        """
        Match CSV row to WholesaleProduct using cascading matching logic.

        Args:
            csv_row: Dictionary containing CSV row data

        Returns:
            Tuple of (matched_product, match_type) where match_type indicates
            how the match was found or why it failed
        """
        code = csv_row.get('Code', '').strip()
        barcode = csv_row.get('Barcode', '').strip()
        style_code = csv_row.get('Style Code', '').strip()

        # Primary: Match by product code (Code → cin7_sku)
        if code:
            products = WholesaleProduct.objects.filter(cin7_sku=code)
            if products.count() == 1:
                self.match_stats['by_code'] += 1
                return products.first(), 'code'
            elif products.count() > 1:
                self.match_stats['multiple_matches'] += 1
                return None, f'multiple_matches_by_code ({products.count()} found)'

        # Secondary: Match by barcode (Barcode → cin7_barcode)
        if barcode:
            products = WholesaleProduct.objects.filter(cin7_barcode=barcode)
            if products.count() == 1:
                self.match_stats['by_barcode'] += 1
                return products.first(), 'barcode'
            elif products.count() > 1:
                self.match_stats['multiple_matches'] += 1
                return None, f'multiple_matches_by_barcode ({products.count()} found)'

        # Tertiary: Match by Style Code (Style Code → cin7_id)
        if style_code:
            products = WholesaleProduct.objects.filter(cin7_id=style_code)
            if products.count() == 1:
                self.match_stats['by_style_code'] += 1
                return products.first(), 'style_code'
            elif products.count() > 1:
                self.match_stats['multiple_matches'] += 1
                return None, f'multiple_matches_by_style_code ({products.count()} found)'

        # No match found
        self.match_stats['no_match'] += 1
        return None, 'no_match'


class SchoolMatcher:
    """
    Handles school matching logic with name normalization.
    """

    def __init__(self):
        self.match_stats = {
            'exact_match': 0,
            'normalized_match': 0,
            'no_match': 0,
            'multiple_matches': 0
        }
        self._school_cache = {}
        self._populate_school_cache()

    def _populate_school_cache(self):
        """Pre-populate school cache with normalized names for efficient matching."""
        schools = WholesaleSchool.objects.all()
        for school in schools:
            normalized_name = self._normalize_school_name(school.name)
            if normalized_name not in self._school_cache:
                self._school_cache[normalized_name] = []
            self._school_cache[normalized_name].append(school)

    def _normalize_school_name(self, name: str) -> str:
        """
        Normalize school name for comparison.

        Args:
            name: Raw school name

        Returns:
            Normalized school name (lowercase, stripped, normalized whitespace)
        """
        if not name:
            return ''

        # Normalize unicode characters
        normalized = unicodedata.normalize('NFKD', name)

        # Convert to lowercase and strip
        normalized = normalized.lower().strip()

        # Replace multiple whitespace with single space
        normalized = re.sub(r'\s+', ' ', normalized)

        # Remove common suffixes/prefixes that might vary
        suffixes = ['school', 'high school', 'college', 'academy', 'institute']
        for suffix in suffixes:
            if normalized.endswith(f' {suffix}'):
                normalized = normalized[:-len(f' {suffix}')].strip()
                break

        return normalized

    def match_school(self, school_name: str) -> Tuple[Optional[WholesaleSchool], str]:
        """
        Match school name to WholesaleSchool using normalization.

        Args:
            school_name: School name from CSV

        Returns:
            Tuple of (matched_school, match_type)
        """
        if not school_name or not school_name.strip():
            self.match_stats['no_match'] += 1
            return None, 'empty_name'

        # Try exact match first
        exact_matches = WholesaleSchool.objects.filter(name__iexact=school_name.strip())
        if exact_matches.count() == 1:
            self.match_stats['exact_match'] += 1
            return exact_matches.first(), 'exact'
        elif exact_matches.count() > 1:
            self.match_stats['multiple_matches'] += 1
            return None, f'multiple_exact_matches ({exact_matches.count()} found)'

        # Try normalized match
        normalized_name = self._normalize_school_name(school_name)
        if normalized_name in self._school_cache:
            matches = self._school_cache[normalized_name]
            if len(matches) == 1:
                self.match_stats['normalized_match'] += 1
                return matches[0], 'normalized'
            else:
                self.match_stats['multiple_matches'] += 1
                return None, f'multiple_normalized_matches ({len(matches)} found)'

        # No match found
        self.match_stats['no_match'] += 1
        return None, 'no_match'


class CSVProcessor:
    """
    Handles CSV file processing with encoding detection and validation.
    """

    def __init__(self, csv_file_path: str):
        self.csv_file_path = Path(csv_file_path)
        self.required_columns = [
            'Code', 'Barcode', 'Style Code', 'School or Club Name', 'Sub Category',
            'Cost NZD Excl', 'Product Name'
        ]

    def validate_file(self) -> bool:
        """Validate that the CSV file exists and is readable."""
        if not self.csv_file_path.exists():
            raise CommandError(f"CSV file not found: {self.csv_file_path}")

        if not self.csv_file_path.is_file():
            raise CommandError(f"Path is not a file: {self.csv_file_path}")

        return True

    def detect_encoding(self) -> str:
        """
        Detect CSV file encoding.

        Returns:
            Detected encoding string
        """
        encodings_to_try = ['utf-8', 'utf-8-sig', 'latin1', 'cp1252', 'iso-8859-1']

        for encoding in encodings_to_try:
            try:
                with open(self.csv_file_path, 'r', encoding=encoding) as f:
                    f.read(1024)  # Try to read first 1KB
                return encoding
            except UnicodeDecodeError:
                continue

        # Fallback to utf-8 with error handling
        return 'utf-8'

    def validate_columns(self, reader) -> bool:
        """
        Validate that all required columns are present.

        Args:
            reader: CSV DictReader object

        Returns:
            True if all required columns are present
        """
        fieldnames = reader.fieldnames or []
        missing_columns = [col for col in self.required_columns if col not in fieldnames]

        if missing_columns:
            raise CommandError(
                f"Missing required columns in CSV: {', '.join(missing_columns)}\n"
                f"Available columns: {', '.join(fieldnames)}"
            )

        return True

    def process_csv(self) -> List[Dict[str, str]]:
        """
        Process CSV file and return list of rows.

        Returns:
            List of dictionaries containing CSV row data
        """
        self.validate_file()
        encoding = self.detect_encoding()

        # Increase CSV field size limit to handle large fields
        maxInt = sys.maxsize
        while True:
            try:
                csv.field_size_limit(maxInt)
                break
            except OverflowError:
                maxInt = int(maxInt / 10)

        rows = []
        try:
            with open(self.csv_file_path, 'r', encoding=encoding, errors='replace') as csvfile:
                reader = csv.DictReader(csvfile)
                self.validate_columns(reader)

                for row_num, row in enumerate(reader, start=2):  # Start at 2 since header is row 1
                    # Clean row data - truncate very long fields to prevent memory issues
                    cleaned_row = {}
                    for k, v in row.items():
                        if v:
                            # Truncate very long fields but keep important ones intact
                            if k in ['Description', 'Description 2'] and len(v) > 1000:
                                cleaned_row[k] = v[:1000] + '...'
                            else:
                                cleaned_row[k] = v.strip() if len(v) < 10000 else v[:10000].strip()
                        else:
                            cleaned_row[k] = ''

                    cleaned_row['_row_number'] = row_num
                    rows.append(cleaned_row)

        except Exception as e:
            raise CommandError(f"Error processing CSV file: {e}")

        return rows


class PriceCalculator:
    """
    Handles price calculations for wholesale products.
    """

    @staticmethod
    def parse_decimal(value: str) -> Optional[Decimal]:
        """
        Parse string value to Decimal with error handling.

        Args:
            value: String value to parse

        Returns:
            Decimal value or None if parsing fails
        """
        if not value or not value.strip():
            return None

        # Clean the value (remove currency symbols, extra spaces)
        cleaned = re.sub(r'[^\d.-]', '', value.strip())

        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def calculate_margin_75_price(cost_price: Decimal) -> Optional[Decimal]:
        """
        Calculate 75% margin price (Cost ÷ 0.25).

        Args:
            cost_price: Cost price from CSV

        Returns:
            Calculated 75% margin price
        """
        if not cost_price or cost_price <= 0:
            return None

        try:
            return cost_price / Decimal('0.25')
        except (InvalidOperation, ZeroDivisionError):
            return None

    @staticmethod
    def calculate_discount_percentage(margin_75_price: Decimal, current_price: Decimal) -> Optional[Decimal]:
        """
        Calculate discount percentage from 75% margin price.

        Args:
            margin_75_price: 75% margin price
            current_price: Current wholesale price

        Returns:
            Discount percentage
        """
        if not margin_75_price or not current_price or margin_75_price <= 0:
            return None

        try:
            discount = ((margin_75_price - current_price) / margin_75_price) * 100
            return max(Decimal('0'), discount)  # Don't allow negative discounts
        except (InvalidOperation, ZeroDivisionError):
            return None


class Command(BaseCommand):
    """
    Django management command for updating wholesale product prices from CSV.
    """

    help = 'Update wholesale product prices from CSV file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-file',
            type=str,
            default='/Users/sas/Downloads/All products.csv',
            help='Path to CSV file (default: /Users/sas/Downloads/All products.csv)'
        )

        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without updating database'
        )

        parser.add_argument(
            '--school-filter',
            type=str,
            help='Filter processing to specific school (partial name match)'
        )

        parser.add_argument(
            '--limit',
            type=int,
            help='Limit number of rows to process (for testing)'
        )

        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )

        parser.add_argument(
            '--report-file',
            type=str,
            help='Save detailed report to file'
        )

        parser.add_argument(
            '--use-enhanced-engine',
            action='store_true',
            help='Use the new enhanced price calculation engine for better performance and validation'
        )

        parser.add_argument(
            '--generate-analysis-report',
            action='store_true',
            help='Generate comprehensive pricing analysis report after processing'
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.product_matcher = ProductMatcher()
        self.school_matcher = SchoolMatcher()
        self.price_calculator = PriceCalculator()

        # Processing statistics
        self.stats = {
            'total_rows': 0,
            'processed_rows': 0,
            'skipped_rows': 0,
            'updated_products': 0,
            'errors': 0,
        }

        # Error tracking
        self.errors = []
        self.unmatched_products = []
        self.unmatched_schools = []

    def handle(self, *args, **options):
        """Main command handler."""
        self.verbosity = options.get('verbosity', 1)
        self.dry_run = options.get('dry_run', False)
        self.school_filter = options.get('school_filter')
        self.limit = options.get('limit')
        self.verbose = options.get('verbose', False)
        self.report_file = options.get('report_file')
        self.use_enhanced_engine = options.get('use_enhanced_engine', False)
        self.generate_analysis_report = options.get('generate_analysis_report', False)

        csv_file = options.get('csv_file')

        engine_type = "Enhanced Engine" if self.use_enhanced_engine else "Legacy Engine"
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[DRY RUN] ' if self.dry_run else ''}Starting wholesale price update using {engine_type}..."
            )
        )
        self.stdout.write(f"CSV file: {csv_file}")

        try:
            # Process CSV file
            processor = CSVProcessor(csv_file)
            rows = processor.process_csv()
            self.stats['total_rows'] = len(rows)

            self.stdout.write(f"Found {len(rows)} rows in CSV file")

            # Apply limit if specified
            if self.limit:
                rows = rows[:self.limit]
                self.stdout.write(f"Limited processing to {len(rows)} rows")

            # Process rows
            if self.use_enhanced_engine:
                self._process_rows_enhanced(rows)
            else:
                self._process_rows(rows)

            # Generate reports
            self._generate_reports()

            # Generate analysis report if requested
            if self.generate_analysis_report:
                self._generate_analysis_report()

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Command failed: {e}")
            )
            logger.exception("Wholesale price update command failed")
            raise CommandError(str(e))

    def _process_rows(self, rows: List[Dict[str, str]]):
        """Process CSV rows and update products."""

        for row in rows:
            try:
                with transaction.atomic():
                    self._process_single_row(row)
            except Exception as e:
                self.stats['errors'] += 1
                error_msg = f"Row {row.get('_row_number', '?')}: {e}"
                self.errors.append(error_msg)

                if self.verbose:
                    self.stdout.write(
                        self.style.ERROR(f"Error processing row: {error_msg}")
                    )

    def _process_single_row(self, row: Dict[str, str]):
        """Process a single CSV row."""
        row_num = row.get('_row_number', '?')
        school_name = row.get('School or Club Name', '').strip()
        sub_category = row.get('Sub Category', '').strip()
        product_name = row.get('Product Name', '').strip()
        cost_nzd_excl = row.get('Cost NZD Excl', '').strip()

        # Use Sub Category as school name if School or Club Name is empty
        if not school_name and sub_category:
            school_name = sub_category

        # Skip empty or invalid rows
        if not school_name or not product_name:
            self.stats['skipped_rows'] += 1
            if self.verbose:
                self.stdout.write(f"Skipping row {row_num}: Missing school or product name")
            return

        # Apply school filter
        if self.school_filter and self.school_filter.lower() not in school_name.lower():
            self.stats['skipped_rows'] += 1
            return

        # Match school
        school, school_match_type = self.school_matcher.match_school(school_name)
        if not school:
            self.unmatched_schools.append({
                'row': row_num,
                'school_name': school_name,
                'reason': school_match_type,
                'product_name': product_name
            })
            self.stats['skipped_rows'] += 1
            if self.verbose:
                self.stdout.write(f"Row {row_num}: School not found - {school_name}")
            return

        # Match product
        product, product_match_type = self.product_matcher.match_product(row)
        if not product:
            self.unmatched_products.append({
                'row': row_num,
                'school_name': school_name,
                'product_name': product_name,
                'code': row.get('Code', ''),
                'barcode': row.get('Barcode', ''),
                'style_code': row.get('Style Code', ''),
                'reason': product_match_type
            })
            self.stats['skipped_rows'] += 1
            if self.verbose:
                self.stdout.write(f"Row {row_num}: Product not found - {product_name}")
            return

        # Verify product belongs to matched school
        if product.school_id != school.id:
            self.errors.append(
                f"Row {row_num}: Product {product.name} belongs to {product.school.name}, "
                f"not {school.name}"
            )
            self.stats['skipped_rows'] += 1
            return

        # Parse and calculate prices
        cost_price = self.price_calculator.parse_decimal(cost_nzd_excl)
        if not cost_price or cost_price <= 0:
            if self.verbose:
                self.stdout.write(f"Row {row_num}: Invalid cost price - {cost_nzd_excl}")
            self.stats['skipped_rows'] += 1
            return

        # Calculate new pricing fields
        margin_75_price = self.price_calculator.calculate_margin_75_price(cost_price)
        discount_percentage = None
        if margin_75_price and product.wholesale_price:
            discount_percentage = self.price_calculator.calculate_discount_percentage(
                margin_75_price, product.wholesale_price
            )

        # Update product (if not dry run)
        if not self.dry_run:
            product.cost_price = cost_price
            product.margin_75_price = margin_75_price
            product.discount_percentage = discount_percentage
            product.last_price_update = timezone.now()
            product.save(update_fields=[
                'cost_price', 'margin_75_price', 'discount_percentage', 'last_price_update'
            ])

        self.stats['updated_products'] += 1
        self.stats['processed_rows'] += 1

        if self.verbose:
            self.stdout.write(
                f"Row {row_num}: Updated {product.name} "
                f"(Cost: ${cost_price}, 75% Margin: ${margin_75_price}, "
                f"Discount: {discount_percentage}%)"
            )

    def _process_rows_enhanced(self, rows: List[Dict[str, str]]):
        """Process CSV rows using the enhanced calculation engine."""
        # Collect product-cost price mappings for batch processing
        product_cost_mapping = {}
        valid_products = []

        for row in rows:
            try:
                school_name, product, cost_price = self._extract_row_data(row)
                if school_name and product and cost_price:
                    product_cost_mapping[product.id] = cost_price
                    valid_products.append(product)
                    self.stats['processed_rows'] += 1
                else:
                    self.stats['skipped_rows'] += 1
            except Exception as e:
                self.stats['errors'] += 1
                self.errors.append(f"Row {row.get('_row_number', '?')}: {e}")

        if not valid_products:
            self.stdout.write(self.style.WARNING("No valid products found for batch processing"))
            return

        self.stdout.write(f"Processing {len(valid_products)} products using enhanced engine...")

        # Use batch processing with the enhanced engine
        try:
            if not self.dry_run:
                batch_result = batch_calculate_pricing(
                    valid_products,
                    cost_prices=product_cost_mapping
                )

                # Update statistics
                self.stats['updated_products'] = batch_result.successful_updates
                self.stats['errors'] += batch_result.failed_updates

                # Log batch results
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Enhanced batch processing completed: "
                        f"{batch_result.successful_updates} updated, "
                        f"{batch_result.failed_updates} failed, "
                        f"Success rate: {batch_result.success_rate:.1f}%, "
                        f"Processing time: {batch_result.processing_time:.2f}s"
                    )
                )

                # Add batch errors to our error list
                if batch_result.errors:
                    self.errors.extend(batch_result.errors)

                # Add batch warnings
                if batch_result.warnings and self.verbose:
                    for warning in batch_result.warnings[:10]:  # Show first 10 warnings
                        self.stdout.write(self.style.WARNING(f"Warning: {warning}"))

            else:
                # For dry run, just simulate the enhanced processing
                calculator = PriceCalculator()
                for product in valid_products:
                    cost_price = product_cost_mapping[product.id]
                    price_data = calculator.calculate_all_prices(
                        cost_price=cost_price,
                        wholesale_price=product.wholesale_price,
                        retail_price=product.retail_price
                    )

                    if price_data.is_valid:
                        self.stats['updated_products'] += 1
                        if self.verbose:
                            self.stdout.write(
                                f"[DRY RUN] Would update {product.name}: "
                                f"Cost: ${cost_price}, "
                                f"75% Margin: ${price_data.margin_75_price}, "
                                f"Discount: {price_data.discount_percentage}%"
                            )
                    else:
                        self.stats['errors'] += 1
                        if self.verbose:
                            self.stdout.write(
                                self.style.ERROR(f"[DRY RUN] Validation failed for {product.name}: {price_data.errors}")
                            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Enhanced batch processing failed: {e}"))
            logger.exception("Enhanced batch processing failed")

    def _extract_row_data(self, row: Dict[str, str]) -> Tuple[Optional[str], Optional[WholesaleProduct], Optional[Decimal]]:
        """Extract and validate data from a CSV row for enhanced processing."""
        row_num = row.get('_row_number', '?')
        school_name = row.get('School or Club Name', '').strip()
        sub_category = row.get('Sub Category', '').strip()
        product_name = row.get('Product Name', '').strip()
        cost_nzd_excl = row.get('Cost NZD Excl', '').strip()

        # Use Sub Category as school name if School or Club Name is empty
        if not school_name and sub_category:
            school_name = sub_category

        # Skip empty or invalid rows
        if not school_name or not product_name:
            if self.verbose:
                self.stdout.write(f"Skipping row {row_num}: Missing school or product name")
            return None, None, None

        # Apply school filter
        if self.school_filter and self.school_filter.lower() not in school_name.lower():
            return None, None, None

        # Match school
        school, school_match_type = self.school_matcher.match_school(school_name)
        if not school:
            self.unmatched_schools.append({
                'row': row_num,
                'school_name': school_name,
                'reason': school_match_type,
                'product_name': product_name
            })
            if self.verbose:
                self.stdout.write(f"Row {row_num}: School not found - {school_name}")
            return None, None, None

        # Match product
        product, product_match_type = self.product_matcher.match_product(row)
        if not product:
            self.unmatched_products.append({
                'row': row_num,
                'school_name': school_name,
                'product_name': product_name,
                'code': row.get('Code', ''),
                'barcode': row.get('Barcode', ''),
                'style_code': row.get('Style Code', ''),
                'reason': product_match_type
            })
            if self.verbose:
                self.stdout.write(f"Row {row_num}: Product not found - {product_name}")
            return None, None, None

        # Verify product belongs to matched school
        if product.school_id != school.id:
            self.errors.append(
                f"Row {row_num}: Product {product.name} belongs to {product.school.name}, "
                f"not {school.name}"
            )
            return None, None, None

        # Parse and validate cost price
        cost_price = self.price_calculator.parse_decimal(cost_nzd_excl)
        if not cost_price or cost_price <= 0:
            if self.verbose:
                self.stdout.write(f"Row {row_num}: Invalid cost price - {cost_nzd_excl}")
            return None, None, None

        return school_name, product, cost_price

    def _generate_analysis_report(self):
        """Generate comprehensive pricing analysis report."""
        try:
            self.stdout.write("\n" + "="*60)
            self.stdout.write(self.style.SUCCESS("PRICING ANALYSIS REPORT"))
            self.stdout.write("="*60)

            # Generate analysis for all active wholesale products
            stats = generate_pricing_analysis()

            # Display key statistics
            self.stdout.write(f"Total Active Products: {stats.total_products:,}")
            self.stdout.write(f"Products with Cost Price: {stats.products_with_cost:,}")
            self.stdout.write(f"Products with 75% Margin Price: {stats.products_with_margin_75:,}")

            if stats.avg_cost_price:
                self.stdout.write(f"Average Cost Price: ${stats.avg_cost_price:.2f}")

            if stats.avg_margin_75_price:
                self.stdout.write(f"Average 75% Margin Price: ${stats.avg_margin_75_price:.2f}")

            if stats.avg_discount_percentage is not None:
                self.stdout.write(f"Average Discount: {stats.avg_discount_percentage:.1f}%")

            # Alert on issues
            if stats.high_discount_products > 0:
                self.stdout.write(
                    self.style.WARNING(f"High Discount Products (>50%): {stats.high_discount_products:,}")
                )

            if stats.negative_margin_products > 0:
                self.stdout.write(
                    self.style.ERROR(f"Negative Margin Products: {stats.negative_margin_products:,}")
                )

            if stats.low_margin_products > 0:
                self.stdout.write(
                    self.style.WARNING(f"Low Margin Products (<10%): {stats.low_margin_products:,}")
                )

            # Save detailed report if file specified
            if self.report_file:
                report_content = generate_pricing_report(format_type='text')
                analysis_file = self.report_file.replace('.txt', '_analysis.txt')
                with open(analysis_file, 'w', encoding='utf-8') as f:
                    f.write(report_content)
                self.stdout.write(
                    self.style.SUCCESS(f"Detailed analysis report saved to: {analysis_file}")
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to generate analysis report: {e}")
            )
            logger.error(f"Analysis report generation failed: {e}")

    def _generate_reports(self):
        """Generate and display processing reports."""

        # Summary report
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS("PROCESSING SUMMARY"))
        self.stdout.write("="*60)

        self.stdout.write(f"Total rows in CSV: {self.stats['total_rows']}")
        self.stdout.write(f"Processed rows: {self.stats['processed_rows']}")
        self.stdout.write(f"Skipped rows: {self.stats['skipped_rows']}")
        self.stdout.write(f"Updated products: {self.stats['updated_products']}")
        self.stdout.write(f"Errors: {self.stats['errors']}")

        if self.dry_run:
            self.stdout.write(
                self.style.WARNING("\nThis was a DRY RUN - no changes were made to the database")
            )

        # Product matching stats
        self.stdout.write("\n" + "-"*40)
        self.stdout.write("PRODUCT MATCHING STATISTICS")
        self.stdout.write("-"*40)
        for match_type, count in self.product_matcher.match_stats.items():
            self.stdout.write(f"{match_type.replace('_', ' ').title()}: {count}")

        # School matching stats
        self.stdout.write("\n" + "-"*40)
        self.stdout.write("SCHOOL MATCHING STATISTICS")
        self.stdout.write("-"*40)
        for match_type, count in self.school_matcher.match_stats.items():
            self.stdout.write(f"{match_type.replace('_', ' ').title()}: {count}")

        # Error reports
        if self.errors:
            self.stdout.write("\n" + "-"*40)
            self.stdout.write(self.style.ERROR("ERRORS"))
            self.stdout.write("-"*40)
            for error in self.errors[:10]:  # Show first 10 errors
                self.stdout.write(self.style.ERROR(error))
            if len(self.errors) > 10:
                self.stdout.write(f"... and {len(self.errors) - 10} more errors")

        # Unmatched products (top 10)
        if self.unmatched_products:
            self.stdout.write("\n" + "-"*40)
            self.stdout.write(self.style.WARNING("UNMATCHED PRODUCTS (First 10)"))
            self.stdout.write("-"*40)
            for item in self.unmatched_products[:10]:
                self.stdout.write(
                    f"Row {item['row']}: {item['product_name']} "
                    f"(Code: {item['code']}, Reason: {item['reason']})"
                )
            if len(self.unmatched_products) > 10:
                self.stdout.write(f"... and {len(self.unmatched_products) - 10} more unmatched products")

        # Unmatched schools (top 10)
        if self.unmatched_schools:
            self.stdout.write("\n" + "-"*40)
            self.stdout.write(self.style.WARNING("UNMATCHED SCHOOLS (First 10)"))
            self.stdout.write("-"*40)
            for item in self.unmatched_schools[:10]:
                self.stdout.write(
                    f"Row {item['row']}: {item['school_name']} "
                    f"(Reason: {item['reason']})"
                )
            if len(self.unmatched_schools) > 10:
                self.stdout.write(f"... and {len(self.unmatched_schools) - 10} more unmatched schools")

        # Save detailed report if requested
        if self.report_file:
            self._save_detailed_report()

    def _save_detailed_report(self):
        """Save detailed report to file."""
        try:
            with open(self.report_file, 'w', encoding='utf-8') as f:
                f.write("WHOLESALE PRICE UPDATE DETAILED REPORT\n")
                f.write("="*50 + "\n\n")

                f.write(f"Generated: {timezone.now()}\n")
                f.write(f"Dry Run: {self.dry_run}\n\n")

                # Statistics
                f.write("PROCESSING STATISTICS\n")
                f.write("-"*30 + "\n")
                for key, value in self.stats.items():
                    f.write(f"{key.replace('_', ' ').title()}: {value}\n")

                f.write("\nPRODUCT MATCHING STATISTICS\n")
                f.write("-"*30 + "\n")
                for match_type, count in self.product_matcher.match_stats.items():
                    f.write(f"{match_type.replace('_', ' ').title()}: {count}\n")

                f.write("\nSCHOOL MATCHING STATISTICS\n")
                f.write("-"*30 + "\n")
                for match_type, count in self.school_matcher.match_stats.items():
                    f.write(f"{match_type.replace('_', ' ').title()}: {count}\n")

                # Detailed errors
                if self.errors:
                    f.write(f"\nALL ERRORS ({len(self.errors)})\n")
                    f.write("-"*30 + "\n")
                    for error in self.errors:
                        f.write(f"{error}\n")

                # All unmatched products
                if self.unmatched_products:
                    f.write(f"\nALL UNMATCHED PRODUCTS ({len(self.unmatched_products)})\n")
                    f.write("-"*30 + "\n")
                    for item in self.unmatched_products:
                        f.write(
                            f"Row {item['row']}: {item['product_name']} | "
                            f"School: {item['school_name']} | "
                            f"Code: {item['code']} | "
                            f"Barcode: {item['barcode']} | "
                            f"Style Code: {item['style_code']} | "
                            f"Reason: {item['reason']}\n"
                        )

                # All unmatched schools
                if self.unmatched_schools:
                    f.write(f"\nALL UNMATCHED SCHOOLS ({len(self.unmatched_schools)})\n")
                    f.write("-"*30 + "\n")
                    for item in self.unmatched_schools:
                        f.write(
                            f"Row {item['row']}: {item['school_name']} | "
                            f"Product: {item['product_name']} | "
                            f"Reason: {item['reason']}\n"
                        )

            self.stdout.write(
                self.style.SUCCESS(f"\nDetailed report saved to: {self.report_file}")
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to save report file: {e}")
            )