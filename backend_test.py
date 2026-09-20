#!/usr/bin/env python3
"""
Firebase Admin Integration Smoke Test
Tests Firebase Admin SDK integration after credential replacement.
Does NOT create/delete/modify app data - read-only smoke tests only.
"""
import requests
import sys
import os
from pathlib import Path

# Backend URL from frontend/.env
BACKEND_URL = "https://e98149bb-9c03-4d9e-ac1e-7caaface0345.preview.emergentagent.com/api"

# Test credentials from test_credentials.md
DEMO_EMAIL = "demo@chatly.app"
DEMO_PASSWORD = "Demo1234"

# Expected values
EXPECTED_BUCKET = "chatlyai-12478.firebasestorage.app"
EXPECTED_UID = "user_demo_chatly"

# Test results
passed = 0
failed = 0
test_results = []

def log_test(name, success, details=""):
    global passed, failed
    if success:
        passed += 1
        status = "✅ PASS"
    else:
        failed += 1
        status = "❌ FAIL"
    msg = f"{status}: {name}"
    if details:
        msg += f" - {details}"
    test_results.append(msg)
    print(msg)

def check_no_secrets(response_text, test_name):
    """Check that response doesn't contain secrets or stack traces"""
    secrets = ["Traceback", "sk_", "tvly", "sk-emergent", "ek_", "MONGO_URL", 
               "JWT_SECRET", "private_key", "service_account"]
    found = []
    for secret in secrets:
        if secret in response_text:
            found.append(secret)
    
    if found:
        log_test(f"{test_name} - No secrets exposed", False, f"Found: {', '.join(found)}")
        return False
    else:
        log_test(f"{test_name} - No secrets exposed", True)
        return True

def test_firebase_status():
    """Test GET /api/firebase/status"""
    print("\n=== Test 1: Firebase Status Endpoint ===")
    try:
        resp = requests.get(f"{BACKEND_URL}/firebase/status", timeout=10)
        
        # Check status code
        if resp.status_code == 200:
            log_test("GET /api/firebase/status returns 200", True)
        else:
            log_test("GET /api/firebase/status returns 200", False, f"Got {resp.status_code}")
            return
        
        # Check response structure
        data = resp.json()
        
        # Check ready=true
        if data.get("ready") == True:
            log_test("Firebase status ready=true", True)
        else:
            log_test("Firebase status ready=true", False, f"Got ready={data.get('ready')}")
        
        # Check error=null
        if data.get("error") is None:
            log_test("Firebase status error=null", True)
        else:
            log_test("Firebase status error=null", False, f"Got error={data.get('error')}")
        
        # Check correct bucket
        if data.get("bucket") == EXPECTED_BUCKET:
            log_test(f"Firebase status bucket={EXPECTED_BUCKET}", True)
        else:
            log_test(f"Firebase status bucket={EXPECTED_BUCKET}", False, 
                    f"Got bucket={data.get('bucket')}")
        
        # Check no secrets exposed
        check_no_secrets(resp.text, "Firebase status")
        
    except Exception as e:
        log_test("GET /api/firebase/status", False, str(e))

def test_demo_login():
    """Test authenticated demo login still works"""
    print("\n=== Test 2: Demo Login ===")
    try:
        resp = requests.post(
            f"{BACKEND_URL}/auth/login",
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
            timeout=10
        )
        
        if resp.status_code == 200:
            log_test("Demo login returns 200", True)
            data = resp.json()
            token = data.get("token")
            if token:
                log_test("Demo login returns token", True)
                return token
            else:
                log_test("Demo login returns token", False, "No token in response")
                return None
        else:
            log_test("Demo login returns 200", False, f"Got {resp.status_code}: {resp.text}")
            return None
            
    except Exception as e:
        log_test("Demo login", False, str(e))
        return None

def test_firebase_custom_token(token):
    """Test GET /api/auth/firebase-token"""
    print("\n=== Test 3: Firebase Custom Token ===")
    if not token:
        log_test("GET /api/auth/firebase-token", False, "No auth token available")
        return
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{BACKEND_URL}/auth/firebase-token", headers=headers, timeout=10)
        
        if resp.status_code == 200:
            log_test("GET /api/auth/firebase-token returns 200", True)
        else:
            log_test("GET /api/auth/firebase-token returns 200", False, 
                    f"Got {resp.status_code}: {resp.text}")
            return
        
        data = resp.json()
        
        # Check firebase_token is non-empty
        firebase_token = data.get("firebase_token")
        if firebase_token and len(firebase_token) > 0:
            log_test("Firebase custom token is non-empty", True)
        else:
            log_test("Firebase custom token is non-empty", False, 
                    f"Got token: {firebase_token}")
        
        # Check uid matches expected
        uid = data.get("uid")
        if uid == EXPECTED_UID:
            log_test(f"Firebase token uid={EXPECTED_UID}", True)
        else:
            log_test(f"Firebase token uid={EXPECTED_UID}", False, f"Got uid={uid}")
        
        # Check no secrets exposed
        check_no_secrets(resp.text, "Firebase custom token")
        
    except Exception as e:
        log_test("GET /api/auth/firebase-token", False, str(e))

def test_invalid_firebase_token():
    """Test invalid Firebase ID token returns safe 401 (not 500)"""
    print("\n=== Test 4: Invalid Firebase ID Token ===")
    try:
        resp = requests.post(
            f"{BACKEND_URL}/auth/firebase",
            json={"id_token": "invalid.token.here"},
            timeout=10
        )
        
        # Should return 401, not 500
        if resp.status_code == 401:
            log_test("Invalid Firebase ID token returns 401", True)
        elif resp.status_code == 500:
            log_test("Invalid Firebase ID token returns 401 (not 500)", False, 
                    "Got 500 - server error not handled")
        else:
            log_test("Invalid Firebase ID token returns 401", False, 
                    f"Got {resp.status_code}")
        
        # Check response is user-safe (no stack traces)
        check_no_secrets(resp.text, "Invalid Firebase token")
        
    except Exception as e:
        log_test("Invalid Firebase ID token", False, str(e))

def test_direct_admin_sdk():
    """Test direct Admin SDK can obtain Storage bucket and read Firestore"""
    print("\n=== Test 5: Direct Admin SDK Access ===")
    try:
        # Import firebase_service from backend
        sys.path.insert(0, str(Path(__file__).parent / "backend"))
        import firebase_service as fb
        
        # Test 1: Get Storage bucket handle
        try:
            bucket = fb.get_bucket()
            if bucket and bucket.name == EXPECTED_BUCKET:
                log_test(f"Admin SDK obtains Storage bucket {EXPECTED_BUCKET}", True)
            else:
                log_test(f"Admin SDK obtains Storage bucket {EXPECTED_BUCKET}", False, 
                        f"Got bucket: {bucket.name if bucket else None}")
        except Exception as e:
            log_test("Admin SDK obtains Storage bucket", False, str(e))
        
        # Test 2: Read Firestore users/user_demo_chatly
        try:
            db = fb.get_db()
            doc_ref = db.collection("users").document(EXPECTED_UID)
            doc = doc_ref.get()
            if doc.exists:
                log_test(f"Admin SDK reads Firestore users/{EXPECTED_UID}", True)
                data = doc.to_dict()
                # Verify it has expected fields
                if data.get("user_id") == EXPECTED_UID:
                    log_test(f"Firestore doc has correct user_id", True)
                else:
                    log_test(f"Firestore doc has correct user_id", False, 
                            f"Got user_id={data.get('user_id')}")
            else:
                log_test(f"Admin SDK reads Firestore users/{EXPECTED_UID}", False, 
                        "Document does not exist")
        except Exception as e:
            log_test("Admin SDK reads Firestore", False, str(e))
            
    except Exception as e:
        log_test("Direct Admin SDK access", False, str(e))

def test_auth_me(token):
    """Test GET /api/auth/me still returns 200"""
    print("\n=== Test 6: Auth Me Endpoint ===")
    if not token:
        log_test("GET /api/auth/me", False, "No auth token available")
        return
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{BACKEND_URL}/auth/me", headers=headers, timeout=10)
        
        if resp.status_code == 200:
            log_test("GET /api/auth/me returns 200", True)
        else:
            log_test("GET /api/auth/me returns 200", False, 
                    f"Got {resp.status_code}: {resp.text}")
        
        # Check no secrets exposed
        check_no_secrets(resp.text, "Auth me")
        
    except Exception as e:
        log_test("GET /api/auth/me", False, str(e))

def test_chats(token):
    """Test GET /api/chats still returns 200"""
    print("\n=== Test 7: Chats Endpoint ===")
    if not token:
        log_test("GET /api/chats", False, "No auth token available")
        return
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{BACKEND_URL}/chats", headers=headers, timeout=10)
        
        if resp.status_code == 200:
            log_test("GET /api/chats returns 200", True)
        else:
            log_test("GET /api/chats returns 200", False, 
                    f"Got {resp.status_code}: {resp.text}")
        
        # Check no secrets exposed
        check_no_secrets(resp.text, "Chats")
        
    except Exception as e:
        log_test("GET /api/chats", False, str(e))

def main():
    print("=" * 70)
    print("Firebase Admin Integration Smoke Test")
    print("=" * 70)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test User: {DEMO_EMAIL}")
    print("=" * 70)
    
    # Run tests
    test_firebase_status()
    
    token = test_demo_login()
    
    test_firebase_custom_token(token)
    
    test_invalid_firebase_token()
    
    test_direct_admin_sdk()
    
    test_auth_me(token)
    
    test_chats(token)
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for result in test_results:
        print(result)
    print("=" * 70)
    print(f"TOTAL: {passed} passed, {failed} failed out of {passed + failed} tests")
    print("=" * 70)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n✅ All Firebase Admin integration tests PASSED")
        sys.exit(0)

if __name__ == "__main__":
    main()
