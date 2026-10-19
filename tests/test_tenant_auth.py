"""Tenant-aware authentication contract tests."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken
from accounts.jwt import (
    FIPAccessToken,
    FIPRefreshToken as RefreshToken,
    issue_token_pair,
)
from accounts.models import AuthSession

from subscriptions.models import Subscription, SubscriptionPlan
from teams.models import TeamMember
from tenants.models import Tenant


class TenantAuthTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="tenant-user", password="Passw0rd123"
        )
        self.other_user = get_user_model().objects.create_user(
            username="other-user", password="Passw0rd123"
        )
        self.tenant_a = Tenant.objects.create(
            name="Tenant A", slug="tenant-a", owner=self.user, status="active"
        )
        self.tenant_b = Tenant.objects.create(
            name="Tenant B", slug="tenant-b", owner=self.other_user, status="active"
        )
        self.other_tenant = Tenant.objects.create(
            name="Secret Tenant", slug="secret-tenant", owner=self.other_user, status="active"
        )

        self.member_a = TeamMember.objects.create(
            tenant=self.tenant_a,
            user=self.user,
            role="owner",
            status="active",
            product_permissions={
                "agenticorcha": {"access": True, "role": "admin"},
                "decisionops": {"access": False},
            },
        )
        self.member_b = TeamMember.objects.create(
            tenant=self.tenant_b,
            user=self.user,
            role="viewer",
            status="active",
            product_permissions={"datacognis": {"access": True, "role": "member"}},
        )
        TeamMember.objects.create(
            tenant=self.other_tenant,
            user=self.other_user,
            role="owner",
            status="active",
        )

        self.agent_plan = self._plan("agenticorcha", "Agent")
        self.data_plan = self._plan("datacognis", "Data")
        self.decision_plan = self._plan("decisionops", "Decision")
        self._subscription(self.user, self.tenant_a, self.agent_plan)
        self._subscription(self.user, self.tenant_a, self.decision_plan)
        self._subscription(self.other_user, self.tenant_b, self.data_plan)
        # This subscription must never leak merely because it belongs to the user.
        self._subscription(self.user, self.other_tenant, self.decision_plan)

        self.initial_access, self.initial_refresh = issue_token_pair(self.user)
        self.initial_sid = FIPAccessToken(self.initial_access)["sid"]
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self.initial_access}"
        )

    def _plan(self, product, name):
        return SubscriptionPlan.objects.create(
            product=product,
            tier="basic",
            period="monthly",
            name=name,
            price="10.00",
        )

    def _subscription(self, user, tenant, plan):
        return Subscription.objects.create(
            user=user,
            tenant=tenant,
            plan=plan,
            status="active",
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=30),
        )

    def test_tenant_list_returns_only_active_memberships_with_isolated_scopes(self):
        disabled_tenant = Tenant.objects.create(
            name="Disabled Membership", slug="disabled-membership", owner=self.user
        )
        TeamMember.objects.create(
            tenant=disabled_tenant, user=self.user, role="admin", status="disabled"
        )

        response = self.client.get("/api/auth/tenants/")

        self.assertEqual(response.status_code, 200)
        tenants = {item["tenant_id"]: item for item in response.data}
        self.assertEqual(set(tenants), {self.tenant_a.id, self.tenant_b.id})
        self.assertEqual(tenants[self.tenant_a.id]["roles"], ["owner"])
        self.assertEqual(tenants[self.tenant_a.id]["product_scopes"], ["agenticorcha"])
        self.assertEqual(tenants[self.tenant_b.id]["roles"], ["viewer"])
        self.assertEqual(tenants[self.tenant_b.id]["product_scopes"], ["datacognis"])
        self.assertNotContains(response, "Secret Tenant")

    def test_switch_tenant_issues_claims_and_httponly_sso_cookies(self):
        response = self.client.post(
            "/api/auth/tenant/switch/", {"tenant_id": self.tenant_b.id}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        access_claims = AccessToken(response.data["access"])
        refresh_claims = RefreshToken(response.data["refresh"])
        for claims in (access_claims, refresh_claims):
            self.assertEqual(claims["tenant_id"], self.tenant_b.id)
            self.assertEqual(claims["tenant_uuid"], str(self.tenant_b.tenant_uuid))
            self.assertEqual(claims["roles"], ["viewer"])
            self.assertEqual(claims["product_scopes"], ["datacognis"])
        self.assertTrue(response.cookies["fip_access_token"]["httponly"])
        self.assertTrue(response.cookies["fip_refresh_token"]["httponly"])

        source_session = AuthSession.objects.get(sid=self.initial_sid)
        new_sid = FIPAccessToken(response.data["access"])["sid"]
        self.assertIsNotNone(source_session.revoked_at)
        self.assertEqual(source_session.revoked_reason, "tenant_switched")
        self.assertTrue(
            AuthSession.objects.filter(
                sid=new_sid, revoked_at__isnull=True
            ).exists()
        )
        self.assertEqual(self.client.get("/api/auth/tenants/").status_code, 401)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {response.data['access']}"
        )
        self.assertEqual(self.client.get("/api/auth/tenants/").status_code, 200)

    def test_switch_missing_and_unauthorized_tenant_do_not_disclose_existence(self):
        forbidden = self.client.post(
            "/api/auth/tenant/switch/", {"tenant_id": self.other_tenant.id}, format="json"
        )
        missing = self.client.post(
            "/api/auth/tenant/switch/", {"tenant_id": 999999}, format="json"
        )

        self.assertEqual(forbidden.status_code, 404)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(forbidden.data, missing.data)
        self.assertNotIn("access", forbidden.data)
        self.assertNotIn(self.other_tenant.name, forbidden.content.decode())

    def test_switch_claims_are_isolated_between_tenants(self):
        response_a = self.client.post(
            "/api/auth/tenant/switch/", {"tenant_id": self.tenant_a.id}, format="json"
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {response_a.data['access']}"
        )
        response_b = self.client.post(
            "/api/auth/tenant/switch/", {"tenant_id": self.tenant_b.id}, format="json"
        )

        claims_a = AccessToken(response_a.data["access"])
        claims_b = AccessToken(response_b.data["access"])
        self.assertEqual(claims_a["product_scopes"], ["agenticorcha"])
        self.assertEqual(claims_b["product_scopes"], ["datacognis"])
        self.assertNotIn("datacognis", claims_a["product_scopes"])
        self.assertNotIn("agenticorcha", claims_b["product_scopes"])

    def test_password_login_keeps_first_active_tenant_default(self):
        expected = TeamMember.objects.filter(user=self.user, status="active").first()
        self.client.credentials()

        response = self.client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "Passw0rd123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        claims = AccessToken(response.data["access"])
        self.assertEqual(claims["tenant_id"], expected.tenant_id)
        self.assertEqual(claims["tenant_uuid"], str(expected.tenant.tenant_uuid))
        self.assertEqual(claims["roles"], [expected.role])

    def test_businessbuilder_is_a_valid_subscription_product(self):
        plan = self._plan("businessbuilder", "Builder")

        plan.full_clean()
        self.assertEqual(plan.product, "businessbuilder")
