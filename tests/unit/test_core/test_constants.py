"""Tests for core configuration constants and env loading."""

import os

import pytest

from deepr.core.constants import (
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
    CONFIDENCE_THRESHOLD,
    COST_BUFFER_SIZE,
    COST_FLUSH_INTERVAL,
    ENTROPY_THRESHOLD,
    HEALTH_DECAY_FACTOR,
    MAX_CONCURRENT_TASKS,
    MAX_CONTEXT_TOKENS,
    MAX_STORED_FALLBACK_EVENTS,
    MIN_INFORMATION_GAIN,
    MIN_ITERATIONS_BEFORE_STOP,
    MIN_SUCCESS_RATE,
    ROLLING_WINDOW_SIZE,
    TOKEN_BUDGET_DEFAULT,
    _get_env_float,
    _get_env_int,
    _get_env_str,
    load_config,
)
from deepr.core.errors import InvalidConfigError


class TestDefaultConstants:
    """Test that default constant values exist and have correct types."""

    def test_entropy_threshold_type_and_value(self):
        assert isinstance(ENTROPY_THRESHOLD, float)
        assert ENTROPY_THRESHOLD == 0.15

    def test_confidence_threshold_type_and_value(self):
        assert isinstance(CONFIDENCE_THRESHOLD, float)
        assert CONFIDENCE_THRESHOLD == 0.7

    def test_health_decay_factor_type_and_value(self):
        assert isinstance(HEALTH_DECAY_FACTOR, float)
        assert HEALTH_DECAY_FACTOR == 0.95

    def test_circuit_breaker_failure_threshold(self):
        assert isinstance(CIRCUIT_BREAKER_FAILURE_THRESHOLD, int)
        assert CIRCUIT_BREAKER_FAILURE_THRESHOLD == 5

    def test_circuit_breaker_recovery_timeout(self):
        assert isinstance(CIRCUIT_BREAKER_RECOVERY_TIMEOUT, int)
        assert CIRCUIT_BREAKER_RECOVERY_TIMEOUT == 60

    def test_cost_buffer_size(self):
        assert isinstance(COST_BUFFER_SIZE, int)
        assert COST_BUFFER_SIZE == 10

    def test_cost_flush_interval(self):
        assert isinstance(COST_FLUSH_INTERVAL, int)
        assert COST_FLUSH_INTERVAL == 30

    def test_rolling_window_size(self):
        assert isinstance(ROLLING_WINDOW_SIZE, int)
        assert ROLLING_WINDOW_SIZE == 20

    def test_min_success_rate(self):
        assert isinstance(MIN_SUCCESS_RATE, float)
        assert MIN_SUCCESS_RATE == 0.8

    def test_max_stored_fallback_events(self):
        assert isinstance(MAX_STORED_FALLBACK_EVENTS, int)
        assert MAX_STORED_FALLBACK_EVENTS == 100

    def test_token_budget_default(self):
        assert isinstance(TOKEN_BUDGET_DEFAULT, int)
        assert TOKEN_BUDGET_DEFAULT == 50000

    def test_min_information_gain(self):
        assert isinstance(MIN_INFORMATION_GAIN, float)
        assert MIN_INFORMATION_GAIN == 0.10

    def test_min_iterations_before_stop(self):
        assert isinstance(MIN_ITERATIONS_BEFORE_STOP, int)
        assert MIN_ITERATIONS_BEFORE_STOP == 2

    def test_max_context_tokens(self):
        assert isinstance(MAX_CONTEXT_TOKENS, int)
        assert MAX_CONTEXT_TOKENS == 8000

    def test_max_concurrent_tasks(self):
        assert isinstance(MAX_CONCURRENT_TASKS, int)
        assert MAX_CONCURRENT_TASKS == 5


class TestGetEnvInt:
    """Tests for _get_env_int helper."""

    def test_returns_default_when_not_set(self):
        assert _get_env_int("DEEPR_TEST_NONEXISTENT_INT", 42) == 42

    def test_returns_parsed_value(self, monkeypatch):
        monkeypatch.setenv("DEEPR_TEST_INT", "99")
        assert _get_env_int("DEEPR_TEST_INT", 0) == 99

    def test_negative_value_raises(self, monkeypatch):
        monkeypatch.setenv("DEEPR_TEST_INT_NEG", "-5")
        with pytest.raises(InvalidConfigError):
            _get_env_int("DEEPR_TEST_INT_NEG", 0)

    def test_non_integer_raises(self, monkeypatch):
        monkeypatch.setenv("DEEPR_TEST_INT_BAD", "abc")
        with pytest.raises(InvalidConfigError):
            _get_env_int("DEEPR_TEST_INT_BAD", 0)

    def test_float_string_raises(self, monkeypatch):
        monkeypatch.setenv("DEEPR_TEST_INT_FLOAT", "3.14")
        with pytest.raises(InvalidConfigError):
            _get_env_int("DEEPR_TEST_INT_FLOAT", 0)


class TestGetEnvFloat:
    """Tests for _get_env_float helper."""

    def test_returns_default_when_not_set(self):
        assert _get_env_float("DEEPR_TEST_NONEXISTENT_FLOAT", 1.5) == 1.5

    def test_returns_parsed_value(self, monkeypatch):
        monkeypatch.setenv("DEEPR_TEST_FLOAT", "3.14")
        assert _get_env_float("DEEPR_TEST_FLOAT", 0.0) == pytest.approx(3.14)

    def test_negative_value_raises(self, monkeypatch):
        monkeypatch.setenv("DEEPR_TEST_FLOAT_NEG", "-0.5")
        with pytest.raises(InvalidConfigError):
            _get_env_float("DEEPR_TEST_FLOAT_NEG", 0.0)

    def test_non_float_raises(self, monkeypatch):
        monkeypatch.setenv("DEEPR_TEST_FLOAT_BAD", "xyz")
        with pytest.raises(InvalidConfigError):
            _get_env_float("DEEPR_TEST_FLOAT_BAD", 0.0)


class TestGetEnvStr:
    """Tests for _get_env_str helper."""

    def test_returns_default_when_not_set(self):
        assert _get_env_str("DEEPR_TEST_NONEXISTENT_STR", "default") == "default"

    def test_returns_env_value(self, monkeypatch):
        monkeypatch.setenv("DEEPR_TEST_STR", "custom")
        assert _get_env_str("DEEPR_TEST_STR", "default") == "custom"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_applies_env_override(self, monkeypatch):
        monkeypatch.setenv("DEEPR_CONFIDENCE_THRESHOLD", "0.9")
        load_config()
        import deepr.core.constants as c

        assert c.CONFIDENCE_THRESHOLD == pytest.approx(0.9)
        # Restore default
        monkeypatch.delenv("DEEPR_CONFIDENCE_THRESHOLD")
        load_config()

    def test_load_config_invalid_env_raises(self, monkeypatch):
        monkeypatch.setenv("DEEPR_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "not_a_number")
        with pytest.raises(InvalidConfigError):
            load_config()
        monkeypatch.delenv("DEEPR_CIRCUIT_BREAKER_FAILURE_THRESHOLD")
        load_config()


class TestInvalidConfigErrorChaining:
    """Test that InvalidConfigError chains the original ValueError."""

    def test_from_e_chaining_int(self, monkeypatch):
        monkeypatch.setenv("DEEPR_TEST_CHAIN_INT", "bad")
        with pytest.raises(InvalidConfigError) as exc_info:
            _get_env_int("DEEPR_TEST_CHAIN_INT", 0)
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)

    def test_from_e_chaining_float(self, monkeypatch):
        monkeypatch.setenv("DEEPR_TEST_CHAIN_FLOAT", "bad")
        with pytest.raises(InvalidConfigError) as exc_info:
            _get_env_float("DEEPR_TEST_CHAIN_FLOAT", 0.0)
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)
