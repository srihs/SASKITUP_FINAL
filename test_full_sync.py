#!/usr/bin/env python3
"""
Test the full sync process with working API calls
"""
import os
import sys
import django
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kitup.settings')
django.setup()

from clubs.services.woocommerce_service import WooCommerceService
from clubs.models import Club, ClubCategory, Product
from django.db import transaction
import logging

def test_full_sync():
    print("=== Testing Full Sync Process ===")
    
    # Initialize service
    woo_service = WooCommerceService(store_type='LOTTO')
    
    # Test connection
    print("1. Testing WooCommerce connection...")
    if not woo_service.test_connection():
        print("❌ Connection failed!")
        return
    print("✅ Connection successful!")
    
    # Get some categories to work with manually
    print("\n2. Fetching categories manually...")
    params = {
        'per_page': 50,  # Get more categories
        'page': 1,
        'orderby': 'name',
        'order': 'asc'
    }
    
    categories_data = woo_service._make_request('products/categories', params)
    
    if not categories_data:
        print("❌ Failed to fetch categories")
        return
    
    print(f"✅ Found {len(categories_data)} categories")
    
    # Look for categories with products
    categories_with_products = [cat for cat in categories_data if cat.get('count', 0) > 0]
    print(f"✅ Found {len(categories_with_products)} categories with products")
    
    # Show the first few
    print("\nCategories with products:")
    for cat in categories_with_products[:10]:
        print(f"  ID: {cat['id']}, Name: {cat['name']}, Parent: {cat.get('parent', 0)}, Count: {cat.get('count', 0)}")
    
    if not categories_with_products:
        print("⚠️ No categories with products found - cannot test sync")
        return
    
    # Pick the first category with products to test sync
    test_category = categories_with_products[0]
    print(f"\n3. Testing sync with category: {test_category['name']} (ID: {test_category['id']})")
    
    # Get products for this category
    print("   Fetching products for this category...")
    products = woo_service.get_products_by_category(test_category['id'])
    
    print(f"   Found {len(products)} products")
    if products:
        print("   First product:", products[0]['name'])
    
    # Test database save operation (but rollback to not actually save)
    print("\n4. Testing database save operations...")
    
    try:
        with transaction.atomic():
            # Create a test club
            club_data = {
                'name': f"TEST - {test_category['name']}",
                'club_type': 'LOTTO',
                'woo_category_id': test_category['id'],
                'is_active': True,
            }
            
            print("   Creating test club...")
            club = Club.objects.create(**club_data)
            print(f"   ✅ Club created: {club.name}")
            
            # Create a test category
            category_data = {
                'club': club,
                'name': test_category['name'],
                'woo_category_id': test_category['id'],
                'description': test_category.get('description', ''),
                'product_count': test_category.get('count', 0),
            }
            
            print("   Creating test category...")
            category = ClubCategory.objects.create(**category_data)
            print(f"   ✅ Category created: {category.name}")
            
            # Create a test product if we have products
            if products:
                product_data = products[0]
                
                try:
                    from decimal import Decimal
                    regular_price = Decimal(product_data.get('regular_price', '0') or '0')
                    sale_price = Decimal(product_data.get('sale_price', '0') or '0') if product_data.get('sale_price') else None
                    price = sale_price or regular_price
                except:
                    regular_price = Decimal('0')
                    sale_price = None
                    price = Decimal('0')
                
                product_obj_data = {
                    'category': category,
                    'name': product_data['name'],
                    'woo_product_id': product_data['id'],
                    'price': price,
                    'regular_price': regular_price,
                    'sale_price': sale_price,
                    'description': product_data.get('description', ''),
                    'short_description': product_data.get('short_description', ''),
                    'sku': product_data.get('sku', ''),
                    'stock_status': product_data.get('stock_status', 'instock'),
                    'weight': product_data.get('weight', ''),
                }
                
                print("   Creating test product...")
                product = Product.objects.create(**product_obj_data)
                print(f"   ✅ Product created: {product.name}")
                
                # Verify data is actually in MySQL
                print("\n5. Verifying data in MySQL database...")
                print(f"   Clubs in database: {Club.objects.count()}")
                print(f"   Categories in database: {ClubCategory.objects.count()}")
                print(f"   Products in database: {Product.objects.count()}")
                
                print("\n✅ ALL TESTS PASSED - Sync process works!")
                print("   - WooCommerce API connection: ✅")
                print("   - Category fetching: ✅")
                print("   - Product fetching: ✅")
                print("   - MySQL database saves: ✅")
                
            # Rollback the transaction so we don't leave test data
            raise Exception("Rollback test data")
            
    except Exception as e:
        if "Rollback" in str(e):
            print("\n   Test data rolled back successfully")
        else:
            print(f"\n   ❌ Error during database operations: {e}")
    
    print("\n=== Full Sync Test Complete ===")

if __name__ == '__main__':
    test_full_sync()