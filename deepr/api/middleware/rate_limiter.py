# deepr/api/middleware/rate_limiter.py
"""Rate limiting middleware for Flask API.

This module provides rate limiting functionality using Flask-Limiter
to protect the API from abuse and denial-of-service attacks.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging

from deepr.core.constants import (
    RATE_LIMIT_JOB_SUBMIT,
    RATE_LIMIT_JOB_STATUS,
    RATE_LIMIT_LISTING,
)

logger = logging.getLogger(__name__)


def create_limiter(app: Flask) -> Limiter:
    """Create and configure rate limiter for Flask app.
    
    Creates a Flask-Limiter instance configured with:
    - IP-based client identification for unauthenticated requests
    - Default limits of 200/day and 50/hour
    - In-memory storage (use Redis in production)
    - Moving window strategy to prevent burst abuse at window boundaries
    
    Args:
        app: Flask application instance
        
    Returns:
        Configured Limiter instance
        
    Requirements:
        - 2.1: Enforce rate limits on all public endpoints
        - 2.4: Identify clients by IP address
        - 2.6: Use sliding window algorithm
    """
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",  # Use Redis in production
        strategy="moving-window"
    )
    
    @app.errorhandler(429)
    def ratelimit_handler(e):
        """Handle rate limit exceeded errors.
        
        Logs the rate limit event and returns a structured JSON response
        with the Retry-After header indicating when the client can retry.
        
        Requirements:
            - 2.2: Return HTTP 429 with Retry-After header
            - 2.5: Log rate limit events with client identifier and endpoint
        """
        logger.warning(
            f"Rate limit exceeded: {request.remote_addr} on {request.endpoint}"
        )
        return jsonify({
            "error": True,
            "error_code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests. Please try again later.",
            "retry_after": e.description
        }), 429, {"Retry-After": str(e.description)}
    
    return limiter


def limit_job_submit(limiter: Limiter):
    """Rate limit decorator for job submission endpoints.
    
    Applies the configured job submission rate limit (default: 10/min).
    
    Args:
        limiter: Configured Limiter instance
        
    Returns:
        Rate limit decorator
        
    Requirements:
        - 2.3: Support configurable limits per endpoint category
    """
    return limiter.limit(RATE_LIMIT_JOB_SUBMIT)


def limit_job_status(limiter: Limiter):
    """Rate limit decorator for job status endpoints.
    
    Applies the configured job status rate limit (default: 60/min).
    
    Args:
        limiter: Configured Limiter instance
        
    Returns:
        Rate limit decorator
        
    Requirements:
        - 2.3: Support configurable limits per endpoint category
    """
    return limiter.limit(RATE_LIMIT_JOB_STATUS)


def limit_listing(limiter: Limiter):
    """Rate limit decorator for listing endpoints.
    
    Applies the configured listing rate limit (default: 30/min).
    
    Args:
        limiter: Configured Limiter instance
        
    Returns:
        Rate limit decorator
        
    Requirements:
        - 2.3: Support configurable limits per endpoint category
    """
    return limiter.limit(RATE_LIMIT_LISTING)
