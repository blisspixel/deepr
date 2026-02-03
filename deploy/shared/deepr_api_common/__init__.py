"""Deepr API Common Library - Cloud-agnostic validation and utilities."""

from .validation import (
    MAX_PROMPT_LENGTH,
    MAX_METADATA_SIZE,
    VALID_MODELS,
    VALID_STATUSES,
    UUID_PATTERN,
    validate_job_id,
    sanitize_string,
    validate_prompt,
    validate_model,
    validate_priority,
    validate_enable_web_search,
    validate_metadata,
    validate_status_filter,
    validate_limit,
    validate_job_request,
)
from .security import (
    SECURITY_HEADERS,
    CORS_HEADERS,
    get_all_response_headers,
    validate_api_key_from_headers,
)
from .models import (
    API_VERSION,
    DEFAULT_TTL_DAYS,
    generate_job_id,
    get_current_timestamp,
    calculate_ttl,
    estimate_cost,
    create_job_document,
    create_queue_message,
    format_job_response,
    health_response,
)
from .responses import (
    error_response,
    success_response,
    job_submitted_response,
)

__version__ = '1.0.0'
__all__ = [
    # validation
    'MAX_PROMPT_LENGTH',
    'MAX_METADATA_SIZE',
    'VALID_MODELS',
    'VALID_STATUSES',
    'UUID_PATTERN',
    'validate_job_id',
    'sanitize_string',
    'validate_prompt',
    'validate_model',
    'validate_priority',
    'validate_enable_web_search',
    'validate_metadata',
    'validate_status_filter',
    'validate_limit',
    'validate_job_request',
    # security
    'SECURITY_HEADERS',
    'CORS_HEADERS',
    'get_all_response_headers',
    'validate_api_key_from_headers',
    # models
    'API_VERSION',
    'DEFAULT_TTL_DAYS',
    'generate_job_id',
    'get_current_timestamp',
    'calculate_ttl',
    'estimate_cost',
    'create_job_document',
    'create_queue_message',
    'format_job_response',
    'health_response',
    # responses
    'error_response',
    'success_response',
    'job_submitted_response',
]
