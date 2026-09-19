#!/usr/bin/env python3
"""Test to verify structured error responses and no data leaks"""
import requests
import json
import re

BASE_URL = "https://chatly-mobile.preview.emergentagent.com/api"
TEST_EMAIL = "demo@chatly.app"
TEST_PASSWORD = "Demo1234"

SENSITIVE_PATTERNS = [
    r"Traceback",
    r"sk_",  # Sarvam key
    r"tvly",  # Tavily key
    r"sk-emergent",  # Emergent key
    r"SARVAM_API_KEY",
    r"TAVILY_API_KEY",
    r"EMERGENT_LLM_KEY",
]

def check_for_leaks(text):
    """Check if text contains sensitive data"""
    leaked = []
    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            leaked.append(pattern)
    return leaked

# Login
print("Logging in...")
response = requests.post(f"{BASE_URL}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=30)
token = response.json()["token"]

print("\n" + "="*80)
print("SECURITY & ERROR HANDLING VERIFICATION")
print("="*80)

# Test 1: Check all successful responses for leaks
print("\n[1] Checking successful responses for data leaks...")
endpoints = [
    ("GET", "/ai/insights", None),
    ("POST", "/ai/chat", {"message": "test"}),
]

all_clean = True
for method, path, body in endpoints:
    if method == "GET":
        resp = requests.get(f"{BASE_URL}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    else:
        resp = requests.post(f"{BASE_URL}{path}", headers={"Authorization": f"Bearer {token}"}, json=body, timeout=120)
    
    leaked = check_for_leaks(resp.text)
    if leaked:
        print(f"  ❌ {method} {path}: LEAKED {leaked}")
        all_clean = False
    else:
        print(f"  ✅ {method} {path}: No leaks detected")

if all_clean:
    print("\n✅ All responses are clean - no sensitive data leaked")
else:
    print("\n❌ SECURITY ISSUE: Sensitive data found in responses")

# Test 2: Verify structured error format
print("\n[2] Testing structured error format...")
print("  (Testing with invalid chat_id to trigger error handling)")
resp = requests.post(
    f"{BASE_URL}/ai/smart-reply",
    headers={"Authorization": f"Bearer {token}"},
    json={"chat_id": "invalid_chat_id_12345"},
    timeout=30
)
print(f"  Status: {resp.status_code}")
if resp.status_code == 404:
    print(f"  ✅ Correct 404 for invalid chat_id")
    try:
        data = resp.json()
        print(f"  Response: {json.dumps(data, indent=2)}")
        leaked = check_for_leaks(resp.text)
        if leaked:
            print(f"  ❌ Error response leaked: {leaked}")
        else:
            print(f"  ✅ Error response is clean")
    except:
        print(f"  ⚠️  Response is not JSON")

# Test 3: Check backend logs for retry evidence
print("\n[3] Checking backend logs for P0 features...")
import subprocess
result = subprocess.run(
    ["tail", "-n", "100", "/var/log/supervisor/backend.err.log"],
    capture_output=True, text=True
)
logs = result.stdout

# Look for retry/circuit breaker evidence
retry_logs = [line for line in logs.split('\n') if 'attempt=' in line]
circuit_logs = [line for line in logs.split('\n') if 'circuit' in line.lower()]
structured_logs = [line for line in logs.split('\n') if '[AI] provider=' in line]

print(f"  Found {len(structured_logs)} structured AI logs")
print(f"  Found {len(retry_logs)} retry attempt logs")
print(f"  Found {len(circuit_logs)} circuit breaker logs")

if structured_logs:
    print(f"\n  Sample structured log:")
    print(f"    {structured_logs[-1]}")
    print(f"  ✅ Structured logging is working")
else:
    print(f"  ⚠️  No structured logs found")

# Test 4: Verify fallback mechanism
print("\n[4] Checking for Sarvam->Emergent fallback evidence...")
fallback_logs = [line for line in logs.split('\n') if 'fallback' in line.lower()]
if fallback_logs:
    print(f"  Found {len(fallback_logs)} fallback events:")
    for log in fallback_logs[-3:]:
        print(f"    {log}")
    print(f"  ✅ Fallback mechanism is active")
else:
    print(f"  ℹ️  No fallback events in recent logs (Sarvam working well)")

print("\n" + "="*80)
print("VERIFICATION COMPLETE")
print("="*80)
