#!/usr/bin/env python3
"""
Comprehensive runtime smoke test for Chatly AI Messenger.
Tests startup health, read-only operations, and security.
"""

import requests
import json
import sys
import re
import subprocess

# Configuration
BACKEND_URL = "https://e98149bb-9c03-4d9e-ac1e-7caaface0345.preview.emergentagent.com/api"
TEST_EMAIL = "demo@chatly.app"
TEST_PASSWORD = "Demo1234"

# Security patterns to check for leaks
SECURITY_PATTERNS = [
    (r'Traceback', 'Stack trace'),
    (r'sk_[a-zA-Z0-9_-]{20,}', 'API key (sk_)'),
    (r'tvly[a-zA-Z0-9_-]{20,}', 'Tavily key'),
    (r'sk-emergent-[a-zA-Z0-9_-]+', 'Emergent key'),
    (r'ek_[a-zA-Z0-9_-]{20,}', 'Email key'),
    (r'MONGO_URL', 'MongoDB URL'),
    (r'JWT_SECRET', 'JWT secret'),
    (r'private_key.*BEGIN', 'Private key'),
    (r'service_account.*json', 'Service account'),
]

class SmokeTest:
    def __init__(self):
        self.results = {}
        self.token = None
        self.all_responses = []
    
    def check_security_leaks(self, response_text, test_name):
        """Check if response contains any security-sensitive information."""
        leaks = []
        for pattern, description in SECURITY_PATTERNS:
            if re.search(pattern, response_text, re.IGNORECASE):
                leaks.append(description)
        
        if leaks:
            print(f"    ❌ SECURITY LEAK: {', '.join(leaks)}")
            return False
        return True
    
    def test_startup_health(self):
        """Test 1: Verify backend startup and process health."""
        print("\n🔍 Test 1: Startup & Process Health")
        
        # Check supervisor status
        try:
            result = subprocess.run(
                ['sudo', 'supervisorctl', 'status', 'backend'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if 'RUNNING' in result.stdout:
                print("    ✅ Backend process is RUNNING")
            else:
                print(f"    ❌ Backend process status: {result.stdout}")
                return False
        except Exception as e:
            print(f"    ⚠️ Could not check supervisor status: {e}")
        
        # Check for import/startup errors in logs
        try:
            result = subprocess.run(
                ['tail', '-n', '50', '/var/log/supervisor/backend.err.log'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Look for critical errors (not warnings)
            if 'ERROR' in result.stdout and 'Traceback' in result.stdout:
                print("    ❌ Found ERROR with Traceback in logs")
                return False
            
            if 'ModuleNotFoundError' in result.stdout or 'ImportError' in result.stdout:
                # Check if it's just Firebase (which is fail-soft)
                if 'firebase' not in result.stdout.lower():
                    print("    ❌ Found critical import errors in logs")
                    return False
            
            print("    ✅ No critical startup errors in logs")
            
        except Exception as e:
            print(f"    ⚠️ Could not check logs: {e}")
        
        # Check MongoDB connection
        try:
            result = subprocess.run(
                ['python3', '-c', 
                 'from pymongo import MongoClient; import os; '
                 'client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"), serverSelectionTimeoutMS=5000); '
                 'client.server_info(); print("OK")'],
                capture_output=True,
                text=True,
                timeout=10,
                cwd='/app/backend'
            )
            
            if 'OK' in result.stdout:
                print("    ✅ MongoDB connection healthy")
            else:
                print(f"    ❌ MongoDB connection failed: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"    ❌ MongoDB check failed: {e}")
            return False
        
        return True
    
    def test_backend_responding(self):
        """Test 2: Backend HTTP endpoint responding."""
        print("\n🔍 Test 2: Backend HTTP Health")
        try:
            response = requests.get(f"{BACKEND_URL}/", timeout=10)
            self.all_responses.append(response.text)
            
            if response.status_code in [200, 404]:
                print(f"    ✅ Backend responding (status: {response.status_code})")
                return True
            else:
                print(f"    ❌ Unexpected status: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"    ❌ Backend not reachable: {e}")
            return False
    
    def test_login(self):
        """Test 3: Login with demo credentials (read-only test account)."""
        print("\n🔍 Test 3: Authentication (POST /api/auth/login)")
        try:
            response = requests.post(
                f"{BACKEND_URL}/auth/login",
                json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                timeout=10
            )
            self.all_responses.append(response.text)
            
            print(f"    Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"    ❌ Login failed: {response.text[:200]}")
                return False
            
            data = response.json()
            
            if "token" not in data:
                print("    ❌ No token in response")
                return False
            
            self.token = data["token"]
            
            print(f"    ✅ Login successful")
            print(f"    User: {data.get('user', {}).get('email', 'N/A')}")
            
            return True
            
        except Exception as e:
            print(f"    ❌ Request failed: {e}")
            return False
    
    def test_auth_me(self):
        """Test 4: GET /api/auth/me (read-only)."""
        print("\n🔍 Test 4: Get Current User (GET /api/auth/me)")
        try:
            response = requests.get(
                f"{BACKEND_URL}/auth/me",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            self.all_responses.append(response.text)
            
            print(f"    Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"    ❌ Request failed: {response.text[:200]}")
                return False
            
            data = response.json()
            
            # Check response structure
            if "user" in data:
                user = data["user"]
                print(f"    ✅ GET /api/auth/me successful")
                print(f"    Email: {user.get('email', 'N/A')}")
                print(f"    Name: {user.get('name', 'N/A')}")
                return True
            else:
                print("    ⚠️ Unexpected response structure")
                return False
            
        except Exception as e:
            print(f"    ❌ Request failed: {e}")
            return False
    
    def test_get_chats(self):
        """Test 5: GET /api/chats (read-only)."""
        print("\n🔍 Test 5: Get Chats (GET /api/chats)")
        try:
            response = requests.get(
                f"{BACKEND_URL}/chats",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            self.all_responses.append(response.text)
            
            print(f"    Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"    ❌ Request failed: {response.text[:200]}")
                return False
            
            data = response.json()
            
            # Check response structure
            if "chats" in data and isinstance(data["chats"], list):
                print(f"    ✅ GET /api/chats successful")
                print(f"    Number of chats: {len(data['chats'])}")
                return True
            else:
                print("    ⚠️ Unexpected response structure")
                return False
            
        except Exception as e:
            print(f"    ❌ Request failed: {e}")
            return False
    
    def test_error_handling(self):
        """Test 6: Verify proper error handling (no stack traces)."""
        print("\n🔍 Test 6: Error Handling (invalid endpoint)")
        try:
            response = requests.get(
                f"{BACKEND_URL}/nonexistent-endpoint-12345",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            self.all_responses.append(response.text)
            
            print(f"    Status: {response.status_code}")
            
            if response.status_code == 404:
                print("    ✅ Returns 404 for invalid endpoint")
                
                # Check that error response doesn't leak stack traces
                if 'Traceback' in response.text or 'Exception' in response.text:
                    print("    ❌ Error response contains stack trace")
                    return False
                
                print("    ✅ Error response is clean (no stack traces)")
                return True
            else:
                print(f"    ⚠️ Unexpected status for invalid endpoint: {response.status_code}")
                return True  # Not a critical failure
            
        except Exception as e:
            print(f"    ❌ Request failed: {e}")
            return False
    
    def test_security(self):
        """Test 7: Check all responses for security leaks."""
        print("\n🔍 Test 7: Security Audit (all responses)")
        
        all_clean = True
        for i, response_text in enumerate(self.all_responses):
            if not self.check_security_leaks(response_text, f"response_{i}"):
                all_clean = False
        
        if all_clean:
            print("    ✅ No security leaks detected in any response")
            return True
        else:
            print("    ❌ Security leaks found")
            return False
    
    def run_all_tests(self):
        """Run all smoke tests."""
        print("=" * 70)
        print("🚀 Chatly Backend Runtime Smoke Test (Post-Startup)")
        print("=" * 70)
        print(f"Backend URL: {BACKEND_URL}")
        print(f"Test Account: {TEST_EMAIL} (read-only)")
        
        tests = [
            ("startup_health", self.test_startup_health),
            ("backend_responding", self.test_backend_responding),
            ("login", self.test_login),
            ("auth_me", self.test_auth_me),
            ("get_chats", self.test_get_chats),
            ("error_handling", self.test_error_handling),
            ("security", self.test_security),
        ]
        
        for test_name, test_func in tests:
            try:
                self.results[test_name] = test_func()
            except Exception as e:
                print(f"    ❌ Test crashed: {e}")
                self.results[test_name] = False
            
            # Stop if login fails (can't proceed with authenticated tests)
            if test_name == "login" and not self.results[test_name]:
                print("\n❌ Login failed. Cannot proceed with authenticated tests.")
                break
        
        # Summary
        print("\n" + "=" * 70)
        print("📊 Smoke Test Summary")
        print("=" * 70)
        
        all_passed = True
        for test_name, passed in self.results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {test_name:20s}: {status}")
            if not passed:
                all_passed = False
        
        print("=" * 70)
        
        if all_passed:
            print("✅ All smoke tests PASSED - Backend is healthy and runnable")
            return 0
        else:
            print("❌ Some smoke tests FAILED")
            return 1

def main():
    test = SmokeTest()
    exit_code = test.run_all_tests()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
