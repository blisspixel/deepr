"""
Simple Flask web interface for Deepr.

Monitor jobs, view results, submit new research.
"""

import os
import asyncio
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__,
    template_folder='templates',
    static_folder='static')
CORS(app)

# Initialize services
from deepr.queue.local_queue import SQLiteQueue
from deepr.storage.local import LocalStorage
from deepr.providers.openai_provider import OpenAIProvider
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.queue.base import ResearchJob, JobStatus
import uuid

config_path = Path('.deepr')
config_path.mkdir(exist_ok=True)

queue = SQLiteQueue(str(config_path / 'queue.db'))
storage = LocalStorage(str(config_path / 'storage'))
provider = OpenAIProvider(api_key=os.getenv('OPENAI_API_KEY'))


@app.route('/')
def index():
    """Main dashboard."""
    return render_template('index.html')


@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    """Get all jobs."""
    try:
        limit = int(request.args.get('limit', 100))
        status_filter = request.args.get('status', None)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        if status_filter:
            status_enum = JobStatus(status_filter)
            jobs = loop.run_until_complete(queue.list_jobs(status=status_enum, limit=limit))
        else:
            jobs = loop.run_until_complete(queue.list_jobs(limit=limit))

        jobs_data = []
        for job in jobs:
            jobs_data.append({
                'id': job.id,
                'prompt': job.prompt[:200],
                'model': job.model,
                'status': job.status.value,
                'priority': job.priority,
                'cost': job.cost,
                'tokens_used': job.tokens_used,
                'submitted_at': job.submitted_at.isoformat() if job.submitted_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'metadata': job.metadata
            })

        return jsonify({'jobs': jobs_data, 'count': len(jobs_data)})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/stats', methods=['GET'])
def get_stats():
    """Get queue statistics."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        all_jobs = loop.run_until_complete(queue.list_jobs(limit=1000))

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


@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    """Get specific job details."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        job = loop.run_until_complete(queue.get_job(job_id))

        if not job:
            return jsonify({'error': 'Job not found'}), 404

        job_data = {
            'id': job.id,
            'prompt': job.prompt,
            'model': job.model,
            'status': job.status.value,
            'priority': job.priority,
            'cost': job.cost,
            'tokens_used': job.tokens_used,
            'submitted_at': job.submitted_at.isoformat() if job.submitted_at else None,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'metadata': job.metadata,
            'provider_job_id': job.provider_job_id,
            'last_error': job.last_error
        }

        # Get result if completed
        if job.status == JobStatus.COMPLETED:
            try:
                result = loop.run_until_complete(storage.get_report(job_id=job_id, filename='report.md'))
                job_data['result'] = result.decode('utf-8')
            except:
                job_data['result'] = None

        return jsonify(job_data)

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

        if not prompt:
            return jsonify({'error': 'Prompt required'}), 400

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Create job
        job_id = str(uuid.uuid4())
        job = ResearchJob(
            id=job_id,
            prompt=prompt,
            model=model,
            priority=priority,
            enable_web_search=True,
            status=JobStatus.QUEUED,
            metadata=data.get('metadata', {})
        )

        loop.run_until_complete(queue.enqueue(job))

        # Submit to provider
        req = ResearchRequest(
            prompt=prompt,
            model=model,
            system_message='You are a research assistant. Provide comprehensive, citation-backed analysis.',
            tools=[ToolConfig(type='web_search_preview')],
            background=True,
        )

        provider_job_id = loop.run_until_complete(provider.submit_research(req))

        # Update status
        loop.run_until_complete(queue.update_status(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            provider_job_id=provider_job_id
        ))

        return jsonify({
            'job_id': job_id,
            'provider_job_id': provider_job_id,
            'status': 'submitted'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id):
    """Cancel a job."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        success = loop.run_until_complete(queue.cancel_job(job_id))

        return jsonify({'success': success})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("\n" + "="*70)
    print("  Deepr Web Interface")
    print("  Running on http://localhost:5000")
    print("="*70 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
