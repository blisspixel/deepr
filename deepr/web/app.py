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
import random
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
        daily_limit = cost_controller.max_daily_cost if cost_controller else 10.0
        monthly_limit = cost_controller.max_monthly_cost if cost_controller else 100.0
        per_job_limit = cost_controller.max_cost_per_job if cost_controller else 10.0

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
            "per_job": cost_controller.max_cost_per_job if cost_controller else 10.0,
            "daily": cost_controller.max_daily_cost if cost_controller else 10.0,
            "monthly": cost_controller.max_monthly_cost if cost_controller else 100.0,
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
            "per_job": cost_controller.max_cost_per_job if cost_controller else 10.0,
            "daily": cost_controller.max_daily_cost if cost_controller else 10.0,
            "monthly": cost_controller.max_monthly_cost if cost_controller else 100.0,
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
                key=lambda j: (
                    _ensure_utc(j.completed_at)
                    or _ensure_utc(j.submitted_at)
                    or datetime.min.replace(tzinfo=timezone.utc)
                ),
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
                "daily_limit": cost_controller.max_daily_cost if cost_controller else 10.0,
                "monthly_limit": cost_controller.max_monthly_cost if cost_controller else 100.0,
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
                    "portrait_url": getattr(profile, "portrait_url", None),
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
                    "portrait_url": getattr(profile, "portrait_url", None),
                }
            }
        )
    except ImportError:
        return jsonify({"error": "Expert system not available"}), 404
    except Exception as e:
        logger.error(f"Error getting expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/generate-portrait", methods=["POST"])
def generate_expert_portrait(name):
    """Generate an AI portrait for a domain expert."""
    try:
        from deepr.experts.portraits import generate_portrait
        from deepr.experts.profile_store import ExpertStore

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err
        store = ExpertStore(str(_experts_dir))
        if not store.exists(decoded_name):
            return jsonify({"error": "Expert not found"}), 404

        profile = store.load(decoded_name)

        data = request.json or {}
        provider = data.get("provider")  # optional override

        loop = asyncio.new_event_loop()
        try:
            portrait_url = loop.run_until_complete(
                generate_portrait(
                    name=profile.name,
                    domain=getattr(profile, "domain", None),
                    description=getattr(profile, "description", None),
                    provider=provider,
                    output_dir=str(Path("data") / "portraits"),
                )
            )
        finally:
            loop.close()

        profile.portrait_url = portrait_url
        store.save(profile)

        return jsonify({"portrait_url": portrait_url})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error generating portrait for {name}: {e}")
        return jsonify({"error": "Portrait generation failed"}), 500


@app.route("/portraits/<path:filename>")
def serve_portrait(filename):
    """Serve a generated portrait image."""
    portraits_dir = Path("data") / "portraits"
    return send_from_directory(str(portraits_dir.resolve()), filename)


@app.route("/api/experts/<name>/chat", methods=["POST"])
def chat_with_expert(name):
    """Chat with a domain expert."""
    try:
        data = request.json
        if not data or not data.get("message"):
            return jsonify({"error": "Message required"}), 400

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err

        from deepr.experts.chat import start_chat_session

        message = data["message"]
        session_id = data.get("session_id")

        # Create or restore session
        session = run_async(start_chat_session(decoded_name, budget=10.0, agentic=True, quiet=True))

        if session_id:
            _restore_session_messages(session, decoded_name, session_id)

        # Get response
        response_text = run_async(session.send_message(message))

        # Persist conversation
        session_id = session.save_conversation(session_id)

        # Summarize tool calls from reasoning trace
        tool_calls = [
            {"tool": t["step"], "query": t.get("query", "")[:200]}
            for t in session.reasoning_trace
            if t.get("step") in ("search_knowledge_base", "standard_research", "deep_research", "skill_tool_call")
        ]

        import uuid

        # Extract confidence from uncertainty
        confidence = 0.9
        uncertainty_phrases = [
            "i don't know",
            "i'm not sure",
            "i don't have",
            "no information",
            "not in my knowledge",
        ]
        if response_text and any(p in response_text.lower() for p in uncertainty_phrases):
            confidence = 0.3

        return jsonify(
            {
                "response": {
                    "id": uuid.uuid4().hex[:12],
                    "role": "assistant",
                    "content": response_text,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "session_id": session_id,
                    "cost": round(session.cost_accumulated, 4),
                    "tool_calls": tool_calls,
                    "confidence": confidence,
                }
            }
        )
    except ImportError:
        return jsonify({"error": "Expert system not available"}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"Error chatting with expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/council", methods=["POST"])
def expert_council():
    """Consult multiple experts on a query."""
    try:
        data = request.json
        if not data or not data.get("query"):
            return jsonify({"error": "query required"}), 400

        from deepr.experts.council import ExpertCouncil

        council = ExpertCouncil()
        result = run_async(
            council.consult(
                query=data["query"],
                budget=data.get("budget", 5.0),
            )
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Council error: {e}")
        return jsonify({"error": str(e)}), 500


def _restore_session_messages(session, expert_name: str, session_id: str):
    """Restore conversation messages from a saved session file."""
    from deepr.experts.profile import ExpertStore

    store = ExpertStore(str(_experts_dir))
    conversations_dir = store.get_conversations_dir(expert_name)
    conversation_file = conversations_dir / f"{session_id}.json"

    if conversation_file.exists():
        import json as _json

        with open(conversation_file, encoding="utf-8") as f:
            data = _json.load(f)
        saved_messages = data.get("messages", [])
        for msg in saved_messages:
            if msg.get("role") in ("user", "assistant"):
                session.messages.append({"role": msg["role"], "content": msg["content"]})


@app.route("/api/experts/<name>/conversations", methods=["GET"])
def list_expert_conversations(name):
    """List saved conversations for an expert."""
    try:
        import json as _json

        from deepr.experts.profile_store import ExpertStore

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err
        store = ExpertStore(str(_experts_dir))
        conversations_dir = store.get_conversations_dir(decoded_name)
        if not conversations_dir.exists():
            return jsonify({"conversations": []})

        conversations = []
        for f in sorted(conversations_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = _json.load(fh)
                messages = data.get("messages", [])
                summary = data.get("summary", {})
                # Build preview from first user message
                preview = ""
                for m in messages:
                    if m.get("role") == "user":
                        preview = m.get("content", "")[:100]
                        break
                conversations.append(
                    {
                        "session_id": data.get("session_id", f.stem),
                        "started_at": data.get("started_at", ""),
                        "message_count": len(messages),
                        "preview": preview,
                        "cost": summary.get("cost_accumulated", 0.0),
                    }
                )
            except Exception:
                continue
        return jsonify({"conversations": conversations})
    except ImportError:
        return jsonify({"conversations": []})
    except Exception as e:
        logger.error(f"Error listing conversations for expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/conversations/<session_id>", methods=["GET"])
def get_expert_conversation(name, session_id):
    """Load a full conversation."""
    try:
        import json as _json

        from deepr.experts.profile_store import ExpertStore

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err
        store = ExpertStore(str(_experts_dir))
        conversations_dir = store.get_conversations_dir(decoded_name)
        conversation_file = conversations_dir / f"{session_id}.json"

        if not conversation_file.exists():
            return jsonify({"error": "Conversation not found"}), 404

        with open(conversation_file, encoding="utf-8") as f:
            data = _json.load(f)

        return jsonify(
            {
                "session_id": data.get("session_id", session_id),
                "messages": [
                    {"role": m["role"], "content": m["content"]}
                    for m in data.get("messages", [])
                    if m.get("role") in ("user", "assistant")
                ],
                "summary": data.get("summary", {}),
            }
        )
    except ImportError:
        return jsonify({"error": "Expert system not available"}), 404
    except Exception as e:
        logger.error(f"Error loading conversation {session_id} for {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/conversations/<session_id>", methods=["DELETE"])
def delete_expert_conversation(name, session_id):
    """Delete a conversation."""
    try:
        from deepr.experts.profile_store import ExpertStore

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err
        store = ExpertStore(str(_experts_dir))
        conversations_dir = store.get_conversations_dir(decoded_name)
        conversation_file = conversations_dir / f"{session_id}.json"

        if not conversation_file.exists():
            return jsonify({"error": "Conversation not found"}), 404

        conversation_file.unlink()
        return jsonify({"status": "deleted"})
    except ImportError:
        return jsonify({"error": "Expert system not available"}), 404
    except Exception as e:
        logger.error(f"Error deleting conversation {session_id} for {name}: {e}")
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


@app.route("/api/experts/<name>/fill-gaps", methods=["POST"])
def fill_expert_gaps(name):
    """Fill knowledge gaps with optional consensus and deep pipeline."""
    try:
        import asyncio

        from deepr.experts.profile_store import ExpertStore
        from deepr.experts.synthesis import Worldview

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err
        data = request.get_json() or {}
        use_consensus = data.get("consensus", False)
        use_deep = data.get("deep", False)
        top = min(data.get("top", 3), 10)
        budget = min(data.get("budget", 5.0), 50.0)

        store = ExpertStore(str(_experts_dir))
        profile = store.load(decoded_name)
        if not profile:
            return jsonify({"error": f"Expert not found: {decoded_name}"}), 404

        knowledge_dir = store.get_knowledge_dir(decoded_name)
        worldview_path = knowledge_dir / "worldview.json"
        if not worldview_path.exists():
            return jsonify({"error": "Expert has no worldview yet"}), 400

        worldview = Worldview.load(worldview_path)
        if not worldview.knowledge_gaps:
            return jsonify({"filled": 0, "message": "No gaps to fill"})

        sorted_gaps = sorted(worldview.knowledge_gaps, key=lambda g: g.priority, reverse=True)[:top]

        async def _do_fill():
            from deepr.config import AppConfig
            from deepr.providers import create_provider

            config = AppConfig.from_env()
            provider = create_provider("openai", api_key=config.provider.openai_api_key)
            filled = 0

            if use_deep:
                from deepr.experts.multi_pass import MultiPassPipeline

                consensus_engine = None
                if use_consensus:
                    from deepr.experts.consensus import ConsensusEngine

                    consensus_engine = ConsensusEngine()

                pipeline = MultiPassPipeline(client=provider.client, consensus_engine=consensus_engine)
                existing_claims = [b.to_dict() for b in worldview.beliefs[:30]]

                for gap in sorted_gaps:
                    result = await pipeline.fill_gap(
                        gap=gap,
                        existing_claims=existing_claims,
                        expert_name=profile.name,
                        domain=profile.domain or profile.description,
                        budget=budget / len(sorted_gaps),
                        use_consensus=use_consensus,
                    )
                    if result.filled:
                        filled += 1

            return {"filled": filled, "total_gaps": len(sorted_gaps)}

        result = asyncio.run(_do_fill())
        return jsonify(result)
    except ImportError:
        return jsonify({"error": "Required dependencies not installed"}), 500
    except Exception as e:
        logger.error(f"Error filling gaps for expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/citation-validations", methods=["GET"])
def get_citation_validations(name):
    """Get citation validation results for an expert."""
    try:
        import asyncio

        from deepr.experts.profile_store import ExpertStore
        from deepr.experts.synthesis import Worldview

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err

        store = ExpertStore(str(_experts_dir))
        profile = store.load(decoded_name)
        if not profile:
            return jsonify({"validations": [], "summary": {}})

        knowledge_dir = store.get_knowledge_dir(decoded_name)
        worldview_path = knowledge_dir / "worldview.json"
        if not worldview_path.exists():
            return jsonify({"validations": [], "summary": {}})

        worldview = Worldview.load(worldview_path)
        if not worldview.beliefs:
            return jsonify({"validations": [], "summary": {}})

        async def _do_validate():
            from deepr.config import AppConfig
            from deepr.experts.citation_validator import CitationValidator
            from deepr.providers import create_provider

            config = AppConfig.from_env()
            provider = create_provider("openai", api_key=config.provider.openai_api_key)
            validator = CitationValidator(client=provider.client)

            claims = [b.to_claim() for b in worldview.beliefs]
            docs_dir = store.get_documents_dir(decoded_name)
            doc_dict = {}
            for doc_path in docs_dir.glob("*.md"):
                try:
                    doc_dict[doc_path.name] = doc_path.read_text(encoding="utf-8")[:2000]
                except OSError:
                    pass

            validations = await validator.validate_claims(claims, doc_dict)
            summary = validator.summarize(validations)
            return [v.to_dict() for v in validations], summary

        validations, summary = asyncio.run(_do_validate())
        return jsonify({"validations": validations, "summary": summary})
    except ImportError:
        return jsonify({"validations": [], "summary": {}})
    except Exception as e:
        logger.error(f"Error validating citations for expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/discover-gaps", methods=["POST"])
def discover_expert_gaps(name):
    """Trigger automated gap discovery for an expert."""
    try:
        import asyncio

        from deepr.experts.profile_store import ExpertStore
        from deepr.experts.synthesis import Worldview

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err

        store = ExpertStore(str(_experts_dir))
        profile = store.load(decoded_name)
        if not profile:
            return jsonify({"error": f"Expert not found: {decoded_name}"}), 404

        knowledge_dir = store.get_knowledge_dir(decoded_name)
        worldview_path = knowledge_dir / "worldview.json"
        if not worldview_path.exists():
            return jsonify({"error": "Expert has no worldview yet"}), 400

        worldview = Worldview.load(worldview_path)
        if not worldview.beliefs:
            return jsonify({"gaps": []})

        async def _do_discover():
            from deepr.experts.gap_discovery import GapDiscoverer

            discoverer = GapDiscoverer()
            claims = [b.to_claim().to_dict() for b in worldview.beliefs]
            existing_gaps = [g.to_dict() for g in worldview.knowledge_gaps]
            return await discoverer.discover_gaps(claims, profile.domain or "", existing_gaps)

        new_gaps = asyncio.run(_do_discover())
        return jsonify({"gaps": new_gaps})
    except ImportError:
        return jsonify({"gaps": []})
    except Exception as e:
        logger.error(f"Error discovering gaps for expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/resolve-conflicts", methods=["POST"])
def resolve_expert_conflicts(name):
    """Trigger conflict resolution for an expert."""
    try:
        import asyncio

        from deepr.experts.profile_store import ExpertStore
        from deepr.experts.synthesis import Worldview

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err
        data = request.get_json() or {}
        budget = min(data.get("budget", 5.0), 50.0)

        store = ExpertStore(str(_experts_dir))
        profile = store.load(decoded_name)
        if not profile:
            return jsonify({"error": f"Expert not found: {decoded_name}"}), 404

        knowledge_dir = store.get_knowledge_dir(decoded_name)
        worldview_path = knowledge_dir / "worldview.json"
        if not worldview_path.exists():
            return jsonify({"error": "Expert has no worldview yet"}), 400

        worldview = Worldview.load(worldview_path)
        if not worldview.beliefs:
            return jsonify({"results": []})

        async def _do_resolve():
            from deepr.config import AppConfig
            from deepr.experts.beliefs import Belief as BeliefObj
            from deepr.experts.conflict_resolver import ConflictResolver
            from deepr.providers import create_provider

            config = AppConfig.from_env()
            provider = create_provider("openai", api_key=config.provider.openai_api_key)
            resolver = ConflictResolver(client=provider.client)

            belief_objects = []
            for b in worldview.beliefs:
                belief_objects.append(
                    BeliefObj(
                        claim=b.statement,
                        confidence=b.confidence,
                        evidence_refs=b.evidence,
                        domain=b.topic,
                    )
                )
            results = await resolver.resolve_all(belief_objects, budget=budget)
            return [r.to_dict() for r in results]

        results = asyncio.run(_do_resolve())
        return jsonify({"results": results})
    except ImportError:
        return jsonify({"results": []})
    except Exception as e:
        logger.error(f"Error resolving conflicts for expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# =============================================================================
# SKILLS API ENDPOINTS
# =============================================================================


@app.route("/api/skills", methods=["GET"])
def list_all_skills():
    """List all available skills."""
    try:
        from deepr.experts.skills import SkillManager

        manager = SkillManager()
        skills = [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "tools": len(s.tools),
                "tier": s.tier,
                "domains": s.domains,
                "installed": False,
            }
            for s in manager.list_all()
        ]
        return jsonify({"skills": skills})
    except Exception as e:
        logger.error(f"Error listing skills: {e}")
        return jsonify({"skills": []})


@app.route("/api/experts/<name>/skills", methods=["GET"])
def list_expert_skills(name):
    """List installed and available skills for an expert."""
    try:
        from deepr.experts.profile_store import ExpertStore
        from deepr.experts.skills import SkillManager

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err

        store = ExpertStore(str(_experts_dir))
        profile = store.load(decoded_name)
        if not profile:
            return jsonify({"error": f"Expert not found: {decoded_name}"}), 404

        manager = SkillManager(expert_name=decoded_name)
        installed_names = set(getattr(profile, "installed_skills", []))

        installed = []
        for s in manager.get_installed_skills(list(installed_names)):
            installed.append(
                {
                    "name": s.name,
                    "description": s.description,
                    "version": s.version,
                    "tools": len(s.tools),
                    "tier": s.tier,
                    "domains": s.domains,
                    "installed": True,
                }
            )

        available = []
        for s in manager.list_all():
            if s.name not in installed_names:
                available.append(
                    {
                        "name": s.name,
                        "description": s.description,
                        "version": s.version,
                        "tools": len(s.tools),
                        "tier": s.tier,
                        "domains": s.domains,
                        "installed": False,
                    }
                )

        return jsonify({"installed_skills": installed, "available_skills": available})
    except Exception as e:
        logger.error(f"Error listing skills for expert {name}: {e}")
        return jsonify({"installed_skills": [], "available_skills": []})


@app.route("/api/experts/<name>/skills/<skill_name>", methods=["POST"])
def install_expert_skill(name, skill_name):
    """Install a skill on an expert."""
    try:
        from deepr.experts.profile_store import ExpertStore
        from deepr.experts.skills import SkillManager

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err

        store = ExpertStore(str(_experts_dir))
        profile = store.load(decoded_name)
        if not profile:
            return jsonify({"error": f"Expert not found: {decoded_name}"}), 404

        manager = SkillManager(expert_name=decoded_name)
        skill_def = manager.get_skill(skill_name)
        if not skill_def:
            return jsonify({"error": f"Skill not found: {skill_name}"}), 404

        installed = getattr(profile, "installed_skills", [])
        if skill_name in installed:
            return jsonify({"status": "already_installed"})

        profile.installed_skills = [*installed, skill_name]
        store.save(profile)

        return jsonify({"status": "installed"})
    except Exception as e:
        logger.error(f"Error installing skill {skill_name} on expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/skills/<skill_name>", methods=["DELETE"])
def remove_expert_skill(name, skill_name):
    """Remove a skill from an expert."""
    try:
        from deepr.experts.profile_store import ExpertStore

        decoded_name, err = _decode_expert_name(name)
        if err:
            return err

        store = ExpertStore(str(_experts_dir))
        profile = store.load(decoded_name)
        if not profile:
            return jsonify({"error": f"Expert not found: {decoded_name}"}), 404

        installed = getattr(profile, "installed_skills", [])
        if skill_name not in installed:
            return jsonify({"status": "not_installed"})

        profile.installed_skills = [s for s in installed if s != skill_name]
        store.save(profile)

        return jsonify({"status": "removed"})
    except Exception as e:
        logger.error(f"Error removing skill {skill_name} from expert {name}: {e}")
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
# DEMO DATA
# =============================================================================


@app.route("/api/demo/load", methods=["POST"])
def load_demo_data():
    """Load demo experts and sample completed jobs."""
    import subprocess

    errors = []

    # 1. Run demo experts script
    try:
        result = subprocess.run(
            [sys.executable, "scripts/create_demo_experts.py"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        if result.returncode != 0:
            errors.append(f"Demo experts: {result.stderr[:200]}")
    except Exception as e:
        errors.append(f"Demo experts: {e}")

    # 2. Clear existing jobs to remove stale/garbage data, then seed fresh demo
    try:
        import sqlite3

        db_path = _cfg.get("queue_db_path", str(config_path / "queue.db"))
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM research_queue")
        conn.commit()
        conn.close()
    except Exception as e:
        errors.append(f"Clear jobs: {e}")

    created_jobs = 0
    now = datetime.now(timezone.utc)
    # Short demo reports (~600-1000 words each) so result-detail renders real content
    demo_reports = [
        # 0: Quantum error correction
        "# Quantum Error Correction: 2025-2026 Breakthroughs\n\n"
        "## Executive Summary\n\n"
        "The past 18 months have seen transformative advances in quantum error correction (QEC), "
        "bringing fault-tolerant quantum computing meaningfully closer to reality. Google's Willow "
        "chip demonstrated below-threshold surface code performance, while Microsoft's topological "
        "qubits achieved their first logical operations. This report surveys the key breakthroughs, "
        "compares approaches, and assesses the timeline to practical fault tolerance.\n\n"
        "## Key Findings\n\n"
        "### Surface Codes Hit Inflection Point\n\n"
        "Google's 105-qubit Willow processor achieved a landmark result: increasing code distance "
        "from 3 to 7 reduced logical error rates exponentially, falling below the critical threshold "
        "for the first time. At distance-7, the logical error rate reached 1 in 10^7 per cycle, "
        "roughly a 10x improvement per additional distance step. IBM followed with similar results "
        "on their Heron architecture, demonstrating that surface code scaling is reproducible across "
        "hardware platforms.\n\n"
        "### Topological Approaches Mature\n\n"
        "Microsoft announced the first topological qubit operations using Majorana-based hardware, "
        "achieving a two-qubit gate fidelity of 99.2%. While still behind superconducting surface "
        "codes in absolute performance, the inherent noise protection of topological qubits means "
        "fewer physical qubits per logical qubit\u2014potentially 10-100x fewer at scale. Academic groups "
        "at Delft and Copenhagen independently verified the Majorana signatures, strengthening "
        "confidence in the approach.\n\n"
        "### Hybrid and Novel Codes\n\n"
        "Several groups explored LDPC (low-density parity-check) codes that promise better encoding "
        "rates than surface codes. Quantinuum demonstrated a [[144,12,12]] bivariate bicycle code "
        "on trapped-ion hardware, encoding 12 logical qubits with a code distance of 12\u2014a "
        "significant step toward more efficient quantum memory. Additionally, bosonic codes using "
        "cat states in superconducting cavities showed error rates compatible with concatenation "
        "into surface codes, offering a promising hybrid path.\n\n"
        "## Implications\n\n"
        "These results collectively suggest that a 1,000-logical-qubit machine\u2014sufficient for "
        "meaningful quantum chemistry and optimization\u2014could be achievable within 5-8 years, "
        "assuming current scaling trends hold. The primary bottleneck has shifted from physics to "
        "engineering: fabrication yield, cryogenic wiring, and classical decoding throughput.\n\n"
        "## References\n\n"
        "- [Google Quantum AI \u2013 Willow Results](https://blog.google/technology/research/google-willow-quantum-chip/)\n"
        "- [Microsoft Topological Qubits](https://news.microsoft.com/source/features/innovation/microsofts-majorana-1-chip/)\n"
        "- [Quantinuum LDPC Demonstration](https://www.quantinuum.com/blog/logical-qubits)\n"
        "- [Nature \u2013 Surface Code Threshold](https://www.nature.com/articles/s41586-024-08449-y)\n",
        # 1: Carbon border adjustment
        "# Carbon Border Adjustment Mechanisms: Cross-Regional Economic Impact\n\n"
        "## Executive Summary\n\n"
        "Carbon border adjustment mechanisms (CBAMs) are reshaping global trade flows as the EU's "
        "mechanism enters its definitive phase and the US considers parallel legislation. This "
        "analysis examines the economic impact across major trading blocs, with particular attention "
        "to effects on developing nations and potential WTO compatibility challenges.\n\n"
        "## Key Findings\n\n"
        "### EU CBAM Implementation\n\n"
        "The EU's CBAM, which began its transitional reporting phase in October 2023 and moves to "
        "full financial adjustment in 2026, covers cement, iron and steel, aluminium, fertilizers, "
        "electricity, and hydrogen. Early data shows a 12-18% reduction in carbon-intensive imports "
        "from non-EU countries, with significant trade diversion toward suppliers in countries with "
        "comparable carbon pricing. Turkey and Ukraine have been most affected, while North African "
        "producers face the steepest compliance costs relative to GDP.\n\n"
        "### US Policy Landscape\n\n"
        "The US has not enacted a federal carbon border tax, but the PROVE IT Act (introduced 2024) "
        "and the Foreign Pollution Fee Act represent bipartisan momentum. Analysis suggests a US "
        "CBAM modeled on the EU approach would generate $6-10 billion annually, primarily from "
        "imports of steel, aluminum, and cement from China and India. However, the absence of a "
        "domestic carbon price complicates WTO justification.\n\n"
        "### Developing Nation Impact\n\n"
        "For many developing economies, CBAMs represent a significant trade barrier. Our modeling "
        "shows GDP impacts ranging from -0.3% to -1.2% for carbon-intensive exporters like India, "
        "Vietnam, and Egypt. However, nations investing in renewable energy infrastructure\u2014"
        "particularly Morocco, Chile, and Kenya\u2014are positioning themselves as preferred suppliers. "
        "The key policy question is whether CBAM revenue should fund climate adaptation in affected "
        "developing countries.\n\n"
        "## Trade Flow Analysis\n\n"
        "Using a computable general equilibrium model, we find that global trade in CBAM-covered "
        "sectors shifts by approximately $47 billion annually under full implementation. Winners "
        "include domestic EU producers and low-carbon exporters; losers are concentrated in "
        "fossil-fuel-dependent economies. Carbon leakage risk drops by 30-40% compared to "
        "unilateral carbon pricing without border adjustment.\n\n"
        "## References\n\n"
        "- [European Commission \u2013 CBAM Overview](https://taxation-customs.ec.europa.eu/carbon-border-adjustment-mechanism_en)\n"
        "- [World Bank \u2013 Carbon Pricing Dashboard](https://carbonpricingdashboard.worldbank.org/)\n"
        "- [IMF Working Paper \u2013 Border Carbon Adjustments](https://www.imf.org/en/Publications/WP)\n"
        "- [UNCTAD \u2013 Trade and Climate Change](https://unctad.org/topic/trade-and-environment)\n",
        # 2: React Server Components vs SSR
        "# React Server Components vs Traditional SSR\n\n"
        "## Executive Summary\n\n"
        "React Server Components (RSC) represent a fundamental shift in how React applications "
        "handle server-side rendering. Unlike traditional SSR which renders the full component tree "
        "on the server and hydrates on the client, RSC allows individual components to execute "
        "exclusively on the server while seamlessly integrating with interactive client components. "
        "This report benchmarks performance, evaluates developer experience, and provides migration "
        "guidance for enterprise teams.\n\n"
        "## Key Findings\n\n"
        "### Performance Benchmarks\n\n"
        "In our testing across three representative enterprise applications (e-commerce, dashboard, "
        "content site), RSC delivered:\n\n"
        "- **35-45% smaller JavaScript bundles** due to server-only dependencies never reaching the client\n"
        "- **20-30% faster Time to Interactive (TTI)** by eliminating hydration for static content\n"
        "- **15-25% reduction in API calls** as data fetching moves to the server component layer\n\n"
        "Traditional SSR with streaming (React 18) narrows the gap on initial load metrics but "
        "cannot match RSC's bundle size advantages for content-heavy pages.\n\n"
        "### Developer Experience\n\n"
        "RSC introduces a new mental model: the 'use client' directive creates a clear boundary "
        "between server and client code. In our developer survey (n=128 enterprise developers), "
        "67% reported the boundary confusing initially but valuable once understood. The primary "
        "friction points are: inability to use hooks in server components, serialization constraints "
        "on props passed across the boundary, and debugging complexity with mixed execution environments.\n\n"
        "### Migration Strategy\n\n"
        "For enterprise applications, we recommend an incremental approach:\n\n"
        "1. Start with leaf components that fetch data (tables, lists, detail views)\n"
        "2. Convert layout and navigation components that don't need interactivity\n"
        "3. Keep form components, modals, and stateful widgets as client components\n"
        "4. Adopt Next.js App Router as the framework layer\u2014it provides the most mature RSC "
        "implementation with caching, routing, and streaming support\n\n"
        "## References\n\n"
        "- [React \u2013 Server Components RFC](https://react.dev/blog/2023/03/22/react-labs-what-we-have-been-working-on-march-2023)\n"
        "- [Next.js \u2013 App Router Documentation](https://nextjs.org/docs/app)\n"
        "- [Vercel \u2013 RSC Performance Study](https://vercel.com/blog)\n",
        # 3: Autonomous vehicle regulation
        "# Autonomous Vehicle Regulation: Global Status Report (2026)\n\n"
        "## Executive Summary\n\n"
        "Autonomous vehicle (AV) regulation has entered a critical phase as Level 4 commercial "
        "deployments expand globally. This report surveys the liability frameworks, safety standards, "
        "and insurance models emerging across major jurisdictions, highlighting both convergence and "
        "divergence in regulatory approaches.\n\n"
        "## Key Findings\n\n"
        "### Liability Frameworks\n\n"
        "Three distinct liability models have emerged. The US follows a manufacturer-liability "
        "approach where the AV developer assumes liability for crashes in autonomous mode, with "
        "state-level variations. The EU's revised Product Liability Directive (2024) applies strict "
        "liability to AI systems including AVs, with a rebuttable presumption of defect when AI "
        "causes harm. China's approach assigns liability to the vehicle operator by default, with "
        "provisions for manufacturer liability only when defects are proven\u2014creating a more "
        "conservative framework.\n\n"
        "### Safety Standards\n\n"
        "UNECE WP.29 adopted the Automated Lane Keeping System (ALKS) regulation, now recognized "
        "by 47 countries. The US NHTSA issued its final AV safety framework (AVSSF) in 2025, "
        "establishing minimum performance requirements for perception, planning, and fallback "
        "systems. Notably, these standards require a minimum of 10 million miles of validated "
        "testing data and 1,000 hours of scenario-based testing covering 500+ edge cases.\n\n"
        "### Insurance Models\n\n"
        "The insurance industry has developed AV-specific products: single-vehicle policies covering "
        "both conventional and autonomous modes (pioneered by Allianz), fleet-level insurance for "
        "robotaxi operators (led by Munich Re), and parametric policies triggered by specific AV "
        "system failures. Premiums for Level 4 fleets are currently 40-60% higher than comparable "
        "human-driven fleets, but insurers project parity by 2028 as actuarial data accumulates.\n\n"
        "## Outlook\n\n"
        "Regulatory harmonization remains the key challenge. While technical standards are converging "
        "through UNECE, liability frameworks diverge significantly. Companies operating across "
        "jurisdictions face compliance costs of $5-15 million annually for regulatory adaptation.\n\n"
        "## References\n\n"
        "- [UNECE \u2013 Automated Driving Regulations](https://unece.org/transport/vehicle-regulations)\n"
        "- [NHTSA \u2013 AV Safety Framework](https://www.nhtsa.gov/technology-innovation/automated-vehicles-safety)\n"
        "- [European Commission \u2013 AI Liability Directive](https://commission.europa.eu/legal-notice_en)\n"
        "- [McKinsey \u2013 AV Insurance Market](https://www.mckinsey.com/industries/automotive-and-assembly)\n"
        "- [SAE International \u2013 J3016 Automation Levels](https://www.sae.org/standards/content/j3016_202104/)\n",
        # 4: LLM alignment techniques
        "# Large Language Model Alignment Techniques: A Systematic Review\n\n"
        "## Executive Summary\n\n"
        "Aligning large language models with human values and intentions remains one of the most "
        "critical challenges in AI development. This review compares the major alignment approaches\u2014"
        "RLHF, DPO, Constitutional AI, and newer methods\u2014evaluating their effectiveness, "
        "scalability, and limitations based on published research through early 2026.\n\n"
        "## Key Findings\n\n"
        "### RLHF (Reinforcement Learning from Human Feedback)\n\n"
        "RLHF remains the most widely deployed alignment technique. The standard pipeline\u2014"
        "supervised fine-tuning, reward model training, and PPO optimization\u2014has been refined "
        "significantly since its introduction. Key improvements include reward model ensembles to "
        "reduce reward hacking, KL-penalty scheduling for training stability, and process-based "
        "reward models that evaluate reasoning steps rather than final outputs. However, RLHF's "
        "reliance on human annotators creates scalability bottlenecks: annotation costs run "
        "$2-5 per comparison, and inter-annotator agreement rarely exceeds 75%.\n\n"
        "### DPO (Direct Preference Optimization)\n\n"
        "DPO eliminates the separate reward model by directly optimizing the language model on "
        "preference pairs. This reduces training complexity and cost by approximately 40%. "
        "Benchmarks show DPO achieves comparable alignment quality to RLHF on standard evaluations "
        "(MT-Bench, AlpacaEval), with some evidence of superior performance on nuanced reasoning "
        "tasks. Variants like IPO and KTO further improve robustness to noisy preferences.\n\n"
        "### Constitutional AI and Self-Alignment\n\n"
        "Anthropic's Constitutional AI approach uses a set of principles to guide model self-critique "
        "and revision, reducing dependence on human feedback. Recent work extends this with automated "
        "red-teaming and principle discovery, where models generate and refine their own alignment "
        "criteria. The approach scales well but tends to produce overly cautious models without "
        "careful calibration of constitutional principles.\n\n"
        "### Emerging Approaches\n\n"
        "Newer methods include: debate-based alignment where models argue opposing positions; "
        "scalable oversight through recursive reward modeling; and representation engineering that "
        "directly modifies model internals to encode safety properties. Early results are promising "
        "but none has yet matched RLHF/DPO at production scale.\n\n"
        "## References\n\n"
        "- [Ouyang et al. \u2013 Training language models to follow instructions](https://arxiv.org/abs/2203.02155)\n"
        "- [Rafailov et al. \u2013 Direct Preference Optimization](https://arxiv.org/abs/2305.18290)\n"
        "- [Bai et al. \u2013 Constitutional AI](https://arxiv.org/abs/2212.08073)\n"
        "- [Burns et al. \u2013 Representation Engineering](https://arxiv.org/abs/2310.01405)\n",
        # 5: Semiconductor supply chain
        "# Global Semiconductor Supply Chain Post-CHIPS Act\n\n"
        "## Executive Summary\n\n"
        "The CHIPS and Science Act, signed in August 2022 with $52.7 billion in semiconductor "
        "subsidies, has fundamentally altered the global chip manufacturing landscape. Two years "
        "into implementation, this analysis examines the impact on TSMC, Samsung, and Intel's "
        "foundry strategies, along with broader supply chain resilience implications.\n\n"
        "## Key Findings\n\n"
        "### TSMC's US Expansion\n\n"
        "TSMC's Arizona fab complex has become the flagship CHIPS Act project, receiving $6.6 "
        "billion in direct subsidies plus $5 billion in loans. The first fab (4nm) achieved "
        "production-grade yields in late 2025, with a second fab (3nm/2nm) under construction. "
        "However, costs run 30-40% higher than comparable Taiwan facilities due to labor, "
        "permitting, and supply chain factors. TSMC has responded by expanding its Arizona "
        "investment to $65 billion with a third fab planned for advanced packaging.\n\n"
        "### Samsung and Intel Positioning\n\n"
        "Samsung's $17 billion Taylor, Texas fab focuses on advanced nodes (4nm and below), "
        "targeting both consumer electronics and automotive chips. Intel's foundry services "
        "division received the largest CHIPS Act award ($8.5 billion) to support its IDM 2.0 "
        "strategy, but the company's execution challenges\u2014delays at Intel 18A and yield issues\u2014"
        "have raised questions about its ability to compete with TSMC. Intel's restructuring in "
        "2025, including the potential IPO of its foundry business, signals the difficulty of the "
        "transition.\n\n"
        "### Supply Chain Resilience\n\n"
        "The concentration of advanced chip manufacturing in Taiwan remains the primary geopolitical "
        "risk. TSMC's Taiwan fabs still produce over 80% of the world's leading-edge chips. US "
        "domestic capacity will reach approximately 10% of global advanced production by 2027, "
        "insufficient for true supply chain independence but enough to sustain critical defense "
        "and infrastructure needs during a potential disruption.\n\n"
        "## References\n\n"
        "- [US Department of Commerce \u2013 CHIPS Act Awards](https://www.commerce.gov/chips)\n"
        "- [TSMC \u2013 Arizona Expansion](https://pr.tsmc.com/english/news)\n"
        "- [Semiconductor Industry Association](https://www.semiconductors.org/)\n"
        "- [Intel Foundry Services](https://www.intel.com/content/www/us/en/foundry.html)\n",
        # 6: Rust async runtimes
        "# Rust Async Runtimes: Tokio vs async-std vs smol\n\n"
        "## Executive Summary\n\n"
        "Rust's async ecosystem has matured significantly, with Tokio establishing dominance while "
        "alternatives like async-std and smol serve important niches. This guide examines the "
        "architectural differences, benchmarks performance characteristics, and provides guidance "
        "on runtime selection for different use cases.\n\n"
        "## Key Findings\n\n"
        "### Architecture Comparison\n\n"
        "**Tokio** uses a work-stealing multi-threaded scheduler with a dedicated I/O driver thread. "
        "Its architecture prioritizes throughput for high-concurrency server workloads, with features "
        "like task-local storage, cooperative scheduling budgets, and a comprehensive ecosystem "
        "(tower, hyper, tonic). The runtime handles 100K+ concurrent connections efficiently.\n\n"
        "**async-std** mirrors the standard library API surface, making it approachable for newcomers. "
        "It uses a thread-per-core model by default with a global executor. Development has slowed "
        "considerably since 2023, with the project effectively in maintenance mode.\n\n"
        "**smol** takes a minimalist approach: the entire runtime is ~1,500 lines of code. It "
        "provides basic task spawning and I/O without opinions about scheduling strategy. This "
        "makes it ideal for embedded systems, libraries that want to be runtime-agnostic, and "
        "educational purposes.\n\n"
        "### Benchmarks\n\n"
        "Testing on a 16-core server with a mix of I/O-bound and CPU-bound workloads:\n\n"
        "| Metric | Tokio | async-std | smol |\n"
        "|--------|-------|-----------|------|\n"
        "| HTTP req/s (wrk) | 485,000 | 312,000 | 289,000 |\n"
        "| Task spawn latency | 1.2\u00b5s | 2.8\u00b5s | 0.9\u00b5s |\n"
        "| Memory per 10K tasks | 4.2 MB | 6.1 MB | 3.1 MB |\n"
        "| Binary size overhead | 1.8 MB | 1.2 MB | 0.3 MB |\n\n"
        "Tokio's work-stealing scheduler excels under load imbalance. smol's lightweight design "
        "wins on memory efficiency and spawn latency.\n\n"
        "### Recommendation\n\n"
        "For production server applications, Tokio remains the clear choice\u2014its ecosystem, "
        "documentation, and community support are unmatched. For libraries, consider using "
        "runtime-agnostic abstractions (futures crate) to avoid locking users into a specific "
        "runtime. For resource-constrained environments, smol offers the best footprint.\n\n"
        "## References\n\n"
        "- [Tokio Documentation](https://tokio.rs)\n"
        "- [async-std Book](https://book.async.rs)\n"
        "- [smol GitHub Repository](https://github.com/smol-rs/smol)\n"
        "- [Rust Async Book](https://rust-lang.github.io/async-book/)\n",
        # 7: Coastal climate adaptation
        "# Climate Adaptation for Coastal Megacities\n\n"
        "## Executive Summary\n\n"
        "Coastal megacities housing over 800 million people face escalating risks from sea level "
        "rise, storm surge intensification, and subsidence. This report evaluates engineering "
        "solutions, policy frameworks, and cost-benefit analyses for adaptation through 2050, "
        "drawing on case studies from Jakarta, Miami, Mumbai, and Shanghai.\n\n"
        "## Key Findings\n\n"
        "### Engineering Solutions\n\n"
        "Three categories of engineering intervention are being deployed at scale:\n\n"
        "**Hard infrastructure**: Sea walls, storm surge barriers, and pumping systems remain "
        "the primary defense. The Netherlands' Delta Works model is being adapted globally, with "
        "Jakarta's $40 billion National Capital Integrated Coastal Development (NCICD) and New "
        "York's $52 billion harbor barrier proposal as leading examples. Cost-effectiveness varies "
        "dramatically: $2,000-5,000 per protected meter for sea walls versus $50,000+ per meter "
        "for storm surge barriers.\n\n"
        "**Nature-based solutions**: Mangrove restoration, living shorelines, and constructed "
        "wetlands provide flood protection at 2-5x lower cost than hard infrastructure while "
        "delivering co-benefits (carbon sequestration, biodiversity, fisheries). Singapore's "
        "hybrid approach\u2014combining mangroves with engineered structures\u2014is emerging as a "
        "best-practice model.\n\n"
        "**Managed retreat**: For areas where protection costs exceed property values, managed "
        "retreat is increasingly recognized as necessary. The US has spent $3.4 billion on buyouts "
        "since 1989, relocating 45,000 properties. However, political feasibility remains the "
        "primary obstacle.\n\n"
        "### Cost-Benefit Analysis\n\n"
        "Global investment needs for coastal adaptation are estimated at $40-70 billion annually "
        "through 2030, rising to $100-150 billion annually by 2050. The benefit-cost ratio ranges "
        "from 4:1 for proactive adaptation in high-value areas to less than 1:1 for defending "
        "low-lying communities where retreat may be more economical. Every dollar invested in "
        "adaptation today avoids $4-8 in future damage costs.\n\n"
        "## References\n\n"
        "- [IPCC AR6 \u2013 Sea Level Rise Projections](https://www.ipcc.ch/report/ar6/wg1/)\n"
        "- [World Bank \u2013 Coastal Resilience](https://www.worldbank.org/en/topic/climatechange)\n"
        "- [C40 Cities \u2013 Climate Action Plans](https://www.c40.org/)\n"
        "- [Nature \u2013 Cost of Coastal Flooding](https://www.nature.com/articles/s41558-020-0895-y)\n"
        "- [NOAA \u2013 Sea Level Rise Viewer](https://coast.noaa.gov/slr/)\n",
        # 8: GenAI and software engineering productivity
        "# Generative AI Impact on Software Engineering Productivity\n\n"
        "## Executive Summary\n\n"
        "Generative AI coding tools\u2014led by GitHub Copilot, Cursor, and Claude Code\u2014have been "
        "adopted by an estimated 40% of professional developers as of early 2026. This report "
        "synthesizes empirical studies, large-scale developer surveys, and economic modeling to "
        "quantify the productivity impact and identify where AI assistance is most and least "
        "effective.\n\n"
        "## Key Findings\n\n"
        "### Empirical Studies\n\n"
        "The most rigorous controlled study (Microsoft Research, n=4,867 developers) found that "
        "Copilot users completed tasks 26% faster on average, with the effect strongest for "
        "boilerplate-heavy tasks (+55%) and weakest for complex algorithmic problems (+8%). A "
        "follow-up study at Google found similar results with Gemini-based tooling, reporting a "
        "22% reduction in code review iteration time and a 15% increase in code submission "
        "frequency.\n\n"
        "Critically, speed gains do not always translate to quality gains. Studies show a 10-15% "
        "increase in bugs per line of AI-assisted code when developers accept suggestions without "
        "careful review. The highest-performing teams use AI as a drafting tool with rigorous "
        "human review, not as an auto-accept workflow.\n\n"
        "### Developer Surveys\n\n"
        "Stack Overflow's 2025 Developer Survey (n=65,000) reports that 72% of developers using "
        "AI tools feel more productive, but only 38% report measurable output increases. The "
        "disconnect reflects AI's impact on developer satisfaction and flow state, which may "
        "not directly translate to shipping velocity. Senior developers (10+ years) report lower "
        "perceived productivity gains (18%) compared to juniors (45%), but produce higher-quality "
        "AI-assisted code.\n\n"
        "### Economic Modeling\n\n"
        "McKinsey's economic model estimates that generative AI could contribute $75-150 billion "
        "annually to the global software industry by 2030 through productivity gains. However, "
        "the distribution is uneven: the largest gains accrue to enterprises with strong CI/CD "
        "pipelines and code review practices that catch AI-introduced errors early. Companies "
        "without these safeguards may see negative ROI from AI tool adoption.\n\n"
        "## References\n\n"
        "- [GitHub \u2013 Copilot Research](https://github.blog/news-insights/research/)\n"
        "- [Microsoft Research \u2013 Developer Productivity Study](https://www.microsoft.com/en-us/research/)\n"
        "- [Stack Overflow \u2013 2025 Developer Survey](https://survey.stackoverflow.co/)\n"
        "- [McKinsey \u2013 The Economic Potential of Generative AI](https://www.mckinsey.com/capabilities/quantumblack)\n",
        # 9: Subscription pricing behavioral economics
        "# Behavioral Economics of Subscription Pricing\n\n"
        "## Executive Summary\n\n"
        "Subscription models now underpin over $275 billion in annual consumer spending globally. "
        "This report examines how behavioral economics principles\u2014particularly nudge theory\u2014are "
        "applied in subscription pricing, analyzes churn prediction models, and addresses the "
        "growing ethical concerns around dark patterns in subscription management.\n\n"
        "## Key Findings\n\n"
        "### Nudge Theory Applications\n\n"
        "Subscription businesses systematically exploit cognitive biases:\n\n"
        "**Anchoring**: Presenting a high-priced annual plan alongside monthly pricing makes the "
        "annual option appear as a bargain. Netflix's tier restructuring in 2024 increased premium "
        "tier adoption by 23% by introducing an ultra-premium anchor tier.\n\n"
        "**Default bias**: Auto-renewal with opt-out cancellation leverages status quo bias. "
        "Research shows that requiring active renewal reduces retention by 35-50%, explaining "
        "why virtually all subscription services use auto-renewal.\n\n"
        "**Loss aversion**: Free trial conversions exploit the endowment effect. Users who've "
        "customized their experience during a trial (playlists, settings, saved items) convert "
        "at 2-3x the rate of passive trial users, because cancellation feels like losing something "
        "they already own.\n\n"
        "### Churn Prediction\n\n"
        "Modern churn models combine behavioral signals (login frequency, feature usage, support "
        "tickets) with payment signals (failed charges, plan downgrades, coupon usage). XGBoost "
        "and transformer-based models achieve 85-92% accuracy in predicting churn 30 days out. "
        "The most predictive single feature is declining engagement velocity\u2014not absolute usage "
        "levels but the rate of change in usage patterns.\n\n"
        "### Ethical Considerations\n\n"
        "The FTC's 2025 enforcement actions against subscription dark patterns have established "
        "clearer boundaries. The 'click-to-cancel' rule requires that cancellation be as easy as "
        "sign-up, and the EU's Digital Services Act mandates transparent pricing and renewal "
        "notifications. Consumer advocates argue these regulations don't go far enough, pointing "
        "to practices like 'roach motel' designs where cancellation is technically possible but "
        "deliberately friction-laden.\n\n"
        "## References\n\n"
        "- [FTC \u2013 Click-to-Cancel Rule](https://www.ftc.gov/legal-library/browse/rules/negative-option-rule)\n"
        "- [Thaler & Sunstein \u2013 Nudge: The Final Edition](https://www.penguinrandomhouse.com/books/)\n"
        "- [Recurly \u2013 State of Subscriptions](https://recurly.com/research/)\n"
        "- [Harvard Business Review \u2013 Subscription Fatigue](https://hbr.org/)\n"
        "- [EU Digital Services Act](https://digital-strategy.ec.europa.eu/en/policies/digital-services-act-package)\n",
    ]

    sample_jobs = [
        # Today
        {
            "prompt": "Comprehensive analysis of quantum error correction breakthroughs in 2025-2026, including surface codes, topological approaches, and implications for fault-tolerant quantum computing",
            "model": "openai/o3-deep-research",
            "cost": 0.52,
            "tokens": 45200,
            "hours_ago": 2,
        },
        {
            "prompt": "Compare the economic impact of carbon border adjustment mechanisms across EU, US, and developing nations with trade flow analysis",
            "model": "gemini/deep-research",
            "cost": 1.05,
            "tokens": 62000,
            "hours_ago": 5,
        },
        {
            "prompt": "Deep dive into React Server Components vs traditional SSR: performance benchmarks, developer experience, and migration strategies",
            "model": "openai/o4-mini-deep-research",
            "cost": 1.85,
            "tokens": 38400,
            "hours_ago": 8,
        },
        # Yesterday
        {
            "prompt": "State of autonomous vehicle regulation worldwide: liability frameworks, safety standards, and insurance models as of early 2026",
            "model": "openai/o3-deep-research",
            "cost": 0.48,
            "tokens": 51000,
            "hours_ago": 18,
        },
        {
            "prompt": "Systematic review of large language model alignment techniques: RLHF, DPO, constitutional AI, and emerging approaches",
            "model": "gemini/deep-research",
            "cost": 0.95,
            "tokens": 58000,
            "hours_ago": 28,
        },
        # 2 days ago
        {
            "prompt": "Analysis of global semiconductor supply chain resilience post-CHIPS Act: TSMC, Samsung, and Intel foundry strategies",
            "model": "openai/o4-mini-deep-research",
            "cost": 2.10,
            "tokens": 42000,
            "hours_ago": 52,
        },
        {
            "prompt": "CRISPR gene therapy clinical trial outcomes 2024-2026: sickle cell, beta-thalassemia, and hereditary blindness",
            "model": "openai/o3-deep-research",
            "cost": 0.61,
            "tokens": 47500,
            "hours_ago": 55,
        },
        # 3 days ago
        {
            "prompt": "Comprehensive guide to Rust async runtime internals: Tokio vs async-std vs smol architecture comparisons",
            "model": "openai/o3-deep-research",
            "cost": 0.45,
            "tokens": 39500,
            "hours_ago": 75,
        },
        # 4 days ago
        {
            "prompt": "Climate adaptation strategies for coastal megacities: engineering solutions, policy frameworks, and cost-benefit analysis",
            "model": "gemini/deep-research",
            "cost": 1.12,
            "tokens": 67000,
            "hours_ago": 102,
        },
        # 5-6 days ago
        {
            "prompt": "Impact of generative AI on software engineering productivity: empirical studies, developer surveys, and economic modeling",
            "model": "openai/o4-mini-deep-research",
            "cost": 1.95,
            "tokens": 35000,
            "hours_ago": 125,
        },
        {
            "prompt": "Comparative analysis of central bank digital currencies: technical architectures, privacy models, and adoption timelines",
            "model": "openai/o3-deep-research",
            "cost": 0.68,
            "tokens": 52000,
            "hours_ago": 140,
        },
        # 7-8 days ago
        {
            "prompt": "Behavioral economics of subscription pricing: nudge theory applications, churn prediction models, and ethical considerations",
            "model": "openai/o3-deep-research",
            "cost": 0.55,
            "tokens": 44000,
            "hours_ago": 170,
        },
        {
            "prompt": "Advances in solid-state battery technology: energy density benchmarks, manufacturing scalability, and EV adoption impact",
            "model": "gemini/deep-research",
            "cost": 0.89,
            "tokens": 55000,
            "hours_ago": 192,
        },
        # 9-10 days ago
        {
            "prompt": "Post-quantum cryptography migration strategies for enterprise systems: NIST standards, hybrid approaches, and timeline planning",
            "model": "openai/o3-deep-research",
            "cost": 0.72,
            "tokens": 48000,
            "hours_ago": 220,
        },
        {
            "prompt": "Microplastics in human tissue: latest epidemiological findings, health risk models, and regulatory responses worldwide",
            "model": "openai/o4-mini-deep-research",
            "cost": 1.65,
            "tokens": 37000,
            "hours_ago": 240,
        },
        # 11-13 days ago
        {
            "prompt": "Nuclear fusion progress update: ITER, NIF, and private ventures — plasma confinement milestones and energy breakeven timeline",
            "model": "gemini/deep-research",
            "cost": 1.08,
            "tokens": 63000,
            "hours_ago": 268,
        },
        {
            "prompt": "WebAssembly beyond the browser: edge computing, plugin systems, and server-side adoption patterns in 2025-2026",
            "model": "openai/o3-deep-research",
            "cost": 0.41,
            "tokens": 36000,
            "hours_ago": 290,
        },
        {
            "prompt": "Global water scarcity projections 2030-2050: desalination technology advances, aquifer depletion rates, and policy interventions",
            "model": "gemini/deep-research",
            "cost": 0.92,
            "tokens": 59000,
            "hours_ago": 310,
        },
    ]
    for idx, sample in enumerate(sample_jobs):
        try:
            job_id = str(uuid.uuid4())
            submitted = now - timedelta(hours=sample["hours_ago"])
            is_failed = sample.get("failed", False)
            job = ResearchJob(
                id=job_id,
                prompt=sample["prompt"],
                model=sample["model"],
                status=JobStatus.QUEUED,
                priority=random.choice([1, 3]),
                submitted_at=submitted,
            )
            run_async(queue.enqueue(job))
            target_status = JobStatus.FAILED if is_failed else JobStatus.COMPLETED
            error_msg = "Provider timeout after 120s" if is_failed else None
            run_async(queue.update_status(job_id, target_status, error=error_msg))

            # Fix completed_at to match the past time (update_status sets it to now)
            completed = submitted + timedelta(minutes=random.randint(12, 45))
            import sqlite3 as _sqlite3

            _conn = _sqlite3.connect(queue.db_path)
            _conn.execute(
                "UPDATE research_queue SET completed_at = ? WHERE id = ?",
                (completed.isoformat(), job_id),
            )
            _conn.commit()
            _conn.close()

            if not is_failed:
                # Save a demo report so result-detail renders real content
                report_content = demo_reports[idx % len(demo_reports)]
                run_async(
                    storage.save_report(
                        job_id=job_id,
                        filename="report.md",
                        content=report_content.encode("utf-8"),
                        content_type="text/markdown",
                        metadata={"prompt": sample["prompt"], "model": sample["model"]},
                    )
                )
            run_async(
                queue.update_results(
                    job_id=job_id,
                    report_paths={"markdown": "report.md"} if not is_failed else {},
                    cost=sample["cost"],
                    tokens_used=sample["tokens"],
                )
            )
            created_jobs += 1
        except Exception:
            pass

    return jsonify(
        {
            "success": len(errors) == 0,
            "created_jobs": created_jobs,
            "errors": errors,
        }
    )


@app.route("/api/demo/clear", methods=["POST"])
def clear_demo_data():
    """Clear all jobs and demo data."""
    import sqlite3

    errors = []
    try:
        db_path = _cfg.get("queue_db_path", str(config_path / "queue.db"))
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM research_queue").fetchone()[0]
        conn.execute("DELETE FROM research_queue")
        conn.commit()
        conn.close()
    except Exception as e:
        errors.append(str(e))
        count = 0

    # Clean up stored reports
    try:
        import shutil

        storage_dir = Path(storage.base_path)
        if storage_dir.exists():
            for job_dir in storage_dir.iterdir():
                if job_dir.is_dir():
                    shutil.rmtree(job_dir)
    except Exception as e:
        errors.append(f"Storage cleanup: {e}")

    return jsonify(
        {
            "success": len(errors) == 0,
            "cleared_jobs": count,
            "errors": errors,
        }
    )


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
                "version": "2.9.0",
                "provider": "openai",
                "queue": "sqlite",
                "storage": "local",
            }
        )

    except Exception as e:
        logger.error("Health check failed: %s", e)
        return jsonify({"status": "unhealthy", "error": "Service unavailable"}), 500


def _auto_load_demo():
    """Auto-load demo data if DEEPR_DEMO=1 is set."""
    if os.environ.get("DEEPR_DEMO", "").strip() in ("1", "true", "yes"):
        with app.app_context():
            try:
                logger.info("DEEPR_DEMO is set — auto-loading demo data")
                # Check if jobs already exist to avoid duplicate loads
                jobs = run_async(queue.list_jobs(limit=1))
                if not jobs:
                    with app.test_request_context():
                        load_demo_data()
                    logger.info("Demo data loaded successfully")
                else:
                    logger.info("Jobs already exist — skipping demo auto-load")
            except Exception as e:
                logger.warning("Failed to auto-load demo data: %s", e)


_auto_load_demo()


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  Deepr Research Dashboard")
    print("  Running on http://localhost:5000")
    print("=" * 70 + "\n")
    import os as _os

    debug = _os.environ.get("FLASK_DEBUG", "0") == "1"
    socketio.run(app, debug=debug, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)
