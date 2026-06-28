"""Tests for A2A host validation contracts."""

from __future__ import annotations

from deepr.a2a.constants import A2A_AGENT_CARD_PATH, CONSULT_SKILL_NAME
from deepr.a2a.validation import (
    build_offline_a2a_host_fixture,
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
