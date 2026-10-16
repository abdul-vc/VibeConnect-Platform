"""Focused Observability, Correlation ID, and Health/Readiness Tests (Phase 7D).

Verifies:
1. Missing or invalid X-Request-ID generates a valid unique correlation ID.
2. Valid incoming X-Request-ID is preserved and returned in response headers.
3. Request context is strictly isolated and cleaned up across requests (zero leakage).
4. StructuredJsonFormatter emits valid JSON with non-sensitive standard fields.
5. Sensitive fields (passwords, secrets, tokens, etc.) are strictly redacted in log output.
6. Exception tracebacks remain observable in structured logs for 500 triage.
7. Liveness (/api/v1/health/) returns HTTP 200 independently of database status.
8. Readiness (/api/v1/health/ready/) returns HTTP 200 when database connectivity is healthy.
9. Readiness (/api/v1/health/ready/) returns HTTP 503 without leaking secrets when DB is unavailable.
10. Outbound LMS connector attaches X-Request-ID when correlation ID is active.
"""

import json
import logging
import sys
from unittest.mock import MagicMock, patch

from django.db import OperationalError
from rest_framework import status
from rest_framework.test import APITestCase

from common.correlation import (
    CORRELATION_ID_REGEX,
    get_correlation_id,
    is_valid_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from common.logging import StructuredJsonFormatter, redact_sensitive_value


class ObservabilityAndCorrelationTests(APITestCase):
    """Verifies request correlation ID handling and contextvar isolation."""

    def tearDown(self):
        super().tearDown()
        # Guarantee clean contextvar state after each test
        token = set_correlation_id(None)
        reset_correlation_id(token)

    def test_missing_request_id_generates_valid_id(self):
        """When incoming request omits X-Request-ID, middleware generates a valid UUID hex."""
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("X-Request-ID", response.headers)
        generated_id = response.headers["X-Request-ID"]
        self.assertTrue(is_valid_correlation_id(generated_id))
        self.assertTrue(bool(CORRELATION_ID_REGEX.match(generated_id)))

    def test_invalid_request_id_replaced_with_generated_id(self):
        """When incoming request provides invalid or dangerous X-Request-ID, it is replaced."""
        invalid_ids = [
            "bad id with spaces",
            "id-with-control-\n-characters",
            "a" * 65,  # Exceeds max length of 64
            "inject;DROP TABLE users;--",
            "",
        ]
        for bad_id in invalid_ids:
            response = self.client.get("/api/v1/health/", HTTP_X_REQUEST_ID=bad_id)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("X-Request-ID", response.headers)
            returned_id = response.headers["X-Request-ID"]
            self.assertNotEqual(returned_id, bad_id)
            self.assertTrue(is_valid_correlation_id(returned_id))

    def test_valid_request_id_preserved_in_response(self):
        """When incoming request provides valid X-Request-ID, it is accepted and reflected."""
        valid_id = "req-test-uuid-456_abc-XYZ"
        response = self.client.get("/api/v1/health/", HTTP_X_REQUEST_ID=valid_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.headers.get("X-Request-ID"), valid_id)

    def test_request_context_isolation_across_requests(self):
        """Verifies contextvar does not leak between requests or persist after request finishes."""
        self.assertIsNone(get_correlation_id())

        res1 = self.client.get("/api/v1/health/", HTTP_X_REQUEST_ID="test-request-one")
        self.assertEqual(res1.headers.get("X-Request-ID"), "test-request-one")
        self.assertIsNone(get_correlation_id(), "ContextVar must be None after request completes")

        res2 = self.client.get("/api/v1/health/", HTTP_X_REQUEST_ID="test-request-two")
        self.assertEqual(res2.headers.get("X-Request-ID"), "test-request-two")
        self.assertIsNone(get_correlation_id(), "ContextVar must be None after second request completes")


class StructuredLoggingFormatterTests(APITestCase):
    """Verifies StructuredJsonFormatter fields, redaction, and exception formatting."""

    def setUp(self):
        super().setUp()
        self.formatter = StructuredJsonFormatter()

    def test_structured_json_logging_format(self):
        """Formatter outputs valid JSON containing standard observability keys."""
        record = logging.LogRecord(
            name="apps.integration_hub",
            level=logging.INFO,
            pathname="apps/integration_hub/views.py",
            lineno=42,
            msg="Provisioning event processed successfully for org %s",
            args=("org_123",),
            exc_info=None,
            func="process_event",
        )
        record.module = "views"

        token = set_correlation_id("trace-abc-123")
        try:
            formatted = self.formatter.format(record)
            data = json.loads(formatted)

            self.assertEqual(data["level"], "INFO")
            self.assertEqual(data["logger"], "apps.integration_hub")
            self.assertEqual(data["message"], "Provisioning event processed successfully for org org_123")
            self.assertEqual(data["correlation_id"], "trace-abc-123")
            self.assertEqual(data["module"], "views")
            self.assertEqual(data["funcName"], "process_event")
            self.assertEqual(data["lineno"], 42)
            self.assertIn("timestamp", data)
        finally:
            reset_correlation_id(token)

    def test_structured_json_logging_redaction(self):
        """Sensitive fields in extra or attributes are replaced with [REDACTED]."""
        record = logging.LogRecord(
            name="apps.identity",
            level=logging.INFO,
            pathname="apps/identity/views.py",
            lineno=10,
            msg="User login attempted",
            args=(),
            exc_info=None,
            func="login",
        )
        record.module = "views"
        # Attach extra fields with sensitive names
        record.user_password = "supersecretpassword123"
        record.client_token = "tok_live_abcdef123456"
        record.m2m_secret = "m2m_shared_secret_val"
        record.api_key = "vck_live_99999"
        record.safe_tenant_code = "acme_corp"

        formatted = self.formatter.format(record)
        data = json.loads(formatted)

        self.assertIn("extra", data)
        extra = data["extra"]
        self.assertEqual(extra["user_password"], "[REDACTED]")
        self.assertEqual(extra["client_token"], "[REDACTED]")
        self.assertEqual(extra["m2m_secret"], "[REDACTED]")
        self.assertEqual(extra["api_key"], "[REDACTED]")
        self.assertEqual(extra["safe_tenant_code"], "acme_corp")

    def test_structured_json_logging_exception_handling(self):
        """Log records with exception info format exception without crashing and redact secrets in tracebacks."""
        try:
            raise ValueError("Connection failed with secret='super_secret_token_val' for test")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="django.request",
            level=logging.ERROR,
            pathname="common/views.py",
            lineno=50,
            msg="Internal Server Error: /api/v1/test/",
            args=(),
            exc_info=exc_info,
            func="dispatch",
        )
        record.module = "views"

        formatted = self.formatter.format(record)
        data = json.loads(formatted)

        self.assertEqual(data["level"], "ERROR")
        self.assertIn("exception", data)
        self.assertIn("ValueError", data["exception"])
        self.assertNotIn("super_secret_token_val", data["exception"])
        self.assertIn("secret=[REDACTED]", data["exception"])

    def test_rendered_message_string_sanitization(self):
        """Rendered log message strings redact embedded Bearer/Basic tokens, access/refresh tokens, client secrets, query codes, and cookies."""
        test_cases = [
            (
                "Outbound call Authorization: Bearer eyJhbGciOi_secret_jwt_token_here",
                "Outbound call Authorization: Bearer [REDACTED]",
            ),
            (
                "Outbound call Authorization: Basic YWRtaW46cGFzc3dvcmQxMjM=",
                "Outbound call Authorization: Basic [REDACTED]",
            ),
            (
                "Connecting to https://lms.test/api/v1/sso/?code=auth_code_secret_999&state=active",
                "Connecting to https://lms.test/api/v1/sso/?code=[REDACTED]&state=active",
            ),
            (
                "Callback redirect https://app.test/cb?state=ok&code=code_in_second_param",
                "Callback redirect https://app.test/cb?state=ok&code=[REDACTED]",
            ),
            (
                "Uppercase query param: https://app.test/?CODE=code_uppercase_val",
                "Uppercase query param: https://app.test/?CODE=[REDACTED]",
            ),
            (
                "Token exchange payload: access_token=tok_access_live_12345",
                "Token exchange payload: access_token=[REDACTED]",
            ),
            (
                "Token refresh payload: refresh_token=tok_refresh_live_67890",
                "Token refresh payload: refresh_token=[REDACTED]",
            ),
            (
                "Client credentials: client_secret='cs_secret_val_111'",
                "Client credentials: client_secret=[REDACTED]",
            ),
            (
                "M2M credentials: m2m_secret=\"m2m_shared_secret_222\"",
                "M2M credentials: m2m_secret=[REDACTED]",
            ),
            (
                "Failed authentication for user admin with password='raw_password_xyz'",
                "Failed authentication for user admin with password=[REDACTED]",
            ),
            (
                "Session header received: sessionid=sess_cookie_val_123; csrftoken=csrf_456",
                "Session header received: sessionid=[REDACTED]; csrftoken=[REDACTED]",
            ),
            (
                "Uppercase assignment: ACCESS_TOKEN: 'token_caps_val'",
                "Uppercase assignment: ACCESS_TOKEN:[REDACTED]",
            ),
        ]
        for raw_msg, expected_pattern in test_cases:
            record = logging.LogRecord(
                name="apps.identity",
                level=logging.WARNING,
                pathname="apps/identity/views.py",
                lineno=99,
                msg=raw_msg,
                args=(),
                exc_info=None,
                func="test_view",
            )
            record.module = "views"
            formatted = self.formatter.format(record)
            data = json.loads(formatted)
            self.assertEqual(data["message"], expected_pattern)

    def test_safe_identifiers_preserved_in_logs(self):
        """Safe identifiers (tenant codes, correlation IDs, user IDs) are not accidentally redacted."""
        record = logging.LogRecord(
            name="apps.tenants",
            level=logging.INFO,
            pathname="apps/tenants/views.py",
            lineno=15,
            msg="Processing tenant %s for user %s with job %s",
            args=("tenant_acme_corp", "user_uuid_12345", "job_batch_789"),
            exc_info=None,
            func="process_tenant",
        )
        record.module = "views"
        token = set_correlation_id("corr-id-alpha-beta-999")
        try:
            formatted = self.formatter.format(record)
            data = json.loads(formatted)
            self.assertEqual(
                data["message"],
                "Processing tenant tenant_acme_corp for user user_uuid_12345 with job job_batch_789",
            )
            self.assertEqual(data["correlation_id"], "corr-id-alpha-beta-999")
        finally:
            reset_correlation_id(token)

    def test_correlation_fallback_to_request_object(self):
        """When ContextVar has been reset (e.g. in django.request log_response), correlation_id is resolved from record.request."""
        from unittest.mock import Mock

        # ContextVar is explicitly None
        self.assertIsNone(get_correlation_id())

        mock_request = Mock()
        mock_request.correlation_id = "req-from-django-handler-888"

        record = logging.LogRecord(
            name="django.request",
            level=logging.ERROR,
            pathname="django/core/handlers/exception.py",
            lineno=123,
            msg="Internal Server Error: /api/v1/test/",
            args=(),
            exc_info=None,
            func="log_response",
        )
        record.module = "exception"
        record.request = mock_request

        formatted = self.formatter.format(record)
        data = json.loads(formatted)

        self.assertEqual(data["correlation_id"], "req-from-django-handler-888")
        self.assertNotIn("request", data.get("extra", {}))

    def test_correlation_fallback_rejects_unvalidated_request_id(self):
        """Fallback to record.request rejects dangerous or invalid correlation IDs."""
        from unittest.mock import Mock

        self.assertIsNone(get_correlation_id())

        mock_request = Mock()
        mock_request.correlation_id = "invalid id with spaces; DROP TABLE"

        record = logging.LogRecord(
            name="django.request",
            level=logging.ERROR,
            pathname="django/core/handlers/exception.py",
            lineno=123,
            msg="Internal Server Error: /api/v1/test/",
            args=(),
            exc_info=None,
            func="log_response",
        )
        record.module = "exception"
        record.request = mock_request

        formatted = self.formatter.format(record)
        data = json.loads(formatted)

        self.assertIsNone(data["correlation_id"])


class HealthAndReadinessEndpointTests(APITestCase):
    """Verifies liveness and readiness probe separation and response contracts."""

    def test_liveness_endpoint_behavior(self):
        """GET /api/v1/health/ returns HTTP 200 with minimal process status."""
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"status": "healthy", "service": "vibeconnect_backend"})

    def test_liveness_independent_of_database(self):
        """Liveness probe must succeed even when database is simulated as down."""
        with patch("django.db.connection.cursor", side_effect=OperationalError("DB Connection Down")):
            response = self.client.get("/api/v1/health/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.json()["status"], "healthy")

    def test_readiness_endpoint_success(self):
        """GET /api/v1/health/ready/ returns HTTP 200 when database connectivity succeeds."""
        response = self.client.get("/api/v1/health/ready/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["services"]["database"], "connected")

    def test_readiness_endpoint_database_failure(self):
        """GET /api/v1/health/ready/ returns HTTP 503 without leaking credentials on DB failure."""
        with patch("django.db.connection.cursor", side_effect=OperationalError("FATAL: database unreachable")):
            response = self.client.get("/api/v1/health/ready/")
            self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            data = response.json()
            self.assertEqual(data["status"], "unhealthy")
            self.assertEqual(data["services"]["database"], "unavailable")
            # Verify no credentials or connection strings leaked in payload
            self.assertNotIn("FATAL", str(data))
            self.assertNotIn("password", str(data))


class OutboundConnectorCorrelationTests(APITestCase):
    """Verifies correlation ID propagation in centralized outbound LMS HTTP connector."""

    @patch("urllib.request.urlopen")
    def test_outbound_lms_connector_attaches_request_id(self, mock_urlopen):
        """LmsConnectorClient attaches X-Request-ID when active in current context."""
        from apps.integration_hub.lms_connector import LmsConnectorClient

        # Setup mock HTTP response
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"success": true}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        client = LmsConnectorClient(base_url="https://lms.test", secret="test_secret_123")

        # Set correlation ID in context
        token = set_correlation_id("outbound-trace-777")
        try:
            client._send_request(
                endpoint="/api/v1/integration/test/",
                payload={"action": "sync"},
                operation_label="test sync",
            )
        finally:
            reset_correlation_id(token)

        self.assertTrue(mock_urlopen.called)
        sent_req = mock_urlopen.call_args[0][0]
        self.assertEqual(sent_req.headers.get("X-request-id"), "outbound-trace-777")
