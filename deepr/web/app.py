"""
Flask web interface for Deepr.

Monitor jobs, view results, submit new research, track costs.
"""

import os
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__,
    template_folder='templates',
    static_folder='static')
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize services
from deepr.queue.local_queue import SQLiteQueue
from deepr.storage.local import LocalStorage
from deepr.providers.openai_provider import OpenAIProvider
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.queue.base import ResearchJob, JobStatus
from deepr.core.costs import CostController, CostEstimator
import uuid

config_path = Path('.deepr')
config_path.mkdir(exist_ok=True)

queue = SQLiteQueue(str(config_path / 'queue.db'))
storage = LocalStorage(str(config_path / 'storage'))
provider = OpenAIProvider(api_key=os.getenv('OPENAI_API_KEY'))

# Initialize cost tracking
try:
    cost_controller = CostController(
        max_cost_per_job=float(os.getenv('DEEPR_PER_JOB_LIMIT', '20')),
        max_daily_cost=float(os.getenv('DEEPR_DAILY_LIMIT', '100')),
        max_monthly_cost=float(os.getenv('DEEPR_MONTHLY_LIMIT', '1000')),
    )
    cost_estimator = CostEstimator()
except Exception as e:
    logger.warning(f"Cost controller init failed: {e}, using defaults")
    cost_controller = None
    cost_estimator = None


def run_async(coro):
    """Helper to run async code in sync Flask context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.route('/')
def index():
    """Main dashboard."""
    return render_template('index.html')


def _parse_time_range(time_range: str, default_days: int = 30) -> int:
    """Parse time range string like '30d' to integer days.

    Args:
        time_range: String like '7d', '30d', '90d'
        default_days: Fallback if parsing fails

    Returns:
        Number of days as integer
    """
    if not time_range:
        return default_days
    try:
        if time_range.endswith('d'):
            return int(time_range[:-1])
        return int(time_range)
    except (ValueError, TypeError):
        return default_days


@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    """Get all jobs with pagination."""
    try:
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        status_filter = request.args.get('status', None)

        if status_filter and status_filter != 'all':
            try:
                status_enum = JobStatus(status_filter)
            except ValueError:
                return jsonify({'error': f'Invalid status: {status_filter}'}), 400
            jobs = run_async(queue.list_jobs(status=status_enum, limit=limit + offset))
        else:
            jobs = run_async(queue.list_jobs(limit=limit + offset))

        # Apply offset
        jobs = jobs[offset:offset + limit]

        jobs_data = []
        for job in jobs:
            jobs_data.append({
                'id': job.id,
                'prompt': job.prompt[:200] if len(job.prompt) > 200 else job.prompt,
                'model': job.model,
                'status': job.status.value,
                'priority': job.priority,
                'cost': job.cost or 0,
                'tokens_used': job.tokens_used or 0,
                'submitted_at': job.submitted_at.isoformat() if job.submitted_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'metadata': job.metadata or {}
            })

        # Get total count
        all_jobs = run_async(queue.list_jobs(limit=10000))
        total = len(all_jobs)

        return jsonify({'jobs': jobs_data, 'total': total, 'count': len(jobs_data)})

    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
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
            'last_error': job.last_error,
            'result': None
        }

        # Get result if completed
        if job.status == JobStatus.COMPLETED:
            try:
                result = run_async(storage.get_report(job_id=job_id, filename='report.md'))
                job_data['result'] = result.decode('utf-8')
            except (OSError, UnicodeDecodeError, KeyError, Exception):
                job_data['result'] = None

        return jsonify({'job': job_data})

    except Exception as e:
        logger.error(f"Error getting job {job_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>', methods=['DELETE'])
def delete_job(job_id):
    """Delete a job."""
    try:
        job = run_async(queue.get_job(job_id))
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        # Cancel if still running
        if job.status in [JobStatus.QUEUED, JobStatus.PROCESSING]:
            run_async(queue.cancel_job(job_id))

        # Delete from queue (mark as deleted)
        run_async(queue.update_status(job_id, JobStatus.FAILED))

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {e}")
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

        # Estimate cost first
        estimated_cost = None
        if cost_estimator:
            try:
                estimate = cost_estimator.estimate(prompt, model)
                estimated_cost = {
                    'min_cost': estimate.get('min_cost', 0),
                    'max_cost': estimate.get('max_cost', 0),
                    'expected_cost': estimate.get('expected_cost', 0),
                }
            except Exception as e:
                logger.warning(f"Cost estimation failed: {e}")
                estimated_cost = {'min_cost': 1.0, 'max_cost': 5.0, 'expected_cost': 2.0}

        # Create job
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        job = ResearchJob(
            id=job_id,
            prompt=prompt,
            model=model,
            priority=priority,
            enable_web_search=enable_web_search,
            status=JobStatus.QUEUED,
            submitted_at=now,
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

        try:
            provider_job_id = run_async(provider.submit_research(req))

            # Update status
            run_async(queue.update_status(
                job_id=job_id,
                status=JobStatus.PROCESSING,
                provider_job_id=provider_job_id
            ))
        except Exception as e:
            logger.error(f"Provider submission failed: {e}")
            run_async(queue.update_status(job_id=job_id, status=JobStatus.FAILED))
            return jsonify({'error': f'Provider error: {str(e)}'}), 500

        # Return job data matching frontend expectations
        job_response = {
            'id': job_id,
            'prompt': prompt,
            'model': model,
            'status': 'processing',
            'priority': priority,
            'cost': 0,
            'tokens_used': 0,
            'submitted_at': now.isoformat(),
            'provider_job_id': provider_job_id,
        }

        return jsonify({
            'job': job_response,
            'estimated_cost': estimated_cost or {'min_cost': 1.0, 'max_cost': 5.0, 'expected_cost': 2.0}
        })

    except Exception as e:
        logger.error(f"Error submitting job: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/batch', methods=['POST'])
def batch_submit():
    """Submit multiple jobs at once."""
    try:
        data = request.json
        jobs_data = data.get('jobs', [])

        if not jobs_data:
            return jsonify({'error': 'No jobs provided'}), 400

        results = []
        for job_input in jobs_data:
            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            job = ResearchJob(
                id=job_id,
                prompt=job_input.get('prompt', ''),
                model=job_input.get('model', 'o4-mini-deep-research'),
                priority=job_input.get('priority', 3),
                enable_web_search=job_input.get('enable_web_search', True),
                status=JobStatus.QUEUED,
                submitted_at=now,
                metadata=job_input.get('metadata', {})
            )
            run_async(queue.enqueue(job))
            results.append({'job_id': job_id, 'status': 'queued'})

        return jsonify({'jobs': results, 'count': len(results)})

    except Exception as e:
        logger.error(f"Error batch submitting: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/bulk-cancel', methods=['POST'])
def bulk_cancel():
    """Cancel multiple jobs at once."""
    try:
        data = request.json
        job_ids = data.get('job_ids', [])

        cancelled = []
        failed = []
        for job_id in job_ids:
            try:
                success = run_async(queue.cancel_job(job_id))
                if success:
                    cancelled.append(job_id)
                else:
                    failed.append(job_id)
            except Exception:
                failed.append(job_id)

        return jsonify({
            'cancelled': cancelled,
            'failed': failed,
            'count': len(cancelled)
        })

    except Exception as e:
        logger.error(f"Error bulk cancelling: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id):
    """Cancel a job."""
    try:
        success = run_async(queue.cancel_job(job_id))
        return jsonify({'success': success})

    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        return jsonify({'error': str(e)}), 500


# =============================================================================
# COST API ENDPOINTS
# =============================================================================

@app.route('/api/cost/summary', methods=['GET'])
def get_cost_summary():
    """Get cost summary with daily/monthly spending."""
    try:
        all_jobs = run_async(queue.list_jobs(limit=10000))

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Calculate spending
        daily_spending = sum(
            (j.cost or 0) for j in all_jobs
            if j.completed_at and j.completed_at >= today_start
        )
        monthly_spending = sum(
            (j.cost or 0) for j in all_jobs
            if j.completed_at and j.completed_at >= month_start
        )
        total_spending = sum((j.cost or 0) for j in all_jobs)

        completed_jobs = [j for j in all_jobs if j.status == JobStatus.COMPLETED]
        avg_cost = total_spending / len(completed_jobs) if completed_jobs else 0

        # Get limits from controller or defaults
        daily_limit = cost_controller.max_daily_cost if cost_controller else 100.0
        monthly_limit = cost_controller.max_monthly_cost if cost_controller else 1000.0
        per_job_limit = cost_controller.max_cost_per_job if cost_controller else 20.0

        summary = {
            'daily': round(daily_spending, 2),
            'monthly': round(monthly_spending, 2),
            'total': round(total_spending, 2),
            'daily_limit': daily_limit,
            'monthly_limit': monthly_limit,
            'per_job_limit': per_job_limit,
            'avg_cost_per_job': round(avg_cost, 2),
            'completed_jobs': len(completed_jobs),
            'total_jobs': len(all_jobs),
        }

        return jsonify({'summary': summary})

    except Exception as e:
        logger.error(f"Error getting cost summary: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cost/trends', methods=['GET'])
def get_cost_trends():
    """Get daily spending trends."""
    try:
        days = int(request.args.get('days', 30))
        all_jobs = run_async(queue.list_jobs(limit=10000))

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        # Group by day
        daily_costs = {}
        for job in all_jobs:
            if job.completed_at and job.completed_at >= cutoff and job.cost:
                day_key = job.completed_at.strftime('%Y-%m-%d')
                daily_costs[day_key] = daily_costs.get(day_key, 0) + job.cost

        # Build trend data
        trends = []
        cumulative = 0
        for i in range(days):
            day = (now - timedelta(days=days - 1 - i)).strftime('%Y-%m-%d')
            cost = daily_costs.get(day, 0)
            cumulative += cost
            trends.append({
                'date': day,
                'cost': round(cost, 2),
                'cumulative': round(cumulative, 2)
            })

        return jsonify({
            'trends': {
                'daily': trends,
                'cumulative': round(cumulative, 2)
            }
        })

    except Exception as e:
        logger.error(f"Error getting cost trends: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cost/breakdown', methods=['GET'])
def get_cost_breakdown():
    """Get cost breakdown by model."""
    try:
        time_range = request.args.get('time_range', '30d')
        days = _parse_time_range(time_range, 30)

        all_jobs = run_async(queue.list_jobs(limit=10000))
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        # Group by model
        model_costs = {}
        for job in all_jobs:
            if job.completed_at and job.completed_at >= cutoff:
                model = job.model or 'unknown'
                if model not in model_costs:
                    model_costs[model] = {'cost': 0, 'count': 0, 'tokens': 0}
                model_costs[model]['cost'] += job.cost or 0
                model_costs[model]['count'] += 1
                model_costs[model]['tokens'] += job.tokens_used or 0

        breakdown = [
            {
                'model': model,
                'cost': round(data['cost'], 2),
                'count': data['count'],
                'tokens': data['tokens'],
                'avg_cost': round(data['cost'] / data['count'], 2) if data['count'] else 0
            }
            for model, data in model_costs.items()
        ]

        return jsonify({'breakdown': breakdown})

    except Exception as e:
        logger.error(f"Error getting cost breakdown: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cost/history', methods=['GET'])
def get_cost_history():
    """Get detailed cost history."""
    try:
        time_range = request.args.get('time_range', '30d')
        days = _parse_time_range(time_range, 30)
        limit = int(request.args.get('limit', 100))

        all_jobs = run_async(queue.list_jobs(limit=10000))
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        # Filter and sort by completion date
        completed = [
            j for j in all_jobs
            if j.completed_at and j.completed_at >= cutoff and j.cost
        ]
        completed.sort(key=lambda j: j.completed_at, reverse=True)

        history = [
            {
                'id': job.id,
                'prompt': job.prompt[:100],
                'model': job.model,
                'cost': round(job.cost or 0, 2),
                'tokens': job.tokens_used or 0,
                'completed_at': job.completed_at.isoformat()
            }
            for job in completed[:limit]
        ]

        return jsonify({'history': history})

    except Exception as e:
        logger.error(f"Error getting cost history: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cost/estimate', methods=['POST'])
def estimate_cost():
    """Estimate cost for a research prompt."""
    try:
        data = request.json
        prompt = data.get('prompt', '')
        model = data.get('model', 'o4-mini-deep-research')
        enable_web_search = data.get('enable_web_search', True)

        if not prompt:
            return jsonify({'error': 'Prompt required'}), 400

        # Use estimator if available, otherwise use defaults
        if cost_estimator:
            try:
                estimate = cost_estimator.estimate(prompt, model)
            except Exception as e:
                logger.warning(f"Cost estimation failed: {e}")
                estimate = {'min_cost': 1.0, 'max_cost': 5.0, 'expected_cost': 2.0}
        else:
            # Default estimates based on model
            if 'o3' in model:
                estimate = {'min_cost': 2.0, 'max_cost': 15.0, 'expected_cost': 5.0}
            else:
                estimate = {'min_cost': 1.0, 'max_cost': 5.0, 'expected_cost': 2.0}

        # Check against limits
        allowed = True
        reason = None
        if cost_controller:
            expected = estimate.get('expected_cost', 0)
            if expected > cost_controller.max_cost_per_job:
                allowed = False
                reason = f"Exceeds per-job limit of ${cost_controller.max_cost_per_job}"
            elif cost_controller.daily_spending + expected > cost_controller.max_daily_cost:
                allowed = False
                reason = f"Would exceed daily limit of ${cost_controller.max_daily_cost}"

        return jsonify({
            'estimate': {
                'min_cost': round(estimate.get('min_cost', 1.0), 2),
                'max_cost': round(estimate.get('max_cost', 5.0), 2),
                'expected_cost': round(estimate.get('expected_cost', 2.0), 2),
            },
            'allowed': allowed,
            'reason': reason
        })

    except Exception as e:
        logger.error(f"Error estimating cost: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cost/limits', methods=['GET'])
def get_cost_limits():
    """Get current budget limits."""
    try:
        limits = {
            'per_job': cost_controller.max_cost_per_job if cost_controller else 20.0,
            'daily': cost_controller.max_daily_cost if cost_controller else 100.0,
            'monthly': cost_controller.max_monthly_cost if cost_controller else 1000.0,
        }
        return jsonify({'limits': limits})

    except Exception as e:
        logger.error(f"Error getting limits: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cost/limits', methods=['PATCH'])
def update_cost_limits():
    """Update budget limits."""
    try:
        data = request.json

        if cost_controller:
            if 'per_job' in data:
                cost_controller.max_cost_per_job = float(data['per_job'])
            if 'daily' in data:
                cost_controller.max_daily_cost = float(data['daily'])
            if 'monthly' in data:
                cost_controller.max_monthly_cost = float(data['monthly'])

        limits = {
            'per_job': cost_controller.max_cost_per_job if cost_controller else 20.0,
            'daily': cost_controller.max_daily_cost if cost_controller else 100.0,
            'monthly': cost_controller.max_monthly_cost if cost_controller else 1000.0,
        }
        return jsonify({'limits': limits, 'updated': True})

    except Exception as e:
        logger.error(f"Error updating limits: {e}")
        return jsonify({'error': str(e)}), 500


# =============================================================================
# RESULTS API ENDPOINTS
# =============================================================================

@app.route('/api/results', methods=['GET'])
def list_results():
    """List completed research results."""
    try:
        search = request.args.get('search', '')
        sort_by = request.args.get('sort_by', 'date')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))

        # Get completed jobs
        all_jobs = run_async(queue.list_jobs(limit=1000))
        completed = [j for j in all_jobs if j.status == JobStatus.COMPLETED]

        # Filter by search
        if search:
            search_lower = search.lower()
            completed = [j for j in completed if search_lower in j.prompt.lower()]

        # Sort
        if sort_by == 'cost':
            completed.sort(key=lambda j: j.cost or 0, reverse=True)
        elif sort_by == 'model':
            completed.sort(key=lambda j: j.model or '')
        else:  # date
            completed.sort(key=lambda j: j.completed_at or j.submitted_at, reverse=True)

        # Paginate
        total = len(completed)
        completed = completed[offset:offset + limit]

        # Build results with content preview
        results = []
        for job in completed:
            result_data = {
                'id': job.id,
                'job_id': job.id,
                'prompt': job.prompt,
                'model': job.model,
                'cost': job.cost or 0,
                'tokens_used': job.tokens_used or 0,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'created_at': job.submitted_at.isoformat() if job.submitted_at else None,
                'citations_count': 0,
                'content': '',
                'tags': job.tags if hasattr(job, 'tags') else [],
                'enable_web_search': job.enable_web_search,
            }

            # Try to get content preview
            try:
                content = run_async(storage.get_report(job_id=job.id, filename='report.md'))
                content_str = content.decode('utf-8')
                result_data['content'] = content_str[:500] if len(content_str) > 500 else content_str
                # Count citations (rough estimate by counting URLs)
                result_data['citations_count'] = content_str.count('http')
            except Exception:
                pass

            results.append(result_data)

        return jsonify({'results': results, 'total': total})

    except Exception as e:
        logger.error(f"Error listing results: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/results/<job_id>', methods=['GET'])
def get_result(job_id):
    """Get full result for a job."""
    try:
        job = run_async(queue.get_job(job_id))

        if not job:
            return jsonify({'error': 'Job not found'}), 404

        if job.status != JobStatus.COMPLETED:
            return jsonify({'error': 'Job not completed yet'}), 400

        result_data = {
            'id': job.id,
            'job_id': job.id,
            'prompt': job.prompt,
            'model': job.model,
            'cost': job.cost or 0,
            'tokens_used': job.tokens_used or 0,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'created_at': job.submitted_at.isoformat() if job.submitted_at else None,
            'citations_count': 0,
            'content': '',
            'citations': [],
            'tags': job.tags if hasattr(job, 'tags') else [],
            'enable_web_search': job.enable_web_search,
            'metadata': job.metadata or {},
        }

        # Get full content
        try:
            content = run_async(storage.get_report(job_id=job.id, filename='report.md'))
            result_data['content'] = content.decode('utf-8')
            result_data['citations_count'] = result_data['content'].count('http')
        except Exception as e:
            logger.warning(f"Could not load content for {job_id}: {e}")

        return jsonify({'result': result_data})

    except Exception as e:
        logger.error(f"Error getting result {job_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/results/<job_id>/export/<format>', methods=['GET'])
def export_result(job_id, format):
    """Export result in specified format."""
    try:
        job = run_async(queue.get_job(job_id))

        if not job or job.status != JobStatus.COMPLETED:
            return jsonify({'error': 'Completed job not found'}), 404

        # Get content
        try:
            content = run_async(storage.get_report(job_id=job.id, filename='report.md'))
            content_str = content.decode('utf-8')
        except Exception:
            return jsonify({'error': 'Report not found'}), 404

        if format == 'markdown' or format == 'md':
            from flask import Response
            return Response(
                content_str,
                mimetype='text/markdown',
                headers={'Content-Disposition': f'attachment; filename=report-{job_id[:8]}.md'}
            )
        elif format == 'json':
            return jsonify({
                'id': job.id,
                'prompt': job.prompt,
                'model': job.model,
                'content': content_str,
                'cost': job.cost,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            })
        else:
            return jsonify({'error': f'Unsupported format: {format}'}), 400

    except Exception as e:
        logger.error(f"Error exporting result {job_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/results/search', methods=['GET'])
def search_results():
    """Search results by query."""
    try:
        query = request.args.get('q', '')
        limit = int(request.args.get('limit', 20))

        if not query:
            return jsonify({'results': [], 'total': 0})

        # Get completed jobs and search
        all_jobs = run_async(queue.list_jobs(limit=1000))
        completed = [j for j in all_jobs if j.status == JobStatus.COMPLETED]

        query_lower = query.lower()
        matches = []

        for job in completed:
            if query_lower in job.prompt.lower():
                matches.append({
                    'id': job.id,
                    'prompt': job.prompt,
                    'model': job.model,
                    'cost': job.cost or 0,
                    'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                })

        return jsonify({'results': matches[:limit], 'total': len(matches)})

    except Exception as e:
        logger.error(f"Error searching results: {e}")
        return jsonify({'error': str(e)}), 500


# =============================================================================
# CONFIG API ENDPOINTS
# =============================================================================

# In-memory config (would normally be persisted)
_config = {
    'default_model': 'o4-mini-deep-research',
    'default_priority': 1,
    'enable_web_search': True,
    'provider': 'openai',
    'storage': 'local',
    'queue': 'sqlite',
    'has_api_key': bool(os.getenv('OPENAI_API_KEY')),
}


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration."""
    try:
        config = {
            **_config,
            'daily_limit': cost_controller.max_daily_cost if cost_controller else 100.0,
            'monthly_limit': cost_controller.max_monthly_cost if cost_controller else 1000.0,
            'has_api_key': bool(os.getenv('OPENAI_API_KEY')),
        }
        return jsonify(config)

    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['PATCH'])
def update_config():
    """Update configuration."""
    try:
        data = request.json

        # Update allowed fields
        allowed = ['default_model', 'default_priority', 'enable_web_search']
        for key in allowed:
            if key in data:
                _config[key] = data[key]

        # Update cost limits if provided
        if cost_controller:
            if 'daily_limit' in data:
                cost_controller.max_daily_cost = float(data['daily_limit'])
            if 'monthly_limit' in data:
                cost_controller.max_monthly_cost = float(data['monthly_limit'])

        return jsonify({'success': True, 'config': _config})

    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify({'error': str(e)}), 500


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        # Check queue connectivity
        all_jobs = run_async(queue.list_jobs(limit=1))

        return jsonify({
            'status': 'healthy',
            'version': '2.6.0',
            'provider': 'openai',
            'queue': 'sqlite',
            'storage': 'local',
        })

    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


if __name__ == '__main__':
    print("\n" + "="*70)
    print("  Deepr Research Dashboard")
    print("  Running on http://localhost:5000")
    print("="*70 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
