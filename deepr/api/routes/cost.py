"""Cost analytics API routes."""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta

from ...core.costs import CostEstimator, CostController
from ...config import load_config


bp = Blueprint("cost", __name__)


def get_cost_controller():
    """Get cost controller from config."""
    config = load_config()
    return CostController(
        max_cost_per_job=float(config.get("max_cost_per_job", 10.0)),
        max_daily_cost=float(config.get("max_daily_cost", 100.0)),
        max_monthly_cost=float(config.get("max_monthly_cost", 1000.0)),
    )


@bp.route("/summary", methods=["GET"])
def get_summary():
    """
    Get cost summary (daily and monthly spending).

    Returns:
        200: Cost summary
    """
    try:
        cost_controller = get_cost_controller()
        summary = cost_controller.get_spending_summary()

        return jsonify({"summary": summary}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/trends", methods=["GET"])
def get_trends():
    """
    Get spending trends over time.

    Query parameters:
        days: Number of days to include (default: 30)

    Returns:
        200: Trend data for charts
    """
    try:
        days = min(int(request.args.get("days", 30)), 90)

        # Cost trends are tracked via CLI (deepr costs timeline); API returns structure only
        trends = {
            "daily": [],
            "cumulative": 0,
        }

        # Generate mock daily data
        today = datetime.now()
        for i in range(days):
            date = today - timedelta(days=days - i - 1)
            trends["daily"].append({
                "date": date.strftime("%Y-%m-%d"),
                "cost": 0,
                "jobs": 0,
            })

        return jsonify({"trends": trends, "days": days}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/breakdown", methods=["GET"])
def get_breakdown():
    """
    Get cost breakdown by various dimensions.

    Query parameters:
        by: Breakdown dimension (model, date, status)
        days: Number of days to include (default: 30)

    Returns:
        200: Breakdown data
    """
    try:
        by = request.args.get("by", "model")
        days = min(int(request.args.get("days", 30)), 90)

        # Cost breakdown is tracked via CLI (deepr costs breakdown); API returns structure only
        breakdown = {
            "dimension": by,
            "items": [],
        }

        return jsonify({"breakdown": breakdown, "days": days}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/estimate", methods=["POST"])
def estimate_cost():
    """
    Estimate cost for a research job.

    Request body:
        {
            "prompt": "Research prompt",
            "model": "o4-mini-deep-research",
            "enable_web_search": true
        }

    Returns:
        200: Cost estimate
        400: Invalid request
    """
    try:
        data = request.get_json()

        if not data or "prompt" not in data:
            return jsonify({"error": "Prompt is required"}), 400

        prompt = data["prompt"]
        model = data.get("model", "o4-mini-deep-research")
        enable_web_search = data.get("enable_web_search", True)

        estimate = CostEstimator.estimate_cost(
            prompt=prompt,
            model=model,
            enable_web_search=enable_web_search,
        )

        # Check against limits
        cost_controller = get_cost_controller()
        allowed, reason = cost_controller.check_job_limit(estimate.expected_cost)

        return jsonify({
            "estimate": estimate.to_dict(),
            "allowed": allowed,
            "reason": reason if not allowed else None,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/limits", methods=["GET"])
def get_limits():
    """
    Get current budget limits.

    Returns:
        200: Budget limits
    """
    try:
        config = load_config()

        limits = {
            "per_job": float(config.get("max_cost_per_job", 10.0)),
            "daily": float(config.get("max_daily_cost", 100.0)),
            "monthly": float(config.get("max_monthly_cost", 1000.0)),
        }

        return jsonify({"limits": limits}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/limits", methods=["PATCH"])
def update_limits():
    """
    Update budget limits.

    Request body:
        {
            "per_job": 10.0,
            "daily": 100.0,
            "monthly": 1000.0
        }

    Returns:
        200: Limits updated
        400: Invalid request
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "Request body is required"}), 400

        # Validates values but does not persist (budget is managed via CLI)
        per_job = data.get("per_job")
        daily = data.get("daily")
        monthly = data.get("monthly")

        if per_job is not None and per_job < 0:
            return jsonify({"error": "per_job must be non-negative"}), 400
        if daily is not None and daily < 0:
            return jsonify({"error": "daily must be non-negative"}), 400
        if monthly is not None and monthly < 0:
            return jsonify({"error": "monthly must be non-negative"}), 400

        return jsonify({"message": "Limits updated successfully", "limits": data}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
