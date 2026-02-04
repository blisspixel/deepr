"""Job management API routes."""

import asyncio
import logging
from flask import Blueprint, request, jsonify
from typing import Optional

from ...queue import create_queue
from ...queue.base import ResearchJob, JobStatus
from ...core.costs import CostEstimator, CostController
from ...config import load_config

logger = logging.getLogger(__name__)

bp = Blueprint("jobs", __name__)


def get_queue():
    """Get queue instance from config."""
    config = load_config()
    queue_type = config.get("queue", "local")
    db_path = config.get("queue_db_path", "queue/research_queue.db")
    return create_queue(queue_type, db_path=db_path)


def get_cost_controller():
    """Get cost controller from config."""
    config = load_config()
    try:
        max_cost_per_job = float(config.get("max_cost_per_job", 10.0))
        max_daily_cost = float(config.get("max_daily_cost", 100.0))
        max_monthly_cost = float(config.get("max_monthly_cost", 1000.0))
    except (ValueError, TypeError):
        # Fall back to defaults if config values are invalid
        max_cost_per_job = 10.0
        max_daily_cost = 100.0
        max_monthly_cost = 1000.0
    return CostController(
        max_cost_per_job=max_cost_per_job,
        max_daily_cost=max_daily_cost,
        max_monthly_cost=max_monthly_cost,
    )


@bp.route("", methods=["POST"])
def submit_job():
    """
    Submit a new research job.

    Request body:
        {
            "prompt": "Research prompt",
            "model": "o4-mini-deep-research",
            "priority": 1,
            "enable_web_search": true,
            "file_ids": [],
            "config": {}
        }

    Returns:
        201: Job created successfully
        400: Invalid request
        429: Budget exceeded
    """
    try:
        data = request.get_json()

        # Validate required fields
        if not data or "prompt" not in data:
            return jsonify({"error": "Prompt is required"}), 400

        prompt = data["prompt"]
        model = data.get("model", "o4-mini-deep-research")
        priority = data.get("priority", 1)
        enable_web_search = data.get("enable_web_search", True)
        file_ids = data.get("file_ids", [])
        config = data.get("config", {})

        # Estimate cost
        estimate = CostEstimator.estimate_cost(
            prompt=prompt,
            model=model,
            enable_web_search=enable_web_search,
        )

        # Check cost limits
        cost_controller = get_cost_controller()
        allowed, reason = cost_controller.check_job_limit(estimate.expected_cost)

        if not allowed:
            return jsonify({"error": reason, "estimated_cost": estimate.to_dict()}), 429

        # Create job
        job = ResearchJob(
            prompt=prompt,
            model=model,
            priority=priority,
            enable_web_search=enable_web_search,
            file_ids=file_ids,
            config=config,
            estimated_cost=estimate.expected_cost,
        )

        # Enqueue job
        queue = get_queue()
        asyncio.run(queue.enqueue(job))

        return jsonify({
            "job": job.to_dict(),
            "estimated_cost": estimate.to_dict(),
        }), 201

    except Exception as e:
        logger.exception("Error submitting job: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@bp.route("", methods=["GET"])
def list_jobs():
    """
    List jobs with filtering and pagination.

    Query parameters:
        status: Filter by status (pending, in_progress, completed, failed)
        limit: Number of results (default: 50, max: 100)
        offset: Pagination offset (default: 0)

    Returns:
        200: List of jobs
    """
    try:
        status = request.args.get("status")
        try:
            limit = min(int(request.args.get("limit", 50)), 100)
            offset = int(request.args.get("offset", 0))
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid limit or offset parameter"}), 400

        queue = get_queue()
        jobs = asyncio.run(queue.list_jobs(status=status, limit=limit, offset=offset))

        return jsonify({
            "jobs": [job.to_dict() for job in jobs],
            "limit": limit,
            "offset": offset,
            "total": len(jobs),
        }), 200

    except Exception as e:
        logger.exception("Error listing jobs: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/<job_id>", methods=["GET"])
def get_job(job_id: str):
    """
    Get job details by ID.

    Returns:
        200: Job details
        404: Job not found
    """
    try:
        queue = get_queue()
        job = asyncio.run(queue.get_job(job_id))

        if not job:
            return jsonify({"error": "Job not found"}), 404

        return jsonify({"job": job.to_dict()}), 200

    except Exception as e:
        logger.exception("Error getting job %s: %s", job_id, e)
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/<job_id>", methods=["DELETE"])
def delete_job(job_id: str):
    """
    Delete a job.

    Returns:
        204: Job deleted
        404: Job not found
    """
    try:
        queue = get_queue()
        success = asyncio.run(queue.delete_job(job_id))

        if not success:
            return jsonify({"error": "Job not found"}), 404

        return "", 204

    except Exception as e:
        logger.exception("Error deleting job %s: %s", job_id, e)
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    """
    Cancel a job.

    Returns:
        200: Job cancelled
        404: Job not found
        400: Job cannot be cancelled
    """
    try:
        queue = get_queue()
        success = asyncio.run(queue.cancel_job(job_id))

        if not success:
            return jsonify({"error": "Job not found or cannot be cancelled"}), 400

        return jsonify({"message": "Job cancelled successfully"}), 200

    except Exception as e:
        logger.exception("Error cancelling job %s: %s", job_id, e)
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/batch", methods=["POST"])
def submit_batch():
    """
    Submit multiple jobs at once.

    Request body:
        {
            "jobs": [
                {"prompt": "...", "model": "..."},
                {"prompt": "...", "model": "..."}
            ]
        }

    Returns:
        201: Jobs created
        400: Invalid request
    """
    try:
        data = request.get_json()

        if not data or "jobs" not in data:
            return jsonify({"error": "Jobs array is required"}), 400

        jobs_data = data["jobs"]
        created_jobs = []
        errors = []

        for i, job_data in enumerate(jobs_data):
            try:
                prompt = job_data.get("prompt")
                if not prompt:
                    errors.append({"index": i, "error": "Prompt is required"})
                    continue

                model = job_data.get("model", "o4-mini-deep-research")
                priority = job_data.get("priority", 1)
                enable_web_search = job_data.get("enable_web_search", True)

                # Estimate and check cost
                estimate = CostEstimator.estimate_cost(
                    prompt=prompt,
                    model=model,
                    enable_web_search=enable_web_search,
                )

                cost_controller = get_cost_controller()
                allowed, reason = cost_controller.check_job_limit(estimate.expected_cost)

                if not allowed:
                    errors.append({"index": i, "error": reason})
                    continue

                # Create and enqueue job
                job = ResearchJob(
                    prompt=prompt,
                    model=model,
                    priority=priority,
                    enable_web_search=enable_web_search,
                    estimated_cost=estimate.expected_cost,
                )

                queue = get_queue()
                asyncio.run(queue.enqueue(job))
                created_jobs.append(job.to_dict())

            except Exception as e:
                errors.append({"index": i, "error": str(e)})

        return jsonify({
            "created": created_jobs,
            "errors": errors,
            "total": len(jobs_data),
            "successful": len(created_jobs),
            "failed": len(errors),
        }), 201

    except Exception as e:
        logger.exception("Error submitting batch jobs: %s", e)
        return jsonify({"error": "Internal server error"}), 500
