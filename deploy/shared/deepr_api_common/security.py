"""Security utilities - API key validation, headers."""

# Security headers for all responses
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
}

# CORS headers for cross-origin requests
CORS_HEADERS: dict[str, str] = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Api-Key",
}


def get_all_response_headers() -> dict[str, str]:
    """Get combined security + CORS + content-type headers."""
    return {
        **SECURITY_HEADERS,
        **CORS_HEADERS,
        "Content-Type": "application/json",
    }


def validate_api_key_from_headers(auth_header: str | None, api_key_header: str | None, expected_key: str) -> bool:
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

    import hmac as _hmac

    def _ct_eq(provided: str, expected: str) -> bool:
        """Constant-time comparison that tolerates non-ASCII bearer tokens.

        ``hmac.compare_digest`` raises ``TypeError`` when either operand
        is a ``str`` containing characters outside the ASCII range; treat
        that the same as a mismatch to avoid leaking into the generic
        500-handler path.
        """
        try:
            return _hmac.compare_digest(provided, expected)
        except TypeError:
            return False

    # Check Authorization Bearer token
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if _ct_eq(token, expected_key):
            return True

    # Check X-Api-Key header
    if api_key_header and _ct_eq(api_key_header, expected_key):
        return True

    return False
