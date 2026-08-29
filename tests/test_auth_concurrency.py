"""PostgreSQL-only row-lock tests for authentication state transitions.

SQLite is intentionally skipped: its database-wide write locking cannot prove the
SELECT FOR UPDATE behavior used in production.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

import pyotp
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from accounts import totp_service
from accounts.jwt import FIPRefreshToken, issue_token_pair
from accounts.models import AuthSession, LoginChallenge, TwoFactorAuth


@skipUnless(
    connection.vendor == "postgresql",
    "PostgreSQL is required to prove refresh/challenge SELECT FOR UPDATE locking; "
    "local SQLite only provides coarse database locks.",
)
class PostgreSQLAuthenticationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="postgres_auth_concurrency",
            password="Passw0rd123",
        )
        self.secret = totp_service.generate_totp_secret()
        tfa = TwoFactorAuth(
            user=self.user,
            enabled=True,
            backup_codes=[],
        )
        tfa.set_totp_secret(self.secret)
        tfa.save()

    @staticmethod
    def _concurrent_post(url, data, barrier):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            response = APIClient().post(url, data, format="json")
            return response.status_code
        finally:
            close_old_connections()

    def test_concurrent_refresh_allows_one_rotation_then_revokes_reused_family(self):
        _, refresh = issue_token_pair(self.user)
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(
                executor.map(
                    lambda _: self._concurrent_post(
                        "/api/auth/token/refresh/",
                        {"refresh": refresh},
                        barrier,
                    ),
                    range(2),
                )
            )

        self.assertEqual(sorted(statuses), [200, 401])
        session = AuthSession.objects.get(sid=FIPRefreshToken(refresh)["sid"])
        self.assertEqual(session.revoked_reason, "refresh_reuse")
        self.assertIsNotNone(session.reuse_detected_at)

    def test_concurrent_challenge_verification_issues_only_one_family(self):
        _, bearer = LoginChallenge.create_for_user(self.user)
        code = pyotp.TOTP(self.secret).now()
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(
                executor.map(
                    lambda _: self._concurrent_post(
                        "/api/auth/2fa/verify/",
                        {"challenge": bearer, "code": code},
                        barrier,
                    ),
                    range(2),
                )
            )

        self.assertEqual(sorted(statuses), [200, 400])
        challenge = LoginChallenge.objects.get(user=self.user)
        self.assertIsNotNone(challenge.used_at)
        self.assertEqual(AuthSession.objects.filter(user=self.user).count(), 1)
