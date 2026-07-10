"""Regression tests for the web background poller startup hook."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("flask")

import deepr.web.app as web_app
from deepr.web.research_cost_api import WebResearchCostCoordinator


@pytest.fixture
def client(monkeypatch):
    web_app.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    if web_app.limiter is not None:
        monkeypatch.setattr(web_app.limiter, "enabled", False)
    return web_app.app.test_client()


def test_web_import_does_not_construct_metered_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(web_app, "provider", None)

    with pytest.raises(RuntimeError, match="OpenAI is not configured"):
        web_app._default_openai_provider()


def test_socketio_accepts_same_origin_on_custom_local_port(client):
    response = client.get(
        "/socket.io/?EIO=4&transport=polling",
        headers={"Host": "127.0.0.1:5071", "Origin": "http://127.0.0.1:5071"},
    )

    assert response.status_code == 200


def test_socketio_rejects_cross_origin_without_explicit_allowlist(client):
    response = client.get(
        "/socket.io/?EIO=4&transport=polling",
        headers={"Host": "127.0.0.1:5071", "Origin": "https://attacker.example"},
    )

    assert response.status_code == 400


def test_testing_mode_does_not_start_background_poller(monkeypatch):
    monkeypatch.setitem(web_app.app.config, "TESTING", True)
    monkeypatch.setattr(web_app, "_poller_started", False)

    started = []

    class DummyThread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            started.append(self.kwargs)

    monkeypatch.setattr(web_app.threading, "Thread", DummyThread)

    web_app._start_poller()

    assert web_app._poller_started is False
    assert started == []


def test_paid_submit_fails_closed_when_cost_controls_are_unavailable(client, monkeypatch):
    provider_factory = MagicMock()
    monkeypatch.setattr(web_app, "research_costs", WebResearchCostCoordinator(None, None))
    monkeypatch.setattr(web_app, "_default_openai_provider", provider_factory)

    response = client.post("/api/jobs", json={"prompt": "Research power-grid constraints."})

    assert response.status_code == 503
    assert response.get_json()["error"] == "Cost controls unavailable; submission denied"
    provider_factory.assert_not_called()


def test_paid_submit_fails_closed_when_cost_estimation_raises(client, monkeypatch):
    provider_factory = MagicMock()
    estimator = MagicMock()
    estimator.estimate_cost.side_effect = RuntimeError("estimator unavailable")
    monkeypatch.setattr(web_app, "research_costs", WebResearchCostCoordinator(MagicMock(), estimator))
    monkeypatch.setattr(web_app, "_default_openai_provider", provider_factory)

    response = client.post("/api/jobs", json={"prompt": "Research power-grid constraints."})

    assert response.status_code == 503
    assert response.get_json()["error"] == "Cost estimation unavailable; submission denied"
    provider_factory.assert_not_called()


def test_paid_submit_fails_closed_when_cost_limit_check_raises(client, monkeypatch):
    provider_factory = MagicMock()
    estimate = MagicMock(min_cost=0.1, max_cost=0.3, expected_cost=0.2)
    estimator = MagicMock()
    estimator.estimate_cost.return_value = estimate
    controller = MagicMock()
    controller.check_cost_limit.side_effect = RuntimeError("ledger unavailable")
    monkeypatch.setattr(web_app, "research_costs", WebResearchCostCoordinator(controller, estimator))
    monkeypatch.setattr(web_app, "_default_openai_provider", provider_factory)

    response = client.post("/api/jobs", json={"prompt": "Research power-grid constraints."})

    assert response.status_code == 503
    assert response.get_json()["error"] == "Cost limit check unavailable; submission denied"
    provider_factory.assert_not_called()


def test_paid_submit_does_not_expose_cost_reservation_exception(client, monkeypatch):
    from deepr.experts.research_cost_gate import ResearchCostBlocked

    provider_factory = MagicMock()
    estimate = MagicMock(min_cost=0.1, max_cost=0.3, expected_cost=0.2)
    estimator = MagicMock()
    estimator.estimate_cost.return_value = estimate
    controller = MagicMock(max_cost_per_job=1.0, max_daily_cost=5.0, max_monthly_cost=20.0)
    controller.check_cost_limit.return_value = (True, None)
    coordinator = WebResearchCostCoordinator(controller, estimator)
    monkeypatch.setattr(web_app, "research_costs", coordinator)
    monkeypatch.setattr(web_app, "_default_openai_provider", provider_factory)
    monkeypatch.setattr(
        "deepr.web.research_cost_api.reserve_research_cost",
        MagicMock(side_effect=ResearchCostBlocked("secret ledger traceback")),
    )

    response = client.post("/api/jobs", json={"prompt": "Research power-grid constraints."})

    assert response.status_code == 429
    assert response.get_json()["error"] == "Research cost limit exceeded"
    assert b"secret ledger traceback" not in response.data
    provider_factory.assert_not_called()


def test_paid_submit_does_not_expose_provider_configuration_exception(client, monkeypatch):
    reservation = MagicMock()
    coordinator = MagicMock()
    coordinator.reserve.return_value = (
        {"min_cost": 0.1, "max_cost": 0.3, "expected_cost": 0.2},
        reservation,
        None,
    )
    provider_factory = MagicMock(side_effect=RuntimeError("secret provider traceback"))
    monkeypatch.setattr(web_app, "research_costs", coordinator)
    monkeypatch.setattr(web_app, "_default_openai_provider", provider_factory)

    response = client.post("/api/jobs", json={"prompt": "Research power-grid constraints."})

    assert response.status_code == 503
    assert response.get_json() == {"error": "Research provider is unavailable"}
    assert b"secret provider traceback" not in response.data
    coordinator.refund.assert_called_once_with(reservation)


def test_paid_submit_preserves_explicit_no_key_error(client, monkeypatch):
    reservation = MagicMock()
    coordinator = MagicMock()
    coordinator.reserve.return_value = (
        {"min_cost": 0.1, "max_cost": 0.3, "expected_cost": 0.2},
        reservation,
        None,
    )
    monkeypatch.setattr(web_app, "research_costs", coordinator)
    monkeypatch.setattr(web_app, "provider", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.post("/api/jobs", json={"prompt": "Research power-grid constraints."})

    assert response.status_code == 503
    assert response.get_json() == {"error": web_app.research_cost_api.OPENAI_NOT_CONFIGURED}
    coordinator.refund.assert_called_once_with(reservation)


@pytest.mark.parametrize(
    "reserved_key",
    [
        "cleanup_vector_store",
        "cost_reservation_estimated_usd",
        "cost_reservation_id",
        "cost_reservation_model",
        "cost_reservation_provider",
        "provider_file_ids",
        "uploaded_files",
        "vector_store_id",
    ],
)
def test_paid_submit_rejects_provider_lifecycle_metadata_before_reservation(client, monkeypatch, reserved_key):
    coordinator = MagicMock()
    monkeypatch.setattr(web_app, "research_costs", coordinator)

    response = client.post(
        "/api/jobs",
        json={"prompt": "Research power-grid constraints.", "metadata": {reserved_key: "client-selected"}},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "metadata contains reserved fields"}
    coordinator.reserve.assert_not_called()


@pytest.mark.parametrize(
    "reserved_key",
    [
        "cleanup_vector_store",
        "cost_reservation_estimated_usd",
        "cost_reservation_id",
        "cost_reservation_model",
        "cost_reservation_provider",
        "provider_file_ids",
        "uploaded_files",
        "vector_store_id",
    ],
)
def test_batch_submit_rejects_reserved_metadata_before_enqueue(client, monkeypatch, reserved_key):
    queue = MagicMock()
    queue.enqueue = AsyncMock(return_value=True)
    monkeypatch.setattr(web_app, "queue", queue)

    response = client.post(
        "/api/jobs/batch",
        json={
            "jobs": [
                {"prompt": "Safe item", "metadata": {"campaign": "launch"}},
                {"prompt": "Unsafe item", "metadata": {reserved_key: "client-selected"}},
            ]
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "metadata contains reserved fields"}
    queue.enqueue.assert_not_awaited()


def test_web_job_responses_redact_provider_lifecycle_metadata(client, monkeypatch):
    from deepr.queue.base import JobStatus, ResearchJob

    job = ResearchJob(
        id="job-1",
        prompt="Research power-grid constraints.",
        status=JobStatus.PROCESSING,
        metadata={
            "campaign": "launch",
            "provider_file_ids": ["file-private"],
            "vector_store_id": "vs-private",
        },
    )
    queue = MagicMock()
    queue.list_jobs = AsyncMock(return_value=[job])
    queue.get_job = AsyncMock(return_value=job)
    monkeypatch.setattr(web_app, "queue", queue)

    listing = client.get("/api/jobs")
    detail = client.get("/api/jobs/job-1")

    assert listing.status_code == 200
    assert listing.get_json()["jobs"][0]["metadata"] == {"campaign": "launch"}
    assert detail.status_code == 200
    assert detail.get_json()["job"]["metadata"] == {"campaign": "launch"}


def test_web_cancel_returns_not_found_for_missing_job(client, monkeypatch):
    queue = MagicMock()
    queue.get_job = AsyncMock(return_value=None)
    monkeypatch.setattr(web_app, "queue", queue)

    response = client.post("/api/jobs/missing/cancel")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Job not found"}


def test_web_cancel_returns_retryable_failure_when_unconfirmed(client, monkeypatch):
    from deepr.queue.base import ResearchJob

    queue = MagicMock()
    queue.get_job = AsyncMock(return_value=ResearchJob(id="job-1", prompt="Research cancellation"))
    monkeypatch.setattr(web_app, "queue", queue)
    monkeypatch.setattr(web_app, "_cancel_job_with_cost_safety", MagicMock(return_value=False))

    response = client.post("/api/jobs/job-1/cancel")

    assert response.status_code == 503
    assert response.get_json() == {"error": "Job cancellation could not be confirmed"}


def test_web_cancel_returns_success_only_after_confirmation(client, monkeypatch):
    from deepr.queue.base import ResearchJob

    queue = MagicMock()
    queue.get_job = AsyncMock(return_value=ResearchJob(id="job-1", prompt="Research cancellation"))
    monkeypatch.setattr(web_app, "queue", queue)
    monkeypatch.setattr(web_app, "_cancel_job_with_cost_safety", MagicMock(return_value=True))

    response = client.post("/api/jobs/job-1/cancel")

    assert response.status_code == 200
    assert response.get_json() == {"success": True}


def test_web_cancel_preserves_completed_terminal_history(client, monkeypatch):
    from deepr.queue.base import JobStatus, ResearchJob

    queue = MagicMock()
    queue.get_job = AsyncMock(return_value=ResearchJob(id="job-1", prompt="done", status=JobStatus.COMPLETED))
    monkeypatch.setattr(web_app, "queue", queue)

    response = client.post("/api/jobs/job-1/cancel")

    assert response.status_code == 409
    assert response.get_json() == {"error": "Terminal job state cannot be cancelled"}


def test_web_cancel_uses_provider_recorded_on_job(monkeypatch):
    from deepr.queue.base import JobStatus, ResearchJob

    job = ResearchJob(
        id="job-1",
        prompt="owned",
        provider="gemini",
        provider_job_id="gemini-job",
        status=JobStatus.PROCESSING,
    )
    owned_provider = MagicMock()
    create = MagicMock(return_value=owned_provider)
    monkeypatch.setattr(web_app, "create_job_provider", create)

    async def cancel_job(*, queue, job, provider_factory):
        assert provider_factory() is owned_provider
        return True

    monkeypatch.setattr(web_app, "research_costs", MagicMock(cancel_job=cancel_job))

    assert web_app._cancel_job_with_cost_safety(job) is True
    create.assert_called_once_with(job, web_app._cfg)


def test_web_poller_treats_incomplete_as_content_free_terminal_failure(monkeypatch):
    job = MagicMock(id="job-1", provider_job_id="provider-job-1")
    provider = MagicMock()
    provider.get_status = AsyncMock(return_value=SimpleNamespace(status="incomplete", error="secret\nforged"))
    failure = MagicMock()
    monkeypatch.setattr(web_app, "_default_openai_provider", MagicMock(return_value=provider))
    monkeypatch.setattr(web_app, "_handle_failure", failure)
    loop = asyncio.new_event_loop()
    try:
        web_app._check_job(loop, job)
    finally:
        loop.close()

    failure.assert_called_once_with(loop, job, "Provider returned an incomplete research result")


def test_web_poller_persists_provider_cancellation_as_cancelled(monkeypatch):
    from deepr.queue.base import JobStatus

    job = MagicMock(id="job-1", provider_job_id="provider-job-1")
    provider = MagicMock(get_status=AsyncMock(return_value=SimpleNamespace(status="cancelled")))
    failure = MagicMock()
    monkeypatch.setattr(web_app, "_default_openai_provider", MagicMock(return_value=provider))
    monkeypatch.setattr(web_app, "_handle_failure", failure)
    loop = asyncio.new_event_loop()
    try:
        web_app._check_job(loop, job)
    finally:
        loop.close()

    failure.assert_called_once_with(
        loop,
        job,
        "Provider reported research cancellation",
        status=JobStatus.CANCELLED,
    )


def test_web_poller_keeps_unknown_provider_status_active(monkeypatch, caplog):
    job = MagicMock(id="job-1", provider_job_id="provider-job-1", started_at=None)
    provider = MagicMock(get_status=AsyncMock(return_value=SimpleNamespace(status="new\nforged")))
    failure = MagicMock()
    monkeypatch.setattr(web_app, "_default_openai_provider", MagicMock(return_value=provider))
    monkeypatch.setattr(web_app, "_handle_failure", failure)
    loop = asyncio.new_event_loop()
    try:
        web_app._check_job(loop, job)
    finally:
        loop.close()

    failure.assert_not_called()
    assert "unsupported provider status" in caplog.text
    assert "forged" not in caplog.text


def test_web_failure_handler_retains_active_state_when_cost_closure_fails(monkeypatch):
    from deepr.queue.base import JobStatus

    job = MagicMock(id="job-1")
    coordinator = MagicMock()
    coordinator.fail_job.side_effect = RuntimeError("ledger unavailable")
    queue = MagicMock(update_status=AsyncMock())
    monkeypatch.setattr(web_app, "research_costs", coordinator)
    monkeypatch.setattr(web_app, "queue", queue)
    loop = asyncio.new_event_loop()
    try:
        web_app._handle_failure(
            loop,
            job,
            "Provider reported research cancellation",
            status=JobStatus.CANCELLED,
        )
    finally:
        loop.close()

    queue.update_status.assert_not_awaited()


def test_web_poller_logs_exception_type_without_content(monkeypatch, caplog):
    job = MagicMock(id="job-1", provider_job_id="provider-job-1", started_at=None)
    provider = MagicMock()
    provider.get_status = AsyncMock(side_effect=RuntimeError("secret\nforged"))
    monkeypatch.setattr(web_app, "_default_openai_provider", MagicMock(return_value=provider))
    loop = asyncio.new_event_loop()
    try:
        web_app._check_job(loop, job)
    finally:
        loop.close()

    assert "RuntimeError" in caplog.text
    assert "secret" not in caplog.text
