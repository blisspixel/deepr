"""Tests for error handler middleware.

Tests the centralized error handling for the Flask API, ensuring:
- DeeprError subclasses return structured JSON responses
- HTTP status codes are correctly mapped from error codes
- Unexpected exceptions return generic error (no sensitive details)
- All error logging uses sanitized messages
"""

import importlib.util

# Import directly from the module to avoid circular import issues
# with deepr.api.__init__.py trying to import create_app
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask

# Get the correct path to the errors module
project_root = Path(__file__).parent.parent.parent.parent
errors_path = project_root / "deepr" / "api" / "middleware" / "errors.py"

spec = importlib.util.spec_from_file_location("errors", str(errors_path))
errors_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(errors_module)
register_error_handlers = errors_module.register_error_handlers
ERROR_CODE_TO_HTTP_STATUS = errors_module.ERROR_CODE_TO_HTTP_STATUS

from deepr.core.errors import (
    BudgetExceededError,
    DailyLimitError,
    DeeprError,
    FileNotFoundError,
    InvalidInputError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    StorageError,
    StoragePermissionError,
    ValidationError,
)


@pytest.fixture
def app():
    """Create a Flask app with error handlers registered."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    register_error_handlers(app)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


class TestDeeprErrorHandler:
    """Test handling of DeeprError and subclasses."""

    def test_deepr_error_returns_structured_response(self, app, client):
        """DeeprError should return structured JSON with to_dict() format."""

        @app.route("/test-deepr-error")
        def raise_deepr_error():
            raise DeeprError("Test error message", error_code="TEST_ERROR")

        response = client.get("/test-deepr-error")
        data = response.get_json()

        assert data["error"] is True
        assert data["error_code"] == "TEST_ERROR"
        assert data["message"] == "Test error message"
        assert "details" in data

    def test_provider_timeout_returns_504(self, app, client):
        """ProviderTimeoutError should return HTTP 504."""

        @app.route("/test-timeout")
        def raise_timeout():
            raise ProviderTimeoutError("openai", 30)

        response = client.get("/test-timeout")

        assert response.status_code == 504
        data = response.get_json()
        assert data["error_code"] == "PROVIDER_TIMEOUT"

    def test_provider_rate_limit_returns_429(self, app, client):
        """ProviderRateLimitError should return HTTP 429."""

        @app.route("/test-rate-limit")
        def raise_rate_limit():
            raise ProviderRateLimitError("openai", retry_after=60)

        response = client.get("/test-rate-limit")

        assert response.status_code == 429
        data = response.get_json()
        assert data["error_code"] == "PROVIDER_RATE_LIMIT"

    def test_provider_auth_returns_401(self, app, client):
        """ProviderAuthError should return HTTP 401."""

        @app.route("/test-auth")
        def raise_auth():
            raise ProviderAuthError("openai")

        response = client.get("/test-auth")

        assert response.status_code == 401
        data = response.get_json()
        assert data["error_code"] == "PROVIDER_AUTH"

    def test_provider_unavailable_returns_503(self, app, client):
        """ProviderUnavailableError should return HTTP 503."""

        @app.route("/test-unavailable")
        def raise_unavailable():
            raise ProviderUnavailableError("openai")

        response = client.get("/test-unavailable")

        assert response.status_code == 503
        data = response.get_json()
        assert data["error_code"] == "PROVIDER_UNAVAILABLE"

    def test_budget_exceeded_returns_402(self, app, client):
        """BudgetExceededError should return HTTP 402."""

        @app.route("/test-budget")
        def raise_budget():
            raise BudgetExceededError(10.0, 5.0)

        response = client.get("/test-budget")

        assert response.status_code == 402
        data = response.get_json()
        assert data["error_code"] == "BUDGET_EXCEEDED"

    def test_daily_limit_returns_402(self, app, client):
        """DailyLimitError should return HTTP 402."""

        @app.route("/test-daily-limit")
        def raise_daily_limit():
            raise DailyLimitError(100.0, 50.0)

        response = client.get("/test-daily-limit")

        assert response.status_code == 402
        data = response.get_json()
        assert data["error_code"] == "DAILY_LIMIT"

    def test_invalid_input_returns_400(self, app, client):
        """InvalidInputError should return HTTP 400."""

        @app.route("/test-invalid-input")
        def raise_invalid_input():
            raise InvalidInputError("name", "cannot be empty")

        response = client.get("/test-invalid-input")

        assert response.status_code == 400
        data = response.get_json()
        assert data["error_code"] == "INVALID_INPUT"

    def test_validation_error_returns_400(self, app, client):
        """ValidationError should return HTTP 400."""

        @app.route("/test-validation")
        def raise_validation():
            raise ValidationError("Invalid data")

        response = client.get("/test-validation")

        assert response.status_code == 400
        data = response.get_json()
        assert data["error_code"] == "VALIDATION_ERROR"

    def test_file_not_found_returns_404(self, app, client):
        """FileNotFoundError should return HTTP 404."""

        @app.route("/test-file-not-found")
        def raise_file_not_found():
            raise FileNotFoundError("/path/to/file")

        response = client.get("/test-file-not-found")

        assert response.status_code == 404
        data = response.get_json()
        assert data["error_code"] == "FILE_NOT_FOUND"

    def test_storage_error_returns_500(self, app, client):
        """StorageError should return HTTP 500."""

        @app.route("/test-storage")
        def raise_storage():
            raise StorageError("Storage failed")

        response = client.get("/test-storage")

        assert response.status_code == 500
        data = response.get_json()
        assert data["error_code"] == "STORAGE_ERROR"

    def test_storage_permission_returns_403(self, app, client):
        """StoragePermissionError should return HTTP 403."""

        @app.route("/test-permission")
        def raise_permission():
            raise StoragePermissionError("/path/to/file")

        response = client.get("/test-permission")

        assert response.status_code == 403
        data = response.get_json()
        assert data["error_code"] == "STORAGE_PERMISSION"

    def test_error_details_preserved(self, app, client):
        """Error details should be preserved in response."""

        @app.route("/test-details")
        def raise_with_details():
            raise ProviderTimeoutError("openai", 30)

        response = client.get("/test-details")
        data = response.get_json()

        assert data["details"]["provider"] == "openai"
        assert data["details"]["timeout_seconds"] == 30


class TestUnexpectedErrorHandler:
    """Test handling of unexpected exceptions."""

    def test_unexpected_error_returns_500(self, app, client):
        """Unexpected exceptions should return HTTP 500."""

        @app.route("/test-unexpected")
        def raise_unexpected():
            raise RuntimeError("Something went wrong")

        response = client.get("/test-unexpected")

        assert response.status_code == 500

    def test_unexpected_error_returns_generic_message(self, app, client):
        """Unexpected exceptions should return generic message."""

        @app.route("/test-generic")
        def raise_generic():
            raise ValueError("Sensitive internal error details")

        response = client.get("/test-generic")
        data = response.get_json()

        assert data["error"] is True
        assert data["error_code"] == "INTERNAL_ERROR"
        assert "unexpected error" in data["message"].lower()
        # Sensitive details should NOT be in response
        assert "Sensitive internal error details" not in data["message"]

    def test_unexpected_error_has_empty_details(self, app, client):
        """Unexpected exceptions should have empty details."""

        @app.route("/test-empty-details")
        def raise_empty():
            raise Exception("Error")

        response = client.get("/test-empty-details")
        data = response.get_json()

        assert data["details"] == {}


class TestHTTPExceptionHandler:
    """Test handling of Werkzeug HTTP exceptions."""

    def test_http_404_returns_structured_response(self, app, client):
        """HTTP 404 should return structured JSON."""
        # Request a non-existent route
        response = client.get("/non-existent-route")

        assert response.status_code == 404
        data = response.get_json()
        assert data["error"] is True
        assert data["error_code"] == "HTTP_404"


class TestErrorLogging:
    """Test that error logging uses sanitized messages."""

    def test_deepr_error_logs_sanitized_message(self, app, client):
        """DeeprError logging should use sanitize_log_message."""

        @app.route("/test-log-deepr")
        def raise_for_log():
            raise DeeprError("Error with api_key=sk-proj-secret123")

        # Patch the module's logger and sanitize function directly
        with patch.object(errors_module, "logger") as mock_logger:
            with patch.object(errors_module, "sanitize_log_message") as mock_sanitize:
                mock_sanitize.return_value = "Error with api_key=[REDACTED]"

                client.get("/test-log-deepr")

                mock_sanitize.assert_called()
                mock_logger.error.assert_called()

    def test_unexpected_error_logs_sanitized_traceback(self, app, client):
        """Unexpected error logging should sanitize traceback."""

        @app.route("/test-log-unexpected")
        def raise_for_traceback():
            raise RuntimeError("Error with password=secret123")

        # Patch the module's logger and sanitize function directly
        with patch.object(errors_module, "logger") as mock_logger:
            with patch.object(errors_module, "sanitize_log_message") as mock_sanitize:
                mock_sanitize.return_value = "Sanitized traceback"

                client.get("/test-log-unexpected")

                mock_sanitize.assert_called()
                mock_logger.error.assert_called()


class TestErrorCodeMapping:
    """Test the error code to HTTP status mapping."""

    def test_all_provider_errors_mapped(self):
        """All provider error codes should be mapped."""
        provider_codes = [
            "PROVIDER_TIMEOUT",
            "PROVIDER_RATE_LIMIT",
            "PROVIDER_AUTH",
            "PROVIDER_UNAVAILABLE",
            "PROVIDER_ERROR",
        ]
        for code in provider_codes:
            assert code in ERROR_CODE_TO_HTTP_STATUS

    def test_all_budget_errors_mapped(self):
        """All budget error codes should be mapped."""
        budget_codes = ["BUDGET_EXCEEDED", "DAILY_LIMIT", "BUDGET_ERROR"]
        for code in budget_codes:
            assert code in ERROR_CODE_TO_HTTP_STATUS

    def test_all_validation_errors_mapped(self):
        """All validation error codes should be mapped."""
        validation_codes = ["INVALID_INPUT", "VALIDATION_ERROR", "SCHEMA_VALIDATION"]
        for code in validation_codes:
            assert code in ERROR_CODE_TO_HTTP_STATUS

    def test_all_storage_errors_mapped(self):
        """All storage error codes should be mapped."""
        storage_codes = ["FILE_NOT_FOUND", "STORAGE_ERROR", "STORAGE_PERMISSION"]
        for code in storage_codes:
            assert code in ERROR_CODE_TO_HTTP_STATUS

    def test_unknown_error_code_defaults_to_500(self, app, client):
        """Unknown error codes should default to HTTP 500."""

        @app.route("/test-unknown-code")
        def raise_unknown():
            raise DeeprError("Unknown error", error_code="UNKNOWN_CODE")

        response = client.get("/test-unknown-code")

        assert response.status_code == 500


class TestResponseFormat:
    """Test that all error responses have consistent format."""

    def test_deepr_error_response_is_json(self, app, client):
        """DeeprError response should be valid JSON."""

        @app.route("/test-json-deepr")
        def raise_json():
            raise DeeprError("Test")

        response = client.get("/test-json-deepr")

        assert response.content_type == "application/json"
        assert response.get_json() is not None

    def test_unexpected_error_response_is_json(self, app, client):
        """Unexpected error response should be valid JSON."""

        @app.route("/test-json-unexpected")
        def raise_json_unexpected():
            raise RuntimeError("Test")

        response = client.get("/test-json-unexpected")

        assert response.content_type == "application/json"
        assert response.get_json() is not None

    def test_response_has_required_fields(self, app, client):
        """All error responses should have required fields."""

        @app.route("/test-fields")
        def raise_fields():
            raise DeeprError("Test")

        response = client.get("/test-fields")
        data = response.get_json()

        required_fields = ["error", "error_code", "message", "details"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
