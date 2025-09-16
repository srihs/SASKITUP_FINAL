#!/usr/bin/env python3
"""
Test script to validate SAS category variations behavior matches LOTTO color selection

This test validates that:
1. Category variations (Adults/Kids) are rendered as clickable swatches
2. Category selection displays stock banner like color selection
3. Stock information is shown correctly when category is selected
4. UI behavior matches LOTTO color selection pattern
"""

import json
import time
import os
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class SASCategoryVariationTest:
    def __init__(self):
        self.driver = None
        self.test_results = []

    def setup_driver(self):
        """Setup Chrome WebDriver with appropriate options"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            return True
        except Exception as e:
            print(f"Failed to setup Chrome driver: {e}")
            return False

    def test_category_swatches_exist(self, url):
        """Test 1: Verify category swatches exist and are clickable"""
        test_name = "Category Swatches Exist"
        try:
            self.driver.get(url)
            wait = WebDriverWait(self.driver, 10)

            # Wait for page to load and variations to render
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "category-swatches")))
            time.sleep(2)  # Allow JavaScript to render variations

            # Check if category swatches container exists
            category_container = self.driver.find_element(By.CLASS_NAME, "category-swatches")

            # Check if category swatches are rendered
            category_swatches = category_container.find_elements(By.CLASS_NAME, "category-swatch")

            if len(category_swatches) > 0:
                self.test_results.append({
                    "test": test_name,
                    "status": "PASS",
                    "message": f"Found {len(category_swatches)} category swatches",
                    "details": [swatch.text for swatch in category_swatches]
                })
                return True
            else:
                self.test_results.append({
                    "test": test_name,
                    "status": "FAIL",
                    "message": "No category swatches found",
                    "details": "Category swatches container exists but no swatches rendered"
                })
                return False

        except Exception as e:
            self.test_results.append({
                "test": test_name,
                "status": "ERROR",
                "message": str(e),
                "details": "Exception occurred during test"
            })
            return False

    def test_category_swatch_clickable(self, url):
        """Test 2: Verify category swatches are clickable"""
        test_name = "Category Swatches Clickable"
        try:
            if not self.driver.current_url == url:
                self.driver.get(url)
                time.sleep(2)

            # Find category swatches
            category_swatches = self.driver.find_elements(By.CLASS_NAME, "category-swatch")

            if len(category_swatches) == 0:
                self.test_results.append({
                    "test": test_name,
                    "status": "SKIP",
                    "message": "No category swatches found to test",
                    "details": "Prerequisite test failed"
                })
                return False

            # Try clicking the first category swatch
            first_swatch = category_swatches[0]
            category_name = first_swatch.text

            # Check if swatch has proper attributes
            has_data_attrs = (
                first_swatch.get_attribute("data-variation-type") and
                first_swatch.get_attribute("data-variation-value") and
                first_swatch.get_attribute("data-variation-id")
            )

            if not has_data_attrs:
                self.test_results.append({
                    "test": test_name,
                    "status": "FAIL",
                    "message": "Category swatch missing required data attributes",
                    "details": f"Swatch: {category_name}"
                })
                return False

            # Click the swatch
            first_swatch.click()
            time.sleep(1)  # Allow for selection animation

            # Check if swatch is selected
            is_selected = "selected" in first_swatch.get_attribute("class")

            if is_selected:
                self.test_results.append({
                    "test": test_name,
                    "status": "PASS",
                    "message": f"Successfully clicked and selected category: {category_name}",
                    "details": "Category swatch is clickable and shows selection state"
                })
                return True
            else:
                self.test_results.append({
                    "test": test_name,
                    "status": "FAIL",
                    "message": f"Category swatch clicked but not selected: {category_name}",
                    "details": "Click registered but selection state not updated"
                })
                return False

        except Exception as e:
            self.test_results.append({
                "test": test_name,
                "status": "ERROR",
                "message": str(e),
                "details": "Exception occurred during click test"
            })
            return False

    def test_stock_banner_display(self, url):
        """Test 3: Verify stock banner is displayed when category is selected"""
        test_name = "Stock Banner Display"
        try:
            if not self.driver.current_url == url:
                self.driver.get(url)
                time.sleep(2)

            # Find and click a category swatch
            category_swatches = self.driver.find_elements(By.CLASS_NAME, "category-swatch")

            if len(category_swatches) == 0:
                self.test_results.append({
                    "test": test_name,
                    "status": "SKIP",
                    "message": "No category swatches found to test",
                    "details": "Prerequisite test failed"
                })
                return False

            # Click the first available category
            first_swatch = category_swatches[0]
            category_name = first_swatch.text
            first_swatch.click()

            # Wait for stock display to appear
            time.sleep(2)

            # Check if stock grid container is visible
            stock_container = self.driver.find_element(By.CLASS_NAME, "stock-grid-container")
            is_visible = stock_container.is_displayed()

            if is_visible:
                # Check if stock header contains category name
                try:
                    stock_header = stock_container.find_element(By.CLASS_NAME, "stock-grid-header")
                    header_text = stock_header.text

                    if category_name.lower() in header_text.lower():
                        self.test_results.append({
                            "test": test_name,
                            "status": "PASS",
                            "message": f"Stock banner displayed correctly for category: {category_name}",
                            "details": f"Header text: {header_text}"
                        })
                        return True
                    else:
                        self.test_results.append({
                            "test": test_name,
                            "status": "PARTIAL",
                            "message": "Stock banner displayed but header doesn't show category",
                            "details": f"Expected: {category_name}, Got: {header_text}"
                        })
                        return False

                except NoSuchElementException:
                    self.test_results.append({
                        "test": test_name,
                        "status": "PARTIAL",
                        "message": "Stock container visible but no header found",
                        "details": "Stock display incomplete"
                    })
                    return False
            else:
                self.test_results.append({
                    "test": test_name,
                    "status": "FAIL",
                    "message": "Stock banner not displayed after category selection",
                    "details": f"Category selected: {category_name}"
                })
                return False

        except Exception as e:
            self.test_results.append({
                "test": test_name,
                "status": "ERROR",
                "message": str(e),
                "details": "Exception occurred during stock banner test"
            })
            return False

    def test_size_tiles_display(self, url):
        """Test 4: Verify size tiles are displayed with stock information"""
        test_name = "Size Tiles Display"
        try:
            if not self.driver.current_url == url:
                self.driver.get(url)
                time.sleep(2)

            # Find and click a category swatch
            category_swatches = self.driver.find_elements(By.CLASS_NAME, "category-swatch")

            if len(category_swatches) == 0:
                self.test_results.append({
                    "test": test_name,
                    "status": "SKIP",
                    "message": "No category swatches found to test",
                    "details": "Prerequisite test failed"
                })
                return False

            # Click the first available category
            first_swatch = category_swatches[0]
            first_swatch.click()
            time.sleep(2)

            # Check for size tiles in stock display
            size_tiles = self.driver.find_elements(By.CLASS_NAME, "size-tile")

            if len(size_tiles) > 0:
                # Check if size tiles have proper structure
                valid_tiles = 0
                for tile in size_tiles:
                    try:
                        size_name = tile.find_element(By.CLASS_NAME, "size-name")
                        stock_badge = tile.find_element(By.CLASS_NAME, "stock-badge")
                        if size_name.text and stock_badge.text:
                            valid_tiles += 1
                    except NoSuchElementException:
                        continue

                if valid_tiles > 0:
                    self.test_results.append({
                        "test": test_name,
                        "status": "PASS",
                        "message": f"Size tiles displayed correctly: {valid_tiles}/{len(size_tiles)} valid",
                        "details": "Size tiles contain size names and stock information"
                    })
                    return True
                else:
                    self.test_results.append({
                        "test": test_name,
                        "status": "FAIL",
                        "message": "Size tiles found but missing required elements",
                        "details": f"Found {len(size_tiles)} tiles but none have proper structure"
                    })
                    return False
            else:
                self.test_results.append({
                    "test": test_name,
                    "status": "FAIL",
                    "message": "No size tiles displayed after category selection",
                    "details": "Expected size tiles in stock display"
                })
                return False

        except Exception as e:
            self.test_results.append({
                "test": test_name,
                "status": "ERROR",
                "message": str(e),
                "details": "Exception occurred during size tiles test"
            })
            return False

    def run_all_tests(self, url):
        """Run all tests and return results"""
        print(f"Testing SAS Category Variations on: {url}")
        print("=" * 60)

        if not self.setup_driver():
            return {"error": "Failed to setup WebDriver"}

        try:
            # Run tests in sequence
            self.test_category_swatches_exist(url)
            self.test_category_swatch_clickable(url)
            self.test_stock_banner_display(url)
            self.test_size_tiles_display(url)

            # Print results
            for result in self.test_results:
                status_symbol = {
                    "PASS": "✅",
                    "FAIL": "❌",
                    "ERROR": "🚨",
                    "SKIP": "⏭️",
                    "PARTIAL": "⚠️"
                }.get(result["status"], "❓")

                print(f"{status_symbol} {result['test']}: {result['status']}")
                print(f"   {result['message']}")
                if result.get('details'):
                    print(f"   Details: {result['details']}")
                print()

            # Summary
            total_tests = len(self.test_results)
            passed_tests = len([r for r in self.test_results if r["status"] == "PASS"])
            failed_tests = len([r for r in self.test_results if r["status"] in ["FAIL", "ERROR"]])

            print("=" * 60)
            print(f"TEST SUMMARY: {passed_tests}/{total_tests} tests passed")

            if failed_tests == 0:
                print("🎉 All tests passed! Category variations work like LOTTO colors.")
            else:
                print(f"⚠️  {failed_tests} tests failed. See details above.")

            return {
                "total": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "results": self.test_results
            }

        finally:
            if self.driver:
                self.driver.quit()

def main():
    """Main test execution"""
    # Test URL - replace with actual SAS product URL
    test_url = "http://localhost:8000/clubs/sas/product/test-product/"

    if len(sys.argv) > 1:
        test_url = sys.argv[1]

    print("SAS Category Variations Test")
    print("Testing that Adults/Kids behave exactly like LOTTO color selection")
    print(f"URL: {test_url}")
    print()

    tester = SASCategoryVariationTest()
    results = tester.run_all_tests(test_url)

    # Save results to JSON file
    with open('test_category_variations_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: test_category_variations_results.json")

    # Exit with appropriate code
    if results.get("failed", 0) == 0:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()