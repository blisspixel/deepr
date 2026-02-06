"""Error handling middleware for Flask API.

This module provides centralized error handling for the Deepr API,
ensuring consistent error responses and secure logging practices.

Error Handling Strategy:
- DeeprError subclasses: Return structured JSON using to_dict() with appropriate HTTP status
- Unexpected exceptions: Log sanitized traceback, return generic error (no sensitive details)
- All logging uses sanitize_log_message to prevent credential leakage
"""

import logging
import traceback

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from deepr.core.errors import DeeprError
from deepr.utils.security import sanitize_log_message

logger = logging.getLogger(__name__)

# Map DeeprError error_codes to HTTP status codes
ERROR_CODE_TO_HTTP_STATUS = {
    # Provider errors
    "PROVIDER_TIMEOUT": 504,
    "PROVIDER_RATE_LIMIT": 429,
    "PROVIDER_AUTH": 401,
    "PROVIDER_UNAVAILABLE": 503,
    "PROVIDER_ERROR": 502,
    # Budget errors
    "BUDGET_EXCEEDED": 402,
    "DAILY_LIMIT": 402,
    "BUDGET_ERROR": 402,
    # Validation errors
    "INVALID_INPUT": 400,
    "VALIDATION_ERROR": 400,
    "SCHEMA_VALIDATION": 400,
    # Storage errors
    "FILE_NOT_FOUND": 404,
    "STORAGE_ERROR": 500,
    "STORAGE_PERMISSION": 403,
    # Configuration errors
    "CONFIG_ERROR": 500,
    "MISSING_CONFIG": 500,
    "INVALID_CONFIG": 500,
    # Generic
    "DEEPR_ERROR": 500,
}


def register_error_handlers(app: Flask) -> None:
    """Register centralized error handlers for Flask app.

    This function registers error handlers for:
    1. DeeprError and all subclasses - returns structured JSON response
    2. HTTPException - returns standard HTTP error response
    3. Generic Exception - returns sanitized generic error

    Args:
        app: Flask application instance
    """

    @app.errorhandler(DeeprError)
    def handle_deepr_error(error: DeeprError):
        """Handle all DeeprError subclasses with structured response.

        Logs the error with sanitized message and returns a structured
        JSON response using the error's to_dict() method.

        Args:
            error: DeeprError instance or subclass

        Returns:
            Tuple of (JSON response, HTTP status code)
        """
        # Log with sanitized message to prevent credential leakage
        sanitized_msg = sanitize_log_message(str(error))
        logger.error(f"DeeprError [{error.error_code}]: {sanitized_msg}")

        # Return structured response using to_dict()
        response = error.to_dict()

        # Map error code to HTTP status code
        status_code = ERROR_CODE_TO_HTTP_STATUS.get(error.error_code, 500)

        return jsonify(response), status_code

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        """Handle Werkzeug HTTP exceptions.

        Converts HTTP exceptions to structured JSON responses
        consistent with DeeprError format.

        Args:
            error: HTTPException instance

        Returns:
            Tuple of (JSON response, HTTP status code)
        """
        # Log with sanitized message
        sanitized_msg = sanitize_log_message(str(error.description))
        logger.warning(f"HTTPException [{error.code}]: {sanitized_msg}")

        return jsonify(
            {
                "error": True,
                "error_code": f"HTTP_{error.code}",
                "message": error.description or error.name,
                "details": {},
            }
        ), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        """Handle unexpected exceptions with generic response.

        Logs the full traceback (sanitized) for debugging but returns
        only a generic error message to the client to prevent
        information leakage.

        Args:
            error: Any unhandled exception

        Returns:
            Tuple of (JSON response, 500 status code)
        """
        # Log full traceback with sanitized content
        tb = traceback.format_exc()
        sanitized_tb = sanitize_log_message(tb)
        logger.error(f"Unexpected error: {sanitized_tb}")

        # Return generic error - no sensitive details exposed
        return jsonify(
            {
                "error": True,
                "error_code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "details": {},
            }
        ), 500
