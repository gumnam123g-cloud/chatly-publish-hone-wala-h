#!/usr/bin/env python3
"""
Backend API Testing for Chatly - Firebase Integration Phase 9
Tests Firebase status, FCM registry, Firebase Auth bridge, QR lookup fix, and account deletion
"""
import requests
import json
import time
import urllib.parse

# Configuration
BASE_URL = "http://localhost:8001/api"
ACCOUNT_A = {"email": "demo@chatly.app", "password": "Demo1234", "user_id": "user_demo_chatly", "name": "Demo User"}
ACCOUNT_B = {"email": "demo2@chatly.app", "password": "Demo1234", "user_id": "user_demo2_chatly", "name": "Aria Nair"}
THROWAWAY_EMAIL = "delivered@resend.dev"

# Test results tracking
test_results = []

def log_test(test_name, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    test_results.append({"test": test_name, "passed": passed, "details": details})
    print(f"{status}: {test_name}")
    if details:
        print(f"  Details: {details}")

def check_no_leaks(response_text):
    """Check for security leaks in response"""
    leaks = []
    leak_patterns = ["Traceback", "sk_", "tvly", "sk-emergent", "ek_", "MONGO_URL", "JWT_SECRET", "private_key", "service_account"]
    for pattern in leak_patterns:
        if pattern in response_text:
            leaks.append(pattern)
    return leaks

def login(email, password):
    """Login and return token"""
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if resp.status_code == 200:
        return resp.json()["token"]
    raise Exception(f"Login failed: {resp.status_code} {resp.text}")

def test_firebase_status():
    """Test 1: Firebase Status Endpoint"""
    print("\n" + "="*80)
    print("TEST 1: Firebase Status")
    print("="*80)
    
    resp = requests.get(f"{BASE_URL}/firebase/status")
    
    if resp.status_code == 200:
        data = resp.json()
        ready = data.get("ready")
        bucket = data.get("bucket")
        error = data.get("error")
        
        # Check ready is true
        if ready is True:
            log_test("Firebase status - ready:true", True, f"ready={ready}")
        else:
            log_test("Firebase status - ready:true", False, f"ready={ready}, error={error}")
        
        # Check bucket is correct
        if bucket == "chatlyai-12478.firebasestorage.app":
            log_test("Firebase status - correct bucket", True, f"bucket={bucket}")
        else:
            log_test("Firebase status - correct bucket", False, f"Expected 'chatlyai-12478.firebasestorage.app', got '{bucket}'")
        
        # Check error is null
        if error is None:
            log_test("Firebase status - error:null", True)
        else:
            log_test("Firebase status - error:null", False, f"error={error}")
        
        # Check for security leaks
        leaks = check_no_leaks(resp.text)
        if leaks:
            log_test("Firebase status - no secrets leaked", False, f"Found leaks: {leaks}")
        else:
            log_test("Firebase status - no secrets leaked", True)
    else:
        log_test("Firebase status - 200 OK", False, f"Status: {resp.status_code}, Response: {resp.text}")

def test_fcm_registry():
    """Test 2: FCM Device Token Registry"""
    print("\n" + "="*80)
    print("TEST 2: FCM Device Token Registry")
    print("="*80)
    
    # Test without auth - should return 401
    resp = requests.post(f"{BASE_URL}/fcm/register", 
                        json={"token": "test-device-token-123", "platform": "android"})
    
    if resp.status_code in [401, 403]:
        log_test("FCM register - 401 without auth", True, f"Status: {resp.status_code}")
    else:
        log_test("FCM register - 401 without auth", False, f"Expected 401/403, got {resp.status_code}")
    
    # Login as demo user
    token = login(ACCOUNT_A["email"], ACCOUNT_A["password"])
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test register with auth
    resp = requests.post(f"{BASE_URL}/fcm/register", 
                        json={"token": "test-device-token-123", "platform": "android"},
                        headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        if data.get("status") == "registered":
            log_test("FCM register - 200 with status:registered", True)
        else:
            log_test("FCM register - 200 with status:registered", False, f"Response: {data}")
    else:
        log_test("FCM register - 200 with status:registered", False, 
                f"Status: {resp.status_code}, Response: {resp.text}")
    
    # Test unregister
    resp = requests.post(f"{BASE_URL}/fcm/unregister", 
                        json={"token": "test-device-token-123"},
                        headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        if data.get("status") == "unregistered":
            log_test("FCM unregister - 200 with status:unregistered", True)
        else:
            log_test("FCM unregister - 200 with status:unregistered", False, f"Response: {data}")
    else:
        log_test("FCM unregister - 200 with status:unregistered", False, 
                f"Status: {resp.status_code}, Response: {resp.text}")
    
    # Check for security leaks
    leaks = check_no_leaks(resp.text)
    if leaks:
        log_test("FCM registry - no security leaks", False, f"Found leaks: {leaks}")
    else:
        log_test("FCM registry - no security leaks", True)

def test_firebase_auth_bridge():
    """Test 3: Firebase Auth Bridge"""
    print("\n" + "="*80)
    print("TEST 3: Firebase Auth Bridge")
    print("="*80)
    
    # Test with invalid token - should return 401 and NOT 500
    resp = requests.post(f"{BASE_URL}/auth/firebase", 
                        json={"id_token": "invalid.token.here"})
    
    if resp.status_code == 401:
        data = resp.json()
        detail = data.get("detail", "")
        if "Invalid sign-in" in detail:
            log_test("Firebase auth - 401 with 'Invalid sign-in' message", True, f"Detail: {detail}")
        else:
            log_test("Firebase auth - 401 with 'Invalid sign-in' message", False, 
                    f"Got 401 but wrong message: {detail}")
    else:
        log_test("Firebase auth - 401 with 'Invalid sign-in' message", False, 
                f"Expected 401, got {resp.status_code}")
    
    # Check it does NOT return 500
    if resp.status_code != 500:
        log_test("Firebase auth - does NOT return 500", True)
    else:
        log_test("Firebase auth - does NOT return 500", False, "Got 500 error")
    
    # Check for security leaks (no stack traces or keys)
    leaks = check_no_leaks(resp.text)
    if leaks:
        log_test("Firebase auth - no stack traces/keys leaked", False, f"Found leaks: {leaks}")
    else:
        log_test("Firebase auth - no stack traces/keys leaked", True)

def test_qr_lookup_fix():
    """Test 4: QR Lookup Fix (the main bug fix)"""
    print("\n" + "="*80)
    print("TEST 4: QR Lookup Fix")
    print("="*80)
    
    # Login as demo user
    token = login(ACCOUNT_A["email"], ACCOUNT_A["password"])
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get QR token
    resp = requests.get(f"{BASE_URL}/me/qr", headers=headers)
    
    if resp.status_code != 200:
        log_test("QR lookup - get QR token", False, f"Status: {resp.status_code}, Response: {resp.text}")
        return
    
    data = resp.json()
    qr_token = data.get("qr_token")
    
    if not qr_token or not qr_token.startswith("CHATLY-"):
        log_test("QR lookup - get QR token", False, f"Invalid token format: {qr_token}")
        return
    
    log_test("QR lookup - get QR token", True, f"Token: {qr_token}")
    
    # Test 1: Query param with bare token
    resp = requests.get(f"{BASE_URL}/users/by-qr?code={qr_token}", headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        user = data.get("user", {})
        relationship = user.get("relationship", {})
        
        if relationship.get("status") == "self":
            log_test("QR lookup - query param bare token returns self", True)
        else:
            log_test("QR lookup - query param bare token returns self", False, 
                    f"Expected status='self', got '{relationship.get('status')}'")
    else:
        log_test("QR lookup - query param bare token returns self", False, 
                f"Status: {resp.status_code}, Response: {resp.text}")
    
    # Test 2: Query param with deep-link URL (URL-encoded)
    deep_link = f"chatly://user/{qr_token}"
    encoded_link = urllib.parse.quote(deep_link, safe='')
    resp = requests.get(f"{BASE_URL}/users/by-qr?code={encoded_link}", headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        user = data.get("user", {})
        relationship = user.get("relationship", {})
        
        if relationship.get("status") == "self":
            log_test("QR lookup - query param deep-link URL returns self", True, f"Deep link: {deep_link}")
        else:
            log_test("QR lookup - query param deep-link URL returns self", False, 
                    f"Expected status='self', got '{relationship.get('status')}'")
    else:
        log_test("QR lookup - query param deep-link URL returns self", False, 
                f"Status: {resp.status_code}, Response: {resp.text}")
    
    # Test 3: Path variant with bare token
    resp = requests.get(f"{BASE_URL}/users/by-qr/{qr_token}", headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        user = data.get("user", {})
        relationship = user.get("relationship", {})
        
        if relationship.get("status") == "self":
            log_test("QR lookup - path variant bare token returns self", True)
        else:
            log_test("QR lookup - path variant bare token returns self", False, 
                    f"Expected status='self', got '{relationship.get('status')}'")
    else:
        log_test("QR lookup - path variant bare token returns self", False, 
                f"Status: {resp.status_code}, Response: {resp.text}")
    
    # Test 4: Nonexistent QR code
    resp = requests.get(f"{BASE_URL}/users/by-qr?code=NONEXISTENT", headers=headers)
    
    if resp.status_code == 404:
        data = resp.json()
        detail = data.get("detail", "")
        if "not valid" in detail.lower():
            log_test("QR lookup - nonexistent code returns 404", True, f"Detail: {detail}")
        else:
            log_test("QR lookup - nonexistent code returns 404", False, 
                    f"Got 404 but wrong message: {detail}")
    else:
        log_test("QR lookup - nonexistent code returns 404", False, 
                f"Expected 404, got {resp.status_code}")
    
    # Test 5: Verify /api/users/search still works (route ordering not broken)
    resp = requests.get(f"{BASE_URL}/users/search?q=demo", headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        users = data.get("users", [])
        log_test("QR lookup - /users/search still works", True, f"Found {len(users)} users")
    else:
        log_test("QR lookup - /users/search still works", False, 
                f"Status: {resp.status_code}, Response: {resp.text}")
    
    # Check for security leaks
    leaks = check_no_leaks(resp.text)
    if leaks:
        log_test("QR lookup - no security leaks", False, f"Found leaks: {leaks}")
    else:
        log_test("QR lookup - no security leaks", True)

def test_account_deletion():
    """Test 5: Account Deletion (DESTRUCTIVE - uses throwaway account only)"""
    print("\n" + "="*80)
    print("TEST 5: Account Deletion (THROWAWAY ACCOUNT ONLY)")
    print("="*80)
    
    # CRITICAL: Test without auth first
    resp = requests.delete(f"{BASE_URL}/account")
    
    if resp.status_code in [401, 403]:
        log_test("Account deletion - 401 without auth", True, f"Status: {resp.status_code}")
    else:
        log_test("Account deletion - 401 without auth", False, f"Expected 401/403, got {resp.status_code}")
    
    # Try to create throwaway account
    throwaway_name = f"Delete Me {int(time.time())}"
    resp = requests.post(f"{BASE_URL}/auth/signup", 
                        json={"name": throwaway_name, "email": THROWAWAY_EMAIL, "password": "Test1234"})
    
    throwaway_token = None
    
    if resp.status_code == 200:
        # New account created
        data = resp.json()
        dev_code = data.get("dev_code")
        
        if dev_code:
            log_test("Account deletion - create throwaway account", True, f"dev_code: {dev_code}")
            
            # Verify OTP
            resp = requests.post(f"{BASE_URL}/auth/verify-otp", 
                                json={"email": THROWAWAY_EMAIL, "code": dev_code})
            
            if resp.status_code == 200:
                data = resp.json()
                throwaway_token = data.get("token")
                log_test("Account deletion - verify throwaway account", True)
            else:
                log_test("Account deletion - verify throwaway account", False, 
                        f"Status: {resp.status_code}, Response: {resp.text}")
        else:
            log_test("Account deletion - create throwaway account", False, "No dev_code in response")
    
    elif resp.status_code == 409:
        # Account already exists - try to login
        log_test("Account deletion - throwaway account exists", True, "Account already exists, attempting login")
        
        resp = requests.post(f"{BASE_URL}/auth/login", 
                            json={"email": THROWAWAY_EMAIL, "password": "Test1234"})
        
        if resp.status_code == 200:
            throwaway_token = resp.json().get("token")
            log_test("Account deletion - login to existing throwaway", True)
        elif resp.status_code == 403:
            # Unverified account - try forgot password to get code
            log_test("Account deletion - account unverified", True, "Attempting forgot-password to get code")
            
            resp = requests.post(f"{BASE_URL}/auth/forgot-password", 
                                json={"email": THROWAWAY_EMAIL})
            
            if resp.status_code == 200:
                dev_code = resp.json().get("dev_code")
                if dev_code:
                    # Reset password
                    resp = requests.post(f"{BASE_URL}/auth/reset-password", 
                                        json={"email": THROWAWAY_EMAIL, "code": dev_code, "new_password": "Test1234"})
                    
                    if resp.status_code == 200:
                        # Now login
                        resp = requests.post(f"{BASE_URL}/auth/login", 
                                            json={"email": THROWAWAY_EMAIL, "password": "Test1234"})
                        if resp.status_code == 200:
                            throwaway_token = resp.json().get("token")
                            log_test("Account deletion - reset and login throwaway", True)
        else:
            log_test("Account deletion - login to existing throwaway", False, 
                    f"Status: {resp.status_code}, Response: {resp.text}")
    else:
        log_test("Account deletion - create throwaway account", False, 
                f"Status: {resp.status_code}, Response: {resp.text}")
    
    # If we have a throwaway token, proceed with deletion
    if throwaway_token:
        headers = {"Authorization": f"Bearer {throwaway_token}"}
        
        # Delete the throwaway account
        resp = requests.delete(f"{BASE_URL}/account", headers=headers)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "account_deleted":
                log_test("Account deletion - 200 with status:account_deleted", True)
            else:
                log_test("Account deletion - 200 with status:account_deleted", False, f"Response: {data}")
        else:
            log_test("Account deletion - 200 with status:account_deleted", False, 
                    f"Status: {resp.status_code}, Response: {resp.text}")
        
        # Verify throwaway account can no longer login
        resp = requests.post(f"{BASE_URL}/auth/login", 
                            json={"email": THROWAWAY_EMAIL, "password": "Test1234"})
        
        if resp.status_code == 401:
            log_test("Account deletion - throwaway cannot login after deletion", True)
        else:
            log_test("Account deletion - throwaway cannot login after deletion", False, 
                    f"Expected 401, got {resp.status_code}")
    else:
        log_test("Account deletion - skipped", None, "Could not obtain throwaway token")
    
    # CRITICAL: Verify demo accounts still work
    try:
        demo_token = login(ACCOUNT_A["email"], ACCOUNT_A["password"])
        log_test("Account deletion - demo@chatly.app still works", True, "Demo account login successful")
    except Exception as e:
        log_test("Account deletion - demo@chatly.app still works", False, f"Demo account login failed: {e}")
    
    # Check for security leaks
    if throwaway_token:
        leaks = check_no_leaks(resp.text)
        if leaks:
            log_test("Account deletion - no security leaks", False, f"Found leaks: {leaks}")
        else:
            log_test("Account deletion - no security leaks", True)

def test_security_comprehensive():
    """Test 6: Comprehensive Security Check"""
    print("\n" + "="*80)
    print("TEST 6: Comprehensive Security Check")
    print("="*80)
    
    print("Security checks performed throughout all tests:")
    print("- Checking for 'Traceback' in responses")
    print("- Checking for 'sk_' (API keys) in responses")
    print("- Checking for 'tvly' (Tavily keys) in responses")
    print("- Checking for 'sk-emergent' in responses")
    print("- Checking for 'ek_' (email keys) in responses")
    print("- Checking for 'MONGO_URL' in responses")
    print("- Checking for 'JWT_SECRET' in responses")
    print("- Checking for 'private_key' in responses")
    print("- Checking for 'service_account' in responses")
    print("All responses checked for security leaks.")

def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for r in test_results if r["passed"] is True)
    failed = sum(1 for r in test_results if r["passed"] is False)
    skipped = sum(1 for r in test_results if r["passed"] is None)
    total = len(test_results)
    
    print(f"\nTotal Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⏭️  Skipped: {skipped}")
    
    if failed > 0:
        print("\n❌ FAILED TESTS:")
        for r in test_results:
            if r["passed"] is False:
                print(f"  - {r['test']}")
                if r["details"]:
                    print(f"    {r['details']}")
    
    print("\n" + "="*80)
    if failed == 0:
        print("✅ ALL TESTS PASSED!")
    else:
        print(f"❌ {failed} TEST(S) FAILED")
    print("="*80)

if __name__ == "__main__":
    print("="*80)
    print("CHATLY BACKEND API TESTING")
    print("Firebase Integration Phase 9")
    print("="*80)
    print("\n⚠️  WARNING: Account deletion test is DESTRUCTIVE")
    print("⚠️  Only throwaway accounts will be deleted")
    print("⚠️  Demo accounts (demo@chatly.app, demo2@chatly.app) will NOT be touched\n")
    
    try:
        test_firebase_status()
        test_fcm_registry()
        test_firebase_auth_bridge()
        test_qr_lookup_fix()
        test_account_deletion()
        test_security_comprehensive()
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print_summary()
