"""Tests for `deepr mcp serve` transport selection."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from deepr.cli.commands.mcp import mcp
from deepr.mcp.smoke import MCPHttpSmokeReport, MCPHttpSmokeStep


def test_mcp_serve_defaults_to_stdio_server():
    with patch("deepr.mcp.server.main") as main:
        result = CliRunner().invoke(mcp, ["serve"])

    assert result.exit_code == 0, result.output
    main.assert_called_once_with()
    assert "Starting Deepr MCP Server" in result.output


def test_mcp_serve_http_uses_http_runner(tmp_path):
    keys_path = tmp_path / "keys.json"
    calls: list[dict] = []

    def fake_run_http_server(**kwargs):
        calls.append(kwargs)
        return "http-coro"

    with (
        patch("deepr.mcp.http_server.run_http_server", new=fake_run_http_server),
        patch("deepr.cli.commands.mcp.run_async_command") as run_async,
    ):
        result = CliRunner().invoke(
            mcp,
            [
                "serve",
                "--http",
                "--host",
                "127.0.0.1",
                "--port",
                "18888",
                "--path",
                "/x",
                "--auth-token",
                "token",
                "--keys-path",
                str(keys_path),
                "--max-concurrency",
                "9",
            ],
        )

    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "host": "127.0.0.1",
            "port": 18888,
            "path": "/x",
            "auth_token": "token",
            "keys_path": str(keys_path),
            "max_concurrent_requests": 9,
            "allow_unauthenticated_public_bind": False,
        }
    ]
    run_async.assert_called_once_with("http-coro")
    assert "http://127.0.0.1:18888/x" in result.output


def test_mcp_smoke_http_outputs_json_success():
    calls: list[dict] = []
    report = MCPHttpSmokeReport(
        url="http://127.0.0.1:8765/mcp",
        steps=(MCPHttpSmokeStep("health", True, "healthy", status_code=200),),
    )

    def fake_run_http_smoke(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return "smoke-coro"

    with (
        patch("deepr.mcp.smoke.run_http_smoke", new=fake_run_http_smoke),
        patch("deepr.cli.commands.mcp.run_async_command", return_value=report) as run_async,
    ):
        result = CliRunner().invoke(
            mcp,
            [
                "smoke-http",
                "http://127.0.0.1:8765/mcp",
                "--auth-token",
                "secret",
                "--timeout",
                "2",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "url": "http://127.0.0.1:8765/mcp",
            "auth_token": "secret",
            "timeout_seconds": 2.0,
        }
    ]
    run_async.assert_called_once_with("smoke-coro")
    assert '"ok": true' in result.output
    assert '"status_code": 200' in result.output


def test_mcp_smoke_http_exits_nonzero_on_failure():
    report = MCPHttpSmokeReport(
        url="http://127.0.0.1:8765/mcp",
        steps=(MCPHttpSmokeStep("tools/call", False, "Denied"),),
    )

    def fake_run_http_smoke(url, **kwargs):
        return "smoke-coro"

    with (
        patch("deepr.mcp.smoke.run_http_smoke", new=fake_run_http_smoke),
        patch("deepr.cli.commands.mcp.run_async_command", return_value=report),
    ):
        result = CliRunner().invoke(mcp, ["smoke-http", "http://127.0.0.1:8765/mcp"])

    assert result.exit_code == 1
    assert "[fail] tools/call: Denied" in result.output
    assert "Result: failed" in result.output


def test_mcp_registration_manifest_outputs_token_redacted_json():
    calls: list[dict] = []
    report = MCPHttpSmokeReport(
        url="https://mcp.example.com/mcp",
        steps=(MCPHttpSmokeStep("health", True, "healthy", status_code=200),),
    )

    def fake_run_http_smoke(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return "registration-smoke-coro"

    with (
        patch("deepr.mcp.smoke.run_http_smoke", new=fake_run_http_smoke),
        patch("deepr.cli.commands.mcp.run_async_command", return_value=report),
    ):
        result = CliRunner().invoke(
            mcp,
            [
                "registration-manifest",
                "https://mcp.example.com/mcp",
                "--agent-name",
                "planner",
                "--auth-token",
                "test-token-value",
            ],
        )

    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "url": "https://mcp.example.com/mcp",
            "auth_token": "test-token-value",
            "timeout_seconds": 10.0,
        }
    ]
    assert '"schema_version": "deepr-mcp-registration-manifest-v1"' in result.output
    assert '"agent_name": "planner"' in result.output
    assert '"secret_included": false' in result.output
    assert "test-token-value" not in result.output


def test_mcp_registration_manifest_writes_output_file(tmp_path):
    output_path = tmp_path / "manifest.json"

    with patch("deepr.cli.commands.mcp.run_async_command") as run_async:
        result = CliRunner().invoke(
            mcp,
            [
                "registration-manifest",
                "https://mcp.example.com/mcp",
                "--skip-smoke",
                "--output",
                str(output_path),
            ],
        )

    assert result.exit_code == 0, result.output
    run_async.assert_not_called()
    assert "Wrote MCP registration manifest" in result.output
    assert '"url": "https://mcp.example.com/mcp"' in output_path.read_text(encoding="utf-8")


def test_mcp_registration_manifest_exits_nonzero_on_failed_smoke():
    report = MCPHttpSmokeReport(
        url="https://mcp.example.com/mcp",
        steps=(MCPHttpSmokeStep("tools/call", False, "Denied"),),
    )

    def fake_run_http_smoke(url, **kwargs):
        return "registration-smoke-coro"

    with (
        patch("deepr.mcp.smoke.run_http_smoke", new=fake_run_http_smoke),
        patch("deepr.cli.commands.mcp.run_async_command", return_value=report),
    ):
        result = CliRunner().invoke(mcp, ["registration-manifest", "https://mcp.example.com/mcp"])

    assert result.exit_code == 1
    assert '"ok": false' in result.output
