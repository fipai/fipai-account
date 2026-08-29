"""
Subscription State Machine Tests

验证订阅状态流转符合业务规则:
- 订阅创建后状态为 pending
- 支付完成后状态为 paid/active
- 开通必须要求 pending 状态
- 重复开通返回错误
- 取消订阅后状态变更
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.jwt import issue_token_pair
from subscriptions.models import Subscription, SubscriptionPlan
from teams.models import TeamMember
from tenants.models import Tenant


class SubscriptionStateMachineTest(TestCase):
    """Test subscription state transitions"""

    def setUp(self):
        self.client = APIClient()
        self.client.raise_request_exception = False
        self.user_model = get_user_model()

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

    def _create_paid_subscription(self, user, plan: SubscriptionPlan) -> Subscription:
        """Helper: create a subscription with paid status"""
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
            out_trade_no=f"state_machine_trade_{subscription.id}",
            amount=plan.price,
            gateway="alipay",
            status="paid"
        )

        return subscription

    def test_subscription_created_with_pending_status(self):
        """订阅创建后状态为 pending"""
        user = self.user_model.objects.create_user(
            username="13800020101",
            password="Passw0rd123"
        )
        plan = self._create_plan()

        self.client.force_authenticate(user=user)
        resp = self.client.post("/api/subscriptions/", {
            "plan_id": plan.id
        }, format="json")

        self.assertEqual(resp.status_code, 201)
        subscription_id = resp.data["id"]
        subscription = Subscription.objects.get(id=subscription_id)
        self.assertEqual(subscription.status, "pending")

    def test_subscription_activate_requires_pending_status(self):
        """开通必须要求 pending 状态"""
        user = self.user_model.objects.create_user(
            username="13800020102",
            password="Passw0rd123"
        )
        plan = self._create_plan()
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            status="active"  # Not pending
        )

        self.client.force_authenticate(user=user)
        resp = self.client.post(f"/api/subscriptions/{subscription.id}/activate/", {
            "company_email": "owner@corp.com",
            "tenant_name": "Corp Tenant"
        }, format="json")

        self.assertEqual(resp.status_code, 400)
        # Error message: "订阅状态不是待开通" (subscription status is not pending)
        self.assertIn("待开通", resp.data.get("error", ""))

    def test_subscription_activate_with_paid_payment(self):
        """支付完成后可以开通订阅"""
        user = self.user_model.objects.create_user(
            username="13800020103",
            password="Passw0rd123",
            email=""
        )
        plan = self._create_plan()
        subscription = self._create_paid_subscription(user, plan)

        self.client.force_authenticate(user=user)
        resp = self.client.post(f"/api/subscriptions/{subscription.id}/activate/", {
            "company_email": "owner@corp.com",
            "tenant_name": "Corp Tenant"
        }, format="json")

        self.assertEqual(resp.status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, "active")
        self.assertIsNotNone(subscription.tenant)
        self.assertIsNotNone(subscription.start_date)
        self.assertIsNotNone(subscription.end_date)

    def test_subscription_activate_without_payment_fails(self):
        """未支付不能开通订阅"""
        user = self.user_model.objects.create_user(
            username="13800020104",
            password="Passw0rd123"
        )
        plan = self._create_plan()
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            status="pending"
            # No paid payment transaction
        )

        self.client.force_authenticate(user=user)
        resp = self.client.post(f"/api/subscriptions/{subscription.id}/activate/", {
            "company_email": "owner@corp.com",
            "tenant_name": "Corp Tenant"
        }, format="json")

        self.assertEqual(resp.status_code, 400)
        self.assertIn("尚未支付", resp.data.get("error", ""))

    def test_subscription_activate_twice_fails(self):
        """重复开通返回错误"""
        user = self.user_model.objects.create_user(
            username="13800020105",
            password="Passw0rd123",
            email=""
        )
        plan = self._create_plan()
        subscription = self._create_paid_subscription(user, plan)

        self.client.force_authenticate(user=user)

        # First activation
        resp = self.client.post(f"/api/subscriptions/{subscription.id}/activate/", {
            "company_email": "owner@corp.com",
            "tenant_name": "Corp Tenant"
        }, format="json")
        self.assertEqual(resp.status_code, 200)

        # Second activation should fail
        resp = self.client.post(f"/api/subscriptions/{subscription.id}/activate/", {
            "company_email": "owner@corp.com",
            "tenant_name": "Corp Tenant 2"
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_cancel_subscription_changes_status(self):
        """取消订阅后状态变更"""
        user = self.user_model.objects.create_user(
            username="13800020106",
            password="Passw0rd123"
        )
        plan = self._create_plan()
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            status="active",
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=30)
        )

        self.client.force_authenticate(user=user)
        resp = self.client.post(f"/api/subscriptions/{subscription.id}/cancel/")

        self.assertEqual(resp.status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, "cancelled")
        self.assertFalse(subscription.auto_renew)

    def test_cancel_pending_subscription_fails(self):
        """待支付的订阅不能取消"""
        user = self.user_model.objects.create_user(
            username="13800020107",
            password="Passw0rd123"
        )
        plan = self._create_plan()
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            status="pending"
        )

        self.client.force_authenticate(user=user)
        resp = self.client.post(f"/api/subscriptions/{subscription.id}/cancel/")

        self.assertEqual(resp.status_code, 400)

    def test_subscription_end_date_set_on_activation(self):
        """开通订阅后设置正确的结束日期"""
        user = self.user_model.objects.create_user(
            username="13800020108",
            password="Passw0rd123",
            email=""
        )

        # Test monthly plan
        monthly_plan = self._create_plan(tier="basic")
        monthly_sub = self._create_paid_subscription(user, monthly_plan)

        self.client.force_authenticate(user=user)
        resp = self.client.post(f"/api/subscriptions/{monthly_sub.id}/activate/", {
            "company_email": "owner@corp.com",
            "tenant_name": "Monthly Corp"
        }, format="json")

        self.assertEqual(resp.status_code, 200)
        monthly_sub.refresh_from_db()

        # Monthly should have ~30 days
        expected_end = monthly_sub.start_date + timezone.timedelta(days=30)
        self.assertAlmostEqual(
            monthly_sub.end_date.timestamp(),
            expected_end.timestamp(),
            delta=60  # Allow 1 minute tolerance
        )

    def test_subscription_state_preserved_after_tenant_creation(self):
        """创建租户后订阅状态保持正确"""
        user = self.user_model.objects.create_user(
            username="13800020109",
            password="Passw0rd123",
            email=""
        )
        plan = self._create_plan()
        subscription = self._create_paid_subscription(user, plan)

        self.client.force_authenticate(user=user)
        resp = self.client.post(f"/api/subscriptions/{subscription.id}/activate/", {
            "company_email": "owner@corp.com",
            "tenant_name": "State Preserve Corp"
        }, format="json")

        self.assertEqual(resp.status_code, 200)
        subscription.refresh_from_db()

        # Verify subscription is active
        self.assertEqual(subscription.status, "active")
        self.assertIsNotNone(subscription.tenant)

        # Verify tenant exists
        self.assertTrue(Tenant.objects.filter(id=subscription.tenant_id).exists())

        # Verify owner membership was created
        self.assertTrue(
            TeamMember.objects.filter(
                tenant=subscription.tenant,
                user=user,
                role="owner",
                status="active"
            ).exists()
        )

    def test_cannot_activate_expired_subscription(self):
        """不能激活已过期的订阅"""
        user = self.user_model.objects.create_user(
            username="13800020110",
            password="Passw0rd123"
        )
        plan = self._create_plan()
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            status="expired"
        )

        self.client.force_authenticate(user=user)
        resp = self.client.post(f"/api/subscriptions/{subscription.id}/activate/", {
            "company_email": "owner@corp.com",
            "tenant_name": "Expired Corp"
        }, format="json")

        self.assertEqual(resp.status_code, 400)

    def test_cannot_activate_cancelled_subscription(self):
        """不能激活已取消的订阅"""
        user = self.user_model.objects.create_user(
            username="13800020111",
            password="Passw0rd123"
        )
        plan = self._create_plan()
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            status="cancelled"
        )

        self.client.force_authenticate(user=user)
        resp = self.client.post(f"/api/subscriptions/{subscription.id}/activate/", {
            "company_email": "owner@corp.com",
            "tenant_name": "Cancelled Corp"
        }, format="json")

        self.assertEqual(resp.status_code, 400)

    def test_existing_tenant_activation_binds_subscription_and_updates_switch_claims(self):
        user = self.user_model.objects.create_user(
            username="13800020112",
            password="Passw0rd123",
        )
        tenant = Tenant.objects.create(
            name="Existing Tenant",
            slug="existing-tenant",
            owner=user,
            status="active",
        )
        TeamMember.objects.create(
            tenant=tenant,
            user=user,
            role="owner",
            status="active",
            product_permissions={},
        )
        plan = self._create_plan(product="businessbuilder")
        subscription = self._create_paid_subscription(user, plan)

        self.client.force_authenticate(user=user)
        activate_response = self.client.post(
            f"/api/subscriptions/{subscription.id}/activate/",
            {
                "company_email": "owner@existing.example.com",
                "tenant_name": "Ignored New Tenant Name",
            },
            format="json",
        )

        self.assertEqual(activate_response.status_code, 200)
        self.assertEqual(activate_response.data["tenant_id"], tenant.id)
        subscription.refresh_from_db()
        self.assertEqual(subscription.tenant_id, tenant.id)
        self.assertEqual(subscription.status, "active")

        access, _ = issue_token_pair(user)
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        switch_response = self.client.post(
            "/api/auth/tenant/switch/",
            {"tenant_id": tenant.id},
            format="json",
        )
        self.assertEqual(switch_response.status_code, 200)
        claims = AccessToken(switch_response.data["access"])
        self.assertEqual(claims["tenant_id"], tenant.id)
        self.assertIn("businessbuilder", claims["product_scopes"])
