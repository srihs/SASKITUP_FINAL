#!/usr/bin/env python3
"""
Test script to debug what happens when a category is clicked
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

def test_category_click():
    print("🧪 Testing Category Click Behavior")
    print("=" * 50)

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=chrome_options)

    try:
        url = "http://localhost:8000/clubs/sas/product/franklin-basketball-tee/"
        print(f"📍 Loading: {url}")
        driver.get(url)

        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(3)  # Allow JavaScript to load

        print("\n1️⃣ Before clicking category")

        # Check stock container before click
        stock_container = driver.find_element(By.CLASS_NAME, "stock-grid-container")
        print(f"   Stock container visible: {stock_container.is_displayed()}")
        print(f"   Stock container content: '{stock_container.text.strip()}'")

        # Find category swatches
        category_swatches = driver.find_elements(By.CLASS_NAME, "category-swatch")
        print(f"   Category swatches found: {len(category_swatches)}")

        if len(category_swatches) > 0:
            first_swatch = category_swatches[0]
            category_name = first_swatch.text
            print(f"   Will click on: '{category_name}'")

            print("\n2️⃣ Clicking category swatch")
            first_swatch.click()
            time.sleep(2)  # Allow for any async operations

            print("\n3️⃣ After clicking category")

            # Check if swatch is selected
            classes = first_swatch.get_attribute("class")
            print(f"   Swatch classes: {classes}")
            print(f"   Is selected: {'selected' in classes}")

            # Check stock container after click
            stock_container = driver.find_element(By.CLASS_NAME, "stock-grid-container")
            print(f"   Stock container visible: {stock_container.is_displayed()}")
            print(f"   Stock container content: '{stock_container.text.strip()}'")

            # Check for size tiles
            size_tiles = driver.find_elements(By.CLASS_NAME, "size-tile")
            print(f"   Size tiles found: {len(size_tiles)}")

            # Check for stock grid header
            try:
                stock_header = driver.find_element(By.CLASS_NAME, "stock-grid-header")
                print(f"   Stock header found: '{stock_header.text}'")
            except:
                print("   Stock header: Not found")

            # Check console logs for debug messages
            print("\n4️⃣ JavaScript Console Logs")
            logs = driver.get_log('browser')
            if logs:
                for log in logs:
                    if 'STOCK DEBUG' in log['message'] or 'Category' in log['message']:
                        print(f"   {log['message']}")
            else:
                print("   No relevant console logs found")

            # Check JavaScript state
            print("\n5️⃣ JavaScript State")
            variation_state = driver.execute_script("""
                if (typeof variationManager !== 'undefined') {
                    return {
                        selectedVariations: variationManager.selectedVariations,
                        variations: variationManager.variations ? variationManager.variations.length : 0
                    };
                } else {
                    return { error: 'variationManager not found' };
                }
            """)
            print(f"   Selected variations: {variation_state.get('selectedVariations', 'N/A')}")
            print(f"   Total variations: {variation_state.get('variations', 'N/A')}")

    except Exception as e:
        print(f"❌ Error: {e}")

    finally:
        driver.quit()

if __name__ == "__main__":
    test_category_click()