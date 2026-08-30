"""Minimal process and database health endpoints for deployment probes."""
from __future__ import annotations

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


def _response(status: str, *, http_status: int = 200) -> JsonResponse:
    response = JsonResponse({"status": status}, status=http_status)
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def liveness(_request):
    """Prove that the Django application process can serve requests."""
    return _response("ok")


@require_GET
def readiness(_request):
    """Prove that the application can execute a lightweight database query."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                return _response("unavailable", http_status=503)
    except DatabaseError:
        return _response("unavailable", http_status=503)
    return _response("ok")
