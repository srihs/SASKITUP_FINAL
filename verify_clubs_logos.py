#!/usr/bin/env python3
"""
Script to verify that club logos are displaying correctly on the SAS clubs page.
"""
from playwright.sync_api import sync_playwright
import time
import sys

def verify_clubs_page():
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # Navigate to the clubs page
            print("Navigating to http://127.0.0.1:8001/clubs/sas/")
            page.goto("http://127.0.0.1:8001/clubs/sas/", wait_until="networkidle", timeout=30000)

            # Wait for content to load
            time.sleep(2)

            # Take screenshot
            screenshot_path = "/Users/sas/Repos/SASKITUP/clubs_page_screenshot.png"
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"Screenshot saved to: {screenshot_path}")

            # Check for club cards
            club_cards = page.locator(".club-card").count()
            print(f"\nFound {club_cards} club cards on the page")

            # Check for logo images in the first 5 clubs
            print("\nChecking logo display for first 5 clubs:")
            logos_found = 0
            fallbacks_found = 0

            for i in range(min(5, club_cards)):
                card = page.locator(".club-card").nth(i)
                club_name = card.locator(".club-name").text_content().strip()

                # Check if there's an img element
                img_element = card.locator(".club-logo-container img")
                if img_element.count() > 0:
                    img_src = img_element.get_attribute("src")
                    if img_src and "cloudfront" in img_src.lower():
                        print(f"  ✓ {club_name}: CloudFront logo displayed")
                        print(f"    URL: {img_src[:80]}...")
                        logos_found += 1
                    else:
                        print(f"  ~ {club_name}: Image found but not from CloudFront")
                        print(f"    URL: {img_src[:80]}...")
                else:
                    # Check for fallback avatar
                    avatar = card.locator(".club-logo-fallback")
                    if avatar.count() > 0:
                        print(f"  ✗ {club_name}: Using fallback avatar (no logo image)")
                        fallbacks_found += 1
                    else:
                        print(f"  ? {club_name}: Unknown logo state")

            print("\n" + "="*80)
            print("VERIFICATION SUMMARY")
            print("="*80)
            print(f"Total club cards: {club_cards}")
            print(f"CloudFront logos found: {logos_found}/5")
            print(f"Fallback avatars: {fallbacks_found}/5")

            if logos_found >= 3:
                print("\n✅ SUCCESS: Club logos are displaying correctly!")
                return 0
            else:
                print("\n❌ ISSUE: Most clubs are still using fallback avatars")
                return 1

        except Exception as e:
            print(f"Error during verification: {str(e)}")
            import traceback
            traceback.print_exc()
            return 1

        finally:
            browser.close()

if __name__ == "__main__":
    sys.exit(verify_clubs_page())
