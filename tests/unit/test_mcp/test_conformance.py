"""Offline MCP conformance suite tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from click.testing import CliRunner

from deepr.cli.commands.mcp import mcp
from deepr.mcp.conformance import (
    CONFORMANCE_KIND,
    CONFORMANCE_SCHEMA_VERSION,
    run_offline_mcp_conformance,
)
from deepr.mcp.protocol_modern import MODERN_PROTOCOL_VERSION


def test_core_entrypoints_work_without_optional_preparation_dependency(tmp_path) -> None:
    """Use fresh shipped imports: full/dev site packages must not mask the gate."""
    code = textwrap.dedent("""
        import asyncio
        import importlib.abc
        import json
        import sys
        from pathlib import Path

        class CoreDependencies(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "packaging" or fullname.startswith("packaging."):
                    raise ModuleNotFoundError("optional preparation dependency unavailable", name=fullname)

        sys.meta_path.insert(0, CoreDependencies())
        from click.testing import CliRunner
        from deepr.cli.commands.mcp import mcp
        from deepr.cli.commands.semantic.expert_consult import expert_consult
        from deepr.mcp.consult_tool import consult_experts_tool
        from deepr.mcp.request_context import trusted_stdio_request
        import deepr.mcp.server

        result = CliRunner().invoke(mcp, ["conformance", "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["ok"]
        assert CliRunner().invoke(expert_consult, ["--help"]).exit_code == 0
        assert "packaging" not in sys.modules
        assert "deepr.experts.preparation_service" not in sys.modules

        # Explicit opt-in must fail at admission, before profile/backend/private work.
        from deepr.experts.profile_store import ExpertStore
        def forbidden(*args, **kwargs):
            raise AssertionError("profile/backend must not be reached")
        ExpertStore.load = forbidden
        import deepr.experts.consult as consult
        consult.build_synthesis_backend = forbidden
        request = {"schema_version": "deepr-python-preparation-request-v1", "enabled": True,
                   "request_id": "core_absence_fixture_001",
                   "environment": {"interpreter_version": "3.12", "platform": "fixture"},
                   "packages": [{"name": "fixture", "version": "1.0"}]}
        path = Path("request.json")
        path.write_text(json.dumps(request), encoding="utf-8")
        result = CliRunner().invoke(expert_consult, ["q", "-e", "E", "--prepare-python", str(path), "--json"])
        assert result.exit_code == 2, result.output
        assert json.loads(result.output)["error"]["code"] == "CONSULT_PREPARATION_INVALID"
        async def prepared():
            with trusted_stdio_request():
                return await consult_experts_tool(question="q", experts=["E"], preparation=request)
        result = asyncio.run(prepared())
        assert result["error_code"] == "PREPARATION_REFUSED", result
        assert not Path("data/preparation").exists()
        assert sorted(p.name for p in Path(".").iterdir()) == ["request.json"]
    """)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[3] / "src")
    env["DEEPR_DATA_DIR"] = str(tmp_path / "data")
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr


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
    schema_path = Path(__file__).resolve().parents[3] / "docs" / "schemas" / "mcp-conformance-v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    payload = run_offline_mcp_conformance().to_dict()
    assert schema["properties"]["schema_version"]["const"] == payload["schema_version"]
    assert schema["properties"]["kind"]["const"] == payload["kind"]
    assert schema["properties"]["mode"]["const"] == payload["mode"]
    assert schema["properties"]["protocol"]["properties"]["modern"]["const"] == payload["protocol"]["modern"]
    assert payload["server_version"]  # package metadata default, not a pinned release string
    for key in schema["required"]:
        assert key in payload
