#!/usr/bin/env python3
"""
Test authentication flow for the LOTTO sync functionality
"""

import requests
import json
from urllib.parse import urljoin

BASE_URL = 'http://localhost:8080'
USERNAME = 'admin'
PASSWORD = 'admin123'

def test_authentication_flow():
    """Test the complete authentication flow"""
    session = requests.Session()
    
    print("🔐 Testing Authentication Flow")
    print("=" * 50)
    
    # Test 1: Unauthenticated sync request (should fail)
    print("\n1️⃣ Testing unauthenticated sync request...")
    sync_url = urljoin(BASE_URL, '/clubs/sync/lotto/execute/')
    response = session.post(sync_url, json={})
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    assert response.status_code == 401, "Should return 401 for unauthenticated request"
    assert response.json()['error_code'] == 'AUTH_REQUIRED', "Should have AUTH_REQUIRED error code"
    print("✅ Unauthenticated request correctly rejected")
    
    # Test 2: Get login page and CSRF token
    print("\n2️⃣ Getting login page and CSRF token...")
    login_page_url = urljoin(BASE_URL, '/admin/login/')
    response = session.get(login_page_url)
    print(f"Login page status: {response.status_code}")
    assert response.status_code == 200, "Should be able to access login page"
    
    # Extract CSRF token from response
    csrf_token = None
    for line in response.text.split('\n'):
        if 'csrfmiddlewaretoken' in line and 'value=' in line:
            csrf_token = line.split('value="')[1].split('"')[0]
            break
    
    if not csrf_token:
        print("❌ Could not extract CSRF token")
        return False
    
    print(f"✅ CSRF token extracted: {csrf_token[:20]}...")
    
    # Test 3: Login with admin credentials
    print("\n3️⃣ Logging in with admin credentials...")
    login_data = {
        'username': USERNAME,
        'password': PASSWORD,
        'csrfmiddlewaretoken': csrf_token,
        'next': '/clubs/sync/lotto/'
    }
    
    response = session.post(login_page_url, data=login_data)
    print(f"Login response status: {response.status_code}")
    
    # Check if login was successful (should redirect)
    if response.status_code == 302:
        print("✅ Login successful (redirected)")
    else:
        print(f"❌ Login may have failed. Status: {response.status_code}")
        print(f"Response content preview: {response.text[:200]}...")
        return False
    
    # Test 4: Test authenticated sync request
    print("\n4️⃣ Testing authenticated sync request...")
    
    # Get CSRF token for the authenticated session
    test_url = urljoin(BASE_URL, '/clubs/sync/test/')
    response = session.get(test_url)
    test_data = response.json()
    print(f"Test endpoint - Authenticated: {test_data['debug_info']['authenticated']}")
    print(f"Test endpoint - User: {test_data['debug_info']['user']}")
    
    if not test_data['debug_info']['authenticated']:
        print("❌ User is not authenticated after login")
        return False
    
    print("✅ User is properly authenticated")
    
    # Now try the sync endpoint
    # First, get a page with CSRF token
    sync_page_url = urljoin(BASE_URL, '/clubs/sync/lotto/')
    response = session.get(sync_page_url)
    
    if response.status_code != 200:
        print(f"❌ Could not access sync page. Status: {response.status_code}")
        return False
    
    # Extract CSRF token from the page
    csrf_token = None
    for line in response.text.split('\n'):
        if "csrf_token" in line and "'" in line:
            try:
                csrf_token = line.split("'")[1]
                break
            except:
                continue
    
    if not csrf_token:
        # Try alternative method
        for line in response.text.split('\n'):
            if 'csrfmiddlewaretoken' in line and 'value=' in line:
                csrf_token = line.split('value="')[1].split('"')[0]
                break
    
    if not csrf_token:
        print("❌ Could not extract CSRF token from sync page")
        return False
    
    print(f"✅ CSRF token for sync: {csrf_token[:20]}...")
    
    # Test the sync endpoint with authentication
    headers = {
        'X-CSRFToken': csrf_token,
        'Content-Type': 'application/json',
        'Referer': sync_page_url
    }
    
    print("\n5️⃣ Testing authenticated sync endpoint...")
    response = session.post(sync_url, json={}, headers=headers)
    print(f"Authenticated sync status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Sync endpoint accessible! Success: {result.get('success')}")
        if not result.get('success'):
            print(f"Sync failed with error: {result.get('error')}")
            print(f"Error code: {result.get('error_code')}")
    else:
        print(f"❌ Sync endpoint returned {response.status_code}")
        try:
            error_data = response.json()
            print(f"Error: {error_data}")
        except:
            print(f"Response text: {response.text[:200]}...")
        return False
    
    print("\n🎉 Authentication flow test completed successfully!")
    return True

if __name__ == '__main__':
    try:
        success = test_authentication_flow()
        exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        exit(1)