"""
Performance Baseline Tests

验证关键 API 响应时间满足性能基线要求:
- p95 < 500ms for all endpoints
- p95 < 1s for high-latency endpoints (payment processing)

这些测试用于在 CI/CD 中确保性能不回归。
"""
import time
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from payments.models import PaymentTransaction
from subscriptions.models import Subscription, SubscriptionPlan


class PerformanceBaselineTest(TestCase):
    """Performance baseline tests for Account API"""

    def setUp(self):
        self.client = APIClient()
        self.client.raise_request_exception = False
        self.user_model = get_user_model()

        # Create test user
        self.user = self.user_model.objects.create_user(
            username='perf_test_user',
            email='perf@test.com',
            password='testpass123'
        )

        # Create test plan
        self.plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='professional',
            name='DataCognis Pro',
            period='monthly',
            price=Decimal('99.00'),
        )

        # Create subscription
        self.subscription = Subscription.objects.create(
            user=self.user,
            plan=self.plan,
            status='active',
        )

        # Generate JWT token
        refresh = RefreshToken.for_user(self.user)
        self.access_token = str(refresh.access_token)

    def _auth_headers(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.access_token}'}

    def _measure_response_time(self, func, *args, iterations=10, **kwargs):
        """Measure average response time over multiple iterations"""
        times = []
        for _ in range(iterations):
            start = time.time()
            func(*args, **kwargs)
            elapsed = (time.time() - start) * 1000  # Convert to ms
            times.append(elapsed)
        return {
            'avg': sum(times) / len(times),
            'min': min(times),
            'max': max(times),
            'times': sorted(times),
            'p95': times[int(len(times) * 0.95)] if len(times) >= 20 else times[-1],
            'p99': times[int(len(times) * 0.99)] if len(times) >= 100 else times[-1],
        }

    def test_auth_me_response_time(self):
        """验证 /api/auth/me/ 响应时间 p95 < 500ms"""
        # Warm up
        self.client.get('/api/auth/me/', **self._auth_headers())

        times = []
        for _ in range(20):
            start = time.time()
            resp = self.client.get('/api/auth/me/', **self._auth_headers())
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
            self.assertEqual(resp.status_code, 200)

        times.sort()
        p95 = times[int(len(times) * 0.95)]
        avg = sum(times) / len(times)

        print(f"\n[Performance] /api/auth/me/ - avg: {avg:.2f}ms, p95: {p95:.2f}ms")
        self.assertLess(p95, 500, f"p95 response time {p95:.2f}ms exceeds 500ms threshold")

    def test_subscriptions_list_response_time(self):
        """验证 /api/subscriptions/ 响应时间 p95 < 500ms"""
        # Warm up
        self.client.get('/api/subscriptions/', **self._auth_headers())

        times = []
        for _ in range(20):
            start = time.time()
            resp = self.client.get('/api/subscriptions/', **self._auth_headers())
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
            self.assertEqual(resp.status_code, 200)

        times.sort()
        p95 = times[int(len(times) * 0.95)]
        avg = sum(times) / len(times)

        print(f"\n[Performance] /api/subscriptions/ - avg: {avg:.2f}ms, p95: {p95:.2f}ms")
        self.assertLess(p95, 500, f"p95 response time {p95:.2f}ms exceeds 500ms threshold")

    def test_tenants_list_response_time(self):
        """验证 /api/tenants/ 响应时间 p95 < 500ms"""
        # Warm up
        self.client.get('/api/tenants/', **self._auth_headers())

        times = []
        for _ in range(20):
            start = time.time()
            resp = self.client.get('/api/tenants/', **self._auth_headers())
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
            self.assertEqual(resp.status_code, 200)

        times.sort()
        p95 = times[int(len(times) * 0.95)]
        avg = sum(times) / len(times)

        print(f"\n[Performance] /api/tenants/ - avg: {avg:.2f}ms, p95: {p95:.2f}ms")
        self.assertLess(p95, 500, f"p95 response time {p95:.2f}ms exceeds 500ms threshold")

    def test_payments_list_response_time(self):
        """验证 /api/payments/ 响应时间 p95 < 500ms"""
        # Warm up
        self.client.get('/api/payments/', **self._auth_headers())

        times = []
        for _ in range(20):
            start = time.time()
            resp = self.client.get('/api/payments/', **self._auth_headers())
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
            self.assertEqual(resp.status_code, 200)

        times.sort()
        p95 = times[int(len(times) * 0.95)]
        avg = sum(times) / len(times)

        print(f"\n[Performance] /api/payments/ - avg: {avg:.2f}ms, p95: {p95:.2f}ms")
        self.assertLess(p95, 500, f"p95 response time {p95:.2f}ms exceeds 500ms threshold")

    def test_send_code_response_time(self):
        """验证 /api/auth/send-code/ 响应时间 p95 < 500ms"""
        times = []
        for i in range(20):
            start = time.time()
            resp = self.client.post('/api/auth/send-code/', {
                'phone': f'1380000{100 + i}',
                'purpose': 'login'
            }, format='json')
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
            # May return 200 (mock) or 400 (invalid phone in production)

        times.sort()
        p95 = times[int(len(times) * 0.95)]
        avg = sum(times) / len(times)

        print(f"\n[Performance] /api/auth/send-code/ - avg: {avg:.2f}ms, p95: {p95:.2f}ms")
        self.assertLess(p95, 500, f"p95 response time {p95:.2f}ms exceeds 500ms threshold")

    def test_concurrent_requests_no_errors(self):
        """验证连续请求不会导致错误（串行测试，并发在 locustfile.py 中测试）"""
        errors = []
        for _ in range(20):
            resp = self.client.get('/api/auth/me/', **self._auth_headers())
            if resp.status_code >= 500:
                errors.append(f"Status {resp.status_code}")

        print(f"\n[Sequential] Made 20 requests with {len(errors)} errors")
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors[:5]}")
