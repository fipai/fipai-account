"""
JWT Token Claims Tests

验证 JWT Token 包含正确的 claims:
- user_id
- tenant_id
- product_scopes
- roles
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import SMSCode
from subscriptions.models import Subscription, SubscriptionPlan
from tenants.models import Tenant
from teams.models import TeamMember


class JWTClaimsTest(TestCase):
    """Test JWT token claims structure and content"""

    def setUp(self):
        self.client = APIClient()
        self.client.raise_request_exception = False
        self.user_model = get_user_model()

    def _create_sms_code(self, phone: str, purpose: str, code: str = "123456") -> SMSCode:
        """Helper: create a valid SMS code"""
        return SMSCode.objects.create(
            phone=phone,
            code=code,
            purpose=purpose,
            is_used=False,
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )

    def _create_plan(self, product: str = "agenticorcha") -> SubscriptionPlan:
        """Helper: create a subscription plan"""
        return SubscriptionPlan.objects.create(
            product=product,
            tier="basic",
            period="monthly",
            name=f"{product} Basic",
            price="99.00",
            max_users=5,
            max_api_calls=1000,
            max_storage_gb=5,
            is_active=True,
        )

    def _decode_jwt_claims(self, token: str) -> dict:
        """Helper: decode JWT claims without verification"""
        import base64
        import json

        # JWT format: header.payload.signature
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")

        # Decode payload (second part)
        payload = parts[1]
        # Add padding if needed
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding

        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)

    def test_phone_register_token_contains_user_id(self):
        """手机号注册后 Token 包含正确 user_id"""
        phone = "13800010101"
        self._create_sms_code(phone, "register", "123456")

        resp = self.client.post("/api/auth/register/phone/", {
            "phone": phone,
            "code": "123456",
            "password": "Passw0rd123"
        }, format="json")

        self.assertEqual(resp.status_code, 201)
        access_token = resp.data["access"]

        claims = self._decode_jwt_claims(access_token)
        self.assertIn("user_id", claims)
        # user_id in JWT is typically a string representation
        self.assertEqual(str(claims["user_id"]), str(self.user_model.objects.get(username=phone).id))

    def test_token_contains_tenant_id_after_subscription_activated(self):
        """开通订阅后 Token 包含 tenant_id"""
        phone = "13800010102"
        password = "Passw0rd123"
        plan = self._create_plan()

        # Create user and subscription
        user = self.user_model.objects.create_user(username=phone, password=password)
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            status="pending"
        )

        # Create paid payment
        from payments.models import PaymentTransaction
        PaymentTransaction.objects.create(
            subscription=subscription,
            user=user,
            out_trade_no="jwt_tenant_trade",
            amount=plan.price,
            gateway="alipay",
            status="paid"
        )

        # Activate subscription
        self.client.force_authenticate(user=user)
        resp = self.client.post(f"/api/subscriptions/{subscription.id}/activate/", {
            "company_email": "user@company.com",
            "tenant_name": "JWT Tenant Test"
        }, format="json")

        self.assertEqual(resp.status_code, 200)

        # Now login again to get fresh token with tenant_id claim
        self._create_sms_code(phone, "login", "123456")
        resp = self.client.post("/api/auth/login/phone/", {
            "phone": phone,
            "code": "123456"
        }, format="json")

        self.assertEqual(resp.status_code, 200)
        access_token = resp.data["access"]
        claims = self._decode_jwt_claims(access_token)

        self.assertIn("tenant_id", claims)
        self.assertIsNotNone(claims["tenant_id"])

    def test_token_contains_product_scopes_after_subscription_activated(self):
        """开通订阅后 Token 包含 product_scopes"""
        phone = "13800010103"
        password = "Passw0rd123"
        plan1 = self._create_plan("agenticorcha")
        plan2 = self._create_plan("datacognis")

        # Create user and subscriptions
        user = self.user_model.objects.create_user(username=phone, password=password)

        # First subscription
        sub1 = Subscription.objects.create(user=user, plan=plan1, status="pending")
        from payments.models import PaymentTransaction
        PaymentTransaction.objects.create(
            subscription=sub1, user=user, out_trade_no="scope_trade_1",
            amount=plan1.price, gateway="alipay", status="paid"
        )
        self.client.force_authenticate(user=user)
        self.client.post(f"/api/subscriptions/{sub1.id}/activate/", {
            "company_email": "user@company.com",
            "tenant_name": "Scope Tenant"
        }, format="json")

        # Login to get token
        self._create_sms_code(phone, "login", "123456")
        resp = self.client.post("/api/auth/login/phone/", {
            "phone": phone,
            "code": "123456"
        }, format="json")

        self.assertEqual(resp.status_code, 200)
        access_token = resp.data["access"]
        claims = self._decode_jwt_claims(access_token)

        self.assertIn("product_scopes", claims)
        self.assertIn("agenticorcha", claims["product_scopes"])

    def test_token_contains_roles_after_tenant_membership(self):
        """团队成员 Token 包含正确 roles"""
        phone_owner = "13800010104"
        phone_member = "13800010105"
        password = "Passw0rd123"

        # Create owner and member
        owner = self.user_model.objects.create_user(username=phone_owner, password=password)
        member = self.user_model.objects.create_user(username=phone_member, password=password)

        # Create tenant with owner
        tenant = Tenant.objects.create(
            name="Roles Tenant",
            slug="roles-tenant",
            owner=owner,
            status="active"
        )
        TeamMember.objects.create(tenant=tenant, user=owner, role="owner", status="active")

        # Add member
        TeamMember.objects.create(tenant=tenant, user=member, role="member", status="active")

        # Login as member
        self._create_sms_code(phone_member, "login", "123456")
        resp = self.client.post("/api/auth/login/phone/", {
            "phone": phone_member,
            "code": "123456"
        }, format="json")

        self.assertEqual(resp.status_code, 200)
        access_token = resp.data["access"]
        claims = self._decode_jwt_claims(access_token)

        self.assertIn("roles", claims)
        self.assertIn("member", claims["roles"])

    def test_token_expiry_time_reasonable(self):
        """Token 过期时间合理（exp - iat 应该约为 1 hour）"""
        phone = "13800010106"
        self._create_sms_code(phone, "register", "123456")

        resp = self.client.post("/api/auth/register/phone/", {
            "phone": phone,
            "code": "123456",
            "password": "Passw0rd123"
        }, format="json")

        self.assertEqual(resp.status_code, 201)
        access_token = resp.data["access"]
        claims = self._decode_jwt_claims(access_token)

        self.assertIn("exp", claims)
        self.assertIn("iat", claims)

        # exp - iat should be approximately 1 hour (3600 seconds)
        exp_iat_diff = claims["exp"] - claims["iat"]
        self.assertGreaterEqual(exp_iat_diff, 3500)
        self.assertLessEqual(exp_iat_diff, 3700)

    def test_token_without_subscription_has_empty_claims(self):
        """未订阅用户 Token 的 tenant_id 和 product_scopes 为空"""
        phone = "13800010107"
        self._create_sms_code(phone, "register", "123456")

        resp = self.client.post("/api/auth/register/phone/", {
            "phone": phone,
            "code": "123456",
            "password": "Passw0rd123"
        }, format="json")

        self.assertEqual(resp.status_code, 201)
        access_token = resp.data["access"]
        claims = self._decode_jwt_claims(access_token)

        self.assertIn("tenant_id", claims)
        self.assertIn("product_scopes", claims)
        self.assertIn("roles", claims)
        self.assertIsNone(claims["tenant_id"])
        self.assertEqual(claims["product_scopes"], [])
        self.assertEqual(claims["roles"], [])
