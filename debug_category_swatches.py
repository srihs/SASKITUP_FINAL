#!/usr/bin/env python3
"""
Debug script to identify the exact issue with SAS category swatch rendering
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def debug_category_swatches():
    print("🔍 Debugging SAS Category Swatches")
    print("=" * 50)

    # Setup headless Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    try:
        driver = webdriver.Chrome(options=chrome_options)
        url = "http://localhost:8000/clubs/sas/product/franklin-basketball-tee/"

        print(f"📍 Loading: {url}")
        driver.get(url)

        # Wait for page to load
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(3)  # Allow JavaScript to load

        print("\n1️⃣ Checking API Response")
        # Execute JavaScript to check the API response
        api_data = driver.execute_script("""
            return fetch('/clubs/api/sas/product/119/variations/')
                .then(response => response.json())
                .then(data => {
                    console.log('API Response:', data);
                    return data;
                });
        """)

        print(f"   API Success: {api_data.get('success', 'N/A')}")
        if 'grouped_variations' in api_data:
            category_variations = api_data['grouped_variations'].get('select main category', [])
            print(f"   Category Variations Found: {len(category_variations)}")
            for var in category_variations:
                print(f"     - {var['value']}: available={var['is_available']}")

        print("\n2️⃣ Checking DOM Elements")

        # Check if category container exists
        try:
            category_container = driver.find_element(By.CLASS_NAME, "category-swatches")
            print(f"   ✅ Category container found: {category_container.tag_name}")
        except NoSuchElementException:
            print("   ❌ Category container (.category-swatches) not found")
            return

        # Check for actual swatches
        try:
            category_swatches = driver.find_elements(By.CLASS_NAME, "category-swatch")
            print(f"   Category swatches found: {len(category_swatches)}")

            for i, swatch in enumerate(category_swatches):
                text = swatch.text
                classes = swatch.get_attribute("class")
                data_available = swatch.get_attribute("data-available")

                print(f"     Swatch {i+1}:")
                print(f"       Text: '{text}'")
                print(f"       Classes: {classes}")
                print(f"       data-available: {data_available}")
                print(f"       Disabled: {'disabled' in classes}")

        except NoSuchElementException:
            print("   ❌ No category swatches (.category-swatch) found")

        print("\n3️⃣ Checking JavaScript Console Logs")

        # Get console logs
        logs = driver.get_log('browser')
        if logs:
            print("   JavaScript Console Messages:")
            for log in logs[-10:]:  # Last 10 logs
                level = log['level']
                message = log['message']
                print(f"     [{level}] {message}")
        else:
            print("   No console logs found")

        print("\n4️⃣ Testing Variation Manager State")

        # Check if variationManager exists and its state
        manager_state = driver.execute_script("""
            if (typeof variationManager !== 'undefined') {
                return {
                    exists: true,
                    productId: variationManager.productId,
                    productType: variationManager.productType,
                    hasVariations: Object.keys(variationManager.groupedVariations || {}).length > 0,
                    groupedVariations: variationManager.groupedVariations
                };
            } else {
                return { exists: false };
            }
        """)

        if manager_state['exists']:
            print(f"   ✅ variationManager exists")
            print(f"     Product ID: {manager_state['productId']}")
            print(f"     Product Type: {manager_state['productType']}")
            print(f"     Has Variations: {manager_state['hasVariations']}")

            if 'groupedVariations' in manager_state and manager_state['groupedVariations']:
                print(f"     Grouped Variations: {list(manager_state['groupedVariations'].keys())}")
        else:
            print("   ❌ variationManager not found")

        print("\n5️⃣ Summary")
        print("   Issues identified:")

        # Analyze the issues
        issues = []

        if len(category_swatches) == 0:
            issues.append("No category swatches rendered in DOM")
        else:
            for i, swatch in enumerate(category_swatches):
                classes = swatch.get_attribute("class")
                if 'disabled' in classes:
                    issues.append(f"Swatch {i+1} is disabled (class contains 'disabled')")

        if not issues:
            print("   ✅ No issues found!")
        else:
            for issue in issues:
                print(f"   ❌ {issue}")

        return {
            'api_data': api_data,
            'swatches_count': len(category_swatches) if 'category_swatches' in locals() else 0,
            'manager_state': manager_state,
            'issues': issues
        }

    except Exception as e:
        print(f"❌ Error during debugging: {e}")
        return {'error': str(e)}

    finally:
        if 'driver' in locals():
            driver.quit()

if __name__ == "__main__":
    result = debug_category_swatches()
    print(f"\n🎯 Debug completed. Issues found: {len(result.get('issues', []))}")