"""Security utilities - API key validation, headers."""

from typing import Dict, Optional

# Security headers for all responses
SECURITY_HEADERS: Dict[str, str] = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
    'Cache-Control': 'no-store, no-cache, must-revalidate',
    'Pragma': 'no-cache',
}

# CORS headers for cross-origin requests
CORS_HEADERS: Dict[str, str] = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Api-Key',
}


def get_all_response_headers() -> Dict[str, str]:
    """Get combined security + CORS + content-type headers."""
    return {
        **SECURITY_HEADERS,
        **CORS_HEADERS,
        'Content-Type': 'application/json',
    }


def validate_api_key_from_headers(
    auth_header: Optional[str],
    api_key_header: Optional[str],
    expected_key: str
) -> bool:
    """
    Validate API key from request headers.

    Checks both Authorization Bearer token and X-Api-Key header.

    Args:
        auth_header: Value of Authorization header (e.g., "Bearer sk-xxx")
        api_key_header: Value of X-Api-Key header
        expected_key: Expected API key value

    Returns:
        True if valid, False otherwise
    """
    if not expected_key:
        return True  # No key configured, allow all requests

    # Check Authorization Bearer token
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header[7:]
        if token == expected_key:
            return True

    # Check X-Api-Key header
    if api_key_header and api_key_header == expected_key:
        return True

    return False
