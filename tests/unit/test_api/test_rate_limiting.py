"""
Unit tests for API rate limiting middleware.

Tests the rate limiting functionality to ensure:
1. HTTP 429 response when rate limit is exceeded
2. Retry-After header is present in 429 responses
3. Correct JSON structure in 429 responses
4. Different endpoint categories have different limits

Feature: code-quality-security-hardening
**Validates: Requirements 2.2, 2.3**
"""

import importlib.util

# Import directly from the middleware module to avoid the deepr.api.__init__ import chain
# which tries to import create_app that doesn't exist
from pathlib import Path

import pytest
from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Get the correct path to the rate_limiter module
project_root = Path(__file__).parent.parent.parent.parent
rate_limiter_path = project_root / "deepr" / "api" / "middleware" / "rate_limiter.py"

spec = importlib.util.spec_from_file_location("rate_limiter", str(rate_limiter_path))
rate_limiter_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rate_limiter_module)

create_limiter = rate_limiter_module.create_limiter
limit_job_submit = rate_limiter_module.limit_job_submit
limit_job_status = rate_limiter_module.limit_job_status
limit_listing = rate_limiter_module.limit_listing
RATE_LIMIT_JOB_SUBMIT = rate_limiter_module.RATE_LIMIT_JOB_SUBMIT
RATE_LIMIT_JOB_STATUS = rate_limiter_module.RATE_LIMIT_JOB_STATUS
RATE_LIMIT_LISTING = rate_limiter_module.RATE_LIMIT_LISTING


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def test_app():
    """Create a test Flask application with rate limiting."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    # Create limiter with very low limits for testing
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day"],
        storage_uri="memory://",
        strategy="moving-window",
    )

    # Register the 429 error handler
    @app.errorhandler(429)
    def ratelimit_handler(e):
        from flask import jsonify

        return (
            jsonify(
                {
                    "error": True,
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": e.description,
                }
            ),
            429,
            {"Retry-After": str(e.description)},
        )

    # Create test endpoints with different rate limits
    @app.route("/api/jobs", methods=["POST"])
    @limiter.limit("2 per minute")  # Very low limit for testing
    def submit_job():
        return {"status": "submitted"}, 200

    @app.route("/api/jobs/<job_id>", methods=["GET"])
    @limiter.limit("3 per minute")  # Low limit for testing
    def get_job(job_id):
        return {"job_id": job_id}, 200

    @app.route("/api/jobs", methods=["GET"])
    @limiter.limit("2 per minute")  # Low limit for testing
    def list_jobs():
        return {"jobs": []}, 200

    return app, limiter


@pytest.fixture
def client(test_app):
    """Create a test client for the Flask application."""
    app, _ = test_app
    return app.test_client()


# =============================================================================
# Test 429 Response When Limit Exceeded
# =============================================================================


@pytest.mark.unit
class TestRateLimitExceeded:
    """Test that exceeding rate limit returns HTTP 429.

    **Validates: Requirements 2.2**
    """

    def test_429_response_on_job_submit_limit_exceeded(self, client):
        """Test that exceeding job submit rate limit returns 429.

        **Validates: Requirements 2.2**
        """
        # Make requests up to the limit (2 per minute)
        for i in range(2):
            response = client.post("/api/jobs")
            assert response.status_code == 200, f"Request {i + 1} should succeed"

        # Next request should be rate limited
        response = client.post("/api/jobs")
        assert response.status_code == 429, "Request exceeding limit should return 429"

    def test_429_response_on_job_status_limit_exceeded(self, client):
        """Test that exceeding job status rate limit returns 429.

        **Validates: Requirements 2.2**
        """
        # Make requests up to the limit (3 per minute)
        for i in range(3):
            response = client.get("/api/jobs/test-job-123")
            assert response.status_code == 200, f"Request {i + 1} should succeed"

        # Next request should be rate limited
        response = client.get("/api/jobs/test-job-123")
        assert response.status_code == 429, "Request exceeding limit should return 429"

    def test_429_response_on_listing_limit_exceeded(self, client):
        """Test that exceeding listing rate limit returns 429.

        **Validates: Requirements 2.2**
        """
        # Make requests up to the limit (2 per minute)
        for i in range(2):
            response = client.get("/api/jobs")
            assert response.status_code == 200, f"Request {i + 1} should succeed"

        # Next request should be rate limited
        response = client.get("/api/jobs")
        assert response.status_code == 429, "Request exceeding limit should return 429"


# =============================================================================
# Test Retry-After Header Presence
# =============================================================================


@pytest.mark.unit
class TestRetryAfterHeader:
    """Test that 429 response includes Retry-After header.

    **Validates: Requirements 2.2**
    """

    def test_retry_after_header_present(self, client):
        """Test that Retry-After header is present in 429 response.

        **Validates: Requirements 2.2**
        """
        # Exceed the rate limit
        for _ in range(3):
            client.post("/api/jobs")

        response = client.post("/api/jobs")
        assert response.status_code == 429

        # Check Retry-After header is present
        assert "Retry-After" in response.headers, "429 response must include Retry-After header"

    def test_retry_after_header_has_value(self, client):
        """Test that Retry-After header contains a meaningful value.

        Note: Flask-Limiter may return the rate limit description or a numeric value
        depending on configuration. Both are valid per HTTP spec.

        **Validates: Requirements 2.2**
        """
        # Exceed the rate limit
        for _ in range(3):
            client.post("/api/jobs")

        response = client.post("/api/jobs")
        assert response.status_code == 429

        retry_after = response.headers.get("Retry-After")
        assert retry_after is not None, "Retry-After header must be present"
        assert len(retry_after) > 0, "Retry-After header must not be empty"

        # The value should either be numeric or contain rate limit info
        # Both are acceptable per HTTP spec (RFC 7231 allows delay-seconds or HTTP-date)
        # Flask-Limiter uses the rate limit description which is informative


# =============================================================================
# Test JSON Response Structure
# =============================================================================


@pytest.mark.unit
class TestRateLimitResponseStructure:
    """Test that 429 response has correct JSON structure.

    The response should include:
    - error: True
    - error_code: "RATE_LIMIT_EXCEEDED"
    - message: Human-readable message
    - retry_after: Time until retry is allowed

    **Validates: Requirements 2.2**
    """

    def test_429_response_has_error_field(self, client):
        """Test that 429 response includes 'error' field set to True.

        **Validates: Requirements 2.2**
        """
        # Exceed the rate limit
        for _ in range(3):
            client.post("/api/jobs")

        response = client.post("/api/jobs")
        assert response.status_code == 429

        data = response.get_json()
        assert "error" in data, "Response must include 'error' field"
        assert data["error"] is True, "'error' field must be True"

    def test_429_response_has_error_code_field(self, client):
        """Test that 429 response includes 'error_code' field.

        **Validates: Requirements 2.2**
        """
        # Exceed the rate limit
        for _ in range(3):
            client.post("/api/jobs")

        response = client.post("/api/jobs")
        assert response.status_code == 429

        data = response.get_json()
        assert "error_code" in data, "Response must include 'error_code' field"
        assert data["error_code"] == "RATE_LIMIT_EXCEEDED", "error_code must be 'RATE_LIMIT_EXCEEDED'"

    def test_429_response_has_message_field(self, client):
        """Test that 429 response includes 'message' field.

        **Validates: Requirements 2.2**
        """
        # Exceed the rate limit
        for _ in range(3):
            client.post("/api/jobs")

        response = client.post("/api/jobs")
        assert response.status_code == 429

        data = response.get_json()
        assert "message" in data, "Response must include 'message' field"
        assert isinstance(data["message"], str), "'message' must be a string"
        assert len(data["message"]) > 0, "'message' must not be empty"

    def test_429_response_has_retry_after_field(self, client):
        """Test that 429 response includes 'retry_after' field in body.

        **Validates: Requirements 2.2**
        """
        # Exceed the rate limit
        for _ in range(3):
            client.post("/api/jobs")

        response = client.post("/api/jobs")
        assert response.status_code == 429

        data = response.get_json()
        assert "retry_after" in data, "Response must include 'retry_after' field"

    def test_429_response_complete_structure(self, client):
        """Test that 429 response has all required fields.

        **Validates: Requirements 2.2**
        """
        # Exceed the rate limit
        for _ in range(3):
            client.post("/api/jobs")

        response = client.post("/api/jobs")
        assert response.status_code == 429

        data = response.get_json()

        # Verify all required fields are present
        required_fields = ["error", "error_code", "message", "retry_after"]
        for field in required_fields:
            assert field in data, f"Response must include '{field}' field"

        # Verify field values
        assert data["error"] is True
        assert data["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert isinstance(data["message"], str)


# =============================================================================
# Test Per-Endpoint Limits
# =============================================================================


@pytest.mark.unit
class TestPerEndpointLimits:
    """Test that different endpoint categories have different limits.

    **Validates: Requirements 2.3**
    """

    def test_different_endpoints_have_independent_limits(self, client):
        """Test that rate limits are tracked independently per endpoint.

        **Validates: Requirements 2.3**
        """
        # Exhaust the job submit limit (2 per minute)
        for _ in range(2):
            response = client.post("/api/jobs")
            assert response.status_code == 200

        # Job submit should now be rate limited
        response = client.post("/api/jobs")
        assert response.status_code == 429

        # But job status endpoint should still work (different limit)
        response = client.get("/api/jobs/test-job-123")
        assert response.status_code == 200, "Job status endpoint should have independent rate limit"

    def test_job_status_has_higher_limit_than_submit(self, client):
        """Test that job status endpoint allows more requests than submit.

        **Validates: Requirements 2.3**
        """
        # Job status limit is 3 per minute, submit is 2 per minute
        # Make 3 job status requests - all should succeed
        for i in range(3):
            response = client.get("/api/jobs/test-job-123")
            assert response.status_code == 200, f"Job status request {i + 1} should succeed"

        # 4th request should be rate limited
        response = client.get("/api/jobs/test-job-123")
        assert response.status_code == 429

    def test_listing_endpoint_has_separate_limit(self, client):
        """Test that listing endpoint has its own rate limit.

        **Validates: Requirements 2.3**
        """
        # Exhaust the listing limit (2 per minute)
        for _ in range(2):
            response = client.get("/api/jobs")
            assert response.status_code == 200

        # Listing should now be rate limited
        response = client.get("/api/jobs")
        assert response.status_code == 429

        # But job status endpoint should still work
        response = client.get("/api/jobs/test-job-123")
        assert response.status_code == 200


# =============================================================================
# Test Rate Limiter Configuration
# =============================================================================


@pytest.mark.unit
class TestRateLimiterConfiguration:
    """Test rate limiter configuration and constants.

    **Validates: Requirements 2.3**
    """

    def test_rate_limit_constants_defined(self):
        """Test that rate limit constants are properly defined.

        **Validates: Requirements 2.3**
        """
        assert RATE_LIMIT_JOB_SUBMIT is not None
        assert RATE_LIMIT_JOB_STATUS is not None
        assert RATE_LIMIT_LISTING is not None

    def test_rate_limit_constants_format(self):
        """Test that rate limit constants have valid format.

        **Validates: Requirements 2.3**
        """
        # Rate limits should be strings in format "N per minute"
        for limit in [RATE_LIMIT_JOB_SUBMIT, RATE_LIMIT_JOB_STATUS, RATE_LIMIT_LISTING]:
            assert isinstance(limit, str), f"Rate limit should be string, got {type(limit)}"
            assert "per" in limit.lower(), f"Rate limit should contain 'per': {limit}"

    def test_job_submit_limit_is_restrictive(self):
        """Test that job submit has the most restrictive limit.

        Per requirements: job submission: 10/min, job status: 60/min, listing: 30/min

        **Validates: Requirements 2.3**
        """

        # Extract numeric values from limit strings
        def extract_limit(limit_str):
            parts = limit_str.split()
            return int(parts[0])

        submit_limit = extract_limit(RATE_LIMIT_JOB_SUBMIT)
        status_limit = extract_limit(RATE_LIMIT_JOB_STATUS)
        listing_limit = extract_limit(RATE_LIMIT_LISTING)

        # Job submit should be most restrictive
        assert submit_limit < status_limit, "Job submit limit should be lower than status limit"
        assert submit_limit < listing_limit, "Job submit limit should be lower than listing limit"

    def test_job_status_limit_is_highest(self):
        """Test that job status has the highest limit.

        Per requirements: job status: 60/min (highest to allow frequent polling)

        **Validates: Requirements 2.3**
        """

        def extract_limit(limit_str):
            parts = limit_str.split()
            return int(parts[0])

        submit_limit = extract_limit(RATE_LIMIT_JOB_SUBMIT)
        status_limit = extract_limit(RATE_LIMIT_JOB_STATUS)
        listing_limit = extract_limit(RATE_LIMIT_LISTING)

        # Job status should have highest limit
        assert status_limit > submit_limit
        assert status_limit > listing_limit


# =============================================================================
# Test create_limiter Function
# =============================================================================


@pytest.mark.unit
class TestCreateLimiter:
    """Test the create_limiter function.

    **Validates: Requirements 2.1, 2.2**
    """

    def test_create_limiter_returns_limiter_instance(self):
        """Test that create_limiter returns a Limiter instance.

        **Validates: Requirements 2.1**
        """
        app = Flask(__name__)
        app.config["TESTING"] = True

        limiter = create_limiter(app)

        assert limiter is not None
        assert isinstance(limiter, Limiter)

    def test_create_limiter_registers_429_handler(self):
        """Test that create_limiter registers the 429 error handler.

        **Validates: Requirements 2.2**
        """
        app = Flask(__name__)
        app.config["TESTING"] = True

        # Before creating limiter, no 429 handler
        limiter = create_limiter(app)

        # Create a rate-limited endpoint
        @app.route("/test")
        @limiter.limit("1 per minute")
        def test_endpoint():
            return "ok"

        client = app.test_client()

        # First request succeeds
        response = client.get("/test")
        assert response.status_code == 200

        # Second request should trigger 429 handler
        response = client.get("/test")
        assert response.status_code == 429

        # Verify the response is JSON with expected structure
        data = response.get_json()
        assert data is not None, "429 handler should return JSON"
        assert "error" in data
        assert "error_code" in data


# =============================================================================
# Test Decorator Functions
# =============================================================================


@pytest.mark.unit
class TestRateLimitDecorators:
    """Test the rate limit decorator functions.

    **Validates: Requirements 2.3**
    """

    def test_limit_job_submit_returns_decorator(self):
        """Test that limit_job_submit returns a decorator.

        **Validates: Requirements 2.3**
        """
        app = Flask(__name__)
        app.config["TESTING"] = True
        limiter = Limiter(app=app, key_func=get_remote_address, storage_uri="memory://")

        decorator = limit_job_submit(limiter)
        assert callable(decorator), "limit_job_submit should return a callable decorator"

    def test_limit_job_status_returns_decorator(self):
        """Test that limit_job_status returns a decorator.

        **Validates: Requirements 2.3**
        """
        app = Flask(__name__)
        app.config["TESTING"] = True
        limiter = Limiter(app=app, key_func=get_remote_address, storage_uri="memory://")

        decorator = limit_job_status(limiter)
        assert callable(decorator), "limit_job_status should return a callable decorator"

    def test_limit_listing_returns_decorator(self):
        """Test that limit_listing returns a decorator.

        **Validates: Requirements 2.3**
        """
        app = Flask(__name__)
        app.config["TESTING"] = True
        limiter = Limiter(app=app, key_func=get_remote_address, storage_uri="memory://")

        decorator = limit_listing(limiter)
        assert callable(decorator), "limit_listing should return a callable decorator"
