#!/usr/bin/env python3
"""
Debug script to examine the actual variation attributes
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

def debug_variation_attributes():
    print("🔍 Debugging Variation Attributes")
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

        # Get all variations and examine their structure
        variations_data = driver.execute_script("""
            if (typeof variationManager !== 'undefined') {
                const variations = variationManager.variations || [];
                console.log('Examining all variations:');

                variations.forEach((v, index) => {
                    console.log(`Variation ${index}:`, {
                        id: v.id,
                        type: v.type,
                        value: v.value,
                        attributes: v.attributes,
                        stock: v.stock,
                        is_in_stock: v.is_in_stock
                    });
                });

                return variations.map(v => ({
                    id: v.id,
                    type: v.type,
                    value: v.value,
                    attributes: v.attributes,
                    stock: v.stock,
                    is_in_stock: v.is_in_stock
                }));
            } else {
                return [];
            }
        """)

        print(f"\n📊 Found {len(variations_data)} total variations")

        # Group by type to understand structure
        types = {}
        for var in variations_data:
            var_type = var['type']
            if var_type not in types:
                types[var_type] = []
            types[var_type].append(var)

        print(f"\n📋 Variation types found: {list(types.keys())}")

        for var_type, variations in types.items():
            print(f"\n🏷️  {var_type} variations ({len(variations)}):")
            for var in variations[:3]:  # Show first 3 of each type
                print(f"   ID: {var['id']}")
                print(f"   Value: {var['value']}")
                print(f"   Attributes: {var['attributes']}")
                print(f"   Stock: {var['stock']}")
                print(f"   ---")

        # Now test the filtering logic manually
        print(f"\n🧪 Testing filtering logic:")

        filter_result = driver.execute_script("""
            if (typeof variationManager !== 'undefined') {
                const variations = variationManager.variations || [];
                const categoryValue = 'Adults';

                console.log('Testing filter for category:', categoryValue);

                const filtered = variations.filter(v => {
                    const varCategory = v.attributes?.age_group || v.attributes?.gender ||
                                       (v.value && v.value.includes(' - ') ? v.value.split(' - ')[1] : null);

                    console.log('Checking variation:', {
                        id: v.id,
                        value: v.value,
                        attributes: v.attributes,
                        extracted_category: varCategory
                    });

                    const matches = varCategory === categoryValue ||
                                   (categoryValue.toLowerCase() === 'adults' && varCategory === 'Adult') ||
                                   (categoryValue.toLowerCase() === 'kids' && varCategory === 'Kids');

                    console.log('Category match result:', matches);
                    return matches;
                });

                console.log('Filtered result:', filtered);
                return filtered;
            }
            return [];
        """)

        print(f"   Filtered variations for 'Adults': {len(filter_result)}")
        if filter_result:
            for var in filter_result[:3]:  # Show first 3 matches
                print(f"     - {var['id']}: {var['value']}")

    except Exception as e:
        print(f"❌ Error: {e}")

    finally:
        driver.quit()

if __name__ == "__main__":
    debug_variation_attributes()