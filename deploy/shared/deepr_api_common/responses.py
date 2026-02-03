"""Response formatting utilities."""

from typing import Any, Dict


def error_response(message: str) -> Dict[str, Any]:
    """
    Create standard error response body.

    Args:
        message: Error message

    Returns:
        Error response dict
    """
    return {'error': message}


def success_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create standard success response body.

    Args:
        data: Response data

    Returns:
        Success response dict (pass-through)
    """
    return data


def job_submitted_response(
    job_id: str,
    prompt: str,
    model: str,
    estimated_cost: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create job submission response.

    Args:
        job_id: Created job ID
        prompt: Job prompt
        model: Model name
        estimated_cost: Cost estimate dict

    Returns:
        Job submission response dict
    """
    return {
        'job': {
            'id': job_id,
            'prompt': prompt,
            'model': model,
            'status': 'queued',
        },
        'estimated_cost': estimated_cost,
    }
