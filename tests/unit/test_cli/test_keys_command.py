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
    for name in ("OPENAI_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path / ".env"


def test_list_reports_missing_keys(env_file: Path) -> None:
    result = CliRunner().invoke(keys_module.keys, ["list", "--json"])
    payload = json.loads(result.output)
    assert result.exit_code == 0
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


def test_check_validates_present_keys(env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file.write_text("XAI_API_KEY=xai-fresh-key-0001\n", encoding="utf-8")
    monkeypatch.setattr(
        keys_module,
        "_validate",
        lambda p, k: {"status": "valid", "models_visible": 7} if p == "xai" else {"status": "no_key"},
    )
    result = CliRunner().invoke(keys_module.keys, ["check", "--provider", "xai", "--json"])
    payload = json.loads(result.output)
    assert payload["results"] == [
        {"provider": "xai", "env_var": "XAI_API_KEY", "shadowed": False, "status": "valid", "models_visible": 7}
    ]
