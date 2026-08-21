"""Contract tests for deterministic external MCP host references."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
from copy import deepcopy
from pathlib import Path, PurePosixPath
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from jsonschema import Draft202012Validator, ValidationError

import deepr.mcp.host_profile as host_profile_module
from deepr.cli.commands.mcp_host_profile import host_profile
from deepr.mcp.contained_env import build_contained_read_only_env
from deepr.mcp.host_profile import (
    build_host_profile,
    host_profile_sha256,
    read_only_tool_names,
    serialize_host_profile,
    validate_host_profile,
)
from deepr.mcp.runtime_registry import create_runtime_registry
from deepr.mcp.security.tool_allowlist import ResearchMode, ToolAllowlist
from deepr.mcp.server import DeeprMCPServer, _handle_tools_list

ROOT = Path(__file__).parents[3]
SCHEMA_PATH = ROOT / "docs" / "schemas" / "mcp-host-profile-v1.json"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "hosts" / "openclaw" / "v2026.7.1-2" / "profile.json"


def _profile() -> dict:
    return build_host_profile("openclaw")


def test_openclaw_profile_matches_pinned_fixture_and_published_schema() -> None:
    profile = _profile()
    fixture_bytes = FIXTURE_PATH.read_bytes()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(profile)
    assert serialize_host_profile(profile).encode("utf-8") == fixture_bytes
    assert not validate_host_profile(profile)


def test_tool_inventory_is_the_exact_runtime_read_only_surface() -> None:
    registry = create_runtime_registry()
    allowlist = ToolAllowlist(mode=ResearchMode.READ_ONLY)
    expected = tuple(sorted(tool.name for tool in registry.all_tools() if allowlist.is_allowed(tool.name)))
    profile = _profile()

    assert registry.count() == 36
    assert read_only_tool_names() == expected
    assert profile["capabilities"]["initial_advertised_tools"] == list(expected)
    assert profile["capabilities"]["effective_read_only_tools"] == list(expected)
    assert profile["capabilities"]["tool_count"] == len(expected) == 10
    assert profile["config_fragment"]["mcp"]["servers"]["deepr"]["toolFilter"]["include"] == list(expected)


def test_profile_is_deterministic_and_digest_bound() -> None:
    first = _profile()
    second = _profile()

    assert serialize_host_profile(first) == serialize_host_profile(second)
    assert host_profile_sha256(first) == host_profile_sha256(second)
    assert serialize_host_profile(first).endswith("\n")
    assert not serialize_host_profile(first).endswith("\n\n")


def test_profile_has_contained_zero_spend_environment() -> None:
    profile = _profile()
    server = profile["config_fragment"]["mcp"]["servers"]["deepr"]
    env = server["env"]

    assert env["DEEPR_RESEARCH_MODE"] == "read_only"
    assert env["DEEPR_MCP_AUTO_APPROVE"] == "0"
    assert env["DEEPR_MCP_ADVERTISE_FULL_TOOL_LIST"] == "1"
    assert all(
        env[name] == "0"
        for name in (
            "DEEPR_MAX_COST_PER_JOB",
            "DEEPR_MAX_COST_PER_DAY",
            "DEEPR_MAX_COST_PER_WEEK",
            "DEEPR_MAX_COST_PER_MONTH",
            "DEEPR_PER_JOB_LIMIT",
            "DEEPR_DAILY_LIMIT",
            "DEEPR_WEEKLY_LIMIT",
            "DEEPR_MONTHLY_LIMIT",
        )
    )
    assert not any(re.search(r"(?:API_KEY|TOKEN|SECRET|PASSWORD)$", name) for name in env)
    for name in (
        "DEEPR_DATA_DIR",
        "DEEPR_EXPERTS_PATH",
        "DEEPR_REPORTS_PATH",
        "DEEPR_COST_DATA_DIR",
        "DEEPR_CAPACITY_DATA_DIR",
        "DEEPR_BUDGET_FILE",
    ):
        value = env[name]
        assert value.startswith("${DEEPR_HOST_DATA}/")
        assert not PurePosixPath(value).is_absolute()
        assert not re.match(r"^[A-Za-z]:", value)
        assert "\\" not in value


@pytest.mark.parametrize(
    "placeholder",
    ("", "DEEPR_HOST_DATA", "${lower}", "${DEEPR-HOST}", "${DEEPR_HOST_DATA}/outside", "${A}${B}"),
)
def test_contained_environment_rejects_malformed_placeholders(placeholder: str) -> None:
    with pytest.raises(ValueError, match="one explicit"):
        build_contained_read_only_env(placeholder)


def test_profile_cannot_self_promote_or_widen_authority() -> None:
    profile = _profile()
    profile["validation"]["status"] = "live_validated"
    profile["validation"]["live_runtime_checked"] = True
    profile["capabilities"]["auto_approve"] = True

    violations = validate_host_profile(profile)
    assert {item.code for item in violations} >= {"capabilities", "validation_status"}
    with pytest.raises(ValueError, match="invalid host profile"):
        serialize_host_profile(profile)

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(profile)


def test_descriptive_extensions_are_accepted_but_cannot_change_authority() -> None:
    profile = _profile()
    profile["extensions"] = {
        "operator_note": "review before installation",
        "nested": {"items": [None, True, 3, 1.5, "value"]},
    }

    assert not validate_host_profile(profile)
    assert json.loads(serialize_host_profile(profile))["extensions"] == profile["extensions"]

    profile["extensions"]["tools"] = ["deepr_research"]
    assert not validate_host_profile(profile)
    assert profile["capabilities"]["effective_read_only_tools"] == list(read_only_tool_names())


@pytest.mark.parametrize(
    "bad_value",
    (
        float("nan"),
        float("inf"),
        float("-inf"),
        {"set"},
        b"bytes",
        {1: "non-string-key"},
        1 << 5000,
        "\ud800",
    ),
)
def test_extensions_reject_non_finite_or_non_json_values(bad_value) -> None:
    profile = _profile()
    profile["extensions"] = {"bad": bad_value}

    assert {item.code for item in validate_host_profile(profile)} >= {"extensions_json"}
    with pytest.raises(ValueError, match="invalid host profile"):
        serialize_host_profile(profile)


def test_extensions_reject_cycles() -> None:
    profile = _profile()
    cycle: dict[str, object] = {}
    cycle["self"] = cycle
    profile["extensions"] = cycle

    assert {item.code for item in validate_host_profile(profile)} >= {"extensions_json"}


def test_extension_node_cap_stops_before_scanning_late_keys() -> None:
    profile = _profile()
    extensions: dict[object, object] = {f"key-{index}": index for index in range(600)}
    extensions[1] = "late non-string key"
    profile["extensions"] = extensions

    violations = validate_host_profile(profile)

    extension_violation = next(item for item in violations if item.code == "extensions_json")
    assert "maximum JSON node count" in extension_violation.detail


@pytest.mark.parametrize("bad_root", (None, [], "profile"))
def test_non_object_root_returns_a_violation(bad_root) -> None:
    violations = validate_host_profile(bad_root)

    assert {item.code for item in violations} == {"root_type"}


def test_claimed_deepr_version_is_bound_to_runtime_truth() -> None:
    profile = _profile()
    profile["deepr"]["version"] = "999.0.0"

    assert {item.code for item in validate_host_profile(profile)} >= {"deepr_runtime"}


def test_v1_generation_fails_when_runtime_tool_authority_drifts(monkeypatch) -> None:
    profile = _profile()
    base_tools = read_only_tool_names()
    monkeypatch.setattr(
        host_profile_module,
        "effective_tool_names",
        lambda _registry, _allowlist: {*base_tools, "deepr_future_read"},
    )

    with pytest.raises(RuntimeError, match="requires a new host-profile schema version"):
        build_host_profile("openclaw")
    assert {item.code for item in validate_host_profile(profile)} >= {"tool_authority_drift"}


@pytest.mark.parametrize(
    ("host", "version"),
    (("unknown", None), ("openclaw", "v0.0.0")),
)
def test_unknown_host_or_version_fails_closed(host: str, version: str | None) -> None:
    with pytest.raises(ValueError, match="unsupported host or version"):
        build_host_profile(host, version)


def test_generation_opens_no_network_or_subprocess_and_writes_no_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline profile generation attempted an external operation")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    for name in (
        "HOME",
        "USERPROFILE",
        "XDG_DATA_HOME",
        "DEEPR_DATA_DIR",
        "DEEPR_EXPERTS_PATH",
        "DEEPR_REPORTS_PATH",
        "DEEPR_COST_DATA_DIR",
        "DEEPR_CAPACITY_DATA_DIR",
        "DEEPR_BUDGET_FILE",
    ):
        monkeypatch.setenv(name, str(tmp_path / "ambient" / name.lower()))
    before = tuple(tmp_path.iterdir())

    assert _profile()["authority"]["generation_mode"] == "offline_config_only"
    assert tuple(tmp_path.iterdir()) == before


def test_cli_prints_canonical_json_without_writing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(host_profile, ["openclaw"])

    assert result.exit_code == 0, result.output
    assert result.output == serialize_host_profile(_profile())
    assert not tuple(tmp_path.iterdir())


def test_cli_subprocess_stdout_bytes_match_lf_fixture(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from deepr.cli.main import main; main()",
            "mcp",
            "host-profile",
            "openclaw",
        ],
        capture_output=True,
        cwd=tmp_path,
        timeout=45,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert completed.stdout == FIXTURE_PATH.read_bytes()
    assert b"\r" not in completed.stdout
    assert not tuple(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_profile_environment_drives_standard_full_catalog_startup() -> None:
    profile = _profile()
    env = profile["config_fragment"]["mcp"]["servers"]["deepr"]["env"]
    with (
        patch.dict(os.environ, env, clear=True),
        patch("deepr.mcp.server.ExpertStore"),
        patch("deepr.mcp.server.load_config", return_value={}),
        patch("deepr.mcp.server.get_resource_handler"),
        patch("deepr.mcp.server.TaskDurabilityManager"),
        patch("deepr.mcp.server.OutputVerifier"),
    ):
        server = DeeprMCPServer()

    listed = await _handle_tools_list(server, {})
    listed_names = {tool["name"] for tool in listed["tools"]}
    assert listed_names == set(profile["capabilities"]["initial_advertised_tools"])


def test_cli_writes_atomically_and_requires_force(tmp_path: Path) -> None:
    output = tmp_path / "profiles" / "openclaw.json"
    runner = CliRunner()

    first = runner.invoke(host_profile, ["openclaw", "--output", str(output)])
    refused = runner.invoke(host_profile, ["openclaw", "--output", str(output)])
    replaced = runner.invoke(host_profile, ["openclaw", "--output", str(output), "--force"])

    assert first.exit_code == 0, first.output
    assert refused.exit_code != 0
    assert "exists" in refused.output.lower()
    assert replaced.exit_code == 0, replaced.output
    assert output.read_text(encoding="utf-8") == serialize_host_profile(_profile())


def test_cli_invalid_host_creates_no_output_parent(tmp_path: Path) -> None:
    output = tmp_path / "missing" / "profile.json"
    result = CliRunner().invoke(host_profile, ["unknown", "--output", str(output)])

    assert result.exit_code != 0
    assert "unsupported host or version" in result.output
    assert not output.parent.exists()


def test_installed_entrypoint_uses_standard_full_list_and_blocks_write(tmp_path: Path) -> None:
    command = shutil.which("deepr-mcp")
    assert command is not None
    profile = _profile()
    declared = profile["config_fragment"]["mcp"]["servers"]["deepr"]["env"]
    host_data = tmp_path / "host-data"
    environment = {
        name: os.environ[name]
        for name in (
            "COMSPEC",
            "ComSpec",
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "SystemRoot",
            "TEMP",
            "TMP",
            "TMPDIR",
            "WINDIR",
        )
        if name in os.environ
    }
    environment.update(
        {
            "HOME": str(host_data / "home"),
            "USERPROFILE": str(host_data / "home"),
            "DEEPR_HOST_DATA": str(host_data),
            **{name: value.replace("${DEEPR_HOST_DATA}", str(host_data)) for name, value in declared.items()},
        }
    )
    requests = (
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "host-profile-test", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "deepr_research",
                "arguments": {"prompt": "must remain blocked", "_approved": True},
            },
        },
    )

    completed = subprocess.run(
        [command],
        input="".join(f"{json.dumps(request)}\n" for request in requests),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=environment,
        timeout=45,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line]
    assert [response["id"] for response in responses] == [1, 2, 3]
    advertised = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert advertised == set(profile["capabilities"]["initial_advertised_tools"])
    blocked = json.loads(responses[2]["result"]["content"][0]["text"])
    assert blocked["error_code"] == "TOOL_BLOCKED"


def test_unknown_authority_field_fails_closed() -> None:
    profile = deepcopy(_profile())
    profile["authority"]["new_permission"] = True

    assert {item.code for item in validate_host_profile(profile)} >= {"authority"}
