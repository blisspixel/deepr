"""
AWS Lambda handler for Deepr API.

Routes requests to job submission, status, and results endpoints.
Uses DynamoDB for job metadata (O(1) lookups) and S3 for results storage.
"""

import json
import logging
import os
import re
import uuid
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Initialize AWS clients
sqs = boto3.client('sqs')
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
secrets = boto3.client('secretsmanager')

QUEUE_URL = os.environ.get('QUEUE_URL')
RESULTS_BUCKET = os.environ.get('RESULTS_BUCKET')
JOBS_TABLE = os.environ.get('JOBS_TABLE')
SECRETS_ARN = os.environ.get('SECRETS_ARN')

# Initialize DynamoDB table
jobs_table = dynamodb.Table(JOBS_TABLE) if JOBS_TABLE else None

# Cache for secrets
_secrets_cache = None

# CORS headers for preflight responses
CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key,Authorization',
    'Access-Control-Max-Age': '3600',
}

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


def get_secrets() -> dict:
    """Retrieve API keys from Secrets Manager (cached)."""
    global _secrets_cache
    if _secrets_cache is None:
        response = secrets.get_secret_value(SecretId=SECRETS_ARN)
        _secrets_cache = json.loads(response['SecretString'])
    return _secrets_cache


def validate_api_key(event: dict) -> bool:
    """Validate API key from request headers."""
    secrets_data = get_secrets()
    expected_key = secrets_data.get('DEEPR_API_KEY', '')

    if not expected_key:
        return True  # No key configured, allow all

    headers = event.get('headers', {}) or {}
    # Headers may be case-insensitive depending on API Gateway config
    auth_header = headers.get('Authorization', headers.get('authorization', ''))
    api_key_header = headers.get('X-Api-Key', headers.get('x-api-key', ''))

    # Check Bearer token
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header[7:]
        if token == expected_key:
            return True

    # Check X-Api-Key header
    if api_key_header == expected_key:
        return True

    return False


def validate_job_id(job_id: str) -> bool:
    """Validate job ID is a valid UUID."""
    if not job_id:
        return False
    return bool(UUID_PATTERN.match(job_id.lower()))


def sanitize_string(value: str, max_length: int = 1000) -> str:
    """Sanitize string input."""
    if not isinstance(value, str):
        return ''
    # Truncate and strip
    return value[:max_length].strip()


def decimal_default(obj: Any) -> Any:
    """JSON encoder for Decimal types from DynamoDB."""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def lambda_handler(event: dict, context) -> dict:
    """Main Lambda handler - routes to appropriate function."""
    http_method = event.get('httpMethod', '')
    path = event.get('path', '')
    path_params = event.get('pathParameters') or {}

    # Log request (without sensitive data)
    logger.info(f"Request: {http_method} {path}")

    # Handle CORS preflight
    if http_method == 'OPTIONS':
        return {
            'statusCode': 204,
            'headers': CORS_HEADERS,
            'body': ''
        }

    # Health check (no auth required)
    if path == '/health':
        return response(200, {
            'status': 'healthy',
            'service': 'deepr-api',
            'version': '2.6.0'
        })

    # Validate API key for all protected endpoints
    if not validate_api_key(event):
        logger.warning("Unauthorized access attempt")
        return response(401, {'error': 'Unauthorized'})

    # Route requests
    try:
        if path == '/jobs' and http_method == 'POST':
            return submit_job(event)
        elif path == '/jobs' and http_method == 'GET':
            return list_jobs(event)
        elif path.startswith('/jobs/') and path.endswith('/cancel') and http_method == 'POST':
            job_id = path_params.get('job_id')
            return cancel_job(job_id)
        elif path.startswith('/jobs/') and http_method == 'GET':
            job_id = path_params.get('job_id')
            return get_job(job_id)
        elif path.startswith('/results/') and http_method == 'GET':
            job_id = path_params.get('job_id')
            return get_result(job_id)
        elif path == '/costs' and http_method == 'GET':
            return get_costs()

        return response(404, {'error': 'Not found'})

    except ClientError as e:
        logger.error(f"AWS error: {e}")
        return response(500, {'error': 'Internal server error'})
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return response(500, {'error': 'Internal server error'})


def submit_job(event: dict) -> dict:
    """Submit a new research job to the queue."""
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
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

    # Calculate TTL (90 days from now)
    ttl = int(now.timestamp()) + (90 * 24 * 60 * 60)

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
        'ttl': ttl
    }

    # Store job metadata in DynamoDB
    jobs_table.put_item(Item=job)

    # Send to SQS
    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({
            'id': job_id,
            'prompt': prompt,
            'model': model,
            'priority': priority,
            'enable_web_search': enable_web_search,
            'submitted_at': submitted_at,
            'metadata': metadata
        }),
        MessageAttributes={
            'Priority': {
                'DataType': 'Number',
                'StringValue': str(priority)
            }
        }
    )

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


def list_jobs(event: dict) -> dict:
    """List jobs from DynamoDB with efficient queries."""
    query_params = event.get('queryStringParameters') or {}

    # Validate and sanitize parameters
    try:
        limit = min(int(query_params.get('limit', 100)), 1000)
    except ValueError:
        return response(400, {'error': 'Invalid limit parameter'})

    status_filter = query_params.get('status')
    if status_filter:
        status_filter = sanitize_string(status_filter, 20)
        valid_statuses = ['queued', 'running', 'completed', 'failed', 'cancelled']
        if status_filter not in valid_statuses:
            return response(400, {'error': f'Invalid status. Valid options: {", ".join(valid_statuses)}'})

    jobs = []

    if status_filter:
        # Use GSI for efficient status query
        result = jobs_table.query(
            IndexName='status-submitted-index',
            KeyConditionExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': status_filter},
            ScanIndexForward=False,  # Newest first
            Limit=limit
        )
        jobs = result.get('Items', [])
    else:
        # Scan with limit (for all jobs)
        result = jobs_table.scan(Limit=limit)
        jobs = result.get('Items', [])
        # Sort by submission time
        jobs.sort(key=lambda j: j.get('submitted_at', ''), reverse=True)

    # Convert job_id to id for API consistency
    for job in jobs:
        job['id'] = job.pop('job_id', job.get('id'))

    return response(200, {'jobs': jobs[:limit], 'total': len(jobs)})


def get_job(job_id: str) -> dict:
    """Get job details from DynamoDB."""
    if not validate_job_id(job_id):
        return response(400, {'error': 'Invalid job ID format'})

    result = jobs_table.get_item(Key={'job_id': job_id})
    job = result.get('Item')

    if not job:
        return response(404, {'error': 'Job not found'})

    # Convert job_id to id for API consistency
    job['id'] = job.pop('job_id')

    return response(200, {'job': job})


def cancel_job(job_id: str) -> dict:
    """Cancel a job by updating its status in DynamoDB."""
    if not validate_job_id(job_id):
        return response(400, {'error': 'Invalid job ID format'})

    try:
        # Conditional update - only if job is in cancellable state
        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET #status = :cancelled, cancelled_at = :now',
            ConditionExpression='#status IN (:queued, :running)',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':cancelled': 'cancelled',
                ':queued': 'queued',
                ':running': 'running',
                ':now': datetime.now(timezone.utc).isoformat()
            }
        )
        logger.info(f"Job cancelled: {job_id}")
        return response(200, {'success': True})

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            # Job either doesn't exist or is in non-cancellable state
            result = jobs_table.get_item(Key={'job_id': job_id})
            job = result.get('Item')
            if not job:
                return response(404, {'error': 'Job not found'})
            return response(400, {'error': f"Cannot cancel job in {job['status']} state"})
        raise


def get_result(job_id: str) -> dict:
    """Get research result from S3."""
    if not validate_job_id(job_id):
        return response(400, {'error': 'Invalid job ID format'})

    # Check job status in DynamoDB
    result = jobs_table.get_item(Key={'job_id': job_id})
    job = result.get('Item')

    if not job:
        return response(404, {'error': 'Job not found'})

    if job.get('status') != 'completed':
        return response(400, {
            'error': 'Job not completed yet',
            'status': job.get('status')
        })

    try:
        # Get report from S3
        report = s3.get_object(
            Bucket=RESULTS_BUCKET,
            Key=f'results/{job_id}/report.md'
        )
        content = report['Body'].read().decode('utf-8')

        return response(200, {
            'job_id': job_id,
            'content': content,
            'format': 'markdown',
            'completed_at': job.get('completed_at')
        })
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return response(404, {'error': 'Result not found'})
        raise


def get_costs() -> dict:
    """Get cost summary from DynamoDB (efficient aggregation)."""
    # Query completed jobs for cost calculation
    result = jobs_table.query(
        IndexName='status-submitted-index',
        KeyConditionExpression='#status = :completed',
        ExpressionAttributeNames={'#status': 'status'},
        ExpressionAttributeValues={':completed': 'completed'},
        ProjectionExpression='job_id, cost'
    )

    completed_jobs = result.get('Items', [])
    total_cost = sum(float(job.get('cost', 0)) for job in completed_jobs)
    completed_count = len(completed_jobs)

    # Get total job count (scan with count only)
    count_result = jobs_table.scan(Select='COUNT')
    total_jobs = count_result.get('Count', 0)

    secrets_data = get_secrets()

    return response(200, {
        'daily': total_cost,  # Simplified - would need date filtering in production
        'monthly': total_cost,
        'total': total_cost,
        'daily_limit': float(secrets_data.get('DEEPR_BUDGET_DAILY', 50)),
        'monthly_limit': float(secrets_data.get('DEEPR_BUDGET_MONTHLY', 500)),
        'total_jobs': total_jobs,
        'completed_jobs': completed_count,
        'avg_cost_per_job': total_cost / completed_count if completed_count else 0,
        'currency': 'USD'
    })


def response(status_code: int, body: dict) -> dict:
    """Create API Gateway response with security headers."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
            # Security headers
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Cache-Control': 'no-store, no-cache, must-revalidate',
            'Pragma': 'no-cache'
        },
        'body': json.dumps(body, default=decimal_default)
    }
