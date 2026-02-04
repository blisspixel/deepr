"""Central configuration constants for Deepr.

This module defines all configurable thresholds and settings used throughout
the Deepr codebase. Constants can be overridden via environment variables
using the DEEPR_* prefix convention.

Usage:
    from deepr.core.constants import (
        CONFIDENCE_THRESHOLD,
        CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        load_config
    )
    
    # Load config with environment overrides
    load_config()
    
    # Use constants
    if confidence >= CONFIDENCE_THRESHOLD:
        ...

Environment Variables:
    DEEPR_CONFIDENCE_THRESHOLD - Confidence threshold (default: 0.7)
    DEEPR_HEALTH_DECAY_FACTOR - Health decay factor (default: 0.95)
    DEEPR_CIRCUIT_BREAKER_FAILURE_THRESHOLD - Failures before circuit opens (default: 5)
    DEEPR_CIRCUIT_BREAKER_RECOVERY_TIMEOUT - Seconds before recovery attempt (default: 60)
    DEEPR_COST_BUFFER_SIZE - Cost entries before flush (default: 10)
    DEEPR_COST_FLUSH_INTERVAL - Seconds between flushes (default: 30)
    DEEPR_ROLLING_WINDOW_SIZE - Provider router window size (default: 20)
    DEEPR_MIN_SUCCESS_RATE - Minimum provider success rate (default: 0.8)
    DEEPR_MAX_STORED_FALLBACK_EVENTS - Max fallback events to store (default: 100)

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
"""

import os
from typing import Any

from deepr.core.errors import InvalidConfigError

# =============================================================================
# Research Quality Metrics
# =============================================================================

# Entropy threshold for stopping (stop when entropy drops below this)
ENTROPY_THRESHOLD: float = 0.15

# Minimum information gain required per phase
MIN_INFORMATION_GAIN: float = 0.10

# Window size for entropy calculation (recent findings)
ENTROPY_WINDOW_SIZE: int = 3

# Minimum iterations before stopping is allowed
MIN_ITERATIONS_BEFORE_STOP: int = 2

# =============================================================================
# Token Budget Settings
# =============================================================================

# Default token budget for research sessions
TOKEN_BUDGET_DEFAULT: int = 50000

# Reserve percentage for synthesis phase
TOKEN_BUDGET_SYNTHESIS_RESERVE_PCT: float = 0.20

# Maximum context tokens per phase
MAX_CONTEXT_TOKENS: int = 8000

# =============================================================================
# Task Durability Settings
# =============================================================================

# Checkpoint interval in seconds
TASK_CHECKPOINT_INTERVAL: int = 30

# Maximum concurrent tasks
MAX_CONCURRENT_TASKS: int = 5

# Default task timeout in seconds
TASK_DEFAULT_TIMEOUT: int = 600

# =============================================================================
# Security Settings
# =============================================================================

# Maximum age for signed instructions (seconds)
INSTRUCTION_MAX_AGE: int = 300

# Default research mode (standard, read_only, unrestricted)
DEFAULT_RESEARCH_MODE: str = "standard"

# =============================================================================
# Security Thresholds
# =============================================================================

# Confidence threshold for accepting results (0.0 to 1.0)
CONFIDENCE_THRESHOLD: float = 0.7

# Health decay factor for provider health scoring (0.0 to 1.0)
HEALTH_DECAY_FACTOR: float = 0.95

# =============================================================================
# Circuit Breaker Settings
# =============================================================================

# Number of consecutive failures before circuit opens
CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5

# Seconds to wait before attempting recovery (OPEN -> HALF_OPEN)
CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 60

# =============================================================================
# Cost Tracking Settings
# =============================================================================

# Number of cost entries to buffer before flushing to disk
COST_BUFFER_SIZE: int = 10

# Maximum seconds between cost buffer flushes
COST_FLUSH_INTERVAL: int = 30

# =============================================================================
# Rate Limiting (requests per minute)
# =============================================================================

# Rate limit for job submission endpoints
RATE_LIMIT_JOB_SUBMIT: str = "10 per minute"

# Rate limit for job status endpoints
RATE_LIMIT_JOB_STATUS: str = "60 per minute"

# Rate limit for listing endpoints
RATE_LIMIT_LISTING: str = "30 per minute"

# =============================================================================
# Provider Router Settings
# =============================================================================

# Size of rolling window for provider metrics
ROLLING_WINDOW_SIZE: int = 20

# Minimum success rate for provider to be considered healthy (0.0 to 1.0)
MIN_SUCCESS_RATE: float = 0.8

# Maximum number of fallback events to store
MAX_STORED_FALLBACK_EVENTS: int = 100


# =============================================================================
# Helper Functions for Environment Variable Loading
# =============================================================================

def _get_env_int(key: str, default: int) -> int:
    """Get integer from environment variable with validation.
    
    Args:
        key: Environment variable name
        default: Default value if not set
        
    Returns:
        Integer value from environment or default
        
    Raises:
        InvalidConfigError: If value is not a valid non-negative integer
    """
    value = os.getenv(key)
    if value is None:
        return default
    
    try:
        result = int(value)
        if result < 0:
            raise InvalidConfigError(key, value, "must be non-negative")
        return result
    except ValueError:
        raise InvalidConfigError(key, value, "must be an integer")


def _get_env_float(key: str, default: float) -> float:
    """Get float from environment variable with validation.
    
    Args:
        key: Environment variable name
        default: Default value if not set
        
    Returns:
        Float value from environment or default
        
    Raises:
        InvalidConfigError: If value is not a valid non-negative number
    """
    value = os.getenv(key)
    if value is None:
        return default
    
    try:
        result = float(value)
        if result < 0:
            raise InvalidConfigError(key, value, "must be non-negative")
        return result
    except ValueError:
        raise InvalidConfigError(key, value, "must be a number")


def _get_env_str(key: str, default: str) -> str:
    """Get string from environment variable.
    
    Args:
        key: Environment variable name
        default: Default value if not set
        
    Returns:
        String value from environment or default
    """
    return os.getenv(key, default)


def load_config() -> None:
    """Load configuration with environment variable overrides.

    Loads all configuration values from environment variables using the
    DEEPR_* prefix convention. Invalid values raise InvalidConfigError.

    Environment variables:
        DEEPR_CONFIDENCE_THRESHOLD
        DEEPR_HEALTH_DECAY_FACTOR
        DEEPR_CIRCUIT_BREAKER_FAILURE_THRESHOLD
        DEEPR_CIRCUIT_BREAKER_RECOVERY_TIMEOUT
        DEEPR_COST_BUFFER_SIZE
        DEEPR_COST_FLUSH_INTERVAL
        DEEPR_ROLLING_WINDOW_SIZE
        DEEPR_MIN_SUCCESS_RATE
        DEEPR_MAX_STORED_FALLBACK_EVENTS
        DEEPR_RATE_LIMIT_JOB_SUBMIT
        DEEPR_RATE_LIMIT_JOB_STATUS
        DEEPR_RATE_LIMIT_LISTING
        DEEPR_ENTROPY_THRESHOLD
        DEEPR_MIN_INFORMATION_GAIN
        DEEPR_ENTROPY_WINDOW_SIZE
        DEEPR_MIN_ITERATIONS_BEFORE_STOP
        DEEPR_TOKEN_BUDGET_DEFAULT
        DEEPR_TOKEN_BUDGET_SYNTHESIS_RESERVE_PCT
        DEEPR_MAX_CONTEXT_TOKENS
        DEEPR_TASK_CHECKPOINT_INTERVAL
        DEEPR_MAX_CONCURRENT_TASKS
        DEEPR_TASK_DEFAULT_TIMEOUT
        DEEPR_INSTRUCTION_MAX_AGE
        DEEPR_DEFAULT_RESEARCH_MODE

    Raises:
        InvalidConfigError: If any environment variable has an invalid value

    Example:
        >>> import os
        >>> os.environ["DEEPR_CONFIDENCE_THRESHOLD"] = "0.9"
        >>> load_config()
        >>> CONFIDENCE_THRESHOLD
        0.9
    """
    global CONFIDENCE_THRESHOLD, HEALTH_DECAY_FACTOR
    global CIRCUIT_BREAKER_FAILURE_THRESHOLD, CIRCUIT_BREAKER_RECOVERY_TIMEOUT
    global COST_BUFFER_SIZE, COST_FLUSH_INTERVAL
    global ROLLING_WINDOW_SIZE, MIN_SUCCESS_RATE, MAX_STORED_FALLBACK_EVENTS
    global RATE_LIMIT_JOB_SUBMIT, RATE_LIMIT_JOB_STATUS, RATE_LIMIT_LISTING
    global ENTROPY_THRESHOLD, MIN_INFORMATION_GAIN, ENTROPY_WINDOW_SIZE
    global MIN_ITERATIONS_BEFORE_STOP
    global TOKEN_BUDGET_DEFAULT, TOKEN_BUDGET_SYNTHESIS_RESERVE_PCT, MAX_CONTEXT_TOKENS
    global TASK_CHECKPOINT_INTERVAL, MAX_CONCURRENT_TASKS, TASK_DEFAULT_TIMEOUT
    global INSTRUCTION_MAX_AGE, DEFAULT_RESEARCH_MODE

    # Research quality metrics
    ENTROPY_THRESHOLD = _get_env_float("DEEPR_ENTROPY_THRESHOLD", 0.15)
    MIN_INFORMATION_GAIN = _get_env_float("DEEPR_MIN_INFORMATION_GAIN", 0.10)
    ENTROPY_WINDOW_SIZE = _get_env_int("DEEPR_ENTROPY_WINDOW_SIZE", 3)
    MIN_ITERATIONS_BEFORE_STOP = _get_env_int("DEEPR_MIN_ITERATIONS_BEFORE_STOP", 2)

    # Token budget settings
    TOKEN_BUDGET_DEFAULT = _get_env_int("DEEPR_TOKEN_BUDGET_DEFAULT", 50000)
    TOKEN_BUDGET_SYNTHESIS_RESERVE_PCT = _get_env_float(
        "DEEPR_TOKEN_BUDGET_SYNTHESIS_RESERVE_PCT", 0.20
    )
    MAX_CONTEXT_TOKENS = _get_env_int("DEEPR_MAX_CONTEXT_TOKENS", 8000)

    # Task durability settings
    TASK_CHECKPOINT_INTERVAL = _get_env_int("DEEPR_TASK_CHECKPOINT_INTERVAL", 30)
    MAX_CONCURRENT_TASKS = _get_env_int("DEEPR_MAX_CONCURRENT_TASKS", 5)
    TASK_DEFAULT_TIMEOUT = _get_env_int("DEEPR_TASK_DEFAULT_TIMEOUT", 600)

    # Security settings
    INSTRUCTION_MAX_AGE = _get_env_int("DEEPR_INSTRUCTION_MAX_AGE", 300)
    DEFAULT_RESEARCH_MODE = _get_env_str("DEEPR_DEFAULT_RESEARCH_MODE", "standard")

    # Security thresholds
    CONFIDENCE_THRESHOLD = _get_env_float("DEEPR_CONFIDENCE_THRESHOLD", 0.7)
    HEALTH_DECAY_FACTOR = _get_env_float("DEEPR_HEALTH_DECAY_FACTOR", 0.95)

    # Circuit breaker settings
    CIRCUIT_BREAKER_FAILURE_THRESHOLD = _get_env_int(
        "DEEPR_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5
    )
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT = _get_env_int(
        "DEEPR_CIRCUIT_BREAKER_RECOVERY_TIMEOUT", 60
    )

    # Cost tracking settings
    COST_BUFFER_SIZE = _get_env_int("DEEPR_COST_BUFFER_SIZE", 10)
    COST_FLUSH_INTERVAL = _get_env_int("DEEPR_COST_FLUSH_INTERVAL", 30)

    # Provider router settings
    ROLLING_WINDOW_SIZE = _get_env_int("DEEPR_ROLLING_WINDOW_SIZE", 20)
    MIN_SUCCESS_RATE = _get_env_float("DEEPR_MIN_SUCCESS_RATE", 0.8)
    MAX_STORED_FALLBACK_EVENTS = _get_env_int("DEEPR_MAX_STORED_FALLBACK_EVENTS", 100)

    # Rate limiting (string values)
    RATE_LIMIT_JOB_SUBMIT = _get_env_str("DEEPR_RATE_LIMIT_JOB_SUBMIT", "10 per minute")
    RATE_LIMIT_JOB_STATUS = _get_env_str("DEEPR_RATE_LIMIT_JOB_STATUS", "60 per minute")
    RATE_LIMIT_LISTING = _get_env_str("DEEPR_RATE_LIMIT_LISTING", "30 per minute")
