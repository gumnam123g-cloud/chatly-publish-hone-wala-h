#!/usr/bin/env python3
"""
Phase 5 Backend Testing for Chatly AI Messenger
Tests QR codes, public profiles, friend requests, status feature, chat themes, delete chat, and block
"""
import requests
import time
import sys
import base64
from typing import Dict, Any, Tuple

# Backend URL
BASE_URL = "https://chatly-mobile-1.preview.emergentagent.com/api"

# Test credentials
DEMO_EMAIL = "demo@chatly.app"
DEMO_PASSWORD = "Demo1234"
USER_B_EMAIL = "delivered@resend.dev"
USER_B_PASSWORD = "Test1234"
USER_B_NAME = "Test User B"

# Security check patterns
SECURITY_PATTERNS = ["Traceback", "sk_", "tvly", "sk-emergent", "MONGO_URL", "JWT_SECRET"]

class TestResult:
    def __init__(self):
        self.results = []
        self.security_issues = []
    
    def add(self, test_name: str, status_code: int, result: str, data: Any = None, notes: str = ""):
        self.results.append((test_name, status_code, result, data, notes))
    
    def check_security(self, response_text: str, step: str):
        for pattern in SECURITY_PATTERNS:
            if pattern in response_text:
                issue = f"SECURITY LEAK in {step}: Found '{pattern}' in response"
                self.security_issues.append(issue)
                print(f"  ⚠️  {issue}")

def login_user(email: str, password: str) -> Tuple[str, dict]:
    """Login and return token and user data"""
    print(f"\n🔐 Logging in as {email}...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=30)
    if resp.status_code != 200:
        print(f"  ❌ Login failed: {resp.status_code} - {resp.text}")
        return None, None
    data = resp.json()
    token = data.get("token")
    user = data.get("user")
    print(f"  ✅ Logged in as {user.get('name')} (user_id: {user.get('user_id')})")
    return token, user

def create_user_b(tr: TestResult) -> Tuple[str, dict]:
    """Create or login as user B for friend request testing"""
    print(f"\n👤 Setting up User B ({USER_B_EMAIL})...")
    
    # Try to login first
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": USER_B_EMAIL, "password": USER_B_PASSWORD}, timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✅ User B already exists, logged in")
        return data.get("token"), data.get("user")
    
    # Need to create account
    print(f"  📝 Creating new account for User B...")
    resp = requests.post(f"{BASE_URL}/auth/signup", json={
        "name": USER_B_NAME,
        "email": USER_B_EMAIL,
        "password": USER_B_PASSWORD
    }, timeout=30)
    tr.check_security(resp.text, "signup user B")
    
    if resp.status_code == 409:
        # Account exists but not verified, or already verified
        print(f"  ℹ️  Account exists (409), trying login...")
        resp = requests.post(f"{BASE_URL}/auth/login", json={"email": USER_B_EMAIL, "password": USER_B_PASSWORD}, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("token"), data.get("user")
        else:
            print(f"  ❌ Login failed after 409: {resp.status_code}")
            return None, None
    
    if resp.status_code != 200:
        print(f"  ❌ Signup failed: {resp.status_code} - {resp.text}")
        return None, None
    
    data = resp.json()
    dev_code = data.get("dev_code")
    if not dev_code:
        print(f"  ❌ No dev_code in signup response")
        return None, None
    
    print(f"  ✅ Signup successful, dev_code: {dev_code}")
    
    # Verify OTP
    print(f"  📧 Verifying OTP...")
    resp = requests.post(f"{BASE_URL}/auth/verify-otp", json={
        "email": USER_B_EMAIL,
        "code": dev_code
    }, timeout=30)
    tr.check_security(resp.text, "verify-otp user B")
    
    if resp.status_code != 200:
        print(f"  ❌ Verification failed: {resp.status_code} - {resp.text}")
        return None, None
    
    data = resp.json()
    print(f"  ✅ Account verified")
    return data.get("token"), data.get("user")

def test_qr_code(tr: TestResult, token_a: str, user_a: dict, token_b: str, user_b: dict):
    """Test 1: QR Code endpoints"""
    print("\n" + "="*80)
    print("TEST 1: QR CODE ENDPOINTS")
    print("="*80)
    
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    
    # 1.1: GET /api/me/qr (User A)
    print("\n1.1: GET /api/me/qr (User A)")
    resp = requests.get(f"{BASE_URL}/me/qr", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "me/qr user A")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        qr_token_a = data.get("qr_token")
        payload = data.get("payload")
        user_data = data.get("user")
        
        print(f"  qr_token: {qr_token_a}")
        print(f"  payload: {payload}")
        print(f"  user: {user_data.get('name') if user_data else None}")
        
        if qr_token_a and qr_token_a.startswith("CHATLY-") and payload and payload.startswith("chatly://user/"):
            tr.add("1.1: GET /api/me/qr (User A)", resp.status_code, "PASS", data, f"token: {qr_token_a[:20]}...")
            print("  ✅ PASS: QR token format correct")
        else:
            tr.add("1.1: GET /api/me/qr (User A)", resp.status_code, "FAIL", data, "Invalid format")
            print("  ❌ FAIL: Invalid QR token or payload format")
    else:
        tr.add("1.1: GET /api/me/qr (User A)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
        return
    
    # 1.2: GET /api/me/qr again (should be same token)
    print("\n1.2: GET /api/me/qr (User A - second call, should be identical)")
    resp2 = requests.get(f"{BASE_URL}/me/qr", headers=headers_a, timeout=30)
    tr.check_security(resp2.text, "me/qr user A second")
    
    if resp2.status_code == 200:
        data2 = resp2.json()
        qr_token_a2 = data2.get("qr_token")
        
        if qr_token_a == qr_token_a2:
            tr.add("1.2: GET /api/me/qr (permanence)", resp2.status_code, "PASS", data2, "Token unchanged")
            print(f"  ✅ PASS: Token is permanent (same as first call)")
        else:
            tr.add("1.2: GET /api/me/qr (permanence)", resp2.status_code, "FAIL", data2, "Token changed")
            print(f"  ❌ FAIL: Token changed! {qr_token_a} != {qr_token_a2}")
    else:
        tr.add("1.2: GET /api/me/qr (permanence)", resp2.status_code, "FAIL", resp2.text)
    
    # 1.3: GET /api/me/qr (User B - should have different token)
    print("\n1.3: GET /api/me/qr (User B - should be different from User A)")
    resp = requests.get(f"{BASE_URL}/me/qr", headers=headers_b, timeout=30)
    tr.check_security(resp.text, "me/qr user B")
    
    if resp.status_code == 200:
        data = resp.json()
        qr_token_b = data.get("qr_token")
        print(f"  qr_token: {qr_token_b}")
        
        if qr_token_b and qr_token_b != qr_token_a:
            tr.add("1.3: GET /api/me/qr (User B uniqueness)", resp.status_code, "PASS", data, "Unique token")
            print(f"  ✅ PASS: User B has different token")
        else:
            tr.add("1.3: GET /api/me/qr (User B uniqueness)", resp.status_code, "FAIL", data, "Not unique")
            print(f"  ❌ FAIL: Token not unique or missing")
    else:
        tr.add("1.3: GET /api/me/qr (User B uniqueness)", resp.status_code, "FAIL", resp.text)
    
    # 1.4: GET /api/users/by-qr/{qr_token_a} (User A's own token)
    print(f"\n1.4: GET /api/users/by-qr/{qr_token_a} (User A resolving own token)")
    resp = requests.get(f"{BASE_URL}/users/by-qr/{qr_token_a}", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "users/by-qr own token")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        user_data = data.get("user", {})
        relationship = user_data.get("relationship", {})
        rel_status = relationship.get("status")
        
        print(f"  user: {user_data.get('name')}")
        print(f"  relationship.status: {rel_status}")
        
        if rel_status == "self":
            tr.add("1.4: GET /api/users/by-qr (own token)", resp.status_code, "PASS", data, "status=self")
            print(f"  ✅ PASS: Own token returns relationship.status='self'")
        else:
            tr.add("1.4: GET /api/users/by-qr (own token)", resp.status_code, "FAIL", data, f"status={rel_status}")
            print(f"  ❌ FAIL: Expected status='self', got '{rel_status}'")
    else:
        tr.add("1.4: GET /api/users/by-qr (own token)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 1.5: GET /api/users/by-qr/INVALID
    print(f"\n1.5: GET /api/users/by-qr/INVALID (invalid token)")
    resp = requests.get(f"{BASE_URL}/users/by-qr/INVALID", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "users/by-qr invalid")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 404:
        tr.add("1.5: GET /api/users/by-qr (invalid)", resp.status_code, "PASS", resp.json(), "404 as expected")
        print(f"  ✅ PASS: Invalid token returns 404")
    else:
        tr.add("1.5: GET /api/users/by-qr (invalid)", resp.status_code, "FAIL", resp.text, "Expected 404")
        print(f"  ❌ FAIL: Expected 404, got {resp.status_code}")
    
    # Store tokens for later use
    return qr_token_a, qr_token_b

def test_public_profile(tr: TestResult, token_a: str, user_a: dict, token_b: str, user_b: dict):
    """Test 2: Public Profile + Relationship"""
    print("\n" + "="*80)
    print("TEST 2: PUBLIC PROFILE + RELATIONSHIP")
    print("="*80)
    
    headers_a = {"Authorization": f"Bearer {token_a}"}
    
    # 2.1: GET /api/users/{user_id} (User A viewing User B)
    print(f"\n2.1: GET /api/users/{user_b['user_id']} (User A viewing User B)")
    resp = requests.get(f"{BASE_URL}/users/{user_b['user_id']}", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "users/{user_id}")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        user_data = data.get("user", {})
        relationship = user_data.get("relationship", {})
        blocked_by_me = user_data.get("blocked_by_me")
        
        print(f"  user: {user_data.get('name')}")
        print(f"  relationship.status: {relationship.get('status')}")
        print(f"  blocked_by_me: {blocked_by_me}")
        
        if relationship.get("status") in ["self", "friends", "request_sent", "request_incoming", "none"]:
            tr.add("2.1: GET /api/users/{user_id}", resp.status_code, "PASS", data, f"status={relationship.get('status')}")
            print(f"  ✅ PASS: Valid relationship status")
        else:
            tr.add("2.1: GET /api/users/{user_id}", resp.status_code, "FAIL", data, "Invalid status")
            print(f"  ❌ FAIL: Invalid relationship status")
    else:
        tr.add("2.1: GET /api/users/{user_id}", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 2.2: GET /api/users/{bot_id} (should be friends with seeded bots)
    print(f"\n2.2: GET /api/users/bot_aman_gupta (should be friends with seeded bot)")
    resp = requests.get(f"{BASE_URL}/users/bot_aman_gupta", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "users/bot_id")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        user_data = data.get("user", {})
        relationship = user_data.get("relationship", {})
        rel_status = relationship.get("status")
        
        print(f"  user: {user_data.get('name')}")
        print(f"  relationship.status: {rel_status}")
        
        if rel_status == "friends":
            tr.add("2.2: GET /api/users/bot_id", resp.status_code, "PASS", data, "status=friends")
            print(f"  ✅ PASS: Demo user is friends with seeded bot")
        else:
            tr.add("2.2: GET /api/users/bot_id", resp.status_code, "FAIL", data, f"status={rel_status}")
            print(f"  ❌ FAIL: Expected status='friends', got '{rel_status}'")
    else:
        tr.add("2.2: GET /api/users/bot_id", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 2.3: GET /api/users/UNKNOWNID
    print(f"\n2.3: GET /api/users/UNKNOWNID (invalid user_id)")
    resp = requests.get(f"{BASE_URL}/users/UNKNOWNID", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "users/unknown")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 404:
        tr.add("2.3: GET /api/users/UNKNOWNID", resp.status_code, "PASS", resp.json(), "404 as expected")
        print(f"  ✅ PASS: Unknown user returns 404")
    else:
        tr.add("2.3: GET /api/users/UNKNOWNID", resp.status_code, "FAIL", resp.text, "Expected 404")
        print(f"  ❌ FAIL: Expected 404, got {resp.status_code}")
    
    # 2.4: Verify /api/users/search still works (not swallowed by /users/{user_id})
    print(f"\n2.4: GET /api/users/search?q=test (verify route not swallowed)")
    resp = requests.get(f"{BASE_URL}/users/search?q=test", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "users/search")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        users = data.get("users", [])
        tr.add("2.4: GET /api/users/search", resp.status_code, "PASS", data, f"{len(users)} users")
        print(f"  ✅ PASS: Search route works ({len(users)} users found)")
    else:
        tr.add("2.4: GET /api/users/search", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")

def test_friend_requests(tr: TestResult, token_a: str, user_a: dict, token_b: str, user_b: dict):
    """Test 3: Friend Request Flow"""
    print("\n" + "="*80)
    print("TEST 3: FRIEND REQUEST FLOW")
    print("="*80)
    
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    
    # 3.1: User A sends request to User B
    print(f"\n3.1: POST /api/contacts/request (User A -> User B)")
    resp = requests.post(f"{BASE_URL}/contacts/request", headers=headers_a, json={"to_id": user_b["user_id"]}, timeout=30)
    tr.check_security(resp.text, "contacts/request")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        status = data.get("status")
        print(f"  status: {status}")
        
        if status in ["pending", "already_contacts"]:
            tr.add("3.1: POST /api/contacts/request", resp.status_code, "PASS", data, f"status={status}")
            print(f"  ✅ PASS: Request sent (status={status})")
        else:
            tr.add("3.1: POST /api/contacts/request", resp.status_code, "FAIL", data, f"Unexpected status={status}")
            print(f"  ❌ FAIL: Unexpected status={status}")
    else:
        tr.add("3.1: POST /api/contacts/request", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 3.2: User A sends duplicate request (should still return pending)
    print(f"\n3.2: POST /api/contacts/request (duplicate, should return pending)")
    resp = requests.post(f"{BASE_URL}/contacts/request", headers=headers_a, json={"to_id": user_b["user_id"]}, timeout=30)
    tr.check_security(resp.text, "contacts/request duplicate")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        status = data.get("status")
        print(f"  status: {status}")
        
        if status in ["pending", "already_contacts"]:
            tr.add("3.2: POST /api/contacts/request (duplicate)", resp.status_code, "PASS", data, "No error")
            print(f"  ✅ PASS: Duplicate request handled (status={status})")
        else:
            tr.add("3.2: POST /api/contacts/request (duplicate)", resp.status_code, "FAIL", data, f"status={status}")
            print(f"  ❌ FAIL: Unexpected status={status}")
    else:
        tr.add("3.2: POST /api/contacts/request (duplicate)", resp.status_code, "FAIL", resp.text)
    
    # 3.3: User A tries to add self (should fail)
    print(f"\n3.3: POST /api/contacts/request (User A -> self, should fail)")
    resp = requests.post(f"{BASE_URL}/contacts/request", headers=headers_a, json={"to_id": user_a["user_id"]}, timeout=30)
    tr.check_security(resp.text, "contacts/request self")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 400:
        tr.add("3.3: POST /api/contacts/request (self)", resp.status_code, "PASS", resp.json(), "400 as expected")
        print(f"  ✅ PASS: Cannot add self (400)")
    else:
        tr.add("3.3: POST /api/contacts/request (self)", resp.status_code, "FAIL", resp.text, "Expected 400")
        print(f"  ❌ FAIL: Expected 400, got {resp.status_code}")
    
    # 3.4: User B lists incoming requests
    print(f"\n3.4: GET /api/contacts/requests (User B)")
    resp = requests.get(f"{BASE_URL}/contacts/requests", headers=headers_b, timeout=30)
    tr.check_security(resp.text, "contacts/requests")
    print(f"  Status: {resp.status_code}")
    
    request_id = None
    if resp.status_code == 200:
        data = resp.json()
        requests_list = data.get("requests", [])
        print(f"  requests: {len(requests_list)}")
        
        # Find request from User A
        for req in requests_list:
            if req.get("user_id") == user_a["user_id"]:
                request_id = req.get("request_id")
                print(f"  Found request from {req.get('name')} (request_id: {request_id})")
                break
        
        if request_id:
            tr.add("3.4: GET /api/contacts/requests", resp.status_code, "PASS", data, f"Found request_id")
            print(f"  ✅ PASS: Request from User A found")
        else:
            tr.add("3.4: GET /api/contacts/requests", resp.status_code, "FAIL", data, "Request not found")
            print(f"  ❌ FAIL: Request from User A not found")
    else:
        tr.add("3.4: GET /api/contacts/requests", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 3.5: User B views User A's profile (should show request_incoming)
    print(f"\n3.5: GET /api/users/{user_a['user_id']} (User B viewing User A)")
    resp = requests.get(f"{BASE_URL}/users/{user_a['user_id']}", headers=headers_b, timeout=30)
    tr.check_security(resp.text, "users/{user_id} with request")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        user_data = data.get("user", {})
        relationship = user_data.get("relationship", {})
        rel_status = relationship.get("status")
        rel_request_id = relationship.get("request_id")
        
        print(f"  relationship.status: {rel_status}")
        print(f"  relationship.request_id: {rel_request_id}")
        
        if rel_status == "request_incoming" and rel_request_id:
            tr.add("3.5: GET /api/users/{user_id} (request_incoming)", resp.status_code, "PASS", data, "status=request_incoming")
            print(f"  ✅ PASS: Relationship shows request_incoming with request_id")
        else:
            tr.add("3.5: GET /api/users/{user_id} (request_incoming)", resp.status_code, "FAIL", data, f"status={rel_status}")
            print(f"  ❌ FAIL: Expected request_incoming, got {rel_status}")
    else:
        tr.add("3.5: GET /api/users/{user_id} (request_incoming)", resp.status_code, "FAIL", resp.text)
    
    # 3.6: User B accepts request
    if request_id:
        print(f"\n3.6: POST /api/contacts/respond (User B accepts)")
        resp = requests.post(f"{BASE_URL}/contacts/respond", headers=headers_b, 
                           json={"request_id": request_id, "accept": True}, timeout=30)
        tr.check_security(resp.text, "contacts/respond accept")
        print(f"  Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status")
            print(f"  status: {status}")
            
            if status == "accepted":
                tr.add("3.6: POST /api/contacts/respond (accept)", resp.status_code, "PASS", data, "status=accepted")
                print(f"  ✅ PASS: Request accepted")
            else:
                tr.add("3.6: POST /api/contacts/respond (accept)", resp.status_code, "FAIL", data, f"status={status}")
                print(f"  ❌ FAIL: Expected status=accepted, got {status}")
        else:
            tr.add("3.6: POST /api/contacts/respond (accept)", resp.status_code, "FAIL", resp.text)
            print(f"  ❌ FAIL: {resp.text}")
        
        # 3.7: Verify both users now show "friends"
        print(f"\n3.7: Verify friendship (both users should show status=friends)")
        
        # User A views User B
        resp_a = requests.get(f"{BASE_URL}/users/{user_b['user_id']}", headers=headers_a, timeout=30)
        if resp_a.status_code == 200:
            data_a = resp_a.json()
            rel_a = data_a.get("user", {}).get("relationship", {}).get("status")
            print(f"  User A -> User B: {rel_a}")
        else:
            rel_a = None
        
        # User B views User A
        resp_b = requests.get(f"{BASE_URL}/users/{user_a['user_id']}", headers=headers_b, timeout=30)
        if resp_b.status_code == 200:
            data_b = resp_b.json()
            rel_b = data_b.get("user", {}).get("relationship", {}).get("status")
            print(f"  User B -> User A: {rel_b}")
        else:
            rel_b = None
        
        if rel_a == "friends" and rel_b == "friends":
            tr.add("3.7: Verify friendship", 200, "PASS", {"a_to_b": rel_a, "b_to_a": rel_b}, "Both friends")
            print(f"  ✅ PASS: Both users show status=friends")
        else:
            tr.add("3.7: Verify friendship", 200, "FAIL", {"a_to_b": rel_a, "b_to_a": rel_b}, "Not friends")
            print(f"  ❌ FAIL: Expected both friends, got A->B: {rel_a}, B->A: {rel_b}")
    else:
        print(f"\n3.6-3.7: SKIPPED (no request_id)")
        tr.add("3.6: POST /api/contacts/respond (accept)", 0, "SKIP", None, "No request_id")
        tr.add("3.7: Verify friendship", 0, "SKIP", None, "No request_id")

def test_status_feature(tr: TestResult, token_a: str, user_a: dict, token_b: str, user_b: dict):
    """Test 4: Status Feature"""
    print("\n" + "="*80)
    print("TEST 4: STATUS FEATURE")
    print("="*80)
    
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    
    # 4.1: Create text status
    print(f"\n4.1: POST /api/status (text status)")
    resp = requests.post(f"{BASE_URL}/status", headers=headers_a, json={
        "kind": "text",
        "text": "Hello from automated test!",
        "bg": "#FF5E00"
    }, timeout=30)
    tr.check_security(resp.text, "status create text")
    print(f"  Status: {resp.status_code}")
    
    status_id_text = None
    if resp.status_code == 200:
        data = resp.json()
        status_obj = data.get("status", {})
        status_id_text = status_obj.get("id")
        created_at = status_obj.get("created_at")
        expires_at = status_obj.get("expires_at")
        
        print(f"  id: {status_id_text}")
        print(f"  created_at: {created_at}")
        print(f"  expires_at: {expires_at}")
        
        if status_id_text and created_at and expires_at:
            tr.add("4.1: POST /api/status (text)", resp.status_code, "PASS", data, "Status created")
            print(f"  ✅ PASS: Text status created")
        else:
            tr.add("4.1: POST /api/status (text)", resp.status_code, "FAIL", data, "Missing fields")
            print(f"  ❌ FAIL: Missing required fields")
    else:
        tr.add("4.1: POST /api/status (text)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 4.2: Create text status with empty text (should fail)
    print(f"\n4.2: POST /api/status (empty text, should fail)")
    resp = requests.post(f"{BASE_URL}/status", headers=headers_a, json={
        "kind": "text",
        "text": ""
    }, timeout=30)
    tr.check_security(resp.text, "status create empty")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 400:
        tr.add("4.2: POST /api/status (empty text)", resp.status_code, "PASS", resp.json(), "400 as expected")
        print(f"  ✅ PASS: Empty text rejected (400)")
    else:
        tr.add("4.2: POST /api/status (empty text)", resp.status_code, "FAIL", resp.text, "Expected 400")
        print(f"  ❌ FAIL: Expected 400, got {resp.status_code}")
    
    # 4.3: Create image status with valid base64
    print(f"\n4.3: POST /api/status (image status with base64)")
    # Tiny 1x1 red PNG
    tiny_png_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    
    resp = requests.post(f"{BASE_URL}/status", headers=headers_a, json={
        "kind": "image",
        "media_b64": tiny_png_b64
    }, timeout=30)
    tr.check_security(resp.text, "status create image")
    print(f"  Status: {resp.status_code}")
    
    status_id_image = None
    if resp.status_code == 200:
        data = resp.json()
        status_obj = data.get("status", {})
        status_id_image = status_obj.get("id")
        
        print(f"  id: {status_id_image}")
        tr.add("4.3: POST /api/status (image)", resp.status_code, "PASS", data, "Image status created")
        print(f"  ✅ PASS: Image status created")
    else:
        tr.add("4.3: POST /api/status (image)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 4.4: Create image status with invalid base64 (should fail)
    print(f"\n4.4: POST /api/status (invalid image, should fail)")
    resp = requests.post(f"{BASE_URL}/status", headers=headers_a, json={
        "kind": "image",
        "media_b64": "notadatauri"
    }, timeout=30)
    tr.check_security(resp.text, "status create invalid image")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 400:
        tr.add("4.4: POST /api/status (invalid image)", resp.status_code, "PASS", resp.json(), "400 as expected")
        print(f"  ✅ PASS: Invalid image rejected (400)")
    else:
        tr.add("4.4: POST /api/status (invalid image)", resp.status_code, "FAIL", resp.text, "Expected 400")
        print(f"  ❌ FAIL: Expected 400, got {resp.status_code}")
    
    # 4.5: GET /api/status/feed (User A)
    print(f"\n4.5: GET /api/status/feed (User A)")
    resp = requests.get(f"{BASE_URL}/status/feed", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "status/feed")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        mine = data.get("mine", [])
        mine_user = data.get("mine_user", {})
        others = data.get("others", [])
        
        print(f"  mine: {len(mine)} statuses")
        print(f"  mine_user: {mine_user.get('name')}")
        print(f"  others: {len(others)} groups")
        
        # Check if our created statuses are in mine
        found_text = any(s.get("id") == status_id_text for s in mine)
        found_image = any(s.get("id") == status_id_image for s in mine)
        
        print(f"  Found text status: {found_text}")
        print(f"  Found image status: {found_image}")
        
        if mine and mine_user:
            tr.add("4.5: GET /api/status/feed", resp.status_code, "PASS", data, f"{len(mine)} mine, {len(others)} others")
            print(f"  ✅ PASS: Feed returned")
        else:
            tr.add("4.5: GET /api/status/feed", resp.status_code, "FAIL", data, "Missing data")
            print(f"  ❌ FAIL: Missing mine or mine_user")
    else:
        tr.add("4.5: GET /api/status/feed", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 4.6: GET /api/status/feed (User B - should see User A's statuses if friends)
    print(f"\n4.6: GET /api/status/feed (User B - should see User A's statuses)")
    resp = requests.get(f"{BASE_URL}/status/feed", headers=headers_b, timeout=30)
    tr.check_security(resp.text, "status/feed user B")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        others = data.get("others", [])
        
        print(f"  others: {len(others)} groups")
        
        # Find User A's group
        user_a_group = None
        for group in others:
            if group.get("user", {}).get("user_id") == user_a["user_id"]:
                user_a_group = group
                break
        
        if user_a_group:
            has_unseen = user_a_group.get("has_unseen")
            statuses = user_a_group.get("statuses", [])
            print(f"  Found User A's group: {len(statuses)} statuses, has_unseen={has_unseen}")
            
            if has_unseen:
                tr.add("4.6: GET /api/status/feed (User B)", resp.status_code, "PASS", data, "has_unseen=true")
                print(f"  ✅ PASS: User A's statuses visible with has_unseen=true")
            else:
                tr.add("4.6: GET /api/status/feed (User B)", resp.status_code, "PARTIAL", data, "has_unseen=false")
                print(f"  ⚠️  PARTIAL: User A's statuses visible but has_unseen=false")
        else:
            tr.add("4.6: GET /api/status/feed (User B)", resp.status_code, "FAIL", data, "User A not in feed")
            print(f"  ❌ FAIL: User A's statuses not in feed (may not be friends)")
    else:
        tr.add("4.6: GET /api/status/feed (User B)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 4.7: POST /api/status/{id}/view (User B views User A's status)
    if status_id_text:
        print(f"\n4.7: POST /api/status/{status_id_text}/view (User B)")
        resp = requests.post(f"{BASE_URL}/status/{status_id_text}/view", headers=headers_b, timeout=30)
        tr.check_security(resp.text, "status/view")
        print(f"  Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            ok = data.get("ok")
            
            if ok:
                tr.add("4.7: POST /api/status/{id}/view", resp.status_code, "PASS", data, "ok=true")
                print(f"  ✅ PASS: Status viewed")
                
                # Verify seen=true in feed
                print(f"  Verifying seen=true in feed...")
                resp_feed = requests.get(f"{BASE_URL}/status/feed", headers=headers_b, timeout=30)
                if resp_feed.status_code == 200:
                    feed_data = resp_feed.json()
                    others = feed_data.get("others", [])
                    for group in others:
                        if group.get("user", {}).get("user_id") == user_a["user_id"]:
                            for status in group.get("statuses", []):
                                if status.get("id") == status_id_text:
                                    seen = status.get("seen")
                                    print(f"    Status seen={seen}")
                                    if seen:
                                        print(f"    ✅ Status marked as seen in feed")
                                    else:
                                        print(f"    ⚠️  Status not marked as seen in feed")
                                    break
            else:
                tr.add("4.7: POST /api/status/{id}/view", resp.status_code, "FAIL", data, "ok=false")
                print(f"  ❌ FAIL: ok=false")
        else:
            tr.add("4.7: POST /api/status/{id}/view", resp.status_code, "FAIL", resp.text)
            print(f"  ❌ FAIL: {resp.text}")
    else:
        print(f"\n4.7: SKIPPED (no status_id)")
        tr.add("4.7: POST /api/status/{id}/view", 0, "SKIP", None, "No status_id")
    
    # 4.8: DELETE /api/status/{id} (User A deletes own status)
    if status_id_text:
        print(f"\n4.8: DELETE /api/status/{status_id_text} (User A deletes own)")
        resp = requests.delete(f"{BASE_URL}/status/{status_id_text}", headers=headers_a, timeout=30)
        tr.check_security(resp.text, "status delete own")
        print(f"  Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status")
            
            if status == "deleted":
                tr.add("4.8: DELETE /api/status/{id} (own)", resp.status_code, "PASS", data, "status=deleted")
                print(f"  ✅ PASS: Status deleted")
            else:
                tr.add("4.8: DELETE /api/status/{id} (own)", resp.status_code, "FAIL", data, f"status={status}")
                print(f"  ❌ FAIL: Expected status=deleted, got {status}")
        else:
            tr.add("4.8: DELETE /api/status/{id} (own)", resp.status_code, "FAIL", resp.text)
            print(f"  ❌ FAIL: {resp.text}")
    else:
        print(f"\n4.8: SKIPPED (no status_id)")
        tr.add("4.8: DELETE /api/status/{id} (own)", 0, "SKIP", None, "No status_id")
    
    # 4.9: DELETE /api/status/{id} (User B tries to delete User A's status - should fail)
    if status_id_image:
        print(f"\n4.9: DELETE /api/status/{status_id_image} (User B tries to delete User A's)")
        resp = requests.delete(f"{BASE_URL}/status/{status_id_image}", headers=headers_b, timeout=30)
        tr.check_security(resp.text, "status delete other")
        print(f"  Status: {resp.status_code}")
        
        if resp.status_code == 404:
            tr.add("4.9: DELETE /api/status/{id} (other's)", resp.status_code, "PASS", resp.json(), "404 as expected")
            print(f"  ✅ PASS: Cannot delete other's status (404)")
        else:
            tr.add("4.9: DELETE /api/status/{id} (other's)", resp.status_code, "FAIL", resp.text, "Expected 404")
            print(f"  ❌ FAIL: Expected 404, got {resp.status_code}")
    else:
        print(f"\n4.9: SKIPPED (no status_id)")
        tr.add("4.9: DELETE /api/status/{id} (other's)", 0, "SKIP", None, "No status_id")

def test_chat_theme(tr: TestResult, token_a: str, user_a: dict):
    """Test 5: Chat Theme"""
    print("\n" + "="*80)
    print("TEST 5: CHAT THEME")
    print("="*80)
    
    headers_a = {"Authorization": f"Bearer {token_a}"}
    
    # 5.1: Get a chat_id
    print(f"\n5.1: GET /api/chats (to get a chat_id)")
    resp = requests.get(f"{BASE_URL}/chats", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "chats list")
    print(f"  Status: {resp.status_code}")
    
    chat_id = None
    if resp.status_code == 200:
        data = resp.json()
        chats = data.get("chats", [])
        print(f"  chats: {len(chats)}")
        
        if chats:
            chat_id = chats[0].get("chat_id")
            print(f"  Using chat_id: {chat_id}")
            tr.add("5.1: GET /api/chats", resp.status_code, "PASS", data, f"{len(chats)} chats")
        else:
            tr.add("5.1: GET /api/chats", resp.status_code, "FAIL", data, "No chats")
            print(f"  ❌ FAIL: No chats available")
            return
    else:
        tr.add("5.1: GET /api/chats", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
        return
    
    # 5.2: POST /api/chats/{id}/theme (set theme)
    print(f"\n5.2: POST /api/chats/{chat_id}/theme (set theme)")
    theme_data = {
        "preset": "sunset",
        "bg": "#1a1a2e",
        "accent": "#FF5E00"
    }
    resp = requests.post(f"{BASE_URL}/chats/{chat_id}/theme", headers=headers_a, json={"theme": theme_data}, timeout=30)
    tr.check_security(resp.text, "chats/theme set")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        theme = data.get("theme")
        
        print(f"  theme: {theme}")
        
        if theme == theme_data:
            tr.add("5.2: POST /api/chats/{id}/theme (set)", resp.status_code, "PASS", data, "Theme set")
            print(f"  ✅ PASS: Theme set")
        else:
            tr.add("5.2: POST /api/chats/{id}/theme (set)", resp.status_code, "FAIL", data, "Theme mismatch")
            print(f"  ❌ FAIL: Theme mismatch")
    else:
        tr.add("5.2: POST /api/chats/{id}/theme (set)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 5.3: GET /api/chats/{id} (verify theme is returned)
    print(f"\n5.3: GET /api/chats/{chat_id} (verify theme)")
    resp = requests.get(f"{BASE_URL}/chats/{chat_id}", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "chats/{id} with theme")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        theme = data.get("theme")
        
        print(f"  theme: {theme}")
        
        if theme == theme_data:
            tr.add("5.3: GET /api/chats/{id} (verify theme)", resp.status_code, "PASS", data, "Theme matches")
            print(f"  ✅ PASS: Theme matches")
        else:
            tr.add("5.3: GET /api/chats/{id} (verify theme)", resp.status_code, "FAIL", data, "Theme mismatch")
            print(f"  ❌ FAIL: Theme mismatch")
    else:
        tr.add("5.3: GET /api/chats/{id} (verify theme)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 5.4: POST /api/chats/{id}/theme (clear theme with null)
    print(f"\n5.4: POST /api/chats/{chat_id}/theme (clear with null)")
    resp = requests.post(f"{BASE_URL}/chats/{chat_id}/theme", headers=headers_a, json={"theme": None}, timeout=30)
    tr.check_security(resp.text, "chats/theme clear")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        theme = data.get("theme")
        
        print(f"  theme: {theme}")
        
        if theme is None:
            tr.add("5.4: POST /api/chats/{id}/theme (clear)", resp.status_code, "PASS", data, "Theme cleared")
            print(f"  ✅ PASS: Theme cleared")
        else:
            tr.add("5.4: POST /api/chats/{id}/theme (clear)", resp.status_code, "FAIL", data, "Theme not null")
            print(f"  ❌ FAIL: Theme not null")
    else:
        tr.add("5.4: POST /api/chats/{id}/theme (clear)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 5.5: GET /api/chats/{id} (verify theme is null)
    print(f"\n5.5: GET /api/chats/{chat_id} (verify theme null)")
    resp = requests.get(f"{BASE_URL}/chats/{chat_id}", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "chats/{id} theme null")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        theme = data.get("theme")
        
        print(f"  theme: {theme}")
        
        if theme is None:
            tr.add("5.5: GET /api/chats/{id} (verify null)", resp.status_code, "PASS", data, "Theme is null")
            print(f"  ✅ PASS: Theme is null")
        else:
            tr.add("5.5: GET /api/chats/{id} (verify null)", resp.status_code, "FAIL", data, "Theme not null")
            print(f"  ❌ FAIL: Theme not null")
    else:
        tr.add("5.5: GET /api/chats/{id} (verify null)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")

def test_delete_chat_and_block(tr: TestResult, token_a: str, user_a: dict, token_b: str, user_b: dict):
    """Test 6: Delete Chat + Block"""
    print("\n" + "="*80)
    print("TEST 6: DELETE CHAT + BLOCK")
    print("="*80)
    
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    
    # 6.1: Create or get DM chat between A and B
    print(f"\n6.1: POST /api/chats (create DM between A and B)")
    resp = requests.post(f"{BASE_URL}/chats", headers=headers_a, json={"contact_id": user_b["user_id"]}, timeout=30)
    tr.check_security(resp.text, "chats create")
    print(f"  Status: {resp.status_code}")
    
    dm_chat_id = None
    if resp.status_code == 200:
        data = resp.json()
        dm_chat_id = data.get("chat_id")
        print(f"  chat_id: {dm_chat_id}")
        tr.add("6.1: POST /api/chats (create DM)", resp.status_code, "PASS", data, f"chat_id={dm_chat_id}")
    else:
        tr.add("6.1: POST /api/chats (create DM)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
        return
    
    # 6.2: DELETE /api/chats/{id} (User A deletes chat)
    print(f"\n6.2: DELETE /api/chats/{dm_chat_id} (User A)")
    resp = requests.delete(f"{BASE_URL}/chats/{dm_chat_id}", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "chats delete")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        status = data.get("status")
        
        if status == "deleted":
            tr.add("6.2: DELETE /api/chats/{id}", resp.status_code, "PASS", data, "status=deleted")
            print(f"  ✅ PASS: Chat deleted")
        else:
            tr.add("6.2: DELETE /api/chats/{id}", resp.status_code, "FAIL", data, f"status={status}")
            print(f"  ❌ FAIL: Expected status=deleted, got {status}")
    else:
        tr.add("6.2: DELETE /api/chats/{id}", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 6.3: GET /api/chats (verify chat not in list)
    print(f"\n6.3: GET /api/chats (User A - verify chat not listed)")
    resp = requests.get(f"{BASE_URL}/chats", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "chats list after delete")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        chats = data.get("chats", [])
        chat_ids = [c.get("chat_id") for c in chats]
        
        if dm_chat_id not in chat_ids:
            tr.add("6.3: GET /api/chats (after delete)", resp.status_code, "PASS", data, "Chat not listed")
            print(f"  ✅ PASS: Chat not in list")
        else:
            tr.add("6.3: GET /api/chats (after delete)", resp.status_code, "FAIL", data, "Chat still listed")
            print(f"  ❌ FAIL: Chat still in list")
    else:
        tr.add("6.3: GET /api/chats (after delete)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 6.4: POST /api/chats/{id}/messages (send message to deleted chat - should reappear)
    print(f"\n6.4: POST /api/chats/{dm_chat_id}/messages (send to deleted chat)")
    resp = requests.post(f"{BASE_URL}/chats/{dm_chat_id}/messages", headers=headers_a, 
                        json={"text": "Test message after delete"}, timeout=30)
    tr.check_security(resp.text, "chats/messages after delete")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        message = data.get("message", {})
        print(f"  message_id: {message.get('message_id')}")
        tr.add("6.4: POST /api/chats/{id}/messages (after delete)", resp.status_code, "PASS", data, "Message sent")
        print(f"  ✅ PASS: Message sent to deleted chat")
    else:
        tr.add("6.4: POST /api/chats/{id}/messages (after delete)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 6.5: GET /api/chats (verify chat reappeared)
    print(f"\n6.5: GET /api/chats (User A - verify chat reappeared)")
    resp = requests.get(f"{BASE_URL}/chats", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "chats list after message")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        chats = data.get("chats", [])
        chat_ids = [c.get("chat_id") for c in chats]
        
        if dm_chat_id in chat_ids:
            tr.add("6.5: GET /api/chats (after message)", resp.status_code, "PASS", data, "Chat reappeared")
            print(f"  ✅ PASS: Chat reappeared in list")
        else:
            tr.add("6.5: GET /api/chats (after message)", resp.status_code, "FAIL", data, "Chat not listed")
            print(f"  ❌ FAIL: Chat not in list")
    else:
        tr.add("6.5: GET /api/chats (after message)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 6.6: POST /api/contacts/block (User A blocks User B)
    print(f"\n6.6: POST /api/contacts/block (User A blocks User B)")
    resp = requests.post(f"{BASE_URL}/contacts/block", headers=headers_a, json={"user_id": user_b["user_id"]}, timeout=30)
    tr.check_security(resp.text, "contacts/block")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        blocked = data.get("blocked")
        
        print(f"  blocked: {blocked}")
        
        if blocked is True:
            tr.add("6.6: POST /api/contacts/block", resp.status_code, "PASS", data, "blocked=true")
            print(f"  ✅ PASS: User B blocked")
        else:
            tr.add("6.6: POST /api/contacts/block", resp.status_code, "FAIL", data, f"blocked={blocked}")
            print(f"  ❌ FAIL: Expected blocked=true, got {blocked}")
    else:
        tr.add("6.6: POST /api/contacts/block", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 6.7: POST /api/chats/{id}/messages (User A tries to send while blocked - should fail)
    print(f"\n6.7: POST /api/chats/{dm_chat_id}/messages (User A while blocked)")
    resp = requests.post(f"{BASE_URL}/chats/{dm_chat_id}/messages", headers=headers_a, 
                        json={"text": "Test while blocked"}, timeout=30)
    tr.check_security(resp.text, "chats/messages while blocked")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 403:
        tr.add("6.7: POST /api/chats/{id}/messages (blocked)", resp.status_code, "PASS", resp.json(), "403 as expected")
        print(f"  ✅ PASS: Cannot send while blocked (403)")
    else:
        tr.add("6.7: POST /api/chats/{id}/messages (blocked)", resp.status_code, "FAIL", resp.text, "Expected 403")
        print(f"  ❌ FAIL: Expected 403, got {resp.status_code}")
    
    # 6.8: GET /api/chats/{id} (verify blocked_by_me flag)
    print(f"\n6.8: GET /api/chats/{dm_chat_id} (verify blocked_by_me=true)")
    resp = requests.get(f"{BASE_URL}/chats/{dm_chat_id}", headers=headers_a, timeout=30)
    tr.check_security(resp.text, "chats/{id} blocked")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        blocked_by_me = data.get("blocked_by_me")
        
        print(f"  blocked_by_me: {blocked_by_me}")
        
        if blocked_by_me is True:
            tr.add("6.8: GET /api/chats/{id} (blocked_by_me)", resp.status_code, "PASS", data, "blocked_by_me=true")
            print(f"  ✅ PASS: blocked_by_me=true")
        else:
            tr.add("6.8: GET /api/chats/{id} (blocked_by_me)", resp.status_code, "FAIL", data, f"blocked_by_me={blocked_by_me}")
            print(f"  ❌ FAIL: Expected blocked_by_me=true, got {blocked_by_me}")
    else:
        tr.add("6.8: GET /api/chats/{id} (blocked_by_me)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 6.9: POST /api/contacts/block (User A unblocks User B)
    print(f"\n6.9: POST /api/contacts/block (User A unblocks User B)")
    resp = requests.post(f"{BASE_URL}/contacts/block", headers=headers_a, json={"user_id": user_b["user_id"]}, timeout=30)
    tr.check_security(resp.text, "contacts/unblock")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        blocked = data.get("blocked")
        
        print(f"  blocked: {blocked}")
        
        if blocked is False:
            tr.add("6.9: POST /api/contacts/block (unblock)", resp.status_code, "PASS", data, "blocked=false")
            print(f"  ✅ PASS: User B unblocked")
        else:
            tr.add("6.9: POST /api/contacts/block (unblock)", resp.status_code, "FAIL", data, f"blocked={blocked}")
            print(f"  ❌ FAIL: Expected blocked=false, got {blocked}")
    else:
        tr.add("6.9: POST /api/contacts/block (unblock)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")
    
    # 6.10: POST /api/chats/{id}/messages (User A sends after unblock - should work)
    print(f"\n6.10: POST /api/chats/{dm_chat_id}/messages (User A after unblock)")
    resp = requests.post(f"{BASE_URL}/chats/{dm_chat_id}/messages", headers=headers_a, 
                        json={"text": "Test after unblock"}, timeout=30)
    tr.check_security(resp.text, "chats/messages after unblock")
    print(f"  Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        message = data.get("message", {})
        tr.add("6.10: POST /api/chats/{id}/messages (unblocked)", resp.status_code, "PASS", data, "Message sent")
        print(f"  ✅ PASS: Message sent after unblock")
    else:
        tr.add("6.10: POST /api/chats/{id}/messages (unblocked)", resp.status_code, "FAIL", resp.text)
        print(f"  ❌ FAIL: {resp.text}")

def print_summary(tr: TestResult):
    """Print test summary"""
    print("\n" + "="*100)
    print("TEST SUMMARY")
    print("="*100)
    print(f"{'Test':<60} {'Status':<10} {'Result':<15} {'Notes':<15}")
    print("-"*100)
    
    for test_name, status_code, result, data, notes in tr.results:
        print(f"{test_name:<60} {str(status_code):<10} {result:<15} {notes:<15}")
    
    print("\n" + "="*100)
    print("SECURITY CHECK")
    print("="*100)
    if tr.security_issues:
        print("❌ SECURITY ISSUES FOUND:")
        for issue in tr.security_issues:
            print(f"  - {issue}")
    else:
        print("✅ NO SECURITY LEAKS DETECTED")
    
    print("\n" + "="*100)
    
    # Count results
    passed = sum(1 for _, _, result, _, _ in tr.results if "PASS" in result)
    failed = sum(1 for _, _, result, _, _ in tr.results if "FAIL" in result)
    skipped = sum(1 for _, _, result, _, _ in tr.results if "SKIP" in result)
    
    print(f"\nTOTAL: {len(tr.results)} tests")
    print(f"✅ PASSED: {passed}")
    print(f"❌ FAILED: {failed}")
    print(f"⏭️  SKIPPED: {skipped}")
    print("="*100)
    
    return failed

def main():
    print("="*100)
    print("CHATLY AI MESSENGER - PHASE 5 BACKEND TESTING")
    print("="*100)
    print(f"Backend URL: {BASE_URL}")
    print("="*100)
    
    tr = TestResult()
    
    # Login as User A (demo)
    token_a, user_a = login_user(DEMO_EMAIL, DEMO_PASSWORD)
    if not token_a:
        print("❌ Failed to login as User A")
        sys.exit(1)
    
    # Create/login as User B
    token_b, user_b = create_user_b(tr)
    if not token_b:
        print("❌ Failed to setup User B")
        sys.exit(1)
    
    # Run all tests
    test_qr_code(tr, token_a, user_a, token_b, user_b)
    test_public_profile(tr, token_a, user_a, token_b, user_b)
    test_friend_requests(tr, token_a, user_a, token_b, user_b)
    test_status_feature(tr, token_a, user_a, token_b, user_b)
    test_chat_theme(tr, token_a, user_a)
    test_delete_chat_and_block(tr, token_a, user_a, token_b, user_b)
    
    # Print summary
    failed_count = print_summary(tr)
    
    # Exit with appropriate code
    if failed_count > 0 or tr.security_issues:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
