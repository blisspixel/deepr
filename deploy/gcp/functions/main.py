"""
Google Cloud Functions handler for Deepr API (Security Hardened).

Routes HTTP requests to job submission, status, and results endpoints.
Uses Firestore for job metadata (O(1) lookups) and Cloud Storage for results.
"""

import json
import logging
import os
import re
import uuid
import functions_framework
from datetime import datetime, timezone
from typing import Any

from google.cloud import pubsub_v1
from google.cloud import storage
from google.cloud import firestore

# Configure logging
logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.environ.get('PROJECT_ID')
PUBSUB_TOPIC = os.environ.get('PUBSUB_TOPIC')
RESULTS_BUCKET = os.environ.get('RESULTS_BUCKET')
FIRESTORE_DB = os.environ.get('FIRESTORE_DB', '(default)')
DAILY_BUDGET = float(os.environ.get('DAILY_BUDGET', 50))
MONTHLY_BUDGET = float(os.environ.get('MONTHLY_BUDGET', 500))
API_KEY = os.environ.get('API_KEY', '')

# Initialize clients
publisher = pubsub_v1.PublisherClient()
storage_client = storage.Client()
bucket = storage_client.bucket(RESULTS_BUCKET)
db = firestore.Client(database=FIRESTORE_DB)

# Collections
JOBS_COLLECTION = 'jobs'

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

# Route patterns for robust path matching
JOB_ID_PATTERN = re.compile(r'^jobs/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$')
JOB_CANCEL_PATTERN = re.compile(r'^jobs/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/cancel$')
RESULT_PATTERN = re.compile(r'^results/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$')

# TTL configuration
DEFAULT_TTL_DAYS = 90


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


def validate_api_key(request) -> bool:
    """Validate API key from request headers."""
    if not API_KEY:
        return True  # No API key configured, allow all

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        return token == API_KEY

    api_key_header = request.headers.get('X-Api-Key', '')
    return api_key_header == API_KEY


def response(status_code: int, body: dict):
    """Create HTTP response with security headers."""
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Api-Key',
        # Security headers
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Cache-Control': 'no-store, no-cache, must-revalidate',
        'Pragma': 'no-cache'
    }
    return (json.dumps(body), status_code, headers)


@functions_framework.http
def handle_request(request):
    """Main HTTP handler - routes to appropriate function."""
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return ('', 204, {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Api-Key',
            'Access-Control-Max-Age': '3600'
        })

    path = request.path.strip('/')
    method = request.method

    # Log request (without sensitive data)
    logger.info(f"Request: {method} /{path}")

    # Health check (no auth required)
    if path == 'health':
        return response(200, {
            'status': 'healthy',
            'service': 'deepr-api',
            'version': '2.6.0'
        })

    # Validate API key for all other endpoints
    if not validate_api_key(request):
        logger.warning(f"Unauthorized access attempt from {request.remote_addr}")
        return response(401, {'error': 'Unauthorized'})

    try:
        # Route requests using regex for robust path matching
        if path == 'jobs' and method == 'POST':
            return submit_job(request)
        elif path == 'jobs' and method == 'GET':
            return list_jobs(request)
        elif method == 'POST':
            match = JOB_CANCEL_PATTERN.match(path)
            if match:
                return cancel_job(match.group(1))
        elif method == 'GET':
            match = JOB_ID_PATTERN.match(path)
            if match:
                return get_job(match.group(1))
            match = RESULT_PATTERN.match(path)
            if match:
                return get_result(match.group(1))
            if path == 'costs':
                return get_costs()

        return response(404, {'error': 'Not found'})

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return response(500, {'error': 'Internal server error'})


def submit_job(request):
    """Submit a new research job to Pub/Sub."""
    try:
        body = request.get_json()
    except Exception:
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
    now = datetime.now(timezone.utc)
    submitted_at = now.isoformat()

    # Calculate TTL (90 days from now) for automatic cleanup
    ttl = int(now.timestamp()) + (DEFAULT_TTL_DAYS * 24 * 60 * 60)

    job = {
        'job_id': job_id,
        'prompt': prompt,
        'model': model,
        'priority': priority,
        'enable_web_search': enable_web_search,
        'status': 'queued',
        'submitted_at': submitted_at,
        'metadata': metadata,
        'user_id': 'anonymous',  # Would come from auth token in production
        'ttl': ttl  # Firestore TTL for automatic document expiration
    }

    # Store job metadata in Firestore
    db.collection(JOBS_COLLECTION).document(job_id).set(job)

    # Publish to Pub/Sub
    topic_path = publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)
    message_data = json.dumps({
        'id': job_id,
        'prompt': prompt,
        'model': model,
        'priority': priority,
        'enable_web_search': enable_web_search,
        'submitted_at': submitted_at,
        'metadata': metadata
    }).encode('utf-8')
    publisher.publish(topic_path, message_data)

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


def list_jobs(request):
    """List jobs from Firestore with efficient queries."""
    args = request.args

    # Validate and sanitize parameters
    try:
        limit = min(int(args.get('limit', 100)), 1000)
    except ValueError:
        return response(400, {'error': 'Invalid limit parameter'})

    status_filter = args.get('status')
    if status_filter:
        status_filter = sanitize_string(status_filter, 20)
        valid_statuses = ['queued', 'running', 'completed', 'failed', 'cancelled']
        if status_filter not in valid_statuses:
            return response(400, {'error': f'Invalid status. Valid options: {", ".join(valid_statuses)}'})

    jobs = []

    # Query Firestore
    query = db.collection(JOBS_COLLECTION)

    if status_filter:
        query = query.where('status', '==', status_filter)

    query = query.order_by('submitted_at', direction=firestore.Query.DESCENDING)
    query = query.limit(limit)

    docs = query.stream()

    for doc in docs:
        job = doc.to_dict()
        # Convert job_id to id for API consistency
        job['id'] = job.pop('job_id', doc.id)
        jobs.append(job)

    return response(200, {'jobs': jobs, 'total': len(jobs)})


def get_job(job_id: str):
    """Get job details from Firestore."""
    if not validate_job_id(job_id):
        return response(400, {'error': 'Invalid job ID format'})

    doc = db.collection(JOBS_COLLECTION).document(job_id).get()

    if not doc.exists:
        return response(404, {'error': 'Job not found'})

    job = doc.to_dict()
    job['id'] = job.pop('job_id', doc.id)

    return response(200, {'job': job})


def cancel_job(job_id: str):
    """Cancel a job by updating its status in Firestore."""
    if not validate_job_id(job_id):
        return response(400, {'error': 'Invalid job ID format'})

    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    doc = doc_ref.get()

    if not doc.exists:
        return response(404, {'error': 'Job not found'})

    job = doc.to_dict()

    if job.get('status') in ['completed', 'failed', 'cancelled']:
        return response(400, {'error': f"Cannot cancel job in {job['status']} state"})

    doc_ref.update({
        'status': 'cancelled',
        'cancelled_at': datetime.now(timezone.utc).isoformat()
    })

    logger.info(f"Job cancelled: {job_id}")
    return response(200, {'success': True})


def get_result(job_id: str):
    """Get research result from Cloud Storage."""
    if not validate_job_id(job_id):
        return response(400, {'error': 'Invalid job ID format'})

    # Check job status in Firestore
    doc = db.collection(JOBS_COLLECTION).document(job_id).get()

    if not doc.exists:
        return response(404, {'error': 'Job not found'})

    job = doc.to_dict()

    if job.get('status') != 'completed':
        return response(400, {
            'error': 'Job not completed yet',
            'status': job.get('status')
        })

    try:
        # Get report from Cloud Storage
        blob = bucket.blob(f'results/{job_id}/report.md')
        content = blob.download_as_text()

        return response(200, {
            'job_id': job_id,
            'content': content,
            'format': 'markdown',
            'completed_at': job.get('completed_at')
        })
    except Exception:
        return response(404, {'error': 'Result not found'})


def get_costs():
    """Get cost summary from Firestore using efficient aggregation queries."""
    jobs_ref = db.collection(JOBS_COLLECTION)

    # Use Firestore aggregation for efficient counting (no document reads)
    total_jobs_agg = jobs_ref.count()
    total_jobs_result = total_jobs_agg.get()
    total_jobs = total_jobs_result[0][0].value if total_jobs_result else 0

    # Count completed jobs efficiently
    completed_query = jobs_ref.where('status', '==', 'completed')
    completed_count_agg = completed_query.count()
    completed_count_result = completed_count_agg.get()
    completed_count = completed_count_result[0][0].value if completed_count_result else 0

    # For cost sum, we still need to read documents (Firestore doesn't support SUM aggregation)
    # But we use projection to minimize data transfer
    total_cost = 0
    if completed_count > 0:
        completed_docs = completed_query.select(['cost']).stream()
        for doc in completed_docs:
            job = doc.to_dict()
            total_cost += job.get('cost', 0)

    return response(200, {
        'daily': total_cost,  # Simplified - would need date filtering in production
        'monthly': total_cost,
        'total': total_cost,
        'daily_limit': DAILY_BUDGET,
        'monthly_limit': MONTHLY_BUDGET,
        'total_jobs': total_jobs,
        'completed_jobs': completed_count,
        'avg_cost_per_job': total_cost / completed_count if completed_count else 0,
        'currency': 'USD'
    })
