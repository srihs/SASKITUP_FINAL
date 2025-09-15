#!/usr/bin/env python3
"""
Test script for the Product Variation API endpoints.

This script demonstrates how to use the dynamic product variation API
that provides stock-based availability checking.
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000/clubs"

def test_api_endpoint(url, method="GET", data=None, description=""):
    """Test an API endpoint and return the response."""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print(f"URL: {url}")
    print(f"Method: {method}")
    
    if data:
        print(f"Data: {json.dumps(data, indent=2)}")
    
    try:
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            response = requests.post(url, json=data, headers={'Content-Type': 'application/json'})
        
        print(f"Status Code: {response.status_code}")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)}")
            return result
        else:
            print(f"Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None

def main():
    # Test product ID (use the product we tested earlier)
    product_id = 58
    
    print("Dynamic Product Variation API Test Suite")
    print("=" * 60)
    print(f"Testing with Product ID: {product_id}")
    
    # Test 1: Get all variations for a product
    test_api_endpoint(
        f"{BASE_URL}/api/products/{product_id}/variations/",
        description="Get all product variations"
    )
    
    # Test 2: Check availability with no selection
    test_api_endpoint(
        f"{BASE_URL}/api/products/{product_id}/check-availability/",
        method="POST",
        data={},
        description="Check availability with empty selection"
    )
    
    # Test 3: Check availability with size selection
    test_api_endpoint(
        f"{BASE_URL}/api/products/{product_id}/check-availability/",
        method="POST",
        data={"size": "L"},
        description="Check availability with size L selected"
    )
    
    # Test 4: Get available size options
    test_api_endpoint(
        f"{BASE_URL}/api/products/{product_id}/options/size/",
        description="Get available size options"
    )
    
    # Test 5: Get variation details for specific combination
    test_api_endpoint(
        f"{BASE_URL}/api/products/{product_id}/variation-details/",
        method="POST",
        data={"size": "M"},
        description="Get variation details for size M"
    )
    
    # Test 6: Test error handling - invalid product ID
    test_api_endpoint(
        f"{BASE_URL}/api/products/999999/variations/",
        description="Test error handling - product not found"
    )
    
    # Test 7: Test error handling - invalid attribute type
    test_api_endpoint(
        f"{BASE_URL}/api/products/{product_id}/options/invalid_type/",
        description="Test error handling - invalid attribute type"
    )
    
    # Test 8: Test with query parameters for available options
    test_api_endpoint(
        f"{BASE_URL}/api/products/{product_id}/options/color/?size=L",
        description="Get color options with size L already selected"
    )
    
    print(f"\n{'='*60}")
    print("API Test Suite Complete!")
    print("\nThe Dynamic Product Variation API provides the following functionality:")
    print("1. Real-time stock checking for variation combinations")
    print("2. Dynamic filtering of available options based on current selection")
    print("3. Comprehensive variation data for frontend JavaScript")
    print("4. Proper error handling and validation")
    print("5. Support for both LOTTO and generic product models")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        sys.exit(1)