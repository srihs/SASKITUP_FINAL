"""
Shipping and Box Calculation Configuration Models
"""
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal


# New Zealand Regions for shipping rate area mapping
NZ_REGIONS = [
    ('Auckland', 'Auckland'),
    ('Waikato', 'Waikato'),
    ('Wellington', 'Wellington'),
    ('Northland', 'Northland'),
    ('Gisborne', 'Gisborne'),
    ('Tairāwhiti', 'Tairāwhiti'),
    ('Hawke\'s Bay', 'Hawke\'s Bay'),
    ('Taranaki', 'Taranaki'),
    ('Manawatū-Whanganui', 'Manawatū-Whanganui'),
    ('Tasman', 'Tasman'),
    ('Nelson', 'Nelson'),
    ('Marlborough', 'Marlborough'),
    ('Canterbury', 'Canterbury'),
    ('Otago', 'Otago'),
    ('Southland', 'Southland'),
    ('West Coast', 'West Coast'),
]


class ShippingSettings(models.Model):
    """
    Singleton model for shipping configuration and box calculation settings.

    This model stores:
    - Box capacity data (units per product type for 20kg standard carton)
    - Shipping rates by region
    - Additional delivery surcharges
    - Box weight limits

    Only one instance of this model should exist.
    """

    # Box Configuration
    box_weight_limit_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('20.00'),
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Maximum weight capacity per box in kilograms"
    )

    # Product Capacities (units per 20kg box)
    # Stored as JSON for flexibility
    product_capacities = models.JSONField(
        default=dict,
        help_text="Product type to quantity capacity mapping for standard 20kg box"
    )

    # Shipping Rates (by region)
    # Stored as JSON for flexibility
    shipping_rates = models.JSONField(
        default=dict,
        help_text="Shipping costs by region and weight"
    )

    # Additional Charges
    rd_delivery_surcharge = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('6.50'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Additional charge for Rural Delivery (RD) addresses"
    )

    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shipping_settings_updates',
        help_text="User who last updated these settings"
    )

    class Meta:
        verbose_name = "Shipping Settings"
        verbose_name_plural = "Shipping Settings"

    def __str__(self):
        return f"Shipping Settings (Updated: {self.updated_at.strftime('%Y-%m-%d %H:%M')})"

    def save(self, *args, **kwargs):
        """Enforce singleton pattern - only one instance allowed"""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        """Get or create the singleton settings instance"""
        obj, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'product_capacities': cls.get_default_product_capacities(),
                'shipping_rates': cls.get_default_shipping_rates(),
            }
        )
        return obj

    @staticmethod
    def get_default_product_capacities():
        """
        Default box capacity data based on 20kg standard carton.
        Returns units that can fit per box for each product type.
        """
        return {
            'sideline_jackets': 8,
            'jackets': 25,
            'hoodies': 30,
            'pants': 35,
            'jerseys_softball_tops_pants': 60,
            'polos_tees_singlets_dresses': 70,
            'netball_touch_tag_league_skirts_shorts': 80,
            'tights_socks_caps_bucket_hats_min': 80,
            'tights_socks_caps_bucket_hats_max': 100,
        }

    @staticmethod
    def get_default_shipping_rates():
        """
        Default shipping rates (updated rates, incl GST).
        Returns shipping costs by region.
        """
        return {
            'auckland': {
                'cost': '7.15',
                'description': 'Auckland delivery',
                'regions': ['Auckland']
            },
            'auckland_rural': {
                'cost': '13.75',
                'description': 'Auckland Rural delivery',
                'regions': ['Waikato']
            },
            'north_island': {
                'cost': '14.30',
                'description': 'North Island delivery',
                'regions': ['Wellington', 'Northland', 'Gisborne']
            },
            'north_island_rural': {
                'cost': '16.50',
                'description': 'North Island Rural delivery',
                'regions': ['Tairāwhiti', 'Hawke\'s Bay', 'Taranaki', 'Manawatū-Whanganui']
            },
            'south_island': {
                'cost': '16.50',
                'description': 'South Island delivery',
                'regions': ['Tasman', 'Nelson', 'Marlborough', 'Canterbury']
            },
            'south_island_rural': {
                'cost': '21.90',
                'description': 'South Island Rural delivery',
                'regions': ['Otago', 'Southland', 'West Coast']
            },
        }

    def get_product_capacity(self, product_type_key):
        """
        Get the box capacity for a specific product type.

        Args:
            product_type_key: Key from product_capacities dict

        Returns:
            int: Number of units that fit in one box, or None if not found
        """
        return self.product_capacities.get(product_type_key)

    def get_shipping_rate(self, region_key):
        """
        Get shipping rate information for a specific region.

        Args:
            region_key: Key from shipping_rates dict (e.g., 'auckland', 'north_island')

        Returns:
            dict: Shipping rate details, or None if not found
        """
        return self.shipping_rates.get(region_key)

    def get_rate_area_for_region(self, region_name):
        """
        Get the rate area (shipping rate key) for a specific NZ region name.

        Args:
            region_name: Name of the NZ region (e.g., 'Auckland', 'Wellington')

        Returns:
            str: Rate area key (e.g., 'auckland', 'north_island'), or None if not found
        """
        for rate_key, rate_info in self.shipping_rates.items():
            regions = rate_info.get('regions', [])
            if region_name in regions:
                return rate_key
        return None

    def get_rate_for_region(self, region_name):
        """
        Get the shipping rate cost for a specific NZ region name.

        Args:
            region_name: Name of the NZ region (e.g., 'Auckland', 'Wellington')

        Returns:
            str: Rate cost as string, or None if not found
        """
        rate_area = self.get_rate_area_for_region(region_name)
        if rate_area:
            rate_info = self.get_shipping_rate(rate_area)
            return rate_info.get('cost') if rate_info else None
        return None

    def calculate_boxes_needed(self, product_type_key, quantity):
        """
        Calculate how many boxes are needed for a given quantity of products.

        Args:
            product_type_key: Key from product_capacities dict
            quantity: Number of units to ship

        Returns:
            int: Number of boxes needed, or None if product type not found
        """
        capacity = self.get_product_capacity(product_type_key)
        if capacity is None or capacity == 0:
            return None

        import math
        return math.ceil(quantity / capacity)

    def get_product_capacities_display(self):
        """
        Get product capacities formatted for display in UI.

        Returns:
            list: List of dicts with product name and capacity
        """
        capacity_labels = {
            'sideline_jackets': 'Sideline Jackets',
            'jackets': 'Jackets',
            'hoodies': 'Hoodies',
            'pants': 'Pants',
            'jerseys_softball_tops_pants': 'Jerseys / Softball Tops / Pants',
            'polos_tees_singlets_dresses': 'Polos / Tees / Singlets / Dresses',
            'netball_touch_tag_league_skirts_shorts': 'Netball / Touch / Tag / League Skirts / Shorts',
            'tights_socks_caps_bucket_hats_min': 'Tights / Socks / Caps / Bucket Hats (Min)',
            'tights_socks_caps_bucket_hats_max': 'Tights / Socks / Caps / Bucket Hats (Max)',
        }

        result = []
        for key, capacity in self.product_capacities.items():
            result.append({
                'key': key,
                'label': capacity_labels.get(key, key.replace('_', ' ').title()),
                'capacity': capacity
            })

        return result

    def get_shipping_rates_display(self):
        """
        Get shipping rates formatted for display in UI.

        Returns:
            list: List of dicts with region info and rates
        """
        region_labels = {
            'auckland': 'Auckland',
            'auckland_rural': 'Auckland Rural',
            'north_island': 'North Island',
            'north_island_rural': 'North Island Rural',
            'south_island': 'South Island',
            'south_island_rural': 'South Island Rural',
        }

        result = []
        for key, rate_info in self.shipping_rates.items():
            result.append({
                'key': key,
                'label': region_labels.get(key, key.replace('_', ' ').title()),
                'cost': rate_info.get('cost'),
                'description': rate_info.get('description', ''),
                'regions': rate_info.get('regions', [])
            })

        return result
