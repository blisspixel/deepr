"""Tests for `deepr keys` - provider credential visibility without exposure.

Each behavior tested here corresponds to a real failure hit in live operation:
shadowed keys (exported variable wins over .env), misspelled variable names
nothing reads, empty values that look set, and invalid keys that surface
downstream as misleading provider errors.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from deepr.cli.commands import keys as keys_module


@pytest.fixture
def env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("deepr.config.default_data_dir", lambda: tmp_path / "user-deepr")
    from deepr.security.key_quarantine import QUARANTINE_PREFIX

    for name in (
        "OPENAI_API_KEY",
        "XAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(QUARANTINE_PREFIX + name, raising=False)
    return tmp_path / ".env"


def test_list_reports_missing_keys(env_file: Path) -> None:
    result = CliRunner().invoke(keys_module.keys, ["list", "--json"])
    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert {entry["provider"] for entry in payload["keys"]} >= {
        "openai",
        "xai",
        "anthropic",
        "gemini",
        "openrouter",
    }
    assert all(not entry["present"] for entry in payload["keys"])


def test_list_never_prints_key_values(env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "xai-supersecretvalue1234567890"
    env_file.write_text(f"XAI_API_KEY={secret}\n", encoding="utf-8")
    result = CliRunner().invoke(keys_module.keys, ["list", "--json"])
    assert secret not in result.output
    payload = json.loads(result.output)
    xai = next(e for e in payload["keys"] if e["provider"] == "xai")
    assert xai["present"] and xai["in_env_file"] and not xai["shadowed"]


def test_list_detects_shadowing(env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file.write_text("XAI_API_KEY=xai-fresh-key-from-file-0001\n", encoding="utf-8")
    monkeypatch.setenv("XAI_API_KEY", "xai-stale-exported-key-9999")
    result = CliRunner().invoke(keys_module.keys, ["list", "--json"])
    payload = json.loads(result.output)
    xai = next(e for e in payload["keys"] if e["provider"] == "xai")
    # The exported value wins (dotenv does not override), and that must be surfaced.
    assert xai["shadowed"] is True


def test_list_flags_misspelled_key_names(env_file: Path) -> None:
    env_file.write_text("ANTRHOPIC_API_KEY=sk-a-something\n", encoding="utf-8")
    result = CliRunner().invoke(keys_module.keys, ["list", "--json"])
    payload = json.loads(result.output)
    assert payload["suspect_names"] == [{"found": "ANTRHOPIC_API_KEY", "expected": "ANTHROPIC_API_KEY"}]


def test_check_reports_no_key_without_network(env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(keys_module, "_validate", lambda p, k: calls.append(p) or {"status": "valid"})
    result = CliRunner().invoke(keys_module.keys, ["check", "--json"])
    payload = json.loads(result.output)
    assert all(r["status"] == "no_key" for r in payload["results"])
    assert calls == []  # nothing to validate, nothing pinged


def test_set_openrouter_writes_user_env_when_cwd_has_none(env_file: Path, tmp_path: Path) -> None:
    secret = "sk-or-v1-" + "b" * 64
    result = CliRunner().invoke(
        keys_module.keys,
        ["set", "openrouter"],
        input=f"{secret}\n{secret}\n",
    )
    assert result.exit_code == 0, result.output
    assert secret not in result.output
    stored = (tmp_path / "user-deepr" / ".env").read_text(encoding="utf-8")
    assert f"OPENROUTER_API_KEY={secret}" in stored
    assert not env_file.exists()
    assert "value not shown" in result.output


def test_set_prefers_existing_checkout_env(env_file: Path) -> None:
    env_file.write_text("XAI_API_KEY=keep-me\n", encoding="utf-8")
    secret = "sk-or-v1-" + "e" * 64
    result = CliRunner().invoke(
        keys_module.keys,
        ["set", "openrouter"],
        input=f"{secret}\n{secret}\n",
    )
    assert result.exit_code == 0, result.output
    stored = env_file.read_text(encoding="utf-8")
    assert "XAI_API_KEY=keep-me" in stored
    assert f"OPENROUTER_API_KEY={secret}" in stored


def test_set_refuses_empty_keys(env_file: Path) -> None:
    result = CliRunner().invoke(keys_module.keys, ["set", "openrouter"], input="\n\n")
    assert result.exit_code != 0
    assert not env_file.exists() or "OPENROUTER_API_KEY=" not in env_file.read_text(encoding="utf-8")


def test_check_openrouter_uses_key_metadata_without_printing_the_secret(
    env_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sk-or-v1-" + "c" * 64
    env_file.write_text(f"OPENROUTER_API_KEY={secret}\n", encoding="utf-8")
    captured: list[tuple[str, float]] = []

    class _Observation:
        control_eligible = True
        failures: tuple[str, ...] = ()
        limit_usd = 20.0
        limit_remaining_usd = 20.0
        limit_reset = None
        required_headroom_usd = 0.01

    def inspect(api_key: str, *, required_headroom_usd: float) -> _Observation:
        captured.append((api_key, required_headroom_usd))
        return _Observation()

    monkeypatch.setattr("deepr.providers.openrouter_key_controls.inspect_openrouter_key", inspect)
    result = CliRunner().invoke(keys_module.keys, ["check", "--provider", "openrouter", "--json"])
    payload = json.loads(result.output)
    assert result.exit_code == 0, result.output
    assert captured == [(secret, 0.01)]
    assert secret not in result.output
    assert payload["results"][0]["provider"] == "openrouter"
    assert payload["results"][0]["status"] == "valid"
    assert payload["results"][0]["limit_usd"] == 20.0
    assert payload["results"][0]["limit_remaining_usd"] == 20.0


def test_check_openrouter_reports_ineligible_key_limit_above_ceiling(
    env_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sk-or-v1-" + "d" * 64
    env_file.write_text(f"OPENROUTER_API_KEY={secret}\n", encoding="utf-8")

    class _Observation:
        control_eligible = False
        failures = ("current key limit $20.000000 exceeds Deepr maximum $5.000000",)
        limit_usd = 20.0
        limit_remaining_usd = 20.0
        limit_reset = None
        required_headroom_usd = 0.01

    def inspect(api_key: str, *, required_headroom_usd: float) -> _Observation:
        del api_key, required_headroom_usd
        return _Observation()

    monkeypatch.setattr("deepr.providers.openrouter_key_controls.inspect_openrouter_key", inspect)
    result = CliRunner().invoke(keys_module.keys, ["check", "--provider", "openrouter"])
    assert result.exit_code == 0, result.output
    assert secret not in result.output
    assert "ineligible" in result.output
    assert "exceeds Deepr maximum" in result.output
    assert "deepr budget set 20" in result.output.lower()


def test_check_invalid_openrouter_key_shows_provider_http_status(
    env_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sk-or-v1-" + "f" * 64
    env_file.write_text(f"OPENROUTER_API_KEY={secret}\n", encoding="utf-8")
    from deepr.providers.openrouter_key_controls import OpenRouterKeyControlError

    def inspect(api_key: str, *, required_headroom_usd: float):
        del api_key, required_headroom_usd
        raise OpenRouterKeyControlError("OpenRouter current-key endpoint returned HTTP 401")

    monkeypatch.setattr("deepr.providers.openrouter_key_controls.inspect_openrouter_key", inspect)
    result = CliRunner().invoke(keys_module.keys, ["check", "--provider", "openrouter"])
    assert result.exit_code == 0, result.output
    assert secret not in result.output
    assert "HTTP 401" in result.output


def test_check_reads_quarantined_openrouter_key(env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from deepr.security.key_quarantine import QUARANTINE_PREFIX

    secret = "sk-or-v1-" + "e" * 64
    monkeypatch.setenv(QUARANTINE_PREFIX + "OPENROUTER_API_KEY", secret)

    class _Observation:
        control_eligible = True
        failures: tuple[str, ...] = ()
        limit_usd = 20.0
        limit_remaining_usd = 19.0
        limit_reset = None
        required_headroom_usd = 0.01

    def inspect(api_key: str, *, required_headroom_usd: float) -> _Observation:
        assert api_key == secret
        del required_headroom_usd
        return _Observation()

    monkeypatch.setattr("deepr.providers.openrouter_key_controls.inspect_openrouter_key", inspect)
    result = CliRunner().invoke(keys_module.keys, ["check", "--provider", "openrouter", "--json"])
    payload = json.loads(result.output)
    assert result.exit_code == 0, result.output
    assert payload["results"][0]["status"] == "valid"
    assert secret not in result.output


def test_check_blocks_present_keys_before_network(env_file: Path) -> None:
    env_file.write_text("XAI_API_KEY=xai-fresh-key-0001\n", encoding="utf-8")  # gitleaks:allow (fake fixture)
    result = CliRunner().invoke(keys_module.keys, ["check", "--provider", "xai", "--json"])
    payload = json.loads(result.output)
    assert payload["results"] == [
        {
            "provider": "xai",
            "env_var": "XAI_API_KEY",
            "shadowed": False,
            "status": "blocked",
            "reason": "external_metadata_cost_unverified",
        }
    ]
