from __future__ import annotations

from typing import Optional, Tuple

from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieOrHeaderJWTAuthentication(JWTAuthentication):
    """
    JWTAuthentication with a cookie fallback.

    - Prefer Authorization header.
    - If missing, read HttpOnly cookie `fip_access_token` (shared-cookie SSO).

    Note: This enables cookie-based auth for endpoints that explicitly opt in
    via `authentication_classes`, keeping the blast radius small.
    """

    cookie_name = "fip_access_token"

    def authenticate(self, request) -> Optional[Tuple[object, object]]:
        header = self.get_header(request)
        if header is None:
            cookie_token = request.COOKIES.get(self.cookie_name)
            if not cookie_token:
                return None
            header = (b"Bearer " + cookie_token.encode("utf-8"))

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token

