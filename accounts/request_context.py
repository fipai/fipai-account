"""Shared FIP request metadata and tenant-header validation."""
from __future__ import annotations

import re
import uuid
from typing import Any, Callable

from django.http import JsonResponse


CORRELATION_HEADER = "X-Correlation-Id"
IDEMPOTENCY_HEADER = "Idempotency-Key"
TENANT_HEADER = "X-Tenant-Id"
_METADATA_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")


class TenantContextError(ValueError):
    """A non-sensitive tenant-context validation failure."""


def _validate_metadata(value: Any, *, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{name}_INVALID")
    if _METADATA_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name}_INVALID")
    return value


def validate_correlation_id(value: Any) -> str:
    return _validate_metadata(value, name="CORRELATION_ID", maximum=128)


def validate_idempotency_key(value: Any) -> str:
    return _validate_metadata(value, name="IDEMPOTENCY_KEY", maximum=200)


def validate_tenant_header(
    header_value: Any,
    token_tenant_id: Any,
    *,
    required: bool = True,
) -> str | None:
    """Ensure a tenant header is present and equals the JWT tenant claim."""
    if header_value in (None, ""):
        if required:
            raise TenantContextError("TENANT_HEADER_REQUIRED")
        return None
    if token_tenant_id in (None, "") or str(header_value) != str(token_tenant_id):
        raise TenantContextError("TENANT_MISMATCH")
    return str(header_value)


def _error_response(code: str, correlation_id: str) -> JsonResponse:
    message = {
        "CORRELATION_ID_INVALID": "Correlation ID is invalid",
        "IDEMPOTENCY_KEY_INVALID": "Idempotency key is invalid",
    }.get(code, "Request metadata is invalid")
    response = JsonResponse(
        {
            "error": message,
            "code": code,
            "details": {},
            "request_id": correlation_id,
        },
        status=400,
    )
    response[CORRELATION_HEADER] = correlation_id
    return response


class FIPRequestContextMiddleware:
    """Attach and validate the public FIP request metadata headers."""

    def __init__(self, get_response: Callable[..., Any]):
        self.get_response = get_response

    def __call__(self, request):
        request_context = {}
        request.request_context = request_context
        supplied_correlation = request.headers.get(CORRELATION_HEADER)
        correlation_id = supplied_correlation or str(uuid.uuid4())

        try:
            if supplied_correlation is not None:
                validate_correlation_id(supplied_correlation)
            supplied_idempotency = request.headers.get(IDEMPOTENCY_HEADER)
            if supplied_idempotency is not None:
                validate_idempotency_key(supplied_idempotency)
                request.idempotency_key = supplied_idempotency
                request_context["idempotency_key"] = supplied_idempotency
            request.tenant_header = request.headers.get(TENANT_HEADER)
        except ValueError as exc:
            correlation_id = str(uuid.uuid4())
            request.correlation_id = correlation_id
            request_context["correlation_id"] = correlation_id
            return _error_response(str(exc), correlation_id)

        request.correlation_id = correlation_id
        request_context["correlation_id"] = correlation_id
        response = self.get_response(request)
        response[CORRELATION_HEADER] = correlation_id
        return response


def attach_tenant_validation(request, validated_token: dict[str, Any]) -> None:
    """Validate a supplied tenant header against an authenticated JWT."""
    tenant_id = validate_tenant_header(
        request.headers.get(TENANT_HEADER),
        validated_token.get("tenant_id"),
        required=False,
    )
    if tenant_id is not None:
        request.tenant_id = tenant_id
