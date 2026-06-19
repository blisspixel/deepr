"""Tests for `deepr mcp keys` scoped-key management."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.commands.mcp import mcp


def test_mcp_keys_create_outputs_secret_once_and_stores_hash(tmp_path):
    keys_path = tmp_path / "keys.json"
    result = CliRunner().invoke(
        mcp,
        [
            "keys",
            "create",
            "--key-id",
            "agent-alpha",
            "--mode",
            "standard",
            "--expert",
            "alpha",
            "--budget",
            "3.50",
            "--rate-limit",
            "12",
            "--keys-path",
            str(keys_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["key_id"] == "agent-alpha"
    assert payload["mode"] == "standard"
    assert payload["expert_allowlist"] == ["alpha"]
    assert payload["budget_limit_usd"] == 3.5
    assert payload["rate_limit_per_minute"] == 12
    assert payload["secret"].startswith("deepr_mcp_")
    assert "secret_hash" not in payload
    assert payload["secret"] not in keys_path.read_text(encoding="utf-8")


def test_mcp_keys_list_never_reveals_secret(tmp_path):
    keys_path = tmp_path / "keys.json"
    create = CliRunner().invoke(mcp, ["keys", "create", "--key-id", "agent", "--keys-path", str(keys_path), "--json"])
    secret = json.loads(create.output)["secret"]

    result = CliRunner().invoke(mcp, ["keys", "list", "--keys-path", str(keys_path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["key_id"] == "agent"
    assert "secret" not in payload[0]
    assert "secret_hash" not in payload[0]
    assert secret not in result.output


def test_mcp_keys_revoke_disables_key(tmp_path):
    keys_path = tmp_path / "keys.json"
    CliRunner().invoke(mcp, ["keys", "create", "--key-id", "agent", "--keys-path", str(keys_path)])

    revoke = CliRunner().invoke(mcp, ["keys", "revoke", "agent", "--keys-path", str(keys_path), "--json"])
    listed = CliRunner().invoke(mcp, ["keys", "list", "--keys-path", str(keys_path), "--json"])

    assert revoke.exit_code == 0, revoke.output
    assert json.loads(revoke.output) == {"key_id": "agent", "revoked": True}
    assert json.loads(listed.output)[0]["revoked"] is True


def test_mcp_keys_revoke_missing_key_exits_nonzero(tmp_path):
    result = CliRunner().invoke(mcp, ["keys", "revoke", "missing", "--keys-path", str(tmp_path / "keys.json")])

    assert result.exit_code != 0
    assert "not found" in result.output


def test_mcp_keys_duplicate_key_id_exits_nonzero(tmp_path):
    keys_path = tmp_path / "keys.json"
    runner = CliRunner()

    first = runner.invoke(mcp, ["keys", "create", "--key-id", "agent", "--keys-path", str(keys_path)])
    second = runner.invoke(mcp, ["keys", "create", "--key-id", "agent", "--keys-path", str(keys_path)])

    assert first.exit_code == 0, first.output
    assert second.exit_code != 0
    assert "already exists" in second.output
