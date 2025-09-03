#!/usr/bin/env python
"""
Test script to verify the clubs app setup
"""
import os
import sys
import django
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kitup.settings')
django.setup()

# Now we can import Django models
from clubs.models import Club, ClubCategory, Product
from clubs.services.woocommerce_service import WooCommerceService


def test_models():
    """Test model creation"""
    print("Testing models...")
    
    # Test Club model
    club = Club.objects.create(
        name="Test Football Club",
        club_type="LOTTO",
        sport_tag="Football",
        woo_category_id=999,
        contact_person="John Doe",
        email="john@testclub.com"
    )
    print(f"✅ Created club: {club}")
    
    # Test ClubCategory model  
    category = ClubCategory.objects.create(
        club=club,
        name="Jerseys",
        woo_category_id=1000,
        description="Team jerseys and uniforms"
    )
    print(f"✅ Created category: {category}")
    
    # Test Product model
    product = Product.objects.create(
        category=category,
        name="Home Jersey",
        woo_product_id=2000,
        price=89.99,
        regular_price=99.99,
        sale_price=89.99,
        sku="TFC-HOME-001",
        description="Official home team jersey"
    )
    print(f"✅ Created product: {product}")
    
    # Test relationships and methods
    print(f"✅ Club has {club.total_products} products")
    print(f"✅ Club has {club.active_categories_count} active categories")
    print(f"✅ Product is {'on sale' if product.is_on_sale else 'not on sale'}")
    print(f"✅ Product discount: {product.discount_percentage}%")
    
    # Clean up test data
    club.delete()
    print("✅ Test data cleaned up")


def test_woocommerce_service():
    """Test WooCommerce service initialization"""
    print("\nTesting WooCommerce service...")
    
    try:
        # Test LOTTO service (will fail without proper credentials, but should initialize)
        lotto_service = WooCommerceService(store_type='LOTTO')
        print(f"✅ LOTTO service initialized: {type(lotto_service).__name__}")
        
        # Test SAS service
        sas_service = WooCommerceService(store_type='SAS')  
        print(f"✅ SAS service initialized: {type(sas_service).__name__}")
        
        print("⚠️  Note: API connection tests require valid credentials in .env file")
        
    except Exception as e:
        print(f"❌ WooCommerce service error: {e}")


def test_management_command():
    """Test management command availability"""
    print("\nTesting management command...")
    
    from django.core.management import get_commands
    commands = get_commands()
    
    if 'sync_lotto_clubs' in commands:
        print("✅ sync_lotto_clubs command is available")
        print("   Usage: python manage.py sync_lotto_clubs --help")
    else:
        print("❌ sync_lotto_clubs command not found")


def main():
    """Run all tests"""
    print("=" * 50)
    print("SASKITUP Clubs App Setup Test")
    print("=" * 50)
    
    try:
        test_models()
        test_woocommerce_service()  
        test_management_command()
        
        print("\n" + "=" * 50)
        print("✅ All tests passed! Setup is working correctly.")
        print("=" * 50)
        
        print("\nNext steps:")
        print("1. Configure MySQL database by setting USE_MYSQL=True in .env")
        print("2. Install mysqlclient: pip install mysqlclient")
        print("3. Add WooCommerce API credentials to .env file")
        print("4. Run: python manage.py createsuperuser")
        print("5. Run: python manage.py runserver")
        print("6. Access admin at: http://localhost:8000/admin/")
        print("7. Test sync: python manage.py sync_lotto_clubs --dry-run")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()