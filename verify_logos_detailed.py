#!/usr/bin/env python3
"""
Detailed verification of club logo display on SAS clubs page.
"""
from playwright.sync_api import sync_playwright
import time

def verify_clubs_detailed():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            print("Navigating to http://127.0.0.1:8001/clubs/sas/")
            page.goto("http://127.0.0.1:8001/clubs/sas/", wait_until="networkidle", timeout=30000)
            time.sleep(3)

            # Look for any card-like structure
            print("\nSearching for club cards with different selectors...")

            # Try multiple selectors
            selectors = [
                ".card",
                "[class*='card']",
                ".col",
                "[class*='col']"
            ]

            for selector in selectors:
                count = page.locator(selector).count()
                if count > 0:
                    print(f"  Found {count} elements with selector: {selector}")

            # Look specifically for images
            print("\nLooking for all images on the page:")
            all_images = page.locator("img").all()

            cloudfront_logos = 0
            other_images = 0

            for idx, img in enumerate(all_images[:15]):  # Check first 15 images
                src = img.get_attribute("src") or ""
                alt = img.get_attribute("alt") or ""

                if "cloudfront" in src.lower():
                    print(f"  ✓ Logo {cloudfront_logos + 1}: {alt}")
                    print(f"    CloudFront URL: {src[:80]}...")
                    cloudfront_logos += 1
                elif src and not any(x in src for x in ['favicon', 'logo-sm', 'logo-dark']):
                    print(f"  ~ Image {idx + 1}: {alt or 'No alt text'}")
                    print(f"    URL: {src[:80]}...")
                    other_images += 1

            print("\n" + "="*80)
            print("VERIFICATION RESULTS")
            print("="*80)
            print(f"CloudFront club logos found: {cloudfront_logos}")
            print(f"Other images: {other_images}")

            if cloudfront_logos >= 3:
                print("\n✅ SUCCESS: Club logos are displaying from CloudFront!")
                print("The clubs page is working correctly with logo images.")
                return 0
            else:
                print("\n⚠️  WARNING: Few or no CloudFront logos detected")
                return 1

        except Exception as e:
            print(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return 1

        finally:
            browser.close()

if __name__ == "__main__":
    import sys
    sys.exit(verify_clubs_detailed())
