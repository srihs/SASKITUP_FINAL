#!/usr/bin/env python3
"""
Test script for SAS color variation fixes
Tests the specific product: Athletics Auckland Staff and Team Managers Cap
"""

import time
import json
import requests
from playwright.sync_api import sync_playwright


def test_sas_color_variations():
    results = {
        "test_name": "SAS Color Variation Fixes",
        "product_tested": "Athletics Auckland Staff and Team Managers Cap",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tests_performed": [],
        "issues_found": [],
        "api_responses": {},
        "screenshots": []
    }

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        try:
            # Navigate to Athletics Auckland club page first
            print("🔍 Navigating to Athletics Auckland club page...")
            page.goto('http://localhost:8000/clubs/sas/club/athletics-auckland/')
            page.wait_for_load_state('networkidle', timeout=10000)

            # Take screenshot of club page
            screenshot_path = f"/Users/sas/Repos/SASKITUP/test_screenshots/sas_athletics_club_{int(time.time())}.png"
            page.screenshot(path=screenshot_path)
            results["screenshots"].append(screenshot_path)

            # Look for products with various text patterns
            print("🔍 Looking for Athletics Auckland products...")

            # Get all product links on the page
            product_links = page.locator('a[href*="/clubs/sas/product/"]')
            product_count = product_links.count()

            print(f"Found {product_count} product links")

            # Also check for the "View All Products" link to get more products
            if product_count == 0:
                view_all_link = page.locator('a[href*="/clubs/sas/products/?club=athletics-auckland"]')
                if view_all_link.count() > 0:
                    print("🔍 Navigating to View All Products page...")
                    view_all_link.click()
                    page.wait_for_load_state('networkidle', timeout=10000)

                    # Update product links after navigation
                    product_links = page.locator('a[href*="/clubs/sas/product/"]')
                    product_count = product_links.count()
                    print(f"Found {product_count} product links on products page")

            # Look for specific product or similar ones
            target_product = None
            for i in range(product_count):
                link = product_links.nth(i)
                link_text = link.inner_text().lower()
                href = link.get_attribute('href')

                # Check for Athletics Auckland or Staff/Team/Managers/Cap keywords
                if any(keyword in link_text for keyword in ['athletics', 'auckland', 'staff', 'team', 'managers', 'cap']):
                    print(f"Found potential match: {link.inner_text()} -> {href}")
                    target_product = (link, link.inner_text(), href)
                    break

            if not target_product:
                # Just pick the first product for testing
                if product_count > 0:
                    link = product_links.first
                    target_product = (link, link.inner_text(), link.get_attribute('href'))
                    print(f"Using first available product for testing: {target_product[1]}")

            if target_product:
                link, product_name, href = target_product
                results["product_tested"] = product_name

                print(f"✅ Found product: {product_name}, navigating...")
                link.click()
                page.wait_for_load_state('networkidle', timeout=10000)

                # Test 1: Verify we're on the product detail page
                current_url = page.url
                results["tests_performed"].append({
                    "test": "Navigation to product detail page",
                    "status": "PASS" if "/clubs/sas/product/" in current_url else "FAIL",
                    "url": current_url,
                    "product_name": product_name
                })

                # Wait for variations to load
                time.sleep(3)

                # Test 2: Check if color swatches are present and clickable
                print("🎨 Testing color swatches...")
                color_swatches = page.locator('[data-variation-type="color"]')
                color_count = color_swatches.count()

                if color_count > 0:
                    results["tests_performed"].append({
                        "test": "Color swatches present",
                        "status": "PASS",
                        "count": color_count,
                        "details": f"Found {color_count} color variations"
                    })

                    # Test each color swatch for clickability and disabled state
                    colors_tested = []
                    for i in range(color_count):
                        swatch = color_swatches.nth(i)
                        color_value = swatch.get_attribute('data-variation-value')
                        swatch_classes = swatch.get_attribute('class') or ''
                        is_disabled = 'disabled' in swatch_classes
                        is_available = swatch.get_attribute('data-available') != 'false'

                        print(f"  Testing color: {color_value}, disabled: {is_disabled}, available: {is_available}")

                        colors_tested.append({
                            "color": color_value,
                            "disabled": is_disabled,
                            "available": is_available,
                            "classes": swatch_classes
                        })

                        # Try clicking the swatch
                        try:
                            swatch.click()
                            time.sleep(1)

                            # Check if the swatch became active
                            updated_classes = swatch.get_attribute('class') or ''
                            is_active = 'active' in updated_classes

                            results["tests_performed"].append({
                                "test": f"Color swatch clickable - {color_value}",
                                "status": "PASS",
                                "disabled_state": is_disabled,
                                "became_active": is_active,
                                "notes": "Successfully clicked" + (" and became active" if is_active else "")
                            })
                        except Exception as e:
                            results["tests_performed"].append({
                                "test": f"Color swatch clickable - {color_value}",
                                "status": "FAIL",
                                "error": str(e),
                                "disabled_state": is_disabled
                            })
                            results["issues_found"].append(f"Could not click color swatch: {color_value}")

                    results["color_details"] = colors_tested

                    # Key test: Verify that SAS colors are NOT disabled even when out of stock
                    disabled_colors = [c for c in colors_tested if c["disabled"]]
                    if disabled_colors:
                        results["issues_found"].append(f"Found disabled color swatches (should be enabled for SAS): {[c['color'] for c in disabled_colors]}")
                        results["tests_performed"].append({
                            "test": "SAS colors never disabled",
                            "status": "FAIL",
                            "details": f"{len(disabled_colors)} colors are disabled when they should be enabled"
                        })
                    else:
                        results["tests_performed"].append({
                            "test": "SAS colors never disabled",
                            "status": "PASS",
                            "details": "All color swatches are enabled as expected for SAS"
                        })

                else:
                    results["tests_performed"].append({
                        "test": "Color swatches present",
                        "status": "FAIL",
                        "details": "No color swatches found"
                    })
                    results["issues_found"].append("No color variations found on product page")

                # Test 3: Check size tiles for stock information
                print("📏 Testing size tiles and stock display...")
                size_tiles = page.locator('[data-variation-type="size"]')
                size_count = size_tiles.count()

                if size_count > 0:
                    results["tests_performed"].append({
                        "test": "Size tiles present",
                        "status": "PASS",
                        "count": size_count
                    })

                    # Check for stock badges in size tiles
                    stock_badges = page.locator('.stock-badge, .badge')
                    badge_count = stock_badges.count()

                    results["tests_performed"].append({
                        "test": "Stock badges in size tiles",
                        "status": "PASS" if badge_count > 0 else "FAIL",
                        "count": badge_count,
                        "details": f"Found {badge_count} stock indicators"
                    })

                    # Check for SAS-specific styling
                    sas_stock_elements = page.locator('.sas-stock-available')
                    if sas_stock_elements.count() > 0:
                        results["tests_performed"].append({
                            "test": "SAS brand stock styling",
                            "status": "PASS",
                            "count": sas_stock_elements.count(),
                            "details": "SAS-specific stock styling found"
                        })
                    else:
                        results["tests_performed"].append({
                            "test": "SAS brand stock styling",
                            "status": "WARNING",
                            "details": "No SAS-specific stock styling found (may use default styling)"
                        })

                # Test 4: Extract product ID and test API
                print("🔌 Testing API integration...")

                # Extract product ID from the page's product data
                product_id_match = None
                try:
                    # Try to get product ID from JavaScript variables or data attributes
                    product_id_match = page.evaluate("""
                        window.PRODUCT_ID ||
                        document.querySelector('[data-product-id]')?.getAttribute('data-product-id') ||
                        window.productData?.id
                    """)
                except:
                    pass

                # Fallback: extract from URL slug and try to find numeric ID
                if not product_id_match and '/product/' in page.url:
                    url_slug = page.url.split('/product/')[-1].split('/')[0]

                    # For the target product "athletics-auckland-staff-and-team-managers-cap"
                    if 'athletics-auckland-staff-and-team-managers-cap' in url_slug:
                        # This is a hardcoded ID that we know from testing - ID 63
                        product_id_match = 63

                if product_id_match:
                    print(f"Testing API for product ID: {product_id_match}")

                    # Test the SAS-specific variations API endpoint
                    try:
                        api_response = page.evaluate(f"""
                            fetch('/clubs/api/sas/product/{product_id_match}/variations/')
                            .then(response => response.json())
                            .then(data => data)
                            .catch(error => ({{error: error.toString()}}))
                        """)

                        results["api_responses"]["variations"] = api_response

                        if 'error' not in api_response and 'grouped_variations' in api_response:
                            # Check if colors have is_available: true
                            color_variations = api_response.get('grouped_variations', {}).get('color', [])
                            all_colors_available = all(var.get('is_available', False) for var in color_variations)

                            results["tests_performed"].append({
                                "test": "API returns color variations as available",
                                "status": "PASS" if all_colors_available else "FAIL",
                                "details": f"Colors available: {all_colors_available}, Count: {len(color_variations)}",
                                "color_data": color_variations
                            })

                            if not all_colors_available:
                                unavailable_colors = [var.get('value') for var in color_variations if not var.get('is_available')]
                                results["issues_found"].append(f"API returned unavailable colors: {unavailable_colors}")
                        else:
                            results["tests_performed"].append({
                                "test": "API variations endpoint",
                                "status": "FAIL",
                                "error": api_response.get('error', 'Invalid response structure')
                            })
                            results["issues_found"].append(f"API error: {api_response.get('error', 'Invalid response')}")

                    except Exception as e:
                        results["tests_performed"].append({
                            "test": "API variations endpoint",
                            "status": "ERROR",
                            "error": str(e)
                        })
                        results["issues_found"].append(f"API test error: {str(e)}")

                # Take a screenshot of the final state
                screenshot_path = f"/Users/sas/Repos/SASKITUP/test_screenshots/sas_color_test_final_{int(time.time())}.png"
                page.screenshot(path=screenshot_path)
                results["screenshots"].append(screenshot_path)

            else:
                results["tests_performed"].append({
                    "test": "Find target product",
                    "status": "FAIL",
                    "details": "Could not find any products on SAS page"
                })
                results["issues_found"].append("No products found on SAS products page")

        except Exception as e:
            results["issues_found"].append(f"Browser test error: {str(e)}")
            results["tests_performed"].append({
                "test": "Overall browser test",
                "status": "ERROR",
                "error": str(e)
            })

        finally:
            browser.close()

    return results


def test_lotto_comparison():
    """Test a LOTTO product for comparison"""
    print("\n🎰 Testing LOTTO product for comparison...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        try:
            # Navigate to LOTTO products page
            page.goto('http://localhost:8000/clubs/lotto/')
            page.wait_for_load_state('networkidle', timeout=10000)

            # Get first product with color variations
            product_links = page.locator('a[href*="/clubs/lotto/product/"]')
            if product_links.count() > 0:
                link = product_links.first
                product_name = link.inner_text()

                print(f"Testing LOTTO product: {product_name}")
                link.click()
                page.wait_for_load_state('networkidle', timeout=10000)

                time.sleep(2)

                # Check color swatches
                color_swatches = page.locator('[data-variation-type="color"]')
                color_count = color_swatches.count()

                lotto_results = {
                    "product_name": product_name,
                    "color_count": color_count,
                    "colors": []
                }

                if color_count > 0:
                    for i in range(color_count):
                        swatch = color_swatches.nth(i)
                        color_value = swatch.get_attribute('data-variation-value')
                        is_disabled = 'disabled' in (swatch.get_attribute('class') or '')
                        is_available = swatch.get_attribute('data-available') != 'false'

                        lotto_results["colors"].append({
                            "color": color_value,
                            "disabled": is_disabled,
                            "available": is_available
                        })

                return lotto_results

        except Exception as e:
            return {"error": str(e)}

        finally:
            browser.close()

    return None


def main():
    print("🚀 Starting SAS Color Variation Test...")

    # Test SAS product
    sas_results = test_sas_color_variations()

    # Test LOTTO product for comparison
    lotto_results = test_lotto_comparison()

    print("✅ Test completed!")

    # Display results
    print("\n" + "="*60)
    print("SAS COLOR VARIATION TEST RESULTS")
    print("="*60)

    print(f"\n📦 Product Tested: {sas_results['product_tested']}")
    print(f"🔬 Tests Performed: {len(sas_results['tests_performed'])}")
    print(f"⚠️  Issues Found: {len(sas_results['issues_found'])}")

    print("\n🧪 TEST RESULTS:")
    for test in sas_results['tests_performed']:
        status_emoji = {"PASS": "✅", "FAIL": "❌", "WARNING": "⚠️", "ERROR": "🔥"}
        emoji = status_emoji.get(test['status'], "❓")
        print(f"{emoji} {test['test']}: {test['status']}")
        if 'details' in test:
            print(f"   └─ {test['details']}")
        if 'error' in test:
            print(f"   └─ Error: {test['error']}")

    if sas_results['issues_found']:
        print("\n❌ ISSUES FOUND:")
        for issue in sas_results['issues_found']:
            print(f"   • {issue}")

    if lotto_results and 'error' not in lotto_results:
        print(f"\n🎰 LOTTO COMPARISON:")
        print(f"   Product: {lotto_results['product_name']}")
        print(f"   Colors: {lotto_results['color_count']}")
        disabled_lotto = [c for c in lotto_results['colors'] if c['disabled']]
        print(f"   Disabled colors: {len(disabled_lotto)}")

    if sas_results['screenshots']:
        print(f"\n📸 Screenshots saved:")
        for screenshot in sas_results['screenshots']:
            print(f"   • {screenshot}")

    # Combine results
    combined_results = {
        "sas_test": sas_results,
        "lotto_comparison": lotto_results,
        "summary": {
            "sas_colors_working": len([t for t in sas_results['tests_performed'] if t['test'] == 'SAS colors never disabled' and t['status'] == 'PASS']) > 0,
            "issues_found": len(sas_results['issues_found']),
            "total_tests": len(sas_results['tests_performed'])
        }
    }

    # Save detailed results to JSON
    with open('/Users/sas/Repos/SASKITUP/sas_color_test_results.json', 'w') as f:
        json.dump(combined_results, f, indent=2)

    print(f"\n💾 Detailed results saved to: /Users/sas/Repos/SASKITUP/sas_color_test_results.json")

    return combined_results


if __name__ == "__main__":
    main()