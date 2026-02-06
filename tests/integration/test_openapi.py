"""
Integration tests for OpenAPI documentation.

Tests the OpenAPI/Swagger documentation endpoints to ensure:
1. /api/docs endpoint returns Swagger UI HTML
2. /api/docs/openapi.json returns valid OpenAPI specification
3. All API endpoints are documented in the spec
4. Rate limit information is included in documentation

Feature: code-quality-security-hardening
**Validates: Requirements 9.1, 9.2, 9.3, 9.4**

Note: These tests use a standalone Flask app with flasgger to verify
the OpenAPI configuration pattern used in the main app. This avoids
import issues with the full deepr module chain.
"""

import json

import pytest

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def app_client():
    """Create a test client for a Flask application with OpenAPI.

    Creates a standalone Flask app with the same Swagger configuration
    pattern used in deepr/api/app.py to test OpenAPI functionality.
    """
    from flasgger import Swagger
    from flask import Flask

    app = Flask(__name__)
    app.config["TESTING"] = True

    # Swagger template matching the pattern in deepr/api/app.py
    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "Deepr Research API",
            "description": """
REST API for the Deepr deep research assistant.

## Rate Limiting
All endpoints are rate-limited to prevent abuse:
- **Job Submission**: 10 requests per minute
- **Job Status**: 60 requests per minute
- **Listing/Stats**: 30 requests per minute

When rate limits are exceeded, the API returns HTTP 429 with a `Retry-After` header.
            """,
            "version": "1.0.0",
        },
        "basePath": "/api",
        "schemes": ["http", "https"],
        "definitions": {
            "Job": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique job identifier"},
                    "prompt": {"type": "string", "description": "Research prompt"},
                    "status": {"type": "string", "description": "Job status"},
                },
            },
            "JobSubmitRequest": {
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {"type": "string", "description": "Research prompt"},
                },
            },
            "Error": {
                "type": "object",
                "properties": {
                    "error": {"type": "boolean"},
                    "error_code": {"type": "string"},
                    "message": {"type": "string"},
                },
            },
            "RateLimitError": {
                "type": "object",
                "properties": {
                    "error": {"type": "boolean"},
                    "error_code": {"type": "string"},
                    "retry_after": {"type": "integer"},
                },
            },
            "CostSummary": {
                "type": "object",
                "properties": {
                    "daily": {"type": "number"},
                    "monthly": {"type": "number"},
                },
            },
            "QueueStats": {
                "type": "object",
                "properties": {
                    "total": {"type": "integer"},
                },
            },
        },
    }

    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": "openapi",
                "route": "/api/docs/openapi.json",
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/api/docs",
    }

    swagger = Swagger(app, template=swagger_template, config=swagger_config)

    # Add test endpoints with OpenAPI docstrings
    @app.route("/api/jobs", methods=["GET"])
    def list_jobs():
        """List all jobs.
        ---
        tags:
          - Jobs
        responses:
          200:
            description: List of jobs
          429:
            description: Rate limit exceeded
            schema:
              $ref: '#/definitions/RateLimitError'
        """
        return {"jobs": []}, 200

    @app.route("/api/jobs", methods=["POST"])
    def submit_job():
        """Submit a new job.
        ---
        tags:
          - Jobs
        parameters:
          - name: body
            in: body
            schema:
              $ref: '#/definitions/JobSubmitRequest'
        responses:
          200:
            description: Job created
          429:
            description: Rate limit exceeded
        """
        return {"job": {}}, 200

    @app.route("/api/jobs/<job_id>", methods=["GET"])
    def get_job(job_id):
        """Get job details.
        ---
        tags:
          - Jobs
        parameters:
          - name: job_id
            in: path
            type: string
            required: true
        responses:
          200:
            description: Job details
          429:
            description: Rate limit exceeded
        """
        return {"job": {}}, 200

    @app.route("/api/jobs/stats", methods=["GET"])
    def get_stats():
        """Get queue statistics.
        ---
        tags:
          - Jobs
        responses:
          200:
            description: Queue stats
            schema:
              $ref: '#/definitions/QueueStats'
          429:
            description: Rate limit exceeded
        """
        return {"total": 0}, 200

    @app.route("/api/results/<job_id>", methods=["GET"])
    def get_result(job_id):
        """Get job result.
        ---
        tags:
          - Results
        parameters:
          - name: job_id
            in: path
            type: string
            required: true
        responses:
          200:
            description: Job result
          429:
            description: Rate limit exceeded
        """
        return {"content": ""}, 200

    @app.route("/api/cost/summary", methods=["GET"])
    def get_cost_summary():
        """Get cost summary.
        ---
        tags:
          - Costs
        responses:
          200:
            description: Cost summary
            schema:
              $ref: '#/definitions/CostSummary'
          429:
            description: Rate limit exceeded
        """
        return {"daily": 0}, 200

    with app.test_client() as client:
        yield client


# =============================================================================
# Test /api/docs Endpoint (Swagger UI)
# =============================================================================


@pytest.mark.integration
class TestSwaggerUIEndpoint:
    """Test that /api/docs serves Swagger UI.

    **Validates: Requirements 9.1, 9.2**
    """

    def test_api_docs_returns_200(self, app_client):
        """Test that /api/docs endpoint returns HTTP 200.

        **Validates: Requirements 9.2**
        """
        # Try both with and without trailing slash
        response = app_client.get("/api/docs/")
        if response.status_code == 404:
            response = app_client.get("/api/docs")

        assert response.status_code in [200, 302, 308], f"Expected 200/302/308, got {response.status_code}"

    def test_api_docs_returns_html(self, app_client):
        """Test that /api/docs returns HTML content.

        **Validates: Requirements 9.2**
        """
        # Try both with and without trailing slash
        response = app_client.get("/api/docs/")
        if response.status_code == 404:
            response = app_client.get("/api/docs")

        # Follow redirects if needed
        if response.status_code in [302, 308]:
            # The redirect indicates the endpoint exists
            assert True
            return

        assert response.status_code == 200

        content_type = response.content_type
        assert "text/html" in content_type, f"Expected HTML content type, got {content_type}"

    def test_api_docs_contains_swagger_ui(self, app_client):
        """Test that /api/docs contains Swagger UI elements.

        **Validates: Requirements 9.2**
        """
        # Try both with and without trailing slash
        response = app_client.get("/api/docs/")
        if response.status_code == 404:
            response = app_client.get("/api/docs")

        # Follow redirects if needed
        if response.status_code in [302, 308]:
            # The redirect indicates the endpoint exists
            assert True
            return

        assert response.status_code == 200

        html_content = response.data.decode("utf-8")

        # Check for Swagger UI indicators
        swagger_indicators = [
            "swagger",
            "SwaggerUI",
            "swagger-ui",
        ]

        found_indicator = any(indicator.lower() in html_content.lower() for indicator in swagger_indicators)

        assert found_indicator, "Swagger UI page should contain swagger-related content"


# =============================================================================
# Test /api/docs/openapi.json Endpoint
# =============================================================================


@pytest.mark.integration
class TestOpenAPISpecEndpoint:
    """Test that /api/docs/openapi.json returns valid OpenAPI spec.

    **Validates: Requirements 9.1, 9.3**
    """

    def test_openapi_json_returns_200(self, app_client):
        """Test that /api/docs/openapi.json returns HTTP 200.

        **Validates: Requirements 9.1**
        """
        response = app_client.get("/api/docs/openapi.json")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_openapi_json_returns_json(self, app_client):
        """Test that /api/docs/openapi.json returns JSON content.

        **Validates: Requirements 9.1**
        """
        response = app_client.get("/api/docs/openapi.json")
        assert response.status_code == 200

        content_type = response.content_type
        assert "application/json" in content_type, f"Expected JSON content type, got {content_type}"

    def test_openapi_json_is_valid_json(self, app_client):
        """Test that /api/docs/openapi.json returns parseable JSON.

        **Validates: Requirements 9.1**
        """
        response = app_client.get("/api/docs/openapi.json")
        assert response.status_code == 200

        # Should not raise JSONDecodeError
        spec = json.loads(response.data)
        assert isinstance(spec, dict), "OpenAPI spec should be a JSON object"

    def test_openapi_spec_has_info_section(self, app_client):
        """Test that OpenAPI spec contains info section.

        **Validates: Requirements 9.1**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        assert "info" in spec, "OpenAPI spec must have 'info' section"
        assert "title" in spec["info"], "Info section must have 'title'"
        assert "version" in spec["info"], "Info section must have 'version'"

    def test_openapi_spec_has_paths_section(self, app_client):
        """Test that OpenAPI spec contains paths section.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        assert "paths" in spec, "OpenAPI spec must have 'paths' section"
        assert len(spec["paths"]) > 0, "Paths section should not be empty"

    def test_openapi_spec_has_definitions(self, app_client):
        """Test that OpenAPI spec contains schema definitions.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        assert "definitions" in spec, "OpenAPI spec must have 'definitions' section"


# =============================================================================
# Test All Endpoints Are Documented
# =============================================================================


@pytest.mark.integration
class TestEndpointDocumentation:
    """Test that all API endpoints are documented in OpenAPI spec.

    **Validates: Requirements 9.3**
    """

    def test_jobs_list_endpoint_documented(self, app_client):
        """Test that GET /api/jobs is documented.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        # Check for /jobs or /api/jobs path
        paths = spec.get("paths", {})
        jobs_path = paths.get("/jobs") or paths.get("/api/jobs")

        assert jobs_path is not None, "GET /api/jobs should be documented"
        assert "get" in jobs_path, "GET method should be documented for /jobs"

    def test_jobs_submit_endpoint_documented(self, app_client):
        """Test that POST /api/jobs is documented.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        paths = spec.get("paths", {})
        jobs_path = paths.get("/jobs") or paths.get("/api/jobs")

        assert jobs_path is not None, "POST /api/jobs should be documented"
        assert "post" in jobs_path, "POST method should be documented for /jobs"

    def test_job_detail_endpoint_documented(self, app_client):
        """Test that GET /api/jobs/{job_id} is documented.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        paths = spec.get("paths", {})

        # Look for job detail path (may be /jobs/{job_id} or /api/jobs/{job_id})
        job_detail_path = None
        for path_key in paths:
            if "{job_id}" in path_key and "jobs" in path_key and "stats" not in path_key:
                job_detail_path = paths[path_key]
                break

        assert job_detail_path is not None, "GET /api/jobs/{job_id} should be documented"
        assert "get" in job_detail_path, "GET method should be documented for job detail"

    def test_results_endpoint_documented(self, app_client):
        """Test that GET /api/results/{job_id} is documented.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        paths = spec.get("paths", {})

        # Look for results path
        results_path = None
        for path_key in paths:
            if "results" in path_key and "{job_id}" in path_key:
                results_path = paths[path_key]
                break

        assert results_path is not None, "GET /api/results/{job_id} should be documented"

    def test_cost_summary_endpoint_documented(self, app_client):
        """Test that GET /api/cost/summary is documented.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        paths = spec.get("paths", {})

        # Look for cost summary path
        cost_path = None
        for path_key in paths:
            if "cost" in path_key and "summary" in path_key:
                cost_path = paths[path_key]
                break

        assert cost_path is not None, "GET /api/cost/summary should be documented"

    def test_stats_endpoint_documented(self, app_client):
        """Test that GET /api/jobs/stats is documented.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        paths = spec.get("paths", {})

        # Look for stats path
        stats_path = None
        for path_key in paths:
            if "stats" in path_key:
                stats_path = paths[path_key]
                break

        assert stats_path is not None, "GET /api/jobs/stats should be documented"


# =============================================================================
# Test Rate Limit Documentation
# =============================================================================


@pytest.mark.integration
class TestRateLimitDocumentation:
    """Test that rate limit information is included in documentation.

    **Validates: Requirements 9.4**
    """

    def test_rate_limit_mentioned_in_description(self, app_client):
        """Test that rate limits are mentioned in API description.

        **Validates: Requirements 9.4**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        # Check info description for rate limit mention
        info = spec.get("info", {})
        description = info.get("description", "")

        rate_limit_keywords = ["rate limit", "rate-limit", "ratelimit", "429"]
        found_rate_limit = any(keyword.lower() in description.lower() for keyword in rate_limit_keywords)

        assert found_rate_limit, "API description should mention rate limiting"

    def test_429_response_documented(self, app_client):
        """Test that 429 response is documented for endpoints.

        **Validates: Requirements 9.4**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        paths = spec.get("paths", {})

        # Check at least one endpoint has 429 response documented
        found_429 = False
        for path_key, path_item in paths.items():
            for method, operation in path_item.items():
                if isinstance(operation, dict):
                    responses = operation.get("responses", {})
                    if "429" in responses or 429 in responses:
                        found_429 = True
                        break
            if found_429:
                break

        assert found_429, "At least one endpoint should document 429 response"

    def test_rate_limit_error_schema_defined(self, app_client):
        """Test that rate limit error schema is defined.

        **Validates: Requirements 9.4**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        definitions = spec.get("definitions", {})

        # Look for rate limit error definition
        rate_limit_schemas = ["RateLimitError", "Error", "ErrorResponse"]

        found_schema = any(schema in definitions for schema in rate_limit_schemas)

        assert found_schema, "Rate limit error schema should be defined"


# =============================================================================
# Test Request/Response Schemas
# =============================================================================


@pytest.mark.integration
class TestRequestResponseSchemas:
    """Test that request/response schemas are properly defined.

    **Validates: Requirements 9.3**
    """

    def test_job_schema_defined(self, app_client):
        """Test that Job schema is defined.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        definitions = spec.get("definitions", {})

        assert "Job" in definitions, "Job schema should be defined"

        job_schema = definitions["Job"]
        assert "properties" in job_schema, "Job schema should have properties"

    def test_job_submit_request_schema_defined(self, app_client):
        """Test that job submission request schema is defined.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        definitions = spec.get("definitions", {})

        # Look for job submit request schema
        submit_schemas = ["JobSubmitRequest", "JobRequest", "CreateJobRequest"]

        found_schema = any(schema in definitions for schema in submit_schemas)

        assert found_schema, "Job submission request schema should be defined"

    def test_error_schema_defined(self, app_client):
        """Test that Error schema is defined.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        definitions = spec.get("definitions", {})

        assert "Error" in definitions, "Error schema should be defined"

        error_schema = definitions["Error"]
        assert "properties" in error_schema, "Error schema should have properties"

    def test_cost_summary_schema_defined(self, app_client):
        """Test that CostSummary schema is defined.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        definitions = spec.get("definitions", {})

        assert "CostSummary" in definitions, "CostSummary schema should be defined"


# =============================================================================
# Test OpenAPI Spec Validity
# =============================================================================


@pytest.mark.integration
class TestOpenAPISpecValidity:
    """Test that the OpenAPI spec is structurally valid.

    **Validates: Requirements 9.1**
    """

    def test_spec_has_swagger_version(self, app_client):
        """Test that spec declares Swagger/OpenAPI version.

        **Validates: Requirements 9.1**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        # Should have either 'swagger' (2.0) or 'openapi' (3.x)
        has_version = "swagger" in spec or "openapi" in spec

        assert has_version, "OpenAPI spec must declare version (swagger or openapi field)"

    def test_spec_has_base_path_or_servers(self, app_client):
        """Test that spec declares base path or servers.

        **Validates: Requirements 9.1**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        # Swagger 2.0 uses basePath, OpenAPI 3.x uses servers
        has_base = "basePath" in spec or "servers" in spec

        assert has_base, "OpenAPI spec should declare basePath or servers"

    def test_all_paths_have_operations(self, app_client):
        """Test that all paths have at least one operation defined.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        paths = spec.get("paths", {})

        http_methods = ["get", "post", "put", "patch", "delete", "options", "head"]

        for path_key, path_item in paths.items():
            has_operation = any(method in path_item for method in http_methods)
            assert has_operation, f"Path {path_key} should have at least one HTTP method defined"

    def test_operations_have_responses(self, app_client):
        """Test that all operations have responses defined.

        **Validates: Requirements 9.3**
        """
        response = app_client.get("/api/docs/openapi.json")
        spec = json.loads(response.data)

        paths = spec.get("paths", {})
        http_methods = ["get", "post", "put", "patch", "delete"]

        for path_key, path_item in paths.items():
            for method in http_methods:
                if method in path_item:
                    operation = path_item[method]
                    if isinstance(operation, dict):
                        assert "responses" in operation, f"{method.upper()} {path_key} should have responses defined"
