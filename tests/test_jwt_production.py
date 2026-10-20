import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.jwt import FIPTokenBackend, issue_service_access_token, issue_token_pair
from tenants.models import Tenant


PROJECT_DIR = Path(__file__).resolve().parents[1]


def _rsa_pair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return private_pem, public_pem


class AccountJWTContractTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="jwt-user", password="Passw0rd123"
        )

    def _decode(self, token: str) -> dict:
        return jwt.decode(
            token,
            settings.JWT_VERIFYING_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer="https://account.fipai.cn",
            audience="fip-api",
        )

    def test_password_login_and_refresh_use_kid_backend_and_required_claims(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "Passw0rd123"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        for name in ("access", "refresh"):
            token = response.data[name]
            self.assertEqual(jwt.get_unverified_header(token)["kid"], settings.JWT_KEY_ID)
            claims = self._decode(token)
            self.assertEqual(claims["iss"], "https://account.fipai.cn")
            self.assertEqual(claims["aud"], "fip-api")
            self.assertEqual(claims["platform_roles"], [])

        refreshed = self.client.post(
            "/api/auth/token/refresh/",
            {"refresh": response.data["refresh"]},
            format="json",
        )
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(
            jwt.get_unverified_header(refreshed.data["access"])["kid"],
            settings.JWT_KEY_ID,
        )
        self.assertEqual(self._decode(refreshed.data["access"])["platform_roles"], [])

    def test_platform_roles_are_independent_from_tenant_roles(self):
        _, regular_refresh = issue_token_pair(self.user)
        regular_claims = self._decode(regular_refresh)
        self.assertEqual(regular_claims["roles"], [])
        self.assertEqual(regular_claims["platform_roles"], [])

        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        staff_access, _ = issue_token_pair(self.user)
        staff_claims = self._decode(staff_access)
        self.assertEqual(staff_claims["roles"], [])
        self.assertEqual(staff_claims["platform_roles"], ["platform_admin"])

    @override_settings(
        FIP_SERVICE_JWT_ALLOWLIST={"decisionops": ["businessbuilder"]},
    )
    def test_service_access_token_has_scoped_non_user_identity(self):
        tenant = Tenant.objects.create(name="Service Tenant", slug="service-tenant")

        token = issue_service_access_token(
            service_name="decisionops",
            tenant_id=tenant.id,
            product_scopes=["businessbuilder"],
        )
        claims = self._decode(token)

        self.assertEqual(claims["principal_type"], "service")
        self.assertEqual(claims["service_name"], "decisionops")
        self.assertIsNone(claims["user_id"])
        self.assertEqual(claims["tenant_id"], tenant.id)
        self.assertEqual(claims["tenant_uuid"], str(tenant.tenant_uuid))
        self.assertEqual(claims["product_scopes"], ["businessbuilder"])
        self.assertEqual(claims["roles"], [])
        self.assertEqual(claims["platform_roles"], [])
        self.assertEqual(claims["token_type"], "access")

    def test_service_access_token_rejects_unconfigured_scope(self):
        tenant = Tenant.objects.create(name="Service Tenant", slug="service-tenant")

        with self.assertRaises(ValueError):
            issue_service_access_token(
                service_name="decisionops",
                tenant_id=tenant.id,
                product_scopes=["datacognis"],
            )

    def test_jwks_and_openid_publish_only_rsa_public_material(self):
        _, public_pem = _rsa_pair()
        with override_settings(
            JWT_ALGORITHM="RS256",
            JWT_VERIFYING_KEY=public_pem,
            JWT_KEY_ID="account-prod-1",
        ):
            jwks = self.client.get("/.well-known/jwks.json")
            discovery = self.client.get("/.well-known/openid-configuration")

        self.assertEqual(jwks.status_code, 200)
        self.assertIn("public, max-age=300", jwks["Cache-Control"])
        key = jwks.json()["keys"][0]
        self.assertEqual(set(key), {"kty", "kid", "use", "alg", "n", "e"})
        self.assertEqual(
            {key["kty"], key["use"], key["alg"], key["kid"]},
            {"RSA", "sig", "RS256", "account-prod-1"},
        )
        serialized = json.dumps(jwks.json()).lower()
        self.assertNotIn("private", serialized)
        self.assertNotIn('"d"', serialized)

        self.assertEqual(discovery.status_code, 200)
        self.assertIn("public, max-age=3600", discovery["Cache-Control"])
        self.assertEqual(discovery.json()["issuer"], "https://account.fipai.cn")
        self.assertEqual(
            discovery.json()["jwks_uri"],
            "https://account.fipai.cn/.well-known/jwks.json",
        )

    def test_jwks_publishes_previous_public_key_during_rotation(self):
        _, active_public_pem = _rsa_pair()
        _, previous_public_pem = _rsa_pair()
        with override_settings(
            JWT_ALGORITHM="RS256",
            JWT_VERIFYING_KEY=active_public_pem,
            JWT_KEY_ID="account-prod-1",
            JWT_PREVIOUS_VERIFYING_KEYS={"account-prod-0": previous_public_pem},
        ):
            response = self.client.get("/.well-known/jwks.json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {key["kid"] for key in response.json()["keys"]},
            {"account-prod-1", "account-prod-0"},
        )

    def test_previous_kid_is_accepted_during_rotation(self):
        previous_private_pem, previous_public_pem = _rsa_pair()
        now = datetime.now(timezone.utc)
        old_token = jwt.encode(
            {
                "user_id": str(self.user.id),
                "token_type": "access",
                "jti": "old-jti",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
                "iss": "https://account.fipai.cn",
                "aud": "fip-api",
                "tenant_id": "tenant-1",
            },
            previous_private_pem,
            algorithm="RS256",
            headers={"kid": "account-prod-0"},
        )
        with override_settings(
            JWT_ALGORITHM="RS256",
            JWT_VERIFYING_KEY=previous_public_pem,
            JWT_KEY_ID="account-prod-1",
            JWT_PREVIOUS_VERIFYING_KEYS={"account-prod-0": previous_public_pem},
        ):
            backend = FIPTokenBackend(
                algorithm="RS256",
                signing_key=previous_private_pem,
                verifying_key=previous_public_pem,
                audience="fip-api",
                issuer="https://account.fipai.cn",
            )
            decoded = backend.decode(old_token)

        self.assertEqual(decoded["jti"], "old-jti")


class AccountJWTProductionSettingsTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_pem, cls.public_pem = _rsa_pair()

    def _run_settings(self, overrides: dict[str, str]) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        for key in (
            "DJANGO_DEBUG",
            "DJANGO_SECRET_KEY",
            "DJANGO_ALLOWED_HOSTS",
            "JWT_ALGORITHM",
            "JWT_SIGNING_KEY",
            "JWT_VERIFYING_KEY",
            "JWT_KEY_ID",
            "JWT_PREVIOUS_VERIFYING_KEYS",
            "TOTP_ENCRYPTION_KEY_ID",
            "TOTP_ENCRYPTION_KEY",
            "TOTP_PREVIOUS_ENCRYPTION_KEYS",
        ):
            env.pop(key, None)
        env.update(overrides)
        env["PYTHONPATH"] = str(PROJECT_DIR)
        env["DJANGO_SETTINGS_MODULE"] = "fipai.settings"
        return subprocess.run(
            [sys.executable, "-c", "import fipai.settings as s; print(s.JWT_ALGORITHM, s.JWT_ISSUER, s.JWT_AUDIENCE)"],
            cwd=PROJECT_DIR,
            env=env,
            capture_output=True,
            text=True,
        )

    def _valid_environment(self) -> dict[str, str]:
        return {
            "DJANGO_DEBUG": "false",
            "DJANGO_SECRET_KEY": "production-django-secret",
            "DJANGO_ALLOWED_HOSTS": "account.fipai.cn",
            "JWT_ALGORITHM": "RS256",
            "JWT_SIGNING_KEY": self.private_pem,
            "JWT_VERIFYING_KEY": self.public_pem,
            "JWT_KEY_ID": "account-prod-1",
            "TOTP_ENCRYPTION_KEY_ID": "account-totp-test",
            "TOTP_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }

    def test_production_accepts_valid_rs256_contract(self):
        result = self._run_settings(self._valid_environment())
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("RS256 https://account.fipai.cn fip-api", result.stdout)

    def test_production_rejects_hs256_missing_keys_and_default_kid(self):
        for changes in (
            {"JWT_ALGORITHM": "HS256"},
            {"JWT_SIGNING_KEY": ""},
            {"JWT_VERIFYING_KEY": ""},
            {"JWT_KEY_ID": "default"},
            {"JWT_VERIFYING_KEY": "not-a-public-key"},
        ):
            environment = self._valid_environment()
            environment.update(changes)
            result = self._run_settings(environment)
            self.assertNotEqual(result.returncode, 0, msg=changes)

    def test_production_rejects_invalid_previous_jwt_key_config(self):
        for previous_keys in ("[]", "{invalid", json.dumps({"account-prod-1": "old"})):
            environment = self._valid_environment()
            environment["JWT_PREVIOUS_VERIFYING_KEYS"] = previous_keys
            result = self._run_settings(environment)
            self.assertNotEqual(result.returncode, 0, msg=previous_keys)
