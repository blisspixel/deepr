"""Tests for A2A CLI commands."""

from __future__ import annotations

import json
from unittest.mock import patch

from click.testing import CliRunner

from deepr.a2a.validation import A2AHostValidationCheck, A2AHostValidationReport
from deepr.cli.commands.a2a import a2a
from deepr.cli.main import cli


def test_a2a_validate_host_offline_outputs_json() -> None:
    result = CliRunner().invoke(a2a, ["validate-host", "--expert", "Math Expert", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-a2a-host-validation-v1"
    assert payload["mode"] == "offline"
    assert payload["summary"]["ok"] is True
    assert payload["task_summary"]["capacity"]["live_metered_fallback"] is False


def test_root_cli_registers_a2a_group() -> None:
    result = CliRunner().invoke(cli, ["a2a", "validate-host", "--json"])

    assert result.exit_code == 0, result.output
    assert '"schema_version": "deepr-a2a-host-validation-v1"' in result.output


def test_a2a_validate_host_remote_uses_http_runner() -> None:
    report = A2AHostValidationReport(
        mode="http",
        backend="local",
        endpoint="http://127.0.0.1:8080",
        discovery_path="/.well-known/agent-card.json",
        question="q",
        requested_experts=("Math Expert",),
        checks=(A2AHostValidationCheck("agent_card_envelope", "passed", "ok"),),
    )

    def fake_validate(endpoint, **kwargs):
        assert endpoint == "http://127.0.0.1:8080"
        assert kwargs["auth_token"] == "secret"
        assert kwargs["experts"] == ("Math Expert",)
        assert kwargs["backend"] == "local"
        return "validate-coro"

    with (
        patch("deepr.a2a.validation.run_http_a2a_host_validation", new=fake_validate),
        patch("deepr.cli.commands.a2a.run_async_command", return_value=report),
    ):
        result = CliRunner().invoke(
            a2a,
            [
                "validate-host",
                "http://127.0.0.1:8080",
                "--auth-token",
                "secret",
                "--expert",
                "Math Expert",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "A2A host validation: http://127.0.0.1:8080" in result.output
    assert "Discovery path: /.well-known/agent-card.json" in result.output
    assert "[ok] agent_card_envelope: ok" in result.output


def test_a2a_validate_host_requires_explicit_plan() -> None:
    result = CliRunner().invoke(a2a, ["validate-host", "--synthesis-backend", "plan"])

    assert result.exit_code != 0
    assert "--plan is required" in result.output
