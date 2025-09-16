#!/usr/bin/env python3
"""
Test script for SAS layout fixes - specifically testing:
1. Color swatches positioning under "Available Colors" label
2. "Select Size" label removal
3. Stock text fixes (no hardcoded "Bottle")
"""

import time
import json
from playwright.sync_api import sync_playwright


def test_sas_layout_fixes():
    """Test the specific layout fixes implemented"""
    results = {
        "test_name": "SAS Layout Fixes Verification",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tests_performed": [],
        "issues_found": [],
        "layout_checks": {},
        "screenshots": []
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Set to True for headless
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        try:
            # Navigate to a SAS product page
            print("🔍 Navigating to SAS product page...")
            page.goto('http://localhost:8000/clubs/sas/club/athletics-auckland/')
            page.wait_for_load_state('networkidle', timeout=10000)

            # Find any product to test layout
            product_links = page.locator('a[href*="/clubs/sas/product/"]')
            if product_links.count() == 0:
                # Try the view all products page
                view_all_link = page.locator('a[href*="/clubs/sas/products/"]')
                if view_all_link.count() > 0:
                    view_all_link.click()
                    page.wait_for_load_state('networkidle', timeout=10000)
                    product_links = page.locator('a[href*="/clubs/sas/product/"]')

            if product_links.count() > 0:
                # Navigate to the first product
                product_links.first.click()
                page.wait_for_load_state('networkidle', timeout=10000)

                # Wait for variations to load
                time.sleep(3)

                # Test 1: Check for "Available Colors" label positioning
                print("🎨 Testing color label positioning...")
                available_colors_label = page.locator('h6:has-text("Available Colors")')
                color_swatches_container = page.locator('.color-swatches')

                if available_colors_label.count() > 0 and color_swatches_container.count() > 0:
                    # Check if color swatches come after the label in DOM order
                    label_element = available_colors_label.first
                    swatches_element = color_swatches_container.first

                    # Get their positions in the DOM
                    label_position = page.evaluate("""(element) => {
                        const rect = element.getBoundingClientRect();
                        return {top: rect.top, left: rect.left};
                    }""", label_element)

                    swatches_position = page.evaluate("""(element) => {
                        const rect = element.getBoundingClientRect();
                        return {top: rect.top, left: rect.left};
                    }""", swatches_element)

                    # Color swatches should be below the label (higher top value)
                    colors_below_label = swatches_position['top'] > label_position['top']

                    results["tests_performed"].append({
                        "test": "Color swatches positioned under Available Colors label",
                        "status": "PASS" if colors_below_label else "FAIL",
                        "details": f"Label at Y:{label_position['top']}, Swatches at Y:{swatches_position['top']}",
                        "colors_below_label": colors_below_label
                    })

                    results["layout_checks"]["colors_positioned_correctly"] = colors_below_label

                    if not colors_below_label:
                        results["issues_found"].append("Color swatches appear ABOVE the 'Available Colors' label")
                else:
                    results["tests_performed"].append({
                        "test": "Available Colors label and swatches present",
                        "status": "FAIL",
                        "details": f"Label found: {available_colors_label.count()}, Swatches found: {color_swatches_container.count()}"
                    })
                    results["issues_found"].append("Missing Available Colors label or color swatches container")

                # Test 2: Check for absence of "Select Size" label
                print("📏 Testing Select Size label removal...")
                select_size_labels = page.locator('h6:has-text("Select Size"), .variation-title:has-text("Select Size")')
                select_size_count = select_size_labels.count()

                results["tests_performed"].append({
                    "test": "Select Size label removed",
                    "status": "PASS" if select_size_count == 0 else "FAIL",
                    "details": f"Found {select_size_count} 'Select Size' labels (should be 0)",
                    "select_size_labels_found": select_size_count
                })

                results["layout_checks"]["select_size_removed"] = select_size_count == 0

                if select_size_count > 0:
                    results["issues_found"].append(f"Found {select_size_count} 'Select Size' labels that should be removed")

                # Test 3: Check stock text is not hardcoded "Bottle"
                print("📦 Testing stock text fixes...")

                # Wait for color selection and stock display
                color_swatches = page.locator('[data-variation-type="color"]')
                if color_swatches.count() > 0:
                    # Click first color to trigger stock display
                    color_swatches.first.click()
                    time.sleep(2)

                    # Check for stock text
                    stock_headers = page.locator('.stock-grid-header h6, .stock-grid-header')
                    stock_text_contains_bottle = False
                    stock_texts = []

                    for i in range(stock_headers.count()):
                        header = stock_headers.nth(i)
                        text = header.inner_text()
                        stock_texts.append(text)
                        if "bottle" in text.lower():
                            stock_text_contains_bottle = True

                    results["tests_performed"].append({
                        "test": "Stock text not hardcoded as 'Bottle'",
                        "status": "PASS" if not stock_text_contains_bottle else "FAIL",
                        "details": f"Stock texts found: {stock_texts}",
                        "contains_bottle": stock_text_contains_bottle
                    })

                    results["layout_checks"]["stock_text_fixed"] = not stock_text_contains_bottle

                    if stock_text_contains_bottle:
                        results["issues_found"].append("Stock text still contains hardcoded 'Bottle' reference")
                else:
                    results["tests_performed"].append({
                        "test": "Color swatches available for stock testing",
                        "status": "FAIL",
                        "details": "No color swatches found to test stock display"
                    })

                # Test 4: Overall layout structure check
                print("🏗️ Testing overall layout structure...")

                # Check template structure matches expected layout
                product_variations = page.locator('#productVariations')
                color_options = page.locator('.color-options')
                size_options = page.locator('.size-options')

                structure_valid = (
                    product_variations.count() > 0 and
                    color_options.count() > 0 and
                    size_options.count() > 0
                )

                results["tests_performed"].append({
                    "test": "Product variation structure present",
                    "status": "PASS" if structure_valid else "FAIL",
                    "details": f"Variations: {product_variations.count()}, Colors: {color_options.count()}, Sizes: {size_options.count()}"
                })

                results["layout_checks"]["structure_valid"] = structure_valid

                # Take screenshot for verification
                screenshot_path = f"/Users/sas/Repos/SASKITUP/test_screenshots/sas_layout_test_{int(time.time())}.png"
                page.screenshot(path=screenshot_path)
                results["screenshots"].append(screenshot_path)

            else:
                results["tests_performed"].append({
                    "test": "Find SAS product for testing",
                    "status": "FAIL",
                    "details": "No SAS products found to test layout"
                })
                results["issues_found"].append("No SAS products available for layout testing")

        except Exception as e:
            results["issues_found"].append(f"Browser test error: {str(e)}")
            results["tests_performed"].append({
                "test": "Overall layout test",
                "status": "ERROR",
                "error": str(e)
            })

        finally:
            browser.close()

    return results


def main():
    print("🚀 Starting SAS Layout Fixes Test...")

    results = test_sas_layout_fixes()

    print("✅ Test completed!")

    # Display results
    print("\n" + "="*60)
    print("SAS LAYOUT FIXES TEST RESULTS")
    print("="*60)

    print(f"\n🔬 Tests Performed: {len(results['tests_performed'])}")
    print(f"⚠️  Issues Found: {len(results['issues_found'])}")

    print("\n🧪 TEST RESULTS:")
    for test in results['tests_performed']:
        status_emoji = {"PASS": "✅", "FAIL": "❌", "WARNING": "⚠️", "ERROR": "🔥"}
        emoji = status_emoji.get(test['status'], "❓")
        print(f"{emoji} {test['test']}: {test['status']}")
        if 'details' in test:
            print(f"   └─ {test['details']}")
        if 'error' in test:
            print(f"   └─ Error: {test['error']}")

    if results['issues_found']:
        print("\n❌ ISSUES FOUND:")
        for issue in results['issues_found']:
            print(f"   • {issue}")

    print("\n📊 LAYOUT CHECKS SUMMARY:")
    layout_checks = results.get('layout_checks', {})
    for check, passed in layout_checks.items():
        emoji = "✅" if passed else "❌"
        print(f"{emoji} {check.replace('_', ' ').title()}: {'PASS' if passed else 'FAIL'}")

    if results['screenshots']:
        print(f"\n📸 Screenshots saved:")
        for screenshot in results['screenshots']:
            print(f"   • {screenshot}")

    # Save results
    with open('/Users/sas/Repos/SASKITUP/sas_layout_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n💾 Detailed results saved to: /Users/sas/Repos/SASKITUP/sas_layout_test_results.json")

    # Summary
    total_tests = len(results['tests_performed'])
    passed_tests = len([t for t in results['tests_performed'] if t['status'] == 'PASS'])

    print(f"\n🎯 SUMMARY: {passed_tests}/{total_tests} tests passed")

    return results


if __name__ == "__main__":
    main()