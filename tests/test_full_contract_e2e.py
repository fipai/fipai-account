"""
Full Contract E2E Tests - Complete user journey testing

Tests all INTERFACES.md defined endpoints in a complete user journey:
1. Send SMS code → Phone register → Get current user
2. Send SMS code → Phone login → Get current user
3. Subscribe plan → Activate subscription → Create tenant
4. Invite member → Accept invitation → Verify member list
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.jwt import FIPRefreshToken as RefreshToken

from accounts.models import SMSCode
from subscriptions.models import Subscription, SubscriptionPlan
from tenants.models import Tenant
from teams.models import Invitation, TeamMember


class ContractE2ETestBase(TestCase):
    """Base class for E2E contract tests"""

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

    def _create_plan(self, product: str = "agenticorcha", tier: str = "basic") -> SubscriptionPlan:
        """Helper: create a subscription plan"""
        return SubscriptionPlan.objects.create(
            product=product,
            tier=tier,
            period="monthly",
            name=f"{product} {tier}",
            price="99.00",
            max_users=5,
            max_api_calls=1000,
            max_storage_gb=5,
            is_active=True,
        )


class SendCodeEndpointTest(ContractE2ETestBase):
    """Test: POST /api/auth/send-code/"""

    def test_send_code_register_request_format(self):
        """验证发送验证码请求格式"""
        resp = self.client.post("/api/auth/send-code/", {
            "phone": "13800000001",
            "purpose": "register"
        }, format="json")

        # Mock mode returns 200 even without real SMS
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data.get('ok') or resp.data.get('error') is None)

    def test_send_code_login_request_format(self):
        """验证登录验证码请求格式"""
        resp = self.client.post("/api/auth/send-code/", {
            "phone": "13800000002",
            "purpose": "login"
        }, format="json")

        self.assertEqual(resp.status_code, 200)

    def test_send_code_invalid_phone_format(self):
        """验证无效手机号格式"""
        resp = self.client.post("/api/auth/send-code/", {
            "phone": "12345",
            "purpose": "register"
        }, format="json")

        self.assertIn(resp.status_code, [400, 422])

    def test_send_code_invalid_purpose(self):
        """验证无效 purpose"""
        resp = self.client.post("/api/auth/send-code/", {
            "phone": "13800000003",
            "purpose": "invalid"
        }, format="json")

        self.assertIn(resp.status_code, [400, 422])


class PhoneRegisterEndpointTest(ContractE2ETestBase):
    """Test: POST /api/auth/register/phone/"""

    def test_phone_register_returns_jwt(self):
        """验证手机号注册返回 JWT"""
        phone = "13800000101"
        code = "123456"
        self._create_sms_code(phone, "register", code)

        resp = self.client.post("/api/auth/register/phone/", {
            "phone": phone,
            "code": code,
            "password": "Passw0rd123"
        }, format="json")

        self.assertEqual(resp.status_code, 201)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_phone_register_invalid_code(self):
        """验证码错误"""
        phone = "13800000102"
        self._create_sms_code(phone, "register", "123456")

        resp = self.client.post("/api/auth/register/phone/", {
            "phone": phone,
            "code": "999999",
            "password": "Passw0rd123"
        }, format="json")

        self.assertEqual(resp.status_code, 400)

    def test_phone_register_expired_code(self):
        """验证码过期"""
        phone = "13800000103"
        SMSCode.objects.create(
            phone=phone,
            code="123456",
            purpose="register",
            is_used=False,
            expires_at=timezone.now() - timezone.timedelta(minutes=1),  # expired
        )

        resp = self.client.post("/api/auth/register/phone/", {
            "phone": phone,
            "code": "123456",
            "password": "Passw0rd123"
        }, format="json")

        self.assertEqual(resp.status_code, 400)

    def test_phone_register_duplicate_phone(self):
        """重复手机号注册"""
        phone = "13800000104"
        self._create_sms_code(phone, "register", "123456")

        # First registration
        self.client.post("/api/auth/register/phone/", {
            "phone": phone,
            "code": "123456",
            "password": "Passw0rd123"
        }, format="json")

        # Second registration with same phone
        self._create_sms_code(phone, "register", "123456")
        resp = self.client.post("/api/auth/register/phone/", {
            "phone": phone,
            "code": "123456",
            "password": "Passw0rd1232"
        }, format="json")

        self.assertEqual(resp.status_code, 400)


class PhoneLoginEndpointTest(ContractE2ETestBase):
    """Test: POST /api/auth/login/phone/"""

    def test_phone_login_returns_jwt(self):
        """验证手机号登录返回 JWT"""
        phone = "13800000201"
        password = "Passw0rd123"
        self._create_sms_code(phone, "login", "123456")

        # Create user first
        self.user_model.objects.create_user(username=phone, password=password)

        resp = self.client.post("/api/auth/login/phone/", {
            "phone": phone,
            "code": "123456"
        }, format="json")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_phone_login_invalid_code(self):
        """登录验证码错误"""
        phone = "13800000202"
        self._create_sms_code(phone, "login", "123456")
        self.user_model.objects.create_user(username=phone, password="Passw0rd123")

        resp = self.client.post("/api/auth/login/phone/", {
            "phone": phone,
            "code": "999999"
        }, format="json")

        self.assertEqual(resp.status_code, 400)

    def test_phone_login_user_not_exists(self):
        """用户不存在时不得与错误验证码响应区分"""
        phone = "13800000203"
        self._create_sms_code(phone, "login", "123456")

        resp = self.client.post("/api/auth/login/phone/", {
            "phone": phone,
            "code": "123456"
        }, format="json")

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {'error': '登录凭据无效'})


class AuthMeEndpointTest(ContractE2ETestBase):
    """Test: GET /api/auth/me/"""

    def test_auth_me_response_fields(self):
        """验证 /me 响应字段完整性"""
        phone = "13800000301"
        user = self.user_model.objects.create_user(
            username=phone,
            password="Passw0rd123",
            first_name="Test User"
        )

        self.client.force_authenticate(user=user)
        resp = self.client.get("/api/auth/me/")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("phone", resp.data)
        self.assertIn("name", resp.data)
        # Contract requires: phone, name, tenant_id, subscriptions
        self.assertIn("tenant_id", resp.data)
        self.assertIn("subscriptions", resp.data)

    def test_auth_me_unauthenticated(self):
        """未认证访问 /me 应返回 401"""
        resp = self.client.get("/api/auth/me/")
        self.assertIn(resp.status_code, [401, 403])


class SubscriptionPlanEndpointTest(ContractE2ETestBase):
    """Test: GET /api/subscriptions/plans/"""

    def test_plans_list_returns_grouped(self):
        """验证套餐列表按产品分组"""
        self._create_plan("agenticorcha", "basic")
        self._create_plan("datacognis", "basic")

        resp = self.client.get("/api/subscriptions/plans/")

        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.data, list)


class SubscriptionCreateEndpointTest(ContractE2ETestBase):
    """Test: POST /api/subscriptions/"""

    def test_create_subscription(self):
        """验证订阅套餐"""
        user = self.user_model.objects.create_user(
            username="13800000401",
            password="Passw0rd123"
        )
        plan = self._create_plan()

        self.client.force_authenticate(user=user)
        resp = self.client.post("/api/subscriptions/", {
            "plan_id": plan.id
        }, format="json")

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], "pending")


class SubscriptionActivateEndpointTest(ContractE2ETestBase):
    """Test: POST /api/subscriptions/{id}/activate/"""

    def test_activate_subscription_creates_tenant(self):
        """验证开通订阅并创建租户"""
        user = self.user_model.objects.create_user(
            username="13800000501",
            password="Passw0rd123",
            email=""
        )
        plan = self._create_plan()
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            status="pending"
        )

        # Create a paid payment transaction
        from payments.models import PaymentTransaction
        PaymentTransaction.objects.create(
            subscription=subscription,
            user=user,
            out_trade_no="test_trade_001",
            amount=plan.price,
            gateway="alipay",
            status="paid"
        )

        self.client.force_authenticate(user=user)
        resp = self.client.post(f"/api/subscriptions/{subscription.id}/activate/", {
            "company_email": "owner@company.com",
            "tenant_name": "Test Company"
        }, format="json")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("tenant_id", resp.data)

        # Verify tenant was created
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, "active")
        self.assertIsNotNone(subscription.tenant)


class TenantCreateEndpointTest(ContractE2ETestBase):
    """Test: POST /api/tenants/"""

    def test_create_tenant(self):
        """验证创建租户"""
        user = self.user_model.objects.create_user(
            username="13800000601",
            password="Passw0rd123"
        )

        self.client.force_authenticate(user=user)
        resp = self.client.post("/api/tenants/", {
            "name": "My Company",
            "slug": "my-company",
            "description": "Test tenant"
        }, format="json")

        self.assertEqual(resp.status_code, 201)
        self.assertIn("id", resp.data)

    def test_create_tenant_auto_creates_owner_membership(self):
        """验证创建租户自动创建 owner 成员关系"""
        user = self.user_model.objects.create_user(
            username="13800000602",
            password="Passw0rd123"
        )

        self.client.force_authenticate(user=user)
        resp = self.client.post("/api/tenants/", {
            "name": "My Company 2",
            "slug": "my-company-2",
            "description": "Test tenant"
        }, format="json")

        self.assertEqual(resp.status_code, 201)
        tenant_id = resp.data["id"]

        # Verify owner membership exists
        self.assertTrue(
            TeamMember.objects.filter(
                tenant_id=tenant_id,
                user=user,
                role="owner",
                status="active"
            ).exists()
        )


class TenantInviteEndpointTest(ContractE2ETestBase):
    """Test: POST /api/tenants/{id}/invite/"""

    def test_invite_member(self):
        """验证邀请成员"""
        owner = self.user_model.objects.create_user(
            username="13800000701",
            password="Passw0rd123"
        )
        tenant = Tenant.objects.create(
            name="Invite Test Tenant",
            slug="invite-test-tenant",
            owner=owner,
            status="active"
        )
        TeamMember.objects.create(
            tenant=tenant,
            user=owner,
            role="owner",
            status="active"
        )

        self.client.force_authenticate(user=owner)
        resp = self.client.post(f"/api/tenants/{tenant.id}/invite/", {
            "email": "newmember@example.com",
            "role": "member"
        }, format="json")

        self.assertEqual(resp.status_code, 201)
        self.assertIn("code", resp.data)


class InvitationAcceptEndpointTest(ContractE2ETestBase):
    """Test: POST /api/teams/invitations/accept/"""

    def test_accept_invitation(self):
        """验证接受邀请"""
        owner = self.user_model.objects.create_user(
            username="13800000801",
            password="Passw0rd123"
        )
        invitee = self.user_model.objects.create_user(
            username="13800000802",
            password="Passw0rd123",
            email="invitee@example.com"
        )
        tenant = Tenant.objects.create(
            name="Accept Test Tenant",
            slug="accept-test-tenant",
            owner=owner,
            status="active"
        )
        TeamMember.objects.create(
            tenant=tenant,
            user=owner,
            role="owner",
            status="active"
        )
        invitation = Invitation.objects.create(
            tenant=tenant,
            email="invitee@example.com",
            role="member",
            invited_by=owner,
            code="test-invite-code-123",
            status="pending",
            expires_at=timezone.now() + timezone.timedelta(days=7)
        )

        self.client.force_authenticate(user=invitee)
        resp = self.client.post("/api/teams/invitations/accept/", {
            "code": "test-invite-code-123"
        }, format="json")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("tenant_id", resp.data)

        # Verify member was created
        self.assertTrue(
            TeamMember.objects.filter(
                tenant=tenant,
                user=invitee,
                role="member",
                status="active"
            ).exists()
        )


class CompleteUserJourneyTest(ContractE2ETestBase):
    """Complete user journey from registration to tenant membership"""

    def test_full_journey_register_subscribe_activate(self):
        """完整流程: 注册 → 订阅 → 开通 → 创建租户"""
        phone = "13800000901"
        password = "Passw0rd123"
        plan = self._create_plan()

        # 1. Send code for registration
        self._create_sms_code(phone, "register", "123456")

        # 2. Register with phone
        resp = self.client.post("/api/auth/register/phone/", {
            "phone": phone,
            "code": "123456",
            "password": password
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("access", resp.data)

        # 3. Get current user
        access_token = resp.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("phone", resp.data)

        # 4. Subscribe to plan
        self.client.credentials()  # Reset credentials
        user = self.user_model.objects.get(username=phone)
        self.client.force_authenticate(user=user)
        resp = self.client.post("/api/subscriptions/", {
            "plan_id": plan.id
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        subscription_id = resp.data["id"]

        # 5. Create payment transaction
        from payments.models import PaymentTransaction
        subscription = Subscription.objects.get(id=subscription_id)
        PaymentTransaction.objects.create(
            subscription=subscription,
            user=user,
            out_trade_no="journey_trade_001",
            amount=plan.price,
            gateway="alipay",
            status="paid"
        )

        # 6. Activate subscription
        resp = self.client.post(f"/api/subscriptions/{subscription_id}/activate/", {
            "company_email": "user@company.com",
            "tenant_name": "Journey Test Company"
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("tenant_id", resp.data)
        tenant_id = resp.data["tenant_id"]

        # 7. Verify tenant membership
        self.assertTrue(
            TeamMember.objects.filter(
                tenant_id=tenant_id,
                user=user,
                role="owner",
                status="active"
            ).exists()
        )
