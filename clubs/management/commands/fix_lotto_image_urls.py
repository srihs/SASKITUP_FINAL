"""
Management command to fix LOTTO product and variation image URLs to use configured domain
"""
from django.core.management.base import BaseCommand
from clubs.models_lotto import LottoProduct, LottoProductVariation
from clubs.utils import normalize_lotto_image_url
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix LOTTO product and variation image URLs to use configured domain from settings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without updating database',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output for each change',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No database changes will be made'))

        # Fix product images
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write('Fixing LOTTO Product Images')
        self.stdout.write('=' * 70)

        products = LottoProduct.objects.exclude(image='')
        product_count = 0
        product_changes = []

        for product in products:
            old_url = product.image if product.image else None
            if old_url:
                new_url = normalize_lotto_image_url(old_url)
                if new_url and new_url != old_url:
                    product_changes.append({
                        'product': product,
                        'old_url': old_url,
                        'new_url': new_url
                    })

                    if verbose:
                        self.stdout.write(f'\nProduct: {product.name}')
                        self.stdout.write(f'  Old: {old_url}')
                        self.stdout.write(f'  New: {new_url}')

                    if not dry_run:
                        product.image = new_url
                        product.save(update_fields=['image', 'updated_at'])
                        product_count += 1

        if dry_run:
            product_count = len(product_changes)

        # Fix variation images
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write('Fixing LOTTO Product Variation Images')
        self.stdout.write('=' * 70)

        variations = LottoProductVariation.objects.exclude(image='')
        variation_count = 0
        variation_changes = []

        for variation in variations:
            old_url = variation.image if variation.image else None
            if old_url:
                new_url = normalize_lotto_image_url(old_url)
                if new_url and new_url != old_url:
                    variation_changes.append({
                        'variation': variation,
                        'old_url': old_url,
                        'new_url': new_url
                    })

                    if verbose:
                        self.stdout.write(f'\nVariation: {variation.product.name} - {variation.variation_value}')
                        self.stdout.write(f'  Old: {old_url}')
                        self.stdout.write(f'  New: {new_url}')

                    if not dry_run:
                        variation.image = new_url
                        variation.save(update_fields=['image', 'updated_at'])
                        variation_count += 1

        if dry_run:
            variation_count = len(variation_changes)

        # Summary
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write('Summary')
        self.stdout.write('=' * 70)

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nWould fix {product_count} product images and {variation_count} variation images'
                )
            )
            self.stdout.write('\nRun without --dry-run to apply changes')
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nFixed {product_count} product images and {variation_count} variation images'
                )
            )

        # Log statistics
        logger.info(
            f'fix_lotto_image_urls: {"[DRY RUN] " if dry_run else ""}'
            f'Products: {product_count}, Variations: {variation_count}'
        )
