from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.jwt import FIPAccessToken, build_tenant_claims, issue_token_pair
from teams.models import Invitation, TeamMember
from tenants.models import Tenant


class TenantLifecycleSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()
        self.owner = self._user("lifecycle-owner")
        self.second_owner = self._user("lifecycle-second-owner")
        self.admin = self._user("lifecycle-admin")
        self.invitee = self._user("lifecycle-invitee")
        self.tenant = Tenant.objects.create(
            name="Lifecycle Tenant",
            slug="lifecycle-tenant",
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.owner_membership = self._membership(self.owner, "owner")
        self.second_owner_membership = self._membership(self.second_owner, "owner")
        self.admin_membership = self._membership(self.admin, "admin")

    def _user(self, label, **kwargs):
        return self.user_model.objects.create_user(
            username=label,
            email=f"{label}@example.com",
            password="Passw0rd123",
            **kwargs,
        )

    def _membership(self, user, role, status="active"):
        return TeamMember.objects.create(
            tenant=self.tenant,
            user=user,
            role=role,
            status=status,
        )

    def _member_url(self, membership, suffix=""):
        return f"/api/teams/members/{membership.id}/{suffix}"

    def _invitation(self, code="lifecycle-invitation"):
        return Invitation.objects.create(
            tenant=self.tenant,
            email=self.invitee.email,
            role="member",
            invited_by=self.owner,
            code=code,
            expires_at=timezone.now() + timezone.timedelta(days=1),
        )

    def test_admin_cannot_mutate_owner_even_when_two_owners_exist(self):
        self.client.force_authenticate(user=self.admin)

        downgrade = self.client.put(
            self._member_url(self.second_owner_membership, "update_role/"),
            {"role": "member"},
            format="json",
        )
        permissions = self.client.put(
            self._member_url(self.second_owner_membership, "update_permissions/"),
            {"product_permissions": {"decisionops": {"access": True}}},
            format="json",
        )
        remove = self.client.post(
            self._member_url(self.second_owner_membership, "remove/")
        )

        self.assertEqual(downgrade.status_code, 403)
        self.assertEqual(permissions.status_code, 403)
        self.assertEqual(remove.status_code, 400)
        self.second_owner_membership.refresh_from_db()
        self.assertEqual(self.second_owner_membership.role, "owner")
        self.assertEqual(self.second_owner_membership.status, "active")
        self.assertEqual(self.second_owner_membership.product_permissions, {})

    def test_owner_delete_hides_tenant_team_actions_switch_and_claims(self):
        self.client.force_authenticate(user=self.owner)
        tenant_url = f"/api/tenants/{self.tenant.id}/"
        self.assertEqual(self.client.delete(tenant_url).status_code, 204)

        responses = (
            self.client.get(tenant_url),
            self.client.patch(tenant_url, {"name": "Hidden rename"}, format="json"),
            self.client.get(self._member_url(self.second_owner_membership)),
            self.client.put(
                self._member_url(self.second_owner_membership, "update_role/"),
                {"role": "admin"},
                format="json",
            ),
            self.client.post(
                "/api/auth/tenant/switch/",
                {"tenant_id": self.tenant.id},
                format="json",
            ),
        )
        self.assertTrue(all(response.status_code == 404 for response in responses))

        team_list = self.client.get("/api/teams/members/")
        self.assertEqual(team_list.status_code, 404)
        claims = build_tenant_claims(self.owner, tenant_id=self.tenant.id)
        self.assertIsNone(claims["tenant_id"])
        self.assertEqual(claims["roles"], [])
        self.assertEqual(claims["product_scopes"], [])

    def test_suspended_tenant_cannot_be_listed_switched_or_claimed(self):
        self.tenant.status = "suspended"
        self.tenant.save(update_fields=["status"])
        self.client.force_authenticate(user=self.owner)

        tenant_list = self.client.get("/api/auth/tenants/")
        switch = self.client.post(
            "/api/auth/tenant/switch/",
            {"tenant_id": self.tenant.id},
            format="json",
        )

        self.assertEqual(tenant_list.status_code, 200)
        self.assertEqual(tenant_list.data, [])
        self.assertEqual(switch.status_code, 404)
        self.assertIsNone(
            build_tenant_claims(self.owner, tenant_id=self.tenant.id)["tenant_id"]
        )

    def test_disabled_historical_inviter_cannot_retrieve_or_cancel(self):
        invitation = self._invitation("disabled-inviter")
        self.owner_membership.status = "disabled"
        self.owner_membership.save(update_fields=["status"])
        self.client.force_authenticate(user=self.owner)
        invitation_url = f"/api/teams/invitations/{invitation.id}/"

        self.assertEqual(self.client.get(invitation_url).status_code, 404)
        self.assertEqual(self.client.post(f"{invitation_url}cancel/").status_code, 404)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "pending")

    def test_accept_rejects_invitation_when_inviter_no_longer_manages(self):
        invitation = self._invitation("revoked-inviter")
        self.owner_membership.role = "member"
        self.owner_membership.save(update_fields=["role"])
        self.client.force_authenticate(user=self.invitee)

        response = self.client.post(
            "/api/teams/invitations/accept/",
            {"code": invitation.code},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "pending")
        self.assertFalse(
            TeamMember.objects.filter(tenant=self.tenant, user=self.invitee).exists()
        )

    def test_accepted_invitation_cannot_be_cancelled_or_reverted(self):
        invitation = self._invitation("accepted-then-cancelled")
        self.client.force_authenticate(user=self.invitee)
        accepted = self.client.post(
            "/api/teams/invitations/accept/",
            {"code": invitation.code},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200)

        self.client.force_authenticate(user=self.owner)
        cancel = self.client.post(
            f"/api/teams/invitations/{invitation.id}/cancel/"
        )

        self.assertEqual(cancel.status_code, 400)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "accepted")
        self.assertTrue(
            TeamMember.objects.filter(
                tenant=self.tenant,
                user=self.invitee,
                status="active",
            ).exists()
        )

    def test_refresh_rejects_cancelled_or_suspended_selected_tenant(self):
        for terminal_status in ("cancelled", "suspended"):
            with self.subTest(status=terminal_status):
                self.tenant.status = "active"
                self.tenant.is_active = True
                self.tenant.save(update_fields=["status", "is_active"])
                _, refresh = issue_token_pair(self.owner, tenant_id=self.tenant.id)

                self.tenant.status = terminal_status
                if terminal_status == "cancelled":
                    self.tenant.is_active = False
                self.tenant.save(update_fields=["status", "is_active"])

                response = APIClient().post(
                    "/api/auth/token/refresh/",
                    {"refresh": refresh},
                    format="json",
                )
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("access", response.data)

    def test_refresh_rejects_disabled_selected_membership(self):
        _, refresh = issue_token_pair(self.owner, tenant_id=self.tenant.id)
        self.owner_membership.status = "disabled"
        self.owner_membership.save(update_fields=["status"])

        response = APIClient().post(
            "/api/auth/token/refresh/",
            {"refresh": refresh},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access", response.data)

    def test_refresh_rebuilds_role_and_platform_claims(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        _, refresh = issue_token_pair(self.owner, tenant_id=self.tenant.id)

        self.owner.is_staff = False
        self.owner.save(update_fields=["is_staff"])
        self.owner_membership.role = "member"
        self.owner_membership.save(update_fields=["role"])

        response = APIClient().post(
            "/api/auth/token/refresh/",
            {"refresh": refresh},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        claims = FIPAccessToken(response.data["access"])
        self.assertEqual(claims["tenant_id"], self.tenant.id)
        self.assertEqual(claims["roles"], ["member"])
        self.assertEqual(claims["platform_roles"], [])
