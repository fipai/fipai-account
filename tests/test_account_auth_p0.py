import pyotp

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.jwt import FIPAccessToken, FIPRefreshToken, issue_token_pair
from accounts.models import AuthSession, LoginChallenge, SMSCode, TwoFactorAuth
from accounts import totp_service


User = get_user_model()


class RefreshFamilySecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="family-user", password="Passw0rd123"
        )

    def _refresh(self, token):
        return self.client.post(
            "/api/auth/token/refresh/", {"refresh": token}, format="json"
        )

    def test_refresh_always_rotates_and_carries_sid_in_both_tokens(self):
        access, original = issue_token_pair(self.user)
        response = self._refresh(original)

        self.assertEqual(response.status_code, 200)
        self.assertIn("refresh", response.data)
        self.assertNotEqual(response.data["refresh"], original)
        original_claims = FIPRefreshToken(original)
        rotated_claims = FIPRefreshToken(response.data["refresh"])
        access_claims = FIPAccessToken(response.data["access"])
        self.assertEqual(rotated_claims["sid"], original_claims["sid"])
        self.assertEqual(access_claims["sid"], original_claims["sid"])
        self.assertEqual(FIPAccessToken(access)["sid"], original_claims["sid"])
        session = AuthSession.objects.get(sid=original_claims["sid"])
        self.assertEqual(session.current_refresh_jti, rotated_claims["jti"])

    def test_old_refresh_reuse_revokes_whole_family(self):
        access, original = issue_token_pair(self.user)
        rotated = self._refresh(original)
        self.assertEqual(rotated.status_code, 200)

        reuse = self._refresh(original)
        after_reuse = self._refresh(rotated.data["refresh"])

        self.assertEqual(reuse.status_code, 401)
        self.assertEqual(after_reuse.status_code, 401)
        session = AuthSession.objects.get(sid=FIPRefreshToken(original)["sid"])
        self.assertEqual(session.revoked_reason, "refresh_reuse")
        self.assertIsNotNone(session.reuse_detected_at)
        access_client = APIClient()
        access_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(access_client.get("/api/auth/me/").status_code, 401)

    def test_missing_sid_legacy_refresh_fails_closed(self):
        legacy = FIPRefreshToken.for_user(self.user)
        response = self._refresh(str(legacy))
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access", response.data)

    def test_logout_body_cookie_and_old_family_token_revoke(self):
        for source in ("body", "cookie", "old"):
            with self.subTest(source=source):
                client = APIClient()
                _, original = issue_token_pair(self.user)
                current = original
                supplied = original
                if source == "old":
                    rotated = client.post(
                        "/api/auth/token/refresh/",
                        {"refresh": original},
                        format="json",
                    )
                    self.assertEqual(rotated.status_code, 200)
                    current = rotated.data["refresh"]
                if source == "cookie":
                    client.cookies["fip_refresh_token"] = supplied
                    logout = client.post("/api/auth/logout/", {}, format="json")
                else:
                    logout = client.post(
                        "/api/auth/logout/",
                        {"refresh": supplied},
                        format="json",
                    )
                self.assertEqual(logout.status_code, 200)
                self.assertIn("fip_access_token", logout.cookies)
                self.assertIn("fip_refresh_token", logout.cookies)
                rejected = client.post(
                    "/api/auth/token/refresh/",
                    {"refresh": current},
                    format="json",
                )
                self.assertEqual(rejected.status_code, 401)

    def test_reuse_is_isolated_from_another_family(self):
        _, first = issue_token_pair(self.user)
        _, second = issue_token_pair(self.user)
        first_rotated = self._refresh(first)
        self.assertEqual(first_rotated.status_code, 200)
        self.assertEqual(self._refresh(first).status_code, 401)
        self.assertEqual(self._refresh(first_rotated.data["refresh"]).status_code, 401)
        self.assertEqual(self._refresh(second).status_code, 200)

    def test_password_change_revokes_all_families_and_clears_cookies(self):
        access, first = issue_token_pair(self.user)
        _, second = issue_token_pair(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = self.client.post(
            "/api/auth/password/",
            {"old_password": "Passw0rd123", "new_password": "N3wPassw0rd!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("fip_access_token", response.cookies)
        self.assertIn("fip_refresh_token", response.cookies)
        self.assertFalse(AuthSession.objects.filter(user=self.user, revoked_at=None).exists())
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        anonymous = APIClient()
        self.assertEqual(
            anonymous.post(
                "/api/auth/token/refresh/", {"refresh": first}, format="json"
            ).status_code,
            401,
        )
        self.assertEqual(
            anonymous.post(
                "/api/auth/token/refresh/", {"refresh": second}, format="json"
            ).status_code,
            401,
        )


    def test_missing_sid_legacy_access_fails_closed(self):
        legacy = FIPRefreshToken.for_user(self.user)
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {legacy.access_token}"
        )

        response = client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 401)

    def test_logout_can_revoke_family_from_access_body_header_or_cookie(self):
        for source in ("body", "header", "cookie"):
            with self.subTest(source=source):
                access, refresh = issue_token_pair(self.user)
                sid = FIPRefreshToken(refresh)["sid"]
                client = APIClient()
                data = {}
                if source == "body":
                    data["access"] = access
                elif source == "header":
                    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
                else:
                    client.cookies["fip_access_token"] = access

                response = client.post("/api/auth/logout/", data, format="json")

                self.assertEqual(response.status_code, 200)
                session = AuthSession.objects.get(sid=sid)
                self.assertEqual(session.revoked_reason, "logout")
                self.assertIsNotNone(session.revoked_at)

    def test_logout_with_revoked_refresh_cookie_is_idempotent_and_clears_cookies(self):
        access, refresh = issue_token_pair(self.user)
        first = APIClient().post(
            "/api/auth/logout/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(first.status_code, 200)

        client = APIClient()
        client.cookies["fip_refresh_token"] = refresh
        client.cookies["fip_access_token"] = access
        response = client.post("/api/auth/logout/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.cookies["fip_access_token"]["max-age"], 0)
        self.assertEqual(response.cookies["fip_refresh_token"]["max-age"], 0)

    def test_logout_old_access_cannot_switch_or_access_protected_api_or_create_family(self):
        access, refresh = issue_token_pair(self.user)
        client = APIClient()
        logout = client.post(
            "/api/auth/logout/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(logout.status_code, 200)
        family_count = AuthSession.objects.filter(user=self.user).count()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        switch = client.post(
            "/api/auth/tenant/switch/", {"tenant_id": 1}, format="json"
        )
        protected = client.get("/api/auth/me/")

        self.assertEqual(switch.status_code, 401)
        self.assertEqual(protected.status_code, 401)
        self.assertEqual(
            AuthSession.objects.filter(user=self.user).count(), family_count
        )

    def test_public_login_ignores_stale_access_cookie(self):
        client = APIClient()
        client.cookies["fip_access_token"] = "stale.invalid.token"

        response = client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "Passw0rd123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)


class LoginChallengeSecurityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="13800009999",
            email="challenge@example.com",
            password="Passw0rd123",
        )
        self.secret = totp_service.generate_totp_secret()
        self.backup_plain = "ABCD1234"
        self.tfa = TwoFactorAuth(
            user=self.user,
            enabled=True,
            backup_codes=[totp_service.hash_backup_code(self.backup_plain)],
        )
        self.tfa.set_totp_secret(self.secret)
        self.tfa.save()

    def _password_first_factor(self):
        return self.client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "Passw0rd123"},
            format="json",
        )

    def _verify(self, challenge, code):
        return self.client.post(
            "/api/auth/2fa/verify/",
            {"challenge": challenge, "code": code},
            format="json",
        )

    def test_password_first_factor_returns_only_hashed_challenge(self):
        response = self._password_first_factor()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            set(response.data), {"requires_2fa", "challenge", "expires_in"}
        )
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertNotIn("fip_access_token", response.cookies)
        self.assertNotIn("fip_refresh_token", response.cookies)
        self.assertNotIn("_auth_user_id", self.client.session)
        bearer = response.data["challenge"]
        self.assertGreaterEqual(len(bearer), 43)
        challenge = LoginChallenge.objects.get(user=self.user)
        self.assertNotEqual(challenge.challenge_hash, bearer)
        self.assertEqual(challenge.challenge_hash, LoginChallenge.hash_bearer(bearer))

    def test_phone_first_factor_consumes_sms_then_returns_challenge(self):
        sms = SMSCode.objects.create(
            phone=self.user.username,
            code="123456",
            purpose="login",
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )
        response = self.client.post(
            "/api/auth/login/phone/",
            {"phone": self.user.username, "code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("access", response.data)
        self.assertIn("challenge", response.data)
        sms.refresh_from_db()
        self.assertTrue(sms.is_used)

    def test_totp_challenge_success_issues_family_and_cookies(self):
        first = self._password_first_factor()
        response = self._verify(first.data["challenge"], pyotp.TOTP(self.secret).now())

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        refresh = FIPRefreshToken(response.data["refresh"])
        self.assertTrue(AuthSession.objects.filter(sid=refresh["sid"]).exists())
        self.assertEqual(FIPAccessToken(response.data["access"])["sid"], refresh["sid"])
        self.assertIn("fip_access_token", response.cookies)
        self.assertIn("fip_refresh_token", response.cookies)

    def test_backup_challenge_success_consumes_backup_code(self):
        first = self._password_first_factor()
        response = self._verify(first.data["challenge"], self.backup_plain)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["used_backup"])
        self.tfa.refresh_from_db()
        self.assertEqual(self.tfa.backup_codes, [])

    def test_user_id_cannot_bypass_challenge(self):
        first = self._password_first_factor()
        response = self.client.post(
            "/api/auth/2fa/verify/",
            {
                "user_id": self.user.id,
                "challenge": first.data["challenge"],
                "code": pyotp.TOTP(self.secret).now(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access", response.data)
        self.assertIsNone(LoginChallenge.objects.get(user=self.user).used_at)

    def test_challenge_replay_and_expiry_fail(self):
        first = self._password_first_factor()
        code = pyotp.TOTP(self.secret).now()
        self.assertEqual(self._verify(first.data["challenge"], code).status_code, 200)
        replay = self._verify(first.data["challenge"], code)
        self.assertEqual(replay.status_code, 400)
        self.assertNotIn("access", replay.data)

        second = self._password_first_factor()
        LoginChallenge.objects.filter(user=self.user, used_at=None).update(
            expires_at=timezone.now() - timezone.timedelta(seconds=1)
        )
        expired = self._verify(second.data["challenge"], code)
        self.assertEqual(expired.status_code, 400)
        self.assertNotIn("access", expired.data)

    def test_five_failures_lock_challenge(self):
        first = self._password_first_factor()
        for _ in range(5):
            response = self._verify(first.data["challenge"], "000000")
            self.assertEqual(response.status_code, 400)
        challenge = LoginChallenge.objects.get(user=self.user)
        self.assertEqual(challenge.attempts, 5)
        locked = self._verify(
            first.data["challenge"], pyotp.TOTP(self.secret).now()
        )
        self.assertEqual(locked.status_code, 400)
        self.assertNotIn("access", locked.data)

    def test_disabled_user_cannot_finish_challenge(self):
        first = self._password_first_factor()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self._verify(
            first.data["challenge"], pyotp.TOTP(self.secret).now()
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access", response.data)

    def test_new_challenge_invalidates_older_unused_challenge(self):
        first = self._password_first_factor()
        second = self._password_first_factor()
        self.assertNotEqual(first.data["challenge"], second.data["challenge"])
        old = self._verify(first.data["challenge"], pyotp.TOTP(self.secret).now())
        self.assertEqual(old.status_code, 400)
        self.assertEqual(
            self._verify(second.data["challenge"], pyotp.TOTP(self.secret).now()).status_code,
            200,
        )


class TwoFactorSessionRevocationTests(TestCase):
    def test_enabling_two_factor_revokes_existing_sessions_and_clears_cookies(self):
        user = User.objects.create_user(
            username="enroll-user", password="Passw0rd123"
        )
        access, refresh = issue_token_pair(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        setup = client.post("/api/auth/2fa/setup/", {}, format="json")
        self.assertEqual(setup.status_code, 201)

        verified = client.post(
            "/api/auth/2fa/verify/",
            {"code": pyotp.TOTP(setup.data["secret"]).now()},
            format="json",
        )
        self.assertEqual(verified.status_code, 200)
        self.assertIn("fip_access_token", verified.cookies)
        self.assertIn("fip_refresh_token", verified.cookies)
        self.assertFalse(AuthSession.objects.filter(user=user, revoked_at=None).exists())
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)
        rejected = APIClient().post(
            "/api/auth/token/refresh/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(rejected.status_code, 401)
