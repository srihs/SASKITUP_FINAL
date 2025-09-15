#!/usr/bin/env python3
"""
LOTTO Product Variations Browser Test

This script tests the LOTTO product color variations functionality in a real browser
to verify they're working correctly and identify any issues.

Test Requirements:
1. Navigate to the LOTTO product page: `/clubs/lotto/product/nzf-referee-shirt-men-23679/`
2. Check if the page loads correctly
3. Verify if color variation elements are present in the DOM
4. Test if the ProductVariationManager is initializing correctly
5. Check browser console for any JavaScript errors
6. Verify if the API calls are working
7. Test the color variation functionality

Expected Behavior:
- Color variations should appear as clickable image thumbnails
- 4 colors should be visible (Black, Fluro Yellow, Pink, Turquoise)
- Clicking colors should update the main product image
- No JavaScript errors in console

Server URL: http://localhost:8076
"""

import sys
import time
import json
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests

class LottoProductVariationsTester:
    def __init__(self, base_url="http://localhost:8076"):
        self.base_url = base_url
        self.test_url = urljoin(base_url, "/clubs/lotto/product/nzf-referee-shirt-men-23679/")
        self.api_base = urljoin(base_url, "/clubs/api/")
        self.driver = None
        self.results = {
            "test_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "page_load": {"success": False, "errors": []},
            "dom_structure": {"success": False, "elements_found": {}, "errors": []},
            "javascript": {"success": False, "console_errors": [], "errors": []},
            "api_calls": {"success": False, "responses": {}, "errors": []},
            "color_variations": {"success": False, "colors_found": [], "functionality": {}, "errors": []},
            "recommendations": []
        }

    def setup_browser(self):
        """Setup Chrome browser with appropriate options"""
        try:
            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--allow-running-insecure-content")
            chrome_options.add_argument("--disable-features=VizDisplayCompositor")
            # Enable console log capture
            chrome_options.add_argument("--enable-logging")
            chrome_options.add_argument("--log-level=0")
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_window_size(1200, 800)
            return True
        except Exception as e:
            self.results["page_load"]["errors"].append(f"Browser setup failed: {str(e)}")
            return False

    def test_page_load(self):
        """Test if the LOTTO product page loads correctly"""
        print(f"🌐 Testing page load: {self.test_url}")
        
        try:
            # Navigate to the page
            self.driver.get(self.test_url)
            
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Check if it's an error page
            page_title = self.driver.title
            page_source = self.driver.page_source.lower()
            
            if "404" in page_title or "not found" in page_source or "error" in page_source:
                self.results["page_load"]["errors"].append(f"Page shows error - Title: {page_title}")
                return False
                
            # Look for product-specific elements
            try:
                product_title = self.driver.find_element(By.CLASS_NAME, "product-title")
                self.results["page_load"]["product_title"] = product_title.text
                print(f"✅ Page loaded successfully - Product: {product_title.text}")
            except NoSuchElementException:
                self.results["page_load"]["errors"].append("Product title not found")
                return False
            
            self.results["page_load"]["success"] = True
            self.results["page_load"]["url"] = self.driver.current_url
            self.results["page_load"]["title"] = page_title
            return True
            
        except TimeoutException:
            self.results["page_load"]["errors"].append("Page load timeout")
            return False
        except Exception as e:
            self.results["page_load"]["errors"].append(f"Page load error: {str(e)}")
            return False

    def test_dom_structure(self):
        """Check DOM structure for color variation elements"""
        print("🔍 Checking DOM structure for variation elements...")
        
        elements_to_check = {
            "variation_section": ".variation-section, #productVariations",
            "variation_loading": ".variation-loading",
            "color_swatches": ".color-swatches",
            "color_swatch": ".color-swatch",
            "main_product_image": "#mainProductImage",
            "thumbnail_sidebar": ".thumbnail-sidebar",
            "product_variations_js": "script[src*='product-variations.js']",
            "variation_manager_script": "script:contains('ProductVariationManager')"
        }
        
        for element_name, selector in elements_to_check.items():
            try:
                if "script" in selector and "contains" in selector:
                    # Special handling for script content
                    scripts = self.driver.find_elements(By.TAG_NAME, "script")
                    found = False
                    for script in scripts:
                        script_content = script.get_attribute("innerHTML")
                        if script_content and "ProductVariationManager" in script_content:
                            found = True
                            break
                    self.results["dom_structure"]["elements_found"][element_name] = found
                else:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    self.results["dom_structure"]["elements_found"][element_name] = len(elements)
                    
                    if len(elements) > 0:
                        print(f"✅ Found {len(elements)} {element_name} element(s)")
                        
                        # Get additional info for variation elements
                        if element_name == "variation_section":
                            element = elements[0]
                            self.results["dom_structure"]["variation_section_html"] = element.get_attribute("outerHTML")[:500]
                            
                    else:
                        print(f"❌ {element_name} not found")
                        
            except Exception as e:
                self.results["dom_structure"]["errors"].append(f"Error checking {element_name}: {str(e)}")
                self.results["dom_structure"]["elements_found"][element_name] = 0

        # Check if variation container has content
        try:
            variation_container = self.driver.find_element(By.CSS_SELECTOR, ".variation-section, #productVariations")
            container_html = variation_container.get_attribute("innerHTML")
            if "Loading product options" in container_html:
                print("⚠️  Variation container still shows loading message")
                self.results["dom_structure"]["still_loading"] = True
            elif "color-swatch" in container_html:
                print("✅ Variation container has color swatches")
                self.results["dom_structure"]["has_color_swatches"] = True
            else:
                print("❌ Variation container appears empty or has different content")
                self.results["dom_structure"]["container_content"] = container_html[:200]
        except NoSuchElementException:
            self.results["dom_structure"]["errors"].append("Variation container not found")

        # Success if we found key elements
        key_elements = ["variation_section", "main_product_image", "product_variations_js"]
        found_key_elements = sum(1 for elem in key_elements if self.results["dom_structure"]["elements_found"].get(elem, 0) > 0)
        self.results["dom_structure"]["success"] = found_key_elements >= 2

        return self.results["dom_structure"]["success"]

    def test_javascript_errors(self):
        """Check browser console for JavaScript errors"""
        print("📜 Checking JavaScript console for errors...")
        
        try:
            # Get console logs
            logs = self.driver.get_log('browser')
            
            js_errors = []
            warnings = []
            
            for log in logs:
                level = log['level']
                message = log['message']
                
                if level == 'SEVERE':
                    js_errors.append({
                        "level": level,
                        "message": message,
                        "timestamp": log['timestamp']
                    })
                    print(f"❌ JS Error: {message}")
                elif level == 'WARNING':
                    warnings.append({
                        "level": level,
                        "message": message,
                        "timestamp": log['timestamp']
                    })
                    print(f"⚠️  JS Warning: {message}")
            
            self.results["javascript"]["console_errors"] = js_errors
            self.results["javascript"]["console_warnings"] = warnings
            self.results["javascript"]["success"] = len(js_errors) == 0
            
            if len(js_errors) == 0:
                print("✅ No JavaScript errors found")
            else:
                print(f"❌ Found {len(js_errors)} JavaScript errors")
                
            return len(js_errors) == 0
            
        except Exception as e:
            self.results["javascript"]["errors"].append(f"Error checking console: {str(e)}")
            return False

    def test_api_calls(self):
        """Test API endpoints for product variations"""
        print("🔗 Testing API endpoints...")
        
        # Test the variations API endpoint directly
        try:
            # Get product ID from the URL or page
            product_id = None
            try:
                # Try to extract from URL or find in page
                url_parts = self.test_url.split('/')
                # Look for product ID in the page's JavaScript
                scripts = self.driver.find_elements(By.TAG_NAME, "script")
                for script in scripts:
                    content = script.get_attribute("innerHTML")
                    if content and "productId" in content:
                        # Extract product ID from JavaScript
                        import re
                        match = re.search(r'productId.*?(\d+)', content)
                        if match:
                            product_id = int(match.group(1))
                            break
            except:
                pass
            
            if not product_id:
                # Try to find product ID from data attributes or other sources
                try:
                    body = self.driver.find_element(By.TAG_NAME, "body")
                    product_id = body.get_attribute("data-product-id")
                    if product_id:
                        product_id = int(product_id)
                except:
                    pass
            
            if product_id:
                print(f"📝 Found product ID: {product_id}")
                
                # Test variations API
                variations_url = f"{self.api_base}lotto/product/{product_id}/variations/"
                print(f"🔗 Testing variations API: {variations_url}")
                
                response = requests.get(variations_url, timeout=10)
                self.results["api_calls"]["responses"]["variations"] = {
                    "status_code": response.status_code,
                    "url": variations_url,
                    "response_size": len(response.content)
                }
                
                if response.status_code == 200:
                    data = response.json()
                    self.results["api_calls"]["responses"]["variations"]["data"] = data
                    print(f"✅ Variations API successful - Found {len(data.get('variations', []))} variations")
                    
                    # Check for color variations specifically
                    color_variations = []
                    grouped_variations = data.get('grouped_variations', {})
                    if 'color' in grouped_variations:
                        color_variations = grouped_variations['color']
                        print(f"✅ Found {len(color_variations)} color variations")
                        self.results["api_calls"]["color_variations_found"] = color_variations
                    else:
                        print("❌ No color variations found in API response")
                        
                else:
                    print(f"❌ Variations API failed: {response.status_code}")
                    self.results["api_calls"]["errors"].append(f"Variations API returned {response.status_code}")
                    
            else:
                print("❌ Could not determine product ID")
                self.results["api_calls"]["errors"].append("Could not determine product ID")
                
        except Exception as e:
            self.results["api_calls"]["errors"].append(f"API test error: {str(e)}")
            print(f"❌ API test error: {str(e)}")

        self.results["api_calls"]["success"] = len(self.results["api_calls"]["errors"]) == 0
        return self.results["api_calls"]["success"]

    def test_color_variations_functionality(self):
        """Test the actual color variation functionality"""
        print("🎨 Testing color variation functionality...")
        
        try:
            # Wait a bit for JavaScript to initialize
            time.sleep(3)
            
            # Look for color swatches
            color_swatches = self.driver.find_elements(By.CSS_SELECTOR, ".color-swatch")
            
            if not color_swatches:
                print("❌ No color swatches found")
                self.results["color_variations"]["errors"].append("No color swatches found")
                return False
            
            print(f"✅ Found {len(color_swatches)} color swatches")
            self.results["color_variations"]["colors_found"] = []
            
            # Test each color swatch
            for i, swatch in enumerate(color_swatches):
                try:
                    color_value = swatch.get_attribute("data-variation-value")
                    color_available = swatch.get_attribute("data-available")
                    image_url = swatch.get_attribute("data-image-url")
                    
                    color_info = {
                        "index": i,
                        "color_value": color_value,
                        "available": color_available,
                        "has_image": bool(image_url),
                        "clickable": True
                    }
                    
                    print(f"   Color {i+1}: {color_value} (Available: {color_available})")
                    
                    # Test clicking the swatch
                    try:
                        original_main_image = self.driver.find_element(By.ID, "mainProductImage").get_attribute("src")
                        
                        # Click the swatch
                        self.driver.execute_script("arguments[0].click();", swatch)
                        time.sleep(1)  # Wait for image to potentially change
                        
                        new_main_image = self.driver.find_element(By.ID, "mainProductImage").get_attribute("src")
                        
                        color_info["click_test"] = {
                            "clicked": True,
                            "image_changed": original_main_image != new_main_image,
                            "original_image": original_main_image,
                            "new_image": new_main_image
                        }
                        
                        if original_main_image != new_main_image:
                            print(f"   ✅ Clicking color {color_value} changed main image")
                        else:
                            print(f"   ⚠️  Clicking color {color_value} did not change main image")
                            
                    except Exception as e:
                        color_info["click_test"] = {"error": str(e)}
                        print(f"   ❌ Error testing click for color {color_value}: {str(e)}")
                    
                    self.results["color_variations"]["colors_found"].append(color_info)
                    
                except Exception as e:
                    print(f"   ❌ Error processing color swatch {i}: {str(e)}")
                    self.results["color_variations"]["errors"].append(f"Error processing swatch {i}: {str(e)}")
            
            # Test if ProductVariationManager is initialized
            try:
                variation_manager_exists = self.driver.execute_script(
                    "return typeof variationManager !== 'undefined' && variationManager !== null;"
                )
                
                if variation_manager_exists:
                    print("✅ ProductVariationManager is initialized")
                    
                    # Get debug info from the variation manager
                    debug_info = self.driver.execute_script(
                        "return variationManager ? variationManager.getDebugInfo() : null;"
                    )
                    
                    if debug_info:
                        self.results["color_variations"]["variation_manager_debug"] = debug_info
                        print(f"   📊 Variation Manager Debug Info:")
                        print(f"   - Product ID: {debug_info.get('productId')}")
                        print(f"   - Product Type: {debug_info.get('productType')}")
                        print(f"   - Variations Count: {debug_info.get('variationsCount')}")
                        print(f"   - Selected Variations: {debug_info.get('selectedVariations')}")
                        print(f"   - Stock Status Visible: {debug_info.get('stockStatusVisible')}")
                        
                else:
                    print("❌ ProductVariationManager is not initialized")
                    self.results["color_variations"]["errors"].append("ProductVariationManager not initialized")
                    
            except Exception as e:
                print(f"❌ Error checking ProductVariationManager: {str(e)}")
                self.results["color_variations"]["errors"].append(f"Error checking variation manager: {str(e)}")
            
            # Success if we found color swatches and at least some work
            working_colors = sum(1 for color in self.results["color_variations"]["colors_found"] 
                               if color.get("click_test", {}).get("clicked", False))
                               
            self.results["color_variations"]["success"] = len(color_swatches) > 0 and working_colors > 0
            
            if self.results["color_variations"]["success"]:
                print(f"✅ Color variations working - {working_colors}/{len(color_swatches)} colors functional")
            else:
                print(f"❌ Color variations not working properly")
                
            return self.results["color_variations"]["success"]
            
        except Exception as e:
            self.results["color_variations"]["errors"].append(f"Functionality test error: {str(e)}")
            print(f"❌ Color variation functionality test error: {str(e)}")
            return False

    def generate_recommendations(self):
        """Generate recommendations based on test results"""
        print("💡 Generating recommendations...")
        
        recommendations = []
        
        # Page load issues
        if not self.results["page_load"]["success"]:
            recommendations.append({
                "category": "Page Load",
                "priority": "High",
                "issue": "Page failed to load properly",
                "solution": "Check URL routing, view implementation, and template rendering"
            })
        
        # DOM structure issues
        if not self.results["dom_structure"]["success"]:
            if self.results["dom_structure"]["elements_found"].get("variation_section", 0) == 0:
                recommendations.append({
                    "category": "DOM Structure",
                    "priority": "High",
                    "issue": "Variation section element not found",
                    "solution": "Ensure #productVariations or .variation-section element exists in template"
                })
            
            if self.results["dom_structure"]["elements_found"].get("product_variations_js", 0) == 0:
                recommendations.append({
                    "category": "JavaScript",
                    "priority": "High",
                    "issue": "product-variations.js script not loaded",
                    "solution": "Check static file serving and script inclusion in template"
                })
        
        # JavaScript errors
        if self.results["javascript"]["console_errors"]:
            recommendations.append({
                "category": "JavaScript",
                "priority": "High",
                "issue": f"Found {len(self.results['javascript']['console_errors'])} JavaScript errors",
                "solution": "Fix JavaScript errors in console - check product-variations.js and page scripts"
            })
        
        # API issues
        if not self.results["api_calls"]["success"]:
            recommendations.append({
                "category": "API",
                "priority": "High",
                "issue": "API calls failing",
                "solution": "Check API endpoint implementation and URL routing for variations"
            })
        
        # Color variations not working
        if not self.results["color_variations"]["success"]:
            if not self.results["color_variations"]["colors_found"]:
                recommendations.append({
                    "category": "Color Variations",
                    "priority": "High",
                    "issue": "No color swatches found",
                    "solution": "Check if ProductVariationManager is rendering color swatches correctly"
                })
            else:
                recommendations.append({
                    "category": "Color Variations",
                    "priority": "Medium",
                    "issue": "Color variations found but not functioning correctly",
                    "solution": "Check click handlers and image update functionality in ProductVariationManager"
                })
        
        # If still loading
        if self.results["dom_structure"].get("still_loading"):
            recommendations.append({
                "category": "Loading",
                "priority": "High",
                "issue": "Variation container still shows loading message",
                "solution": "Check if API call is completing and variation rendering is working"
            })
        
        self.results["recommendations"] = recommendations
        
        for rec in recommendations:
            print(f"   🔧 {rec['priority']} Priority ({rec['category']}): {rec['issue']}")
            print(f"      💡 Solution: {rec['solution']}")

    def run_tests(self):
        """Run all tests"""
        print("🚀 Starting LOTTO Product Variations Tests")
        print("=" * 60)
        
        if not self.setup_browser():
            print("❌ Failed to setup browser")
            return self.results
        
        try:
            # Run tests in sequence
            self.test_page_load()
            self.test_dom_structure()
            self.test_javascript_errors()
            self.test_api_calls()
            self.test_color_variations_functionality()
            
            # Generate recommendations
            self.generate_recommendations()
            
            # Summary
            print("\n" + "=" * 60)
            print("📊 TEST SUMMARY")
            print("=" * 60)
            
            tests = [
                ("Page Load", self.results["page_load"]["success"]),
                ("DOM Structure", self.results["dom_structure"]["success"]),
                ("JavaScript", self.results["javascript"]["success"]),
                ("API Calls", self.results["api_calls"]["success"]),
                ("Color Variations", self.results["color_variations"]["success"])
            ]
            
            for test_name, success in tests:
                status = "✅ PASS" if success else "❌ FAIL"
                print(f"{test_name:20} {status}")
            
            total_passed = sum(1 for _, success in tests if success)
            print(f"\nOverall: {total_passed}/{len(tests)} tests passed")
            
            if total_passed == len(tests):
                print("🎉 All tests passed! Color variations should be working.")
            else:
                print("⚠️  Some tests failed. See recommendations above.")
                
        finally:
            if self.driver:
                self.driver.quit()
        
        return self.results

    def save_results(self, filename="test_results.json"):
        """Save test results to file"""
        try:
            with open(filename, 'w') as f:
                json.dump(self.results, f, indent=2, default=str)
            print(f"📄 Test results saved to {filename}")
        except Exception as e:
            print(f"❌ Error saving results: {str(e)}")

def main():
    """Main function"""
    tester = LottoProductVariationsTester()
    results = tester.run_tests()
    tester.save_results()
    
    # Exit with appropriate code
    all_passed = all([
        results["page_load"]["success"],
        results["dom_structure"]["success"],
        results["javascript"]["success"],
        results["api_calls"]["success"],
        results["color_variations"]["success"]
    ])
    
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()