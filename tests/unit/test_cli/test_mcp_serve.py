"""Tests for `deepr mcp serve` transport selection."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from deepr.cli.commands.mcp import mcp


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
            "allow_unauthenticated_public_bind": False,
        }
    ]
    run_async.assert_called_once_with("http-coro")
    assert "http://127.0.0.1:18888/x" in result.output
