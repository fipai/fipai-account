"""JWT signing, validation, and tenant-aware claim helpers."""
from __future__ import annotations

from datetime import datetime, timezone as datetime_timezone
from typing import Any
import uuid

import jwt
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.backends import TokenBackend, TokenBackendError
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView


class FIPTokenBackend(TokenBackend):
    """SimpleJWT backend that pins both the configured algorithm and key id."""

    def encode(self, payload: dict[str, Any]) -> str:
        jwt_payload = payload.copy()
        if self.audience is not None:
            jwt_payload["aud"] = self.audience
        if self.issuer is not None:
            jwt_payload["iss"] = self.issuer
        token = jwt.encode(
            jwt_payload,
            self.prepared_signing_key,
            algorithm=self.algorithm,
            headers={"typ": "JWT", "kid": settings.JWT_KEY_ID},
            json_encoder=self.json_encoder,
        )
        return token.decode("utf-8") if isinstance(token, bytes) else token

    def decode(self, token: str, verify: bool = True) -> dict[str, Any]:
        if verify:
            try:
                header = jwt.get_unverified_header(token)
            except jwt.PyJWTError as exc:
                raise TokenBackendError("Invalid token header") from exc
            if header.get("alg") != self.algorithm:
                raise TokenBackendError("Token algorithm does not match configuration")
            known_kids = {settings.JWT_KEY_ID} | set(
                getattr(settings, "JWT_PREVIOUS_VERIFYING_KEYS", {})
            )
            if header.get("kid") not in known_kids:
                raise TokenBackendError("Token key id does not match configuration")
        return super().decode(token, verify=verify)

    def get_verifying_key(self, token):
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        previous_keys = getattr(settings, "JWT_PREVIOUS_VERIFYING_KEYS", {})
        if kid in previous_keys:
            return self._prepare_key(previous_keys[kid])
        return super().get_verifying_key(token)


def _new_token_backend() -> FIPTokenBackend:
    return FIPTokenBackend(
        algorithm=api_settings.ALGORITHM,
        signing_key=api_settings.SIGNING_KEY,
        verifying_key=api_settings.VERIFYING_KEY,
        audience=api_settings.AUDIENCE,
        issuer=api_settings.ISSUER,
        leeway=api_settings.LEEWAY,
        json_encoder=api_settings.JSON_ENCODER,
    )


class _FIPTokenBackendMixin:
    """Give each token instance its backend without monkeypatching SimpleJWT state."""

    _fip_token_backend: FIPTokenBackend | None = None

    @property
    def token_backend(self) -> FIPTokenBackend:
        if self._fip_token_backend is None:
            self._fip_token_backend = _new_token_backend()
        return self._fip_token_backend


class FIPAccessToken(_FIPTokenBackendMixin, AccessToken):
    pass


class FIPRefreshToken(_FIPTokenBackendMixin, RefreshToken):
    access_token_class = FIPAccessToken


class FIPTokenRefreshSerializer(TokenRefreshSerializer):
    token_class = FIPRefreshToken

    def validate(self, attrs: dict[str, Any]) -> dict[str, str]:
        """Rotate a locked server-side family and rebuild authorization claims."""
        from .models import AuthSession

        refresh = self.token_class(attrs["refresh"])
        sid_value = refresh.payload.get("sid")
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM)
        token_jti = refresh.payload.get(api_settings.JTI_CLAIM)
        if not sid_value or user_id is None or not token_jti:
            raise AuthenticationFailed("Token is invalid or expired.", "token_not_valid")
        try:
            sid = uuid.UUID(str(sid_value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AuthenticationFailed(
                "Token is invalid or expired.", "token_not_valid"
            ) from exc

        rejection = None
        data = None
        with transaction.atomic():
            try:
                auth_session = (
                    AuthSession.objects.select_for_update()
                    .select_related("user")
                    .get(sid=sid)
                )
            except AuthSession.DoesNotExist:
                rejection = "Token is invalid or expired."
            else:
                now = timezone.now()
                if str(auth_session.user_id) != str(user_id):
                    rejection = "Token is invalid or expired."
                elif auth_session.revoked_at is not None:
                    rejection = "Token is invalid or expired."
                elif auth_session.expires_at <= now:
                    auth_session.revoked_at = now
                    auth_session.revoked_reason = "expired"
                    auth_session.save(update_fields=["revoked_at", "revoked_reason", "updated_at"])
                    rejection = "Token is invalid or expired."
                elif auth_session.current_refresh_jti != str(token_jti):
                    # Persist this before rejecting: raising inside atomic would roll it back.
                    auth_session.revoked_at = now
                    auth_session.revoked_reason = "refresh_reuse"
                    auth_session.reuse_detected_at = now
                    auth_session.save(
                        update_fields=[
                            "revoked_at",
                            "revoked_reason",
                            "reuse_detected_at",
                            "updated_at",
                        ]
                    )
                    rejection = "Token is invalid or expired."
                else:
                    user = auth_session.user
                    if not api_settings.USER_AUTHENTICATION_RULE(user):
                        rejection = "Token is invalid or expired."
                    else:
                        selected_tenant_id = refresh.payload.get("tenant_id")
                        current_claims = build_tenant_claims(
                            user, tenant_id=selected_tenant_id
                        )
                        if (
                            selected_tenant_id is not None
                            and current_claims["tenant_id"] != selected_tenant_id
                        ):
                            rejection = "Tenant context is no longer active."
                        else:
                            for claim, value in current_claims.items():
                                refresh[claim] = value
                            refresh["sid"] = str(auth_session.sid)
                            refresh.set_jti()
                            refresh.set_exp()
                            refresh.set_iat()
                            auth_session.current_refresh_jti = str(
                                refresh.payload[api_settings.JTI_CLAIM]
                            )
                            auth_session.expires_at = datetime.fromtimestamp(
                                refresh.payload["exp"], tz=datetime_timezone.utc
                            )
                            auth_session.save(
                                update_fields=[
                                    "current_refresh_jti",
                                    "expires_at",
                                    "updated_at",
                                ]
                            )
                            data = {
                                "access": str(refresh.access_token),
                                "refresh": str(refresh),
                            }

        if rejection is not None or data is None:
            code = "tenant_inactive" if rejection and rejection.startswith("Tenant") else "token_not_valid"
            raise AuthenticationFailed(rejection or "Token is invalid or expired.", code)
        return data


def get_active_tenant_memberships(user):
    """Return active memberships for lifecycle-eligible tenants."""
    from teams.models import TeamMember
    from tenants.eligibility import eligible_tenant_filters

    return TeamMember.objects.filter(
        user=user,
        status="active",
        **eligible_tenant_filters(),
    ).select_related("tenant")


def get_active_tenant_membership(user, tenant_id=None):
    """Resolve an active membership, defaulting to the first active tenant."""
    memberships = get_active_tenant_memberships(user)
    if tenant_id is not None:
        memberships = memberships.filter(tenant_id=tenant_id)
    return memberships.first()


def get_membership_product_scopes(membership):
    """Calculate product access only from subscriptions belonging to this tenant."""
    from subscriptions.models import Subscription

    subscribed_products = set(
        Subscription.objects.filter(
            tenant_id=membership.tenant_id,
            status="active",
            end_date__gt=timezone.now(),
        ).values_list("plan__product", flat=True)
    )
    permissions = membership.product_permissions
    if not isinstance(permissions, dict) or not permissions:
        return sorted(subscribed_products)
    return sorted(
        product
        for product in subscribed_products
        if isinstance(permissions.get(product), dict)
        and permissions[product].get("access") is True
    )


def build_tenant_claims(user, tenant_id=None):
    """Build tenant claims separately from platform-wide authorization claims."""
    membership = get_active_tenant_membership(user, tenant_id=tenant_id)
    claims = {
        "tenant_id": None,
        "enterprise_id": None,
        "product_scopes": [],
        "roles": [],
        "platform_roles": ["platform_admin"] if user.is_staff or user.is_superuser else [],
    }
    if membership is not None:
        claims.update(
            tenant_id=membership.tenant_id,
            # DataCognis keys its multi-tenant rows on a numeric enterprise id, so
            # it consumes this claim rather than tenant_id.
            enterprise_id=membership.tenant_id,
            product_scopes=get_membership_product_scopes(membership),
            roles=[membership.role],
        )
    # Phase 9 — 个人/企业区分（向后兼容：缺 profile 的旧用户不写 claim）
    profile = getattr(user, "profile", None)
    if profile is not None:
        claims["account_type"] = profile.account_type
        claims["tenant_type"] = profile.account_type

    # Cross-product SSO identity claims (Phase: FIP Account Identity Unification)
    # 让 orcha.fipai.cn / cognis.fipai.cn / ops.fipai.cn 直接从 JWT 读到真名/邮箱/头像,
    # 不再各自 hardcode demo 名字 (张三/张明远/stub-user-1)。
    full_name = (user.get_full_name() or "").strip()
    claims["name"] = full_name or user.username
    claims["email"] = user.email or ""
    claims["username"] = user.username
    if profile is not None:
        if profile.display_name:
            claims["display_name"] = profile.display_name
        if profile.avatar_url:
            claims["avatar_url"] = profile.avatar_url
    return claims


def build_tenant_summary(membership):
    """Serialize the tenant context exposed by the tenant-list endpoint."""
    return {
        "tenant_id": membership.tenant_id,
        "tenant_name": membership.tenant.name,
        "roles": [membership.role],
        "product_scopes": get_membership_product_scopes(membership),
    }


def add_custom_token_claims(refresh_token, user, tenant_id=None):
    """Apply all public authorization claims to a refresh/access token pair."""
    for claim, value in build_tenant_claims(user, tenant_id=tenant_id).items():
        refresh_token[claim] = value
    return refresh_token


def _token_expiry(token) -> datetime:
    return datetime.fromtimestamp(token.payload["exp"], tz=datetime_timezone.utc)


def issue_token_pair(user, tenant_id=None):
    """Create a server-side refresh family and issue its first token pair."""
    from .models import AuthSession

    with transaction.atomic():
        refresh = FIPRefreshToken.for_user(user)
        sid = uuid.uuid4()
        refresh["sid"] = str(sid)
        add_custom_token_claims(refresh, user, tenant_id=tenant_id)
        AuthSession.objects.create(
            sid=sid,
            user=user,
            current_refresh_jti=str(refresh.payload[api_settings.JTI_CLAIM]),
            expires_at=_token_expiry(refresh),
        )
        access = str(refresh.access_token)
        refresh_string = str(refresh)
    return access, refresh_string


def revoke_all_auth_sessions(user, reason: str) -> int:
    """Revoke every active refresh family for a user."""
    from .models import AuthSession

    return AuthSession.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now(), revoked_reason=reason
    )


def revoke_auth_session_from_token(raw_refresh: str, reason: str = "logout") -> bool:
    """Verify a refresh signature then revoke its family, regardless of its jti."""
    from .models import AuthSession

    try:
        refresh = FIPRefreshToken(raw_refresh)
        sid = uuid.UUID(str(refresh.payload.get("sid")))
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM)
        if user_id is None:
            return False
    except Exception:
        return False
    updated = AuthSession.objects.filter(
        sid=sid,
        user_id=user_id,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now(), revoked_reason=reason)
    return bool(updated)



def revoke_auth_session_from_access_token(
    raw_access: str, reason: str = "logout"
) -> bool:
    """Verify an access token and revoke its matching server-side family."""
    from .models import AuthSession

    try:
        access = FIPAccessToken(raw_access)
        sid = uuid.UUID(str(access.payload.get("sid")))
        user_id = access.payload.get(api_settings.USER_ID_CLAIM)
        if user_id is None:
            return False
    except Exception:
        return False
    updated = AuthSession.objects.filter(
        sid=sid,
        user_id=user_id,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now(), revoked_reason=reason)
    return bool(updated)

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Compatibility serializer that never issues a non-family refresh token."""

    token_class = FIPRefreshToken

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        return add_custom_token_claims(token, user)

    def validate(self, attrs):
        credentials = {
            self.username_field: attrs[self.username_field],
            "password": attrs["password"],
        }
        request = self.context.get("request")
        if request is not None:
            credentials["request"] = request
        self.user = authenticate(**credentials)
        if self.user is None or not api_settings.USER_AUTHENTICATION_RULE(self.user):
            raise AuthenticationFailed(
                self.error_messages["no_active_account"], "no_active_account"
            )
        if getattr(getattr(self.user, "two_factor_auth", None), "enabled", False):
            raise AuthenticationFailed("Additional authentication required.", "2fa_required")
        access, refresh = issue_token_pair(self.user)
        return {"access": access, "refresh": refresh}


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
