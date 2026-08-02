"""Offline MCP conformance suite tests."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from deepr.cli.commands.mcp import mcp
from deepr.mcp.conformance import (
    CONFORMANCE_KIND,
    CONFORMANCE_SCHEMA_VERSION,
    run_offline_mcp_conformance,
)
from deepr.mcp.protocol_modern import MODERN_PROTOCOL_VERSION


def test_offline_mcp_conformance_passes_without_network_or_model() -> None:
    report = run_offline_mcp_conformance(server_version="test")
    payload = report.to_dict()

    assert report.ok is True
    assert payload["schema_version"] == CONFORMANCE_SCHEMA_VERSION
    assert payload["kind"] == CONFORMANCE_KIND
    assert payload["mode"] == "offline"
    assert payload["cost_usd"] == 0.0
    assert payload["contract"]["network_opened"] is False
    assert payload["contract"]["calls_metered_api"] is False
    assert payload["contract"]["live_model_required"] is False
    assert payload["protocol"]["modern"] == MODERN_PROTOCOL_VERSION
    assert payload["summary"]["ok"] is True
    assert payload["summary"]["failed_checks"] == []
    names = {check["name"] for check in payload["checks"]}
    assert names == {
        "dual_era_protocol",
        "offline_consult_validation",
        "remote_smoke_fail_closed",
        "managed_conversation_fail_closed",
        "registration_manifest_offline",
        "capabilities_map",
    }
    assert all(check["status"] == "passed" for check in payload["checks"])


def test_mcp_conformance_cli_json_exit_zero() -> None:
    result = CliRunner().invoke(mcp, ["conformance", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["schema_version"] == CONFORMANCE_SCHEMA_VERSION
    assert payload["summary"]["failed_checks"] == []


def test_mcp_conformance_cli_writes_output_file(tmp_path: Path) -> None:
    out = tmp_path / "conformance.json"
    result = CliRunner().invoke(mcp, ["conformance", "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert "Wrote MCP conformance report" in result.output
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["kind"] == CONFORMANCE_KIND


def test_published_mcp_conformance_schema_matches_payload() -> None:
    schema_path = (
        Path(__file__).resolve().parents[3] / "docs" / "schemas" / "mcp-conformance-v1.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    payload = run_offline_mcp_conformance(server_version="2.43.0").to_dict()
    assert schema["properties"]["schema_version"]["const"] == payload["schema_version"]
    assert schema["properties"]["kind"]["const"] == payload["kind"]
    assert schema["properties"]["mode"]["const"] == payload["mode"]
    assert schema["properties"]["protocol"]["properties"]["modern"]["const"] == payload["protocol"][
        "modern"
    ]
    for key in schema["required"]:
        assert key in payload
