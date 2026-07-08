"""Flask webhook server implementation."""

import asyncio
import hashlib
import hmac
import inspect
import logging
import os
from collections.abc import Callable
from typing import Any

from flask import Flask, Response, jsonify, request

logger = logging.getLogger(__name__)
WebhookResponse = tuple[Response, int]
CompletionCallback = Callable[[str | None, dict[str, Any]], object]


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


def _extract_job_id(data: dict[str, Any]) -> str | None:
    """Return the provider job id when it is present and well formed."""
    metadata = data.get("metadata", {})
    metadata_id = metadata.get("run_id") if isinstance(metadata, dict) else None
    if metadata_id is not None and not isinstance(metadata_id, str):
        raise ValueError("Webhook job id must be a string when present")
    job_id = metadata_id or data.get("id")

    if job_id is None or isinstance(job_id, str):
        return job_id

    raise ValueError("Webhook job id must be a string when present")


def _parse_webhook_payload() -> dict[str, Any] | WebhookResponse:
    parsed = request.get_json(silent=True)

    if parsed is None:
        return jsonify({"error": "No data provided"}), 400
    if not isinstance(parsed, dict):
        return jsonify({"error": "Webhook payload must be a JSON object"}), 400
    if not parsed:
        return jsonify({"error": "No data provided"}), 400

    return parsed


def _handle_webhook(webhook_secret: str | None, on_completion: CompletionCallback) -> WebhookResponse:
    try:
        # Always require a signature header. When no secret is configured,
        # we refuse every request - there is no "trust the loopback"
        # fallback because a local process running under the same user
        # could still spoof callbacks.
        if not webhook_secret:
            logger.warning("Webhook rejected: DEEPR_WEBHOOK_SECRET is not configured")
            return jsonify({"error": "Webhook authentication is not configured"}), 503

        signature = request.headers.get("X-Webhook-Signature", "")
        if not signature or not _verify_signature(request.get_data(), signature, webhook_secret):
            logger.warning("Webhook signature verification failed")
            return jsonify({"error": "Invalid signature"}), 403

        payload = _parse_webhook_payload()
        if not isinstance(payload, dict):
            return payload

        try:
            job_id = _extract_job_id(payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        status_value = payload.get("status", "unknown")
        status = status_value if isinstance(status_value, str) else "unknown"

        logger.info("Webhook received for job %s: %s", job_id, status)

        # Call completion handler - sync OR async accepted.
        result = on_completion(job_id, payload)
        if inspect.iscoroutine(result):
            asyncio.run(result)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error("Webhook error: %s", type(e).__name__)
        return jsonify({"error": "Internal server error"}), 500


def create_webhook_server(
    on_completion: CompletionCallback,
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
    # Cap request body. Provider webhooks are JSON status payloads; anything
    # over 1 MiB is almost certainly hostile.
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

    webhook_secret = os.getenv("DEEPR_WEBHOOK_SECRET")

    # Refuse to start the server without a shared secret when bound to any
    # non-loopback interface. The previous behaviour silently accepted any
    # anonymous POST to /webhook when DEEPR_WEBHOOK_SECRET was unset, which
    # meant a misconfigured deploy could be triggered to invoke ``on_completion``
    # by any reachable peer.
    if not webhook_secret and host not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError(
            "DEEPR_WEBHOOK_SECRET must be set when binding the webhook server "
            f"to a non-loopback host ({host!r}). Set the env var or bind 127.0.0.1."
        )

    def webhook() -> WebhookResponse:
        """Handle webhook POST requests from AI provider.

        Sync handler - when ``on_completion`` is async we dispatch it
        via ``asyncio.run``. The previous ``async def`` version required
        the ``flask[async]`` extra and produced confusing 500 errors
        under test clients that already manage an event loop.
        """
        return _handle_webhook(webhook_secret, on_completion)

    def health() -> WebhookResponse:
        """Health check endpoint."""
        return jsonify({"status": "healthy"}), 200

    app.add_url_rule("/webhook", "webhook", webhook, methods=["POST"])
    app.add_url_rule("/health", "health", health, methods=["GET"])

    return app
