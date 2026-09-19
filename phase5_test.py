#!/usr/bin/env python3
"""
Phase 5 Backend Testing: Friend Request Flow + Block Enforcement
Tests the two previously SKIPPED items now that email works and demo2 account exists.
"""
import requests
import sys
from typing import Dict, Any

# Backend URL from frontend/.env
BASE_URL = "https://chatly-mobile.preview.emergentagent.com/api"

# Test credentials from test_credentials.md
USER_A_EMAIL = "demo@chatly.app"
USER_A_PASSWORD = "Demo1234"
USER_B_EMAIL = "demo2@chatly.app"
USER_B_PASSWORD = "Demo1234"

# Security check patterns
SECURITY_PATTERNS = ["Traceback", "sk_", "tvly", "sk-emergent", "MONGO_URL", "JWT_SECRET"]

def check_security(response_text: str, step: str) -> list:
    """Check if response contains any security leaks"""
    leaks = []
    for pattern in SECURITY_PATTERNS:
        if pattern in response_text:
            leaks.append(f"SECURITY LEAK in {step}: Found '{pattern}' in response")
    return leaks

def login_user(email: str, password: str) -> tuple[str, dict]:
    """Login and return (token, user_data)"""
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=30)
    if resp.status_code != 200:
        raise Exception(f"Login failed for {email}: {resp.status_code} {resp.text}")
    data = resp.json()
    return data["token"], data["user"]

def test_friend_request_flow():
    """Test 3: FRIEND REQUEST FLOW"""
    results = []
    security_issues = []
    
    print("\n" + "="*100)
    print("TEST 3: FRIEND REQUEST FLOW")
    print("="*100)
    
    # Login both users
    print("\n--- Setup: Login both users ---")
    try:
        token_a, user_a = login_user(USER_A_EMAIL, USER_A_PASSWORD)
        print(f"✓ User A logged in: {user_a['name']} ({user_a['user_id']})")
        token_b, user_b = login_user(USER_B_EMAIL, USER_B_PASSWORD)
        print(f"✓ User B logged in: {user_b['name']} ({user_b['user_id']})")
    except Exception as e:
        print(f"✗ Login failed: {e}")
        results.append(("Setup: Login", "ERROR", str(e), None))
        return results, security_issues
    
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    
    # Step 1: A sends friend request to B
    print("\n--- Step 1: A sends friend request to B ---")
    print(f"POST /api/contacts/request {{to_id: {user_b['user_id']}}}")
    try:
        resp = requests.post(f"{BASE_URL}/contacts/request", 
                           json={"to_id": user_b["user_id"]}, 
                           headers=headers_a, timeout=30)
        security_issues.extend(check_security(resp.text, "send request"))
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {data}")
        
        if resp.status_code == 200 and data.get("status") in ["pending", "already_contacts"]:
            results.append(("Step 1: Send request A→B", resp.status_code, "PASS", data))
            print(f"✓ PASS: Request sent, status={data.get('status')}")
        else:
            results.append(("Step 1: Send request A→B", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 200 with status=pending or already_contacts")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 1: Send request A→B", "ERROR", str(e), None))
    
    # Step 2: A sends duplicate request to B
    print("\n--- Step 2: A sends duplicate request to B ---")
    print(f"POST /api/contacts/request {{to_id: {user_b['user_id']}}} (duplicate)")
    try:
        resp = requests.post(f"{BASE_URL}/contacts/request", 
                           json={"to_id": user_b["user_id"]}, 
                           headers=headers_a, timeout=30)
        security_issues.extend(check_security(resp.text, "duplicate request"))
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {data}")
        
        if resp.status_code == 200 and data.get("status") in ["pending", "already_contacts"]:
            results.append(("Step 2: Duplicate request A→B", resp.status_code, "PASS", data))
            print(f"✓ PASS: Duplicate handled gracefully, status={data.get('status')}")
        else:
            results.append(("Step 2: Duplicate request A→B", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 200 with status=pending or already_contacts")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 2: Duplicate request A→B", "ERROR", str(e), None))
    
    # Step 3: A tries to add self
    print("\n--- Step 3: A tries to add self ---")
    print(f"POST /api/contacts/request {{to_id: {user_a['user_id']}}} (self)")
    try:
        resp = requests.post(f"{BASE_URL}/contacts/request", 
                           json={"to_id": user_a["user_id"]}, 
                           headers=headers_a, timeout=30)
        security_issues.extend(check_security(resp.text, "self-add request"))
        print(f"Status: {resp.status_code}")
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"detail": resp.text}
        print(f"Response: {data}")
        
        if resp.status_code == 400 and "cannot add yourself" in str(data).lower():
            results.append(("Step 3: Self-add A→A", resp.status_code, "PASS", data))
            print(f"✓ PASS: Self-add correctly rejected with 400")
        else:
            results.append(("Step 3: Self-add A→A", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 400 with 'cannot add yourself'")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 3: Self-add A→A", "ERROR", str(e), None))
    
    # Step 4: B lists incoming requests
    print("\n--- Step 4: B lists incoming requests ---")
    print("GET /api/contacts/requests")
    try:
        resp = requests.get(f"{BASE_URL}/contacts/requests", headers=headers_b, timeout=30)
        security_issues.extend(check_security(resp.text, "list requests"))
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {data}")
        
        if resp.status_code == 200 and "requests" in data:
            # Check if A's request is in the list
            a_request = next((r for r in data["requests"] if r["user_id"] == user_a["user_id"]), None)
            if a_request and "request_id" in a_request:
                request_id = a_request["request_id"]
                results.append(("Step 4: B lists incoming requests", resp.status_code, "PASS", {"request_id": request_id}))
                print(f"✓ PASS: Found A's request with request_id={request_id}")
            else:
                results.append(("Step 4: B lists incoming requests", resp.status_code, "FAIL - A's request not found", data))
                print(f"✗ FAIL: A's request not found in list")
                request_id = None
        else:
            results.append(("Step 4: B lists incoming requests", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 200 with requests list")
            request_id = None
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 4: B lists incoming requests", "ERROR", str(e), None))
        request_id = None
    
    # Step 5: B views A's profile (should show request_incoming)
    print("\n--- Step 5: B views A's profile ---")
    print(f"GET /api/users/{user_a['user_id']}")
    try:
        resp = requests.get(f"{BASE_URL}/users/{user_a['user_id']}", headers=headers_b, timeout=30)
        security_issues.extend(check_security(resp.text, "view profile"))
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {data}")
        
        if resp.status_code == 200 and "user" in data:
            rel = data["user"].get("relationship", {})
            if rel.get("status") == "request_incoming" and "request_id" in rel:
                results.append(("Step 5: B views A's profile", resp.status_code, "PASS", rel))
                print(f"✓ PASS: Relationship status=request_incoming with request_id={rel['request_id']}")
            else:
                results.append(("Step 5: B views A's profile", resp.status_code, "FAIL - wrong relationship", rel))
                print(f"✗ FAIL: Expected relationship.status=request_incoming with request_id, got {rel}")
        else:
            results.append(("Step 5: B views A's profile", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 200 with user object")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 5: B views A's profile", "ERROR", str(e), None))
    
    # Step 6: B accepts the request
    if request_id:
        print("\n--- Step 6: B accepts the request ---")
        print(f"POST /api/contacts/respond {{request_id: {request_id}, accept: true}}")
        try:
            resp = requests.post(f"{BASE_URL}/contacts/respond", 
                               json={"request_id": request_id, "accept": True}, 
                               headers=headers_b, timeout=30)
            security_issues.extend(check_security(resp.text, "accept request"))
            print(f"Status: {resp.status_code}")
            data = resp.json()
            print(f"Response: {data}")
            
            if resp.status_code == 200 and data.get("status") == "accepted":
                results.append(("Step 6: B accepts request", resp.status_code, "PASS", data))
                print(f"✓ PASS: Request accepted")
            else:
                results.append(("Step 6: B accepts request", resp.status_code, "FAIL", data))
                print(f"✗ FAIL: Expected 200 with status=accepted")
        except Exception as e:
            print(f"✗ ERROR: {e}")
            results.append(("Step 6: B accepts request", "ERROR", str(e), None))
    else:
        print("\n--- Step 6: SKIPPED (no request_id from step 4) ---")
        results.append(("Step 6: B accepts request", "SKIP", "No request_id", None))
    
    # Step 7: Verify A sees B as friends
    print("\n--- Step 7: A views B's profile (should be friends) ---")
    print(f"GET /api/users/{user_b['user_id']}")
    try:
        resp = requests.get(f"{BASE_URL}/users/{user_b['user_id']}", headers=headers_a, timeout=30)
        security_issues.extend(check_security(resp.text, "verify friends A"))
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {data}")
        
        if resp.status_code == 200 and "user" in data:
            rel = data["user"].get("relationship", {})
            if rel.get("status") == "friends":
                results.append(("Step 7: A views B (friends)", resp.status_code, "PASS", rel))
                print(f"✓ PASS: A sees B as friends")
            else:
                results.append(("Step 7: A views B (friends)", resp.status_code, "FAIL - not friends", rel))
                print(f"✗ FAIL: Expected relationship.status=friends, got {rel}")
        else:
            results.append(("Step 7: A views B (friends)", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 200 with user object")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 7: A views B (friends)", "ERROR", str(e), None))
    
    # Step 8: Verify B sees A as friends
    print("\n--- Step 8: B views A's profile (should be friends) ---")
    print(f"GET /api/users/{user_a['user_id']}")
    try:
        resp = requests.get(f"{BASE_URL}/users/{user_a['user_id']}", headers=headers_b, timeout=30)
        security_issues.extend(check_security(resp.text, "verify friends B"))
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {data}")
        
        if resp.status_code == 200 and "user" in data:
            rel = data["user"].get("relationship", {})
            if rel.get("status") == "friends":
                results.append(("Step 8: B views A (friends)", resp.status_code, "PASS", rel))
                print(f"✓ PASS: B sees A as friends")
            else:
                results.append(("Step 8: B views A (friends)", resp.status_code, "FAIL - not friends", rel))
                print(f"✗ FAIL: Expected relationship.status=friends, got {rel}")
        else:
            results.append(("Step 8: B views A (friends)", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 200 with user object")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 8: B views A (friends)", "ERROR", str(e), None))
    
    return results, security_issues, (token_a, user_a, token_b, user_b)

def test_block_enforcement(token_a: str, user_a: dict, token_b: dict, user_b: dict):
    """Test 6: BLOCK ENFORCEMENT"""
    results = []
    security_issues = []
    
    print("\n" + "="*100)
    print("TEST 6: BLOCK ENFORCEMENT")
    print("="*100)
    
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    
    # Step 1: A creates/gets chat with B
    print("\n--- Step 1: A creates chat with B ---")
    print(f"POST /api/chats {{contact_id: {user_b['user_id']}}}")
    try:
        resp = requests.post(f"{BASE_URL}/chats", 
                           json={"contact_id": user_b["user_id"]}, 
                           headers=headers_a, timeout=30)
        security_issues.extend(check_security(resp.text, "create chat"))
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {data}")
        
        if resp.status_code == 200 and "chat_id" in data:
            chat_id = data["chat_id"]
            results.append(("Step 1: A creates chat with B", resp.status_code, "PASS", {"chat_id": chat_id}))
            print(f"✓ PASS: Chat created, chat_id={chat_id}")
        else:
            results.append(("Step 1: A creates chat with B", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 200 with chat_id")
            return results, security_issues
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 1: A creates chat with B", "ERROR", str(e), None))
        return results, security_issues
    
    # Step 2: A sends message before block
    print("\n--- Step 2: A sends message before block ---")
    print(f"POST /api/chats/{chat_id}/messages {{text: 'hi'}}")
    try:
        resp = requests.post(f"{BASE_URL}/chats/{chat_id}/messages", 
                           json={"text": "hi"}, 
                           headers=headers_a, timeout=30)
        security_issues.extend(check_security(resp.text, "send before block"))
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {data}")
        
        if resp.status_code == 200 and "message" in data:
            results.append(("Step 2: A sends before block", resp.status_code, "PASS", {"message_id": data["message"]["message_id"]}))
            print(f"✓ PASS: Message sent successfully")
        else:
            results.append(("Step 2: A sends before block", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 200 with message")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 2: A sends before block", "ERROR", str(e), None))
    
    # Step 3: A blocks B
    print("\n--- Step 3: A blocks B ---")
    print(f"POST /api/contacts/block {{user_id: {user_b['user_id']}}}")
    try:
        resp = requests.post(f"{BASE_URL}/contacts/block", 
                           json={"user_id": user_b["user_id"]}, 
                           headers=headers_a, timeout=30)
        security_issues.extend(check_security(resp.text, "block user"))
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {data}")
        
        if resp.status_code == 200 and data.get("blocked") == True:
            results.append(("Step 3: A blocks B", resp.status_code, "PASS", data))
            print(f"✓ PASS: B blocked by A")
        else:
            results.append(("Step 3: A blocks B", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 200 with blocked=true")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 3: A blocks B", "ERROR", str(e), None))
    
    # Step 4: A views chat (should show blocked_by_me=true)
    print("\n--- Step 4: A views chat (should show blocked_by_me=true) ---")
    print(f"GET /api/chats/{chat_id}")
    try:
        resp = requests.get(f"{BASE_URL}/chats/{chat_id}", headers=headers_a, timeout=30)
        security_issues.extend(check_security(resp.text, "view chat blocked"))
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {data}")
        
        if resp.status_code == 200 and data.get("blocked_by_me") == True:
            results.append(("Step 4: A views chat (blocked_by_me)", resp.status_code, "PASS", {"blocked_by_me": True}))
            print(f"✓ PASS: blocked_by_me=true")
        else:
            results.append(("Step 4: A views chat (blocked_by_me)", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected blocked_by_me=true, got {data.get('blocked_by_me')}")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 4: A views chat (blocked_by_me)", "ERROR", str(e), None))
    
    # Step 5: A tries to send message while blocked (should get 403)
    print("\n--- Step 5: A tries to send message while blocked ---")
    print(f"POST /api/chats/{chat_id}/messages {{text: 'blocked?'}}")
    try:
        resp = requests.post(f"{BASE_URL}/chats/{chat_id}/messages", 
                           json={"text": "blocked?"}, 
                           headers=headers_a, timeout=30)
        security_issues.extend(check_security(resp.text, "send while blocked"))
        print(f"Status: {resp.status_code}")
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"detail": resp.text}
        print(f"Response: {data}")
        
        if resp.status_code == 403 and "can't send messages" in str(data).lower():
            results.append(("Step 5: A sends while blocked", resp.status_code, "PASS", data))
            print(f"✓ PASS: Send blocked with 403")
        else:
            results.append(("Step 5: A sends while blocked", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 403 with 'can't send messages', got {resp.status_code}")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 5: A sends while blocked", "ERROR", str(e), None))
    
    # Step 6: A unblocks B (toggle)
    print("\n--- Step 6: A unblocks B (toggle) ---")
    print(f"POST /api/contacts/block {{user_id: {user_b['user_id']}}} (toggle)")
    try:
        resp = requests.post(f"{BASE_URL}/contacts/block", 
                           json={"user_id": user_b["user_id"]}, 
                           headers=headers_a, timeout=30)
        security_issues.extend(check_security(resp.text, "unblock user"))
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {data}")
        
        if resp.status_code == 200 and data.get("blocked") == False:
            results.append(("Step 6: A unblocks B", resp.status_code, "PASS", data))
            print(f"✓ PASS: B unblocked by A")
        else:
            results.append(("Step 6: A unblocks B", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 200 with blocked=false")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 6: A unblocks B", "ERROR", str(e), None))
    
    # Step 7: A sends message after unblock (should work)
    print("\n--- Step 7: A sends message after unblock ---")
    print(f"POST /api/chats/{chat_id}/messages {{text: 'back'}}")
    try:
        resp = requests.post(f"{BASE_URL}/chats/{chat_id}/messages", 
                           json={"text": "back"}, 
                           headers=headers_a, timeout=30)
        security_issues.extend(check_security(resp.text, "send after unblock"))
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Response: {data}")
        
        if resp.status_code == 200 and "message" in data:
            results.append(("Step 7: A sends after unblock", resp.status_code, "PASS", {"message_id": data["message"]["message_id"]}))
            print(f"✓ PASS: Message sent successfully after unblock")
        else:
            results.append(("Step 7: A sends after unblock", resp.status_code, "FAIL", data))
            print(f"✗ FAIL: Expected 200 with message")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        results.append(("Step 7: A sends after unblock", "ERROR", str(e), None))
    
    return results, security_issues

def print_summary(all_results, all_security_issues):
    """Print test summary"""
    print("\n" + "="*100)
    print("TEST SUMMARY")
    print("="*100)
    print(f"{'Step':<60} {'Status':<10} {'Result':<15}")
    print("-"*100)
    
    for step, status, result, data in all_results:
        print(f"{step:<60} {str(status):<10} {result:<15}")
    
    print("\n" + "="*100)
    print("SECURITY CHECK")
    print("="*100)
    if all_security_issues:
        print("❌ SECURITY ISSUES FOUND:")
        for issue in all_security_issues:
            print(f"  - {issue}")
    else:
        print("✅ NO SECURITY LEAKS DETECTED")
    
    print("\n" + "="*100)
    
    # Count pass/fail
    passed = sum(1 for _, _, result, _ in all_results if "PASS" in result)
    failed = sum(1 for _, _, result, _ in all_results if "FAIL" in result)
    errors = sum(1 for _, _, result, _ in all_results if "ERROR" in result)
    skipped = sum(1 for _, _, result, _ in all_results if "SKIP" in result)
    
    print(f"\nTOTAL: {len(all_results)} tests")
    print(f"✅ PASSED: {passed}")
    print(f"❌ FAILED: {failed}")
    print(f"⚠️  ERRORS: {errors}")
    print(f"⏭️  SKIPPED: {skipped}")
    print("="*100)

def main():
    print("="*100)
    print("CHATLY AI MESSENGER - PHASE 5 BACKEND TESTING")
    print("Friend Request Flow + Block Enforcement")
    print("="*100)
    print(f"Backend URL: {BASE_URL}")
    print(f"User A: {USER_A_EMAIL}")
    print(f"User B: {USER_B_EMAIL}")
    print("="*100)
    
    all_results = []
    all_security_issues = []
    
    # Test 3: Friend Request Flow
    results, security, user_data = test_friend_request_flow()
    all_results.extend(results)
    all_security_issues.extend(security)
    
    # Test 6: Block Enforcement (only if friend request flow succeeded)
    if user_data:
        token_a, user_a, token_b, user_b = user_data
        results, security = test_block_enforcement(token_a, user_a, token_b, user_b)
        all_results.extend(results)
        all_security_issues.extend(security)
    else:
        print("\n⚠️  SKIPPING BLOCK ENFORCEMENT TEST (friend request flow failed)")
    
    # Print summary
    print_summary(all_results, all_security_issues)
    
    # Exit with appropriate code
    failed = sum(1 for _, _, result, _ in all_results if "FAIL" in result)
    errors = sum(1 for _, _, result, _ in all_results if "ERROR" in result)
    if failed > 0 or errors > 0 or all_security_issues:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
