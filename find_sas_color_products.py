#!/usr/bin/env python3
"""
Script to find SAS products with color variations
"""

import time
from playwright.sync_api import sync_playwright


def find_sas_color_products():
    """Find SAS products that have color variations"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        try:
            # Navigate to Athletics Auckland club page
            print("🔍 Checking Athletics Auckland products...")
            page.goto('http://localhost:8000/clubs/sas/club/athletics-auckland/')
            page.wait_for_load_state('networkidle', timeout=10000)

            # Get all product links
            product_links = page.locator('a[href*="/clubs/sas/product/"]')
            product_count = product_links.count()

            print(f"Found {product_count} products")

            products_with_colors = []

            for i in range(min(product_count, 10)):  # Check first 10 products
                try:
                    link = product_links.nth(i)
                    href = link.get_attribute('href')
                    product_name = link.inner_text() or "Unnamed Product"

                    print(f"\nChecking product {i+1}: {product_name}")
                    print(f"URL: {href}")

                    # Navigate to product page
                    link.click()
                    page.wait_for_load_state('networkidle', timeout=8000)
                    time.sleep(2)

                    # Check for color swatches
                    color_swatches = page.locator('[data-variation-type="color"]')
                    color_count = color_swatches.count()

                    if color_count > 0:
                        print(f"✅ Found {color_count} color variations!")

                        # Get color values
                        colors = []
                        for j in range(color_count):
                            swatch = color_swatches.nth(j)
                            color_value = swatch.get_attribute('data-variation-value')
                            is_disabled = 'disabled' in (swatch.get_attribute('class') or '')
                            colors.append({
                                'value': color_value,
                                'disabled': is_disabled
                            })

                        # Try to get product ID from API call
                        product_id = None
                        try:
                            product_id = page.evaluate("""
                                window.PRODUCT_ID ||
                                document.querySelector('[data-product-id]')?.getAttribute('data-product-id') ||
                                window.productData?.id
                            """)
                        except:
                            pass

                        products_with_colors.append({
                            'name': product_name,
                            'url': href,
                            'product_id': product_id,
                            'color_count': color_count,
                            'colors': colors
                        })
                    else:
                        print(f"❌ No color variations found")

                    # Go back to the products page
                    page.go_back()
                    page.wait_for_load_state('networkidle', timeout=8000)

                except Exception as e:
                    print(f"Error checking product {i+1}: {str(e)}")
                    # Try to go back to products page
                    try:
                        page.goto('http://localhost:8000/clubs/sas/club/athletics-auckland/')
                        page.wait_for_load_state('networkidle', timeout=8000)
                    except:
                        pass

            print(f"\n🎨 SUMMARY: Found {len(products_with_colors)} products with color variations:")
            for product in products_with_colors:
                print(f"  • {product['name']} (ID: {product['product_id']}) - {product['color_count']} colors")
                for color in product['colors']:
                    status = "DISABLED" if color['disabled'] else "ENABLED"
                    print(f"    - {color['value']}: {status}")

            return products_with_colors

        finally:
            browser.close()


if __name__ == "__main__":
    find_sas_color_products()