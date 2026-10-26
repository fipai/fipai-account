import datetime
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.jwt import get_membership_product_scopes
from subscriptions.models import Subscription, SubscriptionPlan
from teams.models import TeamMember
from tenants.models import Tenant


class GrantPlatformProductsCommandTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="owner", email="owner@example.com")
        self.tenant = Tenant.objects.create(name="FIP Tenant", slug="fip-tenant")
        self.member = TeamMember.objects.create(
            user=self.user,
            tenant=self.tenant,
            role="owner",
            status="active",
            product_permissions={"agenticorcha": {"access": True, "role": "platform_admin"}},
        )
        # 线上现状：租户只订了 agenticorcha
        plan = SubscriptionPlan.objects.create(
            product="agenticorcha",
            tier="enterprise",
            period="yearly",
            name="FIP.AI AgenticOrcha 企业版",
            price=0,
        )
        Subscription.objects.create(
            user=self.user,
            plan=plan,
            tenant=self.tenant,
            status="active",
            start_date=timezone.now(),
            end_date=timezone.now() + datetime.timedelta(days=3650),
        )

    def test_grants_all_platform_products(self):
        stdout = StringIO()
        call_command("grant_platform_products", "--tenant-id", str(self.tenant.id), stdout=stdout)

        self.member.refresh_from_db()
        scopes = get_membership_product_scopes(self.member)
        self.assertIn("datacognis", scopes)
        self.assertIn("decisionops", scopes)
        self.assertIn("businessbuilder", scopes)
        # 原有授权不能被覆盖掉
        self.assertIn("agenticorcha", scopes)

    def test_is_idempotent(self):
        call_command("grant_platform_products", "--tenant-id", str(self.tenant.id), stdout=StringIO())
        call_command("grant_platform_products", "--tenant-id", str(self.tenant.id), stdout=StringIO())

        # 原有 agenticorcha 套餐 + 新开的三个 = 4
        self.assertEqual(SubscriptionPlan.objects.filter(tier="enterprise").count(), 4)
        self.assertEqual(Subscription.objects.filter(tenant=self.tenant, status="active").count(), 4)

    def test_rejects_unknown_tenant(self):
        with self.assertRaises(CommandError):
            call_command("grant_platform_products", "--tenant-id", "999999", stdout=StringIO())

    def test_rejects_unknown_product(self):
        with self.assertRaises(CommandError):
            call_command(
                "grant_platform_products",
                "--tenant-id",
                str(self.tenant.id),
                "--products",
                "nosuchproduct",
                stdout=StringIO(),
            )
