"""Regression tests for test-suite isolation guarantees."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_socket import SocketBlockedError, SocketConnectBlockedError

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_unit_collection_ignores_dotenv_and_inherited_provider_credentials():
    """Shared unit setup must remove every ambient metered credential."""
    credential_names = (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
        "ANTHROPIC_API_KEY",
        "XAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_FOUNDRY_API_KEY",
        "ANTIGRAVITY_API_KEY",
        "KIRO_API_KEY",
    )
    environment = os.environ.copy()
    environment.pop("DEEPR_RUN_LIVE_TESTS", None)
    environment["PYTHON_DOTENV_DISABLED"] = "0"
    environment.update({name: f"inherited-{index}" for index, name in enumerate(credential_names)})
    names_literal = repr(credential_names)
    script = (
        "import os, runpy; "
        "runpy.run_path('tests/conftest.py'); "
        "assert os.environ.get('PYTHON_DOTENV_DISABLED') == '1'; "
        f"assert not any(os.environ.get(name) for name in {names_literal})"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_live_integration_setup_loads_dotenv_only_after_explicit_opt_in():
    """The live-only subtree owns dotenv loading after the explicit gate."""
    script = """
import os
import runpy
import sys
import types

calls = []
dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda: calls.append("loaded")
sys.modules["dotenv"] = dotenv
os.environ["DEEPR_RUN_LIVE_TESTS"] = "1"
runpy.run_path("tests/integration/conftest.py")
assert calls == ["loaded"]
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_unit_gate_blocks_outbound_sockets():
    """Unit tests must fail closed on accidental provider or web calls."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.01)
        with pytest.warns(UserWarning, match="socket.socket.connect"):
            with pytest.raises((SocketBlockedError, SocketConnectBlockedError)):
                sock.connect(("203.0.113.1", 80))


def test_unit_gate_allows_loopback_sockets():
    """Loopback remains available for local fixtures and smoke helpers."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.settimeout(1.0)
    client.settimeout(1.0)

    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)

        client.connect(server.getsockname())
        connection, _address = server.accept()
        connection.close()
    finally:
        client.close()
        server.close()
