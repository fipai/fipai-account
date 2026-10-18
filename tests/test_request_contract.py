import json
import uuid

from django.test import SimpleTestCase
from django.test import RequestFactory

from accounts.request_context import (
    FIPRequestContextMiddleware,
    TenantContextError,
    validate_tenant_header,
)


class RequestContractTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _middleware(self, response=None):
        def get_response(request):
            request.request_context["view_seen"] = True
            return response or __import__("django.http").http.JsonResponse({"ok": True})

        return FIPRequestContextMiddleware(get_response)

    def test_missing_correlation_id_is_generated_and_returned(self):
        request = self.factory.get("/health/live")
        response = self._middleware()(request)

        correlation_id = response["X-Correlation-Id"]
        self.assertEqual(request.correlation_id, correlation_id)
        uuid.UUID(correlation_id)
        self.assertTrue(request.request_context["view_seen"])

    def test_valid_correlation_and_idempotency_headers_are_normalized(self):
        request = self.factory.post(
            "/api/v1/commands",
            HTTP_X_CORRELATION_ID="workflow-123",
            HTTP_IDEMPOTENCY_KEY="command-123",
        )
        response = self._middleware()(request)

        self.assertEqual(request.correlation_id, "workflow-123")
        self.assertEqual(request.idempotency_key, "command-123")
        self.assertEqual(response["X-Correlation-Id"], "workflow-123")

    def test_invalid_request_metadata_returns_standard_error(self):
        request = self.factory.post(
            "/api/v1/commands",
            HTTP_X_CORRELATION_ID="not valid with spaces",
        )
        response = self._middleware()(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["code"], "CORRELATION_ID_INVALID")
        self.assertNotEqual(response["X-Correlation-Id"], "not valid with spaces")
        uuid.UUID(response["X-Correlation-Id"])

    def test_tenant_header_must_match_token_claim(self):
        self.assertEqual(validate_tenant_header("tenant-a", "tenant-a"), "tenant-a")
        with self.assertRaisesRegex(TenantContextError, "TENANT_HEADER_REQUIRED"):
            validate_tenant_header(None, "tenant-a")
        with self.assertRaisesRegex(TenantContextError, "TENANT_MISMATCH"):
            validate_tenant_header("tenant-b", "tenant-a")
