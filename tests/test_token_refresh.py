"""
Token 刷新机制测试

验证:
1. Cookie 刷新测试
2. 跨域刷新测试
3. Token 撤回测试
"""
import json
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


class TokenRefreshTest(TestCase):
    """Token 刷新测试"""

    def setUp(self):
        """创建测试用户"""
        User = get_user_model()
        self.user = User.objects.create_user(
            username='13800000000',
            password='testpass123',
            email='test@example.com'
        )
        self.client = APIClient()

    def test_token_refresh_with_valid_token(self):
        """使用有效的 refresh token 刷新"""
        # 获取 refresh token
        refresh = RefreshToken.for_user(self.user)

        response = self.client.post(
            '/api/auth/token/refresh/',
            data=json.dumps({'refresh': str(refresh)}),
            content_type='application/json'
        )

        # 成功时返回 200
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)

    def test_token_refresh_cookie_fallback(self):
        """当请求体无 refresh token 时从 Cookie 读取"""
        # 获取 refresh token
        refresh = RefreshToken.for_user(self.user)
        refresh_token_str = str(refresh)

        # 模拟带 Cookie 的请求
        self.client.cookies['fip_refresh_token'] = refresh_token_str

        response = self.client.post('/api/auth/token/refresh/', {})

        self.assertEqual(response.status_code, 200)

    def test_token_refresh_invalid_token(self):
        """无效的 refresh token 返回错误"""
        response = self.client.post(
            '/api/auth/token/refresh/',
            data=json.dumps({'refresh': 'invalid_token'}),
            content_type='application/json'
        )

        # 应该返回非 200 状态码
        self.assertNotEqual(response.status_code, 200)


class TokenRefreshCrossDomainTest(TestCase):
    """跨域 Token 刷新测试"""

    def setUp(self):
        """创建测试用户"""
        User = get_user_model()
        self.user = User.objects.create_user(
            username='13800000001',
            password='testpass123',
            email='test2@example.com'
        )

    @override_settings(
        ALLOWED_HOSTS=['account.fipai.cn', 'localhost', '127.0.0.1'],
        DEBUG=False,
    )
    def test_cookie_domain_for_subdomain(self):
        """验证子域名设置正确的 Cookie domain"""
        from accounts.views import _sso_cookie_domain

        # 模拟 account.fipai.cn 的请求
        class MockRequest:
            def get_host(self):
                return 'account.fipai.cn'

        request = MockRequest()
        domain = _sso_cookie_domain(request)

        # 应该返回 .fipai.cn 以支持跨子域
        self.assertEqual(domain, '.fipai.cn')

    @override_settings(
        ALLOWED_HOSTS=['localhost'],
        DEBUG=True,
    )
    def test_cookie_domain_localhost(self):
        """localhost 不设置 domain"""
        from accounts.views import _sso_cookie_domain

        class MockRequest:
            def get_host(self):
                return 'localhost'

        request = MockRequest()
        domain = _sso_cookie_domain(request)

        # localhost 不应设置 domain
        self.assertIsNone(domain)


class LogoutTokenRevocationTest(TestCase):
    """登出 Token 撤回测试"""

    def setUp(self):
        """创建测试用户"""
        User = get_user_model()
        self.user = User.objects.create_user(
            username='13800000002',
            password='testpass123',
            email='test3@example.com'
        )
        self.client = APIClient()

    def test_logout_clears_cookies(self):
        """登出时清除 SSO cookies"""
        response = self.client.post('/api/auth/logout/')

        self.assertEqual(response.status_code, 200)
        # 验证 Cookie 被清除
        self.assertIn('fip_access_token', response.cookies)
        self.assertIn('fip_refresh_token', response.cookies)

    def test_logout_no_auth_required(self):
        """登出不需要认证"""
        response = self.client.post('/api/auth/logout/')

        self.assertEqual(response.status_code, 200)
        # 即使没有 token 也应该成功
        self.assertTrue(response.data.get('ok'))
