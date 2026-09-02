"""CLI coverage for authenticated, no-inference OpenRouter key checks."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from click.testing import CliRunner

from deepr.cli.commands.providers import providers
from deepr.providers.openrouter_key_controls import (
    OpenRouterKeyControlError,
    OpenRouterKeyControlObservation,
)
from deepr.security.key_quarantine import QUARANTINE_PREFIX

_API_KEY = "sk-or-v1-" + "a" * 64


def _observation(*, eligible: bool = True) -> OpenRouterKeyControlObservation:
    return OpenRouterKeyControlObservation(
        control_eligible=eligible,
        failures=() if eligible else ("remaining headroom is too small",),
        account_ref_sha256="a" * 64,
        key_label_sha256="b" * 64,
        credential_fingerprint="scrypt:" + "c" * 64,
        required_headroom_usd=4.0,
        maximum_monthly_limit_usd=5.0,
        limit_usd=5.0,
        limit_remaining_usd=4.0,
        usage_usd=0.8,
        usage_monthly_usd=0.8,
        byok_usage_usd=0.2,
        byok_usage_monthly_usd=0.2,
        limit_reset="monthly",
        include_byok_in_limit=True,
        expires_at="2026-10-01T00:00:00+00:00",
        observed_at="2026-09-01T12:00:00+00:00",
        source_sha256="d" * 64,
    )


def test_key_check_reads_hidden_prompt_not_environment_or_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, float]] = []

    def inspect(api_key: str, *, required_headroom_usd: float) -> OpenRouterKeyControlObservation:
        captured.append((api_key, required_headroom_usd))
        return _observation()

    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-be-read")
    monkeypatch.setattr("deepr.cli.commands.openrouter_key.inspect_openrouter_key", inspect)
    result = CliRunner().invoke(
        providers,
        ["openrouter-key-check", "--required-headroom", "4", "--json"],
        input=_API_KEY + "\n",
    )
    assert result.exit_code == 0, result.output
    assert captured == [(_API_KEY, 4.0)]
    payload = json.loads(result.stdout)
    assert payload["control_eligible"] is True
    assert payload["required_headroom_usd"] == 4.0
    assert payload["maximum_monthly_limit_usd"] == 5.0
    assert payload["api_key_source"] == "hidden_prompt"
    assert payload["inference_requests"] == 0
    assert payload["paid_requests"] == 0
    assert payload["billing_reconciliation_complete"] is False
    assert payload["dispatch_authorized"] is False
    assert _API_KEY not in result.output
    assert "must-not-be-read" not in result.output


def test_key_check_can_explicitly_read_only_the_quarantined_environment_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []
    monkeypatch.setenv("OPENROUTER_API_KEY", "live-key-must-not-be-read")
    monkeypatch.setenv(QUARANTINE_PREFIX + "OPENROUTER_API_KEY", _API_KEY)
    monkeypatch.setattr(
        "deepr.cli.commands.openrouter_key.inspect_openrouter_key",
        lambda api_key, required_headroom_usd: captured.append(api_key) or _observation(),
    )

    result = CliRunner().invoke(providers, ["openrouter-key-check", "--from-env", "--json"])

    assert result.exit_code == 0, result.output
    assert captured == [_API_KEY]
    payload = json.loads(result.stdout)
    assert payload["api_key_source"] == "quarantined_environment"
    assert _API_KEY not in result.output
    assert "live-key-must-not-be-read" not in result.output


def test_key_check_from_env_fails_closed_when_quarantined_key_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(QUARANTINE_PREFIX + "OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(providers, ["openrouter-key-check", "--from-env"])

    assert result.exit_code == 1
    assert "No OPENROUTER_API_KEY" in result.output


def test_key_check_can_read_checkout_local_env_without_exporting_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: list[str] = []
    monkeypatch.delenv(QUARANTINE_PREFIX + "OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(f"OPENROUTER_API_KEY={_API_KEY}\n", encoding="ascii")
    monkeypatch.setattr(
        "deepr.cli.commands.openrouter_key.inspect_openrouter_key",
        lambda api_key, required_headroom_usd: captured.append(api_key) or _observation(),
    )

    result = CliRunner().invoke(providers, ["openrouter-key-check", "--from-env", "--json"])

    assert result.exit_code == 0, result.output
    assert captured == [_API_KEY]
    assert "OPENROUTER_API_KEY" not in os.environ
    payload = json.loads(result.stdout)
    assert payload["api_key_source"] == "checkout_local_env"


def test_key_check_text_keeps_dispatch_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deepr.cli.commands.openrouter_key.inspect_openrouter_key",
        lambda api_key, required_headroom_usd: _observation(),
    )
    result = CliRunner().invoke(providers, ["openrouter-key-check"], input=_API_KEY + "\n")
    assert result.exit_code == 0, result.output
    assert "Control eligible: true" in result.output
    assert "0 inference requests" in result.output
    assert "$0.00" in result.output
    assert "dispatch remains blocked" in result.output


def test_key_check_returns_nonzero_for_ineligible_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deepr.cli.commands.openrouter_key.inspect_openrouter_key",
        lambda api_key, required_headroom_usd: _observation(eligible=False),
    )
    result = CliRunner().invoke(providers, ["openrouter-key-check", "--json"], input=_API_KEY + "\n")
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["control_eligible"] is False
    assert payload["failures"] == ["remaining headroom is too small"]
    assert payload["dispatch_authorized"] is False


def test_key_check_does_not_render_an_absent_limit_as_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    observation = replace(
        _observation(eligible=False),
        limit_usd=None,
        limit_remaining_usd=None,
        limit_reset=None,
    )
    monkeypatch.setattr(
        "deepr.cli.commands.openrouter_key.inspect_openrouter_key",
        lambda api_key, required_headroom_usd: observation,
    )

    result = CliRunner().invoke(providers, ["openrouter-key-check"], input=_API_KEY + "\n")

    assert result.exit_code == 1
    assert "Monthly key limit: not set" in result.output
    assert "Remaining key limit: not set" in result.output
    assert "Monthly key limit: $0.00" not in result.output


def test_key_check_reports_transport_error_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(api_key: str, *, required_headroom_usd: float) -> OpenRouterKeyControlObservation:
        raise OpenRouterKeyControlError("current-key observation unavailable")

    monkeypatch.setattr("deepr.cli.commands.openrouter_key.inspect_openrouter_key", fail)
    result = CliRunner().invoke(providers, ["openrouter-key-check"], input=_API_KEY + "\n")
    assert result.exit_code == 1
    assert "current-key observation unavailable" in result.output
    assert _API_KEY not in result.output
    assert "Traceback" not in result.output
