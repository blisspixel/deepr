"""Tests for core error hierarchy."""

from deepr.core.errors import (
    BudgetError,
    BudgetExceededError,
    ConfigurationError,
    DailyLimitError,
    DeeprError,
    FileNotFoundError,
    InvalidConfigError,
    InvalidInputError,
    MissingConfigError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SchemaValidationError,
    StorageError,
    StoragePermissionError,
    ValidationError,
)


class TestErrorHierarchy:
    """Test exception inheritance."""

    def test_all_errors_inherit_from_deepr_error(self):
        """All custom errors should inherit from DeeprError."""
        errors = [
            ProviderError("test"),
            ProviderTimeoutError("openai", 30),
            ProviderRateLimitError("openai"),
            ProviderAuthError("openai"),
            BudgetError("test"),
            BudgetExceededError(10.0, 5.0),
            DailyLimitError(100.0, 50.0),
            ConfigurationError("test"),
            MissingConfigError("API_KEY"),
            InvalidConfigError("timeout", -1, "must be positive"),
            StorageError("test"),
            FileNotFoundError("/path/to/file"),
            StoragePermissionError("/path/to/file"),
            ValidationError("test"),
            InvalidInputError("name", "cannot be empty"),
            SchemaValidationError("config", ["missing field"]),
        ]

        for error in errors:
            assert isinstance(error, DeeprError)

    def test_provider_errors_inherit_from_provider_error(self):
        """Provider-specific errors should inherit from ProviderError."""
        errors = [
            ProviderTimeoutError("openai", 30),
            ProviderRateLimitError("openai"),
            ProviderAuthError("openai"),
            ProviderUnavailableError("openai"),
        ]

        for error in errors:
            assert isinstance(error, ProviderError)
            assert isinstance(error, DeeprError)

    def test_budget_errors_inherit_from_budget_error(self):
        """Budget-specific errors should inherit from BudgetError."""
        errors = [
            BudgetExceededError(10.0, 5.0),
            DailyLimitError(100.0, 50.0),
        ]

        for error in errors:
            assert isinstance(error, BudgetError)
            assert isinstance(error, DeeprError)


class TestErrorCodes:
    """Test error codes are set correctly."""

    def test_base_error_code(self):
        """DeeprError should have default error code."""
        error = DeeprError("test")
        assert error.error_code == "DEEPR_ERROR"

    def test_provider_timeout_error_code(self):
        """ProviderTimeoutError should have correct code."""
        error = ProviderTimeoutError("openai", 30)
        assert error.error_code == "PROVIDER_TIMEOUT"

    def test_budget_exceeded_error_code(self):
        """BudgetExceededError should have correct code."""
        error = BudgetExceededError(10.0, 5.0)
        assert error.error_code == "BUDGET_EXCEEDED"

    def test_missing_config_error_code(self):
        """MissingConfigError should have correct code."""
        error = MissingConfigError("API_KEY")
        assert error.error_code == "MISSING_CONFIG"


class TestErrorDetails:
    """Test error details are captured correctly."""

    def test_provider_timeout_captures_details(self):
        """ProviderTimeoutError should capture provider and timeout."""
        error = ProviderTimeoutError("openai", 30)

        assert error.details["provider"] == "openai"
        assert error.details["timeout_seconds"] == 30

    def test_budget_exceeded_captures_amounts(self):
        """BudgetExceededError should capture cost and limit."""
        error = BudgetExceededError(10.0, 5.0, "deep_research")

        assert error.details["estimated_cost"] == 10.0
        assert error.details["budget_limit"] == 5.0
        assert error.details["operation"] == "deep_research"

    def test_rate_limit_captures_retry_after(self):
        """ProviderRateLimitError should capture retry_after."""
        error = ProviderRateLimitError("openai", retry_after=60)

        assert error.details["retry_after"] == 60


class TestErrorToDict:
    """Test error serialization."""

    def test_to_dict_includes_all_fields(self):
        """to_dict should include error, code, message, and details."""
        error = BudgetExceededError(10.0, 5.0)
        result = error.to_dict()

        assert result["error"] is True
        assert result["error_code"] == "BUDGET_EXCEEDED"
        assert "message" in result
        assert "details" in result

    def test_to_dict_is_json_serializable(self):
        """to_dict output should be JSON serializable."""
        import json

        error = ProviderTimeoutError("openai", 30)
        result = error.to_dict()

        # Should not raise
        json_str = json.dumps(result)
        assert json_str is not None


class TestErrorMessages:
    """Test error messages are helpful."""

    def test_timeout_message_suggests_retry(self):
        """Timeout error should suggest retrying."""
        error = ProviderTimeoutError("openai", 30)

        assert "try again" in error.message.lower()

    def test_auth_error_mentions_key(self):
        """Auth error should mention API key."""
        error = ProviderAuthError("openai", "OPENAI_API_KEY")

        assert "OPENAI_API_KEY" in error.message

    def test_budget_error_shows_amounts(self):
        """Budget error should show cost and limit."""
        error = BudgetExceededError(10.50, 5.00)

        assert "$10.50" in error.message
        assert "$5.00" in error.message

    def test_daily_limit_mentions_reset(self):
        """Daily limit error should mention reset time."""
        error = DailyLimitError(100.0, 50.0)

        assert "midnight" in error.message.lower() or "reset" in error.message.lower()
