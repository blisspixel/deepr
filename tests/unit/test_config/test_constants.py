"""Unit tests for configuration constants module.

Tests:
- Default values are correct
- Environment variable overrides work
- Validation errors are raised for invalid values

Requirements: 8.4, 8.5
"""

import os
import pytest
from unittest.mock import patch

from deepr.core.errors import InvalidConfigError


class TestDefaultValues:
    """Test that default configuration values are correct."""
    
    def test_confidence_threshold_default(self):
        """Test CONFIDENCE_THRESHOLD has correct default value."""
        # Import fresh to get defaults
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        assert constants.CONFIDENCE_THRESHOLD == 0.7
    
    def test_health_decay_factor_default(self):
        """Test HEALTH_DECAY_FACTOR has correct default value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        assert constants.HEALTH_DECAY_FACTOR == 0.95
    
    def test_circuit_breaker_failure_threshold_default(self):
        """Test CIRCUIT_BREAKER_FAILURE_THRESHOLD has correct default value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        assert constants.CIRCUIT_BREAKER_FAILURE_THRESHOLD == 5
    
    def test_circuit_breaker_recovery_timeout_default(self):
        """Test CIRCUIT_BREAKER_RECOVERY_TIMEOUT has correct default value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        assert constants.CIRCUIT_BREAKER_RECOVERY_TIMEOUT == 60
    
    def test_cost_buffer_size_default(self):
        """Test COST_BUFFER_SIZE has correct default value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        assert constants.COST_BUFFER_SIZE == 10
    
    def test_cost_flush_interval_default(self):
        """Test COST_FLUSH_INTERVAL has correct default value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        assert constants.COST_FLUSH_INTERVAL == 30
    
    def test_rate_limit_job_submit_default(self):
        """Test RATE_LIMIT_JOB_SUBMIT has correct default value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        assert constants.RATE_LIMIT_JOB_SUBMIT == "10 per minute"
    
    def test_rate_limit_job_status_default(self):
        """Test RATE_LIMIT_JOB_STATUS has correct default value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        assert constants.RATE_LIMIT_JOB_STATUS == "60 per minute"
    
    def test_rate_limit_listing_default(self):
        """Test RATE_LIMIT_LISTING has correct default value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        assert constants.RATE_LIMIT_LISTING == "30 per minute"
    
    def test_rolling_window_size_default(self):
        """Test ROLLING_WINDOW_SIZE has correct default value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        assert constants.ROLLING_WINDOW_SIZE == 20
    
    def test_min_success_rate_default(self):
        """Test MIN_SUCCESS_RATE has correct default value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        assert constants.MIN_SUCCESS_RATE == 0.8
    
    def test_max_stored_fallback_events_default(self):
        """Test MAX_STORED_FALLBACK_EVENTS has correct default value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        assert constants.MAX_STORED_FALLBACK_EVENTS == 100


class TestEnvironmentVariableOverrides:
    """Test that environment variables override default values."""
    
    def test_confidence_threshold_override(self):
        """Test CONFIDENCE_THRESHOLD can be overridden via environment."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_CONFIDENCE_THRESHOLD": "0.9"}):
            importlib.reload(constants)
            constants.load_config()
            assert constants.CONFIDENCE_THRESHOLD == 0.9
    
    def test_health_decay_factor_override(self):
        """Test HEALTH_DECAY_FACTOR can be overridden via environment."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_HEALTH_DECAY_FACTOR": "0.85"}):
            importlib.reload(constants)
            constants.load_config()
            assert constants.HEALTH_DECAY_FACTOR == 0.85
    
    def test_circuit_breaker_failure_threshold_override(self):
        """Test CIRCUIT_BREAKER_FAILURE_THRESHOLD can be overridden."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_CIRCUIT_BREAKER_FAILURE_THRESHOLD": "10"}):
            importlib.reload(constants)
            constants.load_config()
            assert constants.CIRCUIT_BREAKER_FAILURE_THRESHOLD == 10
    
    def test_circuit_breaker_recovery_timeout_override(self):
        """Test CIRCUIT_BREAKER_RECOVERY_TIMEOUT can be overridden."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_CIRCUIT_BREAKER_RECOVERY_TIMEOUT": "120"}):
            importlib.reload(constants)
            constants.load_config()
            assert constants.CIRCUIT_BREAKER_RECOVERY_TIMEOUT == 120
    
    def test_cost_buffer_size_override(self):
        """Test COST_BUFFER_SIZE can be overridden via environment."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_COST_BUFFER_SIZE": "20"}):
            importlib.reload(constants)
            constants.load_config()
            assert constants.COST_BUFFER_SIZE == 20
    
    def test_cost_flush_interval_override(self):
        """Test COST_FLUSH_INTERVAL can be overridden via environment."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_COST_FLUSH_INTERVAL": "60"}):
            importlib.reload(constants)
            constants.load_config()
            assert constants.COST_FLUSH_INTERVAL == 60
    
    def test_rate_limit_job_submit_override(self):
        """Test RATE_LIMIT_JOB_SUBMIT can be overridden via environment."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_RATE_LIMIT_JOB_SUBMIT": "20 per minute"}):
            importlib.reload(constants)
            constants.load_config()
            assert constants.RATE_LIMIT_JOB_SUBMIT == "20 per minute"
    
    def test_rolling_window_size_override(self):
        """Test ROLLING_WINDOW_SIZE can be overridden via environment."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_ROLLING_WINDOW_SIZE": "50"}):
            importlib.reload(constants)
            constants.load_config()
            assert constants.ROLLING_WINDOW_SIZE == 50
    
    def test_min_success_rate_override(self):
        """Test MIN_SUCCESS_RATE can be overridden via environment."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_MIN_SUCCESS_RATE": "0.9"}):
            importlib.reload(constants)
            constants.load_config()
            assert constants.MIN_SUCCESS_RATE == 0.9


class TestValidationErrors:
    """Test that invalid configuration values raise appropriate errors."""
    
    def test_invalid_integer_raises_error(self):
        """Test that non-integer value for integer config raises InvalidConfigError."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_CIRCUIT_BREAKER_FAILURE_THRESHOLD": "not_an_int"}):
            importlib.reload(constants)
            with pytest.raises(InvalidConfigError) as exc_info:
                constants.load_config()
            
            assert "DEEPR_CIRCUIT_BREAKER_FAILURE_THRESHOLD" in str(exc_info.value)
            assert "must be an integer" in str(exc_info.value)
    
    def test_invalid_float_raises_error(self):
        """Test that non-float value for float config raises InvalidConfigError."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_CONFIDENCE_THRESHOLD": "not_a_float"}):
            importlib.reload(constants)
            with pytest.raises(InvalidConfigError) as exc_info:
                constants.load_config()
            
            assert "DEEPR_CONFIDENCE_THRESHOLD" in str(exc_info.value)
            assert "must be a number" in str(exc_info.value)
    
    def test_negative_integer_raises_error(self):
        """Test that negative integer value raises InvalidConfigError."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_COST_BUFFER_SIZE": "-5"}):
            importlib.reload(constants)
            with pytest.raises(InvalidConfigError) as exc_info:
                constants.load_config()
            
            assert "DEEPR_COST_BUFFER_SIZE" in str(exc_info.value)
            assert "must be non-negative" in str(exc_info.value)
    
    def test_negative_float_raises_error(self):
        """Test that negative float value raises InvalidConfigError."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_HEALTH_DECAY_FACTOR": "-0.5"}):
            importlib.reload(constants)
            with pytest.raises(InvalidConfigError) as exc_info:
                constants.load_config()
            
            assert "DEEPR_HEALTH_DECAY_FACTOR" in str(exc_info.value)
            assert "must be non-negative" in str(exc_info.value)


class TestHelperFunctions:
    """Test the helper functions for environment variable loading."""
    
    def test_get_env_int_returns_default_when_not_set(self):
        """Test _get_env_int returns default when env var not set."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            result = constants._get_env_int("NONEXISTENT_VAR", 42)
            assert result == 42
    
    def test_get_env_int_returns_env_value_when_set(self):
        """Test _get_env_int returns env value when set."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        with patch.dict(os.environ, {"TEST_INT_VAR": "100"}):
            result = constants._get_env_int("TEST_INT_VAR", 42)
            assert result == 100
    
    def test_get_env_float_returns_default_when_not_set(self):
        """Test _get_env_float returns default when env var not set."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        with patch.dict(os.environ, {}, clear=True):
            result = constants._get_env_float("NONEXISTENT_VAR", 3.14)
            assert result == 3.14
    
    def test_get_env_float_returns_env_value_when_set(self):
        """Test _get_env_float returns env value when set."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        with patch.dict(os.environ, {"TEST_FLOAT_VAR": "2.718"}):
            result = constants._get_env_float("TEST_FLOAT_VAR", 3.14)
            assert result == 2.718
    
    def test_get_env_int_accepts_zero(self):
        """Test _get_env_int accepts zero as valid value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        with patch.dict(os.environ, {"TEST_ZERO_VAR": "0"}):
            result = constants._get_env_int("TEST_ZERO_VAR", 42)
            assert result == 0
    
    def test_get_env_float_accepts_zero(self):
        """Test _get_env_float accepts zero as valid value."""
        import importlib
        import deepr.core.constants as constants
        importlib.reload(constants)
        
        with patch.dict(os.environ, {"TEST_ZERO_VAR": "0.0"}):
            result = constants._get_env_float("TEST_ZERO_VAR", 3.14)
            assert result == 0.0


class TestInvalidConfigErrorDetails:
    """Test that InvalidConfigError contains proper details."""
    
    def test_error_contains_config_key(self):
        """Test InvalidConfigError contains the config key in details."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_COST_BUFFER_SIZE": "invalid"}):
            importlib.reload(constants)
            with pytest.raises(InvalidConfigError) as exc_info:
                constants.load_config()
            
            error = exc_info.value
            assert error.details["config_key"] == "DEEPR_COST_BUFFER_SIZE"
    
    def test_error_contains_invalid_value(self):
        """Test InvalidConfigError contains the invalid value in details."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_COST_BUFFER_SIZE": "bad_value"}):
            importlib.reload(constants)
            with pytest.raises(InvalidConfigError) as exc_info:
                constants.load_config()
            
            error = exc_info.value
            assert error.details["value"] == "bad_value"
    
    def test_error_has_correct_error_code(self):
        """Test InvalidConfigError has INVALID_CONFIG error code."""
        import importlib
        import deepr.core.constants as constants
        
        with patch.dict(os.environ, {"DEEPR_COST_BUFFER_SIZE": "invalid"}):
            importlib.reload(constants)
            with pytest.raises(InvalidConfigError) as exc_info:
                constants.load_config()
            
            error = exc_info.value
            assert error.error_code == "INVALID_CONFIG"
