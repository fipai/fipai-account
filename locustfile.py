"""
Locust Performance Test Script for FIP.AI Account API

Usage:
    locust -f locustfile.py --host=http://localhost:8000

For headless mode (outputting to file):
    locust -f locustfile.py --host=http://localhost:8000 \
        --headless -u 100 -r 10 -t 60s --csv=/tmp/locust_results

Scenarios:
- /api/auth/send-code/ - Send SMS verification code
- /api/auth/login/phone/ - Phone number login
- /api/auth/me/ - Get current user info
- /api/subscriptions/ - List subscriptions
"""
import random
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner

# Test configuration
BASE_URL = ""  # Will be set via --host flag
TEST_PHONE_PREFIX = "1380000"  # Phone numbers will be 1380000XXX


class AccountAPIUser(HttpUser):
    """Simulates a user interacting with Account API"""

    # Wait 0.5-2 seconds between tasks
    wait_time = between(0.5, 2.0)

    def on_start(self):
        """Called when a simulated user starts. Register and login."""
        self.user_id = None
        self.access_token = None
        self.phone = f"{TEST_PHONE_PREFIX}{random.randint(100, 999)}"
        self._register_and_login()

    def _register_and_login(self):
        """Register a new user or login with existing credentials"""
        # Step 1: Send SMS code for login
        phone = self.phone
        send_code_payload = {
            "phone": phone,
            "purpose": "login"
        }

        # Note: In production, you would need valid SMS codes
        # For load testing, we use the mock SMS service
        self.client.post("/api/auth/send-code/", json=send_code_payload)

        # Step 2: Login with the code (mock code "123456" works in test mode)
        login_payload = {
            "phone": phone,
            "code": "123456"
        }

        response = self.client.post("/api/auth/login/phone/", json=login_payload)

        if response.status_code == 200:
            data = response.json()
            if data.get("access"):
                self.access_token = data["access"]
                self.user_id = data.get("user_id")

    def _auth_headers(self):
        """Get authorization headers"""
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        return {}

    @task(10)
    def get_current_user(self):
        """GET /api/auth/me/ - Get current user info (high frequency)"""
        self.client.get("/api/auth/me/", headers=self._auth_headers())

    @task(5)
    def send_verification_code(self):
        """POST /api/auth/send-code/ - Send SMS verification code"""
        payload = {
            "phone": f"{TEST_PHONE_PREFIX}{random.randint(100, 999)}",
            "purpose": random.choice(["login", "register"])
        }
        self.client.post("/api/auth/send-code/", json=payload)

    @task(3)
    def phone_login(self):
        """POST /api/auth/login/phone/ - Phone number login"""
        payload = {
            "phone": self.phone,
            "code": "123456"
        }
        self.client.post("/api/auth/login/phone/", json=payload)

    @task(2)
    def list_subscriptions(self):
        """GET /api/subscriptions/ - List user subscriptions"""
        self.client.get("/api/subscriptions/", headers=self._auth_headers())

    @task(1)
    def list_plans(self):
        """GET /api/subscriptions/plans/ - List available plans"""
        self.client.get("/api/subscriptions/plans/")

    @task(1)
    def list_teams(self):
        """GET /api/teams/ - List teams"""
        self.client.get("/api/teams/", headers=self._auth_headers())

    @task(1)
    def list_tenants(self):
        """GET /api/tenants/ - List tenants"""
        self.client.get("/api/tenants/", headers=self._auth_headers())

    @task(1)
    def list_payments(self):
        """GET /api/payments/ - List payment transactions"""
        self.client.get("/api/payments/", headers=self._auth_headers())


class HeavyUser(HttpUser):
    """Simulates a heavy user making more requests"""

    wait_time = between(0.2, 0.5)

    def on_start(self):
        self.access_token = None
        self.phone = f"{TEST_PHONE_PREFIX}{random.randint(100, 999)}"
        self._register_and_login()

    def _register_and_login(self):
        # Quick login flow
        self.client.post("/api/auth/send-code/", json={
            "phone": self.phone,
            "purpose": "login"
        })

        response = self.client.post("/api/auth/login/phone/", json={
            "phone": self.phone,
            "code": "123456"
        })

        if response.status_code == 200:
            data = response.json()
            self.access_token = data.get("access")

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.access_token}"} if self.access_token else {}

    @task(20)
    def get_current_user(self):
        self.client.get("/api/auth/me/", headers=self._auth_headers())

    @task(10)
    def list_subscriptions(self):
        self.client.get("/api/subscriptions/", headers=self._auth_headers())


# Event handlers for collecting metrics
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when the test starts"""
    print(f"Starting load test with {environment.runner.user_count if hasattr(environment.runner, 'user_count') else 'N'} users")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Called after each request"""
    pass  # Could add custom logging here


@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """Called when the test is about to quit"""
    if hasattr(environment.runner, 'stats'):
        stats = environment.runner.stats
        print(f"\n=== Load Test Summary ===")
        print(f"Total requests: {stats.total.num_requests}")
        print(f"Total failures: {stats.total.num_failures}")
        if stats.total.num_requests > 0:
            print(f"Average response time: {stats.total.avg_response_time:.2f}ms")
            print(f"Median response time: {stats.total.median_response_time:.2f}ms")
            print(f"95th percentile: {stats.total.get_response_time_percentile(0.95):.2f}ms")
            print(f"99th percentile: {stats.total.get_response_time_percentile(0.99):.2f}ms")
