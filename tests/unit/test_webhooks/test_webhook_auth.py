"""Regression tests: webhook server now refuses anonymous POSTs.

The previous behaviour silently accepted any request when
``DEEPR_WEBHOOK_SECRET`` was unset; this test pins down the new
fail-closed semantics.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def test_post_without_secret_returns_503():
    from deepr.webhooks.server import create_webhook_server

    with patch.dict("os.environ", {}, clear=False):
        # Ensure no secret is configured
        with patch("os.getenv", return_value=None):
            app = create_webhook_server(on_completion=AsyncMock(), host="127.0.0.1", port=5000)

    client = app.test_client()
    resp = client.post("/webhook", json={"id": "test", "status": "completed"})
    assert resp.status_code == 503
    assert "not configured" in resp.get_json()["error"].lower()


def test_non_loopback_bind_without_secret_raises():
    from deepr.webhooks.server import create_webhook_server

    with patch("os.getenv", return_value=None):
        with pytest.raises(RuntimeError, match="DEEPR_WEBHOOK_SECRET"):
            create_webhook_server(on_completion=AsyncMock(), host="0.0.0.0", port=5000)


def test_valid_signature_passes():
    import hashlib
    import hmac

    from deepr.webhooks.server import create_webhook_server

    secret = "test-secret-123"
    on_completion = AsyncMock()
    with patch("os.getenv", return_value=secret):
        app = create_webhook_server(on_completion=on_completion, host="127.0.0.1", port=5000)

    body = b'{"id": "job-1", "status": "completed"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    client = app.test_client()
    resp = client.post(
        "/webhook", data=body, content_type="application/json", headers={"X-Webhook-Signature": f"sha256={sig}"}
    )
    assert resp.status_code == 200


def test_invalid_signature_returns_403():
    from deepr.webhooks.server import create_webhook_server

    with patch("os.getenv", return_value="real-secret"):
        app = create_webhook_server(on_completion=AsyncMock(), host="127.0.0.1", port=5000)

    client = app.test_client()
    resp = client.post(
        "/webhook",
        data=b'{"id": "x"}',
        content_type="application/json",
        headers={"X-Webhook-Signature": "sha256=garbage"},
    )
    assert resp.status_code == 403
