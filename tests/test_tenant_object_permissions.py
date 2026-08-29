from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from teams.models import TeamMember
from tenants.models import Tenant


class TenantObjectPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user_model = get_user_model()
        self.tenant = Tenant.objects.create(
            name="Permission Tenant",
            slug="permission-tenant",
            domain="old.example.com",
            owner=self._user("owner"),
            status="active",
            is_active=True,
            current_plan="professional",
            max_users=25,
            max_api_calls=50000,
        )
        self.owner = self.tenant.owner
        self.viewer = self._member("viewer", "viewer")
        self.member = self._member("member", "member")
        self.admin = self._member("admin", "admin")
        TeamMember.objects.create(
            tenant=self.tenant, user=self.owner, role="owner", status="active"
        )
        self.platform_staff = self._user("platform", is_staff=True)
        self.platform_superuser = self._user("superuser", is_superuser=True)
        self.outsider = self._user("outsider")

    def _user(self, label, **kwargs):
        return self.user_model.objects.create_user(
            username=f"{label}_user",
            email=f"{label}@example.com",
            password="Passw0rd123",
            **kwargs,
        )

    def _member(self, label, role):
        user = self._user(label)
        TeamMember.objects.create(
            tenant=self.tenant, user=user, role=role, status="active"
        )
        return user

    def _patch(self, user, payload):
        self.client.force_authenticate(user=user)
        return self.client.patch(
            f"/api/tenants/{self.tenant.id}/", payload, format="json"
        )

    def _delete(self, user):
        self.client.force_authenticate(user=user)
        return self.client.delete(f"/api/tenants/{self.tenant.id}/")

    def test_active_roles_can_list_retrieve_and_members_uses_joined_at(self):
        for user in (self.viewer, self.member, self.admin, self.owner):
            self.client.force_authenticate(user=user)
            list_response = self.client.get("/api/tenants/")
            detail_response = self.client.get(f"/api/tenants/{self.tenant.id}/")
            members_response = self.client.get(
                f"/api/tenants/{self.tenant.id}/members/"
            )

            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(detail_response.status_code, 200)
            self.assertEqual(members_response.status_code, 200)
            self.assertTrue(all(item["joined_at"] for item in members_response.data))

    def test_viewer_member_and_admin_cannot_patch(self):
        for user in (self.viewer, self.member, self.admin):
            response = self._patch(user, {"name": "Forbidden rename"})
            self.assertEqual(response.status_code, 403)

        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.name, "Permission Tenant")

    def test_owner_and_platform_can_patch_basic_fields(self):
        actors = (self.owner, self.platform_staff, self.platform_superuser)
        for index, user in enumerate(actors):
            new_name = f"Allowed rename {index}"
            response = self._patch(user, {"name": new_name})
            self.assertEqual(response.status_code, 200)
            self.tenant.refresh_from_db()
            self.assertEqual(self.tenant.name, new_name)

    def test_sensitive_fields_are_rejected_and_unchanged(self):
        original = {
            "status": self.tenant.status,
            "is_active": self.tenant.is_active,
            "current_plan": self.tenant.current_plan,
            "max_users": self.tenant.max_users,
            "max_api_calls": self.tenant.max_api_calls,
        }

        for field, value in {
            "status": "cancelled",
            "is_active": False,
            "current_plan": "attacker-plan",
            "max_users": 999,
            "max_api_calls": 999999,
        }.items():
            response = self._patch(self.owner, {field: value})
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, str(response.data))

        self.tenant.refresh_from_db()
        for field, value in original.items():
            self.assertEqual(getattr(self.tenant, field), value)

    def test_viewer_member_and_admin_cannot_delete(self):
        for user in (self.viewer, self.member, self.admin):
            response = self._delete(user)
            self.assertEqual(response.status_code, 403)
            self.assertTrue(Tenant.objects.filter(pk=self.tenant.pk).exists())

    def test_owner_delete_soft_deactivates_and_returns_204(self):
        response = self._delete(self.owner)

        self.assertEqual(response.status_code, 204)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status, "cancelled")
        self.assertFalse(self.tenant.is_active)
        self.assertTrue(TeamMember.objects.filter(tenant=self.tenant).exists())
        self.client.force_authenticate(user=self.owner)
        self.assertEqual(
            self.client.get(f"/api/tenants/{self.tenant.id}/").status_code,
            404,
        )

    def test_platform_admin_can_soft_delete_without_membership(self):
        response = self._delete(self.platform_staff)

        self.assertEqual(response.status_code, 204)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.status, "cancelled")
        self.assertFalse(self.tenant.is_active)

    def test_cross_tenant_user_gets_404_for_detail_actions(self):
        self.assertEqual(
            self._patch(self.outsider, {"name": "Hidden"}).status_code, 404
        )
        self.assertEqual(self._delete(self.outsider).status_code, 404)

        self.client.force_authenticate(user=self.outsider)
        self.assertEqual(
            self.client.get(f"/api/tenants/{self.tenant.id}/").status_code, 404
        )
        self.assertEqual(
            self.client.get(
                f"/api/tenants/{self.tenant.id}/members/"
            ).status_code,
            404,
        )
