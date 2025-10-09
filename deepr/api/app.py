"""
Flask API for Deepr - matches React frontend API expectations.
"""

import os
import asyncio
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"])

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
def list_jobs():
    """List all jobs with filtering."""
    try:
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

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    """Get specific job details."""
    try:
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

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs', methods=['POST'])
def submit_job():
    """Submit a new research job."""
    try:
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

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id):
    """Cancel a job."""
    try:
        success = run_async(queue.cancel_job(job_id))
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>', methods=['DELETE'])
def delete_job(job_id):
    """Delete a job."""
    try:
        # For now, just cancel it
        success = run_async(queue.cancel_job(job_id))
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/stats', methods=['GET'])
def get_stats():
    """Get queue statistics."""
    try:
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

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/results/<job_id>', methods=['GET'])
def get_result(job_id):
    """Get job result."""
    try:
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

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/cost/summary', methods=['GET'])
def get_cost_summary():
    """Get cost summary and limits."""
    try:
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
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("\n" + "="*70)
    print("  Deepr API Server")
    print("  Running on http://localhost:5000")
    print("  CORS enabled for React dev server (port 5173)")
    print("="*70 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
