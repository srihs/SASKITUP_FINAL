"""
Management command to compare Bespoke product data between cpq_kitup and kitup databases

Usage:
    python manage.py compare_bespoke_data
"""

from django.core.management.base import BaseCommand
from django.db import connections
from decimal import Decimal


class Command(BaseCommand):
    help = 'Compare Bespoke product pricing data between cpq_kitup and kitup databases'

    def handle(self, *args, **options):
        self.stdout.write("=" * 100)
        self.stdout.write(self.style.SUCCESS("BESPOKE DATA COMPARISON: cpq_kitup vs kitup"))
        self.stdout.write("=" * 100)

        # Query both databases
        cpq_data = self.query_database('cpq_kitup')
        kitup_data = self.query_database('kitup')

        if not cpq_data and not kitup_data:
            self.stdout.write(self.style.ERROR("Could not connect to databases"))
            return

        # Compare products
        self.stdout.write("\n" + "=" * 100)
        self.stdout.write(self.style.WARNING("BESPOKE_PRODUCT COMPARISON"))
        self.stdout.write("=" * 100)

        self.compare_products(cpq_data['products'], kitup_data['products'])

        # Compare variations
        self.stdout.write("\n" + "=" * 100)
        self.stdout.write(self.style.WARNING("BESPOKE_PRODUCT_VARIATION COMPARISON"))
        self.stdout.write("=" * 100)

        self.compare_variations(cpq_data['variations'], kitup_data['variations'])

        # Summary
        self.stdout.write("\n" + "=" * 100)
        self.stdout.write(self.style.SUCCESS("SUMMARY"))
        self.stdout.write("=" * 100)
        self.print_summary(cpq_data, kitup_data)

    def query_database(self, db_name):
        """Query bespoke data from specified database"""
        try:
            # Create connection using Django's connection string format
            from django.conf import settings

            # Get credentials from settings
            db_config = settings.DATABASES['default']

            self.stdout.write(f"\nQuerying {db_name} database...")

            # Query products
            product_query = f"""
                SELECT id, name, sku, cost_price, retail_price, price, margin_75_price
                FROM {db_name}.bespoke_product
                ORDER BY id
                LIMIT 5
            """

            # Query variations
            variation_query = f"""
                SELECT id, parent_product_id, sku, cost_price, retail_price, price, margin_75_price
                FROM {db_name}.bespoke_product_variation
                ORDER BY id
                LIMIT 5
            """

            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute(product_query)
                products = cursor.fetchall()

                cursor.execute(variation_query)
                variations = cursor.fetchall()

            return {
                'products': products,
                'variations': variations
            }

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error querying {db_name}: {e}"))
            return {'products': [], 'variations': []}

    def compare_products(self, cpq_products, kitup_products):
        """Compare product pricing data"""
        self.stdout.write("\ncpq_kitup Products (First 5):")
        self.stdout.write("-" * 100)
        self.print_products_table(cpq_products)

        self.stdout.write("\nkitup Products (First 5):")
        self.stdout.write("-" * 100)
        self.print_products_table(kitup_products)

        # Analyze differences
        if cpq_products and kitup_products:
            self.stdout.write("\n" + self.style.WARNING("KEY DIFFERENCES:"))
            self.analyze_product_differences(cpq_products, kitup_products)

    def compare_variations(self, cpq_variations, kitup_variations):
        """Compare variation pricing data"""
        self.stdout.write("\ncpq_kitup Variations (First 5):")
        self.stdout.write("-" * 100)
        self.print_variations_table(cpq_variations)

        self.stdout.write("\nkitup Variations (First 5):")
        self.stdout.write("-" * 100)
        self.print_variations_table(kitup_variations)

        # Analyze differences
        if cpq_variations and kitup_variations:
            self.stdout.write("\n" + self.style.WARNING("KEY DIFFERENCES:"))
            self.analyze_variation_differences(cpq_variations, kitup_variations)

    def print_products_table(self, products):
        """Print products in table format"""
        header = f"{'ID':<5} {'Name':<30} {'SKU':<20} {'Cost':<10} {'Retail':<10} {'Price':<10} {'Margin75':<10}"
        self.stdout.write(header)
        self.stdout.write("-" * 100)

        for p in products:
            row = f"{p[0]:<5} {p[1][:28]:<30} {p[2][:18]:<20} {str(p[3]):<10} {str(p[4]):<10} {str(p[5]):<10} {str(p[6]):<10}"
            self.stdout.write(row)

    def print_variations_table(self, variations):
        """Print variations in table format"""
        header = f"{'ID':<5} {'Parent':<8} {'SKU':<20} {'Cost':<10} {'Retail':<10} {'Price':<10} {'Margin75':<10}"
        self.stdout.write(header)
        self.stdout.write("-" * 100)

        for v in variations:
            row = f"{v[0]:<5} {v[1]:<8} {v[2][:18]:<20} {str(v[3]):<10} {str(v[4]):<10} {str(v[5]):<10} {str(v[6]):<10}"
            self.stdout.write(row)

    def analyze_product_differences(self, cpq_products, kitup_products):
        """Analyze and report key differences in products"""
        cpq_sample = cpq_products[0] if cpq_products else None
        kitup_sample = kitup_products[0] if kitup_products else None

        if cpq_sample and kitup_sample:
            # Compare price relationships
            cpq_cost = cpq_sample[3] or 0
            cpq_retail = cpq_sample[4] or 0
            cpq_price = cpq_sample[5] or 0
            cpq_margin = cpq_sample[6] or 0

            kitup_cost = kitup_sample[3] or 0
            kitup_retail = kitup_sample[4] or 0
            kitup_price = kitup_sample[5] or 0
            kitup_margin = kitup_sample[6] or 0

            self.stdout.write(f"\n  cpq_kitup:  price={cpq_price}, cost={cpq_cost}, retail={cpq_retail}, margin_75={cpq_margin}")
            self.stdout.write(f"  kitup:      price={kitup_price}, cost={kitup_cost}, retail={kitup_retail}, margin_75={kitup_margin}")

            # Check relationships
            if cpq_price == cpq_margin:
                self.stdout.write(self.style.SUCCESS("  ✓ cpq_kitup: price == margin_75_price"))
            elif cpq_price == cpq_cost:
                self.stdout.write(self.style.WARNING("  ⚠ cpq_kitup: price == cost_price"))

            if kitup_price == kitup_margin:
                self.stdout.write(self.style.SUCCESS("  ✓ kitup: price == margin_75_price"))
            elif kitup_price == kitup_cost:
                self.stdout.write(self.style.WARNING("  ⚠ kitup: price == cost_price"))

    def analyze_variation_differences(self, cpq_variations, kitup_variations):
        """Analyze and report key differences in variations"""
        cpq_sample = cpq_variations[0] if cpq_variations else None
        kitup_sample = kitup_variations[0] if kitup_variations else None

        if cpq_sample and kitup_sample:
            cpq_cost = cpq_sample[3] or 0
            cpq_retail = cpq_sample[4] or 0
            cpq_price = cpq_sample[5] or 0
            cpq_margin = cpq_sample[6] or 0

            kitup_cost = kitup_sample[3] or 0
            kitup_retail = kitup_sample[4] or 0
            kitup_price = kitup_sample[5] or 0
            kitup_margin = kitup_sample[6] or 0

            self.stdout.write(f"\n  cpq_kitup:  price={cpq_price}, cost={cpq_cost}, retail={cpq_retail}, margin_75={cpq_margin}")
            self.stdout.write(f"  kitup:      price={kitup_price}, cost={kitup_cost}, retail={kitup_retail}, margin_75={kitup_margin}")

            # Check relationships
            if cpq_price == cpq_margin:
                self.stdout.write(self.style.SUCCESS("  ✓ cpq_kitup: price == margin_75_price"))
            elif cpq_price == cpq_cost:
                self.stdout.write(self.style.WARNING("  ⚠ cpq_kitup: price == cost_price"))

            if kitup_price == kitup_margin:
                self.stdout.write(self.style.SUCCESS("  ✓ kitup: price == margin_75_price"))
            elif kitup_price == kitup_cost:
                self.stdout.write(self.style.WARNING("  ⚠ kitup: price == cost_price"))

    def print_summary(self, cpq_data, kitup_data):
        """Print summary of findings"""
        self.stdout.write("\nFindings:")
        self.stdout.write("  1. Check if price field values match between databases")
        self.stdout.write("  2. For discounts to work: price should be LESS than margin_75_price")
        self.stdout.write("  3. Discount formula: ((margin_75_price - price) / margin_75_price) * 100")
        self.stdout.write("\nRecommended SQL to fix kitup (if price is wrong):")
        self.stdout.write(self.style.SUCCESS("  UPDATE kitup.bespoke_product SET price = margin_75_price WHERE price != margin_75_price;"))
        self.stdout.write(self.style.SUCCESS("  UPDATE kitup.bespoke_product_variation SET price = margin_75_price WHERE price != margin_75_price;"))
