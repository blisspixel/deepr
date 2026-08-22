"""Flask web interface for Deepr monitoring, research, and cost tracking."""

import asyncio
import json as _json
import logging
import math
import os
import random
import re
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
from werkzeug.utils import safe_join, secure_filename

from deepr.config import runtime_data_path
from deepr.security.http_auth import (
    SharedSecretDecision,
    check_shared_secret,
    env_flag,
    presented_http_secret,
)
from deepr.services.provider_completion import authoritative_completion_usage

# Shared sync-to-async bridge, retaining the historical local alias.
from deepr.utils.async_runner import run_async_command as run_async
from deepr.utils.security import is_contained_path, is_loopback_bind_host, reserved_windows_device_stem
from deepr.web import action_safety, council_api
from deepr.web.expert_chat_contract import BrowserChatContractError, parse_browser_expert_chat_request  # noqa: F401
from deepr.web.expert_chat_rest import (
    build_browser_expert_chat_response,
    handle_browser_expert_chat_request,
    run_browser_expert_chat_once,
)
from deepr.web.expert_loop_status_api import register_expert_read_apis
from deepr.web.metered_expert_gate import metered_expert_mutation_block
from deepr.web.portrait_api import generate_expert_portrait_response

load_dotenv()

# Serve the Vite-built frontend from frontend/dist/
_frontend_dist = Path(__file__).parent / "frontend" / "dist"

# ---------------------------------------------------------------------------
# Security configuration
# ---------------------------------------------------------------------------
# Loopback locality is not caller authentication. Sensitive dashboard APIs and
# Socket.IO events require DEEPR_API_KEY unless the operator explicitly opts
# into the unsafe loopback compatibility mode.
_API_KEY = os.getenv("DEEPR_API_KEY", "").strip()
_ALLOW_UNAUTHENTICATED_LOOPBACK = env_flag("DEEPR_WEB_ALLOW_UNAUTHENTICATED_LOOPBACK")
_CORS_ORIGINS = [
    origin.strip() for origin in os.getenv("DEEPR_CORS_ORIGINS", "http://localhost:5000").split(",") if origin.strip()
]
_SOCKETIO_CORS_ORIGINS = _CORS_ORIGINS if os.getenv("DEEPR_CORS_ORIGINS") else None
_MAX_PROMPT_LENGTH = 50_000  # characters
_MAX_BATCH_SIZE = 50
_MAX_QUERY_LIMIT = 1000
_WEB_OPENAI_RESEARCH_MODELS = {
    "o3-deep-research",
    "o4-mini-deep-research",
    "gpt-5.2",
}

app = Flask(
    __name__,
    template_folder=str(_frontend_dist),
    static_folder=str(_frontend_dist / "assets"),
    static_url_path="/assets",
)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB request body limit
CORS(app, origins=_CORS_ORIGINS)
socketio = SocketIO(app, cors_allowed_origins=_SOCKETIO_CORS_ORIGINS, async_mode="threading")

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
    limiter = None  # type: ignore[assignment]

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authentication middleware
# ---------------------------------------------------------------------------
@app.before_request
def _check_auth():
    """
    Require API key on sensitive API routes.

    Tokenless loopback compatibility requires a separate explicit opt-in.
    """
    # Skip auth for non-API routes (SPA, static assets, health check)
    if not request.path.startswith("/api/"):
        return
    if request.path == "/api/health":
        return
    decision = check_shared_secret(
        configured_secret=_API_KEY,
        presented_secret=presented_http_secret(
            request.headers.get("Authorization", ""),
            request.headers.get("X-Api-Key", ""),
        ),
        allow_unauthenticated_loopback=_ALLOW_UNAUTHENTICATED_LOOPBACK,
        remote_addr=request.remote_addr,
    )
    if decision is SharedSecretDecision.ALLOW:
        return
    if decision is SharedSecretDecision.NOT_CONFIGURED:
        return jsonify(
            {
                "error": "Dashboard authentication is not configured",
                "error_code": "AUTH_NOT_CONFIGURED",
            }
        ), 503
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


import uuid

import deepr
from deepr.config import experts_root, load_config
from deepr.core.costs import CostController, CostEstimator
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.providers.openai_provider import OpenAIProvider
from deepr.queue.base import JobStatus, ResearchJob, client_job_metadata, public_job_metadata
from deepr.queue.local_queue import SQLiteQueue
from deepr.services.job_provider import create_job_provider
from deepr.services.provider_status import (
    classify_provider_status,
    provider_exception_name,
    terminal_provider_error,
)
from deepr.services.research_cost_reconciliation import reconcile_research_cost_reservations
from deepr.services.research_submission import dispatch_reserved_research
from deepr.storage.local import LocalStorage
from deepr.web import demo_seed, research_cost_api, spend_truth

_cfg = load_config()
config_path = Path(".deepr")
config_path.mkdir(exist_ok=True)

queue = SQLiteQueue(_cfg.get("queue_db_path", str(config_path / "queue.db")))
storage = LocalStorage(_cfg.get("results_dir", str(config_path / "storage")))
provider: OpenAIProvider | None = None
_provider_lock = threading.Lock()


def _default_openai_provider() -> OpenAIProvider:
    """Create the metered provider only at a gated provider operation."""
    global provider
    if provider is not None:
        return provider
    with _provider_lock:
        if provider is not None:
            return provider
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise research_cost_api.WebProviderNotConfiguredError(research_cost_api.OPENAI_NOT_CONFIGURED)
        provider = OpenAIProvider(api_key=api_key)
        return provider


# Canonical, CWD-independent experts root (ADR 0004): web + CLI read one store.
_experts_dir = experts_root()


# ---------------------------------------------------------------------------
# Canonical budget authority
# ---------------------------------------------------------------------------


def _sync_cost_controller_to_authority() -> dict[str, float]:
    """Refresh the web controller from the same caps every interface uses."""
    from deepr.core.cost_caps import resolve_spend_caps

    caps = resolve_spend_caps()
    controller = globals().get("cost_controller")
    if controller is not None:
        controller.max_cost_per_job = caps["per_job"]
        controller.max_daily_cost = caps["daily"]
        controller.max_monthly_cost = caps["monthly"]
    return caps


def _validated_cost_limit_updates(data: dict, fields: dict[str, str]) -> dict[str, float]:
    """Parse web limit updates without inventing interface-local authority."""
    from deepr.core.cost_caps import resolve_spend_caps

    authority = resolve_spend_caps()
    updates: dict[str, float] = {}
    for request_field, cap_field in fields.items():
        if request_field not in data:
            continue
        value = data[request_field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{request_field} must be a finite non-negative number")
        if cap_field != "monthly" and float(value) != authority[cap_field]:
            raise ValueError(
                f"{request_field} is controlled by canonical environment policy and cannot be changed "
                f"from the dashboard; current effective value is {authority[cap_field]}"
            )
        updates[cap_field] = float(value)
    return updates


def _apply_canonical_cost_limit_updates(data: dict, fields: dict[str, str]) -> dict[str, float]:
    """Narrow the canonical operator budget and return fresh effective caps."""
    from deepr.cli.commands.budget import mutate_budget_config
    from deepr.core.cost_caps import apply_paid_api_freeze, resolve_spend_caps

    updates = _validated_cost_limit_updates(data, fields)
    monthly = updates.get("monthly")
    if monthly is not None:

        def narrow(config: dict) -> None:
            current = resolve_spend_caps(provider="openai")["monthly"]
            if monthly > current:
                raise ValueError(
                    f"monthly limit may only narrow current effective authority of {current}; "
                    "use the local CLI to review and raise operator authority"
                )
            config["monthly_limit"] = monthly
            if monthly == 0 and not config.get("paid_api_frozen", False):
                apply_paid_api_freeze(
                    config,
                    reason="paid API monthly ceiling is zero",
                    kind="zero_ceiling",
                )

        mutate_budget_config(narrow)
    return _sync_cost_controller_to_authority()


try:
    from deepr.core.cost_caps import resolve_spend_caps

    _limits = resolve_spend_caps()
    cost_controller = CostController(
        max_cost_per_job=_limits["per_job"],
        max_daily_cost=_limits["daily"],
        max_monthly_cost=_limits["monthly"],
    )
    cost_estimator = CostEstimator()
except Exception as e:
    logger.error("Cost controls unavailable; paid submissions are disabled: %s", e)
    cost_controller = None  # type: ignore[assignment]
    cost_estimator = None  # type: ignore[assignment]

research_costs = research_cost_api.WebResearchCostCoordinator(cost_controller, cost_estimator)


def _web_expert_chat_budget_ceiling() -> float:
    """Return the configured browser-chat ceiling, or zero when unavailable."""
    from deepr.experts.cost_safety import CostSafetyManager

    if cost_controller is None:
        return 0.0
    configured = cost_controller.max_cost_per_job
    if isinstance(configured, bool) or not isinstance(configured, (int, float)) or not math.isfinite(configured):
        return 0.0
    return max(0.0, min(float(configured), CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION))


from deepr.api.websockets.events import (
    emit_job_completed,
    emit_job_created,
    emit_job_failed,
    register_socketio_events,
)

register_socketio_events(
    socketio,
    max_chat_budget=_web_expert_chat_budget_ceiling,
    api_key=lambda: _API_KEY,
    allow_unauthenticated_loopback=lambda: _ALLOW_UNAUTHENTICATED_LOOPBACK,
)

# ---------------------------------------------------------------------------
# Background poller - checks provider status for PROCESSING jobs
# ---------------------------------------------------------------------------
_poller_lock = threading.Lock()
_poller_started = False
_POLL_INTERVAL = 15  # seconds
_STUCK_THRESHOLD = timedelta(minutes=30)
# Jobs the provider just confirmed alive (in_progress/queued) are exempt from
# the 30-minute stuck cancellation: deep research legitimately runs for an
# hour or more, and auto-cancelling a live provider job burns everything
# billed so far and destroys the result. The hard cap below is the only
# ceiling for confirmed-alive jobs.
_LIVE_JOB_HARD_CAP = timedelta(hours=24)


def _run_poller_loop():
    """Infinite loop that polls provider for job status updates."""
    logger.info("Background poller started (interval=%ds)", _POLL_INTERVAL)
    while True:
        try:
            _poll_once()
        except Exception:
            logger.exception("Poller cycle error")
            # Intent: one poller cycle failure (transient provider issue, etc.) must not kill the background status poller; continue for all other jobs.
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
                # Intent: one job status check failure must not abort the entire poll cycle; continue with remaining jobs.
    finally:
        loop.close()


def _check_job(loop, job):
    """Check a single job's provider status."""
    if not job.provider_job_id:
        _check_stuck(loop, job)
        return

    provider_factory = _provider_factory_for_job(job)
    try:
        active_provider = provider_factory()
    except Exception as exc:
        logger.warning(
            "Poller: recorded provider unavailable for job %s (%s)",
            job.id,
            provider_exception_name(exc),
        )
        # Status unknown, not dead: the job may still be running (and
        # billing) at the provider, so only the hard cap may cancel it.
        _check_stuck(loop, job, threshold=_LIVE_JOB_HARD_CAP)
        return

    try:
        response = loop.run_until_complete(active_provider.get_status(job.provider_job_id))
    except Exception as exc:
        logger.warning(
            "Poller: provider status check failed for job %s (%s)",
            job.id,
            provider_exception_name(exc),
        )
        _check_stuck(loop, job, threshold=_LIVE_JOB_HARD_CAP)
        return

    provider_status = classify_provider_status(response.status)
    if provider_status == "completed":
        _handle_completion(loop, job, response)
    elif terminal_error := terminal_provider_error(provider_status):
        if provider_status == "cancelled":
            _handle_failure(loop, job, terminal_error, status=JobStatus.CANCELLED)
        else:
            _handle_failure(loop, job, terminal_error)
    elif provider_status in ("in_progress", "queued"):
        # Provider confirmed the job is alive: money is being spent on real
        # work. Only the 24h hard cap applies, never the 30-minute threshold.
        _check_stuck(loop, job, threshold=_LIVE_JOB_HARD_CAP)
    elif provider_status == "unsupported":
        logger.warning("Poller: job %s returned an unsupported provider status", job.id)
        _check_stuck(loop, job)


def _provider_factory_for_job(job):
    """Bind provider construction to the owner persisted on a job."""
    return partial(create_job_provider, job, _cfg)


def _handle_completion(loop, job, response):
    """Save results and emit completion event."""
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

    cost, tokens = authoritative_completion_usage(job, response)

    research_costs.cleanup_uploads(
        loop=loop,
        queue=queue,
        job=job,
        provider_factory=_provider_factory_for_job(job),
    )
    research_costs.finalize_completed_job(
        loop=loop, queue=queue, job=job, actual_cost=cost, tokens=tokens, report_saved=bool(report_text)
    )

    updated_job = loop.run_until_complete(queue.get_job(job.id))
    if not updated_job:
        logger.error("Poller: job %s vanished after completion update - WebSocket notification lost", job.id)
    elif report_text:
        emit_job_completed(socketio, updated_job)
    else:
        emit_job_failed(socketio, updated_job, "Provider completion had no report content")
        logger.error("Poller: job %s billed as complete but produced no report content", job.id)
    logger.info("Poller: job %s completed (cost=%.4f)", job.id, cost or 0)


def _handle_failure(loop, job, error, *, status=JobStatus.FAILED):
    """Close a terminal provider outcome and emit its state change."""
    try:
        research_costs.fail_job(job)
    except Exception:
        logger.exception("Poller: failed to close provider cost for failed job %s", job.id)
        return
    research_costs.cleanup_uploads(
        loop=loop,
        queue=queue,
        job=job,
        provider_factory=_provider_factory_for_job(job),
    )
    loop.run_until_complete(queue.update_status(job_id=job.id, status=status, error=str(error)))
    updated_job = loop.run_until_complete(queue.get_job(job.id))
    if updated_job:
        emit_job_failed(socketio, updated_job, str(error))
    else:
        logger.error("Poller: job %s vanished after failure update - WebSocket notification lost", job.id)
    logger.info("Poller: job %s failed: %s", job.id, error)


def _cancel_job_with_cost_safety(job) -> bool:
    provider_factory = _provider_factory_for_job(job)
    return run_async(research_costs.cancel_job(queue=queue, job=job, provider_factory=provider_factory))


def _check_stuck(loop, job, threshold: timedelta = _STUCK_THRESHOLD):
    """Cancel a stale job before closing its cost, state, or resources."""
    if not job.started_at:
        return
    if datetime.now(UTC) - _ensure_utc(job.started_at) > threshold:
        try:
            cancelled = _cancel_job_with_cost_safety(job)
        except Exception:
            cancelled = False
            logger.exception("Poller: stuck-job cancellation failed for %s", job.id)
        if not cancelled:
            logger.warning("Poller: retaining stuck job %s after unconfirmed cancellation", job.id)


@app.before_request
def _start_poller():
    """Start the background poller thread on first request (runs once)."""
    global _poller_started
    if app.config.get("TESTING") or _poller_started:
        return
    with _poller_lock:
        if _poller_started:
            return
        _poller_started = True
        t = threading.Thread(target=_run_poller_loop, daemon=True, name="job-poller")
        t.start()
        logger.info("Background job poller thread launched")


@app.route("/")
def index():
    """Main dashboard."""
    return render_template("index.html")


@app.errorhandler(404)
def fallback_to_spa(e):
    """Serve index.html for unknown routes so client-side routing works."""
    # Don't catch missing API routes - return 404 JSON for those
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    # Serve static files from dist if they exist (with path traversal protection)
    relative = request.path.lstrip("/")
    if relative:
        parts = Path(relative).parts
        if (
            parts
            and not any(part in ("", ".", "..") for part in parts)
            and not any(reserved_windows_device_stem(part) for part in parts)
        ):
            joined = safe_join(str(_frontend_dist.resolve()), *parts)
            if joined:
                resolved = Path(joined)
                if resolved.is_file() and is_contained_path(resolved, _frontend_dist.resolve()):
                    return send_from_directory(str(_frontend_dist), Path(*parts).as_posix())
    # Flask 404 handlers keep status 404 unless a code is set. Nested SPA
    # routes must be a 200 document so refresh and client routing work.
    return render_template("index.html"), 200


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC)."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


# Allow only a literal space (not the whole \s class). \s also matches
# newlines, tabs, and other control whitespace, which would let an expert
# name carry a line break that splits a copied/agent-run shell command (the
# health-check recommended-action strings interpolate the name).
_SAFE_NAME_RE = re.compile(r"^[\w \-().,']+$")  # letters, digits, single spaces, basic punctuation


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
    """Decode an expert URL name into a storage-safe lookup token."""
    from urllib.parse import unquote

    from deepr.experts.paths import expert_slug
    from deepr.utils.security import InvalidInputError

    decoded = unquote(name)
    err = _validate_expert_name(decoded)
    if err:
        return None, (jsonify({"error": err}), 400)

    # Preserve the canonical on-disk naming scheme, then pass the result
    # through Werkzeug's path sanitizer. The second step is intentionally
    # explicit at the HTTP trust boundary so static analysis and reviewers can
    # prove route data no longer controls a path expression.
    try:
        storage_slug = secure_filename(expert_slug(decoded))
    except InvalidInputError:
        return None, (jsonify({"error": "Invalid expert name"}), 400)
    if not storage_slug:
        return None, (jsonify({"error": "Invalid expert name"}), 400)
    return storage_slug, None


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

        jobs = jobs[offset : offset + limit]

        jobs_data = []
        for job in jobs:
            jobs_data.append(
                {
                    "id": job.id,
                    "prompt": (job.prompt[:200] if len(job.prompt) > 200 else job.prompt) if job.prompt else "",
                    "model": job.model,
                    "provider": job.provider,
                    "status": job.status.value,
                    "priority": job.priority,
                    "cost": job.cost or 0,
                    "tokens_used": job.tokens_used or 0,
                    "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    "metadata": public_job_metadata(job.metadata),
                }
            )

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
            "provider": job.provider,
            "status": job.status.value,
            "priority": job.priority,
            "cost": job.cost or 0,
            "tokens_used": job.tokens_used or 0,
            "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "metadata": public_job_metadata(job.metadata),
            "provider_job_id": job.provider_job_id,
            "last_error": job.last_error,
            "result": None,
        }

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

        if job.status == JobStatus.CANCELLED:
            if _cancel_job_with_cost_safety(job):
                return jsonify({"success": True})
            return jsonify({"error": "Cancellation closure could not be confirmed"}), 503
        if job.status not in {JobStatus.QUEUED, JobStatus.PROCESSING}:
            return jsonify({"error": "Terminal job state cannot be cancelled"}), 409
        if not _cancel_job_with_cost_safety(job):
            return jsonify({"error": "Job could not be cancelled safely"}), 503

        return jsonify({"success": True})

    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {e}")
        return jsonify({"error": "Internal server error"}), 500


def _build_submitted_research_job(
    data,
    *,
    job_id: str,
    prompt: str,
    model: str,
    priority: int,
    enable_web_search,
    metadata: dict,
    reservation,
) -> ResearchJob:
    mode = data.get("mode")
    if mode:
        metadata["mode"] = mode
    if reservation is not None:
        metadata.update(reservation.metadata())
    return ResearchJob(
        id=job_id,
        prompt=prompt,
        model=model,
        provider="openai",
        priority=priority,
        enable_web_search=enable_web_search,
        status=JobStatus.QUEUED,
        submitted_at=datetime.now(UTC),
        metadata=metadata,
    )


@app.route("/api/jobs", methods=["POST"])
@(limiter.limit("10 per minute") if limiter else (lambda f: f))
def submit_job():
    """Submit a new research job."""
    reservation = None
    provider_submitted = False
    try:
        data = request.json
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        prompt = str(data.get("prompt", "")).strip()
        model = str(data.get("model", "o4-mini-deep-research"))
        priority = max(1, min(10, _safe_int(data.get("priority", 3), 3)))
        enable_web_search = data.get("enable_web_search", True)

        input_denial = research_cost_api.validate_web_research_input(
            prompt=prompt,
            model=model,
            max_prompt_length=_MAX_PROMPT_LENGTH,
            allowed_models=_WEB_OPENAI_RESEARCH_MODELS,
            metadata=data.get("metadata"),
        )
        if input_denial is not None:
            payload, status = input_denial
            return jsonify(payload), status

        metadata = client_job_metadata(data.get("metadata"))
        if denial := research_cost_api.metered_api_consent_error(data):
            return jsonify({"error": denial}), 403

        job_id = str(uuid.uuid4())
        run_async(reconcile_research_cost_reservations(queue, default_provider="openai"))
        estimated_cost, reservation, denial = research_costs.reserve(
            job_id=job_id,
            prompt=prompt,
            model=model,
        )
        if denial is not None:
            payload, status = denial
            return jsonify(payload), status

        active_provider, provider_denial = research_cost_api.resolve_web_research_provider(_default_openai_provider)
        if provider_denial is not None:
            research_costs.refund(reservation)
            reservation = None
            payload, status = provider_denial
            return jsonify(payload), status

        job = _build_submitted_research_job(
            data,
            job_id=job_id,
            prompt=prompt,
            model=model,
            priority=priority,
            enable_web_search=enable_web_search,
            metadata=metadata,
            reservation=reservation,
        )

        req = ResearchRequest(
            prompt=prompt,
            model=model,
            system_message="You are a research assistant. Provide comprehensive, citation-backed analysis.",
            tools=[ToolConfig(type="web_search_preview")] if enable_web_search else [],
            background=True,
        )

        try:
            provider_job_id = run_async(
                dispatch_reserved_research(
                    queue=queue,
                    provider=active_provider,
                    job=job,
                    request=req,
                    reservation=reservation,
                )
            )
            provider_submitted = True
            research_costs.remember(reservation)
        except Exception as exc:
            retry_payload = research_cost_api.retryable_dispatch_payload(exc, job_id)
            if retry_payload is not None:
                return jsonify(retry_payload), 503
            research_costs.refund_job(job)
            reservation = None
            error = "Provider submission failed"
            logger.error(
                "Provider submission failed for job %s (%s)",
                job_id,
                provider_exception_name(exc),
            )
            run_async(queue.update_status(job_id=job_id, status=JobStatus.FAILED, error=error))
            job.status = JobStatus.FAILED
            job.last_error = error
            emit_job_failed(socketio, job, error)
            return jsonify(
                {
                    "error": "Provider submission failed",
                    "job_id": job_id,
                }
            ), 500

        job.status = JobStatus.PROCESSING
        job.provider_job_id = provider_job_id
        emit_job_created(socketio, job)

        job_response = {
            "id": job_id,
            "prompt": prompt,
            "model": model,
            "provider": "openai",
            "status": "processing",
            "priority": priority,
            "cost": 0,
            "tokens_used": 0,
            "submitted_at": job.submitted_at.isoformat(),
            "provider_job_id": provider_job_id,
        }

        return jsonify(
            {
                "job": job_response,
                "estimated_cost": estimated_cost,
            }
        )

    except Exception as e:
        if reservation is not None and not provider_submitted:
            research_costs.refund(reservation)
        logger.error(f"Error submitting job: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/jobs/batch", methods=["POST"])
def batch_submit():
    """Submit multiple jobs at once."""
    try:
        data = request.json
        if not isinstance(data, dict) or not data:
            return jsonify({"error": "Request body required"}), 400
        jobs, denial = research_cost_api.prepare_web_batch_jobs(
            data.get("jobs"),
            max_batch_size=_MAX_BATCH_SIZE,
            max_prompt_length=_MAX_PROMPT_LENGTH,
            allowed_models=_WEB_OPENAI_RESEARCH_MODELS,
        )
        if denial is not None:
            payload, status = denial
            return jsonify(payload), status
        if consent_denial := research_cost_api.metered_api_consent_error(data):
            return jsonify({"error": consent_denial}), 403

        results = []
        for job in jobs or []:
            run_async(queue.enqueue(job))
            results.append({"job_id": job.id, "status": "queued"})

        return jsonify({"jobs": results, "count": len(results)})

    except Exception as exc:
        logger.error("Error batch submitting: %s", type(exc).__name__)
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/jobs/bulk-cancel", methods=["POST"])
def bulk_cancel():
    """Cancel multiple jobs at once."""
    try:
        data = request.json
        if not isinstance(data, dict) or not data:
            return jsonify({"error": "Request body required"}), 400
        job_ids = data.get("job_ids", [])

        cancelled = []
        failed = []
        for job_id in job_ids:
            try:
                job = run_async(queue.get_job(job_id))
                success = bool(
                    job is not None
                    and (
                        (job.status == JobStatus.CANCELLED and _cancel_job_with_cost_safety(job))
                        or (
                            job.status in {JobStatus.QUEUED, JobStatus.PROCESSING} and _cancel_job_with_cost_safety(job)
                        )
                    )
                )
                if success:
                    cancelled.append(job_id)
                else:
                    failed.append(job_id)
            except Exception:
                failed.append(job_id)
                # Intent: one job cancel failure in a bulk operation must not abort the entire request; record it and continue with the rest.

        return jsonify({"cancelled": cancelled, "failed": failed, "count": len(cancelled)})

    except Exception as e:
        logger.error(f"Error bulk cancelling: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    """Cancel a job."""
    try:
        job = run_async(queue.get_job(job_id))
        if job is None:
            return jsonify({"error": "Job not found"}), 404
        if job.status == JobStatus.CANCELLED:
            if _cancel_job_with_cost_safety(job):
                return jsonify({"success": True})
            return jsonify({"error": "Cancellation closure could not be confirmed"}), 503
        if job.status not in {JobStatus.QUEUED, JobStatus.PROCESSING}:
            return jsonify({"error": "Terminal job state cannot be cancelled"}), 409
        if not _cancel_job_with_cost_safety(job):
            return jsonify({"error": "Job cancellation could not be confirmed"}), 503
        return jsonify({"success": True})

    except Exception as exc:
        logger.error(
            "Job cancellation failed for job %s (%s)",
            job_id,
            provider_exception_name(exc),
        )
        return jsonify({"error": "Internal server error"}), 500


def _cleanup_must_retain(job, age) -> bool:
    """True when stale cleanup must NOT touch this job.

    Never fail a job the provider confirms is still running, and never fail
    one whose status cannot be confirmed: cancelling live deep research burns
    everything billed so far and destroys the pending result. Only the 24h
    hard cap overrides an unconfirmed or confirmed-alive status.
    """
    if not job.provider_job_id or age > _LIVE_JOB_HARD_CAP:
        return False
    try:
        active_provider = _provider_factory_for_job(job)()
        response = run_async(active_provider.get_status(job.provider_job_id))
        return classify_provider_status(response.status) in ("in_progress", "queued")
    except Exception:
        logger.warning("Cleanup: could not confirm provider status for %s; retaining", job.id)
        return True


@app.route("/api/jobs/cleanup-stale", methods=["POST"])
def cleanup_stale_jobs():
    """Mark stale PROCESSING/QUEUED jobs as FAILED.

    A job is considered stale if it has been PROCESSING or QUEUED for over
    30 minutes (matching poller threshold), or PROCESSING with no provider_job_id.
    """
    try:
        all_jobs = run_async(queue.list_jobs(limit=10000))
        now = datetime.now(UTC)
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
                if _cleanup_must_retain(job, now - started):
                    continue
                if not _cancel_job_with_cost_safety(job):
                    continue
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
    """Get cost summary with daily/monthly spending.

    Spend totals come from the canonical append-only cost ledger - the
    single source of truth that every recorder writes (research jobs,
    expert learning, absorb/validate calls, MCP tools). The previous
    implementation summed queue job costs plus expert-profile counters,
    which missed every CLI-side spend path and double-counted others.
    """
    try:
        all_jobs = run_async(queue.list_jobs(limit=10000))
        money = spend_truth.cost_exposure_snapshot()

        completed_jobs = [j for j in all_jobs if j.status == JobStatus.COMPLETED]
        avg_cost = money["total"] / len(completed_jobs) if completed_jobs else 0

        summary = {
            **money,
            "avg_cost_per_job": avg_cost,
            "completed_jobs": len(completed_jobs),
            "total_jobs": len(all_jobs),
        }

        return jsonify({"summary": summary})

    except Exception as e:
        logger.error(f"Error getting cost summary: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/cost/integrity", methods=["GET"])
def get_cost_integrity():
    """Reconcile settled spend against surviving report artifacts.

    Money settled with no artifact on disk is orphaned spend; the $37.79
    campaign with zero survivors must be impossible to miss here.
    """
    try:
        days = max(1, min(_safe_int(request.args.get("days", 45), 45), 365))
        reports_root = Path(load_config()["results_dir"])
        return jsonify({"integrity": spend_truth.audit_spend_integrity(days, reports_root)})
    except Exception as e:
        logger.error(f"Error auditing cost integrity: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/cost/trends", methods=["GET"])
def get_cost_trends():
    """Get daily spending trends (from the canonical cost ledger)."""
    try:
        from deepr.observability.cost_ledger import CostLedger

        days = max(1, min(_safe_int(request.args.get("days", 30), 30), 365))

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=days)

        # Group ledger events by day - every spend path writes the ledger,
        # so the trend reflects research jobs, expert learning, and tool
        # calls alike (queue job costs missed everything but jobs).
        events = CostLedger().with_locked_accounting_events(
            lambda ledger_events: [event for event in ledger_events if event.timestamp >= cutoff]
        )
        daily_costs = {}
        for event in events:
            if event.cost_usd:
                day_key = event.timestamp.strftime("%Y-%m-%d")
                daily_costs[day_key] = daily_costs.get(day_key, 0) + event.cost_usd

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

        from deepr.observability.cost_attribution import project_cost_attribution
        from deepr.observability.cost_ledger import CostLedger

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=days)

        # Group canonical ledger events by model (covers CLI/MCP/expert
        # spend, not just queue jobs; events without a model roll up
        # under "unknown" so the totals still reconcile with the ledger)
        events = CostLedger().with_locked_accounting_events(
            lambda ledger_events: [
                event for event in project_cost_attribution(ledger_events) if event.timestamp >= cutoff
            ]
        )
        model_costs = {}
        for event in events:
            model = event.model or "unknown"
            if model not in model_costs:
                model_costs[model] = {"cost": 0, "count": 0, "tokens": 0}
            model_costs[model]["cost"] += event.cost_usd
            model_costs[model]["count"] += 1
            model_costs[model]["tokens"] += event.tokens_input + event.tokens_output

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
    """Get strict canonical cost history across every metered entry point."""
    try:
        time_range = request.args.get("time_range", "30d")
        days = _parse_time_range(time_range, 30)
        limit = max(1, min(_safe_int(request.args.get("limit", 100), 100), _MAX_QUERY_LIMIT))

        from deepr.observability.cost_ledger import CostLedger

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=days)

        events = CostLedger().with_locked_accounting_events(
            lambda ledger_events: sorted(
                (event for event in ledger_events if event.timestamp >= cutoff and event.cost_usd > 0),
                key=lambda event: event.timestamp,
                reverse=True,
            )[:limit]
        )

        history = [
            {
                "id": event.idempotency_key or event.request_id or f"ledger-event-{index + 1}",
                "prompt": event.operation,
                "operation": event.operation,
                "provider": event.provider,
                "source": event.source,
                "model": event.model,
                "cost": round(event.cost_usd, 6),
                "tokens": event.tokens_input + event.tokens_output,
                "completed_at": event.timestamp.isoformat(),
            }
            for index, event in enumerate(events)
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

        estimate_payload, admission_estimate, estimate_error = spend_truth.verified_cost_estimate(
            cost_estimator,
            prompt,
            model,
        )
        if estimate_error is not None:
            logger.warning("Cost estimation failed: %s", estimate_error)
        if admission_estimate is None:
            return (
                jsonify(
                    {
                        "estimate": estimate_payload,
                        "allowed": False,
                        "reason": "Cost estimate is unavailable; paid API dispatch is blocked.",
                        "money_state": "unknown",
                    }
                ),
                503,
            )

        try:
            from deepr.core.cost_caps import resolve_spend_caps
            from deepr.experts.research_reservation_store import ResearchReservationStore

            caps = resolve_spend_caps(provider="openai")
            exposure = ResearchReservationStore().exposure_snapshot()
            decision = spend_truth.paid_estimate_admission(admission_estimate, caps, exposure)
        except Exception as exc:
            logger.warning("Could not verify canonical cost exposure before estimate: %s", exc)
            return (
                jsonify(
                    {
                        "estimate": estimate_payload,
                        "allowed": False,
                        "reason": "Canonical money state is unreadable; paid API dispatch is blocked.",
                        "money_state": "unknown",
                    }
                ),
                503,
            )

        return jsonify(
            {
                "estimate": estimate_payload,
                **decision,
                "money_state": "known",
            }
        )

    except Exception as e:
        logger.error(f"Error estimating cost: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/cost/limits", methods=["GET"])
def get_cost_limits():
    """Get current budget limits."""
    try:
        caps = _sync_cost_controller_to_authority()
        limits = {
            "per_job": caps["per_job"],
            "daily": caps["daily"],
            "monthly": caps["monthly"],
            "expert_chat_max": _web_expert_chat_budget_ceiling(),
            "mutable_fields": ["monthly"],
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
        if not isinstance(data, dict) or not data:
            return jsonify({"error": "Request body required"}), 400

        if cost_controller is None:
            return jsonify({"error": "Cost controls unavailable; limits cannot be changed"}), 503
        try:
            caps = _apply_canonical_cost_limit_updates(
                data,
                {"per_job": "per_job", "daily": "daily", "monthly": "monthly"},
            )
        except ValueError:
            return jsonify(
                {
                    "error": "Cost limit update rejected by canonical budget policy",
                    "error_code": "cost_limit_update_rejected",
                }
            ), 400

        limits = {
            "per_job": caps["per_job"],
            "daily": caps["daily"],
            "monthly": caps["monthly"],
            "expert_chat_max": _web_expert_chat_budget_ceiling(),
            "mutable_fields": ["monthly"],
        }
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
                    _ensure_utc(j.completed_at) or _ensure_utc(j.submitted_at) or datetime.min.replace(tzinfo=UTC)
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
            except Exception as exc:
                logger.debug("Could not load result preview for job %s: %s", job.id, exc, exc_info=exc)

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
            "metadata": public_job_metadata(job.metadata),
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
        caps = _sync_cost_controller_to_authority()
        with _config_lock:
            config = {
                **_config,
                "daily_limit": caps["daily"],
                "monthly_limit": caps["monthly"],
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
        if not isinstance(data, dict) or not data:
            return jsonify({"error": "Request body required"}), 400

        caps: dict[str, float] | None = None
        if cost_controller and ("daily_limit" in data or "monthly_limit" in data):
            try:
                caps = _apply_canonical_cost_limit_updates(
                    data,
                    {"daily_limit": "daily", "monthly_limit": "monthly"},
                )
            except ValueError:
                return jsonify(
                    {
                        "error": "Cost limit update rejected by canonical budget policy",
                        "error_code": "cost_limit_update_rejected",
                    }
                ), 400

        # Update allowed fields only after the whole request validates.
        allowed = ["default_model", "default_priority", "enable_web_search"]
        with _config_lock:
            for key in allowed:
                if key in data:
                    _config[key] = data[key]

        if caps is None:
            caps = _sync_cost_controller_to_authority()
        with _config_lock:
            response_config = {
                **_config,
                "daily_limit": caps["daily"],
                "monthly_limit": caps["monthly"],
            }
        return jsonify({"config": response_config})

    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify({"error": "Internal server error"}), 500


def _expert_counts(profile) -> tuple[int, int, int]:
    """Real knowledge counts for an expert: (documents, findings, open gaps).

    The legacy mapping read profile.source_files (seed files only) and
    profile.research_jobs, which undercounted both documents and findings -
    an expert with 7 documents and 25 absorbed beliefs displayed as
    "2 docs, 0 findings". Documents come from the profile counter (which
    learning/integration updates), findings from the canonical belief store,
    gaps from the manifest backlog.
    """
    doc_count = max(
        int(getattr(profile, "total_documents", 0) or 0),
        len(getattr(profile, "source_files", []) or []),
    )

    finding_count = len(getattr(profile, "research_jobs", []) or [])
    try:
        from deepr.experts.beliefs import BeliefStore

        finding_count = max(finding_count, len(BeliefStore(profile.name).beliefs))
    except Exception as exc:
        logger.debug("Could not read belief store for %s: %s", profile.name, exc, exc_info=exc)

    gap_count = 0
    try:
        gap_count = len(profile.get_manifest().gaps)
    except Exception as exc:
        logger.debug("Could not read expert manifest for %s: %s", profile.name, exc, exc_info=exc)

    return doc_count, finding_count, gap_count


register_expert_read_apis(app, _experts_dir, _decode_expert_name, _safe_int, _MAX_QUERY_LIMIT, logger)


@app.route("/api/experts", methods=["GET"])
def list_experts():
    """List all domain experts."""
    try:
        from deepr.experts.profile_store import ExpertStore
        from deepr.web.expert_v2_api import roster_entry, roster_readiness

        store = ExpertStore(str(_experts_dir))
        profiles = store.list_all()
        experts = []
        for profile in profiles:
            doc_count, finding_count, gap_count = _expert_counts(profile)
            roster = roster_entry(profile.name)
            portrait_url = getattr(profile, "portrait_url", None)
            experts.append(
                {
                    "name": profile.name,
                    "description": getattr(profile, "description", "") or "",
                    "document_count": doc_count,
                    "finding_count": finding_count,
                    "gap_count": gap_count,
                    "total_cost": getattr(profile, "total_research_cost", 0.0),
                    "last_active": getattr(profile, "updated_at", datetime.now(UTC)).isoformat(),
                    "created_at": getattr(profile, "created_at", datetime.now(UTC)).isoformat(),
                    "portrait_url": portrait_url,
                    "roster_tier": getattr(profile, "roster_tier", "standard"),
                    # What distinguishes one expert from another. Without these
                    # the roster is forty rows of the same three counters, and
                    # a reader has nothing to choose on.
                    **roster,
                    **roster_readiness(roster, portrait_url=portrait_url),
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

        # Description and domain must be strings - the React Expert Hub
        # calls .toLowerCase() and renders them directly. A persisted object
        # or array would trip the frontend error boundary for every client.
        raw_description = data.get("description", "")
        raw_domain = data.get("domain", "")
        if not isinstance(raw_description, str):
            return jsonify({"error": "description must be a string"}), 400
        if not isinstance(raw_domain, str):
            return jsonify({"error": "domain must be a string"}), 400
        description = raw_description.strip()[:1000]
        domain = raw_domain.strip()[:200]

        store = ExpertStore(str(_experts_dir))
        if store.exists(name):
            return jsonify({"error": "Expert already exists"}), 409

        profile = ExpertProfile(
            name=name,
            vector_store_id="",
            description=description,
            domain=domain,
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
        doc_count, finding_count, gap_count = _expert_counts(profile)

        return jsonify(
            {
                "expert": {
                    "name": profile.name,
                    "description": getattr(profile, "description", "") or "",
                    "document_count": doc_count,
                    "finding_count": finding_count,
                    "gap_count": gap_count,
                    "total_cost": getattr(profile, "total_research_cost", 0.0),
                    "last_active": getattr(profile, "updated_at", datetime.now(UTC)).isoformat(),
                    "created_at": getattr(profile, "created_at", datetime.now(UTC)).isoformat(),
                    "portrait_url": getattr(profile, "portrait_url", None),
                }
            }
        )
    except ImportError:
        return jsonify({"error": "Expert system not available"}), 404
    except Exception as e:
        logger.error(f"Error getting expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# Cooldown window between portrait generations per expert. The portrait
# endpoint calls paid image-generation APIs, so without this any caller able
# to reach the route can run up provider spend in a tight loop.
_PORTRAIT_COOLDOWN_SECONDS = 60
_PORTRAIT_LAST_GENERATED: dict[str, float] = {}
_PORTRAIT_ALLOWED_PROVIDERS = {"local", "openai", "google", "xai"}


@app.route("/api/experts/<name>/generate-portrait", methods=["POST"])
@(limiter.limit("5 per hour") if limiter else (lambda f: f))
def generate_expert_portrait(name):
    """Generate an AI portrait for a domain expert.

    Hardened against cost-abuse:
    - Tight per-route rate limit (5/hour) when flask-limiter is installed.
    - Per-expert cooldown stops the same expert being regenerated in a loop.
    - Provider override is validated against an allowlist; arbitrary strings
      cannot be passed through to portraits.generate_portrait.
    """
    decoded_name, err = _decode_expert_name(name)
    if err:
        return jsonify({"error": "Invalid expert name"}), 400
    return generate_expert_portrait_response(
        decoded_name=decoded_name,
        experts_dir=_experts_dir,
        portraits_dir=runtime_data_path("portraits"),
        request_data=request.json or {},
        last_generated=_PORTRAIT_LAST_GENERATED,
        allowed_providers=_PORTRAIT_ALLOWED_PROVIDERS,
        cooldown_seconds=_PORTRAIT_COOLDOWN_SECONDS,
    )


@app.route("/portraits/<filename>")
def serve_portrait(filename):
    """Serve a generated portrait image."""
    if not filename.endswith(".png") or reserved_windows_device_stem(filename):
        return jsonify({"error": "Invalid file type"}), 400
    portraits_dir = runtime_data_path("portraits")
    return send_from_directory(str(portraits_dir.resolve()), filename)


@app.route("/api/experts/<name>/chat", methods=["POST"])
def chat_with_expert(name):
    """Chat with a domain expert."""
    return handle_browser_expert_chat_request(
        name=name,
        data=request.get_json(silent=True),
        decode_expert_name=_decode_expert_name,
        max_budget=_web_expert_chat_budget_ceiling(),
        run_async_command=run_async,
        parse_request=parse_browser_expert_chat_request,
        run_chat_once=run_browser_expert_chat_once,
        build_response=build_browser_expert_chat_response,
        experts_dir=_experts_dir,
        jsonify_response=jsonify,
        route_logger=logger,
    )


@app.route("/api/experts/council", methods=["POST"])
@(limiter.limit("5 per minute") if limiter else (lambda f: f))
def expert_council():
    """Consult multiple experts on a query."""
    return council_api.handle_expert_council_request(
        request.get_json(silent=True),
        run_async=run_async,
        jsonify_response=jsonify,
    )


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
            except Exception as exc:
                logger.debug("Skipping unreadable conversation file %s: %s", f, exc, exc_info=exc)
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
        # Guard against path traversal: session_id flows into a file path.
        if not re.match(r"^[\w\-]+$", session_id):
            return jsonify({"error": "Invalid session_id"}), 400
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
        # Guard against path traversal: session_id flows into a file path.
        if not re.match(r"^[\w\-]+$", session_id):
            return jsonify({"error": "Invalid session_id"}), 400
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
        claims = list(manifest.claims)

        # Include the canonical belief store (absorb/learning writes there,
        # not to manifest claims) so the web surfaces the expert's actual
        # perspective - confidence-decayed, with contradiction edges.
        try:
            from deepr.experts.beliefs import BeliefStore

            seen_ids = {getattr(c, "id", None) for c in claims}
            for belief in BeliefStore(decoded_name).beliefs.values():
                claim = belief.to_claim()
                if claim.id not in seen_ids:
                    claims.append(claim)
        except Exception as exc:
            logger.debug("Could not merge belief store for %s: %s", decoded_name, exc, exc_info=exc)

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
        budget = min(data.get("budget", 1.0), 5.0)
        allow_metered_api = bool(data.get("allow_metered_api"))
        confirm_metered_cost = bool(data.get("confirm_metered_cost"))

        if not (allow_metered_api and confirm_metered_cost):
            return (
                jsonify(
                    {
                        "error": "Metered gap filling requires explicit API and cost confirmation.",
                        "status": "blocked",
                        "estimated_cost_usd": round(float(budget), 2),
                        "required": {
                            "allow_metered_api": True,
                            "confirm_metered_cost": True,
                        },
                        "safe_alternative": "deepr expert route-gaps EXPERT --execute --scheduled",
                    }
                ),
                402,
            )

        return metered_expert_mutation_block(
            "api_fill_gaps",
            safe_alternative="deepr expert route-gaps EXPERT --execute --scheduled",
        )

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


# Maximum number of (belief, source) pairs to validate per request. The
# validator fans out one paid LLM call per batch of five, so without a cap a
# populated expert can cost-amplify a single GET into many provider calls.
_CITATION_VALIDATION_PAIR_CAP = 50
# Validation results are deterministic for a given (worldview, documents)
# tuple, so cache them per expert for a window long enough to absorb dashboard
# polling without redoing paid LLM calls.
_CITATION_VALIDATION_CACHE_TTL = 600  # seconds
_CITATION_VALIDATION_CACHE: dict[str, tuple[float, str, dict]] = {}
# Per-expert fill lock for the citation cache. Without this, two
# concurrent uncached requests both miss the cache and fan out paid
# LLM batches; the rate limiter only constrains a single client IP.
_CITATION_VALIDATION_LOCKS: dict[str, threading.Lock] = {}
_CITATION_VALIDATION_LOCKS_LOCK = threading.Lock()


def _citation_cache_lock_for(expert_name: str) -> threading.Lock:
    with _CITATION_VALIDATION_LOCKS_LOCK:
        lock = _CITATION_VALIDATION_LOCKS.get(expert_name)
        if lock is None:
            lock = threading.Lock()
            _CITATION_VALIDATION_LOCKS[expert_name] = lock
        return lock


def _citation_validation_cache_key(worldview_path: Path, docs_dir: Path) -> str:
    """Build a cache key from the latest mtime of the worldview + documents.

    Any edit to the worldview or any markdown source invalidates the cache
    because the underlying claims/sources have moved.
    """
    parts = [str(worldview_path.stat().st_mtime_ns)]
    if docs_dir.exists():
        for doc_path in sorted(docs_dir.glob("*.md")):
            try:
                parts.append(f"{doc_path.name}:{doc_path.stat().st_mtime_ns}")
            except OSError:
                continue
    return "|".join(parts)


def _read_markdown_docs_within_root(docs_dir: Path, *, max_chars: int = 2000) -> dict[str, str]:
    docs: dict[str, str] = {}
    try:
        docs_root = docs_dir.resolve()
    except OSError:
        return docs

    for doc_path in docs_root.glob("*.md"):
        try:
            resolved_doc_path = doc_path.resolve()
            resolved_doc_path.relative_to(docs_root)
            docs[resolved_doc_path.name] = resolved_doc_path.read_text(encoding="utf-8")[:max_chars]
        except (OSError, ValueError):
            continue
    return docs


@app.route("/api/experts/<name>/citation-validations", methods=["GET"])
@(limiter.limit("5 per minute") if limiter else (lambda f: f))
def get_citation_validations(name):
    """Fail closed before the legacy paid citation-validation batch."""
    return metered_expert_mutation_block(
        "api_validate_citations",
        safe_alternative="review stored beliefs and source files locally",
    )

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

        expert_name = profile.name
        knowledge_dir = store.get_knowledge_dir(expert_name)
        worldview_path = knowledge_dir / "worldview.json"
        if not worldview_path.exists():
            return jsonify({"validations": [], "summary": {}})

        worldview = Worldview.load(worldview_path)
        if not worldview.beliefs:
            return jsonify({"validations": [], "summary": {}})

        beliefs = worldview.beliefs[:_CITATION_VALIDATION_PAIR_CAP]
        truncated = len(worldview.beliefs) > _CITATION_VALIDATION_PAIR_CAP
        docs_dir = store.get_documents_dir(expert_name)
        cache_key = _citation_validation_cache_key(worldview_path, docs_dir)

        # Fast path: cache hit outside the lock.
        cached = _CITATION_VALIDATION_CACHE.get(decoded_name)
        if cached and cached[1] == cache_key and (time.time() - cached[0]) < _CITATION_VALIDATION_CACHE_TTL:
            payload = dict(cached[2])
            payload["cached"] = True
            return jsonify(payload)

        async def _do_validate():
            from deepr.config import AppConfig
            from deepr.experts.citation_validator import CitationValidator
            from deepr.providers import create_provider

            config = AppConfig.from_env()
            provider = create_provider("openai", api_key=config.provider.openai_api_key)
            validator = CitationValidator(client=provider.client)

            claims = [b.to_claim() for b in beliefs]
            doc_dict = _read_markdown_docs_within_root(docs_dir)

            validations = await validator.validate_claims(claims, doc_dict)
            summary = validator.summarize(validations)
            return [v.to_dict() for v in validations], summary

        # Slow path: serialize cache fills per expert so concurrent
        # callers don't all fan out paid LLM batches when the cache is
        # cold. Re-check the cache after acquiring the lock.
        fill_lock = _citation_cache_lock_for(decoded_name)
        with fill_lock:
            cached = _CITATION_VALIDATION_CACHE.get(decoded_name)
            if cached and cached[1] == cache_key and (time.time() - cached[0]) < _CITATION_VALIDATION_CACHE_TTL:
                payload = dict(cached[2])
                payload["cached"] = True
                return jsonify(payload)

            validations, summary = asyncio.run(_do_validate())
            payload = {
                "validations": validations,
                "summary": summary,
                "truncated": truncated,
                "pair_cap": _CITATION_VALIDATION_PAIR_CAP,
                "cached": False,
            }
            _CITATION_VALIDATION_CACHE[decoded_name] = (time.time(), cache_key, payload)
            return jsonify(payload)
    except ImportError:
        return jsonify({"validations": [], "summary": {}})
    except Exception as e:
        logger.error(f"Error validating citations for expert {name}: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/experts/<name>/discover-gaps", methods=["POST"])
def discover_expert_gaps(name):
    """Fail closed before legacy paid embedding and gap-generation calls."""
    return metered_expert_mutation_block(
        "api_discover_gaps",
        safe_alternative="deepr expert next EXPERT",
    )

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
    """Fail closed until conflict-resolution provider calls are accounted."""
    return (
        jsonify(
            {
                "error": (
                    "Conflict resolution is temporarily blocked because this legacy path cannot "
                    "guarantee reservation and canonical settlement for every provider call."
                ),
                "error_code": "METERED_ACCOUNTING_UNAVAILABLE",
                "read_only_alternative": "deepr expert contested",
            }
        ),
        503,
    )


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
        trace_dir = runtime_data_path("traces").resolve()
        trace_path = (trace_dir / f"{job_id}_trace.json").resolve()
        if not is_contained_path(trace_path, trace_dir):
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
        trace_dir = runtime_data_path("traces").resolve()
        trace_path = (trace_dir / f"{job_id}_trace.json").resolve()
        if not is_contained_path(trace_path, trace_dir):
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
        all_jobs.sort(key=lambda j: _ensure_utc(j.submitted_at) or datetime.min.replace(tzinfo=UTC), reverse=True)

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
    """Block external provider metadata calls before credential or client use."""
    return (
        jsonify(
            {
                "success": False,
                "error_code": "external_metadata_cost_unverified",
                "message": "Live provider connection tests are disabled because endpoint and proxy cost cannot be proven",
            }
        ),
        503,
    )


# =============================================================================
# BENCHMARKS API ENDPOINTS
# =============================================================================

_benchmark_proc: dict = {}  # pid, process, started_at, output_lines
_benchmark_lock = threading.Lock()
_BENCHMARK_DIR = runtime_data_path("benchmarks")


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
            except Exception as exc:
                logger.debug("Skipping unreadable benchmark file %s: %s", f, exc, exc_info=exc)
                continue

        return jsonify({"benchmarks": benchmarks})

    except Exception as e:
        logger.error(f"Error listing benchmarks: {e}")
        return jsonify({"error": "Internal server error"}), 500


# Same patterns as scripts/benchmark_models.py:redact_secrets - duplicated here so
# the web app does not require the benchmark script to be importable as a module.
_BENCHMARK_SECRET_PATTERNS = [
    re.compile(r"(?i)([?&](?:key|api[_-]?key|access[_-]?token)=)[^&\s\"'<>]+"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"'<>]+"),
    re.compile(r"(?i)(x[_-](?:api[_-]?key|goog[_-]api[_-]key)\s*[:=]\s*)[^\s\"'<>]+"),
]


def _redact_secrets(text):
    """Replace embedded provider API keys / bearer tokens with REDACTED."""
    if not isinstance(text, str) or not text:
        return text
    out = text
    for pattern in _BENCHMARK_SECRET_PATTERNS:
        out = pattern.sub(r"\1REDACTED", out)
    return out


def _redact_in_place(obj):
    """Walk a JSON-serializable structure and redact secrets in string values.

    Returns the same object for convenience. Mutates dicts/lists in place; for
    bare strings, callers should reassign the returned value.
    """
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                obj[k] = _redact_secrets(v)
            else:
                _redact_in_place(v)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i] = _redact_secrets(v)
            else:
                _redact_in_place(v)
    return obj


def _sanitize_benchmark(data: dict) -> dict:
    """Replace Infinity/NaN with JSON-safe values and strip any leaked secrets.

    Historical benchmark JSON may contain raw exception strings (e.g. Gemini
    URLs with ?key=...). Redact those before returning data to API clients.
    """
    for ranking in data.get("rankings", []):
        for key in ("cost_per_quality", "avg_quality", "avg_latency_ms", "total_cost"):
            val = ranking.get(key)
            if isinstance(val, float) and (math.isinf(val) or math.isnan(val)):
                ranking[key] = 0.0
    _redact_in_place(data)
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
            except Exception as exc:
                logger.debug("Skipping invalid benchmark candidate %s: %s", f, exc, exc_info=exc)
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
        if not is_contained_path(filepath, _BENCHMARK_DIR.resolve()):
            return jsonify({"error": "Invalid filename"}), 400

        if not filepath.exists():
            return jsonify({"error": "Benchmark not found"}), 404

        data = _sanitize_benchmark(_json.loads(filepath.read_text(encoding="utf-8")))
        return jsonify({"result": data, "filename": filename})

    except Exception as e:
        logger.error(f"Error getting benchmark {filename}: {e}")
        return jsonify({"error": "Internal server error"}), 500


# Serialize and cache benchmark-estimate runs so concurrent POSTs cannot
# spawn many Python subprocesses. Each unique (tier, quick, no_judge) tuple
# is memoised for `_BENCHMARK_ESTIMATE_TTL` seconds; the lock ensures only
# one subprocess runs at a time even on cache miss.
_benchmark_estimate_lock = threading.Lock()
_benchmark_estimate_cache: dict[tuple[str, bool, bool], tuple[float, dict]] = {}
_BENCHMARK_ESTIMATE_TTL = 120  # seconds


@app.route("/api/benchmarks/estimate", methods=["POST"])
@(limiter.limit("6 per minute") if limiter else (lambda f: f))
def estimate_benchmark():
    """Estimate cost for a benchmark run (dry-run).

    Hardened against subprocess-spawn DoS:
    - Per-route 6/min rate limit when flask-limiter is installed.
    - Module-level lock serialises subprocess execution; concurrent requests
      block on the lock rather than each spawning their own Python child.
    - Results are cached per (tier, quick, no_judge) for 2 minutes so a
      burst of identical estimates returns the prior result instead of
      re-running the script.
    """
    import subprocess

    try:
        data = request.json or {}
        tier = data.get("tier", "all")
        quick = bool(data.get("quick", False))
        no_judge = bool(data.get("no_judge", False))

        if tier not in ("all", "chat", "news", "research", "docs"):
            return jsonify({"error": "Invalid tier"}), 400

        cache_key = (tier, quick, no_judge)
        now = time.monotonic()
        cached = _benchmark_estimate_cache.get(cache_key)
        if cached and (now - cached[0]) < _BENCHMARK_ESTIMATE_TTL:
            return jsonify({**cached[1], "cached": True})

        cmd = action_safety.benchmark_command("--dry-run", "--format", "json", "--skip-discovery-check", "--tier", tier)
        if quick:
            cmd.append("--quick")
        if no_judge:
            cmd.append("--no-judge")

        # acquire(timeout=...) prevents request workers from stacking up
        # waiting on a stuck subprocess; refuse fast and let the client retry.
        if not _benchmark_estimate_lock.acquire(timeout=20):
            return jsonify({"error": "Estimator busy, try again shortly"}), 503
        try:
            cached = _benchmark_estimate_cache.get(cache_key)
            if cached and (time.monotonic() - cached[0]) < _BENCHMARK_ESTIMATE_TTL:
                return jsonify({**cached[1], "cached": True})

            result = subprocess.run(  # Internal trusted benchmark script (scripts/benchmark_models.py). No user-controlled input; same pattern as scripts/eval.py and deepr/providers.py.
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
                cwd=action_safety.benchmark_project_root(),
                check=False,
            )

            if result.returncode != 0:
                return jsonify({"error": "Benchmark estimation failed"}), 502

            try:
                estimated_cost, model_count, provider_count = action_safety.parse_benchmark_estimate(result.stdout)
            except ValueError:
                return jsonify({"error": "Benchmark estimation failed"}), 502

            payload = {
                "estimated_cost": estimated_cost,
                "model_count": model_count,
                "provider_count": provider_count,
                "tier": tier,
            }
            _benchmark_estimate_cache[cache_key] = (time.monotonic(), payload)
            return jsonify({**payload, "cached": False})
        finally:
            _benchmark_estimate_lock.release()

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

            try:
                cmd = action_safety.approved_benchmark_command(tier, data.get("max_estimated_cost"))
            except ValueError:
                return jsonify({"error": action_safety.BENCHMARK_COST_VALIDATION_ERROR}), 400
            if quick:
                cmd.append("--quick")
            if no_judge:
                cmd.append("--no-judge")

            output_lines: deque = deque(maxlen=200)
            started_at = datetime.now(UTC).isoformat()

            proc = subprocess.Popen(  # Internal trusted benchmark script (scripts/benchmark_models.py) for long-running jobs. No user-controlled input.
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=action_safety.benchmark_project_root(),
            )

            _benchmark_proc.update(
                {
                    "pid": proc.pid,
                    "process": proc,
                    "started_at": started_at,
                    "output_lines": output_lines,
                }
            )

            # Reader thread to capture output. Redact secrets per-line so any
            # exception strings that contain ?key=... or Authorization headers
            # never reach API consumers via /api/benchmarks/status.
            def _read_output():
                try:
                    for line in proc.stdout:
                        output_lines.append(_redact_secrets(line.rstrip("\n")))
                except Exception as exc:
                    logger.debug("Benchmark reader output loop terminated: %s", exc, exc_info=exc)

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
                    "deprecated": cap.deprecated,
                    "successor": cap.successor,
                }
            )
        return jsonify({"models": models})

    except Exception as e:
        logger.error(f"Error getting model registry: {e}")
        return jsonify({"error": "Internal server error"}), 500


def _demo_mode_enabled() -> bool:
    """Return True if demo mode is explicitly enabled via DEEPR_DEMO env var."""
    return os.environ.get("DEEPR_DEMO", "").strip().lower() in ("1", "true", "yes", "on")


def _confirm_destructive(data: dict | None) -> bool:
    """Caller must include {"confirm": "DELETE_ALL_DATA"} in request body."""
    return isinstance(data, dict) and data.get("confirm") == "DELETE_ALL_DATA"


@app.route("/api/demo/load", methods=["POST"])
@action_safety.serialize_demo_action
def load_demo_data():
    """Load demo experts and sample completed jobs.

    Destructive: clears the research_queue table before seeding. Gated behind:
      - DEEPR_DEMO=1 environment variable, AND
      - request body containing {"confirm": "DELETE_ALL_DATA"}
    Returns 403 otherwise to prevent accidental or unauthenticated wipes.
    """
    if not _demo_mode_enabled():
        return jsonify(
            {
                "error": "Demo mode is disabled. Set DEEPR_DEMO=1 to enable.",
            }
        ), 403

    if not _confirm_destructive(request.json if request.is_json else None):
        return jsonify(
            {
                "error": "Destructive action requires explicit confirmation.",
                "hint": 'POST {"confirm": "DELETE_ALL_DATA"} to acknowledge that this clears the queue.',
            }
        ), 400

    import subprocess

    errors = []

    # 1. Run demo experts script
    try:
        result = subprocess.run(
            [sys.executable, "scripts/create_demo_experts.py"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path(__file__).resolve().parents[3]),
        )
        if result.returncode != 0:
            errors.append(f"Demo experts: {result.stderr[:200]}")
    except Exception as e:
        errors.append(f"Demo experts: {e}")

    # 2. Clear PREVIOUS DEMO jobs only, then seed fresh demo data. Demo jobs
    # are namespaced with a "demo-" id prefix precisely so this route can
    # never touch real work: an earlier version deleted every queue row and
    # every report directory, which meant "load demo data" silently destroyed
    # all paid research artifacts on disk.
    try:
        import sqlite3

        db_path = _cfg.get("queue_db_path", str(config_path / "queue.db"))
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM research_queue WHERE id LIKE 'demo-%'")
        conn.commit()
        conn.close()
    except Exception as e:
        errors.append(f"Clear jobs: {e}")

    # Also clean up this route's own orphaned demo report directories so
    # repeated loads don't accumulate disk usage. Only demo-prefixed dirs
    # are eligible; everything else on disk is someone's paid artifact.
    try:
        import shutil as _shutil

        storage_dir = Path(storage.base_path)
        if storage_dir.exists():
            for job_dir in storage_dir.iterdir():
                if job_dir.is_dir() and job_dir.name.startswith("demo-"):
                    _shutil.rmtree(job_dir, ignore_errors=True)
    except Exception as e:
        errors.append(f"Clear orphaned reports: {e}")

    created_jobs = 0
    now = datetime.now(UTC)
    # Short demo reports (~600-1000 words each) so result-detail renders real content
    demo_reports = demo_seed.DEMO_REPORTS
    sample_jobs = demo_seed.SAMPLE_JOBS

    for idx, sample in enumerate(sample_jobs):
        try:
            job_id = f"demo-{uuid.uuid4()}"
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
        except Exception as exc:
            errors.append(f"Failed to create demo job sample {idx}: {exc}")
            logger.warning("Failed creating demo job sample %s: %s", idx, exc)

    return jsonify(
        {
            "success": len(errors) == 0,
            "created_jobs": created_jobs,
            "errors": errors,
        }
    )


@app.route("/api/demo/clear", methods=["POST"])
@action_safety.serialize_demo_action
def clear_demo_data():
    """Clear demo jobs and their stored reports.

    Removes only demo-namespaced data (job ids and report directories with
    the "demo-" prefix); real research jobs and paid report artifacts are
    never eligible. Still gated behind:
      - DEEPR_DEMO=1 environment variable, AND
      - request body containing {"confirm": "DELETE_ALL_DATA"}
    Returns 403 otherwise to prevent accidental or unauthenticated wipes.
    """
    if not _demo_mode_enabled():
        return jsonify(
            {
                "error": "Demo mode is disabled. Set DEEPR_DEMO=1 to enable.",
            }
        ), 403

    if not _confirm_destructive(request.json if request.is_json else None):
        return jsonify(
            {
                "error": "Destructive action requires explicit confirmation.",
                "hint": 'POST {"confirm": "DELETE_ALL_DATA"} to acknowledge that this wipes jobs and reports.',
            }
        ), 400

    import sqlite3

    errors = []
    try:
        db_path = _cfg.get("queue_db_path", str(config_path / "queue.db"))
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM research_queue WHERE id LIKE 'demo-%'").fetchone()[0]
        conn.execute("DELETE FROM research_queue WHERE id LIKE 'demo-%'")
        conn.commit()
        conn.close()
    except Exception as e:
        errors.append(str(e))
        count = 0

    # Clean up stored demo reports only; every other directory is a real,
    # possibly paid, research artifact and is never deleted by this route.
    try:
        import shutil

        storage_dir = Path(storage.base_path)
        if storage_dir.exists():
            for job_dir in storage_dir.iterdir():
                if job_dir.is_dir() and job_dir.name.startswith("demo-"):
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
                "version": deepr.__version__,
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
    if _demo_mode_enabled():
        with app.app_context():
            try:
                logger.info("DEEPR_DEMO is set - auto-loading demo data")
                # Check if jobs already exist to avoid duplicate loads
                jobs = run_async(queue.list_jobs(limit=1))
                if not jobs:
                    # Use a synthetic request body with the confirm token so the
                    # gated load_demo_data() handler proceeds. The DEEPR_DEMO
                    # env var has already opted in to destructive demo behavior.
                    with app.test_request_context(
                        method="POST",
                        json={"confirm": "DELETE_ALL_DATA"},
                    ):
                        load_demo_data()
                    logger.info("Demo data loaded successfully")
                else:
                    logger.info("Jobs already exist - skipping demo auto-load")
            except Exception as e:
                logger.warning("Failed to auto-load demo data: %s", e)


_auto_load_demo()


def _run_loopback_development_server(*, host: str, port: int, debug: bool) -> None:
    """Run Flask-SocketIO's development server after a loopback-only check."""
    if not is_loopback_bind_host(host):
        raise RuntimeError("Werkzeug development server requires a loopback host")
    socketio.run(
        app,
        debug=debug,
        host=host,
        port=port,
        allow_unsafe_werkzeug=True,
    )


if __name__ == "__main__":
    import os as _os
    import sys as _sys

    debug = _os.environ.get("FLASK_DEBUG", "0") == "1"
    host = _os.environ.get("DEEPR_HOST", "127.0.0.1")
    port = int(_os.environ.get("DEEPR_PORT", "5000") or "5000")
    loopback = is_loopback_bind_host(host)
    if not _API_KEY and (not loopback or not _ALLOW_UNAUTHENTICATED_LOOPBACK):
        _sys.stderr.write(
            f"ERROR: refusing to start '{host}' without DEEPR_API_KEY. The dashboard\n"
            "ships provider-backed and data-bearing APIs, and loopback locality is\n"
            "not caller authentication. Set DEEPR_API_KEY. For an explicitly accepted\n"
            "loopback-only compatibility mode, set\n"
            "DEEPR_WEB_ALLOW_UNAUTHENTICATED_LOOPBACK=1.\n"
        )
        raise SystemExit(2)

    # Werkzeug is a development server, not a hardened production WSGI host.
    # Only opt out of Flask-SocketIO's production-safety check when the
    # operator has explicitly bound to loopback. For any non-loopback bind
    # the operator must front the app with a real server (gunicorn+eventlet,
    # uvicorn workers, etc.) - we surface that requirement instead of
    # silently running the dev server on a reachable interface.
    use_werkzeug = loopback

    print("\n" + "=" * 70)
    print("  Deepr Research Dashboard")
    print(f"  Running on http://{host}:{port}")
    if not _API_KEY:
        print("  WARNING: explicit unauthenticated loopback compatibility mode.")
    if not use_werkzeug:
        print("  ERROR: refusing to start Werkzeug dev server on a non-loopback host.")
        print("  Run behind gunicorn/eventlet or uvicorn for production.")
        print("=" * 70 + "\n")
        raise SystemExit(2)
    print("=" * 70 + "\n")
    _run_loopback_development_server(host=host, port=port, debug=debug)
