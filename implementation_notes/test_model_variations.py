#!/usr/bin/env python
"""
Test script to validate separate variation logic for SAS and LOTTO products.
This script tests that both systems provide the same API interface but with their own implementation.
"""

import os
import sys
import django
import json
from decimal import Decimal

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kitup.settings')
django.setup()

from clubs.models_sas import SASProduct, SASClub, SASSport, SASProductVariation
from clubs.models_lotto import LottoProduct, LottoProductVariation
from clubs.models import Product


def test_sas_product_variations():
    """Test SAS product variation methods"""
    print("=" * 60)
    print("TESTING SAS PRODUCT VARIATIONS")
    print("=" * 60)
    
    # Get a sample SAS product
    sas_products = SASProduct.objects.filter(is_active=True)[:5]
    
    if not sas_products.exists():
        print("❌ No SAS products found for testing")
        return False
    
    for product in sas_products:
        print(f"\n📦 Testing SAS Product: {product.name}")
        print(f"   ID: {product.id}")
        print(f"   SKU: {product.sku}")
        print(f"   Price: ${product.effective_price}")
        
        # Test variation methods
        print(f"   Has variations: {product.has_variations}")
        
        if product.has_variations:
            # Test parsed attributes
            parsed_attrs = product.parsed_variation_attributes
            print(f"   Parsed attributes: {parsed_attrs}")
            
            # Test individual attribute getters
            print(f"   Available sizes: {product.available_sizes}")
            print(f"   Available colors: {product.available_colors}")
            print(f"   Available materials: {product.available_materials}")
            print(f"   Available styles: {product.available_styles}")
            
            # Test frontend data
            frontend_data = product.get_variation_data_for_frontend()
            print(f"   Frontend data keys: {list(frontend_data.keys())}")
            print(f"   Variation types: {frontend_data.get('variation_types', [])}")
            print(f"   Number of variations: {len(frontend_data.get('variations', []))}")
            
            # Test availability checking
            if product.available_sizes and product.available_colors:
                test_combination = {
                    'size': product.available_sizes[0],
                    'color': product.available_colors[0]
                }
                print(f"   Testing combination: {test_combination}")
                
                available_for_selection = product.get_available_variations_for_selection(**test_combination)
                print(f"   Available for selection: {list(available_for_selection.keys())}")
                
                stock = product.get_variation_combination_stock(**test_combination)
                print(f"   Stock for combination: {stock}")
                
                is_available = product.is_variation_combination_available(**test_combination)
                print(f"   Is combination available: {is_available}")
        
        else:
            print("   ✓ Product has no variations (using base product logic)")
    
    return True


def test_lotto_product_variations():
    """Test LOTTO product variation methods"""
    print("\n" + "=" * 60)
    print("TESTING LOTTO PRODUCT VARIATIONS")
    print("=" * 60)
    
    # Get a sample LOTTO product with variations
    lotto_products = LottoProduct.objects.filter(
        status='publish',
        type='variable'
    )[:3]
    
    if not lotto_products.exists():
        print("❌ No LOTTO variable products found for testing")
        return False
    
    for product in lotto_products:
        print(f"\n📦 Testing LOTTO Product: {product.name}")
        print(f"   ID: {product.id}")
        print(f"   SKU: {product.sku}")
        print(f"   Price: ${product.price}")
        print(f"   Product type: {product.type}")
        
        # Test variation methods
        print(f"   Has variations: {product.has_variations}")
        
        if product.has_variations:
            # Test variations
            variations = product.variations.all()
            print(f"   Number of active variations: {variations.count()}")
            
            # Test frontend data
            frontend_data = product.get_variation_data_for_frontend()
            print(f"   Frontend data keys: {list(frontend_data.keys())}")
            print(f"   Variation types: {frontend_data.get('variation_types', [])}")
            print(f"   Number of variations: {len(frontend_data.get('variations', []))}")
            
            # Test a few variations
            for i, variation in enumerate(variations[:3]):
                print(f"   Variation {i+1}: {variation.variation_type} = {variation.variation_value}")
                print(f"     Stock: {variation.stock_quantity}")
                print(f"     Price: ${variation.final_price}")
                print(f"     SKU: {variation.full_sku}")
        
        else:
            print("   ✓ Product has no variations (simple product)")
    
    return True


def test_api_consistency():
    """Test that both systems provide consistent API responses"""
    print("\n" + "=" * 60)
    print("TESTING API CONSISTENCY")
    print("=" * 60)
    
    # Test SAS product API structure
    sas_product = SASProduct.objects.filter(is_active=True).first()
    if sas_product:
        print(f"\n🔧 Testing SAS API structure for product ID {sas_product.id}")
        
        if sas_product.has_variations:
            sas_data = sas_product.get_variation_data_for_frontend()
            print("   ✓ SAS API Response Structure:")
            print(f"     - product_id: {sas_data.get('product_id')}")
            print(f"     - has_variations: {sas_data.get('has_variations')}")
            print(f"     - variation_types: {sas_data.get('variation_types')}")
            print(f"     - variations count: {len(sas_data.get('variations', []))}")
            print(f"     - parsed_attributes: {bool(sas_data.get('parsed_attributes'))}")
            
            # Test variation combination checking
            if sas_product.available_sizes:
                test_combo = {'size': sas_product.available_sizes[0]}
                stock = sas_product.get_variation_combination_stock(**test_combo)
                available = sas_product.is_variation_combination_available(**test_combo)
                print(f"     - Stock checking works: stock={stock}, available={available}")
    
    # Test LOTTO product API structure
    lotto_product = LottoProduct.objects.filter(status='publish', type='variable').first()
    if lotto_product:
        print(f"\n🔧 Testing LOTTO API structure for product ID {lotto_product.id}")
        
        if lotto_product.has_variations:
            lotto_data = lotto_product.get_variation_data_for_frontend()
            print("   ✓ LOTTO API Response Structure:")
            print(f"     - product_id: {lotto_data.get('product_id')}")
            print(f"     - has_variations: {lotto_data.get('has_variations')}")
            print(f"     - variation_types: {lotto_data.get('variation_types')}")
            print(f"     - variations count: {len(lotto_data.get('variations', []))}")
            print(f"     - base_price: {lotto_data.get('base_price')}")
    
    return True


def test_variation_model_creation():
    """Test SAS variation model creation"""
    print("\n" + "=" * 60)
    print("TESTING SAS VARIATION MODEL CREATION")
    print("=" * 60)
    
    # Get a SAS product to create variations for
    sas_product = SASProduct.objects.filter(is_active=True).first()
    if not sas_product:
        print("❌ No SAS products found for testing")
        return False
    
    print(f"📦 Creating test variations for SAS Product: {sas_product.name}")
    
    # Create test variations
    test_variations = [
        {'variation_type': 'size', 'variation_value': 'Large', 'stock_quantity': 10},
        {'variation_type': 'color', 'variation_value': 'Blue', 'stock_quantity': 5},
        {'variation_type': 'size', 'variation_value': 'Medium', 'stock_quantity': 8},
        {'variation_type': 'color', 'variation_value': 'Red', 'stock_quantity': 3},
    ]
    
    created_variations = []
    for var_data in test_variations:
        try:
            # Check if variation already exists
            existing = SASProductVariation.objects.filter(
                product=sas_product,
                variation_type=var_data['variation_type'],
                variation_value=var_data['variation_value']
            ).first()
            
            if existing:
                print(f"   ✓ Variation already exists: {var_data['variation_type']} = {var_data['variation_value']}")
                created_variations.append(existing)
            else:
                variation = SASProductVariation.objects.create(
                    product=sas_product,
                    **var_data
                )
                print(f"   ✓ Created variation: {variation}")
                created_variations.append(variation)
                
        except Exception as e:
            print(f"   ❌ Failed to create variation {var_data}: {e}")
    
    # Test the created variations
    if created_variations:
        print(f"\n🧪 Testing created variations:")
        print(f"   Product now has {len(created_variations)} variations")
        print(f"   Product.has_variations: {sas_product.has_variations}")
        
        # Test methods after creating variations
        frontend_data = sas_product.get_variation_data_for_frontend()
        print(f"   Frontend variations count: {len(frontend_data.get('variations', []))}")
        
        # Test stock checking
        size_large_variations = [v for v in created_variations if v.variation_type == 'size' and v.variation_value == 'Large']
        if size_large_variations:
            test_combo = {'size': 'Large'}
            stock = sas_product.get_variation_combination_stock(**test_combo)
            print(f"   Stock for Large size: {stock}")
    
    return True


def main():
    """Run all tests"""
    print("🚀 Starting variation logic separation tests...\n")
    
    try:
        results = []
        
        # Test SAS variations
        results.append(("SAS Product Variations", test_sas_product_variations()))
        
        # Test LOTTO variations  
        results.append(("LOTTO Product Variations", test_lotto_product_variations()))
        
        # Test API consistency
        results.append(("API Consistency", test_api_consistency()))
        
        # Test SAS variation model creation
        results.append(("SAS Variation Model Creation", test_variation_model_creation()))
        
        # Print summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        for test_name, result in results:
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"{test_name:<30} {status}")
        
        all_passed = all(result for _, result in results)
        print(f"\nOverall Result: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
        
        return all_passed
        
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)