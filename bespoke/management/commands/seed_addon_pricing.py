from django.core.management.base import BaseCommand
from decimal import Decimal
from bespoke.models import AddonPricingTier, AddonSizeDefinition, AddonPrice


class Command(BaseCommand):
    help = 'Seed initial addon pricing data (tiers and sizes - prices must be entered manually)'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS('SEEDING ADDON PRICING DATA'))
        self.stdout.write(self.style.SUCCESS('=' * 80))

        # Create pricing tiers
        self.stdout.write('\n1. Creating Pricing Tiers...')
        tiers_data = {
            'heat_transfer': [
                {'min': 1, 'max': 9, 'label': '1-9'},
                {'min': 10, 'max': 25, 'label': '10-25'},
                {'min': 26, 'max': 50, 'label': '26-50'},
                {'min': 51, 'max': 199, 'label': '51-199'},
                {'min': 200, 'max': None, 'label': '200+'},
            ],
            'screen_print': [
                {'min': 1, 'max': 9, 'label': '1-9'},
                {'min': 10, 'max': 25, 'label': '10-25'},
                {'min': 26, 'max': 50, 'label': '26-50'},
                {'min': 51, 'max': 199, 'label': '51-199'},
                {'min': 200, 'max': None, 'label': '200+'},
            ],
            'emb_applique': [
                {'min': 1, 'max': 9, 'label': '1-9'},
                {'min': 10, 'max': 25, 'label': '10-25'},
                {'min': 26, 'max': 50, 'label': '26-50'},
                {'min': 51, 'max': 199, 'label': '51-199'},
                {'min': 200, 'max': None, 'label': '200+'},
            ],
        }

        tier_count = 0
        for addon_type, tiers in tiers_data.items():
            for idx, tier_data in enumerate(tiers):
                tier, created = AddonPricingTier.objects.get_or_create(
                    addon_type=addon_type,
                    min_quantity=tier_data['min'],
                    max_quantity=tier_data['max'],
                    defaults={
                        'display_label': tier_data['label'],
                        'sort_order': idx,
                    }
                )
                if created:
                    tier_count += 1
                    self.stdout.write(f"  ✓ Created: {tier}")
                else:
                    self.stdout.write(f"  - Exists: {tier}")

        self.stdout.write(self.style.SUCCESS(f'\nCreated {tier_count} new pricing tiers'))

        # Create size definitions
        self.stdout.write('\n2. Creating Size Definitions...')
        sizes_data = {
            'heat_transfer': [
                {'size': 'small', 'width': Decimal('5.00'), 'height': Decimal('5.00'), 'label': 'Small - 8x8 cm'},
                {'size': 'medium', 'width': Decimal('8.00'), 'height': Decimal('8.00'), 'label': 'Medium - 16x16 cm'},
                {'size': 'large', 'width': Decimal('11.00'), 'height': Decimal('11.00'), 'label': 'Large - 25x25 cm'},
            ],
            'screen_print': [
                {'size': 'small', 'width': Decimal('5.00'), 'height': Decimal('5.00'), 'label': 'Small - 8x8 cm'},
                {'size': 'medium', 'width': Decimal('8.00'), 'height': Decimal('8.00'), 'label': 'Medium - 16x16 cm'},
                {'size': 'large', 'width': Decimal('11.00'), 'height': Decimal('11.00'), 'label': 'Large - 25x25 cm'},
            ],
            'emb_applique': [
                # Low Stitch
                {'size': 'small', 'width': Decimal('2.36'), 'height': Decimal('2.36'), 'label': 'Low Stitch - 1-12,000', 'stitch': 'low'},
                {'size': 'medium', 'width': Decimal('5.12'), 'height': Decimal('5.12'), 'label': 'Avg Stitch - 13-26,000', 'stitch': 'avg'},
                {'size': 'large', 'width': Decimal('10.24'), 'height': Decimal('10.24'), 'label': 'Lrg Stitch - 26-50,000', 'stitch': 'lrg'},
            ],
        }

        size_count = 0
        for addon_type, sizes in sizes_data.items():
            for idx, size_data in enumerate(sizes):
                size, created = AddonSizeDefinition.objects.get_or_create(
                    addon_type=addon_type,
                    size_code=size_data['size'],
                    stitch_complexity=size_data.get('stitch'),
                    defaults={
                        'max_width_inches': size_data['width'],
                        'max_height_inches': size_data['height'],
                        'display_label': size_data['label'],
                        'sort_order': idx,
                    }
                )
                if created:
                    size_count += 1
                    self.stdout.write(f"  ✓ Created: {size}")
                else:
                    self.stdout.write(f"  - Exists: {size}")

        self.stdout.write(self.style.SUCCESS(f'\nCreated {size_count} new size definitions'))

        # Summary
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS('SEEDING COMPLETE'))
        self.stdout.write('=' * 80)
        self.stdout.write(f'\nTotal Tiers: {AddonPricingTier.objects.count()}')
        self.stdout.write(f'Total Sizes: {AddonSizeDefinition.objects.count()}')
        self.stdout.write(f'Total Prices: {AddonPrice.objects.count()}')
        self.stdout.write('\n' + self.style.WARNING('⚠️  NEXT STEP: Add prices manually via /bespoke/category/addon/'))
        self.stdout.write(self.style.WARNING('   Prices must be entered based on the pricing table image'))
        self.stdout.write('')
