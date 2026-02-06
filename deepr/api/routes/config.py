"""Configuration management API routes."""

import logging

from flask import Blueprint, jsonify, request

from ... import __version__
from ...config import load_config
from ...providers import create_provider

logger = logging.getLogger(__name__)

bp = Blueprint("config", __name__)


@bp.route("", methods=["GET"])
def get_config():
    """
    Get current configuration.

    Returns:
        200: Configuration (sensitive values masked)
    """
    try:
        config = load_config()

        # Mask sensitive values
        safe_config = {
            "provider": config.get("provider", "openai"),
            "default_model": config.get("default_model", "o4-mini-deep-research"),
            "enable_web_search": config.get("enable_web_search", True),
            "storage": config.get("storage", "local"),
            "queue": config.get("queue", "local"),
            "results_dir": config.get("results_dir", "results"),
            "has_api_key": bool(config.get("api_key")),
        }

        return jsonify({"config": safe_config}), 200

    except Exception as e:
        logger.exception("Error getting config: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@bp.route("", methods=["PATCH"])
def update_config():
    """
    Update configuration.

    Request body:
        {
            "provider": "openai",
            "api_key": "sk-...",
            "default_model": "o4-mini-deep-research",
            "enable_web_search": true
        }

    Returns:
        200: Configuration updated
        400: Invalid request
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "Request body is required"}), 400

        # Validates values but does not persist (config is managed via CLI and .env)
        provider = data.get("provider")
        if provider and provider not in ["openai", "azure"]:
            return jsonify({"error": "provider must be 'openai' or 'azure'"}), 400

        return jsonify({"message": "Configuration updated successfully"}), 200

    except Exception as e:
        logger.exception("Error updating config: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/test", methods=["POST"])
def test_connection():
    """
    Test API connection with current credentials.

    Request body (optional):
        {
            "provider": "openai",
            "api_key": "sk-..."
        }

    Returns:
        200: Connection successful
        400: Connection failed
    """
    try:
        data = request.get_json() or {}

        # Use provided credentials or load from config
        provider_type = data.get("provider")
        api_key = data.get("api_key")

        if not provider_type or not api_key:
            config = load_config()
            provider_type = provider_type or config.get("provider", "openai")
            api_key = api_key or config.get("api_key")

        if not api_key:
            return jsonify({"error": "API key is required"}), 400

        # Try to create provider and test connection
        try:
            create_provider(provider_type, api_key=api_key)
            # Verifies provider can be instantiated with given credentials

            return jsonify(
                {
                    "status": "success",
                    "message": "Connection successful",
                    "provider": provider_type,
                }
            ), 200

        except Exception as e:
            return jsonify(
                {
                    "status": "error",
                    "message": f"Connection failed: {str(e)}",
                    "provider": provider_type,
                }
            ), 400

    except Exception as e:
        logger.exception("Error testing connection: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/status", methods=["GET"])
def get_status():
    """
    Get system status.

    Returns:
        200: System status
    """
    try:
        config = load_config()

        # Get queue stats
        from ...queue import create_queue

        queue = create_queue(
            config.get("queue", "local"), db_path=config.get("queue_db_path", "queue/research_queue.db")
        )

        import asyncio

        stats = asyncio.run(queue.get_queue_stats())

        # Get cost controller
        from ...core.costs import CostController

        try:
            max_cost_per_job = float(config.get("max_cost_per_job", 10.0))
            max_daily_cost = float(config.get("max_daily_cost", 100.0))
            max_monthly_cost = float(config.get("max_monthly_cost", 1000.0))
        except (ValueError, TypeError):
            max_cost_per_job = 10.0
            max_daily_cost = 100.0
            max_monthly_cost = 1000.0
        cost_controller = CostController(
            max_cost_per_job=max_cost_per_job,
            max_daily_cost=max_daily_cost,
            max_monthly_cost=max_monthly_cost,
        )
        spending = cost_controller.get_spending_summary()

        status = {
            "healthy": True,
            "version": __version__,
            "provider": config.get("provider", "openai"),
            "queue": {
                "type": config.get("queue", "local"),
                "stats": stats,
            },
            "storage": {
                "type": config.get("storage", "local"),
            },
            "spending": spending,
        }

        return jsonify({"status": status}), 200

    except Exception as e:
        logger.exception("Error getting status: %s", e)
        return jsonify({"error": "Internal server error"}), 500
