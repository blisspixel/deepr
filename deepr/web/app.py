"""
Flask web interface for Deepr.

Monitor jobs, view results, submit new research, track costs.
"""

import asyncio
import hmac
import json as _json
import logging
import math
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO

load_dotenv()

# Serve the Vite-built frontend from frontend/dist/
_frontend_dist = Path(__file__).parent / "frontend" / "dist"

# ---------------------------------------------------------------------------
# Security configuration
# ---------------------------------------------------------------------------
_API_KEY = os.getenv("DEEPR_API_KEY", "")  # empty = auth disabled (local dev)
_CORS_ORIGINS = os.getenv("DEEPR_CORS_ORIGINS", "http://localhost:5000").split(",")
_MAX_PROMPT_LENGTH = 50_000  # characters
_MAX_BATCH_SIZE = 50
_MAX_QUERY_LIMIT = 1000
_ALLOWED_MODELS = {
    "o3-deep-research",
    "o4-mini-deep-research",
    "gpt-5.2",
    "gemini-2.5-flash",
    "grok-4",
    "grok-4-fast",
    "claude-sonnet-4-5-20250929",
}

app = Flask(
    __name__,
    template_folder=str(_frontend_dist),
    static_folder=str(_frontend_dist / "assets"),
    static_url_path="/assets",
)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB request body limit

CORS(app, origins=_CORS_ORIGINS)
socketio = SocketIO(app, cors_allowed_origins=_CORS_ORIGINS, async_mode="threading")

# ---------------------------------------------------------------------------
# Rate limiting (requires flask-limiter)
# ---------------------------------------------------------------------------
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["120 per minute"],
        storage_uri="memory://",
    )
except ImportError:
    limiter = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authentication middleware
# ---------------------------------------------------------------------------
@app.before_request
def _check_auth():
    """Require API key on /api/ routes when DEEPR_API_KEY is set."""
    if not _API_KEY:
        return  # Auth disabled — local dev mode

    # Skip auth for non-API routes (SPA, static assets, health check)
    if not request.path.startswith("/api/"):
        return
    if request.path == "/api/health":
        return

    # Accept via Authorization: Bearer <key> or X-Api-Key: <key>
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.headers.get("X-Api-Key", "")

    if not token or not hmac.compare_digest(token, _API_KEY):
        return jsonify({"error": "Unauthorized"}), 401


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
@app.after_request
def _set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self' wss: ws:; "
        "font-src 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Initialize services
import uuid

# Load project config for correct paths
from deepr.config import load_config
from deepr.core.costs import CostController, CostEstimator
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.providers.openai_provider import OpenAIProvider
from deepr.queue.base import JobStatus, ResearchJob
from deepr.queue.local_queue import SQLiteQueue
from deepr.storage.local import LocalStorage

_cfg = load_config()
config_path = Path(".deepr")
config_path.mkdir(exist_ok=True)

queue = SQLiteQueue(_cfg.get("queue_db_path", str(config_path / "queue.db")))
storage = LocalStorage(_cfg.get("results_dir", str(config_path / "storage")))
provider = OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY"))

# Experts live under the data directory, not .deepr
_experts_dir = Path("data") / "experts"


# ---------------------------------------------------------------------------
# Persistent budget limits
# ---------------------------------------------------------------------------
_LIMITS_FILE = config_path / "budget_limits.json"


def _load_persisted_limits() -> dict:
    """Load budget limits from disk, falling back to env vars / defaults."""
    defaults = {
        "per_job": float(os.getenv("DEEPR_PER_JOB_LIMIT", "20") or "20"),
        "daily": float(os.getenv("DEEPR_DAILY_LIMIT", "100") or "100"),
        "monthly": float(os.getenv("DEEPR_MONTHLY_LIMIT", "1000") or "1000"),
    }
    if _LIMITS_FILE.exists():
        try:
            with open(_LIMITS_FILE, encoding="utf-8") as f:
                saved = _json.load(f)
            defaults.update({k: float(v) for k, v in saved.items() if k in defaults})
        except Exception:
            logger.warning("Could not read %s, using defaults", _LIMITS_FILE)
    return defaults


def _save_limits(per_job: float, daily: float, monthly: float):
    """Persist budget limits to disk."""
    try:
        with open(_LIMITS_FILE, "w", encoding="utf-8") as f:
            _json.dump({"per_job": per_job, "daily": daily, "monthly": monthly}, f)
    except Exception:
        logger.warning("Could not write %s", _LIMITS_FILE)


# Initialize cost tracking
try:
    _limits = _load_persisted_limits()
    cost_controller = CostController(
        max_cost_per_job=_limits["per_job"],
        max_daily_cost=_limits["daily"],
        max_monthly_cost=_limits["monthly"],
    )
    cost_estimator = CostEstimator()
except Exception as e:
    logger.warning(f"Cost controller init failed: {e}, using defaults")
    cost_controller = None
    cost_estimator = None

# Register WebSocket event handlers
from deepr.api.websockets.events import (
    emit_job_completed,
    emit_job_created,
    emit_job_failed,
    register_socketio_events,
)

register_socketio_events(socketio)

# ---------------------------------------------------------------------------
# Background poller — checks provider status for PROCESSING jobs
# ---------------------------------------------------------------------------
_poller_lock = threading.Lock()
_poller_started = False
_POLL_INTERVAL = 15  # seconds
_STUCK_THRESHOLD = timedelta(minutes=30)


def _run_poller_loop():
    """Infinite loop that polls provider for job status updates."""
    logger.info("Background poller started (interval=%ds)", _POLL_INTERVAL)
    while True:
        try:
            _poll_once()
        except Exception:
            logger.exception("Poller cycle error")
        time.sleep(_POLL_INTERVAL)


def _poll_once():
    """One poll cycle: check all PROCESSING jobs using a single event loop."""
    loop = asyncio.new_event_loop()
    try:
        jobs = loop.run_until_complete(queue.list_jobs(status=JobStatus.PROCESSING, limit=100))
        if not jobs:
            return
        logger.info("Poller: checking %d processing jobs", len(jobs))
        for job in jobs:
            try:
                _check_job(loop, job)
            except Exception:
                logger.exception("Poller: error checking job %s", job.id)
    finally:
        loop.close()


def _check_job(loop, job):
    """Check a single job's provider status."""
    if not job.provider_job_id:
        _check_stuck(loop, job)
        return

    try:
        response = loop.run_until_complete(provider.get_status(job.provider_job_id))
    except Exception as exc:
        logger.warning("Poller: provider error for job %s: %s", job.id, exc)
        _check_stuck(loop, job)
        return

    if response.status == "completed":
        _handle_completion(loop, job, response)
    elif response.status in ("failed", "cancelled", "expired"):
        _handle_failure(loop, job, response.error or f"Provider status: {response.status}")
    else:
        _check_stuck(loop, job)


def _handle_completion(loop, job, response):
    """Save results and emit completion event."""
    # Extract report text from provider output
    report_text = ""
    if response.output:
        for block in response.output:
            if block.get("type") == "message":
                for content in block.get("content", []):
                    if content.get("type") == "output_text":
                        report_text += content.get("text", "")
                    elif content.get("type") == "text":
                        report_text += content.get("text", "")

    if report_text:
        loop.run_until_complete(
            storage.save_report(
                job_id=job.id,
                filename="report.md",
                content=report_text.encode("utf-8"),
                content_type="text/markdown",
                metadata={"prompt": job.prompt, "model": job.model},
            )
        )

    cost = response.usage.cost if response.usage else None
    tokens = response.usage.total_tokens if response.usage else None

    loop.run_until_complete(queue.update_status(job_id=job.id, status=JobStatus.COMPLETED))
    if cost is not None or tokens is not None:
        loop.run_until_complete(
            queue.update_results(
                job_id=job.id,
                report_paths={"markdown": "report.md"},
                cost=cost,
                tokens_used=tokens,
            )
        )

    # Re-fetch to get updated job for the event payload
    updated_job = loop.run_until_complete(queue.get_job(job.id))
    if updated_job:
        emit_job_completed(socketio, updated_job)
    else:
        logger.error("Poller: job %s vanished after completion update — WebSocket notification lost", job.id)
    logger.info("Poller: job %s completed (cost=%.4f)", job.id, cost or 0)


def _handle_failure(loop, job, error):
    """Mark job as failed and emit failure event."""
    loop.run_until_complete(queue.update_status(job_id=job.id, status=JobStatus.FAILED, error=str(error)))
    updated_job = loop.run_until_complete(queue.get_job(job.id))
    if updated_job:
        emit_job_failed(socketio, updated_job, str(error))
    else:
        logger.error("Poller: job %s vanished after failure update — WebSocket notification lost", job.id)
    logger.info("Poller: job %s failed: %s", job.id, error)


def _check_stuck(loop, job):
    """If a job has been PROCESSING for too long, mark it failed."""
    if not job.started_at:
        return
    if datetime.now(timezone.utc) - _ensure_utc(job.started_at) > _STUCK_THRESHOLD:
        _handle_failure(loop, job, "Job stuck — exceeded 30 minute processing threshold")


@app.before_request
def _start_poller():
    """Start the background poller thread on first request (runs once)."""
    global _poller_started
    if _poller_started:
        return
    with _poller_lock:
        if _poller_started:
            return
        _poller_started = True
        t = threading.Thread(target=_run_poller_loop, daemon=True, name="job-poller")
        t.start()
        logger.info("Background job poller thread launched")


def run_async(coro):
    """Helper to run async code in sync Flask context."""
    return asyncio.run(coro)


@app.route("/")
def index():
    """Main dashboard."""
    return render_template("index.html")


@app.errorhandler(404)
def fallback_to_spa(e):
    """Serve index.html for unknown routes so client-side routing works."""
    # Don't catch missing API routes — return 404 JSON for those
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    # Serve static files from dist if they exist (with path traversal protection)
    relative = request.path.lstrip("/")
    if relative:
        try:
            resolved = (_frontend_dist / relative).resolve()
            if resolved.is_file() and str(resolved).startswith(str(_frontend_dist.resolve())):
                return send_from_directory(str(_frontend_dist), relative)
        except (OSError, ValueError):
            pass
    return render_template("index.html")


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC)."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


_SAFE_NAME_RE = re.compile(r"^[\w\s\-().,']+$")  # letters, digits, spaces, basic punctuation


def _validate_expert_name(name: str) -> str | None:
    """Validate an expert name. Returns error message or None if valid."""
    if not name or len(name) > 200:
        return "Name must be 1-200 characters"
    if ".." in name or "/" in name or "\\" in name:
        return "Name contains invalid characters"
    if not _SAFE_NAME_RE.match(name):
        return "Name contains invalid characters"
    return None


def _decode_expert_name(name: str):
    """Decode and validate a URL-encoded expert name. Returns (decoded, error_response)."""
    from urllib.parse import unquote

    decoded = unquote(name)
    err = _validate_expert_name(decoded)
    if err:
        return None, (jsonify({"error": err}), 400)
    return decoded, None


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
            days = int(time_range[:-1])
        else:
            days = int(time_range)
        return max(1, min(days, 365))
    except (ValueError, TypeError):
        return default_days


@app.route("/api/jobs", methods=["GET"])
def get_jobs():
    """Get all jobs with pagination."""
    try:
        limit = min(_safe_int(request.args.get("limit", 100), 100), _MAX_QUERY_LIMIT)
        offset = max(0, _safe_int(request.args.get("offset", 0), 0))
        status_filter = request.args.get("status", None)

        if status_filter and status_filter != "all":
            try:
                status_enum = JobStatus(status_filter)
            except ValueError:
                return jsonify({"error": "Invalid status filter"}), 400
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
                    "prompt": (job.prompt[:200] if len(job.prompt) > 200 else job.prompt) if job.prompt else "",
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
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/jobs/stats", methods=["GET"])
def get_stats():
    """Get queue statistics."""
    try:
        all_jobs = run_async(queue.list_jobs(limit=1000))

        stats = {
            "total": len(all_jobs),
            "queued": sum(1 for j in all_jobs if j.status == JobStatus.QUEUED),
            "processing": sum(1 for j in all_jobs if j.status == JobStatus.PROCESSING),
            "completed": sum(1 for j in all_jobs if j.status == JobStatus.COMPLETED),
            "failed": sum(1 for j in all_jobs if j.status == JobStatus.FAILED),
            "cancelled": sum(1 for j in all_jobs if j.status == JobStatus.CANCELLED),
            "total_cost": sum(j.cost or 0 for j in all_jobs),
            "total_tokens": sum(j.tokens_used or 0 for j in all_jobs),
        }

        return jsonify(stats)

    except Exception:
        logger.exception("Error getting stats")
        return jsonify({"error": "Internal server error"}), 500


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
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    """Delete a job."""
    try:
        job = run_async(queue.get_job(job_id))
        if not job:
            return jsonify({"error": "Job not found"}), 404

        # Mark as cancelled
        if job.status in [JobStatus.QUEUED, JobStatus.PROCESSING]:
            run_async(queue.cancel_job(job_id))
        elif job.status not in [JobStatus.CANCELLED]:
            run_async(queue.update_status(job_id, JobStatus.CANCELLED))

        return jsonify({"success": True})

    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/jobs", methods=["POST"])
@(limiter.limit("10 per minute") if limiter else (lambda f: f))
def submit_job():
    """Submit a new research job."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        prompt = str(data.get("prompt", "")).strip()
        model = str(data.get("model", "o4-mini-deep-research"))
        priority = max(1, min(10, _safe_int(data.get("priority", 3), 3)))
        enable_web_search = data.get("enable_web_search", True)

        if not prompt:
            return jsonify({"error": "Prompt required"}), 400
        if len(prompt) > _MAX_PROMPT_LENGTH:
            return jsonify({"error": f"Prompt exceeds {_MAX_PROMPT_LENGTH} character limit"}), 400
        if model not in _ALLOWED_MODELS:
            return jsonify({"error": "Invalid model"}), 400

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
        metadata = data.get("metadata", {})
        mode = data.get("mode")
        if mode:
            metadata["mode"] = mode
        job = ResearchJob(
            id=job_id,
            prompt=prompt,
            model=model,
            priority=priority,
            enable_web_search=enable_web_search,
            status=JobStatus.QUEUED,
            submitted_at=now,
            metadata=metadata,
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
            run_async(queue.update_status(job_id=job_id, status=JobStatus.FAILED, error=str(e)))
            # Notify WebSocket clients so the job shows up as failed
            job.status = JobStatus.FAILED
            job.last_error = str(e)
            emit_job_failed(socketio, job, str(e))
            return jsonify(
                {
                    "error": "Provider submission failed",
                    "job_id": job_id,
                }
            ), 500

        # Notify connected clients via WebSocket
        job.status = JobStatus.PROCESSING
        job.provider_job_id = provider_job_id
        emit_job_created(socketio, job)

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
        return jsonify({"error": "Internal server error"}), 500


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
        if len(jobs_data) > _MAX_BATCH_SIZE:
            return jsonify({"error": f"Batch size exceeds limit of {_MAX_BATCH_SIZE}"}), 400

        results = []
        for job_input in jobs_data:
            prompt = str(job_input.get("prompt", "")).strip()
            if not prompt:
                continue  # Skip empty prompts
            if len(prompt) > _MAX_PROMPT_LENGTH:
                continue  # Skip oversized prompts
            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            metadata = job_input.get("metadata", {})
            mode = job_input.get("mode")
            if mode:
                metadata["mode"] = mode
            job = ResearchJob(
                id=job_id,
                prompt=prompt,
                model=job_input.get("model", "o4-mini-deep-research"),
                priority=job_input.get("priority", 3),
                enable_web_search=job_input.get("enable_web_search", True),
                status=JobStatus.QUEUED,
                submitted_at=now,
                metadata=metadata,
            )
            run_async(queue.enqueue(job))
            results.append({"job_id": job_id, "status": "queued"})

        return jsonify({"jobs": results, "count": len(results)})

    except Exception as e:
        logger.error(f"Error batch submitting: {e}")
        return jsonify({"error": "Internal server error"}), 500


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
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    """Cancel a job."""
    try:
        success = run_async(queue.cancel_job(job_id))
        return jsonify({"success": success})

    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/jobs/cleanup-stale", methods=["POST"])
def cleanup_stale_jobs():
    """Mark stale PROCESSING/QUEUED jobs as FAILED.

    A job is considered stale if it has been PROCESSING or QUEUED for over
    30 minutes (matching poller threshold), or PROCESSING with no provider_job_id.
    """
    try:
        all_jobs = run_async(queue.list_jobs(limit=10000))
        now = datetime.now(timezone.utc)
        stale_threshold = _STUCK_THRESHOLD  # 30 minutes, same as poller
        cleaned = 0

        for job in all_jobs:
            if job.status not in (JobStatus.QUEUED, JobStatus.PROCESSING):
                continue

            started = job.started_at or job.submitted_at
            if not started:
                continue

            started = _ensure_utc(started)
            is_old = (now - started) > stale_threshold
            is_no_provider = job.status == JobStatus.PROCESSING and not job.provider_job_id

            if is_old or is_no_provider:
                run_async(
                    queue.update_status(
                        job_id=job.id,
                        status=JobStatus.FAILED,
                        error="Cleaned up: stale job",
                    )
                )
                updated_job = run_async(queue.get_job(job.id))
                if updated_job:
                    emit_job_failed(socketio, updated_job, "Cleaned up: stale job")
                cleaned += 1

        return jsonify({"cleaned": cleaned})

    except Exception as e:
        logger.error(f"Error cleaning up stale jobs: {e}")
        return jsonify({"error": "Internal server error"}), 500


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
        daily_spending = sum(
            (j.cost or 0) for j in all_jobs if j.completed_at and _ensure_utc(j.completed_at) >= today_start
        )
        monthly_spending = sum(
            (j.cost or 0) for j in all_jobs if j.completed_at and _ensure_utc(j.completed_at) >= month_start
        )
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
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/cost/trends", methods=["GET"])
def get_cost_trends():
    """Get daily spending trends."""
    try:
        days = max(1, min(_safe_int(request.args.get("days", 30), 30), 365))
        all_jobs = run_async(queue.list_jobs(limit=10000))

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        # Group by day
        daily_costs = {}
        for job in all_jobs:
            if job.completed_at and _ensure_utc(job.completed_at) >= cutoff and job.cost:
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
        return jsonify({"error": "Internal server error"}), 500


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
            if job.completed_at and _ensure_utc(job.completed_at) >= cutoff:
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
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/cost/history", methods=["GET"])
def get_cost_history():
    """Get detailed cost history."""
    try:
        time_range = request.args.get("time_range", "30d")
        days = _parse_time_range(time_range, 30)
        limit = min(_safe_int(request.args.get("limit", 100), 100), _MAX_QUERY_LIMIT)

        all_jobs = run_async(queue.list_jobs(limit=10000))
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        # Filter and sort by completion date
        completed = [j for j in all_jobs if j.completed_at and _ensure_utc(j.completed_at) >= cutoff and j.cost]
        completed.sort(key=lambda j: j.completed_at, reverse=True)

        history = [
            {
                "id": job.id,
                "prompt": (job.prompt or "")[:100],
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
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/cost/estimate", methods=["POST"])
def estimate_cost():
    """Estimate cost for a research prompt."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "JSON body required"}), 400
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
                        (j.cost or 0) for j in all_jobs if j.completed_at and _ensure_utc(j.completed_at) >= today_start
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
        return jsonify({"error": "Internal server error"}), 500


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
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/cost/limits", methods=["PATCH"])
def update_cost_limits():
    """Update budget limits."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Request body required"}), 400

        if cost_controller:
            _MAX_LIMIT = 100_000.0
            for field in ("per_job", "daily", "monthly"):
                if field not in data:
                    continue
                val = data[field]
                if not isinstance(val, (int, float)) or not math.isfinite(val) or val < 0 or val > _MAX_LIMIT:
                    return jsonify({"error": f"{field} must be a finite number between 0 and {_MAX_LIMIT}"}), 400
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
        _save_limits(limits["per_job"], limits["daily"], limits["monthly"])
        return jsonify({"limits": limits, "updated": True})

    except Exception as e:
        logger.error(f"Error updating limits: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# RESULTS API ENDPOINTS
# =============================================================================


@app.route("/api/results", methods=["GET"])
def list_results():
    """List completed research results."""
    try:
        search = request.args.get("search", "")
        sort_by = request.args.get("sort_by", "date")
        limit = min(_safe_int(request.args.get("limit", 50), 50), _MAX_QUERY_LIMIT)
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
            completed.sort(
                key=lambda j: _ensure_utc(j.completed_at)
                or _ensure_utc(j.submitted_at)
                or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )

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
        return jsonify({"error": "Internal server error"}), 500


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
        return jsonify({"error": "Internal server error"}), 500


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
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/results/search", methods=["GET"])
def search_results():
    """Search results by query."""
    try:
        query = request.args.get("q", "")
        limit = min(_safe_int(request.args.get("limit", 20), 20), _MAX_QUERY_LIMIT)

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
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# CONFIG API ENDPOINTS
# =============================================================================

# In-memory config (would normally be persisted)
_config_lock = threading.Lock()
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
        with _config_lock:
            config = {
                **_config,
                "daily_limit": cost_controller.max_daily_cost if cost_controller else 100.0,
                "monthly_limit": cost_controller.max_monthly_cost if cost_controller else 1000.0,
                "has_api_key": bool(os.getenv("OPENAI_API_KEY")),
                "provider_keys": {
                    "openai": bool(os.getenv("OPENAI_API_KEY")),
                    "xai": bool(os.getenv("XAI_API_KEY")),
                    "gemini": bool(os.getenv("GEMINI_API_KEY")),
                    "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
                    "azure-foundry": bool(os.getenv("AZURE_PROJECT_ENDPOINT")),
                },
            }
        return jsonify({"config": config})

    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/config", methods=["PATCH"])
def update_config():
    """Update configuration."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Request body required"}), 400

        # Update allowed fields
        allowed = ["default_model", "default_priority", "enable_web_search"]
        with _config_lock:
            for key in allowed:
                if key in data:
                    _config[key] = data[key]

        # Update cost limits if provided
        if cost_controller:
            if "daily_limit" in data:
                try:
                    cost_controller.max_daily_cost = float(data["daily_limit"])
                except (TypeError, ValueError):
                    return jsonify({"error": "daily_limit must be a number"}), 400
            if "monthly_limit" in data:
                try:
                    cost_controller.max_monthly_cost = float(data["monthly_limit"])
                except (TypeError, ValueError):
                    return jsonify({"error": "monthly_limit must be a number"}), 400
            _save_limits(
                cost_controller.max_cost_per_job,
                cost_controller.max_daily_cost,
                cost_controller.max_monthly_cost,
            )

        return jsonify({"config": _config})

    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# EXPERTS API ENDPOINTS
# =============================================================================


@app.route("/api/experts", methods=["GET"])
def list_experts():
    """List all domain experts."""
    try:
        from deepr.experts.profile_store import ExpertStore

        store = ExpertStore(str(_experts_dir))
        profiles = store.list_all()
        experts = []
        for profile in profiles:
            gap_count = 0
            try:
                manifest = profile.get_manifest()
                gap_count = len(manifest.gaps)
            except Exception:
                pass
            experts.append(
                {
                    "name": profile.name,
                    "description": getattr(profile, "description", "") or "",
                    "document_count": len(getattr(profile, "source_files", [])),
                    "finding_count": len(getattr(profile, "research_jobs", [])),
                    "gap_count": gap_count,
                    "total_cost": getattr(profile, "total_research_cost", 0.0),
                    "last_active": getattr(profile, "updated_at", datetime.now(timezone.utc)).isoformat(),
                    "created_at": getattr(profile, "created_at", datetime.now(timezone.utc)).isoformat(),
                }
            )
        return jsonify({"experts": experts})
    except ImportError:
        return jsonify({"experts": []})
    except Exception as e:
        logger.error(f"Error listing experts: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts", methods=["POST"])
def create_expert():
    """Create a new domain expert (no API calls, $0 cost)."""
    try:
        from deepr.experts.profile import ExpertProfile
        from deepr.experts.profile_store import ExpertStore

        data = request.json
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        name = str(data.get("name", "")).strip()
        if not name:
            return jsonify({"error": "Name required"}), 400
        name_err = _validate_expert_name(name)
        if name_err:
            return jsonify({"error": name_err}), 400

        store = ExpertStore(str(_experts_dir))
        if store.exists(name):
            return jsonify({"error": "Expert already exists"}), 409

        profile = ExpertProfile(
            name=name,
            vector_store_id="",
            description=data.get("description", ""),
            domain=data.get("domain", ""),
        )
        store.save(profile)

        return jsonify(
            {
                "expert": {
                    "name": profile.name,
                    "description": profile.description or "",
                    "document_count": 0,
                    "finding_count": 0,
                    "gap_count": 0,
                    "total_cost": 0,
                    "last_active": profile.updated_at.isoformat(),
                    "created_at": profile.created_at.isoformat(),
                }
            }
        ), 201
    except ImportError:
        return jsonify({"error": "Expert system not available"}), 500
    except Exception as e:
        logger.error(f"Error creating expert: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>", methods=["GET"])
def get_expert(name):
    """Get expert details."""
    try:
        from deepr.experts.profile_store import ExpertStore

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err
        store = ExpertStore(str(_experts_dir))
        if not store.exists(decoded_name):
            return jsonify({"error": "Expert not found"}), 404

        profile = store.load(decoded_name)
        gap_count = 0
        try:
            manifest = profile.get_manifest()
            gap_count = len(manifest.gaps)
        except Exception:
            pass

        return jsonify(
            {
                "expert": {
                    "name": profile.name,
                    "description": getattr(profile, "description", "") or "",
                    "document_count": len(getattr(profile, "source_files", [])),
                    "finding_count": len(getattr(profile, "research_jobs", [])),
                    "gap_count": gap_count,
                    "total_cost": getattr(profile, "total_research_cost", 0.0),
                    "last_active": getattr(profile, "updated_at", datetime.now(timezone.utc)).isoformat(),
                    "created_at": getattr(profile, "created_at", datetime.now(timezone.utc)).isoformat(),
                }
            }
        )
    except ImportError:
        return jsonify({"error": "Expert system not available"}), 404
    except Exception as e:
        logger.error(f"Error getting expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/chat", methods=["POST"])
def chat_with_expert(name):
    """Chat with a domain expert."""
    try:
        data = request.json
        if not data or not data.get("message"):
            return jsonify({"error": "Message required"}), 400
        # Stub — interactive chat requires the full expert system
        decoded_name, err = _decode_expert_name(name)
        if err:
            return err
        return jsonify(
            {
                "response": {
                    "role": "assistant",
                    "content": (
                        f'Web chat with "{decoded_name}" is not yet available. '
                        "You can explore this expert's knowledge using the tabs above:\n\n"
                        "- **Claims** \u2014 verified facts the expert has learned\n"
                        "- **Gaps** \u2014 topics where knowledge is missing\n"
                        "- **Decisions** \u2014 audit trail of research choices\n\n"
                        f'For interactive chat, use the CLI:\n`deepr expert chat "{decoded_name}"`'
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            }
        )
    except Exception as e:
        logger.error(f"Error chatting with expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/gaps", methods=["GET"])
def get_expert_gaps(name):
    """Get scored knowledge gaps for an expert."""
    try:
        from deepr.experts.profile_store import ExpertStore

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err
        store = ExpertStore(str(_experts_dir))
        profile = store.load(decoded_name)
        if not profile:
            return jsonify({"gaps": []})
        manifest = profile.get_manifest()
        return jsonify({"gaps": [g.to_dict() for g in manifest.gaps]})
    except ImportError:
        return jsonify({"gaps": []})
    except Exception as e:
        logger.error(f"Error getting gaps for expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/history", methods=["GET"])
def get_expert_history(name):
    """Get learning history for an expert."""
    try:
        return jsonify({"events": []})
    except Exception as e:
        logger.error(f"Error getting history for expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/manifest", methods=["GET"])
def get_expert_manifest(name):
    """Get full ExpertManifest as JSON."""
    try:
        from deepr.experts.profile_store import ExpertStore

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err
        store = ExpertStore(str(_experts_dir))
        profile = store.load(decoded_name)
        if not profile:
            return jsonify({"error": "Expert not found"}), 404
        manifest = profile.get_manifest()
        return jsonify({"manifest": manifest.to_dict()})
    except ImportError:
        return jsonify({"error": "Expert system not available"}), 404
    except Exception as e:
        logger.error(f"Error getting manifest for expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/claims", methods=["GET"])
def get_expert_claims(name):
    """Get claims for an expert with optional filtering."""
    try:
        from deepr.experts.profile_store import ExpertStore

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err
        domain_filter = request.args.get("domain")
        try:
            min_confidence = float(request.args.get("min_confidence", 0.0))
        except (ValueError, TypeError):
            min_confidence = 0.0

        store = ExpertStore(str(_experts_dir))
        profile = store.load(decoded_name)
        if not profile:
            return jsonify({"claims": []})
        manifest = profile.get_manifest()
        claims = manifest.claims
        if domain_filter:
            claims = [c for c in claims if c.domain == domain_filter]
        if min_confidence > 0:
            claims = [c for c in claims if c.confidence >= min_confidence]
        return jsonify({"claims": [c.to_dict() for c in claims]})
    except ImportError:
        return jsonify({"claims": []})
    except Exception as e:
        logger.error(f"Error getting claims for expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/decisions", methods=["GET"])
def get_expert_decisions(name):
    """Get decision records for an expert with optional filtering."""
    try:
        from deepr.experts.profile_store import ExpertStore

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err
        type_filter = request.args.get("type")
        job_id_filter = request.args.get("job_id")
        limit = min(_safe_int(request.args.get("limit", 50), 50), _MAX_QUERY_LIMIT)

        store = ExpertStore(str(_experts_dir))
        profile = store.load(decoded_name)
        if not profile:
            return jsonify({"decisions": []})
        manifest = profile.get_manifest()
        decisions = manifest.decisions
        if type_filter:
            decisions = [d for d in decisions if d.decision_type.value == type_filter]
        if job_id_filter:
            decisions = [d for d in decisions if d.context.get("job_id") == job_id_filter]
        decisions = decisions[:limit]
        return jsonify({"decisions": [d.to_dict() for d in decisions]})
    except ImportError:
        return jsonify({"decisions": []})
    except Exception as e:
        logger.error(f"Error getting decisions for expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# TRACES API ENDPOINTS
# =============================================================================


@app.route("/api/traces/<job_id>", methods=["GET"])
def get_trace(job_id):
    """Get trace data for a job."""
    try:
        if not all(c in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in job_id.lower()):
            return jsonify({"error": "Invalid job_id"}), 400
        trace_dir = Path("data/traces").resolve()
        trace_path = (trace_dir / f"{job_id}_trace.json").resolve()
        if not str(trace_path).startswith(str(trace_dir)):
            return jsonify({"error": "Invalid job_id"}), 400
        if trace_path.exists():
            import json

            with open(trace_path, encoding="utf-8") as f:
                trace_data = json.load(f)
            return jsonify({"trace": trace_data})
        return jsonify({"trace": None})
    except Exception as e:
        logger.error(f"Error getting trace {job_id}: {e}")
        return jsonify({"error": "Internal error"}), 500


@app.route("/api/traces/<job_id>/temporal", methods=["GET"])
def get_trace_temporal(job_id):
    """Get temporal findings for a trace."""
    try:
        if not all(c in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in job_id.lower()):
            return jsonify({"error": "Invalid job_id"}), 400
        trace_dir = Path("data/traces").resolve()
        trace_path = (trace_dir / f"{job_id}_trace.json").resolve()
        if not str(trace_path).startswith(str(trace_dir)):
            return jsonify({"error": "Invalid job_id"}), 400
        if trace_path.exists():
            import json

            with open(trace_path, encoding="utf-8") as f:
                trace_data = json.load(f)
            findings = trace_data.get("temporal_findings", [])
            return jsonify({"findings": findings})
        return jsonify({"findings": []})
    except Exception as e:
        logger.error(f"Error getting temporal data for {job_id}: {e}")
        return jsonify({"error": "Internal error"}), 500


# =============================================================================
# ACTIVITY API ENDPOINT
# =============================================================================


@app.route("/api/activity", methods=["GET"])
def get_activity():
    """Get recent activity items."""
    try:
        limit = min(_safe_int(request.args.get("limit", 20), 20), _MAX_QUERY_LIMIT)
        all_jobs = run_async(queue.list_jobs(limit=limit * 2))

        # Sort by most recent first
        all_jobs.sort(
            key=lambda j: _ensure_utc(j.submitted_at) or datetime.min.replace(tzinfo=timezone.utc), reverse=True
        )

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
        return jsonify({"error": "Internal server error"}), 500


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
                logger.warning("Connection test failed: %s", e)
                return jsonify({"success": False, "message": "Connection failed"})
        else:
            return jsonify({"success": False, "message": "Provider test not implemented"})

    except Exception as e:
        logger.error(f"Error testing connection: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# BENCHMARKS API ENDPOINTS
# =============================================================================

_benchmark_proc: dict = {}  # pid, process, started_at, output_lines
_benchmark_lock = threading.Lock()
_BENCHMARK_DIR = Path("data/benchmarks")


@app.route("/api/benchmarks", methods=["GET"])
def list_benchmarks():
    """List saved benchmark result files."""
    try:
        if not _BENCHMARK_DIR.exists():
            return jsonify({"benchmarks": []})

        files = sorted(_BENCHMARK_DIR.glob("benchmark_*.json"), reverse=True)
        benchmarks = []
        for f in files:
            try:
                data = _json.loads(f.read_text(encoding="utf-8"))
                rankings = data.get("rankings", [])
                tiers = {r.get("tier", "chat") for r in rankings}
                benchmarks.append(
                    {
                        "filename": f.name,
                        "timestamp": data.get("timestamp", ""),
                        "tier_count": len(tiers),
                        "model_count": len(rankings),
                        "total_cost": round(data.get("total_cost", 0), 4),
                    }
                )
            except Exception:
                continue

        return jsonify({"benchmarks": benchmarks})

    except Exception as e:
        logger.error(f"Error listing benchmarks: {e}")
        return jsonify({"error": "Internal server error"}), 500


def _sanitize_benchmark(data: dict) -> dict:
    """Replace Infinity/NaN with JSON-safe values in benchmark data."""
    for ranking in data.get("rankings", []):
        for key in ("cost_per_quality", "avg_quality", "avg_latency_ms", "total_cost"):
            val = ranking.get(key)
            if isinstance(val, float) and (math.isinf(val) or math.isnan(val)):
                ranking[key] = 0.0
    return data


@app.route("/api/benchmarks/latest", methods=["GET"])
def get_latest_benchmark():
    """Get the best benchmark result (most models, then most recent)."""
    try:
        if not _BENCHMARK_DIR.exists():
            return jsonify({"result": None})

        files = sorted(_BENCHMARK_DIR.glob("benchmark_*.json"), reverse=True)
        if not files:
            return jsonify({"result": None})

        # Pick the file with the most models (most comprehensive run),
        # breaking ties by most recent timestamp
        best_file = None
        best_count = 0
        for f in files:
            try:
                data = _json.loads(f.read_text(encoding="utf-8"))
                count = len([r for r in data.get("rankings", []) if r.get("num_evals", 0) > 0])
                if count > best_count:
                    best_count = count
                    best_file = (f, data)
            except Exception:
                continue

        if not best_file:
            # Fallback to most recent
            data = _sanitize_benchmark(_json.loads(files[0].read_text(encoding="utf-8")))
            return jsonify({"result": data, "filename": files[0].name})

        return jsonify({"result": _sanitize_benchmark(best_file[1]), "filename": best_file[0].name})

    except Exception as e:
        logger.error(f"Error getting latest benchmark: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/benchmarks/<filename>", methods=["GET"])
def get_benchmark(filename):
    """Get a specific benchmark result by filename."""
    try:
        # Validate filename: must match benchmark_YYYYMMDD_HHMMSS.json
        if not re.match(r"^benchmark_\d{8}_\d{6}\.json$", filename):
            return jsonify({"error": "Invalid filename"}), 400

        filepath = (_BENCHMARK_DIR / filename).resolve()
        if not str(filepath).startswith(str(_BENCHMARK_DIR.resolve())):
            return jsonify({"error": "Invalid filename"}), 400

        if not filepath.exists():
            return jsonify({"error": "Benchmark not found"}), 404

        data = _sanitize_benchmark(_json.loads(filepath.read_text(encoding="utf-8")))
        return jsonify({"result": data, "filename": filename})

    except Exception as e:
        logger.error(f"Error getting benchmark {filename}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/benchmarks/estimate", methods=["POST"])
def estimate_benchmark():
    """Estimate cost for a benchmark run (dry-run)."""
    import subprocess

    try:
        data = request.json or {}
        tier = data.get("tier", "all")
        quick = data.get("quick", False)
        no_judge = data.get("no_judge", False)

        if tier not in ("all", "chat", "news", "research", "docs"):
            return jsonify({"error": "Invalid tier"}), 400

        cmd = [sys.executable, "scripts/benchmark_models.py", "--dry-run", "--tier", tier]
        if quick:
            cmd.append("--quick")
        if no_judge:
            cmd.append("--no-judge")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )

        estimated_cost = 0.0
        model_count = 0
        provider_count = 0
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if "Estimated cost:" in stripped:
                try:
                    estimated_cost = float(stripped.split("$")[1])
                except (IndexError, ValueError):
                    pass
            if "models selected" in stripped:
                try:
                    parts = stripped.split(",")
                    provider_count = int(parts[0].strip().split()[0])
                    model_count = int(parts[1].strip().split()[0])
                except (IndexError, ValueError):
                    pass

        return jsonify(
            {
                "estimated_cost": estimated_cost,
                "model_count": model_count,
                "provider_count": provider_count,
                "tier": tier,
            }
        )

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Estimation timed out"}), 504
    except Exception as e:
        logger.error(f"Error estimating benchmark: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/benchmarks/start", methods=["POST"])
def start_benchmark():
    """Start a benchmark run as a subprocess."""
    try:
        import subprocess
        from collections import deque

        with _benchmark_lock:
            # Check if already running
            proc = _benchmark_proc.get("process")
            if proc and proc.poll() is None:
                return jsonify({"error": "Benchmark already running"}), 409

            data = request.json or {}
            tier = data.get("tier", "all")
            quick = data.get("quick", False)
            no_judge = data.get("no_judge", False)

            # Validate tier
            if tier not in ("all", "chat", "news", "research", "docs"):
                return jsonify({"error": "Invalid tier"}), 400

            # Build command
            cmd = [
                sys.executable,
                "scripts/benchmark_models.py",
                "--tier",
                tier,
                "--save",
                "--emit-routing-config",
            ]
            if quick:
                cmd.append("--quick")
            if no_judge:
                cmd.append("--no-judge")

            output_lines: deque = deque(maxlen=200)
            started_at = datetime.now(timezone.utc).isoformat()

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(Path(__file__).resolve().parent.parent.parent),
            )

            _benchmark_proc.update(
                {
                    "pid": proc.pid,
                    "process": proc,
                    "started_at": started_at,
                    "output_lines": output_lines,
                }
            )

            # Reader thread to capture output
            def _read_output():
                try:
                    for line in proc.stdout:
                        output_lines.append(line.rstrip("\n"))
                except Exception:
                    pass

            reader = threading.Thread(target=_read_output, daemon=True, name="benchmark-reader")
            reader.start()

        return jsonify({"status": "started", "started_at": started_at})

    except Exception as e:
        logger.error(f"Error starting benchmark: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/benchmarks/status", methods=["GET"])
def benchmark_status():
    """Get running benchmark status."""
    try:
        with _benchmark_lock:
            proc = _benchmark_proc.get("process")
            if not proc:
                return jsonify({"status": "idle"})

            output_lines = _benchmark_proc.get("output_lines", [])
            last_lines = list(output_lines)[-50:]

            poll = proc.poll()
            if poll is None:
                status = "running"
            elif poll == 0:
                status = "completed"
            else:
                status = "failed"

            return jsonify(
                {
                    "status": status,
                    "started_at": _benchmark_proc.get("started_at"),
                    "exit_code": poll,
                    "output_lines": last_lines,
                }
            )

    except Exception as e:
        logger.error(f"Error getting benchmark status: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/benchmarks/routing-preferences", methods=["GET"])
def get_routing_preferences():
    """Get current routing preferences from benchmark results."""
    try:
        prefs_file = _BENCHMARK_DIR / "routing_preferences.json"
        if not prefs_file.exists():
            return jsonify({"preferences": None})

        data = _json.loads(prefs_file.read_text(encoding="utf-8"))
        return jsonify({"preferences": data})

    except Exception as e:
        logger.error(f"Error getting routing preferences: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# MODEL REGISTRY
# =============================================================================


@app.route("/api/models/registry", methods=["GET"])
def get_model_registry():
    """Return all registered model capabilities for the Models dashboard."""
    try:
        from deepr.providers.registry import MODEL_CAPABILITIES

        models = []
        for key, cap in MODEL_CAPABILITIES.items():
            models.append(
                {
                    "model_key": key,
                    "provider": cap.provider,
                    "model": cap.model,
                    "cost_per_query": cap.cost_per_query,
                    "input_cost_per_1m": cap.input_cost_per_1m,
                    "output_cost_per_1m": cap.output_cost_per_1m,
                    "latency_ms": cap.latency_ms,
                    "context_window": cap.context_window,
                    "specializations": cap.specializations,
                    "strengths": cap.strengths,
                    "weaknesses": cap.weaknesses,
                }
            )
        return jsonify({"models": models})

    except Exception as e:
        logger.error(f"Error getting model registry: {e}")
        return jsonify({"error": "Internal server error"}), 500


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
                "version": "2.8.1",
                "provider": "openai",
                "queue": "sqlite",
                "storage": "local",
            }
        )

    except Exception as e:
        logger.error("Health check failed: %s", e)
        return jsonify({"status": "unhealthy", "error": "Service unavailable"}), 500


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  Deepr Research Dashboard")
    print("  Running on http://localhost:5000")
    print("=" * 70 + "\n")
    import os as _os

    debug = _os.environ.get("FLASK_DEBUG", "0") == "1"
    socketio.run(app, debug=debug, host="0.0.0.0", port=5000)
