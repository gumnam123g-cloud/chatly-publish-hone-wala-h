#!/usr/bin/env python3
"""Quick test of just the research endpoint"""
import requests
import json

BASE_URL = "https://chatly-app-3.preview.emergentagent.com/api"
TEST_EMAIL = "demo@chatly.app"
TEST_PASSWORD = "Demo1234"

# Login
print("Logging in...")
response = requests.post(f"{BASE_URL}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=30)
token = response.json()["token"]
print(f"Token: {token[:20]}...")

# Test research
print("\nTesting POST /api/ai/research...")
response = requests.post(
    f"{BASE_URL}/ai/research",
    headers={"Authorization": f"Bearer {token}"},
    json={"query": "latest news on AI"},
    timeout=120
)

print(f"Status: {response.status_code}")
print(f"Headers: {dict(response.headers)}")
print(f"Body (first 500 chars): {response.text[:500]}")

if response.status_code == 200:
    data = response.json()
    print(f"\n✅ SUCCESS")
    print(f"Report length: {len(data.get('report', ''))}")
    print(f"Sources: {len(data.get('sources', []))}")
elif response.status_code == 503:
    try:
        data = response.json()
        print(f"\n⚠️  503 Structured Error (acceptable):")
        print(json.dumps(data, indent=2))
    except:
        print(f"\n❌ 503 but not JSON")
else:
    print(f"\n❌ FAILED")
