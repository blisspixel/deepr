"""Flask webhook server implementation."""

from flask import Flask, request, jsonify
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)


def create_webhook_server(
    on_completion: Callable,
    host: str = "0.0.0.0",
    port: int = 5000,
    debug: bool = False,
) -> Flask:
    """
    Create Flask webhook server.

    Args:
        on_completion: Callback function for job completion
        host: Server host
        port: Server port
        debug: Enable debug mode

    Returns:
        Flask app instance
    """
    app = Flask(__name__)
    app.config["DEBUG"] = debug

    @app.route("/webhook", methods=["POST"])
    async def webhook():
        """Handle webhook POST requests from AI provider."""
        try:
            data = request.json

            if not data:
                return jsonify({"error": "No data provided"}), 400

            # Extract job information
            job_id = data.get("metadata", {}).get("run_id") or data.get("id")
            status = data.get("status", "unknown")

            logger.info(f"Webhook received for job {job_id}: {status}")

            # Call completion handler
            await on_completion(job_id, data)

            return jsonify({"status": "success"}), 200

        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "healthy"}), 200

    return app
