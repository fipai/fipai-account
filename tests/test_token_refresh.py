"""
Token 刷新机制测试

验证:
1. Cookie 刷新测试
2. 跨域刷新测试
3. Token 撤回测试
4. Cookie 刷新契约测试(04UnifiedPortal ↔ 07Account 协作约束)
"""
import json
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from accounts.jwt import (
    FIPAccessToken,
    FIPRefreshToken as RefreshToken,
    issue_token_pair,
)
from accounts.models import AuthSession


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
        # 获取已登记服务端 family 的 refresh token
        _, refresh_token = issue_token_pair(self.user)

        response = self.client.post(
            '/api/auth/token/refresh/',
            data=json.dumps({'refresh': refresh_token}),
            content_type='application/json'
        )

        # 成功时返回 200
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)

    def test_token_refresh_cookie_fallback(self):
        """当请求体无 refresh token 时从 Cookie 读取"""
        _, refresh_token_str = issue_token_pair(self.user)

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


class CookieTokenRefreshContractTests(TestCase):
    """04UnifiedPortal ↔ 07Account cookie 刷新契约测试。

    这些测试锁定的契约是 PR-04-UP-02 之后 04UnifiedPortal 实际依赖的行为:
    1. 客户端只发送空 body + HttpOnly fip_refresh_token cookie
    2. 07Account 必须能识别 cookie 中的 refresh 并完成 rotation
    3. 显式 body.refresh 必须优先于 cookie(防止 cookie 跨账号污染)
    4. Cookie-only 路径必须享有与 body 路径同等的安全语义(rotation、reuse 检测)
    5. 响应必须重新设置两个 cookie,确保客户端保持同步

    如果 07Account 改坏了其中任何一条,这些测试应当立即失败,
    防止 04UnifiedPortal 在生产环境出现 401 风暴或安全降级。
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='13800001111',
            password='Passw0rd123',
            email='contract@example.com',
        )
        self.client = APIClient()

    def _refresh_post(self, body=None, cookies=None):
        if cookies:
            for name, value in cookies.items():
                self.client.cookies[name] = value
        return self.client.post(
            '/api/auth/token/refresh/',
            data=json.dumps(body) if body is not None else '',
            content_type='application/json',
        )

    def test_empty_body_with_valid_cookie_rotates_family_and_sets_new_cookies(self):
        """04UnifiedPortal 实际请求:空 body + cookie → 200 + 新 access/refresh + 新 cookie。

        锁定契约:客户端不再需要在 body 里携带 refresh。
        """
        _, original_refresh = issue_token_pair(self.user)
        original_sid = RefreshToken(original_refresh)['sid']
        original_jti = RefreshToken(original_refresh)['jti']

        response = self._refresh_post(
            body={},
            cookies={'fip_refresh_token': original_refresh},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertNotEqual(response.data['refresh'], original_refresh)
        new_refresh_claims = RefreshToken(response.data['refresh'])
        new_access_claims = FIPAccessToken(response.data['access'])
        self.assertEqual(new_refresh_claims['sid'], original_sid)
        self.assertEqual(new_access_claims['sid'], original_sid)
        self.assertNotEqual(new_refresh_claims['jti'], original_jti)
        self.assertIn('fip_access_token', response.cookies)
        self.assertIn('fip_refresh_token', response.cookies)
        self.assertEqual(
            response.cookies['fip_refresh_token'].value,
            response.data['refresh'],
        )
        session = AuthSession.objects.get(sid=original_sid)
        self.assertEqual(session.current_refresh_jti, new_refresh_claims['jti'])
        self.assertIsNone(session.revoked_at)

    def test_empty_body_without_cookie_fails_closed_with_401(self):
        """空 body 且无 cookie → 401。不允许静默成功也不允许 500。"""
        response = self._refresh_post(body={})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)
        self.assertNotIn('fip_access_token', response.cookies)

    def test_body_refresh_takes_precedence_over_cookie_from_different_family(self):
        """显式 body.refresh 必须优先于 cookie.refresh。

        安全:如果 cookie 是别的设备/账号的旧 token,不能让它劫持请求。
        锁定契约:body 里的 token 才是 authoritative,cookie 只在 body 缺失时使用。
        """
        _, body_refresh = issue_token_pair(self.user)
        _, cookie_refresh = issue_token_pair(self.user)
        body_sid = RefreshToken(body_refresh)['sid']
        cookie_sid = RefreshToken(cookie_refresh)['sid']
        body_jti = RefreshToken(body_refresh)['jti']
        cookie_jti = RefreshToken(cookie_refresh)['jti']
        self.assertNotEqual(body_sid, cookie_sid)

        response = self._refresh_post(
            body={'refresh': body_refresh},
            cookies={'fip_refresh_token': cookie_refresh},
        )

        self.assertEqual(response.status_code, 200)
        rotated_sid = RefreshToken(response.data['refresh'])['sid']
        self.assertEqual(rotated_sid, body_sid)
        self.assertNotEqual(rotated_sid, cookie_sid)
        cookie_session = AuthSession.objects.get(sid=cookie_sid)
        self.assertIsNone(cookie_session.revoked_at)
        self.assertEqual(cookie_session.current_refresh_jti, cookie_jti)
        body_session = AuthSession.objects.get(sid=body_sid)
        self.assertEqual(body_session.current_refresh_jti, RefreshToken(response.data['refresh'])['jti'])
        self.assertNotEqual(body_session.current_refresh_jti, body_jti)

    def test_body_refresh_only_keeps_backward_compatibility(self):
        """纯 body 路径(无 cookie)必须继续工作,不能因为新加 cookie 路径而破坏旧客户端。"""
        _, refresh = issue_token_pair(self.user)
        response = self._refresh_post(body={'refresh': refresh})
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertNotEqual(response.data['refresh'], refresh)

    def test_cookie_reuse_after_rotation_revokes_whole_family(self):
        """Cookie 路径必须享有与 body 路径同等的 reuse 检测:旧 cookie 再次使用 → family 撤销。"""
        _, original_refresh = issue_token_pair(self.user)
        sid = RefreshToken(original_refresh)['sid']

        first = self._refresh_post(
            body={},
            cookies={'fip_refresh_token': original_refresh},
        )
        self.assertEqual(first.status_code, 200)

        reuse = self._refresh_post(
            body={},
            cookies={'fip_refresh_token': original_refresh},
        )
        self.assertEqual(reuse.status_code, 401)
        session = AuthSession.objects.get(sid=sid)
        self.assertEqual(session.revoked_reason, 'refresh_reuse')
        self.assertIsNotNone(session.reuse_detected_at)

    def test_invalid_body_refresh_does_not_silently_fall_back_to_valid_cookie(self):
        """body.refresh 无效时,绝对不能静默回退到 cookie。

        安全契约:body 是 explicit,cookie 是 implicit。一旦客户端在 body 里
        显式给了 token,服务端只信任 body。如果回退到 cookie,等于把 explicit
        选择降级为 implicit,可能让攻击者通过操纵 body 触发意料外的 cookie 路径。
        因此:body 有 refresh 字段(无论值是否有效)→ 只用 body,失败就 401。
        """
        _, valid_cookie_refresh = issue_token_pair(self.user)
        cookie_sid = RefreshToken(valid_cookie_refresh)['sid']

        response = self._refresh_post(
            body={'refresh': 'garbage.not.a.token'},
            cookies={'fip_refresh_token': valid_cookie_refresh},
        )

        self.assertEqual(response.status_code, 401)
        cookie_session = AuthSession.objects.get(sid=cookie_sid)
        self.assertIsNone(cookie_session.revoked_at)
        self.assertEqual(
            cookie_session.current_refresh_jti,
            RefreshToken(valid_cookie_refresh)['jti'],
        )

    def test_cookie_with_invalid_signature_fails_401(self):
        """Cookie 里的 refresh 签名错误 → 401,不静默降级。"""
        bogus = 'eyJhbGciOiJSUzI1NiJ9.eyJ0eXBlIjoicmVmcmVzaCIsInVzZXJfaWQiOjF9.invalidsig'
        response = self._refresh_post(
            body={},
            cookies={'fip_refresh_token': bogus},
        )
        self.assertEqual(response.status_code, 401)
