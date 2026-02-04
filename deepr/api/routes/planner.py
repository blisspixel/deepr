"""
Research Planner API Routes

Endpoints for the "Prep" feature - decompose scenarios into multiple research tasks.
"""

import logging
import uuid
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from deepr.services.research_planner import create_planner
from deepr.services.queue import get_queue
from deepr.services.cost_estimation import CostEstimator
from deepr.models.job import Job, JobStatus

logger = logging.getLogger(__name__)

bp = Blueprint("planner", __name__)


@bp.route("/plan", methods=["POST"])
def plan_research():
    """
    Plan research strategy using GPT-5 models.

    Request:
        {
            "scenario": "Meeting with Company X about Topic Y tomorrow",
            "max_tasks": 5,
            "context": "Optional additional context",
            "planner_model": "gpt-5-mini",  // gpt-5, gpt-5-mini, gpt-5-nano
            "provider": "openai"  // or "azure"
        }

    Response:
        {
            "plan": [
                {
                    "title": "Company Background Research",
                    "prompt": "Research Company X's...",
                    "estimated_cost": 0.15
                },
                ...
            ],
            "total_estimated_cost": 0.75
        }
    """
    try:
        data = request.get_json()

        # Validate required fields
        if not data or "scenario" not in data:
            return jsonify({"error": "Missing required field: scenario"}), 400

        scenario = data["scenario"]
        try:
            max_tasks = int(data.get("max_tasks", 5))
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid max_tasks parameter"}), 400
        context = data.get("context")
        planner_model = data.get("planner_model", "gpt-5-mini")
        provider = data.get("provider", "openai")
        azure_endpoint = data.get("azure_endpoint")

        # Validate planner model is GPT-5 family
        valid_models = ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5-chat"]
        if planner_model not in valid_models:
            return jsonify({
                "error": f"Invalid planner model. Must be one of: {', '.join(valid_models)}"
            }), 400

        # Create planner
        planner = create_planner(
            model=planner_model,
            provider=provider,
            azure_endpoint=azure_endpoint,
        )

        # Generate research plan
        tasks = planner.plan_research(
            scenario=scenario,
            max_tasks=max_tasks,
            context=context,
        )

        # Estimate cost for each task
        # These will be executed with o4-mini-deep-research or o3-deep-research
        research_model = data.get("research_model", "o4-mini-deep-research")
        enable_web_search = data.get("enable_web_search", True)

        plan_with_costs = []
        total_cost = 0.0

        for task in tasks:
            estimate = CostEstimator.estimate_cost(
                prompt=task["prompt"],
                model=research_model,
                enable_web_search=enable_web_search,
            )
            task["estimated_cost"] = estimate.expected_cost
            total_cost += estimate.expected_cost
            plan_with_costs.append(task)

        return jsonify({
            "plan": plan_with_costs,
            "total_estimated_cost": total_cost,
            "planner_model": planner_model,
            "research_model": research_model,
        }), 200

    except Exception as e:
        logger.exception("Error planning research: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/execute", methods=["POST"])
def execute_plan():
    """
    Execute a research plan by creating batch jobs.

    Request:
        {
            "scenario": "Meeting with Company X about Topic Y",
            "tasks": [
                {"title": "...", "prompt": "..."},
                ...
            ],
            "model": "o4-mini-deep-research",
            "priority": 3,
            "enable_web_search": true
        }

    Response:
        {
            "batch_id": "batch-uuid",
            "jobs": [
                {"id": "job-uuid-1", "title": "...", "status": "pending"},
                ...
            ],
            "total_estimated_cost": 0.75
        }
    """
    try:
        data = request.get_json()

        # Validate required fields
        if not data or "tasks" not in data:
            return jsonify({"error": "Missing required field: tasks"}), 400

        tasks = data["tasks"]
        if not isinstance(tasks, list) or len(tasks) == 0:
            return jsonify({"error": "tasks must be a non-empty array"}), 400

        scenario = data.get("scenario", "Research batch")
        model = data.get("model", "o4-mini-deep-research")
        try:
            priority = int(data.get("priority", 3))
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid priority parameter"}), 400
        enable_web_search = data.get("enable_web_search", True)

        # Generate batch ID
        batch_id = f"batch-{uuid.uuid4().hex[:12]}"

        # Create jobs for each task
        queue = get_queue()
        jobs = []
        total_cost = 0.0

        for task in tasks:
            if not isinstance(task, dict) or "prompt" not in task:
                continue

            job_id = str(uuid.uuid4())
            title = task.get("title", "Research task")
            prompt = task["prompt"]

            # Create job object
            job = Job(
                id=job_id,
                prompt=prompt,
                model=model,
                priority=priority,
                enable_web_search=enable_web_search,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                status=JobStatus.PENDING,
                metadata={
                    "batch_id": batch_id,
                    "batch_scenario": scenario,
                    "task_title": title,
                },
            )

            # Estimate cost
            estimate = CostEstimator.estimate_cost(
                prompt=prompt,
                model=model,
                enable_web_search=enable_web_search,
            )
            job.estimated_cost = estimate.expected_cost
            total_cost += estimate.expected_cost

            # Enqueue
            queue.enqueue(job)

            jobs.append({
                "id": job_id,
                "title": title,
                "prompt": prompt,
                "status": "pending",
                "estimated_cost": estimate.expected_cost,
            })

        return jsonify({
            "batch_id": batch_id,
            "scenario": scenario,
            "jobs": jobs,
            "total_jobs": len(jobs),
            "total_estimated_cost": total_cost,
        }), 200

    except Exception as e:
        logger.exception("Error executing plan: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/batch/<batch_id>", methods=["GET"])
def get_batch_status(batch_id: str):
    """
    Get status of all jobs in a batch.

    Response:
        {
            "batch_id": "batch-uuid",
            "scenario": "Meeting with Company X",
            "jobs": [
                {
                    "id": "job-uuid-1",
                    "title": "...",
                    "status": "completed",
                    "actual_cost": 0.12
                },
                ...
            ],
            "summary": {
                "total": 5,
                "pending": 0,
                "in_progress": 1,
                "completed": 3,
                "failed": 1,
                "total_cost": 0.68
            }
        }
    """
    try:
        queue = get_queue()

        # Get all jobs in batch
        # This depends on queue implementation having a method to filter by metadata
        # For now, we'll get all jobs and filter
        all_jobs = queue.list_jobs(limit=1000)  # Adjust as needed

        batch_jobs = []
        for job in all_jobs:
            if (
                hasattr(job, "metadata")
                and job.metadata
                and job.metadata.get("batch_id") == batch_id
            ):
                batch_jobs.append({
                    "id": job.id,
                    "title": job.metadata.get("task_title", "Research task"),
                    "prompt": job.prompt,
                    "status": job.status.value,
                    "estimated_cost": getattr(job, "estimated_cost", None),
                    "actual_cost": getattr(job, "actual_cost", None),
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                })

        if not batch_jobs:
            return jsonify({"error": "Batch not found"}), 404

        # Calculate summary
        summary = {
            "total": len(batch_jobs),
            "pending": sum(1 for j in batch_jobs if j["status"] == "pending"),
            "in_progress": sum(1 for j in batch_jobs if j["status"] == "in_progress"),
            "completed": sum(1 for j in batch_jobs if j["status"] == "completed"),
            "failed": sum(1 for j in batch_jobs if j["status"] == "failed"),
            "total_cost": sum(
                j.get("actual_cost") or j.get("estimated_cost") or 0.0
                for j in batch_jobs
            ),
        }

        # Get scenario from first job's metadata (stored in the job list item directly)
        scenario = "Research batch"
        if batch_jobs:
            # The batch_scenario was stored in job.metadata, which we don't have here
            # Use a default value
            scenario = "Research batch"

        return jsonify({
            "batch_id": batch_id,
            "scenario": scenario,
            "jobs": batch_jobs,
            "summary": summary,
        }), 200

    except Exception as e:
        logger.exception("Error getting batch status %s: %s", batch_id, e)
        return jsonify({"error": "Internal server error"}), 500
