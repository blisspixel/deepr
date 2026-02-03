"""Input validation utilities - pure Python, no cloud dependencies."""

import json
import re
from typing import Any, Dict, Optional, Tuple

# Constants
MAX_PROMPT_LENGTH = 10000
MAX_METADATA_SIZE = 4096
VALID_MODELS = [
    'o4-mini-deep-research',
    'o3-deep-research',
    'gemini-2.0-flash-thinking-exp',
    'gemini-2.5-pro-exp-03-25',
    'grok-3-mini-fast',
    'grok-3-fast',
]
VALID_STATUSES = ['queued', 'running', 'completed', 'failed', 'cancelled']
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
)


def validate_job_id(job_id: str) -> bool:
    """Validate job ID is a valid UUID."""
    if not job_id:
        return False
    return bool(UUID_PATTERN.match(job_id.lower()))


def sanitize_string(value: str, max_length: int = 1000) -> str:
    """Sanitize string input by truncating and stripping whitespace."""
    if not isinstance(value, str):
        return ''
    return value[:max_length].strip()


def validate_prompt(prompt: Any) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate prompt field.

    Returns:
        Tuple of (valid, sanitized_prompt, error_message)
    """
    if not prompt:
        return False, None, 'Prompt required'
    if not isinstance(prompt, str):
        return False, None, 'Prompt must be a string'
    if len(prompt) > MAX_PROMPT_LENGTH:
        return False, None, f'Prompt exceeds maximum length of {MAX_PROMPT_LENGTH}'
    return True, sanitize_string(prompt, MAX_PROMPT_LENGTH), None


def validate_model(model: Optional[str]) -> Tuple[bool, str, Optional[str]]:
    """
    Validate model field.

    Returns:
        Tuple of (valid, model_or_default, error_message)
    """
    if model is None:
        return True, 'o4-mini-deep-research', None
    if model not in VALID_MODELS:
        return False, '', f'Invalid model. Valid options: {", ".join(VALID_MODELS)}'
    return True, model, None


def validate_priority(priority: Any) -> Tuple[bool, int, Optional[str]]:
    """
    Validate priority field.

    Returns:
        Tuple of (valid, priority_or_default, error_message)
    """
    if priority is None:
        return True, 3, None
    if not isinstance(priority, int) or priority < 1 or priority > 5:
        return False, 0, 'Priority must be an integer between 1 and 5'
    return True, priority, None


def validate_enable_web_search(value: Any) -> Tuple[bool, bool, Optional[str]]:
    """
    Validate enable_web_search field.

    Returns:
        Tuple of (valid, value_or_default, error_message)
    """
    if value is None:
        return True, True, None
    if not isinstance(value, bool):
        return False, False, 'enable_web_search must be a boolean'
    return True, value, None


def validate_metadata(metadata: Any) -> Tuple[bool, Dict, Optional[str]]:
    """
    Validate metadata field.

    Returns:
        Tuple of (valid, metadata_or_default, error_message)
    """
    if metadata is None:
        return True, {}, None
    if not isinstance(metadata, dict):
        return False, {}, 'Metadata must be an object'
    if len(json.dumps(metadata)) > MAX_METADATA_SIZE:
        return False, {}, f'Metadata exceeds maximum size of {MAX_METADATA_SIZE} bytes'
    return True, metadata, None


def validate_status_filter(status: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate status filter parameter.

    Returns:
        Tuple of (valid, sanitized_status, error_message)
    """
    if not status:
        return True, None, None
    status = sanitize_string(status, 20)
    if status not in VALID_STATUSES:
        return False, None, f'Invalid status. Valid options: {", ".join(VALID_STATUSES)}'
    return True, status, None


def validate_limit(limit_str: Optional[str], max_limit: int = 1000) -> Tuple[bool, int, Optional[str]]:
    """
    Validate limit parameter.

    Returns:
        Tuple of (valid, limit_value, error_message)
    """
    if not limit_str:
        return True, 100, None
    try:
        limit = min(int(limit_str), max_limit)
        if limit < 1:
            limit = 1
        return True, limit, None
    except ValueError:
        return False, 0, 'Invalid limit parameter'


def validate_job_request(body: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Validate complete job submission request.

    Args:
        body: Request body dictionary

    Returns:
        Tuple of (valid, validated_data, error_message)
    """
    # Validate prompt
    valid, prompt, error = validate_prompt(body.get('prompt'))
    if not valid:
        return False, {}, error

    # Validate model
    valid, model, error = validate_model(body.get('model'))
    if not valid:
        return False, {}, error

    # Validate priority
    valid, priority, error = validate_priority(body.get('priority'))
    if not valid:
        return False, {}, error

    # Validate web search flag
    valid, enable_web_search, error = validate_enable_web_search(body.get('enable_web_search'))
    if not valid:
        return False, {}, error

    # Validate metadata
    valid, metadata, error = validate_metadata(body.get('metadata'))
    if not valid:
        return False, {}, error

    return True, {
        'prompt': prompt,
        'model': model,
        'priority': priority,
        'enable_web_search': enable_web_search,
        'metadata': metadata,
    }, None
