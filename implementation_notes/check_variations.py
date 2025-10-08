#!/usr/bin/env python
"""Check product variations for debugging"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kitup.settings')
django.setup()

from clubs.models_tus import TUSProduct, TUSProductVariation

# Find the product by slug
product = TUSProduct.objects.filter(slug='1-2-elastic-grey-p-c-short').first()

if product:
    print(f'Product found: {product.name}')
    print(f'Product ID: {product.id}')
    print(f'Product type: {product.type}')
    print(f'Has variations: {product.has_variations}')

    # Get variations
    variations = product.variations.all()
    print(f'\nTotal variations: {variations.count()}')

    # Show first 10 variations
    for i, var in enumerate(variations[:10], 1):
        print(f'\n--- Variation {i} ---')
        print(f'ID: {var.id}')
        print(f'Type: {var.variation_type}')
        print(f'Value: {var.variation_value}')
        print(f'Price: {var.price}')
        print(f'Stock: {var.stock_quantity}')
        print(f'SKU: {var.sku}')
        print(f'Active: {var.is_active}')
        print(f'Attributes: {var.attributes}')
else:
    print('Product not found!')
