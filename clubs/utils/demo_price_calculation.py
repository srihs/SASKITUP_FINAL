#!/usr/bin/env python
"""
Demonstration script for the wholesale price calculation engine.

This script shows how to use the various components of the price calculation
engine with sample data.

Usage:
    python manage.py shell < clubs/utils/demo_price_calculation.py

Author: Claude Code SuperClaude
"""

from decimal import Decimal
from schools.utils.price_calculation import (
    PriceCalculator, ProductPriceManager, PriceAnalyzer,
    calculate_product_pricing, batch_calculate_pricing,
    generate_pricing_analysis, generate_pricing_report
)

def demo_price_calculator():
    """Demonstrate core price calculation functionality."""
    print("=" * 60)
    print("PRICE CALCULATOR DEMONSTRATION")
    print("=" * 60)

    calculator = PriceCalculator()

    # Test parsing various input formats
    print("\n1. Input Parsing Examples:")
    test_inputs = ["25.50", "$30.99", "1,234.56", "€15.00", 20, None, "invalid"]

    for input_val in test_inputs:
        result = calculator.parse_decimal(input_val)
        print(f"   Input: {input_val!r:12} → Output: {result}")

    # Test core calculations
    print("\n2. Core Calculations:")
    cost_price = Decimal('25.00')
    wholesale_price = Decimal('80.00')

    margin_75 = calculator.calculate_margin_75_price(cost_price)
    discount = calculator.calculate_discount_percentage(margin_75, wholesale_price)
    profit_margin = calculator.calculate_profit_margin(wholesale_price, cost_price)

    print(f"   Cost Price: ${cost_price}")
    print(f"   Wholesale Price: ${wholesale_price}")
    print(f"   75% Margin Price: ${margin_75}")
    print(f"   Discount Percentage: {discount}%")
    print(f"   Profit Margin: {profit_margin}%")

    # Test comprehensive calculation
    print("\n3. Comprehensive Calculation:")
    price_data = calculator.calculate_all_prices(
        cost_price=cost_price,
        wholesale_price=wholesale_price
    )

    if price_data.is_valid:
        print(f"   ✓ Calculation successful")
        print(f"   75% Margin: ${price_data.margin_75_price}")
        print(f"   Discount: {price_data.discount_percentage}%")
        print(f"   Profit Margin: {price_data.profit_margin}%")
        if price_data.warnings:
            print(f"   Warnings: {price_data.warnings}")
    else:
        print(f"   ✗ Calculation failed: {price_data.errors}")


def demo_product_manager():
    """Demonstrate product price manager functionality."""
    print("\n" + "=" * 60)
    print("PRODUCT PRICE MANAGER DEMONSTRATION")
    print("=" * 60)

    try:
        from schools.models import WholesaleProduct, WholesaleSchool

        # Try to get a sample product
        sample_product = WholesaleProduct.objects.filter(
            cost_price__isnull=False,
            wholesale_price__isnull=False
        ).first()

        if not sample_product:
            print("   No suitable sample products found. Creating demo data...")

            # Create sample school if needed
            school, created = WholesaleSchool.objects.get_or_create(
                cin7_id="DEMO_SCHOOL_001",
                defaults={'name': "Demo School"}
            )

            # Create sample product
            sample_product = WholesaleProduct.objects.create(
                name="Demo Product",
                school=school,
                cin7_id="DEMO_PRODUCT_001",
                cost_price=Decimal('20.00'),
                wholesale_price=Decimal('70.00')
            )
            print(f"   Created demo product: {sample_product.name}")

        print(f"\n1. Sample Product: {sample_product.name}")
        print(f"   Current Cost Price: ${sample_product.cost_price}")
        print(f"   Current Wholesale Price: ${sample_product.wholesale_price}")

        # Demonstrate single product calculation
        manager = ProductPriceManager()
        result = manager.update_product_pricing(
            sample_product,
            cost_price=Decimal('22.00'),
            save=False  # Don't save for demo
        )

        print(f"\n2. Price Calculation Result:")
        if result.success:
            print(f"   ✓ Calculation successful")
            print(f"   New Cost Price: ${result.new_values.cost_price}")
            print(f"   75% Margin Price: ${result.new_values.margin_75_price}")
            print(f"   Discount Percentage: {result.new_values.discount_percentage}%")
            if result.warnings:
                print(f"   Warnings: {result.warnings}")
        else:
            print(f"   ✗ Calculation failed: {result.errors}")

    except Exception as e:
        print(f"   Error in product manager demo: {e}")


def demo_batch_processing():
    """Demonstrate batch processing functionality."""
    print("\n" + "=" * 60)
    print("BATCH PROCESSING DEMONSTRATION")
    print("=" * 60)

    try:
        from schools.models import WholesaleProduct

        # Get a small sample of products
        products = list(WholesaleProduct.objects.filter(
            cost_price__isnull=False,
            wholesale_price__isnull=False,
            is_active=True
        )[:5])

        if not products:
            print("   No suitable products found for batch demo")
            return

        print(f"\n1. Sample Products ({len(products)} products):")
        for i, product in enumerate(products, 1):
            print(f"   {i}. {product.name}: Cost=${product.cost_price}, Wholesale=${product.wholesale_price}")

        # Create cost price mapping for demo
        cost_prices = {}
        for i, product in enumerate(products):
            # Simulate new cost prices
            new_cost = product.cost_price + Decimal('1.00') if product.cost_price else Decimal('25.00')
            cost_prices[product.id] = new_cost

        print(f"\n2. Batch Processing (dry run):")

        # Don't actually save changes - this is just a demo
        manager = ProductPriceManager()

        # Process without saving to database
        batch_result = manager.batch_update_pricing(
            products,
            cost_prices=cost_prices,
            use_transaction=False  # Don't use transaction for demo
        )

        print(f"   Total Processed: {batch_result.total_processed}")
        print(f"   Successful Updates: {batch_result.successful_updates}")
        print(f"   Failed Updates: {batch_result.failed_updates}")
        print(f"   Success Rate: {batch_result.success_rate:.1f}%")
        if batch_result.processing_time:
            print(f"   Processing Time: {batch_result.processing_time:.2f}s")

        if batch_result.errors:
            print(f"   Errors: {batch_result.errors[:3]}...")  # Show first 3 errors

    except Exception as e:
        print(f"   Error in batch processing demo: {e}")


def demo_analytics():
    """Demonstrate pricing analytics functionality."""
    print("\n" + "=" * 60)
    print("PRICING ANALYTICS DEMONSTRATION")
    print("=" * 60)

    try:
        analyzer = PriceAnalyzer()

        # Generate pricing statistics
        stats = generate_pricing_analysis()

        print(f"\n1. Pricing Statistics:")
        print(f"   Total Products: {stats.total_products:,}")
        print(f"   Products with Cost Price: {stats.products_with_cost:,}")
        print(f"   Products with 75% Margin Price: {stats.products_with_margin_75:,}")

        if stats.avg_cost_price:
            print(f"   Average Cost Price: ${stats.avg_cost_price:.2f}")

        if stats.avg_margin_75_price:
            print(f"   Average 75% Margin Price: ${stats.avg_margin_75_price:.2f}")

        if stats.avg_discount_percentage is not None:
            print(f"   Average Discount: {stats.avg_discount_percentage:.1f}%")

        print(f"\n2. Issue Analysis:")
        print(f"   High Discount Products (>50%): {stats.high_discount_products:,}")
        print(f"   Low Margin Products (<10%): {stats.low_margin_products:,}")
        print(f"   Negative Margin Products: {stats.negative_margin_products:,}")

        # Generate a sample report
        print(f"\n3. Sample Report (first 10 lines):")
        report_lines = generate_pricing_report(format_type='text').split('\n')
        for line in report_lines[:10]:
            print(f"   {line}")
        print("   ...")

    except Exception as e:
        print(f"   Error in analytics demo: {e}")


def demo_convenience_functions():
    """Demonstrate convenience functions."""
    print("\n" + "=" * 60)
    print("CONVENIENCE FUNCTIONS DEMONSTRATION")
    print("=" * 60)

    try:
        from schools.models import WholesaleProduct

        # Get a sample product
        sample_product = WholesaleProduct.objects.filter(
            cost_price__isnull=False,
            wholesale_price__isnull=False
        ).first()

        if sample_product:
            print(f"\n1. Single Product Calculation:")
            print(f"   Product: {sample_product.name}")

            # Use convenience function
            result = calculate_product_pricing(sample_product)

            if result.success:
                print(f"   ✓ Calculation successful")
                print(f"   75% Margin: ${result.new_values.margin_75_price}")
                print(f"   Discount: {result.new_values.discount_percentage}%")
            else:
                print(f"   ✗ Calculation failed: {result.errors}")

            print(f"\n2. Batch Calculation (convenience):")
            products = list(WholesaleProduct.objects.filter(
                cost_price__isnull=False,
                is_active=True
            )[:3])

            if products:
                batch_result = batch_calculate_pricing(products)
                print(f"   Processed {batch_result.total_processed} products")
                print(f"   Success rate: {batch_result.success_rate:.1f}%")

        else:
            print("   No suitable products found for convenience function demo")

    except Exception as e:
        print(f"   Error in convenience functions demo: {e}")


def main():
    """Run all demonstrations."""
    print("WHOLESALE PRICE CALCULATION ENGINE DEMONSTRATION")
    print("This script demonstrates the key features of the price calculation engine.")
    print("All calculations are performed without saving to the database.")

    try:
        demo_price_calculator()
        demo_product_manager()
        demo_batch_processing()
        demo_analytics()
        demo_convenience_functions()

        print("\n" + "=" * 60)
        print("DEMONSTRATION COMPLETED")
        print("=" * 60)
        print("The price calculation engine is ready for use!")
        print("\nNext steps:")
        print("1. Use the enhanced management command:")
        print("   python manage.py update_wholesale_prices --use-enhanced-engine")
        print("2. Try the new admin actions for batch pricing updates")
        print("3. Generate pricing analysis reports")
        print("4. Integrate the API-ready functions into your web interface")

    except Exception as e:
        print(f"\nDemonstration failed: {e}")
        print("Make sure you have wholesale products with cost prices in your database.")


if __name__ == '__main__':
    main()