"""Tests for A2A host validation contracts."""

from __future__ import annotations

from typing import Any

import aiohttp
import pytest

from deepr.a2a.constants import A2A_AGENT_CARD_PATH, CONSULT_SKILL_NAME
from deepr.a2a.validation import (
    build_offline_a2a_host_fixture,
    run_http_a2a_host_validation,
    run_offline_a2a_host_validation,
    validate_a2a_host_payload,
)


def _failed_names(checks) -> set[str]:
    return {check.name for check in checks if check.status == "failed"}


def test_offline_a2a_host_validation_passes() -> None:
    report = run_offline_a2a_host_validation(experts=("Math Expert",))
    payload = report.to_dict()

    assert report.ok is True
    assert payload["schema_version"] == "deepr-a2a-host-validation-v1"
    assert payload["mode"] == "offline"
    assert payload["discovery_path"] == A2A_AGENT_CARD_PATH
    assert payload["agent_card_summary"]["has_consult_skill"] is True
    assert payload["task_summary"]["state"] == "completed"
    assert payload["task_summary"]["capacity"]["live_metered_fallback"] is False
    assert payload["contract"]["submits_a2a_task"] is False
    assert payload["contract"]["cost_scope"] == "validation_client_only"


def test_validation_fails_when_consult_skill_is_missing() -> None:
    agent_card, task = build_offline_a2a_host_fixture(experts=("Math Expert",))
    agent_card["skills"] = [skill for skill in agent_card["skills"] if skill["name"] != CONSULT_SKILL_NAME]

    checks = validate_a2a_host_payload(agent_card, task, expected_backend="local")

    assert "consult_skill_discovery" in _failed_names(checks)


def test_validation_fails_when_artifact_link_is_broken() -> None:
    agent_card, task = build_offline_a2a_host_fixture(experts=("Math Expert",))
    task["result"]["artifact_id"] = "missing-artifact"

    checks = validate_a2a_host_payload(agent_card, task, expected_backend="local")

    assert "artifact_linkage" in _failed_names(checks)


@pytest.mark.parametrize("cost", [float("nan"), float("inf"), -0.01, "0"])
def test_validation_rejects_non_finite_negative_or_non_numeric_costs(cost: Any) -> None:
    agent_card, task = build_offline_a2a_host_fixture()
    task["cost"] = cost

    checks = validate_a2a_host_payload(agent_card, task, expected_backend="local")

    assert "no_metered_cost" in _failed_names(checks)


@pytest.mark.parametrize("ceiling", [float("nan"), float("inf"), -0.01, "0"])
def test_validation_rejects_invalid_cost_ceiling(ceiling: Any) -> None:
    agent_card, task = build_offline_a2a_host_fixture()

    checks = validate_a2a_host_payload(
        agent_card,
        task,
        expected_backend="local",
        cost_ceiling_usd=ceiling,
    )

    assert {"cost_ceiling", "no_metered_cost"}.issubset(_failed_names(checks))


def _fail_if_network_client_created(*args: Any, **kwargs: Any) -> None:
    del args, kwargs
    raise AssertionError("network client must not be created")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com",
        "http://localhost:8080",
        "http://127.0.0.1.example.com:8080",
        "http://127.0.0.1:8080/tasks",
        "http://user:secret@127.0.0.1:8080",
        "http://127.0.0.2:8080",
    ],
)
async def test_http_validation_rejects_non_owned_endpoint_before_network(
    endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(aiohttp, "ClientSession", _fail_if_network_client_created)

    report = await run_http_a2a_host_validation(endpoint, auth_token="owned-secret")

    assert report.ok is False
    assert report.error["error_code"] == "INVALID_HTTP_PREFLIGHT"
    assert report.endpoint is None
    assert report.to_dict()["contract"]["task_submission_attempted"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("auth_token", [None, "owned-secret"])
async def test_http_validation_blocks_task_submission_before_network(
    auth_token: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(aiohttp, "ClientSession", _fail_if_network_client_created)

    report = await run_http_a2a_host_validation(
        "http://127.0.0.1:8080",
        auth_token=auth_token,
    )
    contract = report.to_dict()["contract"]

    assert report.ok is False
    assert report.error["error_code"] == "A2A_HTTP_TASK_VALIDATION_BLOCKED"
    assert contract["submits_a2a_task"] is False
    assert contract["task_submission_attempted"] is False
    assert contract["remote_task_cost_status"] == "not_submitted"
    assert contract["remote_task_calls_metered_api"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": 301.0},
        {"poll_attempts": 101},
        {"poll_interval_seconds": float("nan")},
        {"poll_interval_seconds": float("inf")},
        {"poll_interval_seconds": 11.0},
        {"timeout_seconds": 1.0, "poll_attempts": 2, "poll_interval_seconds": 1.0},
    ],
)
async def test_http_validation_rejects_unbounded_waits_before_network(
    kwargs: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(aiohttp, "ClientSession", _fail_if_network_client_created)

    report = await run_http_a2a_host_validation(
        "http://127.0.0.1:8080",
        auth_token="owned-secret",
        **kwargs,
    )

    assert report.ok is False
    assert report.error["error_code"] == "INVALID_HTTP_PREFLIGHT"
    assert report.to_dict()["contract"]["task_submission_attempted"] is False
