"""
Azure Functions app for Deepr API.

Handles job submission, status, and results via HTTP triggers.
"""

import azure.functions as func
import json
import os
import uuid
import logging
from datetime import datetime, timezone

from azure.storage.queue import QueueClient
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

app = func.FunctionApp()

# Configuration
STORAGE_CONNECTION = os.environ.get('STORAGE_CONNECTION_STRING')
QUEUE_NAME = os.environ.get('QUEUE_NAME', 'deepr-jobs')
RESULTS_CONTAINER = os.environ.get('RESULTS_CONTAINER', 'results')
KEY_VAULT_URI = os.environ.get('KEY_VAULT_URI')

# Initialize clients
queue_client = QueueClient.from_connection_string(STORAGE_CONNECTION, QUEUE_NAME)
blob_service = BlobServiceClient.from_connection_string(STORAGE_CONNECTION)
results_container = blob_service.get_container_client(RESULTS_CONTAINER)

# Secrets cache
_secrets_cache = {}


def get_secret(name: str) -> str:
    """Get secret from Key Vault (cached)."""
    if name not in _secrets_cache:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=KEY_VAULT_URI, credential=credential)
        _secrets_cache[name] = client.get_secret(name).value
    return _secrets_cache[name]


def response(status_code: int, body: dict) -> func.HttpResponse:
    """Create HTTP response."""
    return func.HttpResponse(
        json.dumps(body),
        status_code=status_code,
        mimetype='application/json',
        headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization'
        }
    )


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint."""
    return response(200, {'status': 'healthy', 'service': 'deepr-api'})


@app.route(route="jobs", methods=["POST"])
def submit_job(req: func.HttpRequest) -> func.HttpResponse:
    """Submit a new research job."""
    try:
        body = req.get_json()
    except ValueError:
        return response(400, {'error': 'Invalid JSON'})

    prompt = body.get('prompt')
    if not prompt:
        return response(400, {'error': 'Prompt required'})

    job_id = str(uuid.uuid4())
    model = body.get('model', 'o4-mini-deep-research')
    priority = body.get('priority', 3)
    enable_web_search = body.get('enable_web_search', True)

    job = {
        'id': job_id,
        'prompt': prompt,
        'model': model,
        'priority': priority,
        'enable_web_search': enable_web_search,
        'status': 'queued',
        'submitted_at': datetime.now(timezone.utc).isoformat(),
        'metadata': body.get('metadata', {})
    }

    # Send to queue
    queue_client.send_message(json.dumps(job))

    # Store metadata in blob
    metadata_blob = results_container.get_blob_client(f'jobs/{job_id}/metadata.json')
    metadata_blob.upload_blob(json.dumps(job), overwrite=True)

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


@app.route(route="jobs", methods=["GET"])
def list_jobs(req: func.HttpRequest) -> func.HttpResponse:
    """List all jobs."""
    limit = int(req.params.get('limit', 100))
    status_filter = req.params.get('status')

    jobs = []
    blobs = results_container.list_blobs(name_starts_with='jobs/')

    for blob in blobs:
        if not blob.name.endswith('metadata.json'):
            continue

        try:
            blob_client = results_container.get_blob_client(blob.name)
            data = blob_client.download_blob().readall()
            job = json.loads(data)

            if status_filter and job.get('status') != status_filter:
                continue

            jobs.append(job)

            if len(jobs) >= limit:
                break
        except Exception as e:
            logging.warning(f"Failed to read job metadata: {e}")
            continue

    # Sort by submission time
    jobs.sort(key=lambda j: j.get('submitted_at', ''), reverse=True)

    return response(200, {'jobs': jobs[:limit], 'total': len(jobs)})


@app.route(route="jobs/{job_id}", methods=["GET"])
def get_job(req: func.HttpRequest) -> func.HttpResponse:
    """Get job details."""
    job_id = req.route_params.get('job_id')

    try:
        blob_client = results_container.get_blob_client(f'jobs/{job_id}/metadata.json')
        data = blob_client.download_blob().readall()
        job = json.loads(data)
        return response(200, {'job': job})
    except Exception:
        return response(404, {'error': 'Job not found'})


@app.route(route="jobs/{job_id}/cancel", methods=["POST"])
def cancel_job(req: func.HttpRequest) -> func.HttpResponse:
    """Cancel a job."""
    job_id = req.route_params.get('job_id')

    try:
        blob_client = results_container.get_blob_client(f'jobs/{job_id}/metadata.json')
        data = blob_client.download_blob().readall()
        job = json.loads(data)

        if job.get('status') in ['completed', 'failed', 'cancelled']:
            return response(400, {'error': f"Cannot cancel job in {job['status']} state"})

        job['status'] = 'cancelled'
        job['cancelled_at'] = datetime.now(timezone.utc).isoformat()

        blob_client.upload_blob(json.dumps(job), overwrite=True)

        return response(200, {'success': True})
    except Exception:
        return response(404, {'error': 'Job not found'})


@app.route(route="results/{job_id}", methods=["GET"])
def get_result(req: func.HttpRequest) -> func.HttpResponse:
    """Get job result."""
    job_id = req.route_params.get('job_id')

    try:
        # Check status
        metadata_blob = results_container.get_blob_client(f'jobs/{job_id}/metadata.json')
        job = json.loads(metadata_blob.download_blob().readall())

        if job.get('status') != 'completed':
            return response(400, {'error': 'Job not completed yet'})

        # Get report
        report_blob = results_container.get_blob_client(f'jobs/{job_id}/report.md')
        content = report_blob.download_blob().readall().decode('utf-8')

        return response(200, {
            'job_id': job_id,
            'content': content,
            'format': 'markdown'
        })
    except Exception:
        return response(404, {'error': 'Job or result not found'})


@app.route(route="costs", methods=["GET"])
def get_costs(req: func.HttpRequest) -> func.HttpResponse:
    """Get cost summary."""
    total_cost = 0
    job_count = 0
    completed_count = 0

    blobs = results_container.list_blobs(name_starts_with='jobs/')

    for blob in blobs:
        if not blob.name.endswith('metadata.json'):
            continue

        try:
            blob_client = results_container.get_blob_client(blob.name)
            data = blob_client.download_blob().readall()
            job = json.loads(data)

            job_count += 1
            if job.get('status') == 'completed':
                completed_count += 1
                total_cost += job.get('cost', 0)
        except Exception:
            continue

    return response(200, {
        'daily': total_cost,
        'monthly': total_cost,
        'total': total_cost,
        'daily_limit': float(os.environ.get('DEEPR_BUDGET_DAILY', 50)),
        'monthly_limit': float(os.environ.get('DEEPR_BUDGET_MONTHLY', 500)),
        'total_jobs': job_count,
        'completed_jobs': completed_count,
        'avg_cost_per_job': total_cost / completed_count if completed_count else 0,
        'currency': 'USD'
    })
