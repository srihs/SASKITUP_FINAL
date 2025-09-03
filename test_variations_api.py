#!/usr/bin/env python
"""
Test script to examine WooCommerce API variation data structure
"""
import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kitup.settings')
sys.path.append('/Users/sas/Repos/SASKITUP')
django.setup()

from clubs.services.woocommerce_service import WooCommerceService
import json

def test_woo_variations():
    """Test WooCommerce variations API"""
    
    print("🔍 Testing WooCommerce Variations API")
    print("=" * 50)
    
    # Initialize service
    try:
        woo_service = WooCommerceService(store_type='LOTTO')
        print(f"✅ Connected to LOTTO WooCommerce API")
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return
    
    # Test connection
    if not woo_service.test_connection():
        print("❌ API connection test failed")
        return
    
    print("✅ API connection successful")
    print()
    
    # Get categories with products (limit to first few for testing)
    print("📂 Fetching categories with products...")
    categories = woo_service.get_categories_with_products(parent_id=23)
    
    if not categories:
        print("❌ No categories found")
        return
    
    print(f"✅ Found {len(categories)} categories")
    
    # Look for variable products in the first category
    category = categories[0]  # Test with first category
    print(f"\n🏷️  Testing category: {category['name']} (ID: {category['id']})")
    
    # Get products from this category
    products = woo_service.get_products_by_category(category['id'])
    
    if not products:
        print("❌ No products found in category")
        return
    
    print(f"✅ Found {len(products)} products")
    
    # Look for variable products
    variable_products = []
    for product in products:
        if woo_service.is_variable_product(product):
            variable_products.append(product)
    
    if not variable_products:
        print("ℹ️  No variable products found in this category")
        print("\n📝 Sample simple product structure:")
        if products:
            sample_product = products[0]
            print(f"   Name: {sample_product.get('name', 'N/A')}")
            print(f"   Type: {sample_product.get('type', 'N/A')}")
            print(f"   Price: {sample_product.get('price', 'N/A')}")
            print(f"   Attributes: {len(sample_product.get('attributes', []))}")
            if sample_product.get('attributes'):
                for attr in sample_product['attributes'][:3]:  # Show first 3 attributes
                    print(f"     - {attr.get('name', 'N/A')}: {attr.get('options', [])}")
        return
    
    print(f"🎯 Found {len(variable_products)} variable products!")
    
    # Test variations for the first variable product
    test_product = variable_products[0]
    print(f"\n🔍 Testing variations for: {test_product['name']}")
    print(f"   Product ID: {test_product['id']}")
    print(f"   Type: {test_product['type']}")
    print(f"   Price: {test_product.get('price', 'N/A')}")
    
    # Get variations
    variations = woo_service.get_product_variations(test_product['id'])
    
    if not variations:
        print("❌ No variations found")
        return
    
    print(f"✅ Found {len(variations)} variations")
    print()
    
    # Analyze variation structure
    print("📊 Variation Analysis:")
    print("-" * 30)
    
    for i, variation in enumerate(variations[:3]):  # Show first 3 variations
        print(f"\n🔸 Variation {i+1}:")
        print(f"   ID: {variation.get('id', 'N/A')}")
        print(f"   Price: {variation.get('price', 'N/A')}")
        print(f"   Regular Price: {variation.get('regular_price', 'N/A')}")
        print(f"   Sale Price: {variation.get('sale_price', 'N/A')}")
        print(f"   Stock Status: {variation.get('stock_status', 'N/A')}")
        print(f"   Stock Quantity: {variation.get('stock_quantity', 'N/A')}")
        print(f"   Manage Stock: {variation.get('manage_stock', 'N/A')}")
        print(f"   SKU: {variation.get('sku', 'N/A')}")
        print(f"   Weight: {variation.get('weight', 'N/A')}")
        
        # Show attributes
        attributes = variation.get('attributes', [])
        print(f"   Attributes ({len(attributes)}):")
        for attr in attributes:
            print(f"     - {attr.get('name', 'N/A')}: {attr.get('option', 'N/A')}")
        
        # Test our extraction method
        print(f"\n   📋 Extracted Data:")
        extracted = woo_service.extract_variation_data(variation, test_product)
        print(f"     Variation Type: {extracted['variation_type']}")
        print(f"     Variation Value: {extracted['variation_value']}")
        print(f"     Price Modifier: {extracted['price_modifier']}")
        print(f"     Stock Quantity: {extracted['stock_quantity']}")
        print(f"     SKU Suffix: {extracted['sku_suffix']}")
        print(f"     Is Active: {extracted['is_active']}")
        print(f"     Attributes: {extracted['attributes']}")
    
    # Show parent product attributes for comparison
    print(f"\n📋 Parent Product Attributes:")
    parent_attrs = test_product.get('attributes', [])
    print(f"   Total attributes: {len(parent_attrs)}")
    for attr in parent_attrs:
        print(f"     - {attr.get('name', 'N/A')}")
        print(f"       Options: {attr.get('options', [])}")
        print(f"       Variation: {attr.get('variation', False)}")
        print(f"       Visible: {attr.get('visible', False)}")
    
    print("\n" + "=" * 50)
    print("✅ Variation API test completed successfully!")

if __name__ == '__main__':
    test_woo_variations()