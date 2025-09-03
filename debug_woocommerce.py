#!/usr/bin/env python3
"""
Debug script for WooCommerce API issues
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
import requests

# Configure detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def debug_woocommerce_api():
    """Debug WooCommerce API connectivity and endpoints"""
    
    print("=== WooCommerce API Debug Session ===")
    
    # Initialize service
    woo_service = WooCommerceService(store_type='LOTTO')
    
    print(f"\nAPI Configuration:")
    print(f"  Base URL: {woo_service.api_url}")
    print(f"  Store Type: {woo_service.store_type}")
    
    # Test different endpoints
    endpoints_to_test = [
        'system_status',
        'products?per_page=1',
        'categories?per_page=1',
        'categories?parent=23&per_page=1',
        'products/categories?per_page=1',
    ]
    
    print(f"\n=== Testing API Endpoints ===")
    
    for endpoint in endpoints_to_test:
        print(f"\nTesting endpoint: {endpoint}")
        url = f"{woo_service.api_url}{endpoint}"
        print(f"Full URL: {url}")
        
        try:
            response = woo_service.session.get(url, timeout=30)
            print(f"  Status Code: {response.status_code}")
            print(f"  Headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    print(f"  Response: List with {len(data)} items")
                    if data:
                        print(f"  First item keys: {list(data[0].keys()) if data[0] else 'Empty'}")
                else:
                    print(f"  Response: Dict with keys: {list(data.keys()) if data else 'Empty'}")
            else:
                print(f"  Error Response: {response.text[:200]}...")
                
        except Exception as e:
            print(f"  Exception: {str(e)}")
    
    # Test manual categories request with different parent IDs
    print(f"\n=== Testing Different Parent Category IDs ===")
    
    parent_ids_to_test = [0, 1, 23, None]  # 0 = root categories
    
    for parent_id in parent_ids_to_test:
        print(f"\nTesting parent_id: {parent_id}")
        try:
            categories = woo_service.get_categories(parent_id=parent_id, per_page=5)
            print(f"  Found {len(categories)} categories")
            
            if categories:
                for i, cat in enumerate(categories[:3]):  # Show first 3
                    print(f"    {i+1}. ID: {cat['id']}, Name: {cat['name']}, Parent: {cat.get('parent', 'N/A')}, Count: {cat.get('count', 'N/A')}")
                    
        except Exception as e:
            print(f"  Exception: {str(e)}")
    
    # Test getting all categories to understand structure
    print(f"\n=== Getting All Categories (first 10) ===")
    try:
        all_categories = woo_service.get_categories(per_page=10)
        print(f"Found {len(all_categories)} total categories")
        
        for cat in all_categories:
            print(f"  ID: {cat['id']}, Name: {cat['name']}, Parent: {cat.get('parent', 0)}, Count: {cat.get('count', 0)}")
            
    except Exception as e:
        print(f"Exception: {str(e)}")
    
    print(f"\n=== Debug Complete ===")

if __name__ == '__main__':
    debug_woocommerce_api()