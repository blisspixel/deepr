"""Tests for `deepr mcp agent-guide`."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from deepr.cli.commands.mcp import mcp


def test_mcp_agent_guide_creates_scoped_zero_budget_key(tmp_path):
    keys_path = tmp_path / "keys.json"
    guide_path = tmp_path / "agent-guide.md"
    result = CliRunner().invoke(
        mcp,
        [
            "agent-guide",
            "--endpoint",
            "http://10.0.0.5:8765/mcp",
            "--key-id",
            "agent-trial",
            "--keys-path",
            str(keys_path),
            "--output",
            str(guide_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote redacted MCP agent guide" in result.output
    assert "Token: deepr_mcp_" in result.output
    guide = guide_path.read_text(encoding="utf-8")
    assert "deepr_mcp_" not in guide
    assert "<redacted-token>" in guide
    assert "deepr_consult_experts" in guide
    assert "capacity.live_metered_fallback=false" in guide
    assert "cost_usd=0" in guide
    assert "one expert for focused advice or multiple experts for council guidance" in guide
    assert "Preserve expert disagreement and uncertainty" in guide
    assert "deepr_mcp_" not in keys_path.read_text(encoding="utf-8")


def test_mcp_agent_guide_refuses_json_key_creation_even_with_output(tmp_path):
    keys_path = tmp_path / "keys.json"
    guide_path = tmp_path / "agent-guide.md"
    result = CliRunner().invoke(
        mcp,
        [
            "agent-guide",
            "--key-id",
            "agent-trial",
            "--keys-path",
            str(keys_path),
            "--output",
            str(guide_path),
            "--json",
        ],
    )

    assert result.exit_code != 0
    assert "JSON output redacts bearer tokens" in result.output
    assert not keys_path.exists()
    assert not guide_path.exists()


def test_mcp_agent_guide_json_redacts_existing_token():
    result = CliRunner().invoke(
        mcp,
        [
            "agent-guide",
            "--endpoint",
            "http://10.0.0.5:8765/mcp",
            "--auth-token",
            "existing-secret",
            "--no-create-key",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-mcp-agent-guide-v1"
    assert payload["endpoint"] == "http://10.0.0.5:8765/mcp"
    assert payload["key_id"] is None
    assert payload["mode"] == "standard"
    assert payload["budget_limit_usd"] == 0.0
    assert payload["rate_limit_per_minute"] == 30
    assert payload["token_included"] is False
    assert "existing-secret" not in result.output
    assert "<redacted-token>" in payload["guide"]


def test_mcp_agent_guide_can_write_existing_token_guide(tmp_path):
    guide_path = tmp_path / "agent-guide.md"
    keys_path = tmp_path / "keys.json"
    result = CliRunner().invoke(
        mcp,
        [
            "agent-guide",
            "--endpoint",
            "http://10.0.0.5:8765/mcp",
            "--auth-token",
            "existing-secret",
            "--no-create-key",
            "--keys-path",
            str(keys_path),
            "--expert",
            "AI Agent Harnesses",
            "--output",
            str(guide_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote redacted MCP agent guide" in result.output
    assert "existing-secret" in result.output
    text = guide_path.read_text(encoding="utf-8")
    assert "existing-secret" not in text
    assert "<redacted-token>" in text
    assert "Use only these experts: AI Agent Harnesses." in text
    assert "deepr_list_experts" not in text
    assert not keys_path.exists()


def test_mcp_agent_guide_rejects_git_trackable_output_before_key_creation():
    if shutil.which("git") is None:
        pytest.skip("git is required for git-trackable output validation")

    runner = CliRunner()
    with runner.isolated_filesystem():
        subprocess.run(["git", "init"], check=True, capture_output=True, text=True)
        result = runner.invoke(
            mcp,
            [
                "agent-guide",
                "--key-id",
                "agent-trial",
                "--output",
                "docs/agent-guide.md",
            ],
        )

        assert result.exit_code != 0
        assert "tracked or unignored git path" in result.output
        assert not Path("docs/agent-guide.md").exists()
        assert not Path("data/security/mcp_keys.json").exists()


def test_mcp_agent_guide_allows_git_ignored_output():
    if shutil.which("git") is None:
        pytest.skip("git is required for git-ignored output validation")

    runner = CliRunner()
    with runner.isolated_filesystem():
        subprocess.run(["git", "init"], check=True, capture_output=True, text=True)
        Path(".gitignore").write_text("/data/\n", encoding="utf-8")
        result = runner.invoke(
            mcp,
            [
                "agent-guide",
                "--key-id",
                "agent-trial",
                "--keys-path",
                "data/security/mcp_keys.json",
                "--output",
                "data/security/agent-guide.md",
            ],
        )

        assert result.exit_code == 0, result.output
        assert Path("data/security/agent-guide.md").exists()
        assert Path("data/security/mcp_keys.json").exists()


def test_mcp_agent_guide_requires_token_when_not_creating_key(tmp_path):
    result = CliRunner().invoke(
        mcp,
        [
            "agent-guide",
            "--no-create-key",
            "--keys-path",
            str(tmp_path / "keys.json"),
        ],
    )

    assert result.exit_code != 0
    assert "--no-create-key requires --auth-token" in result.output
