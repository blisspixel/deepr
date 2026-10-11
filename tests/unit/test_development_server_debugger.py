"""Exercise development launchers through the real Flask/Werkzeug boundary."""

import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import werkzeug._reloader
import werkzeug.serving
from click.testing import CliRunner
from werkzeug.debug import DebuggedApplication

import deepr


@pytest.fixture
def listener(monkeypatch):
    """Replace only socket ownership and the reload process, not framework code."""
    for name in (
        "FLASK_RUN_FROM_CLI",
        "FLASK_DEBUG",
        "WERKZEUG_RUN_MAIN",
        "DEEPR_DEMO",
        "DEEPR_HOST",
        "DEEPR_PORT",
        "DEEPR_DEBUG",
        "DEEPR_API_TOKEN",
        "DEEPR_API_KEY",
        "DEEPR_API_ALLOW_UNAUTHENTICATED_LOOPBACK",
        "DEEPR_WEB_ALLOW_UNAUTHENTICATED_LOOPBACK",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WERKZEUG_SERVER_FD", "-1")
    server = MagicMock()
    server.fileno.return_value = 42
    factory = MagicMock(return_value=server)
    reloader = MagicMock()
    monkeypatch.setattr(werkzeug.serving, "make_server", factory)
    monkeypatch.setattr(werkzeug._reloader, "run_with_reloader", reloader)
    return SimpleNamespace(factory=factory, server=server, reloader=reloader)


@pytest.fixture
def dashboard(monkeypatch, listener):
    from deepr.web import app as web_app

    # The framework and Click launcher update these existing module objects.
    monkeypatch.setitem(web_app.app.config, "DEBUG", web_app.app.debug)
    monkeypatch.setattr(web_app, "_API_KEY", web_app._API_KEY)
    monkeypatch.setattr(web_app, "_ALLOW_UNAUTHENTICATED_LOOPBACK", web_app._ALLOW_UNAUTHENTICATED_LOOPBACK)
    return web_app


def _run_api_module():
    runpy.run_path(str(Path(deepr.__file__).parent / "api" / "app.py"), run_name="__main__")


def _assert_server_contract(listener, *, host, port, debug):
    listener.factory.assert_called_once()
    actual_host, actual_port, application = listener.factory.call_args.args[:3]
    assert (actual_host, actual_port) == (host, port)
    assert not isinstance(application, DebuggedApplication)
    assert application.debug is debug
    if debug:
        listener.reloader.assert_called_once()
        assert listener.reloader.call_args.args[0] == listener.server.serve_forever
        listener.server.serve_forever.assert_not_called()
    else:
        listener.reloader.assert_not_called()
        listener.server.serve_forever.assert_called_once_with()


@pytest.mark.parametrize(
    ("host", "debug_env", "expected_debug"),
    [
        ("127.0.0.1", "", False),
        ("127.0.0.1", "1", True),
        ("127.0.0.1", "true", True),
        ("127.0.0.1", "YES", True),
        ("127.0.0.1", "0", False),
        ("localhost", "true", True),
        ("::1", "1", True),
        ("0.0.0.0", "1", False),
    ],
)
def test_api_startup_disables_browser_debugger_and_preserves_reload(
    listener, monkeypatch, host, debug_env, expected_debug
):
    monkeypatch.setenv("DEEPR_HOST", host)
    monkeypatch.setenv("DEEPR_PORT", "5071")
    monkeypatch.setenv("DEEPR_DEBUG", debug_env)
    monkeypatch.setenv("DEEPR_API_TOKEN", "test-only-api-token")

    _run_api_module()

    _assert_server_contract(listener, host=host, port=5071, debug=expected_debug)


def test_api_explicit_tokenless_loopback_preserves_debug_reload(listener, monkeypatch):
    monkeypatch.setenv("DEEPR_HOST", "127.0.0.1")
    monkeypatch.setenv("DEEPR_PORT", "")
    monkeypatch.setenv("DEEPR_DEBUG", "1")
    monkeypatch.setenv("DEEPR_API_ALLOW_UNAUTHENTICATED_LOOPBACK", "1")

    _run_api_module()

    _assert_server_contract(listener, host="127.0.0.1", port=5000, debug=True)


@pytest.mark.parametrize(("host", "allow_tokenless"), [("127.0.0.1", False), ("0.0.0.0", True), ("", True)])
def test_api_debug_cannot_bypass_startup_authentication(listener, monkeypatch, host, allow_tokenless):
    monkeypatch.setenv("DEEPR_HOST", host)
    monkeypatch.setenv("DEEPR_DEBUG", "1")
    monkeypatch.setenv("DEEPR_API_ALLOW_UNAUTHENTICATED_LOOPBACK", "1" if allow_tokenless else "0")

    with pytest.raises(SystemExit) as error:
        _run_api_module()

    assert error.value.code == 2
    listener.factory.assert_not_called()
    listener.reloader.assert_not_called()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
@pytest.mark.parametrize("debug", [False, True])
def test_dashboard_helper_disables_browser_debugger_and_preserves_reload(listener, dashboard, host, debug):
    dashboard._run_loopback_development_server(host=host, port=5071, debug=debug)

    _assert_server_contract(listener, host=host, port=5071, debug=debug)


@pytest.mark.parametrize("host", ["0.0.0.0", "", "::", "example.invalid"])
@pytest.mark.parametrize("debug", [False, True])
def test_dashboard_debug_cannot_bypass_loopback_refusal(listener, dashboard, host, debug):
    with pytest.raises(RuntimeError, match="requires a loopback host"):
        dashboard._run_loopback_development_server(host=host, port=5071, debug=debug)

    listener.factory.assert_not_called()
    listener.reloader.assert_not_called()


@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.parametrize("tokenless", [False, True])
def test_cli_disables_browser_debugger_and_preserves_reload(listener, dashboard, monkeypatch, debug, tokenless):
    from deepr.cli.commands.web import web

    args = ["--host", "localhost", "--port", "5071"]
    if debug:
        args.append("--debug")
    if tokenless:
        args.append("--allow-unauthenticated-loopback")
    else:
        monkeypatch.setenv("DEEPR_API_KEY", "test-only-dashboard-key")

    result = CliRunner().invoke(web, args)

    assert result.exit_code == 0, result.output
    assert dashboard._API_KEY == ("" if tokenless else "test-only-dashboard-key")
    assert dashboard._ALLOW_UNAUTHENTICATED_LOOPBACK is tokenless
    _assert_server_contract(listener, host="localhost", port=5071, debug=debug)


@pytest.mark.parametrize(
    ("host", "tokenless", "configured_key"),
    [("127.0.0.1", False, False), ("0.0.0.0", False, True), ("0.0.0.0", True, False)],
)
def test_cli_debug_cannot_bypass_bind_or_authentication_refusal(
    listener, dashboard, monkeypatch, host, tokenless, configured_key
):
    from deepr.cli.commands.web import web

    args = ["--host", host, "--debug"]
    if tokenless:
        args.append("--allow-unauthenticated-loopback")
    if configured_key:
        monkeypatch.setenv("DEEPR_API_KEY", "test-only-dashboard-key")

    result = CliRunner().invoke(web, args)

    assert result.exit_code != 0
    assert "Refusing" in result.output
    listener.factory.assert_not_called()
    listener.reloader.assert_not_called()
