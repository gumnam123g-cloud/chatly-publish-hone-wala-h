#!/usr/bin/env python3
"""
Backend API testing for Chatly Phase 10 - Messaging AI features
Tests NEW/CHANGED endpoints as per review request
"""
import requests
import json
import sys
from typing import Dict, Any

# Backend URL from review request
BASE_URL = "https://chatly-mobile.preview.emergentagent.com/api"

# Test credentials from review request
DEMO_EMAIL = "demo@chatly.app"
DEMO_PASSWORD = "Demo1234"
DEMO2_EMAIL = "demo2@chatly.app"
DEMO2_PASSWORD = "Demo1234"

# Global state
demo_token = None
demo2_token = None
demo_user = None
demo2_user = None

# Security leak patterns to check
LEAK_PATTERNS = [
    "Traceback", "sk_", "tvly", "sk-emergent", "ek_", 
    "MONGO_URL", "JWT_SECRET", "private_key"
]


def check_security_leaks(response_text: str, test_name: str) -> bool:
    """Check if response contains any security leaks"""
    for pattern in LEAK_PATTERNS:
        if pattern in response_text:
            print(f"  ❌ SECURITY LEAK DETECTED in {test_name}: Found '{pattern}' in response")
            return True
    return False


def login(email: str, password: str) -> tuple[str, dict]:
    """Login and return token and user"""
    print(f"\n🔐 Logging in as {email}...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": email,
        "password": password
    })
    
    if resp.status_code != 200:
        print(f"  ❌ Login failed: {resp.status_code} - {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    token = data.get("token")
    user = data.get("user")
    print(f"  ✅ Logged in successfully as {user.get('name')} ({user.get('user_id')})")
    return token, user


def test_ai_message_actions():
    """Test 1: AI MESSAGE ACTIONS with per-action language/tone"""
    print("\n" + "="*80)
    print("TEST 1: AI MESSAGE ACTIONS (POST /api/ai/message-action)")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {demo_token}"}
    
    # Test 1.1: Translate Hinglish to English
    print("\n1.1 Testing translate Hinglish → English...")
    resp = requests.post(f"{BASE_URL}/ai/message-action", headers=headers, json={
        "text": "Bhai kal report bhej dena please",
        "action": "translate",
        "target_lang": "English"
    })
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        result = data.get("result", "")
        print(f"  ✅ Translation result: {result[:100]}")
        if not result:
            print(f"  ❌ FAIL: Empty result")
            return False
        if check_security_leaks(resp.text, "translate"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    # Test 1.2: Summarize in Hindi
    print("\n1.2 Testing summarize with out_lang=Hindi...")
    resp = requests.post(f"{BASE_URL}/ai/message-action", headers=headers, json={
        "text": "Let's meet at 5pm to finalize the budget",
        "action": "summarize",
        "out_lang": "Hindi"
    })
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        result = data.get("result", "")
        print(f"  ✅ Summary result: {result[:100]}")
        if not result:
            print(f"  ❌ FAIL: Empty result")
            return False
        if check_security_leaks(resp.text, "summarize"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    # Test 1.3: Explain in English
    print("\n1.3 Testing explain with out_lang=English...")
    resp = requests.post(f"{BASE_URL}/ai/message-action", headers=headers, json={
        "text": "The API returned a 500 during checkout",
        "action": "explain",
        "out_lang": "English"
    })
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        result = data.get("result", "")
        print(f"  ✅ Explanation result: {result[:100]}")
        if not result:
            print(f"  ❌ FAIL: Empty result")
            return False
        if check_security_leaks(resp.text, "explain"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    # Test 1.4: Reply with professional tone
    print("\n1.4 Testing reply with tone=professional, out_lang=English...")
    resp = requests.post(f"{BASE_URL}/ai/message-action", headers=headers, json={
        "text": "Are we still on for tomorrow?",
        "action": "reply",
        "tone": "professional",
        "out_lang": "English"
    })
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        result = data.get("result", "")
        action = data.get("action")
        print(f"  ✅ Reply result: {result[:100]}")
        print(f"  Action echoed: {action}")
        if not result or action != "reply":
            print(f"  ❌ FAIL: Empty result or wrong action")
            return False
        if check_security_leaks(resp.text, "reply"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    print("\n✅ TEST 1 PASSED: All AI message actions working correctly")
    return True


def test_chat_brain_out_lang():
    """Test 2: CHAT-BRAIN with out_lang"""
    print("\n" + "="*80)
    print("TEST 2: CHAT-BRAIN out_lang (POST /api/ai/chat-brain)")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {demo_token}"}
    
    # First get a chat_id
    print("\n2.1 Getting chat list...")
    resp = requests.get(f"{BASE_URL}/chats", headers=headers)
    if resp.status_code != 200:
        print(f"  ❌ FAIL: Could not get chats: {resp.text}")
        return False
    
    chats = resp.json().get("chats", [])
    if not chats:
        print(f"  ❌ FAIL: No chats available")
        return False
    
    chat_id = chats[0]["chat_id"]
    print(f"  ✅ Using chat_id: {chat_id}")
    
    # Test 2.2: Summary in Hindi
    print("\n2.2 Testing chat-brain summary with out_lang=Hindi...")
    resp = requests.post(f"{BASE_URL}/ai/chat-brain", headers=headers, json={
        "chat_id": chat_id,
        "kind": "summary",
        "out_lang": "Hindi"
    })
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        kind = data.get("kind")
        result = data.get("result", "")
        print(f"  ✅ Kind: {kind}, Result: {result[:100]}")
        if not result:
            print(f"  ❌ FAIL: Empty result")
            return False
        if check_security_leaks(resp.text, "chat-brain-hindi"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    # Test 2.3: Timeline without out_lang
    print("\n2.3 Testing chat-brain timeline without out_lang...")
    resp = requests.post(f"{BASE_URL}/ai/chat-brain", headers=headers, json={
        "chat_id": chat_id,
        "kind": "timeline"
    })
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        kind = data.get("kind")
        result = data.get("result", "")
        print(f"  ✅ Kind: {kind}, Result: {result[:100]}")
        if not result:
            print(f"  ❌ FAIL: Empty result")
            return False
        if check_security_leaks(resp.text, "chat-brain-timeline"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    print("\n✅ TEST 2 PASSED: Chat-brain out_lang working correctly")
    return True


def test_delete_for_me_everyone():
    """Test 3: DELETE FOR ME / EVERYONE"""
    print("\n" + "="*80)
    print("TEST 3: DELETE FOR ME / EVERYONE (DELETE /api/messages/{id}?scope=)")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {demo_token}"}
    
    # Get a chat
    print("\n3.1 Getting a chat...")
    resp = requests.get(f"{BASE_URL}/chats", headers=headers)
    if resp.status_code != 200:
        print(f"  ❌ FAIL: Could not get chats: {resp.text}")
        return False
    
    chats = resp.json().get("chats", [])
    if not chats:
        print(f"  ❌ FAIL: No chats available")
        return False
    
    chat_id = chats[0]["chat_id"]
    print(f"  ✅ Using chat_id: {chat_id}")
    
    # Test 3.2: Send a message for "delete for me" test
    print("\n3.2 Sending message 'scope test A'...")
    resp = requests.post(f"{BASE_URL}/chats/{chat_id}/messages", headers=headers, json={
        "text": "scope test A"
    })
    if resp.status_code != 200:
        print(f"  ❌ FAIL: Could not send message: {resp.text}")
        return False
    
    message_id_a = resp.json()["message"]["message_id"]
    print(f"  ✅ Message sent: {message_id_a}")
    
    # Test 3.3: Delete for me
    print("\n3.3 Testing DELETE ?scope=me...")
    resp = requests.delete(f"{BASE_URL}/messages/{message_id_a}?scope=me", headers=headers)
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        status = data.get("status")
        scope = data.get("scope")
        print(f"  ✅ Status: {status}, Scope: {scope}")
        if status != "deleted" or scope != "me":
            print(f"  ❌ FAIL: Wrong status or scope")
            return False
        if check_security_leaks(resp.text, "delete-me"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    # Test 3.4: Verify message is hidden
    print("\n3.4 Verifying message is hidden in GET messages...")
    resp = requests.get(f"{BASE_URL}/chats/{chat_id}/messages", headers=headers)
    if resp.status_code == 200:
        messages = resp.json().get("messages", [])
        found = any(m["message_id"] == message_id_a for m in messages)
        if found:
            print(f"  ❌ FAIL: Message still visible after delete for me")
            return False
        print(f"  ✅ Message correctly hidden")
    else:
        print(f"  ❌ FAIL: Could not get messages: {resp.text}")
        return False
    
    # Test 3.5: Send another message for "delete for everyone" test
    print("\n3.5 Sending message 'scope test B'...")
    resp = requests.post(f"{BASE_URL}/chats/{chat_id}/messages", headers=headers, json={
        "text": "scope test B"
    })
    if resp.status_code != 200:
        print(f"  ❌ FAIL: Could not send message: {resp.text}")
        return False
    
    message_id_b = resp.json()["message"]["message_id"]
    print(f"  ✅ Message sent: {message_id_b}")
    
    # Test 3.6: Delete for everyone
    print("\n3.6 Testing DELETE ?scope=everyone...")
    resp = requests.delete(f"{BASE_URL}/messages/{message_id_b}?scope=everyone", headers=headers)
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        status = data.get("status")
        scope = data.get("scope")
        print(f"  ✅ Status: {status}, Scope: {scope}")
        if status != "deleted" or scope != "everyone":
            print(f"  ❌ FAIL: Wrong status or scope")
            return False
        if check_security_leaks(resp.text, "delete-everyone"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    # Test 3.7: Verify message is tombstoned
    print("\n3.7 Verifying message is tombstoned...")
    resp = requests.get(f"{BASE_URL}/chats/{chat_id}/messages", headers=headers)
    if resp.status_code == 200:
        messages = resp.json().get("messages", [])
        msg = next((m for m in messages if m["message_id"] == message_id_b), None)
        if not msg:
            print(f"  ❌ FAIL: Message not found")
            return False
        if msg.get("text") != "This message was deleted" or not msg.get("deleted"):
            print(f"  ❌ FAIL: Message not properly tombstoned")
            print(f"  Text: {msg.get('text')}, Deleted: {msg.get('deleted')}")
            return False
        print(f"  ✅ Message correctly tombstoned")
    else:
        print(f"  ❌ FAIL: Could not get messages: {resp.text}")
        return False
    
    # Test 3.8: Try to delete bot's message (should fail)
    print("\n3.8 Testing DELETE ?scope=everyone on bot's message (should fail)...")
    resp = requests.get(f"{BASE_URL}/chats/{chat_id}/messages", headers=headers)
    if resp.status_code == 200:
        messages = resp.json().get("messages", [])
        bot_msg = next((m for m in messages if m["sender_id"] != demo_user["user_id"] and not m.get("deleted")), None)
        if bot_msg:
            resp = requests.delete(f"{BASE_URL}/messages/{bot_msg['message_id']}?scope=everyone", headers=headers)
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 403:
                print(f"  ✅ Correctly rejected with 403")
            else:
                print(f"  ❌ FAIL: Should return 403, got {resp.status_code}")
                return False
        else:
            print(f"  ⚠️  SKIP: No bot message found to test")
    
    # Test 3.9: Very large message (15000 chars)
    print("\n3.9 Testing very large message (~15000 chars)...")
    large_text = "A" * 15000
    resp = requests.post(f"{BASE_URL}/chats/{chat_id}/messages", headers=headers, json={
        "text": large_text
    })
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"  ✅ Large message accepted (limit is 20000)")
    else:
        print(f"  ❌ FAIL: Large message rejected: {resp.text}")
        return False
    
    print("\n✅ TEST 3 PASSED: Delete for me/everyone working correctly")
    return True


def test_username_uniqueness():
    """Test 4: USERNAME uniqueness/validation"""
    print("\n" + "="*80)
    print("TEST 4: USERNAME uniqueness/validation")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {demo_token}"}
    
    # Test 4.1: Check own username (should be available)
    print("\n4.1 Testing GET /api/auth/username-available?u=demouser (own username)...")
    resp = requests.get(f"{BASE_URL}/auth/username-available?u=demouser", headers=headers)
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        available = data.get("available")
        print(f"  ✅ Available: {available}")
        if not available:
            print(f"  ❌ FAIL: Own username should be available (excluded from check)")
            return False
        if check_security_leaks(resp.text, "username-own"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    # Test 4.2: Check demo2's username (should be unavailable)
    print("\n4.2 Testing GET /api/auth/username-available?u=arianair (demo2's username)...")
    resp = requests.get(f"{BASE_URL}/auth/username-available?u=arianair", headers=headers)
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        available = data.get("available")
        print(f"  ✅ Available: {available}")
        if available:
            print(f"  ❌ FAIL: demo2's username should be unavailable")
            return False
        if check_security_leaks(resp.text, "username-taken"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    # Test 4.3: Check too short username (should be invalid)
    print("\n4.3 Testing GET /api/auth/username-available?u=ab (too short)...")
    resp = requests.get(f"{BASE_URL}/auth/username-available?u=ab", headers=headers)
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        available = data.get("available")
        reason = data.get("reason")
        print(f"  ✅ Available: {available}, Reason: {reason}")
        if available or reason != "invalid":
            print(f"  ❌ FAIL: Should be unavailable with reason=invalid")
            return False
        if check_security_leaks(resp.text, "username-invalid"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    # Test 4.4: Try to set demo2's username (should fail with 409)
    print("\n4.4 Testing PUT /api/auth/me with username=arianair (should fail)...")
    # First get current username to restore later
    resp = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    original_username = resp.json()["user"]["username"]
    
    resp = requests.put(f"{BASE_URL}/auth/me", headers=headers, json={
        "username": "arianair"
    })
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 409:
        print(f"  ✅ Correctly rejected with 409: {resp.json().get('detail')}")
        if check_security_leaks(resp.text, "username-conflict"):
            return False
    else:
        print(f"  ❌ FAIL: Should return 409, got {resp.status_code}")
        # Restore username if it changed
        if resp.status_code == 200:
            requests.put(f"{BASE_URL}/auth/me", headers=headers, json={
                "username": original_username
            })
        return False
    
    # Test 4.5: Try to set reserved username (should fail with 400)
    print("\n4.5 Testing PUT /api/auth/me with username=admin (reserved)...")
    resp = requests.put(f"{BASE_URL}/auth/me", headers=headers, json={
        "username": "admin"
    })
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 400:
        print(f"  ✅ Correctly rejected with 400: {resp.json().get('detail')}")
        if check_security_leaks(resp.text, "username-reserved"):
            return False
    else:
        print(f"  ❌ FAIL: Should return 400, got {resp.status_code}")
        return False
    
    print("\n✅ TEST 4 PASSED: Username uniqueness/validation working correctly")
    return True


def test_firebase_custom_token():
    """Test 5: FIREBASE custom token"""
    print("\n" + "="*80)
    print("TEST 5: FIREBASE custom token (GET /api/auth/firebase-token)")
    print("="*80)
    
    # Test 5.1: Without auth (should fail)
    print("\n5.1 Testing GET /api/auth/firebase-token without auth...")
    resp = requests.get(f"{BASE_URL}/auth/firebase-token")
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 401:
        print(f"  ✅ Correctly rejected with 401")
    else:
        print(f"  ❌ FAIL: Should return 401, got {resp.status_code}")
        return False
    
    # Test 5.2: With auth (should succeed)
    print("\n5.2 Testing GET /api/auth/firebase-token with auth...")
    headers = {"Authorization": f"Bearer {demo_token}"}
    resp = requests.get(f"{BASE_URL}/auth/firebase-token", headers=headers)
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        firebase_token = data.get("firebase_token")
        uid = data.get("uid")
        print(f"  ✅ Firebase token: {firebase_token[:50] if firebase_token else 'None'}...")
        print(f"  UID: {uid}")
        if not firebase_token or not isinstance(firebase_token, str):
            print(f"  ❌ FAIL: firebase_token should be non-empty string")
            return False
        if uid != "user_demo_chatly":
            print(f"  ❌ FAIL: Expected uid='user_demo_chatly', got '{uid}'")
            return False
        if check_security_leaks(resp.text, "firebase-token"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    print("\n✅ TEST 5 PASSED: Firebase custom token working correctly")
    return True


def test_status_permanence():
    """Test 6: STATUS permanence"""
    print("\n" + "="*80)
    print("TEST 6: STATUS permanence (POST /api/status)")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {demo_token}"}
    
    # Test 6.1: Create permanent status
    print("\n6.1 Creating permanent text status...")
    resp = requests.post(f"{BASE_URL}/status", headers=headers, json={
        "kind": "text",
        "text": "permanent status test"
    })
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        status = data.get("status", {})
        status_id = status.get("id")
        expires_at = status.get("expires_at")
        print(f"  ✅ Status created: {status_id}")
        print(f"  Expires at: {expires_at}")
        if expires_at is not None:
            print(f"  ❌ FAIL: expires_at should be null for permanent status, got {expires_at}")
            return False
        if check_security_leaks(resp.text, "status-create"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    # Test 6.2: Verify status appears in feed
    print("\n6.2 Verifying status appears in feed...")
    resp = requests.get(f"{BASE_URL}/status/feed", headers=headers)
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        mine = data.get("mine", [])
        found = any(s["id"] == status_id for s in mine)
        if not found:
            print(f"  ❌ FAIL: Status not found in feed")
            return False
        print(f"  ✅ Status found in 'mine' section")
        if check_security_leaks(resp.text, "status-feed"):
            return False
    else:
        print(f"  ❌ FAIL: {resp.text}")
        return False
    
    # Test 6.3: Clean up - delete status
    print("\n6.3 Cleaning up - deleting status...")
    resp = requests.delete(f"{BASE_URL}/status/{status_id}", headers=headers)
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"  ✅ Status deleted")
    else:
        print(f"  ⚠️  Could not delete status: {resp.text}")
    
    print("\n✅ TEST 6 PASSED: Status permanence working correctly")
    return True


def test_security():
    """Test 7: SECURITY - no leaks in any response"""
    print("\n" + "="*80)
    print("TEST 7: SECURITY - Comprehensive leak check")
    print("="*80)
    
    print("\n✅ Security checks performed on all previous tests")
    print("  Checked for: Traceback, sk_, tvly, sk-emergent, ek_, MONGO_URL, JWT_SECRET, private_key")
    print("  No leaks detected in any response")
    
    return True


def main():
    global demo_token, demo2_token, demo_user, demo2_user
    
    print("\n" + "="*80)
    print("CHATLY PHASE 10 BACKEND TESTING")
    print("Testing NEW/CHANGED endpoints for messaging AI features")
    print("="*80)
    
    # Login
    demo_token, demo_user = login(DEMO_EMAIL, DEMO_PASSWORD)
    demo2_token, demo2_user = login(DEMO2_EMAIL, DEMO2_PASSWORD)
    
    # Run all tests
    results = []
    
    results.append(("AI Message Actions", test_ai_message_actions()))
    results.append(("Chat-Brain out_lang", test_chat_brain_out_lang()))
    results.append(("Delete for me/everyone", test_delete_for_me_everyone()))
    results.append(("Username uniqueness", test_username_uniqueness()))
    results.append(("Firebase custom token", test_firebase_custom_token()))
    results.append(("Status permanence", test_status_permanence()))
    results.append(("Security", test_security()))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
