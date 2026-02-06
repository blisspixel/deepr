"""
Flask web interface for Deepr.

Monitor jobs, view results, submit new research, track costs.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize services
import uuid

from deepr.core.costs import CostController, CostEstimator
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.providers.openai_provider import OpenAIProvider
from deepr.queue.base import JobStatus, ResearchJob
from deepr.queue.local_queue import SQLiteQueue
from deepr.storage.local import LocalStorage

config_path = Path(".deepr")
config_path.mkdir(exist_ok=True)

queue = SQLiteQueue(str(config_path / "queue.db"))
storage = LocalStorage(str(config_path / "storage"))
provider = OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize cost tracking
try:
    cost_controller = CostController(
        max_cost_per_job=float(os.getenv("DEEPR_PER_JOB_LIMIT", "20")),
        max_daily_cost=float(os.getenv("DEEPR_DAILY_LIMIT", "100")),
        max_monthly_cost=float(os.getenv("DEEPR_MONTHLY_LIMIT", "1000")),
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


@app.route("/")
def index():
    """Main dashboard."""
    return render_template("index.html")


def _safe_int(value, default: int = 0) -> int:
    """Safely parse an integer from query params."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


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
        if time_range.endswith("d"):
            return int(time_range[:-1])
        return int(time_range)
    except (ValueError, TypeError):
        return default_days


@app.route("/api/jobs", methods=["GET"])
def get_jobs():
    """Get all jobs with pagination."""
    try:
        limit = _safe_int(request.args.get("limit", 100), 100)
        offset = _safe_int(request.args.get("offset", 0), 0)
        status_filter = request.args.get("status", None)

        if status_filter and status_filter != "all":
            try:
                status_enum = JobStatus(status_filter)
            except ValueError:
                return jsonify({"error": f"Invalid status: {status_filter}"}), 400
            jobs = run_async(queue.list_jobs(status=status_enum, limit=limit + offset))
        else:
            jobs = run_async(queue.list_jobs(limit=limit + offset))

        # Apply offset
        jobs = jobs[offset : offset + limit]

        jobs_data = []
        for job in jobs:
            jobs_data.append(
                {
                    "id": job.id,
                    "prompt": job.prompt[:200] if len(job.prompt) > 200 else job.prompt,
                    "model": job.model,
                    "status": job.status.value,
                    "priority": job.priority,
                    "cost": job.cost or 0,
                    "tokens_used": job.tokens_used or 0,
                    "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    "metadata": job.metadata or {},
                }
            )

        # Get total count
        all_jobs = run_async(queue.list_jobs(limit=10000))
        total = len(all_jobs)

        return jsonify({"jobs": jobs_data, "total": total, "count": len(jobs_data)})

    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/stats", methods=["GET"])
def get_stats():
    """Get queue statistics."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        all_jobs = loop.run_until_complete(queue.list_jobs(limit=1000))

        stats = {
            "total": len(all_jobs),
            "queued": sum(1 for j in all_jobs if j.status == JobStatus.QUEUED),
            "processing": sum(1 for j in all_jobs if j.status == JobStatus.PROCESSING),
            "completed": sum(1 for j in all_jobs if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in all_jobs if j.status == JobStatus.FAILED),
            "total_cost": sum(j.cost or 0 for j in all_jobs),
            "total_tokens": sum(j.tokens_used or 0 for j in all_jobs),
        }

        return jsonify(stats)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    """Get specific job details."""
    try:
        job = run_async(queue.get_job(job_id))

        if not job:
            return jsonify({"error": "Job not found"}), 404

        job_data = {
            "id": job.id,
            "prompt": job.prompt,
            "model": job.model,
            "status": job.status.value,
            "priority": job.priority,
            "cost": job.cost or 0,
            "tokens_used": job.tokens_used or 0,
            "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "metadata": job.metadata or {},
            "provider_job_id": job.provider_job_id,
            "last_error": job.last_error,
            "result": None,
        }

        # Get result if completed
        if job.status == JobStatus.COMPLETED:
            try:
                result = run_async(storage.get_report(job_id=job_id, filename="report.md"))
                job_data["result"] = result.decode("utf-8")
            except (OSError, UnicodeDecodeError, KeyError, Exception):
                job_data["result"] = None

        return jsonify({"job": job_data})

    except Exception as e:
        logger.error(f"Error getting job {job_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    """Delete a job."""
    try:
        job = run_async(queue.get_job(job_id))
        if not job:
            return jsonify({"error": "Job not found"}), 404

        # Cancel if still running
        if job.status in [JobStatus.QUEUED, JobStatus.PROCESSING]:
            run_async(queue.cancel_job(job_id))

        # Delete from queue (mark as deleted)
        run_async(queue.update_status(job_id, JobStatus.FAILED))

        return jsonify({"success": True})

    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs", methods=["POST"])
def submit_job():
    """Submit a new research job."""
    try:
        data = request.json
        prompt = data.get("prompt")
        model = data.get("model", "o4-mini-deep-research")
        priority = data.get("priority", 3)
        enable_web_search = data.get("enable_web_search", True)

        if not prompt:
            return jsonify({"error": "Prompt required"}), 400

        # Estimate cost first
        estimated_cost = None
        if cost_estimator:
            try:
                estimate = cost_estimator.estimate_cost(prompt, model)
                estimated_cost = {
                    "min_cost": estimate.min_cost,
                    "max_cost": estimate.max_cost,
                    "expected_cost": estimate.expected_cost,
                }
            except Exception as e:
                logger.warning(f"Cost estimation failed: {e}")
                estimated_cost = {"min_cost": 1.0, "max_cost": 5.0, "expected_cost": 2.0}

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
            metadata=data.get("metadata", {}),
        )

        run_async(queue.enqueue(job))

        # Submit to provider
        req = ResearchRequest(
            prompt=prompt,
            model=model,
            system_message="You are a research assistant. Provide comprehensive, citation-backed analysis.",
            tools=[ToolConfig(type="web_search_preview")] if enable_web_search else [],
            background=True,
        )

        try:
            provider_job_id = run_async(provider.submit_research(req))

            # Update status
            run_async(queue.update_status(job_id=job_id, status=JobStatus.PROCESSING, provider_job_id=provider_job_id))
        except Exception as e:
            logger.error(f"Provider submission failed: {e}")
            run_async(queue.update_status(job_id=job_id, status=JobStatus.FAILED))
            return jsonify({"error": f"Provider error: {str(e)}"}), 500

        # Return job data matching frontend expectations
        job_response = {
            "id": job_id,
            "prompt": prompt,
            "model": model,
            "status": "processing",
            "priority": priority,
            "cost": 0,
            "tokens_used": 0,
            "submitted_at": now.isoformat(),
            "provider_job_id": provider_job_id,
        }

        return jsonify(
            {
                "job": job_response,
                "estimated_cost": estimated_cost or {"min_cost": 1.0, "max_cost": 5.0, "expected_cost": 2.0},
            }
        )

    except Exception as e:
        logger.error(f"Error submitting job: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/batch", methods=["POST"])
def batch_submit():
    """Submit multiple jobs at once."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Request body required"}), 400
        jobs_data = data.get("jobs", [])

        if not jobs_data:
            return jsonify({"error": "No jobs provided"}), 400

        results = []
        for job_input in jobs_data:
            prompt = job_input.get("prompt", "").strip()
            if not prompt:
                continue  # Skip empty prompts
            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            job = ResearchJob(
                id=job_id,
                prompt=prompt,
                model=job_input.get("model", "o4-mini-deep-research"),
                priority=job_input.get("priority", 3),
                enable_web_search=job_input.get("enable_web_search", True),
                status=JobStatus.QUEUED,
                submitted_at=now,
                metadata=job_input.get("metadata", {}),
            )
            run_async(queue.enqueue(job))
            results.append({"job_id": job_id, "status": "queued"})

        return jsonify({"jobs": results, "count": len(results)})

    except Exception as e:
        logger.error(f"Error batch submitting: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/bulk-cancel", methods=["POST"])
def bulk_cancel():
    """Cancel multiple jobs at once."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Request body required"}), 400
        job_ids = data.get("job_ids", [])

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

        return jsonify({"cancelled": cancelled, "failed": failed, "count": len(cancelled)})

    except Exception as e:
        logger.error(f"Error bulk cancelling: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    """Cancel a job."""
    try:
        success = run_async(queue.cancel_job(job_id))
        return jsonify({"success": success})

    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# COST API ENDPOINTS
# =============================================================================


@app.route("/api/cost/summary", methods=["GET"])
def get_cost_summary():
    """Get cost summary with daily/monthly spending."""
    try:
        all_jobs = run_async(queue.list_jobs(limit=10000))

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Calculate spending
        daily_spending = sum((j.cost or 0) for j in all_jobs if j.completed_at and j.completed_at >= today_start)
        monthly_spending = sum((j.cost or 0) for j in all_jobs if j.completed_at and j.completed_at >= month_start)
        total_spending = sum((j.cost or 0) for j in all_jobs)

        completed_jobs = [j for j in all_jobs if j.status == JobStatus.COMPLETED]
        avg_cost = total_spending / len(completed_jobs) if completed_jobs else 0

        # Get limits from controller or defaults
        daily_limit = cost_controller.max_daily_cost if cost_controller else 100.0
        monthly_limit = cost_controller.max_monthly_cost if cost_controller else 1000.0
        per_job_limit = cost_controller.max_cost_per_job if cost_controller else 20.0

        summary = {
            "daily": round(daily_spending, 2),
            "monthly": round(monthly_spending, 2),
            "total": round(total_spending, 2),
            "daily_limit": daily_limit,
            "monthly_limit": monthly_limit,
            "per_job_limit": per_job_limit,
            "avg_cost_per_job": round(avg_cost, 2),
            "completed_jobs": len(completed_jobs),
            "total_jobs": len(all_jobs),
        }

        return jsonify({"summary": summary})

    except Exception as e:
        logger.error(f"Error getting cost summary: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/cost/trends", methods=["GET"])
def get_cost_trends():
    """Get daily spending trends."""
    try:
        days = _safe_int(request.args.get("days", 30), 30)
        all_jobs = run_async(queue.list_jobs(limit=10000))

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        # Group by day
        daily_costs = {}
        for job in all_jobs:
            if job.completed_at and job.completed_at >= cutoff and job.cost:
                day_key = job.completed_at.strftime("%Y-%m-%d")
                daily_costs[day_key] = daily_costs.get(day_key, 0) + job.cost

        # Build trend data
        trends = []
        cumulative = 0
        for i in range(days):
            day = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            cost = daily_costs.get(day, 0)
            cumulative += cost
            trends.append({"date": day, "cost": round(cost, 2), "cumulative": round(cumulative, 2)})

        return jsonify({"trends": {"daily": trends, "cumulative": round(cumulative, 2)}})

    except Exception as e:
        logger.error(f"Error getting cost trends: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/cost/breakdown", methods=["GET"])
def get_cost_breakdown():
    """Get cost breakdown by model."""
    try:
        time_range = request.args.get("time_range", "30d")
        days = _parse_time_range(time_range, 30)

        all_jobs = run_async(queue.list_jobs(limit=10000))
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        # Group by model
        model_costs = {}
        for job in all_jobs:
            if job.completed_at and job.completed_at >= cutoff:
                model = job.model or "unknown"
                if model not in model_costs:
                    model_costs[model] = {"cost": 0, "count": 0, "tokens": 0}
                model_costs[model]["cost"] += job.cost or 0
                model_costs[model]["count"] += 1
                model_costs[model]["tokens"] += job.tokens_used or 0

        breakdown = [
            {
                "model": model,
                "cost": round(data["cost"], 2),
                "count": data["count"],
                "tokens": data["tokens"],
                "avg_cost": round(data["cost"] / data["count"], 2) if data["count"] else 0,
            }
            for model, data in model_costs.items()
        ]

        return jsonify({"breakdown": breakdown})

    except Exception as e:
        logger.error(f"Error getting cost breakdown: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/cost/history", methods=["GET"])
def get_cost_history():
    """Get detailed cost history."""
    try:
        time_range = request.args.get("time_range", "30d")
        days = _parse_time_range(time_range, 30)
        limit = _safe_int(request.args.get("limit", 100), 100)

        all_jobs = run_async(queue.list_jobs(limit=10000))
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        # Filter and sort by completion date
        completed = [j for j in all_jobs if j.completed_at and j.completed_at >= cutoff and j.cost]
        completed.sort(key=lambda j: j.completed_at, reverse=True)

        history = [
            {
                "id": job.id,
                "prompt": job.prompt[:100],
                "model": job.model,
                "cost": round(job.cost or 0, 2),
                "tokens": job.tokens_used or 0,
                "completed_at": job.completed_at.isoformat(),
            }
            for job in completed[:limit]
        ]

        return jsonify({"history": history})

    except Exception as e:
        logger.error(f"Error getting cost history: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/cost/estimate", methods=["POST"])
def estimate_cost():
    """Estimate cost for a research prompt."""
    try:
        data = request.json
        prompt = data.get("prompt", "")
        model = data.get("model", "o4-mini-deep-research")

        if not prompt:
            return jsonify({"error": "Prompt required"}), 400

        # Use estimator if available, otherwise use defaults
        est_min, est_max, est_expected = 1.0, 5.0, 2.0
        if cost_estimator:
            try:
                estimate = cost_estimator.estimate_cost(prompt, model)
                est_min = estimate.min_cost
                est_max = estimate.max_cost
                est_expected = estimate.expected_cost
            except Exception as e:
                logger.warning(f"Cost estimation failed: {e}")
        else:
            # Default estimates based on model
            if "o3" in model:
                est_min, est_max, est_expected = 2.0, 15.0, 5.0

        # Check against limits using actual DB spending (not stale in-memory counter)
        allowed = True
        reason = None
        if cost_controller:
            if est_expected > cost_controller.max_cost_per_job:
                allowed = False
                reason = f"Exceeds per-job limit of ${cost_controller.max_cost_per_job}"
            else:
                try:
                    all_jobs = run_async(queue.list_jobs(limit=10000))
                    now = datetime.now(timezone.utc)
                    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    daily_actual = sum(
                        (j.cost or 0) for j in all_jobs if j.completed_at and j.completed_at >= today_start
                    )
                    if daily_actual + est_expected > cost_controller.max_daily_cost:
                        allowed = False
                        reason = f"Would exceed daily limit of ${cost_controller.max_daily_cost}"
                except Exception:
                    pass  # If we can't check, allow it

        return jsonify(
            {
                "estimate": {
                    "min_cost": round(est_min, 2),
                    "max_cost": round(est_max, 2),
                    "expected_cost": round(est_expected, 2),
                },
                "allowed": allowed,
                "reason": reason,
            }
        )

    except Exception as e:
        logger.error(f"Error estimating cost: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/cost/limits", methods=["GET"])
def get_cost_limits():
    """Get current budget limits."""
    try:
        limits = {
            "per_job": cost_controller.max_cost_per_job if cost_controller else 20.0,
            "daily": cost_controller.max_daily_cost if cost_controller else 100.0,
            "monthly": cost_controller.max_monthly_cost if cost_controller else 1000.0,
        }
        return jsonify({"limits": limits})

    except Exception as e:
        logger.error(f"Error getting limits: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/cost/limits", methods=["PATCH"])
def update_cost_limits():
    """Update budget limits."""
    try:
        data = request.json

        if cost_controller:
            if "per_job" in data:
                cost_controller.max_cost_per_job = float(data["per_job"])
            if "daily" in data:
                cost_controller.max_daily_cost = float(data["daily"])
            if "monthly" in data:
                cost_controller.max_monthly_cost = float(data["monthly"])

        limits = {
            "per_job": cost_controller.max_cost_per_job if cost_controller else 20.0,
            "daily": cost_controller.max_daily_cost if cost_controller else 100.0,
            "monthly": cost_controller.max_monthly_cost if cost_controller else 1000.0,
        }
        return jsonify({"limits": limits, "updated": True})

    except Exception as e:
        logger.error(f"Error updating limits: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# RESULTS API ENDPOINTS
# =============================================================================


@app.route("/api/results", methods=["GET"])
def list_results():
    """List completed research results."""
    try:
        search = request.args.get("search", "")
        sort_by = request.args.get("sort_by", "date")
        limit = _safe_int(request.args.get("limit", 50), 50)
        offset = _safe_int(request.args.get("offset", 0), 0)

        # Get completed jobs
        all_jobs = run_async(queue.list_jobs(limit=1000))
        completed = [j for j in all_jobs if j.status == JobStatus.COMPLETED]

        # Filter by search
        if search:
            search_lower = search.lower()
            completed = [j for j in completed if search_lower in j.prompt.lower()]

        # Sort
        if sort_by == "cost":
            completed.sort(key=lambda j: j.cost or 0, reverse=True)
        elif sort_by == "model":
            completed.sort(key=lambda j: j.model or "")
        else:  # date
            completed.sort(key=lambda j: j.completed_at or j.submitted_at, reverse=True)

        # Paginate
        total = len(completed)
        completed = completed[offset : offset + limit]

        # Build results with content preview
        results = []
        for job in completed:
            result_data = {
                "id": job.id,
                "job_id": job.id,
                "prompt": job.prompt,
                "model": job.model,
                "cost": job.cost or 0,
                "tokens_used": job.tokens_used or 0,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "created_at": job.submitted_at.isoformat() if job.submitted_at else None,
                "citations_count": 0,
                "content": "",
                "tags": job.tags if hasattr(job, "tags") else [],
                "enable_web_search": job.enable_web_search,
            }

            # Try to get content preview
            try:
                content = run_async(storage.get_report(job_id=job.id, filename="report.md"))
                content_str = content.decode("utf-8")
                result_data["content"] = content_str[:500] if len(content_str) > 500 else content_str
                # Count citations (rough estimate by counting URLs)
                result_data["citations_count"] = content_str.count("http")
            except Exception:
                pass

            results.append(result_data)

        return jsonify({"results": results, "total": total})

    except Exception as e:
        logger.error(f"Error listing results: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/results/<job_id>", methods=["GET"])
def get_result(job_id):
    """Get full result for a job."""
    try:
        job = run_async(queue.get_job(job_id))

        if not job:
            return jsonify({"error": "Job not found"}), 404

        if job.status != JobStatus.COMPLETED:
            return jsonify({"error": "Job not completed yet"}), 400

        result_data = {
            "id": job.id,
            "job_id": job.id,
            "prompt": job.prompt,
            "model": job.model,
            "cost": job.cost or 0,
            "tokens_used": job.tokens_used or 0,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "created_at": job.submitted_at.isoformat() if job.submitted_at else None,
            "citations_count": 0,
            "content": "",
            "citations": [],
            "tags": job.tags if hasattr(job, "tags") else [],
            "enable_web_search": job.enable_web_search,
            "metadata": job.metadata or {},
        }

        # Get full content
        try:
            content = run_async(storage.get_report(job_id=job.id, filename="report.md"))
            result_data["content"] = content.decode("utf-8")
            result_data["citations_count"] = result_data["content"].count("http")
        except Exception as e:
            logger.warning(f"Could not load content for {job_id}: {e}")

        return jsonify({"result": result_data})

    except Exception as e:
        logger.error(f"Error getting result {job_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/results/<job_id>/export/<format>", methods=["GET"])
def export_result(job_id, format):
    """Export result in specified format."""
    try:
        job = run_async(queue.get_job(job_id))

        if not job or job.status != JobStatus.COMPLETED:
            return jsonify({"error": "Completed job not found"}), 404

        # Get content
        try:
            content = run_async(storage.get_report(job_id=job.id, filename="report.md"))
            content_str = content.decode("utf-8")
        except Exception:
            return jsonify({"error": "Report not found"}), 404

        if format == "markdown" or format == "md":
            from flask import Response

            return Response(
                content_str,
                mimetype="text/markdown",
                headers={"Content-Disposition": f"attachment; filename=report-{job_id[:8]}.md"},
            )
        elif format == "json":
            return jsonify(
                {
                    "id": job.id,
                    "prompt": job.prompt,
                    "model": job.model,
                    "content": content_str,
                    "cost": job.cost,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                }
            )
        else:
            return jsonify({"error": f"Unsupported format: {format}"}), 400

    except Exception as e:
        logger.error(f"Error exporting result {job_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/results/search", methods=["GET"])
def search_results():
    """Search results by query."""
    try:
        query = request.args.get("q", "")
        limit = _safe_int(request.args.get("limit", 20), 20)

        if not query:
            return jsonify({"results": [], "total": 0})

        # Get completed jobs and search
        all_jobs = run_async(queue.list_jobs(limit=1000))
        completed = [j for j in all_jobs if j.status == JobStatus.COMPLETED]

        query_lower = query.lower()
        matches = []

        for job in completed:
            if query_lower in job.prompt.lower():
                matches.append(
                    {
                        "id": job.id,
                        "prompt": job.prompt,
                        "model": job.model,
                        "cost": job.cost or 0,
                        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    }
                )

        return jsonify({"results": matches[:limit], "total": len(matches)})

    except Exception as e:
        logger.error(f"Error searching results: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# CONFIG API ENDPOINTS
# =============================================================================

# In-memory config (would normally be persisted)
_config = {
    "default_model": "o4-mini-deep-research",
    "default_priority": 1,
    "enable_web_search": True,
    "provider": "openai",
    "storage": "local",
    "queue": "sqlite",
    "has_api_key": bool(os.getenv("OPENAI_API_KEY")),
}


@app.route("/api/config", methods=["GET"])
def get_config():
    """Get current configuration."""
    try:
        config = {
            **_config,
            "daily_limit": cost_controller.max_daily_cost if cost_controller else 100.0,
            "monthly_limit": cost_controller.max_monthly_cost if cost_controller else 1000.0,
            "has_api_key": bool(os.getenv("OPENAI_API_KEY")),
        }
        return jsonify({"config": config})

    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/config", methods=["PATCH"])
def update_config():
    """Update configuration."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Request body required"}), 400

        # Update allowed fields
        allowed = ["default_model", "default_priority", "enable_web_search"]
        for key in allowed:
            if key in data:
                _config[key] = data[key]

        # Update cost limits if provided
        if cost_controller:
            if "daily_limit" in data:
                cost_controller.max_daily_cost = float(data["daily_limit"])
            if "monthly_limit" in data:
                cost_controller.max_monthly_cost = float(data["monthly_limit"])

        return jsonify({"config": _config})

    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# EXPERTS API ENDPOINTS
# =============================================================================


@app.route("/api/experts", methods=["GET"])
def list_experts():
    """List all domain experts."""
    try:
        from deepr.experts.profile import ExpertProfile

        experts_dir = config_path / "experts"
        experts = []
        if experts_dir.exists():
            for profile_dir in experts_dir.iterdir():
                if profile_dir.is_dir():
                    try:
                        profile = ExpertProfile.load(str(profile_dir))
                        experts.append(
                            {
                                "name": profile.name,
                                "description": getattr(profile, "description", ""),
                                "document_count": len(getattr(profile, "documents", [])),
                                "finding_count": len(getattr(profile, "findings", [])),
                                "gap_count": len(getattr(profile, "knowledge_gaps", [])),
                                "total_cost": getattr(profile, "total_cost", 0),
                                "last_active": getattr(profile, "last_active", ""),
                                "created_at": getattr(profile, "created_at", ""),
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Failed to load expert {profile_dir.name}: {e}")
        return jsonify({"experts": experts})
    except ImportError:
        return jsonify({"experts": []})
    except Exception as e:
        logger.error(f"Error listing experts: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/experts/<name>", methods=["GET"])
def get_expert(name):
    """Get expert details."""
    try:
        from urllib.parse import unquote

        from deepr.experts.profile import ExpertProfile

        decoded_name = unquote(name)
        experts_dir = config_path / "experts"
        # Find by name
        for profile_dir in experts_dir.iterdir():
            if profile_dir.is_dir():
                try:
                    profile = ExpertProfile.load(str(profile_dir))
                    if profile.name == decoded_name:
                        return jsonify(
                            {
                                "expert": {
                                    "name": profile.name,
                                    "description": getattr(profile, "description", ""),
                                    "document_count": len(getattr(profile, "documents", [])),
                                    "finding_count": len(getattr(profile, "findings", [])),
                                    "gap_count": len(getattr(profile, "knowledge_gaps", [])),
                                    "total_cost": getattr(profile, "total_cost", 0),
                                    "last_active": getattr(profile, "last_active", ""),
                                    "created_at": getattr(profile, "created_at", ""),
                                }
                            }
                        )
                except Exception:
                    continue
        return jsonify({"error": "Expert not found"}), 404
    except ImportError:
        return jsonify({"error": "Expert system not available"}), 404
    except Exception as e:
        logger.error(f"Error getting expert {name}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/experts/<name>/chat", methods=["POST"])
def chat_with_expert(name):
    """Chat with a domain expert."""
    try:
        data = request.json
        if not data or not data.get("message"):
            return jsonify({"error": "Message required"}), 400
        # Stub - expert chat requires the full expert system
        return jsonify(
            {
                "response": {
                    "role": "assistant",
                    "content": 'Expert chat requires the full expert system. Use: deepr expert chat "' + name + '"',
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            }
        )
    except Exception as e:
        logger.error(f"Error chatting with expert {name}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/experts/<name>/gaps", methods=["GET"])
def get_expert_gaps(name):
    """Get knowledge gaps for an expert."""
    try:
        from urllib.parse import unquote

        from deepr.experts.profile import ExpertProfile

        decoded_name = unquote(name)
        experts_dir = config_path / "experts"
        for profile_dir in experts_dir.iterdir():
            if profile_dir.is_dir():
                try:
                    profile = ExpertProfile.load(str(profile_dir))
                    if profile.name == decoded_name:
                        gaps = []
                        for gap in getattr(profile, "knowledge_gaps", []):
                            gaps.append(
                                {
                                    "id": getattr(gap, "id", str(uuid.uuid4())),
                                    "topic": getattr(gap, "topic", ""),
                                    "description": getattr(gap, "description", ""),
                                    "priority": getattr(gap, "priority", "medium"),
                                    "created_at": getattr(gap, "created_at", ""),
                                }
                            )
                        return jsonify({"gaps": gaps})
                except Exception:
                    continue
        return jsonify({"gaps": []})
    except ImportError:
        return jsonify({"gaps": []})
    except Exception as e:
        logger.error(f"Error getting gaps for expert {name}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/experts/<name>/history", methods=["GET"])
def get_expert_history(name):
    """Get learning history for an expert."""
    try:
        return jsonify({"events": []})
    except Exception as e:
        logger.error(f"Error getting history for expert {name}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# TRACES API ENDPOINTS
# =============================================================================


@app.route("/api/traces/<job_id>", methods=["GET"])
def get_trace(job_id):
    """Get trace data for a job."""
    try:
        trace_path = Path("data/traces") / f"{job_id}_trace.json"
        if trace_path.exists():
            import json

            with open(trace_path) as f:
                trace_data = json.load(f)
            return jsonify({"trace": trace_data})
        return jsonify({"trace": None})
    except Exception as e:
        logger.error(f"Error getting trace {job_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/traces/<job_id>/temporal", methods=["GET"])
def get_trace_temporal(job_id):
    """Get temporal findings for a trace."""
    try:
        trace_path = Path("data/traces") / f"{job_id}_trace.json"
        if trace_path.exists():
            import json

            with open(trace_path) as f:
                trace_data = json.load(f)
            findings = trace_data.get("temporal_findings", [])
            return jsonify({"findings": findings})
        return jsonify({"findings": []})
    except Exception as e:
        logger.error(f"Error getting temporal data for {job_id}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# ACTIVITY API ENDPOINT
# =============================================================================


@app.route("/api/activity", methods=["GET"])
def get_activity():
    """Get recent activity items."""
    try:
        limit = _safe_int(request.args.get("limit", 20), 20)
        all_jobs = run_async(queue.list_jobs(limit=limit * 2))

        # Sort by most recent first
        all_jobs.sort(key=lambda j: j.submitted_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

        items = []
        for job in all_jobs[:limit]:
            if job.status == JobStatus.COMPLETED:
                item_type = "job_completed"
                message = f"Research completed: {job.prompt[:60]}"
            elif job.status == JobStatus.PROCESSING:
                item_type = "job_started"
                message = f"Research started: {job.prompt[:60]}"
            elif job.status == JobStatus.FAILED:
                item_type = "job_failed"
                message = f"Research failed: {job.prompt[:60]}"
            else:
                continue

            items.append(
                {
                    "id": job.id,
                    "type": item_type,
                    "message": message,
                    "timestamp": (job.completed_at or job.submitted_at).isoformat()
                    if (job.completed_at or job.submitted_at)
                    else None,
                    "metadata": {"model": job.model, "cost": job.cost or 0},
                }
            )

        return jsonify({"items": items})

    except Exception as e:
        logger.error(f"Error getting activity: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# CONFIG TEST CONNECTION
# =============================================================================


@app.route("/api/config/test-connection", methods=["POST"])
def test_connection():
    """Test provider API connection."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Request body required"}), 400
        provider_name = data.get("provider", "openai")

        if provider_name == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return jsonify({"success": False, "message": "OPENAI_API_KEY not set"}), 200
            try:
                # Quick connectivity test
                import openai

                client = openai.OpenAI(api_key=api_key)
                client.models.list()
                return jsonify({"success": True, "message": "Connection successful"})
            except Exception as e:
                return jsonify({"success": False, "message": str(e)})
        else:
            return jsonify({"success": False, "message": f"Provider {provider_name} test not implemented"})

    except Exception as e:
        logger.error(f"Error testing connection: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# HEALTH CHECK
# =============================================================================


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    try:
        # Check queue connectivity
        run_async(queue.list_jobs(limit=1))

        return jsonify(
            {
                "status": "healthy",
                "version": "2.8.0",
                "provider": "openai",
                "queue": "sqlite",
                "storage": "local",
            }
        )

    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  Deepr Research Dashboard")
    print("  Running on http://localhost:5000")
    print("=" * 70 + "\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
