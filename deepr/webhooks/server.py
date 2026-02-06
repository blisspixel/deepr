"""Flask webhook server implementation."""

import hashlib
import hmac
import logging
import os
from typing import Callable

from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)


def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 webhook signature.

    Args:
        payload: Raw request body
        signature: Signature from X-Webhook-Signature header
        secret: Shared secret for HMAC computation

    Returns:
        True if signature is valid
    """
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def create_webhook_server(
    on_completion: Callable,
    host: str = "127.0.0.1",
    port: int = 5000,
    debug: bool = False,
) -> Flask:
    """
    Create Flask webhook server.

    Args:
        on_completion: Callback function for job completion
        host: Server host (defaults to localhost)
        port: Server port
        debug: Enable debug mode

    Returns:
        Flask app instance
    """
    app = Flask(__name__)
    app.config["DEBUG"] = debug

    webhook_secret = os.getenv("DEEPR_WEBHOOK_SECRET")

    @app.route("/webhook", methods=["POST"])
    async def webhook():
        """Handle webhook POST requests from AI provider."""
        try:
            # Verify signature if a secret is configured
            if webhook_secret:
                signature = request.headers.get("X-Webhook-Signature", "")
                if not signature or not _verify_signature(request.get_data(), signature, webhook_secret):
                    logger.warning("Webhook signature verification failed")
                    return jsonify({"error": "Invalid signature"}), 403

            data = request.json

            if not data:
                return jsonify({"error": "No data provided"}), 400

            # Extract job information
            job_id = data.get("metadata", {}).get("run_id") or data.get("id")
            status = data.get("status", "unknown")

            logger.info("Webhook received for job %s: %s", job_id, status)

            # Call completion handler
            await on_completion(job_id, data)

            return jsonify({"status": "success"}), 200

        except Exception as e:
            logger.error("Webhook error: %s", type(e).__name__)
            return jsonify({"error": "Internal server error"}), 500

    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "healthy"}), 200

    return app
