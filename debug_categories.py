#!/usr/bin/env python3
"""
Debug categories endpoint specifically
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
import logging

# Configure detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')

def debug_categories():
    woo_service = WooCommerceService(store_type='LOTTO')
    
    # Test the corrected endpoint directly
    print("=== Testing products/categories endpoint ===")
    
    # Test with no parent filter first
    params = {
        'per_page': 10,
        'page': 1,
        'orderby': 'name',
        'order': 'asc'
    }
    
    print("Making request to products/categories...")
    data = woo_service._make_request('products/categories', params)
    
    if data:
        print(f"Success! Found {len(data)} categories")
        for cat in data:
            print(f"  ID: {cat['id']}, Name: {cat['name']}, Parent: {cat.get('parent', 0)}, Count: {cat.get('count', 0)}")
    else:
        print("Failed to get categories")
    
    # Now test with parent=23
    print(f"\n=== Testing with parent=23 ===")
    params['parent'] = 23
    
    data = woo_service._make_request('products/categories', params)
    
    if data:
        print(f"Success! Found {len(data)} categories with parent=23")
        for cat in data:
            print(f"  ID: {cat['id']}, Name: {cat['name']}, Parent: {cat.get('parent', 0)}, Count: {cat.get('count', 0)}")
    else:
        print("Failed to get categories with parent=23")
    
    # Test finding the right parent ID for clubs
    print(f"\n=== Finding Club Shop Categories ===")
    
    # Get all categories and look for club-related ones
    params = {'per_page': 100, 'page': 1}
    all_data = woo_service._make_request('products/categories', params)
    
    if all_data:
        print(f"Total categories found: {len(all_data)}")
        
        # Look for categories that might be club-related
        club_keywords = ['club', 'shop', 'team', 'sport']
        potential_clubs = []
        
        for cat in all_data:
            name_lower = cat['name'].lower()
            if any(keyword in name_lower for keyword in club_keywords):
                potential_clubs.append(cat)
                print(f"  Potential club category: ID: {cat['id']}, Name: {cat['name']}, Parent: {cat.get('parent', 0)}, Count: {cat.get('count', 0)}")
        
        # Look for categories with high product counts that might be clubs
        high_count_categories = [cat for cat in all_data if cat.get('count', 0) > 10]
        print(f"\nCategories with >10 products (potential club stores):")
        for cat in high_count_categories[:10]:  # Show top 10
            print(f"  ID: {cat['id']}, Name: {cat['name']}, Parent: {cat.get('parent', 0)}, Count: {cat.get('count', 0)}")
    
    print("Debug complete!")

if __name__ == '__main__':
    debug_categories()