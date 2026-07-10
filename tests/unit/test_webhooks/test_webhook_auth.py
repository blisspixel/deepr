"""Regression tests: webhook server now refuses anonymous POSTs.

The previous behaviour silently accepted any request when
``DEEPR_WEBHOOK_SECRET`` was unset; this test pins down the new
fail-closed semantics.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _signature(secret: str, body: bytes) -> str:
    import hashlib
    import hmac

    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


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
    from deepr.webhooks.server import create_webhook_server

    secret = "test-secret-123"
    on_completion = AsyncMock()
    with patch("os.getenv", return_value=secret):
        app = create_webhook_server(on_completion=on_completion, host="127.0.0.1", port=5000)

    body = b'{"id": "job-1", "status": "completed"}'
    client = app.test_client()
    resp = client.post(
        "/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Webhook-Signature": _signature(secret, body)},
    )
    assert resp.status_code == 200
    on_completion.assert_called_once()


def test_valid_signed_payload_is_not_reflected():
    from deepr.webhooks.server import create_webhook_server

    secret = "test-secret-123"
    on_completion = AsyncMock()
    with patch("os.getenv", return_value=secret):
        app = create_webhook_server(on_completion=on_completion, host="127.0.0.1", port=5000)

    marker = "<script>alert(1)</script>"
    body = ('{"id": "job-1", "status": "completed", "marker": "' + marker + '"}').encode()
    resp = app.test_client().post(
        "/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Webhook-Signature": _signature(secret, body)},
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "success"}
    assert marker.encode() not in resp.data
    on_completion.assert_awaited_once_with("job-1", {"id": "job-1", "status": "completed", "marker": marker})


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


def test_signed_invalid_json_returns_400_without_callback():
    from deepr.webhooks.server import create_webhook_server

    secret = "test-secret-123"
    on_completion = AsyncMock()
    with patch("os.getenv", return_value=secret):
        app = create_webhook_server(on_completion=on_completion, host="127.0.0.1", port=5000)

    body = b"{not-json"
    resp = app.test_client().post(
        "/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Webhook-Signature": _signature(secret, body)},
    )

    assert resp.status_code == 400
    on_completion.assert_not_called()


def test_signed_non_object_json_returns_400_without_callback():
    from deepr.webhooks.server import create_webhook_server

    secret = "test-secret-123"
    on_completion = AsyncMock()
    with patch("os.getenv", return_value=secret):
        app = create_webhook_server(on_completion=on_completion, host="127.0.0.1", port=5000)

    body = b"[1]"
    resp = app.test_client().post(
        "/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Webhook-Signature": _signature(secret, body)},
    )

    assert resp.status_code == 400
    assert "json object" in resp.get_json()["error"].lower()
    on_completion.assert_not_called()


def test_signed_wrong_content_type_returns_400_without_callback():
    from deepr.webhooks.server import create_webhook_server

    secret = "test-secret-123"
    on_completion = AsyncMock()
    with patch("os.getenv", return_value=secret):
        app = create_webhook_server(on_completion=on_completion, host="127.0.0.1", port=5000)

    body = b'{"id": "job-1", "status": "completed"}'
    resp = app.test_client().post(
        "/webhook", data=body, content_type="text/plain", headers={"X-Webhook-Signature": _signature(secret, body)}
    )

    assert resp.status_code == 400
    on_completion.assert_not_called()


def test_signed_non_string_job_id_returns_400_without_callback():
    from deepr.webhooks.server import create_webhook_server

    secret = "test-secret-123"
    on_completion = AsyncMock()
    with patch("os.getenv", return_value=secret):
        app = create_webhook_server(on_completion=on_completion, host="127.0.0.1", port=5000)

    body = b'{"id": 123, "status": "completed"}'
    resp = app.test_client().post(
        "/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Webhook-Signature": _signature(secret, body)},
    )

    assert resp.status_code == 400
    assert "job id" in resp.get_json()["error"].lower()
    on_completion.assert_not_called()


def test_webhook_validation_exception_is_not_reflected():
    from deepr.webhooks.server import create_webhook_server

    secret = "test-secret-123"
    on_completion = AsyncMock()
    with patch("os.getenv", return_value=secret):
        app = create_webhook_server(on_completion=on_completion, host="127.0.0.1", port=5000)

    body = b'{"id": 123, "status": "completed"}'
    with patch("deepr.webhooks.server._extract_job_id", side_effect=ValueError("<script>secret traceback</script>")):
        resp = app.test_client().post(
            "/webhook",
            data=body,
            content_type="application/json",
            headers={"X-Webhook-Signature": _signature(secret, body)},
        )

    assert resp.status_code == 400
    assert resp.mimetype == "application/json"
    assert resp.get_json() == {"error": "Webhook job id must be a string when present"}
    assert b"script" not in resp.data
    on_completion.assert_not_called()


def test_signed_falsy_non_string_metadata_job_id_returns_400_without_callback():
    from deepr.webhooks.server import create_webhook_server

    secret = "test-secret-123"
    on_completion = AsyncMock()
    with patch("os.getenv", return_value=secret):
        app = create_webhook_server(on_completion=on_completion, host="127.0.0.1", port=5000)

    body = b'{"metadata": {"run_id": 0}, "status": "completed"}'
    resp = app.test_client().post(
        "/webhook",
        data=body,
        content_type="application/json",
        headers={"X-Webhook-Signature": _signature(secret, body)},
    )

    assert resp.status_code == 400
    assert "job id" in resp.get_json()["error"].lower()
    on_completion.assert_not_called()
