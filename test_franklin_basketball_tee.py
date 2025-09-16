#!/usr/bin/env python3
"""
Comprehensive test script for Franklin Basketball Tee product page
Tests Adult/Child category options and debugging functionality
"""

import time
import json
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime

class FranklinBasketballTeeTest:
    def __init__(self):
        self.test_url = "http://localhost:8000/clubs/sas/product/franklin-basketball-tee/"
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'test_url': self.test_url,
            'tests': {},
            'api_data': {},
            'console_logs': [],
            'html_structure': {},
            'recommendations': []
        }
        self.driver = None

    def setup_driver(self):
        """Setup Chrome driver with options for testing"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run headless for CI/automation
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        # Enable logging to capture console messages
        chrome_options.add_argument("--enable-logging")
        chrome_options.add_argument("--log-level=0")
        chrome_options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

        self.driver = webdriver.Chrome(options=chrome_options)
        return self.driver

    def test_page_load(self):
        """Test if the page loads successfully"""
        test_name = "page_load"
        print(f"🔄 Testing: {test_name}")

        try:
            self.driver.get(self.test_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            page_title = self.driver.title
            current_url = self.driver.current_url

            self.results['tests'][test_name] = {
                'status': 'PASS',
                'page_title': page_title,
                'current_url': current_url,
                'load_time': time.time()
            }
            print(f"✅ Page loaded successfully: {page_title}")

        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAIL',
                'error': str(e)
            }
            print(f"❌ Page load failed: {e}")

    def test_category_buttons_visibility(self):
        """Test if Adult/Child category buttons are visible"""
        test_name = "category_buttons_visibility"
        print(f"🔄 Testing: {test_name}")

        try:
            # Wait for page to load completely
            time.sleep(3)

            # Look for category section
            category_section = None
            category_selectors = [
                '[data-variation-type="category"]',
                '.category-section',
                '.product-categories',
                '*[id*="category"]',
                '*[class*="category"]'
            ]

            for selector in category_selectors:
                try:
                    category_section = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if category_section:
                        break
                except NoSuchElementException:
                    continue

            if not category_section:
                # Check all variation sections
                variation_sections = self.driver.find_elements(By.CSS_SELECTOR, '[data-variation-type]')
                print(f"Found {len(variation_sections)} variation sections")
                for section in variation_sections:
                    variation_type = section.get_attribute('data-variation-type')
                    print(f"  - Variation type: {variation_type}")

            # Look for Adult/Child buttons specifically
            adult_child_buttons = []
            button_selectors = [
                'button:contains("Adult")',
                'button:contains("Child")',
                '.swatch-button',
                '.variation-button',
                '[data-value="Adult"]',
                '[data-value="Child"]'
            ]

            # Use JavaScript to find elements containing "Adult" or "Child"
            adult_child_elements = self.driver.execute_script("""
                var elements = [];
                var allElements = document.querySelectorAll('*');
                for (var i = 0; i < allElements.length; i++) {
                    var el = allElements[i];
                    var text = el.textContent || el.innerText || '';
                    if (text.toLowerCase().includes('adult') || text.toLowerCase().includes('child')) {
                        elements.push({
                            tag: el.tagName,
                            text: text.trim(),
                            className: el.className,
                            id: el.id,
                            outerHTML: el.outerHTML.substring(0, 200)
                        });
                    }
                }
                return elements;
            """)

            self.results['tests'][test_name] = {
                'status': 'PARTIAL',
                'category_section_found': category_section is not None,
                'adult_child_elements': adult_child_elements,
                'variation_sections_count': len(variation_sections) if 'variation_sections' in locals() else 0
            }

            if adult_child_elements:
                print(f"✅ Found {len(adult_child_elements)} elements with Adult/Child text")
                for elem in adult_child_elements:
                    print(f"  - {elem['tag']}: {elem['text'][:50]}...")
            else:
                print("❌ No Adult/Child elements found")

        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAIL',
                'error': str(e)
            }
            print(f"❌ Category buttons test failed: {e}")

    def test_api_response(self):
        """Test the API response for product variations"""
        test_name = "api_response"
        print(f"🔄 Testing: {test_name}")

        try:
            # Extract product slug from URL
            product_slug = "franklin-basketball-tee"
            api_url = f"http://localhost:8000/api/sas-products/{product_slug}/"

            print(f"Calling API: {api_url}")
            response = requests.get(api_url, timeout=10)

            if response.status_code == 200:
                api_data = response.json()
                self.results['api_data'] = api_data

                # Check for variations
                variations = api_data.get('variations', [])
                categories = [v for v in variations if v.get('type') == 'category']

                print(f"✅ API response successful")
                print(f"  - Total variations: {len(variations)}")
                print(f"  - Category variations: {len(categories)}")

                if categories:
                    for cat in categories:
                        print(f"  - Category: {cat.get('name')} (value: {cat.get('value')})")

                self.results['tests'][test_name] = {
                    'status': 'PASS',
                    'total_variations': len(variations),
                    'category_variations': len(categories),
                    'categories': [cat.get('value') for cat in categories]
                }

            else:
                self.results['tests'][test_name] = {
                    'status': 'FAIL',
                    'status_code': response.status_code,
                    'response_text': response.text[:500]
                }
                print(f"❌ API request failed: {response.status_code}")

        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAIL',
                'error': str(e)
            }
            print(f"❌ API test failed: {e}")

    def test_javascript_console(self):
        """Capture JavaScript console logs for errors"""
        test_name = "javascript_console"
        print(f"🔄 Testing: {test_name}")

        try:
            # Get console logs
            logs = self.driver.get_log('browser')

            errors = [log for log in logs if log['level'] == 'SEVERE']
            warnings = [log for log in logs if log['level'] == 'WARNING']

            self.results['console_logs'] = logs
            self.results['tests'][test_name] = {
                'status': 'PASS' if len(errors) == 0 else 'WARNING',
                'total_logs': len(logs),
                'errors': len(errors),
                'warnings': len(warnings),
                'error_messages': [log['message'] for log in errors]
            }

            print(f"📊 Console logs captured: {len(logs)} total, {len(errors)} errors, {len(warnings)} warnings")

            if errors:
                print("❌ JavaScript errors found:")
                for error in errors:
                    print(f"  - {error['message'][:100]}...")

        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAIL',
                'error': str(e)
            }
            print(f"❌ Console test failed: {e}")

    def test_html_structure(self):
        """Analyze HTML structure for category elements"""
        test_name = "html_structure"
        print(f"🔄 Testing: {test_name}")

        try:
            # Get product variations container
            variations_html = self.driver.execute_script("""
                var container = document.querySelector('.product-variations') ||
                               document.querySelector('[id*="variation"]') ||
                               document.querySelector('[class*="variation"]');
                return container ? container.outerHTML : null;
            """)

            # Get all form elements
            form_elements = self.driver.execute_script("""
                var forms = document.querySelectorAll('form');
                var formData = [];
                for (var i = 0; i < forms.length; i++) {
                    var form = forms[i];
                    formData.push({
                        id: form.id,
                        className: form.className,
                        innerHTML: form.innerHTML.substring(0, 1000)
                    });
                }
                return formData;
            """)

            # Check for specific variation-related elements
            variation_elements = self.driver.execute_script("""
                var selectors = [
                    '[data-variation-type]',
                    '.swatch-button',
                    '.variation-button',
                    'input[name*="variation"]',
                    'select[name*="variation"]'
                ];

                var found = {};
                selectors.forEach(function(selector) {
                    var elements = document.querySelectorAll(selector);
                    found[selector] = elements.length;
                });

                return found;
            """);

            self.results['html_structure'] = {
                'variations_html': variations_html,
                'form_elements': form_elements,
                'variation_elements': variation_elements
            }

            self.results['tests'][test_name] = {
                'status': 'PASS',
                'has_variations_container': variations_html is not None,
                'form_count': len(form_elements),
                'variation_element_counts': variation_elements
            }

            print(f"✅ HTML structure analyzed")
            print(f"  - Variations container found: {variations_html is not None}")
            print(f"  - Forms found: {len(form_elements)}")

        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAIL',
                'error': str(e)
            }
            print(f"❌ HTML structure test failed: {e}")

    def test_category_functionality(self):
        """Test clicking on category options if they exist"""
        test_name = "category_functionality"
        print(f"🔄 Testing: {test_name}")

        try:
            # Look for clickable category elements
            category_buttons = self.driver.execute_script("""
                var buttons = [];
                var selectors = [
                    'button[data-value*="adult" i]',
                    'button[data-value*="child" i]',
                    '.swatch-button',
                    '[data-variation-type="category"] button'
                ];

                selectors.forEach(function(selector) {
                    var elements = document.querySelectorAll(selector);
                    for (var i = 0; i < elements.length; i++) {
                        var el = elements[i];
                        buttons.push({
                            selector: selector,
                            text: el.textContent.trim(),
                            value: el.getAttribute('data-value'),
                            disabled: el.disabled,
                            visible: el.offsetParent !== null
                        });
                    }
                });

                return buttons;
            """)

            functionality_test = {
                'buttons_found': len(category_buttons),
                'buttons': category_buttons,
                'click_tests': []
            }

            # Try to click each button if found
            for i, button_info in enumerate(category_buttons):
                try:
                    if not button_info['disabled'] and button_info['visible']:
                        # Find and click the button
                        button = self.driver.find_elements(By.CSS_SELECTOR,
                            f"button[data-value='{button_info['value']}']")
                        if button:
                            button[0].click()
                            time.sleep(1)  # Wait for any updates

                            functionality_test['click_tests'].append({
                                'button_value': button_info['value'],
                                'clicked': True,
                                'error': None
                            })

                except Exception as click_error:
                    functionality_test['click_tests'].append({
                        'button_value': button_info.get('value', f'button_{i}'),
                        'clicked': False,
                        'error': str(click_error)
                    })

            self.results['tests'][test_name] = {
                'status': 'PASS' if len(category_buttons) > 0 else 'FAIL',
                **functionality_test
            }

            print(f"📊 Category functionality test completed")
            print(f"  - Buttons found: {len(category_buttons)}")

        except Exception as e:
            self.results['tests'][test_name] = {
                'status': 'FAIL',
                'error': str(e)
            }
            print(f"❌ Category functionality test failed: {e}")

    def generate_recommendations(self):
        """Generate recommendations based on test results"""
        print("🔄 Generating recommendations...")

        recommendations = []

        # Check API data
        if 'api_response' in self.results['tests']:
            api_test = self.results['tests']['api_response']
            if api_test['status'] == 'PASS':
                if api_test.get('category_variations', 0) == 0:
                    recommendations.append({
                        'priority': 'HIGH',
                        'category': 'API Data',
                        'issue': 'No category variations found in API response',
                        'solution': 'Check if product data in database includes Adult/Child variations'
                    })
                elif api_test.get('category_variations', 0) > 0:
                    recommendations.append({
                        'priority': 'MEDIUM',
                        'category': 'Frontend',
                        'issue': 'Category variations exist in API but not displaying on frontend',
                        'solution': 'Check JavaScript rendering logic for category variations'
                    })

        # Check console errors
        if 'javascript_console' in self.results['tests']:
            console_test = self.results['tests']['javascript_console']
            if console_test.get('errors', 0) > 0:
                recommendations.append({
                    'priority': 'HIGH',
                    'category': 'JavaScript',
                    'issue': f"JavaScript errors detected: {console_test['errors']} errors",
                    'solution': 'Fix JavaScript errors preventing proper page functionality'
                })

        # Check HTML structure
        if 'html_structure' in self.results['tests']:
            html_test = self.results['tests']['html_structure']
            if not html_test.get('has_variations_container', False):
                recommendations.append({
                    'priority': 'MEDIUM',
                    'category': 'HTML Structure',
                    'issue': 'No variations container found in HTML',
                    'solution': 'Verify template rendering for product variations section'
                })

        # Check category functionality
        if 'category_functionality' in self.results['tests']:
            func_test = self.results['tests']['category_functionality']
            if func_test.get('buttons_found', 0) == 0:
                recommendations.append({
                    'priority': 'HIGH',
                    'category': 'UI Elements',
                    'issue': 'No category buttons found on page',
                    'solution': 'Verify JavaScript logic for creating category swatch buttons'
                })

        self.results['recommendations'] = recommendations

        print(f"✅ Generated {len(recommendations)} recommendations")
        for rec in recommendations:
            print(f"  {rec['priority']}: {rec['issue']}")

    def run_all_tests(self):
        """Run all tests in sequence"""
        print("🚀 Starting Franklin Basketball Tee Product Page Test Suite")
        print("=" * 60)

        try:
            self.setup_driver()

            # Run tests in order
            self.test_page_load()
            self.test_api_response()
            self.test_javascript_console()
            self.test_html_structure()
            self.test_category_buttons_visibility()
            self.test_category_functionality()

            # Generate recommendations
            self.generate_recommendations()

            print("\n" + "=" * 60)
            print("🏁 Test Suite Completed")

            # Summary
            total_tests = len(self.results['tests'])
            passed_tests = len([t for t in self.results['tests'].values() if t['status'] == 'PASS'])
            failed_tests = len([t for t in self.results['tests'].values() if t['status'] == 'FAIL'])

            print(f"📊 Summary: {passed_tests}/{total_tests} tests passed, {failed_tests} failed")

        except Exception as e:
            print(f"❌ Test suite failed: {e}")
            self.results['suite_error'] = str(e)

        finally:
            if self.driver:
                self.driver.quit()

    def save_results(self, filename="franklin_basketball_test_results.json"):
        """Save test results to JSON file"""
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"💾 Results saved to {filename}")

if __name__ == "__main__":
    tester = FranklinBasketballTeeTest()
    tester.run_all_tests()
    tester.save_results()