from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from subscriptions.models import Subscription, SubscriptionPlan
from teams.models import Invitation, TeamMember
from tenants.models import Tenant


class AccountReviewFindingsTest(TestCase):
    """Regression/contract tests from 2026-07-07 account review."""

    def setUp(self):
        self.client = APIClient()
        self.client.raise_request_exception = False
        self.user_model = get_user_model()

    def _create_user(self, username: str, email: str, password: str = "Passw0rd123"):
        return self.user_model.objects.create_user(
            username=username,
            email=email,
            password=password,
        )

    def _create_tenant_with_owner(self, owner):
        tenant = Tenant.objects.create(
            name="Tenant A",
            slug=f"tenant-a-{owner.id}",
            owner=owner,
            status="active",
        )
        TeamMember.objects.create(
            tenant=tenant,
            user=owner,
            role="owner",
            status="active",
        )
        return tenant

    def test_invitation_accept_must_bind_invited_identity(self):
        owner = self._create_user("owner_inv", "owner_inv@example.com")
        attacker = self._create_user("attacker_inv", "attacker_inv@example.com")
        tenant = self._create_tenant_with_owner(owner)

        invitation = Invitation.objects.create(
            tenant=tenant,
            email="intended@example.com",
            role="member",
            invited_by=owner,
            code="invite-code-identity-check",
            status="pending",
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )

        self.client.force_authenticate(user=attacker)
        resp = self.client.post("/api/teams/invitations/accept/", {"code": invitation.code}, format="json")

        self.assertNotEqual(resp.status_code, 200)
        self.assertFalse(
            TeamMember.objects.filter(tenant=tenant, user=attacker, status="active").exists()
        )

    def test_member_cannot_self_escalate_role_to_owner(self):
        owner = self._create_user("owner_role", "owner_role@example.com")
        member = self._create_user("member_role", "member_role@example.com")
        tenant = self._create_tenant_with_owner(owner)

        member_record = TeamMember.objects.create(
            tenant=tenant,
            user=member,
            role="member",
            status="active",
        )

        self.client.force_authenticate(user=member)
        resp = self.client.put(
            f"/api/teams/members/{member_record.id}/update_role/",
            {"role": "owner"},
            format="json",
        )

        member_record.refresh_from_db()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(member_record.role, "member")

    def test_email_register_endpoint_should_not_500(self):
        payload = {
            "username": "register_user_1",
            "email": "register_user_1@example.com",
            "password": "Passw0rd123",
            "name": "Tester",
        }

        resp = self.client.post("/api/auth/register/", payload, format="json")

        self.assertNotEqual(resp.status_code, 500)
        self.assertEqual(resp.status_code, 201)

    def test_create_tenant_should_auto_create_owner_membership(self):
        user = self._create_user("tenant_creator", "tenant_creator@example.com")

        self.client.force_authenticate(user=user)
        resp = self.client.post(
            "/api/tenants/",
            {
                "name": "Created Tenant",
                "slug": "created-tenant",
                "description": "desc",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 201)
        tenant_id = resp.data["id"]
        self.assertTrue(
            TeamMember.objects.filter(
                tenant_id=tenant_id,
                user=user,
                role="owner",
                status="active",
            ).exists()
        )

    def test_profile_patch_should_update_user_email(self):
        user = self._create_user("profile_user", "profile_old@example.com")

        self.client.force_authenticate(user=user)
        resp = self.client.patch(
            "/api/auth/profile/",
            {"email": "profile_new@example.com"},
            format="json",
        )

        user.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(user.email, "profile_new@example.com")

    def test_auth_me_response_should_include_contract_phone_and_name(self):
        user = self._create_user("13800000000", "me_user@example.com")
        user.first_name = "Contract User"
        user.save(update_fields=["first_name"])

        self.client.force_authenticate(user=user)
        resp = self.client.get("/api/auth/me/")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("phone", resp.data)
        self.assertIn("name", resp.data)

    def test_subscription_activate_requires_pending_state(self):
        user = self._create_user("active_sub_user", "active_sub_user@example.com")
        plan = SubscriptionPlan.objects.create(
            product="agenticorcha",
            tier="basic",
            period="monthly",
            name="AO Basic",
            price="99.00",
            max_users=5,
            max_api_calls=1000,
            max_storage_gb=5,
            is_active=True,
        )
        subscription = Subscription.objects.create(
            user=user,
            plan=plan,
            status="active",
        )

        self.client.force_authenticate(user=user)
        resp = self.client.post(
            f"/api/subscriptions/{subscription.id}/activate/",
            {
                "company_email": "owner@corp.com",
                "tenant_name": "Corp Tenant",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 400)
