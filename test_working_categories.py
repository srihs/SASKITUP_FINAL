#!/usr/bin/env python3
"""
Test the exact working request from earlier
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

def test_working_request():
    woo_service = WooCommerceService(store_type='LOTTO')
    
    # This exact request worked in the debug earlier
    params = {
        'per_page': 10,
        'page': 1,
        'orderby': 'name',
        'order': 'asc'
    }
    
    print("Making the exact working request from debug...")
    data = woo_service._make_request('products/categories', params)
    
    if data:
        print(f"SUCCESS! Found {len(data)} categories")
        for cat in data:
            print(f"  ID: {cat['id']}, Name: {cat['name']}, Parent: {cat.get('parent', 0)}, Count: {cat.get('count', 0)}")
            
        # Look for club categories specifically
        club_categories = [cat for cat in data if cat.get('parent') == 23 and cat.get('count', 0) > 0]
        print(f"\nClub categories with products (parent=23): {len(club_categories)}")
        for cat in club_categories:
            print(f"  CLUB: ID: {cat['id']}, Name: {cat['name']}, Count: {cat.get('count', 0)}")
    else:
        print("FAILED!")

if __name__ == '__main__':
    test_working_request()