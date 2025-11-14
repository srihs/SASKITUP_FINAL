#!/usr/bin/env python
"""
Fix Bespoke Product and Variation Prices

This script sets the correct selling price for addon products and variations:
- Base Garments: price = margin_75_price (75% margin)
- Addons: price = cost_price (pass-through pricing)

Usage:
    python fix_bespoke_prices.py
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kitup.settings')
django.setup()

from decimal import Decimal
from django.db import transaction
from bespoke.models import BespokeProduct, BespokeProductVariation, BespokeCategory


def fix_bespoke_prices():
    """Fix prices for all bespoke products and variations."""

    print("="*80)
    print("BESPOKE PRICE FIX SCRIPT")
    print("="*80)

    # Get addon category
    addon_category = BespokeCategory.objects.filter(slug='addon').first()
    if not addon_category:
        print("ERROR: Addon category not found!")
        return

    # Get base garment category
    base_garment_category = BespokeCategory.objects.filter(slug='base-garment').first()
    if not base_garment_category:
        print("WARNING: Base garment category not found!")

    print(f"\nAddon Category: {addon_category.name}")
    if base_garment_category:
        print(f"Base Garment Category: {base_garment_category.name}")

    # Process addon products
    print("\n" + "-"*80)
    print("PROCESSING ADDON PRODUCTS")
    print("-"*80)

    addon_products = BespokeProduct.objects.filter(
        category_assignments__category=addon_category
    ).distinct()

    print(f"Found {addon_products.count()} addon products")

    updated_products = 0
    updated_variations = 0

    with transaction.atomic():
        for product in addon_products:
            # Check if product needs update
            if product.cost_price and product.price != product.cost_price:
                old_price = product.price
                product.price = product.cost_price
                product.save(update_fields=['price'])
                print(f"✓ Updated {product.name}: ${old_price or 'NULL'} → ${product.price}")
                updated_products += 1

            # Process variations
            if product.product_type == 'variable':
                for variation in product.variations.all():
                    if variation.cost_price and variation.price != variation.cost_price:
                        old_price = variation.price
                        variation.price = variation.cost_price
                        variation.save(update_fields=['price'])
                        print(f"  ✓ Updated variation {variation.option1_value or variation.sku}: ${old_price or 'NULL'} → ${variation.price}")
                        updated_variations += 1

    # Process base garment products (if category exists)
    if base_garment_category:
        print("\n" + "-"*80)
        print("PROCESSING BASE GARMENT PRODUCTS")
        print("-"*80)

        base_garment_products = BespokeProduct.objects.filter(
            category_assignments__category=base_garment_category
        ).distinct()

        print(f"Found {base_garment_products.count()} base garment products")

        with transaction.atomic():
            for product in base_garment_products:
                # Check if product needs update
                if product.margin_75_price and product.price != product.margin_75_price:
                    old_price = product.price
                    product.price = product.margin_75_price
                    product.save(update_fields=['price'])
                    print(f"✓ Updated {product.name}: ${old_price or 'NULL'} → ${product.price}")
                    updated_products += 1

                # Process variations
                if product.product_type == 'variable':
                    for variation in product.variations.all():
                        if variation.margin_75_price and variation.price != variation.margin_75_price:
                            old_price = variation.price
                            variation.price = variation.margin_75_price
                            variation.save(update_fields=['price'])
                            print(f"  ✓ Updated variation {variation.option1_value or variation.sku}: ${old_price or 'NULL'} → ${variation.price}")
                            updated_variations += 1

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Updated products: {updated_products}")
    print(f"Updated variations: {updated_variations}")
    print(f"Total updates: {updated_products + updated_variations}")
    print("\n✓ Price fix completed successfully!")


if __name__ == '__main__':
    fix_bespoke_prices()
