from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
from bespoke.models import AddonPricingTier, AddonSizeDefinition, AddonPrice


class Command(BaseCommand):
    help = 'Populate addon pricing data from the pricing table image'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS('POPULATING ADDON PRICES'))
        self.stdout.write(self.style.SUCCESS('=' * 80))

        today = timezone.now().date()

        # First, create size definitions with color ranges for Heat Transfer and Screen Print
        self.stdout.write('\n1. Creating size definitions with color ranges...')
        self._create_color_based_sizes()

        # Then populate prices
        self.stdout.write('\n2. Populating Heat Transfer prices...')
        self._populate_heat_transfer_prices(today)

        self.stdout.write('\n3. Populating Screen Print prices...')
        self._populate_screen_print_prices(today)

        self.stdout.write('\n4. Populating EMB/Applique prices...')
        self._populate_emb_applique_prices(today)

        # Summary
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS('POPULATION COMPLETE'))
        self.stdout.write('=' * 80)
        self.stdout.write(f'\nTotal Active Prices: {AddonPrice.objects.filter(is_active=True).count()}')
        self.stdout.write(f'Total Size Definitions: {AddonSizeDefinition.objects.count()}')
        self.stdout.write('')

    def _create_color_based_sizes(self):
        """Create size definitions with color ranges for Heat Transfer and Screen Print"""

        sizes_data = [
            ('small', Decimal('5.00'), Decimal('5.00'), 'Small - 8x8 cm'),
            ('medium', Decimal('8.00'), Decimal('8.00'), 'Medium - 16x16 cm'),
            ('large', Decimal('11.00'), Decimal('11.00'), 'Large - 25x25 cm'),
        ]

        created_count = 0

        # Heat Transfer - uses 1-2, 3-4, 5-6
        color_ranges_ht = [
            ('1-2', '1-2 colors'),
            ('3-4', '3-4 colors'),
            ('5-6', '5-6 colors'),
        ]

        for size_code, width, height, base_label in sizes_data:
            for color_code, color_label in color_ranges_ht:
                display_label = f"{base_label} ({color_label})"

                size, created = AddonSizeDefinition.objects.get_or_create(
                    addon_type='heat_transfer',
                    size_code=size_code,
                    display_label=display_label,
                    defaults={
                        'max_width_inches': width,
                        'max_height_inches': height,
                        'sort_order': self._get_sort_order(size_code, color_code),
                    }
                )

                if created:
                    created_count += 1
                    self.stdout.write(f"  ✓ Created: heat_transfer - {display_label}")
                else:
                    self.stdout.write(f"  - Exists: heat_transfer - {display_label}")

        # Screen Print - uses 1-2, 3-4, 5-7 (note the difference!)
        color_ranges_sp = [
            ('1-2', '1-2 colors'),
            ('3-4', '3-4 colors'),
            ('5-7', '5-7 colors'),
        ]

        for size_code, width, height, base_label in sizes_data:
            for color_code, color_label in color_ranges_sp:
                display_label = f"{base_label} ({color_label})"

                size, created = AddonSizeDefinition.objects.get_or_create(
                    addon_type='screen_print',
                    size_code=size_code,
                    display_label=display_label,
                    defaults={
                        'max_width_inches': width,
                        'max_height_inches': height,
                        'sort_order': self._get_sort_order(size_code, color_code),
                    }
                )

                if created:
                    created_count += 1
                    self.stdout.write(f"  ✓ Created: screen_print - {display_label}")
                else:
                    self.stdout.write(f"  - Exists: screen_print - {display_label}")

        self.stdout.write(self.style.SUCCESS(f'\nCreated {created_count} new size definitions'))

    def _get_sort_order(self, size_code, color_code):
        """Generate sort order based on size and color"""
        size_order = {'small': 0, 'medium': 3, 'large': 6}
        color_order = {'1-2': 0, '3-4': 1, '5-6': 2, '5-7': 2}
        return size_order.get(size_code, 0) + color_order.get(color_code, 0)

    def _populate_heat_transfer_prices(self, today):
        """Populate Heat Transfer prices"""
        # Pricing data from the image
        pricing_data = {
            'small': {
                '1-2': {'1-9': 3.44, '10-25': 2.75, '26-50': 2.48, '51-199': 1.93, '200+': 1.65},
                '3-4': {'1-9': 6.25, '10-25': 5.00, '26-50': 4.50, '51-199': 3.50, '200+': 3.00},
                '5-6': {'1-9': 8.13, '10-25': 6.50, '26-50': 5.85, '51-199': 4.55, '200+': 3.90},
            },
            'medium': {
                '1-2': {'1-9': 4.27, '10-25': 3.58, '26-50': 3.40, '51-199': 2.50, '200+': 2.15},
                '3-4': {'1-9': 8.13, '10-25': 6.50, '26-50': 5.85, '51-199': 4.55, '200+': 3.90},
                '5-6': {'1-9': 10.56, '10-25': 8.45, '26-50': 7.61, '51-199': 5.92, '200+': 5.07},
            },
            'large': {
                '1-2': {'1-9': 5.50, '10-25': 4.40, '26-50': 4.18, '51-199': 3.08, '200+': 2.64},
                '3-4': {'1-9': 10.00, '10-25': 8.00, '26-50': 7.20, '51-199': 5.60, '200+': 4.80},
                '5-6': {'1-9': 13.00, '10-25': 10.40, '26-50': 9.36, '51-199': 7.28, '200+': 6.24},
            },
        }

        self._populate_color_based_prices('heat_transfer', pricing_data, today)

    def _populate_screen_print_prices(self, today):
        """Populate Screen Print prices (note: uses 5-7 instead of 5-6)"""
        # Same pricing as Heat Transfer, but color range is 5-7 instead of 5-6
        pricing_data = {
            'small': {
                '1-2': {'1-9': 3.44, '10-25': 2.75, '26-50': 2.48, '51-199': 1.93, '200+': 1.65},
                '3-4': {'1-9': 6.25, '10-25': 5.00, '26-50': 4.50, '51-199': 3.50, '200+': 3.00},
                '5-7': {'1-9': 8.13, '10-25': 6.50, '26-50': 5.85, '51-199': 4.55, '200+': 3.90},
            },
            'medium': {
                '1-2': {'1-9': 4.27, '10-25': 3.58, '26-50': 3.40, '51-199': 2.50, '200+': 2.15},
                '3-4': {'1-9': 8.13, '10-25': 6.50, '26-50': 5.85, '51-199': 4.55, '200+': 3.90},
                '5-7': {'1-9': 10.56, '10-25': 8.45, '26-50': 7.61, '51-199': 5.92, '200+': 5.07},
            },
            'large': {
                '1-2': {'1-9': 5.50, '10-25': 4.40, '26-50': 4.18, '51-199': 3.08, '200+': 2.64},
                '3-4': {'1-9': 10.00, '10-25': 8.00, '26-50': 7.20, '51-199': 5.60, '200+': 4.80},
                '5-7': {'1-9': 13.00, '10-25': 10.40, '26-50': 9.36, '51-199': 7.28, '200+': 6.24},
            },
        }

        self._populate_color_based_prices('screen_print', pricing_data, today)

    def _populate_color_based_prices(self, addon_type, pricing_data, today):
        """Helper to populate prices for color-based addon types"""
        created_count = 0
        updated_count = 0

        for size_code, color_prices in pricing_data.items():
            for color_range, tier_prices in color_prices.items():
                # Get the size definition
                color_label = {
                    '1-2': '1-2 colors',
                    '3-4': '3-4 colors',
                    '5-6': '5-6 colors',
                    '5-7': '5-7 colors'
                }[color_range]
                size_label_part = {
                    'small': 'Small - 8x8 cm',
                    'medium': 'Medium - 16x16 cm',
                    'large': 'Large - 25x25 cm'
                }[size_code]
                display_label = f"{size_label_part} ({color_label})"

                try:
                    size_def = AddonSizeDefinition.objects.get(
                        addon_type=addon_type,
                        size_code=size_code,
                        display_label=display_label
                    )
                except AddonSizeDefinition.DoesNotExist:
                    self.stdout.write(self.style.WARNING(
                        f"  ⚠️  Size definition not found: {addon_type} - {display_label}"
                    ))
                    continue

                for tier_label, price in tier_prices.items():
                    # Get the tier
                    try:
                        tier = AddonPricingTier.objects.get(
                            addon_type=addon_type,
                            display_label=tier_label
                        )
                    except AddonPricingTier.DoesNotExist:
                        self.stdout.write(self.style.WARNING(
                            f"  ⚠️  Tier not found: {addon_type} - {tier_label}"
                        ))
                        continue

                    # Create or update the price
                    price_obj, created = AddonPrice.objects.get_or_create(
                        tier=tier,
                        size_definition=size_def,
                        effective_from=today,
                        defaults={
                            'price_per_unit': Decimal(str(price)),
                            'is_active': True,
                            'created_by': None,
                            'notes': f'Populated from pricing table - {today}'
                        }
                    )

                    if created:
                        created_count += 1
                        self.stdout.write(
                            f"  ✓ Created: {tier_label} × {display_label} = R{price}"
                        )
                    else:
                        # Update if price changed
                        if price_obj.price_per_unit != Decimal(str(price)):
                            price_obj.price_per_unit = Decimal(str(price))
                            price_obj.save()
                            updated_count += 1
                            self.stdout.write(
                                f"  ↻ Updated: {tier_label} × {display_label} = R{price}"
                            )

        self.stdout.write(self.style.SUCCESS(
            f'\nCreated {created_count} prices, Updated {updated_count} prices for {addon_type}'
        ))

    def _populate_emb_applique_prices(self, today):
        """Populate EMB/Applique prices"""
        # Pricing data from the image
        # Note: Some entries have "N/A" which we skip
        pricing_data = {
            'emb': {
                'low': {
                    # 1-9 tier: N/A (skip)
                    '10-25': 5.00,
                    '26-50': 5.63,
                    '51-199': 4.50,
                    '200+': 5.06,
                },
                'avg': {
                    '1-9': 8.13,
                    '10-25': 6.50,
                    '26-50': 7.31,
                    '51-199': 5.85,
                    '200+': 6.58,
                },
                'lrg': {
                    '1-9': 15.00,
                    '10-25': 12.00,
                    '26-50': 13.50,
                    '51-199': 10.80,
                    '200+': 12.15,
                },
            },
            'applique': {
                'low': {
                    # All N/A (skip)
                },
                'avg': {
                    '1-9': 10.00,
                    '10-25': 10.00,
                    '26-50': 10.00,
                    '51-199': 10.00,
                    '200+': 10.00,
                },
                'lrg': {
                    '1-9': 15.00,
                    '10-25': 15.00,
                    '26-50': 15.00,
                    '51-199': 15.00,
                    '200+': 15.00,
                },
            },
        }

        created_count = 0
        updated_count = 0

        # Map stitch complexity to size code
        stitch_to_size = {'low': 'small', 'avg': 'medium', 'lrg': 'large'}

        for product_type, stitch_prices in pricing_data.items():
            for stitch_complexity, tier_prices in stitch_prices.items():
                if not tier_prices:  # Skip empty dicts (N/A entries)
                    continue

                size_code = stitch_to_size[stitch_complexity]

                # Get the size definition
                try:
                    size_def = AddonSizeDefinition.objects.get(
                        addon_type='emb_applique',
                        size_code=size_code,
                        stitch_complexity=stitch_complexity
                    )
                except AddonSizeDefinition.DoesNotExist:
                    self.stdout.write(self.style.WARNING(
                        f"  ⚠️  Size definition not found: emb_applique - {size_code} - {stitch_complexity}"
                    ))
                    continue

                for tier_label, price in tier_prices.items():
                    # Get the tier
                    try:
                        tier = AddonPricingTier.objects.get(
                            addon_type='emb_applique',
                            display_label=tier_label
                        )
                    except AddonPricingTier.DoesNotExist:
                        self.stdout.write(self.style.WARNING(
                            f"  ⚠️  Tier not found: emb_applique - {tier_label}"
                        ))
                        continue

                    # Create or update the price
                    price_obj, created = AddonPrice.objects.get_or_create(
                        tier=tier,
                        size_definition=size_def,
                        effective_from=today,
                        defaults={
                            'price_per_unit': Decimal(str(price)),
                            'is_active': True,
                            'created_by': None,
                            'notes': f'Populated from pricing table - {product_type.upper()} - {today}'
                        }
                    )

                    if created:
                        created_count += 1
                        self.stdout.write(
                            f"  ✓ Created: {tier_label} × {size_def.display_label} ({product_type.upper()}) = R{price}"
                        )
                    else:
                        # Update if price changed
                        if price_obj.price_per_unit != Decimal(str(price)):
                            old_price = price_obj.price_per_unit
                            price_obj.price_per_unit = Decimal(str(price))
                            price_obj.notes = f'Updated from pricing table - {product_type.upper()} - {today}'
                            price_obj.save()
                            updated_count += 1
                            self.stdout.write(
                                f"  ↻ Updated: {tier_label} × {size_def.display_label} ({product_type.upper()}) = R{old_price} → R{price}"
                            )

        self.stdout.write(self.style.SUCCESS(
            f'\nCreated {created_count} prices, Updated {updated_count} prices for emb_applique'
        ))
