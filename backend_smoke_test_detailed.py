#!/usr/bin/env python3
"""
Detailed smoke test to inspect actual response structures.
"""

import requests
import json

BACKEND_URL = "https://e98149bb-9c03-4d9e-ac1e-7caaface0345.preview.emergentagent.com/api"
TEST_EMAIL = "demo@chatly.app"
TEST_PASSWORD = "Demo1234"

print("=" * 60)
print("Detailed Response Inspection")
print("=" * 60)

# Login
print("\n1. Login...")
response = requests.post(
    f"{BACKEND_URL}/auth/login",
    json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    timeout=10
)
print(f"Status: {response.status_code}")
data = response.json()
token = data.get("token")
print(f"Response keys: {list(data.keys())}")
print(f"Token present: {token is not None}")

if token:
    # GET /api/auth/me
    print("\n2. GET /api/auth/me...")
    response = requests.get(
        f"{BACKEND_URL}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10
    )
    print(f"Status: {response.status_code}")
    print(f"Response type: {type(response.json())}")
    data = response.json()
    print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
    print(f"Full response (first 500 chars):\n{json.dumps(data, indent=2)[:500]}")
    
    # GET /api/chats
    print("\n3. GET /api/chats...")
    response = requests.get(
        f"{BACKEND_URL}/chats",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10
    )
    print(f"Status: {response.status_code}")
    print(f"Response type: {type(response.json())}")
    data = response.json()
    if isinstance(data, list):
        print(f"Number of items: {len(data)}")
        if len(data) > 0:
            print(f"First item keys: {list(data[0].keys())}")
    elif isinstance(data, dict):
        print(f"Response keys: {list(data.keys())}")
        print(f"Full response (first 500 chars):\n{json.dumps(data, indent=2)[:500]}")
    else:
        print(f"Unexpected type: {type(data)}")
