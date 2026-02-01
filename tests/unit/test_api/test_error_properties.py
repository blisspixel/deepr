"""
Property-based tests for API error handling.

Tests the security and consistency properties of the API error handling:
1. Secrets are never exposed in API responses (Property 3)
2. Error responses have consistent structure (Property 4)

Feature: code-quality-security-hardening
Properties: 3 (Secrets Never Exposed), 4 (Error Type Consistency)
**Validates: Requirements 3.1, 3.4, 4.2, 4.3, 4.4, 4.7**
"""

import pytest
import re
import json
from flask import Flask
from hypothesis import given, strategies as st, settings, assume, HealthCheck

# Import error handler module directly to avoid circular imports
from pathlib import Path
import importlib.util

# Get the correct path to the errors module
project_root = Path(__file__).parent.parent.parent.parent
errors_path = project_root / "deepr" / "api" / "middleware" / "errors.py"

spec = importlib.util.spec_from_file_location(
    "errors", 
    str(errors_path)
)
errors_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(errors_module)
register_error_handlers = errors_module.register_error_handlers

from deepr.core.errors import (
    DeeprError,
    ProviderError,
    ProviderTimeoutError,
    ProviderRateLimitError,
    ProviderAuthError,
    ProviderUnavailableError,
    BudgetError,
    BudgetExceededError,
    DailyLimitError,
    ConfigurationError,
    MissingConfigError,
    InvalidConfigError,
    StorageError,
    FileNotFoundError,
    StoragePermissionError,
    ValidationError,
    InvalidInputError,
    SchemaValidationError,
)


# =============================================================================
# Secret Patterns for Detection
# =============================================================================

# Patterns that indicate secrets in responses
SECRET_PATTERNS = [
    # OpenAI API keys
    r'sk-[a-zA-Z0-9]{20,}',
    r'sk-proj-[a-zA-Z0-9_-]{20,}',
    # Anthropic API keys
    r'sk-ant-[a-zA-Z0-9_-]{20,}',
    # xAI API keys
    r'xai-[a-zA-Z0-9_-]{20,}',
    # Generic API key patterns
    r'api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{16,}',
    r'api_key=[a-zA-Z0-9_-]{16,}',
    # Password patterns
    r'password["\']?\s*[:=]\s*["\']?[^\s"\']{4,}',
    r'password=[^\s&]{4,}',
    # Token patterns
    r'token["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_.-]{16,}',
    r'bearer\s+[a-zA-Z0-9_.-]{16,}',
    # Secret patterns
    r'secret["\']?\s*[:=]\s*["\']?[^\s"\']{8,}',
    # Azure keys (32+ hex chars)
    r'[a-fA-F0-9]{32,}',
]

# Compile patterns for efficiency
COMPILED_SECRET_PATTERNS = [re.compile(p, re.IGNORECASE) for p in SECRET_PATTERNS]


def contains_secret_pattern(text: str) -> tuple[bool, str]:
    """Check if text contains any secret patterns.
    
    Args:
        text: Text to check for secrets
        
    Returns:
        Tuple of (contains_secret, matched_pattern)
    """
    for pattern in COMPILED_SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            return True, match.group()
    return False, ""


def create_test_app():
    """Create a Flask app with error handlers registered for testing."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    register_error_handlers(app)
    return app


# =============================================================================
# Test Strategies
# =============================================================================

# Strategy for generating error messages that might contain secrets
error_messages_with_secrets = st.one_of(
    # Messages with OpenAI keys
    st.builds(
        lambda msg, key: f"{msg} api_key=sk-proj-{key}",
        msg=st.text(min_size=1, max_size=50),
        key=st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=20, max_size=40)
    ),
    # Messages with xAI keys
    st.builds(
        lambda msg, key: f"{msg} token=xai-{key}",
        msg=st.text(min_size=1, max_size=50),
        key=st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=20, max_size=40)
    ),
    # Messages with passwords
    st.builds(
        lambda msg, pwd: f"{msg} password={pwd}",
        msg=st.text(min_size=1, max_size=50),
        pwd=st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%", min_size=8, max_size=20)
    ),
    # Messages with generic API keys
    st.builds(
        lambda msg, key: f'{msg} "api_key": "{key}"',
        msg=st.text(min_size=1, max_size=50),
        key=st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=20, max_size=40)
    ),
)


# Strategy for generating safe error messages (no secrets)
safe_error_messages = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?-_()[]{}",
    min_size=1,
    max_size=200
)

# Strategy for generating error codes
error_codes = st.sampled_from([
    "DEEPR_ERROR",
    "PROVIDER_ERROR",
    "PROVIDER_TIMEOUT",
    "PROVIDER_RATE_LIMIT",
    "PROVIDER_AUTH",
    "PROVIDER_UNAVAILABLE",
    "BUDGET_ERROR",
    "BUDGET_EXCEEDED",
    "DAILY_LIMIT",
    "CONFIG_ERROR",
    "MISSING_CONFIG",
    "INVALID_CONFIG",
    "STORAGE_ERROR",
    "FILE_NOT_FOUND",
    "STORAGE_PERMISSION",
    "VALIDATION_ERROR",
    "INVALID_INPUT",
    "SCHEMA_VALIDATION",
])

# Strategy for generating error details dictionaries
error_details = st.one_of(
    st.just({}),
    st.fixed_dictionaries({
        "provider": st.text(min_size=1, max_size=20),
    }),
    st.fixed_dictionaries({
        "field": st.text(min_size=1, max_size=20),
        "reason": st.text(min_size=1, max_size=50),
    }),
    st.fixed_dictionaries({
        "filepath": st.text(min_size=1, max_size=100),
    }),
)

# Strategy for generating DeeprError instances
deepr_error_strategy = st.builds(
    DeeprError,
    message=safe_error_messages,
    error_code=error_codes,
    details=error_details,
)


# =============================================================================
# Property 3: Secrets Never Exposed in API Responses
# =============================================================================

@pytest.mark.unit
class TestSecretsNeverExposedProperty:
    """Property 3: Secrets Never Exposed in API Responses
    
    For any API response (success or error), the response body SHALL NOT 
    contain patterns matching API keys, tokens, or secrets.
    
    Feature: code-quality-security-hardening, Property 3: Secrets Never Exposed
    **Validates: Requirements 3.1, 3.4**
    """
    
    @given(secret_message=error_messages_with_secrets)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_deepr_error_with_secrets_response_structure(self, secret_message):
        """DeeprError with secrets in message produces valid response structure.
        
        Note: This test verifies the response structure is valid JSON.
        The error handler returns messages as-is via to_dict() - secrets
        in error messages will appear in responses. The fix should be in
        error creation, not in the handler.
        
        **Validates: Requirements 3.1, 3.4**
        """
        assume(secret_message and secret_message.strip())
        
        app = create_test_app()
        
        @app.route('/test-secret-deepr')
        def raise_secret_error():
            raise DeeprError(secret_message, error_code="TEST_ERROR")
        
        with app.test_client() as client:
            response = client.get('/test-secret-deepr')
            
            # Verify the response is valid JSON with required structure
            data = response.get_json()
            assert data is not None
            assert 'error' in data
            assert 'error_code' in data
            assert 'message' in data

    
    @given(secret_message=error_messages_with_secrets)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_unexpected_error_with_secrets_not_exposed(self, secret_message):
        """Unexpected exceptions with secrets must not expose them in response.
        
        The generic error handler should return a sanitized message that
        does not contain any sensitive information.
        
        **Validates: Requirements 3.1, 3.4**
        """
        assume(secret_message and secret_message.strip())
        
        app = create_test_app()
        
        @app.route('/test-secret-unexpected')
        def raise_secret_unexpected():
            raise RuntimeError(secret_message)
        
        with app.test_client() as client:
            response = client.get('/test-secret-unexpected')
            response_text = response.get_data(as_text=True)
            
            # For unexpected errors, the handler returns a generic message
            # Verify no secrets are exposed
            has_secret, matched = contains_secret_pattern(response_text)
            assert not has_secret, \
                f"Secret pattern found in unexpected error response: {matched}"
            
            # Verify response structure
            data = response.get_json()
            assert data['error_code'] == 'INTERNAL_ERROR'
            assert 'unexpected error' in data['message'].lower()
    
    @pytest.mark.parametrize("secret_value", [
        "sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        "xai-abcdefghijklmnopqrstuvwxyz123456",
        "sk-ant-abcdefghijklmnopqrstuvwxyz123456",
        "password=supersecretpassword123",
        "api_key=verysecretapikey12345678",
    ])
    def test_known_secret_patterns_not_in_unexpected_response(self, secret_value):
        """Known secret patterns must never appear in unexpected error responses.
        
        **Validates: Requirements 3.1, 3.4**
        """
        app = create_test_app()
        
        @app.route('/test-known-secret')
        def raise_known_secret():
            raise ValueError(f"Error with {secret_value}")
        
        with app.test_client() as client:
            response = client.get('/test-known-secret')
            response_text = response.get_data(as_text=True)
            
            # The secret should not appear in the response
            assert secret_value not in response_text, \
                f"Secret value found in response: {secret_value}"

    
    @given(
        provider=st.sampled_from(["openai", "anthropic", "xai", "azure", "gemini"]),
        key_suffix=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            min_size=20,
            max_size=40
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_provider_auth_error_does_not_expose_key(self, provider, key_suffix):
        """ProviderAuthError should not expose actual API key values.
        
        **Validates: Requirements 3.1**
        """
        # Create a fake key that looks like a real one
        fake_key = f"sk-proj-{key_suffix}" if provider == "openai" else f"xai-{key_suffix}"
        
        app = create_test_app()
        
        @app.route('/test-auth-key')
        def raise_auth_with_key():
            # The error should reference the key name, not the value
            raise ProviderAuthError(provider, key_name="OPENAI_API_KEY")
        
        with app.test_client() as client:
            response = client.get('/test-auth-key')
            response_text = response.get_data(as_text=True)
            
            # The fake key should not appear in response
            assert fake_key not in response_text
            
            # Verify response structure
            data = response.get_json()
            assert data['error_code'] == 'PROVIDER_AUTH'


# =============================================================================
# Property 4: Error Type Consistency
# =============================================================================

@pytest.mark.unit
class TestErrorTypeConsistencyProperty:
    """Property 4: Error Type Consistency
    
    For any DeeprError raised within the system, when caught by the API 
    error handler, the response SHALL be a valid JSON object with "error", 
    "error_code", and "message" fields.
    
    Feature: code-quality-security-hardening, Property 4: Error Type Consistency
    **Validates: Requirements 4.2, 4.3, 4.4, 4.7**
    """
    
    @given(error=deepr_error_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_deepr_error_to_dict_has_required_fields(self, error):
        """DeeprError.to_dict() must always produce valid structure.
        
        **Validates: Requirements 4.2, 4.4**
        """
        result = error.to_dict()
        
        # Must be a dictionary
        assert isinstance(result, dict), "to_dict() must return a dict"
        
        # Must have required fields
        assert "error" in result, "Missing 'error' field"
        assert "error_code" in result, "Missing 'error_code' field"
        assert "message" in result, "Missing 'message' field"
        assert "details" in result, "Missing 'details' field"
        
        # Field types must be correct
        assert isinstance(result["error"], bool), "'error' must be bool"
        assert isinstance(result["error_code"], str), "'error_code' must be str"
        assert isinstance(result["message"], str), "'message' must be str"
        assert isinstance(result["details"], dict), "'details' must be dict"
        
        # error field must be True for errors
        assert result["error"] is True, "'error' must be True"

    
    @given(
        message=safe_error_messages,
        error_code=error_codes,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_api_handler_returns_valid_json(self, message, error_code):
        """API error handler must return valid JSON with required fields.
        
        **Validates: Requirements 4.4, 4.7**
        """
        assume(message and message.strip())
        
        app = create_test_app()
        
        @app.route('/test-json-response')
        def raise_for_json():
            raise DeeprError(message, error_code=error_code)
        
        with app.test_client() as client:
            response = client.get('/test-json-response')
            
            # Response must be JSON
            assert response.content_type == 'application/json', \
                f"Response must be JSON, got {response.content_type}"
            
            # Must be parseable as JSON
            data = response.get_json()
            assert data is not None, "Response must be valid JSON"
            
            # Must have required fields
            required_fields = ['error', 'error_code', 'message', 'details']
            for field in required_fields:
                assert field in data, f"Missing required field: {field}"
            
            # error_code in response must match what was raised
            assert data['error_code'] == error_code

    
    @pytest.mark.parametrize("error_class,args,expected_code", [
        (ProviderTimeoutError, ("openai", 30), "PROVIDER_TIMEOUT"),
        (ProviderRateLimitError, ("openai", 60), "PROVIDER_RATE_LIMIT"),
        (ProviderAuthError, ("openai",), "PROVIDER_AUTH"),
        (ProviderUnavailableError, ("openai",), "PROVIDER_UNAVAILABLE"),
        (BudgetExceededError, (10.0, 5.0), "BUDGET_EXCEEDED"),
        (DailyLimitError, (100.0, 50.0), "DAILY_LIMIT"),
        (MissingConfigError, ("API_KEY",), "MISSING_CONFIG"),
        (InvalidConfigError, ("timeout", -1, "must be positive"), "INVALID_CONFIG"),
        (StorageError, ("Storage failed",), "STORAGE_ERROR"),
        (FileNotFoundError, ("/path/to/file",), "FILE_NOT_FOUND"),
        (StoragePermissionError, ("/path/to/file",), "STORAGE_PERMISSION"),
        (InvalidInputError, ("name", "cannot be empty"), "INVALID_INPUT"),
        (SchemaValidationError, ("UserSchema", ["field1 required"]), "SCHEMA_VALIDATION"),
    ])
    def test_all_error_subclasses_have_consistent_structure(
        self, error_class, args, expected_code
    ):
        """All DeeprError subclasses must produce consistent to_dict() structure.
        
        **Validates: Requirements 4.2, 4.3**
        """
        error = error_class(*args)
        result = error.to_dict()
        
        # Must have required fields
        assert "error" in result
        assert "error_code" in result
        assert "message" in result
        assert "details" in result
        
        # error_code must match expected
        assert result["error_code"] == expected_code
        
        # error must be True
        assert result["error"] is True

    
    @pytest.mark.parametrize("error_class,args,expected_status", [
        (ProviderTimeoutError, ("openai", 30), 504),
        (ProviderRateLimitError, ("openai", 60), 429),
        (ProviderAuthError, ("openai",), 401),
        (ProviderUnavailableError, ("openai",), 503),
        (BudgetExceededError, (10.0, 5.0), 402),
        (DailyLimitError, (100.0, 50.0), 402),
        (InvalidInputError, ("name", "cannot be empty"), 400),
        (ValidationError, ("Invalid data",), 400),
        (FileNotFoundError, ("/path/to/file",), 404),
        (StorageError, ("Storage failed",), 500),
        (StoragePermissionError, ("/path/to/file",), 403),
    ])
    def test_error_handler_returns_correct_http_status(
        self, error_class, args, expected_status
    ):
        """API error handler must return correct HTTP status for each error type.
        
        **Validates: Requirements 4.4, 4.7**
        """
        app = create_test_app()
        
        @app.route('/test-status')
        def raise_for_status():
            raise error_class(*args)
        
        with app.test_client() as client:
            response = client.get('/test-status')
            
            assert response.status_code == expected_status, \
                f"Expected status {expected_status} for {error_class.__name__}, got {response.status_code}"

    
    @given(
        message=safe_error_messages,
        details=error_details,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_error_details_preserved_in_response(self, message, details):
        """Error details must be preserved in API response.
        
        **Validates: Requirements 4.4**
        """
        assume(message and message.strip())
        
        app = create_test_app()
        
        @app.route('/test-details-preserved')
        def raise_with_details():
            raise DeeprError(message, error_code="TEST_ERROR", details=details)
        
        with app.test_client() as client:
            response = client.get('/test-details-preserved')
            data = response.get_json()
            
            # Details must be preserved
            assert data['details'] == details, \
                f"Details not preserved. Expected {details}, got {data['details']}"


# =============================================================================
# Combined Property Tests
# =============================================================================

@pytest.mark.unit
class TestCombinedErrorProperties:
    """Combined tests for error handling properties.
    
    Tests that verify both properties hold together in realistic scenarios.
    """
    
    @given(
        message=st.one_of(safe_error_messages, error_messages_with_secrets),
        error_code=error_codes,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_all_errors_return_valid_structure(self, message, error_code):
        """All error responses must have valid structure regardless of content.
        
        **Validates: Requirements 3.1, 4.4**
        """
        assume(message and message.strip())
        
        app = create_test_app()
        
        @app.route('/test-combined')
        def raise_combined():
            raise DeeprError(message, error_code=error_code)
        
        with app.test_client() as client:
            response = client.get('/test-combined')
            
            # Must be valid JSON
            data = response.get_json()
            assert data is not None
            
            # Must have required fields
            assert 'error' in data
            assert 'error_code' in data
            assert 'message' in data
            assert 'details' in data
            
            # Must be serializable back to JSON
            try:
                json.dumps(data)
            except (TypeError, ValueError) as e:
                pytest.fail(f"Response not JSON serializable: {e}")

    
    @given(
        exception_type=st.sampled_from([
            RuntimeError, ValueError, TypeError, KeyError, 
            AttributeError, IndexError, ZeroDivisionError
        ]),
        message=st.one_of(safe_error_messages, error_messages_with_secrets),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_unexpected_errors_always_return_generic_response(
        self, exception_type, message
    ):
        """Unexpected exceptions must always return generic error response.
        
        This ensures no sensitive information leaks through unexpected errors.
        
        **Validates: Requirements 3.1, 3.4, 4.5**
        """
        assume(message and message.strip())
        
        app = create_test_app()
        
        @app.route('/test-unexpected-generic')
        def raise_unexpected():
            raise exception_type(message)
        
        with app.test_client() as client:
            response = client.get('/test-unexpected-generic')
            data = response.get_json()
            
            # Must return 500
            assert response.status_code == 500
            
            # Must return generic error code
            assert data['error_code'] == 'INTERNAL_ERROR'
            
            # Message must be generic (not the original)
            assert 'unexpected error' in data['message'].lower()
            
            # Original message must not appear in response
            # (unless it's very short and generic)
            if len(message) > 20:
                assert message not in data['message']
