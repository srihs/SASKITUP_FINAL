#!/usr/bin/env python3
"""
Quick comparison test between SAS and LOTTO color behavior
"""

import time
import json
from playwright.sync_api import sync_playwright


def test_lotto_sas_comparison():
    """Compare LOTTO and SAS color variation behavior"""

    results = {
        "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "lotto_product": {},
        "sas_product": {},
        "comparison": {}
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        try:
            # Test LOTTO product first
            print("🎰 Testing LOTTO product...")
            page.goto('http://localhost:8000/clubs/lotto/')
            page.wait_for_load_state('networkidle', timeout=10000)

            # Get first LOTTO product
            lotto_product_links = page.locator('a[href*="/clubs/lotto/product/"]')
            if lotto_product_links.count() > 0:
                lotto_link = lotto_product_links.first
                lotto_name = lotto_link.inner_text()
                results["lotto_product"]["name"] = lotto_name

                print(f"Testing LOTTO product: {lotto_name}")
                lotto_link.click()
                page.wait_for_load_state('networkidle', timeout=10000)
                time.sleep(2)

                # Check LOTTO color behavior
                lotto_colors = page.locator('[data-variation-type="color"]')
                lotto_color_count = lotto_colors.count()
                results["lotto_product"]["color_count"] = lotto_color_count

                if lotto_color_count > 0:
                    lotto_disabled = []
                    for i in range(lotto_color_count):
                        swatch = lotto_colors.nth(i)
                        color_value = swatch.get_attribute('data-variation-value')
                        is_disabled = 'disabled' in (swatch.get_attribute('class') or '')
                        if is_disabled:
                            lotto_disabled.append(color_value)

                    results["lotto_product"]["disabled_colors"] = lotto_disabled
                    results["lotto_product"]["has_disabled_colors"] = len(lotto_disabled) > 0
                    print(f"LOTTO - Colors: {lotto_color_count}, Disabled: {len(lotto_disabled)}")

            # Test SAS product
            print("\n🏢 Testing SAS product...")
            page.goto('http://localhost:8000/clubs/sas/club/athletics-auckland/')
            page.wait_for_load_state('networkidle', timeout=10000)

            # Get first SAS product
            sas_product_links = page.locator('a[href*="/clubs/sas/product/"]')
            if sas_product_links.count() > 0:
                sas_link = sas_product_links.first
                sas_name = sas_link.inner_text()
                results["sas_product"]["name"] = sas_name

                print(f"Testing SAS product: {sas_name}")
                sas_link.click()
                page.wait_for_load_state('networkidle', timeout=10000)
                time.sleep(2)

                # Check SAS color behavior
                sas_colors = page.locator('[data-variation-type="color"]')
                sas_color_count = sas_colors.count()
                results["sas_product"]["color_count"] = sas_color_count

                if sas_color_count > 0:
                    sas_disabled = []
                    for i in range(sas_color_count):
                        swatch = sas_colors.nth(i)
                        color_value = swatch.get_attribute('data-variation-value')
                        is_disabled = 'disabled' in (swatch.get_attribute('class') or '')
                        if is_disabled:
                            sas_disabled.append(color_value)

                    results["sas_product"]["disabled_colors"] = sas_disabled
                    results["sas_product"]["has_disabled_colors"] = len(sas_disabled) > 0
                    print(f"SAS - Colors: {sas_color_count}, Disabled: {len(sas_disabled)}")

            # Comparison analysis
            results["comparison"]["sas_colors_never_disabled"] = not results["sas_product"].get("has_disabled_colors", True)
            results["comparison"]["behavior_consistent"] = (
                not results["sas_product"].get("has_disabled_colors", True) and
                results["sas_product"].get("color_count", 0) > 0
            )

        except Exception as e:
            results["error"] = str(e)
            print(f"Error during comparison test: {e}")

        finally:
            browser.close()

    return results


def main():
    print("🔍 Starting LOTTO vs SAS Comparison Test...")

    results = test_lotto_sas_comparison()

    print("\n" + "="*60)
    print("LOTTO vs SAS COLOR BEHAVIOR COMPARISON")
    print("="*60)

    # Display results
    if "lotto_product" in results:
        lotto = results["lotto_product"]
        print(f"\n🎰 LOTTO Product: {lotto.get('name', 'Unknown')}")
        print(f"   Colors: {lotto.get('color_count', 0)}")
        print(f"   Disabled: {len(lotto.get('disabled_colors', []))}")
        if lotto.get('disabled_colors'):
            print(f"   Disabled Colors: {lotto['disabled_colors']}")

    if "sas_product" in results:
        sas = results["sas_product"]
        print(f"\n🏢 SAS Product: {sas.get('name', 'Unknown')}")
        print(f"   Colors: {sas.get('color_count', 0)}")
        print(f"   Disabled: {len(sas.get('disabled_colors', []))}")
        if sas.get('disabled_colors'):
            print(f"   Disabled Colors: {sas['disabled_colors']}")

    if "comparison" in results:
        comp = results["comparison"]
        print(f"\n📊 COMPARISON RESULTS:")
        print(f"   SAS colors never disabled: {'✅ YES' if comp.get('sas_colors_never_disabled') else '❌ NO'}")
        print(f"   Behavior consistent: {'✅ YES' if comp.get('behavior_consistent') else '❌ NO'}")

    # Save results
    with open('/Users/sas/Repos/SASKITUP/lotto_sas_comparison.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n💾 Results saved to: lotto_sas_comparison.json")

    return results


if __name__ == "__main__":
    main()