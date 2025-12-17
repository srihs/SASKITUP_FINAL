"""
Management command to fix BespokeProductVariation prices

Recalculates margin_75_price and price for all variations that have:
- cost_price > 0
- price = 0 or NULL

This fixes the issue where variations were synced with $0 prices.

Usage:
    python manage.py fix_variation_prices
    python manage.py fix_variation_prices --dry-run
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from decimal import Decimal
from bespoke.models import BespokeProductVariation


class Command(BaseCommand):
    help = 'Fix BespokeProductVariation prices by recalculating from cost_price'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without saving to database',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write("=" * 80)
        self.stdout.write(self.style.SUCCESS("BESPOKE VARIATION PRICE FIX"))
        self.stdout.write("=" * 80)

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be saved"))

        # Find variations with cost_price > 0 but price = 0 or NULL
        variations_to_fix = BespokeProductVariation.objects.filter(
            Q(price__isnull=True) | Q(price=0),
            cost_price__gt=0
        ).select_related('parent_product')

        total_count = variations_to_fix.count()

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("✓ No variations need fixing"))
            return

        self.stdout.write(f"\nFound {total_count} variations to fix\n")

        fixed_count = 0
        skipped_count = 0

        for variation in variations_to_fix:
            # Calculate margin_75_price
            margin_75_price = (variation.cost_price / Decimal('0.25')).quantize(Decimal('0.01'))

            # Determine new price (prefer margin_75_price, fallback to retail_price)
            new_price = margin_75_price or variation.retail_price

            if not new_price:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ⚠ Skipping {variation.sku}: No valid price calculated"
                    )
                )
                skipped_count += 1
                continue

            # Show what will change
            self.stdout.write(
                f"  {variation.sku} ({variation.parent_product.name}):\n"
                f"    Cost: ${variation.cost_price}\n"
                f"    Old Price: ${variation.price or 0}\n"
                f"    New Price: ${new_price}\n"
                f"    Margin 75%: ${margin_75_price}\n"
            )

            if not dry_run:
                variation.margin_75_price = margin_75_price
                variation.price = new_price
                variation.save()
                fixed_count += 1
            else:
                fixed_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 80)
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"DRY RUN COMPLETE"))
            self.stdout.write(f"  Would fix: {fixed_count} variations")
            self.stdout.write(f"  Would skip: {skipped_count} variations")
            self.stdout.write(self.style.WARNING("\nRun without --dry-run to apply changes"))
        else:
            self.stdout.write(self.style.SUCCESS(f"PRICE FIX COMPLETE"))
            self.stdout.write(f"  ✓ Fixed: {fixed_count} variations")
            self.stdout.write(f"  ⚠ Skipped: {skipped_count} variations")

        self.stdout.write("=" * 80)
