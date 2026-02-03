"""
Flask API for Deepr - matches React frontend API expectations.

This module provides the REST API for the Deepr research assistant,
including OpenAPI documentation via Swagger UI at /api/docs.
"""

import os
import asyncio
import logging
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger
from dotenv import load_dotenv

# Import rate limiter middleware
from deepr.api.middleware.rate_limiter import (
    create_limiter,
    limit_job_submit,
    limit_job_status,
    limit_listing
)

# Import error handler middleware
from deepr.api.middleware.errors import register_error_handlers

# Import rate limit constants for documentation
from deepr.core.constants import (
    RATE_LIMIT_JOB_SUBMIT,
    RATE_LIMIT_JOB_STATUS,
    RATE_LIMIT_LISTING
)

load_dotenv()

# Configure logging for rate limit events
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS: use env var in production, default to localhost dev servers
_cors_origins = os.getenv(
    "DEEPR_CORS_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://localhost:3000"
)
CORS(app, origins=[o.strip() for o in _cors_origins.split(",")])

# Bearer token authentication
_api_token = os.getenv("DEEPR_API_TOKEN")


@app.before_request
def _check_auth():
    """Require bearer token if DEEPR_API_TOKEN is set."""
    if not _api_token:
        return  # No token configured -- allow all (local dev)
    # Skip auth for health check and docs
    if request.path in ("/health", "/api/docs", "/apispec_1.json"):
        return
    if request.path.startswith("/flasgger_static"):
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != _api_token:
        return jsonify({"error": "Unauthorized"}), 401

# =============================================================================
# OpenAPI/Swagger Configuration
# =============================================================================

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Deepr Research API",
        "description": """
REST API for the Deepr deep research assistant.

## Overview
Deepr provides AI-powered research capabilities with support for multiple LLM providers.
This API allows you to submit research jobs, monitor their status, and retrieve results.

## Rate Limiting
All endpoints are rate-limited to prevent abuse:
- **Job Submission**: 10 requests per minute
- **Job Status**: 60 requests per minute  
- **Listing/Stats**: 30 requests per minute

When rate limits are exceeded, the API returns HTTP 429 with a `Retry-After` header.

## Error Handling
All errors return a consistent JSON structure:
```json
{
    "error": true,
    "error_code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": {}
}
```

## Authentication
Currently, the API does not require authentication. Rate limiting is based on client IP address.
        """,
        "version": "1.0.0",
        "contact": {
            "name": "Deepr Support",
            "url": "https://github.com/deepr-ai/deepr"
        },
        "license": {
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT"
        }
    },
    "basePath": "/api",
    "schemes": ["http", "https"],
    "tags": [
        {
            "name": "Jobs",
            "description": "Research job management endpoints"
        },
        {
            "name": "Results",
            "description": "Job results retrieval"
        },
        {
            "name": "Costs",
            "description": "Cost tracking and summaries"
        }
    ],
    "definitions": {
        "Job": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Unique job identifier (UUID)",
                    "example": "550e8400-e29b-41d4-a716-446655440000"
                },
                "prompt": {
                    "type": "string",
                    "description": "Research prompt/query",
                    "example": "What are the latest advances in quantum computing?"
                },
                "model": {
                    "type": "string",
                    "description": "LLM model to use",
                    "example": "o4-mini-deep-research"
                },
                "status": {
                    "type": "string",
                    "enum": ["queued", "processing", "completed", "failed", "cancelled"],
                    "description": "Current job status"
                },
                "priority": {
                    "type": "integer",
                    "description": "Job priority (1-5, lower is higher priority)",
                    "example": 3
                },
                "cost": {
                    "type": "number",
                    "description": "Actual cost in USD",
                    "example": 0.50
                },
                "tokens_used": {
                    "type": "integer",
                    "description": "Total tokens consumed",
                    "example": 15000
                },
                "submitted_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO 8601 timestamp of submission"
                },
                "started_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO 8601 timestamp when processing started"
                },
                "completed_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO 8601 timestamp when job completed"
                },
                "enable_web_search": {
                    "type": "boolean",
                    "description": "Whether web search is enabled",
                    "example": True
                },
                "last_error": {
                    "type": "string",
                    "description": "Last error message if failed"
                }
            }
        },
        "JobSubmitRequest": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Research prompt/query",
                    "example": "What are the latest advances in quantum computing?"
                },
                "model": {
                    "type": "string",
                    "description": "LLM model to use (default: o4-mini-deep-research)",
                    "example": "o4-mini-deep-research"
                },
                "priority": {
                    "type": "integer",
                    "description": "Job priority 1-5 (default: 3)",
                    "example": 3
                },
                "enable_web_search": {
                    "type": "boolean",
                    "description": "Enable web search (default: true)",
                    "example": True
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional metadata for the job"
                }
            }
        },
        "EstimatedCost": {
            "type": "object",
            "properties": {
                "min_cost": {
                    "type": "number",
                    "description": "Minimum estimated cost in USD",
                    "example": 0.25
                },
                "max_cost": {
                    "type": "number",
                    "description": "Maximum estimated cost in USD",
                    "example": 1.00
                },
                "estimated_cost": {
                    "type": "number",
                    "description": "Expected cost in USD",
                    "example": 0.50
                },
                "currency": {
                    "type": "string",
                    "example": "USD"
                }
            }
        },
        "QueueStats": {
            "type": "object",
            "properties": {
                "total": {
                    "type": "integer",
                    "description": "Total number of jobs"
                },
                "queued": {
                    "type": "integer",
                    "description": "Jobs waiting in queue"
                },
                "processing": {
                    "type": "integer",
                    "description": "Jobs currently processing"
                },
                "completed": {
                    "type": "integer",
                    "description": "Successfully completed jobs"
                },
                "failed": {
                    "type": "integer",
                    "description": "Failed jobs"
                },
                "total_cost": {
                    "type": "number",
                    "description": "Total cost in USD"
                },
                "total_tokens": {
                    "type": "integer",
                    "description": "Total tokens used"
                }
            }
        },
        "CostSummary": {
            "type": "object",
            "properties": {
                "daily": {
                    "type": "number",
                    "description": "Cost for current day in USD"
                },
                "monthly": {
                    "type": "number",
                    "description": "Cost for current month in USD"
                },
                "total": {
                    "type": "number",
                    "description": "Total cost in USD"
                },
                "daily_limit": {
                    "type": "number",
                    "description": "Daily spending limit in USD"
                },
                "monthly_limit": {
                    "type": "number",
                    "description": "Monthly spending limit in USD"
                },
                "total_jobs": {
                    "type": "integer",
                    "description": "Total number of jobs"
                },
                "completed_jobs": {
                    "type": "integer",
                    "description": "Number of completed jobs"
                },
                "avg_cost_per_job": {
                    "type": "number",
                    "description": "Average cost per completed job"
                },
                "currency": {
                    "type": "string",
                    "example": "USD"
                }
            }
        },
        "Error": {
            "type": "object",
            "properties": {
                "error": {
                    "type": "boolean",
                    "example": True
                },
                "error_code": {
                    "type": "string",
                    "description": "Machine-readable error code",
                    "example": "RATE_LIMIT_EXCEEDED"
                },
                "message": {
                    "type": "string",
                    "description": "Human-readable error message",
                    "example": "Too many requests. Please try again later."
                },
                "details": {
                    "type": "object",
                    "description": "Additional error details"
                }
            }
        },
        "RateLimitError": {
            "type": "object",
            "properties": {
                "error": {
                    "type": "boolean",
                    "example": True
                },
                "error_code": {
                    "type": "string",
                    "example": "RATE_LIMIT_EXCEEDED"
                },
                "message": {
                    "type": "string",
                    "example": "Too many requests. Please try again later."
                },
                "retry_after": {
                    "type": "integer",
                    "description": "Seconds to wait before retrying",
                    "example": 60
                }
            }
        }
    }
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
    "specs_route": "/api/docs"
}

swagger = Swagger(app, template=swagger_template, config=swagger_config)

# Initialize rate limiter - must be done after app creation
# The 429 error handler is registered by create_limiter()
limiter = create_limiter(app)

# Register centralized error handlers for DeeprError and unexpected exceptions
# This ensures consistent error responses and secure logging (sanitize_log_message)
register_error_handlers(app)

# Initialize services
from deepr.queue.local_queue import SQLiteQueue
from deepr.storage.local import LocalStorage
from deepr.providers.openai_provider import OpenAIProvider
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.queue.base import ResearchJob, JobStatus
from deepr.config import load_config
import uuid

# Load config to get correct queue path
config = load_config()
queue = SQLiteQueue(config['queue_db_path'])
storage = LocalStorage(config['results_dir'])
provider = OpenAIProvider(api_key=config['api_key'])


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.route('/api/jobs', methods=['GET'])
@limit_listing(limiter)
def list_jobs():
    """List all research jobs with optional filtering.

    Returns a paginated list of research jobs. Can filter by status.

    Rate limit: 30 requests per minute (listing category).
    ---
    tags:
      - Jobs
    parameters:
      - name: limit
        in: query
        type: integer
        default: 100
        description: Maximum number of jobs to return
      - name: offset
        in: query
        type: integer
        default: 0
        description: Number of jobs to skip for pagination
      - name: status
        in: query
        type: string
        enum: [queued, processing, completed, failed, cancelled]
        description: Filter by job status
    responses:
      200:
        description: List of jobs
        schema:
          type: object
          properties:
            jobs:
              type: array
              items:
                $ref: '#/definitions/Job'
            total:
              type: integer
              description: Total number of jobs returned
        examples:
          application/json:
            jobs:
              - id: "550e8400-e29b-41d4-a716-446655440000"
                prompt: "Research quantum computing"
                model: "o4-mini-deep-research"
                status: "completed"
                priority: 3
                cost: 0.50
            total: 1
      429:
        description: Rate limit exceeded
        headers:
          Retry-After:
            type: integer
            description: Seconds to wait before retrying
        schema:
          $ref: '#/definitions/RateLimitError'
      500:
        description: Internal server error
        schema:
          $ref: '#/definitions/Error'
    """
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    status_filter = request.args.get('status', None)

    if status_filter:
        status_enum = JobStatus(status_filter)
        jobs = run_async(queue.list_jobs(status=status_enum, limit=limit, offset=offset))
    else:
        jobs = run_async(queue.list_jobs(limit=limit, offset=offset))

    jobs_data = []
    for job in jobs:
        jobs_data.append({
            'id': job.id,
            'prompt': job.prompt,
            'model': job.model,
            'status': job.status.value,
            'priority': job.priority,
            'cost': job.cost or 0,
            'tokens_used': job.tokens_used or 0,
            'submitted_at': job.submitted_at.isoformat() if job.submitted_at else None,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'metadata': job.metadata or {},
            'provider_job_id': job.provider_job_id,
            'enable_web_search': job.enable_web_search,
            'last_error': job.last_error
        })

    return jsonify({'jobs': jobs_data, 'total': len(jobs_data)})


@app.route('/api/jobs/<job_id>', methods=['GET'])
@limit_job_status(limiter)
def get_job(job_id):
    """Get details for a specific research job.
    
    Returns full details for a single job including status, cost, and timestamps.
    
    Rate limit: 60 requests per minute (job status category).
    ---
    tags:
      - Jobs
    parameters:
      - name: job_id
        in: path
        type: string
        required: true
        description: Unique job identifier (UUID)
    responses:
      200:
        description: Job details
        schema:
          type: object
          properties:
            job:
              $ref: '#/definitions/Job'
        examples:
          application/json:
            job:
              id: "550e8400-e29b-41d4-a716-446655440000"
              prompt: "Research quantum computing"
              model: "o4-mini-deep-research"
              status: "completed"
              priority: 3
              cost: 0.50
              tokens_used: 15000
      404:
        description: Job not found
        schema:
          $ref: '#/definitions/Error'
        examples:
          application/json:
            error: "Job not found"
      429:
        description: Rate limit exceeded
        headers:
          Retry-After:
            type: integer
            description: Seconds to wait before retrying
        schema:
          $ref: '#/definitions/RateLimitError'
      500:
        description: Internal server error
        schema:
          $ref: '#/definitions/Error'
    """
    job = run_async(queue.get_job(job_id))

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    job_data = {
        'id': job.id,
        'prompt': job.prompt,
        'model': job.model,
        'status': job.status.value,
        'priority': job.priority,
        'cost': job.cost or 0,
        'tokens_used': job.tokens_used or 0,
        'submitted_at': job.submitted_at.isoformat() if job.submitted_at else None,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        'metadata': job.metadata or {},
        'provider_job_id': job.provider_job_id,
        'enable_web_search': job.enable_web_search,
        'last_error': job.last_error
    }

    return jsonify({'job': job_data})


@app.route('/api/jobs', methods=['POST'])
@limit_job_submit(limiter)
def submit_job():
    """Submit a new research job.
    
    Creates a new research job and submits it to the LLM provider for processing.
    Returns the created job with an estimated cost.
    
    Rate limit: 10 requests per minute (job submission category).
    ---
    tags:
      - Jobs
    consumes:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/JobSubmitRequest'
    responses:
      200:
        description: Job created successfully
        schema:
          type: object
          properties:
            job:
              type: object
              properties:
                id:
                  type: string
                  description: Unique job identifier
                prompt:
                  type: string
                model:
                  type: string
                status:
                  type: string
                provider_job_id:
                  type: string
                  description: Provider-specific job identifier
            estimated_cost:
              $ref: '#/definitions/EstimatedCost'
        examples:
          application/json:
            job:
              id: "550e8400-e29b-41d4-a716-446655440000"
              prompt: "Research quantum computing"
              model: "o4-mini-deep-research"
              status: "processing"
              provider_job_id: "resp_abc123"
            estimated_cost:
              min_cost: 0.25
              max_cost: 1.00
              estimated_cost: 0.50
              currency: "USD"
      400:
        description: Invalid request (missing prompt)
        schema:
          $ref: '#/definitions/Error'
        examples:
          application/json:
            error: "Prompt required"
      429:
        description: Rate limit exceeded
        headers:
          Retry-After:
            type: integer
            description: Seconds to wait before retrying
        schema:
          $ref: '#/definitions/RateLimitError'
      500:
        description: Internal server error
        schema:
          $ref: '#/definitions/Error'
    """
    data = request.json
    prompt = data.get('prompt')
    model = data.get('model', 'o4-mini-deep-research')
    priority = data.get('priority', 3)
    enable_web_search = data.get('enable_web_search', True)

    if not prompt:
        return jsonify({'error': 'Prompt required'}), 400

    # Create job
    job_id = str(uuid.uuid4())
    job = ResearchJob(
        id=job_id,
        prompt=prompt,
        model=model,
        priority=priority,
        enable_web_search=enable_web_search,
        status=JobStatus.QUEUED,
        metadata=data.get('metadata', {})
    )

    run_async(queue.enqueue(job))

    # Submit to provider
    req = ResearchRequest(
        prompt=prompt,
        model=model,
        system_message='You are a research assistant. Provide comprehensive, citation-backed analysis.',
        tools=[ToolConfig(type='web_search_preview')] if enable_web_search else [],
        background=True,
    )

    provider_job_id = run_async(provider.submit_research(req))

    # Update status
    run_async(queue.update_status(
        job_id=job_id,
        status=JobStatus.PROCESSING,
        provider_job_id=provider_job_id
    ))

    # Calculate cost estimate
    avg_cost = 0.5 if 'mini' in model else 5.0
    estimated_cost = {
        'min_cost': avg_cost * 0.5,
        'max_cost': avg_cost * 2.0,
        'estimated_cost': avg_cost,
        'currency': 'USD'
    }

    return jsonify({
        'job': {
            'id': job_id,
            'prompt': prompt,
            'model': model,
            'status': 'processing',
            'provider_job_id': provider_job_id
        },
        'estimated_cost': estimated_cost
    })


@app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
@limit_job_submit(limiter)
def cancel_job(job_id):
    """Cancel a research job.
    
    Attempts to cancel a job that is queued or processing.
    Completed or already cancelled jobs cannot be cancelled.
    
    Rate limit: 10 requests per minute (job submission category).
    ---
    tags:
      - Jobs
    parameters:
      - name: job_id
        in: path
        type: string
        required: true
        description: Unique job identifier (UUID)
    responses:
      200:
        description: Cancellation result
        schema:
          type: object
          properties:
            success:
              type: boolean
              description: Whether cancellation was successful
        examples:
          application/json:
            success: true
      429:
        description: Rate limit exceeded
        headers:
          Retry-After:
            type: integer
            description: Seconds to wait before retrying
        schema:
          $ref: '#/definitions/RateLimitError'
      500:
        description: Internal server error
        schema:
          $ref: '#/definitions/Error'
    """
    success = run_async(queue.cancel_job(job_id))
    return jsonify({'success': success})


@app.route('/api/jobs/<job_id>', methods=['DELETE'])
@limit_job_submit(limiter)
def delete_job(job_id):
    """Delete a research job.
    
    Removes a job from the queue. Currently implemented as cancellation.
    
    Rate limit: 10 requests per minute (job submission category).
    ---
    tags:
      - Jobs
    parameters:
      - name: job_id
        in: path
        type: string
        required: true
        description: Unique job identifier (UUID)
    responses:
      200:
        description: Deletion result
        schema:
          type: object
          properties:
            success:
              type: boolean
              description: Whether deletion was successful
        examples:
          application/json:
            success: true
      429:
        description: Rate limit exceeded
        headers:
          Retry-After:
            type: integer
            description: Seconds to wait before retrying
        schema:
          $ref: '#/definitions/RateLimitError'
      500:
        description: Internal server error
        schema:
          $ref: '#/definitions/Error'
    """
    # For now, just cancel it
    success = run_async(queue.cancel_job(job_id))
    return jsonify({'success': success})


@app.route('/api/jobs/stats', methods=['GET'])
@limit_listing(limiter)
def get_stats():
    """Get queue statistics.
    
    Returns aggregate statistics about all jobs in the queue including
    counts by status, total cost, and token usage.
    
    Rate limit: 30 requests per minute (listing category).
    ---
    tags:
      - Jobs
    responses:
      200:
        description: Queue statistics
        schema:
          $ref: '#/definitions/QueueStats'
        examples:
          application/json:
            total: 100
            queued: 5
            processing: 2
            completed: 90
            failed: 3
            total_cost: 45.50
            total_tokens: 1500000
      429:
        description: Rate limit exceeded
        headers:
          Retry-After:
            type: integer
            description: Seconds to wait before retrying
        schema:
          $ref: '#/definitions/RateLimitError'
      500:
        description: Internal server error
        schema:
          $ref: '#/definitions/Error'
    """
    all_jobs = run_async(queue.list_jobs(limit=1000))

    stats = {
        'total': len(all_jobs),
        'queued': sum(1 for j in all_jobs if j.status == JobStatus.QUEUED),
        'processing': sum(1 for j in all_jobs if j.status == JobStatus.PROCESSING),
        'completed': sum(1 for j in all_jobs if j.status == JobStatus.COMPLETED),
        'failed': sum(1 for j in all_jobs if j.status == JobStatus.FAILED),
        'total_cost': sum(j.cost or 0 for j in all_jobs),
        'total_tokens': sum(j.tokens_used or 0 for j in all_jobs)
    }

    return jsonify(stats)


@app.route('/api/results/<job_id>', methods=['GET'])
@limit_job_status(limiter)
def get_result(job_id):
    """Get the result of a completed research job.
    
    Returns the research report content for a completed job.
    Returns an error if the job is not yet completed.
    
    Rate limit: 60 requests per minute (job status category).
    ---
    tags:
      - Results
    parameters:
      - name: job_id
        in: path
        type: string
        required: true
        description: Unique job identifier (UUID)
    responses:
      200:
        description: Research result
        schema:
          type: object
          properties:
            job_id:
              type: string
              description: Job identifier
            content:
              type: string
              description: Research report content (markdown)
            format:
              type: string
              description: Content format
              example: "markdown"
        examples:
          application/json:
            job_id: "550e8400-e29b-41d4-a716-446655440000"
            content: "# Research Report\\n\\n## Summary\\n..."
            format: "markdown"
      400:
        description: Job not completed yet
        schema:
          $ref: '#/definitions/Error'
        examples:
          application/json:
            error: "Job not completed yet"
      404:
        description: Job not found
        schema:
          $ref: '#/definitions/Error'
        examples:
          application/json:
            error: "Job not found"
      429:
        description: Rate limit exceeded
        headers:
          Retry-After:
            type: integer
            description: Seconds to wait before retrying
        schema:
          $ref: '#/definitions/RateLimitError'
      500:
        description: Internal server error
        schema:
          $ref: '#/definitions/Error'
    """
    job = run_async(queue.get_job(job_id))

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    if job.status != JobStatus.COMPLETED:
        return jsonify({'error': 'Job not completed yet'}), 400

    # Get result
    result = run_async(storage.get_report(job_id=job_id, filename='report.md'))

    return jsonify({
        'job_id': job_id,
        'content': result.decode('utf-8'),
        'format': 'markdown'
    })


@app.route('/api/cost/summary', methods=['GET'])
@limit_listing(limiter)
def get_cost_summary():
    """Get cost summary and spending limits.
    
    Returns a summary of costs including daily, monthly, and total spending,
    along with configured spending limits.
    
    Rate limit: 30 requests per minute (listing category).
    ---
    tags:
      - Costs
    responses:
      200:
        description: Cost summary
        schema:
          $ref: '#/definitions/CostSummary'
        examples:
          application/json:
            daily: 5.50
            monthly: 45.50
            total: 45.50
            daily_limit: 100.0
            monthly_limit: 1000.0
            total_jobs: 100
            completed_jobs: 90
            avg_cost_per_job: 0.51
            currency: "USD"
      429:
        description: Rate limit exceeded
        headers:
          Retry-After:
            type: integer
            description: Seconds to wait before retrying
        schema:
          $ref: '#/definitions/RateLimitError'
      500:
        description: Internal server error
        schema:
          $ref: '#/definitions/Error'
    """
    all_jobs = run_async(queue.list_jobs(limit=1000))
    total_cost = sum(j.cost or 0 for j in all_jobs)
    completed = [j for j in all_jobs if j.status == JobStatus.COMPLETED]

    # Simple mock for daily/monthly - in real impl, filter by date
    summary = {
        'daily': total_cost,
        'monthly': total_cost,
        'total': total_cost,
        'daily_limit': 100.0,
        'monthly_limit': 1000.0,
        'total_jobs': len(all_jobs),
        'completed_jobs': len(completed),
        'avg_cost_per_job': total_cost / len(completed) if completed else 0,
        'currency': 'USD'
    }
    return jsonify(summary)


if __name__ == '__main__':
    debug = os.getenv("DEEPR_DEBUG", "").lower() in ("1", "true", "yes")
    host = os.getenv("DEEPR_HOST", "127.0.0.1")
    port = int(os.getenv("DEEPR_PORT", "5000"))
    print("\n" + "="*70)
    print(f"  Deepr API Server")
    print(f"  Running on http://{host}:{port}")
    if debug:
        print("  WARNING: Debug mode enabled -- do not use in production")
    print("="*70 + "\n")
    app.run(debug=debug, host=host, port=port)
