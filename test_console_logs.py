#!/usr/bin/env python3
"""
Test script to capture all console logs during category selection
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

def test_console_logs():
    print("📊 Testing Console Logs During Category Selection")
    print("=" * 60)

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

    driver = webdriver.Chrome(options=chrome_options)

    try:
        url = "http://localhost:8000/clubs/sas/product/franklin-basketball-tee/"
        print(f"📍 Loading: {url}")
        driver.get(url)

        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(3)  # Allow JavaScript to load

        print("\n1️⃣ Getting initial console logs")
        logs = driver.get_log('browser')
        if logs:
            print("   Initial logs:")
            for log in logs[-5:]:  # Last 5 logs
                print(f"     [{log['level']}] {log['message']}")
        else:
            print("   No initial logs found")

        # Find and click category swatch
        category_swatches = driver.find_elements(By.CLASS_NAME, "category-swatch")
        if len(category_swatches) > 0:
            first_swatch = category_swatches[0]
            category_name = first_swatch.text
            print(f"\n2️⃣ Clicking category: '{category_name}'")

            first_swatch.click()
            time.sleep(2)  # Allow for async operations

            print("\n3️⃣ Getting console logs after click")
            logs = driver.get_log('browser')
            if logs:
                print("   Logs after click:")
                for log in logs:
                    print(f"     [{log['level']}] {log['message']}")
            else:
                print("   No logs after click")

            # Check if displayCategorySizeStock was called by executing JavaScript
            print("\n4️⃣ JavaScript Debugging")
            js_result = driver.execute_script("""
                // Check if function exists
                if (typeof variationManager !== 'undefined' &&
                    typeof variationManager.displayCategorySizeStock === 'function') {

                    // Try to call the function manually for debugging
                    console.log('[MANUAL TEST] Calling displayCategorySizeStock manually');
                    try {
                        variationManager.displayCategorySizeStock('Adults');
                        return {
                            exists: true,
                            called: true,
                            selectedVariations: variationManager.selectedVariations
                        };
                    } catch (e) {
                        return {
                            exists: true,
                            called: false,
                            error: e.toString(),
                            selectedVariations: variationManager.selectedVariations
                        };
                    }
                } else {
                    return { exists: false };
                }
            """)

            print(f"   Function exists: {js_result.get('exists', False)}")
            print(f"   Function called successfully: {js_result.get('called', False)}")
            if 'error' in js_result:
                print(f"   Error: {js_result['error']}")
            print(f"   Selected variations: {js_result.get('selectedVariations', 'N/A')}")

            # Wait a bit and get final logs
            time.sleep(2)
            print("\n5️⃣ Final console logs")
            logs = driver.get_log('browser')
            if logs:
                print("   Final logs:")
                for log in logs:
                    print(f"     [{log['level']}] {log['message']}")

    except Exception as e:
        print(f"❌ Error: {e}")

    finally:
        driver.quit()

if __name__ == "__main__":
    test_console_logs()