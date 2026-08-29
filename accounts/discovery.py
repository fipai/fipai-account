"""Public OpenID discovery metadata for FIP Account JWT verification."""
import base64

from cryptography.hazmat.primitives.serialization import load_pem_public_key
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET


def _base64url_uint(value: int) -> str:
    raw = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _public_json(data: dict, max_age: int) -> JsonResponse:
    response = JsonResponse(data)
    response["Cache-Control"] = f"public, max-age={max_age}"
    return response


@require_GET
def jwks(request):
    keys = []
    if settings.JWT_ALGORITHM == "RS256":
        public_key = load_pem_public_key(settings.JWT_VERIFYING_KEY.encode())
        numbers = public_key.public_numbers()
        keys.append(
            {
                "kty": "RSA",
                "kid": settings.JWT_KEY_ID,
                "use": "sig",
                "alg": "RS256",
                "n": _base64url_uint(numbers.n),
                "e": _base64url_uint(numbers.e),
            }
        )
    return _public_json({"keys": keys}, max_age=300)


@require_GET
def openid_configuration(request):
    return _public_json(
        {
            "issuer": settings.JWT_ISSUER,
            "jwks_uri": f"{settings.JWT_ISSUER}/.well-known/jwks.json",
            "token_endpoint": f"{settings.JWT_ISSUER}/api/auth/login/",
            "grant_types_supported": ["password", "refresh_token"],
            "response_types_supported": ["token"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": [settings.JWT_ALGORITHM],
            "token_endpoint_auth_methods_supported": ["none"],
        },
        max_age=3600,
    )
