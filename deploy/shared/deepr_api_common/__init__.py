"""Deepr API Common Library - Cloud-agnostic validation and utilities."""

from .models import (
    API_VERSION,
    DEFAULT_TTL_DAYS,
    calculate_ttl,
    create_job_document,
    create_queue_message,
    estimate_cost,
    format_job_response,
    generate_job_id,
    get_current_timestamp,
    health_response,
)
from .responses import (
    error_response,
    job_submitted_response,
    success_response,
)
from .security import (
    CORS_HEADERS,
    SECURITY_HEADERS,
    get_all_response_headers,
    validate_api_key_from_headers,
)
from .validation import (
    MAX_METADATA_SIZE,
    MAX_PROMPT_LENGTH,
    UUID_PATTERN,
    VALID_MODELS,
    VALID_STATUSES,
    sanitize_string,
    validate_enable_web_search,
    validate_job_id,
    validate_job_request,
    validate_limit,
    validate_metadata,
    validate_model,
    validate_priority,
    validate_prompt,
    validate_status_filter,
)

__version__ = '1.0.0'
__all__ = [
    # models
    'API_VERSION',
    'CORS_HEADERS',
    'DEFAULT_TTL_DAYS',
    'MAX_METADATA_SIZE',
    # validation
    'MAX_PROMPT_LENGTH',
    # security
    'SECURITY_HEADERS',
    'UUID_PATTERN',
    'VALID_MODELS',
    'VALID_STATUSES',
    'calculate_ttl',
    'create_job_document',
    'create_queue_message',
    # responses
    'error_response',
    'estimate_cost',
    'format_job_response',
    'generate_job_id',
    'get_all_response_headers',
    'get_current_timestamp',
    'health_response',
    'job_submitted_response',
    'sanitize_string',
    'success_response',
    'validate_api_key_from_headers',
    'validate_enable_web_search',
    'validate_job_id',
    'validate_job_request',
    'validate_limit',
    'validate_metadata',
    'validate_model',
    'validate_priority',
    'validate_prompt',
    'validate_status_filter',
]
