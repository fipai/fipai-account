from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from teams.models import Invitation, TeamMember
from tenants.models import Tenant


class TeamPermissionAttackTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()
        self.owner = self._user("owner")
        self.tenant = Tenant.objects.create(
            name="Team Permission Tenant",
            slug="team-permission-tenant",
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.memberships = {
            "owner": TeamMember.objects.create(
                tenant=self.tenant, user=self.owner, role="owner", status="active"
            )
        }
        for role in ("admin", "member", "viewer"):
            user = self._user(role)
            self.memberships[role] = TeamMember.objects.create(
                tenant=self.tenant, user=user, role=role, status="active"
            )

    def _user(self, label, **kwargs):
        return self.user_model.objects.create_user(
            username=f"{label}_user",
            email=f"{label}@example.com",
            password="Passw0rd123",
            **kwargs,
        )

    def _authenticate(self, user):
        self.client.force_authenticate(user=user)

    def _member_url(self, membership, suffix=""):
        return f"/api/teams/members/{membership.id}/{suffix}"

    def test_generic_member_patch_cannot_escalate_then_tenant_write_stays_denied(self):
        for role in ("viewer", "member", "admin"):
            membership = self.memberships[role]
            self._authenticate(membership.user)

            response = self.client.patch(
                self._member_url(membership),
                {
                    "role": "owner",
                    "status": "active",
                    "product_permissions": {"decisionops": {"access": True, "role": "admin"}},
                },
                format="json",
            )
            self.assertEqual(response.status_code, 405)
            membership.refresh_from_db()
            self.assertEqual(membership.role, role)
            self.assertEqual(membership.product_permissions, {})

            tenant_patch = self.client.patch(
                f"/api/tenants/{self.tenant.id}/",
                {"name": f"attacked-by-{role}"},
                format="json",
            )
            tenant_delete = self.client.delete(f"/api/tenants/{self.tenant.id}/")
            self.assertEqual(tenant_patch.status_code, 403)
            self.assertEqual(tenant_delete.status_code, 403)

        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.name, "Team Permission Tenant")
        self.assertTrue(self.tenant.is_active)

    def test_generic_member_put_and_delete_are_explicitly_disabled(self):
        membership = self.memberships["member"]
        self._authenticate(self.owner)
        self.assertEqual(
            self.client.put(
                self._member_url(membership), {"role": "owner"}, format="json"
            ).status_code,
            405,
        )
        self.assertEqual(self.client.delete(self._member_url(membership)).status_code, 405)

    def test_active_member_can_read_same_tenant_members_but_nonmember_gets_404(self):
        self._authenticate(self.memberships["viewer"].user)
        response = self.client.get("/api/teams/members/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["id"] for item in response.data},
            {membership.id for membership in self.memberships.values()},
        )
        self.assertEqual(
            self.client.get(self._member_url(self.memberships["admin"])).status_code,
            200,
        )

        outsider = self._user("outsider")
        self._authenticate(outsider)
        self.assertEqual(
            self.client.get(self._member_url(self.memberships["admin"])).status_code,
            404,
        )

    def test_update_role_enforces_admin_owner_self_and_last_owner_boundaries(self):
        admin = self.memberships["admin"]
        member = self.memberships["member"]

        self._authenticate(admin.user)
        self.assertEqual(
            self.client.put(
                self._member_url(member, "update_role/"),
                {"role": "owner"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.put(
                self._member_url(admin, "update_role/"),
                {"role": "owner"},
                format="json",
            ).status_code,
            403,
        )

        self._authenticate(self.owner)
        self.assertEqual(
            self.client.put(
                self._member_url(member, "update_role/"),
                {"role": "admin"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.put(
                self._member_url(self.memberships["owner"], "update_role/"),
                {"role": "admin"},
                format="json",
            ).status_code,
            400,
        )
        self.memberships["owner"].refresh_from_db()
        self.assertEqual(self.memberships["owner"].role, "owner")

    def test_update_permissions_and_remove_recheck_requester_in_target_tenant(self):
        target = self.memberships["member"]
        viewer = self.memberships["viewer"]

        self._authenticate(viewer.user)
        self.assertEqual(
            self.client.put(
                self._member_url(target, "update_permissions/"),
                {"product_permissions": {"decisionops": {"access": True}}},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(self._member_url(target, "remove/")).status_code,
            403,
        )

        self._authenticate(self.memberships["admin"].user)
        self.assertEqual(
            self.client.put(
                self._member_url(target, "update_permissions/"),
                {"product_permissions": {"decisionops": {"access": True}}},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.put(
                self._member_url(self.memberships["admin"], "update_permissions/"),
                {"product_permissions": {"decisionops": {"access": True}}},
                format="json",
            ).status_code,
            403,
        )

        self._authenticate(self.owner)
        self.assertEqual(
            self.client.post(
                self._member_url(self.memberships["owner"], "remove/")
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(self._member_url(target, "remove/")).status_code,
            200,
        )
        target.refresh_from_db()
        self.assertEqual(target.status, "disabled")

    def test_specialized_actions_hide_cross_tenant_targets(self):
        other_owner = self._user("other_owner")
        other_tenant = Tenant.objects.create(
            name="Other Tenant",
            slug="other-team-tenant",
            owner=other_owner,
            status="active",
            is_active=True,
        )
        TeamMember.objects.create(
            tenant=other_tenant, user=other_owner, role="owner", status="active"
        )
        other_member = TeamMember.objects.create(
            tenant=other_tenant,
            user=self._user("other_member"),
            role="member",
            status="active",
        )

        self._authenticate(self.owner)
        requests = (
            self.client.put(
                self._member_url(other_member, "update_role/"),
                {"role": "admin"},
                format="json",
            ),
            self.client.put(
                self._member_url(other_member, "update_permissions/"),
                {"product_permissions": {}},
                format="json",
            ),
            self.client.post(self._member_url(other_member, "remove/")),
        )
        self.assertTrue(all(response.status_code == 404 for response in requests))

    def test_platform_staff_can_manage_without_tenant_membership(self):
        platform_staff = self._user("platform_staff", is_staff=True)
        target = self.memberships["viewer"]
        self._authenticate(platform_staff)
        response = self.client.put(
            self._member_url(target, "update_role/"),
            {"role": "member"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.role, "member")

    def test_invitation_generic_writes_are_disabled_but_actions_remain_available(self):
        invitation = Invitation.objects.create(
            tenant=self.tenant,
            email="cancel@example.com",
            role="member",
            invited_by=self.owner,
            code="cancel-invitation-code",
            expires_at=timezone.now() + timezone.timedelta(days=1),
        )
        self._authenticate(self.owner)
        invitation_url = f"/api/teams/invitations/{invitation.id}/"
        self.assertEqual(
            self.client.patch(invitation_url, {"status": "accepted"}, format="json").status_code,
            405,
        )
        self.assertEqual(
            self.client.put(invitation_url, {"status": "accepted"}, format="json").status_code,
            405,
        )
        self.assertEqual(self.client.delete(invitation_url).status_code, 405)
        self.assertEqual(self.client.post(f"{invitation_url}cancel/").status_code, 200)

        invitee = self._user("invitee")
        accepted = Invitation.objects.create(
            tenant=self.tenant,
            email=invitee.email,
            role="member",
            invited_by=self.owner,
            code="accept-invitation-code",
            expires_at=timezone.now() + timezone.timedelta(days=1),
        )
        self._authenticate(invitee)
        response = self.client.post(
            "/api/teams/invitations/accept/", {"code": accepted.code}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            TeamMember.objects.filter(
                tenant=self.tenant, user=invitee, role="member", status="active"
            ).exists()
        )
