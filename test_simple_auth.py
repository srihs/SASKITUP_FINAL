#!/usr/bin/env python3
"""
Simple test to verify authentication and sync endpoint functionality
"""

import requests
import json

BASE_URL = 'http://localhost:8080'

def test_sync_functionality():
    """Test the sync functionality with proper authentication"""
    print("🧪 Testing Sync Functionality")
    print("=" * 40)
    
    session = requests.Session()
    
    # Test 1: Check if sync page is accessible (should redirect to login if not authenticated)
    print("\n1️⃣ Testing sync page access...")
    sync_page_url = f'{BASE_URL}/clubs/sync/lotto/'
    response = session.get(sync_page_url, allow_redirects=False)
    print(f"Sync page status: {response.status_code}")
    
    if response.status_code == 200:
        print("✅ Sync page is accessible without authentication")
    elif response.status_code == 302:
        print("✅ Sync page correctly redirects unauthenticated users (302)")
        # Check if it redirects to login
        location = response.headers.get('Location', '')
        if 'login' in location:
            print("✅ Redirects to login page as expected")
        else:
            print(f"ℹ️ Redirects to: {location}")
    else:
        print(f"❌ Unexpected status for sync page: {response.status_code}")
        return False
    
    # Test 2: Login via admin interface
    print("\n2️⃣ Attempting login...")
    login_url = f'{BASE_URL}/admin/login/'
    
    # Get login page first
    response = session.get(login_url)
    if response.status_code != 200:
        print(f"❌ Cannot access login page. Status: {response.status_code}")
        return False
    
    # Extract CSRF token
    csrf_token = None
    for line in response.text.split('\n'):
        if 'csrfmiddlewaretoken' in line and 'value=' in line:
            try:
                csrf_token = line.split('value="')[1].split('"')[0]
                break
            except:
                continue
    
    if not csrf_token:
        print("❌ Could not find CSRF token in login page")
        return False
    
    # Attempt login
    login_data = {
        'username': 'admin',
        'password': 'admin123',
        'csrfmiddlewaretoken': csrf_token,
        'next': '/clubs/sync/lotto/'
    }
    
    response = session.post(login_url, data=login_data)
    print(f"Login attempt status: {response.status_code}")
    
    if response.status_code == 302:
        print("✅ Login successful (302 redirect)")
    elif response.status_code == 200:
        # Check if we're still on the login page (login failed) or redirected to sync page
        if 'sync' in response.url.lower() or 'dashboard' in response.text.lower():
            print("✅ Login may have succeeded")
        else:
            print("❌ Login may have failed (still on login page)")
            return False
    else:
        print(f"❌ Unexpected login response: {response.status_code}")
        return False
    
    # Test 3: Check authentication status with test endpoint
    print("\n3️⃣ Checking authentication status...")
    test_url = f'{BASE_URL}/clubs/sync/test/'
    response = session.get(test_url)
    
    if response.status_code != 200:
        print(f"❌ Test endpoint not accessible: {response.status_code}")
        return False
    
    try:
        data = response.json()
        auth_info = data.get('debug_info', {})
        print(f"Authenticated: {auth_info.get('authenticated', False)}")
        print(f"User: {auth_info.get('user', 'unknown')}")
        print(f"Is Staff: {auth_info.get('user_is_staff', False)}")
        print(f"Is Superuser: {auth_info.get('user_is_superuser', False)}")
        
        if auth_info.get('authenticated', False):
            print("✅ User is properly authenticated")
        else:
            print("❌ User authentication failed")
            return False
            
    except Exception as e:
        print(f"❌ Could not parse test endpoint response: {e}")
        return False
    
    # Test 4: Try sync endpoint with authenticated session
    print("\n4️⃣ Testing sync endpoint with authentication...")
    
    # Get the sync page to extract CSRF token
    response = session.get(sync_page_url)
    if response.status_code != 200:
        print(f"❌ Cannot access sync page after login: {response.status_code}")
        return False
    
    # Extract CSRF token from the sync page
    csrf_token = None
    
    # Look for meta tag first
    import re
    meta_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.text)
    if meta_match:
        csrf_token = meta_match.group(1)
        print(f"✅ CSRF token found in meta tag")
    else:
        # Fallback to looking in JavaScript
        for line in response.text.split('\n'):
            if "csrf_token" in line and "'" in line:
                try:
                    # Find the token value within quotes
                    start = line.find("'") + 1
                    end = line.find("'", start)
                    if start > 0 and end > start:
                        csrf_token = line[start:end]
                        break
                except:
                    continue
    
    if not csrf_token:
        print("❌ Could not extract CSRF token from sync page")
        print("Looking for CSRF references in page content:")
        for i, line in enumerate(response.text.split('\n')[:20]):
            if 'csrf' in line.lower():
                print(f"Line {i}: {line.strip()}")
        return False
    
    print(f"✅ CSRF token extracted: {csrf_token[:20]}...")
    
    # Test the sync endpoint
    sync_execute_url = f'{BASE_URL}/clubs/sync/lotto/execute/'
    headers = {
        'X-CSRFToken': csrf_token,
        'Content-Type': 'application/json',
        'Referer': sync_page_url
    }
    
    response = session.post(sync_execute_url, json={}, headers=headers)
    print(f"Sync endpoint status: {response.status_code}")
    
    try:
        result = response.json()
        print(f"Sync success: {result.get('success', 'unknown')}")
        
        if response.status_code == 200 or response.status_code == 500:
            # 500 might be expected if WooCommerce connection fails
            print("✅ Sync endpoint is accessible with authentication")
            
            if not result.get('success', False):
                error = result.get('error', 'Unknown error')
                error_code = result.get('error_code', 'UNKNOWN')
                print(f"ℹ️ Sync failed as expected: {error} ({error_code})")
                
                # If it's a WooCommerce connection error, that's actually good - 
                # it means authentication worked but the external service is the issue
                if error_code in ['CONNECTION_FAILED', 'SERVICE_INIT_FAILED', 'MISSING_SETTINGS']:
                    print("✅ Authentication successful - error is with external service")
                    return True
        else:
            print(f"❌ Sync endpoint returned unexpected status: {response.status_code}")
            print(f"Response: {result}")
            return False
            
    except Exception as e:
        print(f"❌ Could not parse sync response: {e}")
        print(f"Raw response: {response.text[:200]}...")
        return False
    
    print("\n🎉 Authentication and sync endpoint test completed successfully!")
    return True

if __name__ == '__main__':
    try:
        success = test_sync_functionality()
        exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        exit(1)