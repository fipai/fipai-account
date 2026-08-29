from __future__ import annotations

import uuid
from typing import Optional, Tuple

from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import AuthSession


class SessionJWTAuthentication(JWTAuthentication):
    """Header-only JWT authentication backed by an active server-side family."""

    error_message = "Token is invalid or expired."

    def authenticate(self, request) -> Optional[Tuple[object, object]]:
        authenticated = super().authenticate(request)
        if authenticated is None:
            return None

        user, validated_token = authenticated
        try:
            sid = uuid.UUID(str(validated_token.get("sid")))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AuthenticationFailed(self.error_message) from exc

        if not AuthSession.objects.filter(
            sid=sid,
            user_id=user.pk,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).exists():
            raise AuthenticationFailed(self.error_message)

        return user, validated_token


class CookieOrHeaderJWTAuthentication(SessionJWTAuthentication):
    """Session JWT authentication with an access-cookie fallback."""

    cookie_name = "fip_access_token"

    def get_header(self, request):
        header = super().get_header(request)
        if header is not None:
            return header

        cookie_token = request.COOKIES.get(self.cookie_name)
        if not cookie_token:
            return None
        return b"Bearer " + cookie_token.encode("utf-8")
