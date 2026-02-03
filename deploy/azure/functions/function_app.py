"""
Azure Functions handler for Deepr API (Security Hardened).

Routes HTTP requests to job submission, status, and results endpoints.
Uses Cosmos DB for job metadata (O(1) lookups) and Blob Storage for results.
"""

import azure.functions as func
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.cosmos import CosmosClient
from azure.storage.blob import BlobServiceClient
from azure.storage.queue import QueueClient

# Configure logging
logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Configuration
STORAGE_ACCOUNT_NAME = os.environ.get('STORAGE_ACCOUNT_NAME')
QUEUE_NAME = os.environ.get('QUEUE_NAME', 'deepr-jobs')
RESULTS_CONTAINER = os.environ.get('RESULTS_CONTAINER', 'results')
KEY_VAULT_URI = os.environ.get('KEY_VAULT_URI')
COSMOS_ENDPOINT = os.environ.get('COSMOS_ENDPOINT')
COSMOS_DATABASE = os.environ.get('COSMOS_DATABASE', 'deepr')
DAILY_BUDGET = float(os.environ.get('DEEPR_BUDGET_DAILY', 50))
MONTHLY_BUDGET = float(os.environ.get('DEEPR_BUDGET_MONTHLY', 500))

# Initialize Azure clients with managed identity
credential = DefaultAzureCredential()

# Cosmos DB client
cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=credential)
database = cosmos_client.get_database_client(COSMOS_DATABASE)
jobs_container = database.get_container_client('jobs')

# Blob Storage client
blob_service = BlobServiceClient(
    account_url=f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
    credential=credential
)
results_container_client = blob_service.get_container_client(RESULTS_CONTAINER)

# Queue client
queue_client = QueueClient(
    account_url=f"https://{STORAGE_ACCOUNT_NAME}.queue.core.windows.net",
    queue_name=QUEUE_NAME,
    credential=credential
)

# Key Vault client for secrets
kv_client = SecretClient(vault_url=KEY_VAULT_URI, credential=credential)

# Cached API key
_api_key_cache = None

# Input validation constants
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
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


def get_api_key() -> str:
    """Retrieve API key from Key Vault (cached)."""
    global _api_key_cache
    if _api_key_cache is None:
        try:
            secret = kv_client.get_secret('deepr-api-key')
            _api_key_cache = secret.value
        except Exception:
            _api_key_cache = ''
    return _api_key_cache


def validate_job_id(job_id: str) -> bool:
    """Validate job ID is a valid UUID."""
    if not job_id:
        return False
    return bool(UUID_PATTERN.match(job_id.lower()))


def sanitize_string(value: str, max_length: int = 1000) -> str:
    """Sanitize string input."""
    if not isinstance(value, str):
        return ''
    return value[:max_length].strip()


def validate_api_key(req: func.HttpRequest) -> bool:
    """Validate API key from request headers."""
    api_key = get_api_key()
    if not api_key:
        return True  # No API key configured, allow all

    auth_header = req.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        return token == api_key

    api_key_header = req.headers.get('X-Api-Key', '')
    return api_key_header == api_key


def response(status_code: int, body: dict) -> func.HttpResponse:
    """Create HTTP response with security headers."""
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Api-Key',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Cache-Control': 'no-store, no-cache, must-revalidate',
        'Pragma': 'no-cache'
    }
    return func.HttpResponse(
        json.dumps(body),
        status_code=status_code,
        headers=headers
    )


def cors_preflight_response() -> func.HttpResponse:
    """Return CORS preflight response."""
    return func.HttpResponse(
        '',
        status_code=204,
        headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Api-Key',
            'Access-Control-Max-Age': '3600'
        }
    )


@app.route(route="health", methods=["GET", "OPTIONS"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint (no auth required)."""
    if req.method == 'OPTIONS':
        return cors_preflight_response()
    return response(200, {
        'status': 'healthy',
        'service': 'deepr-api',
        'version': '2.6.0'
    })


@app.route(route="jobs", methods=["GET", "POST", "OPTIONS"])
def jobs_handler(req: func.HttpRequest) -> func.HttpResponse:
    """Handle jobs collection endpoints."""
    if req.method == 'OPTIONS':
        return cors_preflight_response()
    elif req.method == 'POST':
        return submit_job(req)
    else:
        return list_jobs(req)


def submit_job(req: func.HttpRequest) -> func.HttpResponse:
    """Submit a new research job."""
    if not validate_api_key(req):
        logger.warning(f"Unauthorized access attempt from {req.headers.get('X-Forwarded-For', 'unknown')}")
        return response(401, {'error': 'Unauthorized'})

    try:
        body = req.get_json()
    except ValueError:
        return response(400, {'error': 'Invalid JSON'})

    # Validate prompt
    prompt = body.get('prompt')
    if not prompt:
        return response(400, {'error': 'Prompt required'})
    if not isinstance(prompt, str):
        return response(400, {'error': 'Prompt must be a string'})
    if len(prompt) > MAX_PROMPT_LENGTH:
        return response(400, {'error': f'Prompt exceeds maximum length of {MAX_PROMPT_LENGTH}'})

    prompt = sanitize_string(prompt, MAX_PROMPT_LENGTH)

    # Validate model
    model = body.get('model', 'o4-mini-deep-research')
    if model not in VALID_MODELS:
        return response(400, {'error': f'Invalid model. Valid options: {", ".join(VALID_MODELS)}'})

    # Validate priority
    priority = body.get('priority', 3)
    if not isinstance(priority, int) or priority < 1 or priority > 5:
        return response(400, {'error': 'Priority must be an integer between 1 and 5'})

    # Validate web search flag
    enable_web_search = body.get('enable_web_search', True)
    if not isinstance(enable_web_search, bool):
        return response(400, {'error': 'enable_web_search must be a boolean'})

    # Validate metadata
    metadata = body.get('metadata', {})
    if not isinstance(metadata, dict):
        return response(400, {'error': 'Metadata must be an object'})
    if len(json.dumps(metadata)) > MAX_METADATA_SIZE:
        return response(400, {'error': f'Metadata exceeds maximum size of {MAX_METADATA_SIZE} bytes'})

    job_id = str(uuid.uuid4())
    submitted_at = datetime.now(timezone.utc).isoformat()

    # Calculate TTL (90 days from now in Unix timestamp)
    ttl = int(datetime.now(timezone.utc).timestamp()) + (90 * 24 * 60 * 60)

    job = {
        'id': job_id,  # Cosmos DB partition key - no separate job_id needed
        'prompt': prompt,
        'model': model,
        'priority': priority,
        'enable_web_search': enable_web_search,
        'status': 'queued',
        'submitted_at': submitted_at,
        'metadata': metadata,
        'user_id': 'anonymous',
        'ttl': ttl
    }

    # Store job metadata in Cosmos DB
    jobs_container.create_item(body=job)

    # Send to Queue
    queue_message = json.dumps({
        'id': job_id,
        'prompt': prompt,
        'model': model,
        'priority': priority,
        'enable_web_search': enable_web_search,
        'submitted_at': submitted_at,
        'metadata': metadata
    })
    queue_client.send_message(queue_message)

    logger.info(f"Job submitted: {job_id}")

    # Cost estimate
    avg_cost = 0.5 if 'mini' in model else 5.0
    estimated_cost = {
        'min_cost': avg_cost * 0.5,
        'max_cost': avg_cost * 2.0,
        'estimated_cost': avg_cost,
        'currency': 'USD'
    }

    return response(200, {
        'job': {
            'id': job_id,
            'prompt': prompt,
            'model': model,
            'status': 'queued'
        },
        'estimated_cost': estimated_cost
    })


def list_jobs(req: func.HttpRequest) -> func.HttpResponse:
    """List jobs from Cosmos DB."""
    if not validate_api_key(req):
        return response(401, {'error': 'Unauthorized'})

    # Validate and sanitize parameters
    try:
        limit = min(int(req.params.get('limit', 100)), 1000)
    except ValueError:
        return response(400, {'error': 'Invalid limit parameter'})

    status_filter = req.params.get('status')
    if status_filter:
        status_filter = sanitize_string(status_filter, 20)
        valid_statuses = ['queued', 'running', 'completed', 'failed', 'cancelled']
        if status_filter not in valid_statuses:
            return response(400, {'error': f'Invalid status. Valid options: {", ".join(valid_statuses)}'})

    # Query Cosmos DB
    if status_filter:
        query = f"SELECT * FROM c WHERE c.status = @status ORDER BY c.submitted_at DESC OFFSET 0 LIMIT @limit"
        parameters = [
            {'name': '@status', 'value': status_filter},
            {'name': '@limit', 'value': limit}
        ]
    else:
        query = "SELECT * FROM c ORDER BY c.submitted_at DESC OFFSET 0 LIMIT @limit"
        parameters = [{'name': '@limit', 'value': limit}]

    items = list(jobs_container.query_items(query=query, parameters=parameters, enable_cross_partition_query=True))

    # Items already have 'id' field - no conversion needed
    jobs = [dict(item) for item in items]

    return response(200, {'jobs': jobs, 'total': len(jobs)})


@app.route(route="jobs/{job_id}", methods=["GET", "OPTIONS"])
def get_job(req: func.HttpRequest) -> func.HttpResponse:
    """Get job details from Cosmos DB."""
    if req.method == 'OPTIONS':
        return cors_preflight_response()

    if not validate_api_key(req):
        return response(401, {'error': 'Unauthorized'})

    job_id = req.route_params.get('job_id')
    if not validate_job_id(job_id):
        return response(400, {'error': 'Invalid job ID format'})

    try:
        job = jobs_container.read_item(item=job_id, partition_key=job_id)
        return response(200, {'job': dict(job)})
    except Exception:
        return response(404, {'error': 'Job not found'})


@app.route(route="jobs/{job_id}/cancel", methods=["POST", "OPTIONS"])
def cancel_job(req: func.HttpRequest) -> func.HttpResponse:
    """Cancel a job by updating its status."""
    if req.method == 'OPTIONS':
        return cors_preflight_response()

    if not validate_api_key(req):
        return response(401, {'error': 'Unauthorized'})

    job_id = req.route_params.get('job_id')
    if not validate_job_id(job_id):
        return response(400, {'error': 'Invalid job ID format'})

    try:
        job = jobs_container.read_item(item=job_id, partition_key=job_id)
    except Exception:
        return response(404, {'error': 'Job not found'})

    if job.get('status') in ['completed', 'failed', 'cancelled']:
        return response(400, {'error': f"Cannot cancel job in {job['status']} state"})

    job['status'] = 'cancelled'
    job['cancelled_at'] = datetime.now(timezone.utc).isoformat()
    jobs_container.replace_item(item=job_id, body=job)

    logger.info(f"Job cancelled: {job_id}")
    return response(200, {'success': True})


@app.route(route="results/{job_id}", methods=["GET", "OPTIONS"])
def get_result(req: func.HttpRequest) -> func.HttpResponse:
    """Get research result from Blob Storage."""
    if req.method == 'OPTIONS':
        return cors_preflight_response()

    if not validate_api_key(req):
        return response(401, {'error': 'Unauthorized'})

    job_id = req.route_params.get('job_id')
    if not validate_job_id(job_id):
        return response(400, {'error': 'Invalid job ID format'})

    # Check job status in Cosmos DB
    try:
        job = jobs_container.read_item(item=job_id, partition_key=job_id)
    except Exception:
        return response(404, {'error': 'Job not found'})

    if job.get('status') != 'completed':
        return response(400, {
            'error': 'Job not completed yet',
            'status': job.get('status')
        })

    try:
        blob_client = results_container_client.get_blob_client(f'{job_id}/report.md')
        content = blob_client.download_blob().readall().decode('utf-8')

        return response(200, {
            'job_id': job_id,
            'content': content,
            'format': 'markdown',
            'completed_at': job.get('completed_at')
        })
    except Exception:
        return response(404, {'error': 'Result not found'})


@app.route(route="costs", methods=["GET", "OPTIONS"])
def get_costs(req: func.HttpRequest) -> func.HttpResponse:
    """Get cost summary from Cosmos DB."""
    if req.method == 'OPTIONS':
        return cors_preflight_response()

    if not validate_api_key(req):
        return response(401, {'error': 'Unauthorized'})

    # Query completed jobs
    query = "SELECT c.id, c.cost FROM c WHERE c.status = 'completed'"
    completed_items = list(jobs_container.query_items(query=query, enable_cross_partition_query=True))

    total_cost = sum(float(item.get('cost', 0)) for item in completed_items)
    completed_count = len(completed_items)

    # Get total job count
    count_query = "SELECT VALUE COUNT(1) FROM c"
    total_jobs = list(jobs_container.query_items(query=count_query, enable_cross_partition_query=True))[0]

    return response(200, {
        'daily': total_cost,
        'monthly': total_cost,
        'total': total_cost,
        'daily_limit': DAILY_BUDGET,
        'monthly_limit': MONTHLY_BUDGET,
        'total_jobs': total_jobs,
        'completed_jobs': completed_count,
        'avg_cost_per_job': total_cost / completed_count if completed_count else 0,
        'currency': 'USD'
    })
