"""Tests for `deepr mcp audit` remote-call audit review."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from click.testing import CliRunner

from deepr.cli.commands.mcp import mcp
from deepr.mcp.security.scoped_keys import RemoteMCPAuditEvent, RemoteMCPAuditLog
from deepr.mcp.security.tool_allowlist import ResearchMode


def _record_sample_events(audit_path):
    audit = RemoteMCPAuditLog(audit_path)
    audit.record(
        RemoteMCPAuditEvent(
            key_id="agent-alpha",
            mode=ResearchMode.READ_ONLY,
            tool="deepr_tool_search",
            args_hash="abc",
            trace_id="trace-1",
            outcome="success",
            expert_names=("AI Strategy Expert",),
            cost_usd=0.0,
            timestamp=datetime(2026, 6, 19, 10, 0, tzinfo=UTC),
        )
    )
    audit.record(
        RemoteMCPAuditEvent(
            key_id="agent-beta",
            mode=ResearchMode.STANDARD,
            tool="deepr_query_expert",
            args_hash="def",
            trace_id="trace-2",
            outcome="error",
            error_code="KEY_BUDGET_EXCEEDED",
            expert_names=("Security Expert",),
            cost_usd=None,
            timestamp=datetime(2026, 6, 19, 10, 5, tzinfo=UTC),
        )
    )


def test_mcp_audit_list_outputs_json_with_filters(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    _record_sample_events(audit_path)

    result = CliRunner().invoke(
        mcp,
        [
            "audit",
            "list",
            "--audit-path",
            str(audit_path),
            "--key-id",
            "agent-beta",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["audit_path"] == str(audit_path)
    assert payload["filters"]["key_id"] == "agent-beta"
    assert payload["count"] == 1
    assert payload["events"][0]["key_id"] == "agent-beta"
    assert payload["events"][0]["tool"] == "deepr_query_expert"
    assert payload["events"][0]["error_code"] == "KEY_BUDGET_EXCEEDED"


def test_mcp_audit_list_outputs_table(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    _record_sample_events(audit_path)

    result = CliRunner().invoke(
        mcp,
        [
            "audit",
            "list",
            "--audit-path",
            str(audit_path),
            "--tool",
            "deepr_tool_search",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "MCP remote audit records:" in result.output
    assert "timestamp\tkey_id\tmode\toutcome\ttool\tcost\texperts\terror_code\ttrace_id" in result.output
    assert "agent-alpha\tread_only\tsuccess\tdeepr_tool_search\t$0.0000\tAI Strategy Expert" in result.output
    assert "agent-beta" not in result.output


def test_mcp_audit_list_reports_empty_log(tmp_path):
    audit_path = tmp_path / "missing.jsonl"

    result = CliRunner().invoke(mcp, ["audit", "list", "--audit-path", str(audit_path)])

    assert result.exit_code == 0, result.output
    assert f"No MCP remote audit records found at {audit_path}." in result.output
