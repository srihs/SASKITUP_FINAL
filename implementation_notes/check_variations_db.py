#!/usr/bin/env python3
"""Check if the product has variations in the database."""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'saskitup.settings')
django.setup()

from clubs.models_tus import TUSProduct

# Get the product by slug
product_slug = "albertians-bomber-jacket-powder-amber"
try:
    product = TUSProduct.objects.get(slug=product_slug)
    print(f"\nProduct found: {product.name}")
    print(f"Product ID: {product.id}")
    print(f"Product SKU: {product.sku}")
    print(f"Has variations property: {hasattr(product, 'has_variations')}")

    if hasattr(product, 'has_variations'):
        print(f"Has variations: {product.has_variations}")

    # Check for variations relationship
    if hasattr(product, 'variations'):
        variations = product.variations.all()
        print(f"\nTotal variations: {variations.count()}")

        if variations.exists():
            print("\nVariations:")
            for i, var in enumerate(variations, 1):
                print(f"  {i}. ID: {var.id}")
                print(f"     Type: {var.variation_type}")
                print(f"     Value: {var.variation_value}")
                print(f"     SKU: {var.sku}")
                print(f"     Stock: {var.stock_quantity}")
                print(f"     Active: {var.is_active}")
                print()
        else:
            print("\nNo variations found in database!")
    else:
        print("\nProduct does not have 'variations' relationship!")

except TUSProduct.DoesNotExist:
    print(f"Product with slug '{product_slug}' not found!")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
