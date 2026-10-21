from io import StringIO

import jwt
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from tenants.models import Tenant


class IssueServiceTokenCommandTest(TestCase):
    @override_settings(
        FIP_SERVICE_JWT_ALLOWLIST={"decisionops": ["businessbuilder"]},
    )
    def test_issues_scoped_service_token_for_active_tenant(self):
        tenant = Tenant.objects.create(name="CLI Tenant", slug="cli-tenant")
        stdout = StringIO()

        call_command(
            "issue_service_token",
            "--service",
            "decisionops",
            "--tenant-id",
            str(tenant.id),
            "--scope",
            "businessbuilder",
            stdout=stdout,
        )

        token = stdout.getvalue().strip()
        claims = jwt.decode(
            token,
            settings.JWT_VERIFYING_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
        )
        self.assertEqual(claims["principal_type"], "service")
        self.assertEqual(claims["service_name"], "decisionops")
        self.assertEqual(claims["tenant_id"], tenant.id)
        self.assertEqual(claims["product_scopes"], ["businessbuilder"])
        self.assertEqual(claims["roles"], [])
        self.assertEqual(claims["platform_roles"], [])

    @override_settings(FIP_SERVICE_JWT_ALLOWLIST={"decisionops": ["businessbuilder"]})
    def test_rejects_scope_not_allowlisted_without_output(self):
        tenant = Tenant.objects.create(name="CLI Tenant", slug="cli-tenant")
        stdout = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "issue_service_token",
                "--service",
                "decisionops",
                "--tenant-id",
                str(tenant.id),
                "--scope",
                "datacognis",
                stdout=stdout,
            )

        self.assertEqual(stdout.getvalue(), "")

    @override_settings(FIP_SERVICE_JWT_ALLOWLIST={"decisionops": ["businessbuilder"]})
    def test_rejects_inactive_tenant_without_output(self):
        tenant = Tenant.objects.create(
            name="Inactive CLI Tenant", slug="inactive-cli-tenant", is_active=False
        )
        stdout = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "issue_service_token",
                "--service",
                "decisionops",
                "--tenant-id",
                str(tenant.id),
                "--scope",
                "businessbuilder",
                stdout=stdout,
            )

        self.assertEqual(stdout.getvalue(), "")
