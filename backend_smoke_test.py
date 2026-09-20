#!/usr/bin/env python3
"""
Runtime smoke test for Chatly AI Messenger after startup restoration.
Tests basic backend health and read-only authenticated endpoints.
"""

import requests
import json
import sys
import re

# Configuration
BACKEND_URL = "https://e98149bb-9c03-4d9e-ac1e-7caaface0345.preview.emergentagent.com/api"
TEST_EMAIL = "demo@chatly.app"
TEST_PASSWORD = "Demo1234"

# Security patterns to check for leaks
SECURITY_PATTERNS = [
    r'Traceback',
    r'sk_[a-zA-Z0-9_-]+',  # API keys starting with sk_
    r'tvly[a-zA-Z0-9_-]+',  # Tavily keys
    r'sk-emergent',
    r'ek_[a-zA-Z0-9_-]+',  # Email keys
    r'MONGO_URL',
    r'JWT_SECRET',
    r'private_key',
    r'service_account',
]

def check_security_leaks(response_text, test_name):
    """Check if response contains any security-sensitive information."""
    leaks = []
    for pattern in SECURITY_PATTERNS:
        if re.search(pattern, response_text, re.IGNORECASE):
            leaks.append(pattern)
    
    if leaks:
        print(f"  ❌ SECURITY LEAK in {test_name}: Found patterns: {', '.join(leaks)}")
        return False
    return True

def test_backend_health():
    """Test 1: Backend health check."""
    print("\n🔍 Test 1: Backend Health Check")
    try:
        # Try a simple endpoint that doesn't require auth
        response = requests.get(f"{BACKEND_URL}/", timeout=10)
        print(f"  Status: {response.status_code}")
        
        if response.status_code in [200, 404]:  # 404 is ok, means server is responding
            print("  ✅ Backend is responding")
            return True
        else:
            print(f"  ⚠️ Unexpected status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Backend not reachable: {e}")
        return False

def test_login():
    """Test 2: Login with demo credentials."""
    print("\n🔍 Test 2: Login (POST /api/auth/login)")
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=10
        )
        
        print(f"  Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"  ❌ Login failed: {response.text[:200]}")
            return None
        
        data = response.json()
        
        # Check for security leaks
        if not check_security_leaks(response.text, "login"):
            return None
        
        # Verify response structure
        if "token" not in data:
            print(f"  ❌ No token in response")
            return None
        
        if "user" not in data:
            print(f"  ⚠️ No user object in response")
        
        print(f"  ✅ Login successful")
        print(f"  Token: {data['token'][:20]}...")
        if "user" in data:
            print(f"  User: {data['user'].get('email', 'N/A')}")
        
        return data["token"]
        
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Request failed: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"  ❌ Invalid JSON response: {e}")
        return None

def test_auth_me(token):
    """Test 3: GET /api/auth/me."""
    print("\n🔍 Test 3: Get Current User (GET /api/auth/me)")
    try:
        response = requests.get(
            f"{BACKEND_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        print(f"  Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"  ❌ Request failed: {response.text[:200]}")
            return False
        
        data = response.json()
        
        # Check for security leaks
        if not check_security_leaks(response.text, "auth/me"):
            return False
        
        # Verify response structure
        if "email" not in data:
            print(f"  ⚠️ No email in response")
        
        print(f"  ✅ GET /api/auth/me successful")
        print(f"  Email: {data.get('email', 'N/A')}")
        print(f"  Name: {data.get('name', 'N/A')}")
        print(f"  User ID: {data.get('id', 'N/A')}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Request failed: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"  ❌ Invalid JSON response: {e}")
        return False

def test_get_chats(token):
    """Test 4: GET /api/chats."""
    print("\n🔍 Test 4: Get Chats (GET /api/chats)")
    try:
        response = requests.get(
            f"{BACKEND_URL}/chats",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        print(f"  Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"  ❌ Request failed: {response.text[:200]}")
            return False
        
        data = response.json()
        
        # Check for security leaks
        if not check_security_leaks(response.text, "chats"):
            return False
        
        # Verify response structure
        if not isinstance(data, list):
            print(f"  ⚠️ Response is not a list")
        
        print(f"  ✅ GET /api/chats successful")
        print(f"  Number of chats: {len(data) if isinstance(data, list) else 'N/A'}")
        
        if isinstance(data, list) and len(data) > 0:
            print(f"  First chat ID: {data[0].get('id', 'N/A')}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Request failed: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"  ❌ Invalid JSON response: {e}")
        return False

def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("🚀 Chatly Backend Runtime Smoke Test")
    print("=" * 60)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test Account: {TEST_EMAIL}")
    
    results = {
        "backend_health": False,
        "login": False,
        "auth_me": False,
        "get_chats": False,
    }
    
    # Test 1: Backend health
    results["backend_health"] = test_backend_health()
    
    if not results["backend_health"]:
        print("\n❌ Backend health check failed. Stopping tests.")
        sys.exit(1)
    
    # Test 2: Login
    token = test_login()
    results["login"] = token is not None
    
    if not token:
        print("\n❌ Login failed. Cannot proceed with authenticated tests.")
        sys.exit(1)
    
    # Test 3: GET /api/auth/me
    results["auth_me"] = test_auth_me(token)
    
    # Test 4: GET /api/chats
    results["get_chats"] = test_get_chats(token)
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("✅ All smoke tests PASSED")
        sys.exit(0)
    else:
        print("❌ Some smoke tests FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
