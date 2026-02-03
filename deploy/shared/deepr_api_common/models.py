"""Shared data models and cost estimation."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

API_VERSION = '2.6.0'
DEFAULT_TTL_DAYS = 90


def generate_job_id() -> str:
    """Generate a new job ID (UUID v4)."""
    return str(uuid.uuid4())


def get_current_timestamp() -> str:
    """Get current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def calculate_ttl(days: int = DEFAULT_TTL_DAYS) -> int:
    """
    Calculate TTL as Unix timestamp N days from now.

    Args:
        days: Number of days until expiration (default 90)

    Returns:
        Unix timestamp for expiration
    """
    return int(datetime.now(timezone.utc).timestamp()) + (days * 24 * 60 * 60)


def estimate_cost(model: str) -> Dict[str, Any]:
    """
    Estimate job cost based on model.

    Args:
        model: Model name

    Returns:
        Dict with min_cost, max_cost, estimated_cost, currency
    """
    # Mini models are cheaper
    avg_cost = 0.5 if 'mini' in model.lower() else 5.0
    return {
        'min_cost': avg_cost * 0.5,
        'max_cost': avg_cost * 2.0,
        'estimated_cost': avg_cost,
        'currency': 'USD',
    }


def create_job_document(
    job_id: str,
    prompt: str,
    model: str,
    priority: int,
    enable_web_search: bool,
    metadata: Dict[str, Any],
    user_id: str = 'anonymous',
    include_ttl: bool = True,
) -> Dict[str, Any]:
    """
    Create a standardized job document for storage.

    Args:
        job_id: Unique job identifier
        prompt: Research prompt
        model: Model name
        priority: Job priority (1-5)
        enable_web_search: Whether to enable web search
        metadata: User metadata
        user_id: User identifier
        include_ttl: Whether to include TTL field

    Returns:
        Job document dict ready for storage
    """
    doc = {
        'job_id': job_id,
        'prompt': prompt,
        'model': model,
        'priority': priority,
        'enable_web_search': enable_web_search,
        'status': 'queued',
        'submitted_at': get_current_timestamp(),
        'metadata': metadata,
        'user_id': user_id,
    }

    if include_ttl:
        doc['ttl'] = calculate_ttl()

    return doc


def create_queue_message(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create standardized queue message from job document.

    Args:
        job: Job document dict

    Returns:
        Queue message dict
    """
    return {
        'id': job['job_id'],
        'prompt': job['prompt'],
        'model': job['model'],
        'priority': job['priority'],
        'enable_web_search': job['enable_web_search'],
        'submitted_at': job['submitted_at'],
        'metadata': job['metadata'],
    }


def format_job_response(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format job for API response (convert job_id to id).

    Args:
        job: Job document from storage

    Returns:
        Job dict with 'id' instead of 'job_id'
    """
    result = dict(job)
    if 'job_id' in result:
        result['id'] = result.pop('job_id')
    return result


def health_response() -> Dict[str, Any]:
    """
    Create standard health check response.

    Returns:
        Health check response dict
    """
    return {
        'status': 'healthy',
        'service': 'deepr-api',
        'version': API_VERSION,
    }
