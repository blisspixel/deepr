"""Safety regressions for the local web-dashboard launcher."""

from unittest.mock import MagicMock

from click.testing import CliRunner

from deepr.cli.commands.web import web
from deepr.web import app as web_app


def test_non_loopback_cli_bind_refuses_unsafe_werkzeug_even_with_auth(monkeypatch) -> None:
    run = MagicMock()
    monkeypatch.setenv("DEEPR_API_KEY", "configured-test-key")
    monkeypatch.setattr(web_app.socketio, "run", run)

    result = CliRunner().invoke(web, ["--host", "0.0.0.0"])

    assert result.exit_code != 0
    assert "Werkzeug" in result.output
    assert "production WSGI server" in result.output
    run.assert_not_called()


def test_loopback_cli_fails_closed_without_dashboard_auth(monkeypatch) -> None:
    run = MagicMock()
    monkeypatch.delenv("DEEPR_API_KEY", raising=False)
    monkeypatch.delenv("DEEPR_WEB_ALLOW_UNAUTHENTICATED_LOOPBACK", raising=False)
    monkeypatch.setattr(web_app.socketio, "run", run)

    result = CliRunner().invoke(web, [])

    assert result.exit_code != 0
    assert "Refusing to start without DEEPR_API_KEY" in result.output
    run.assert_not_called()


def test_explicit_unauthenticated_mode_is_loopback_only(monkeypatch) -> None:
    run = MagicMock()
    monkeypatch.delenv("DEEPR_API_KEY", raising=False)
    monkeypatch.setattr(web_app.socketio, "run", run)

    result = CliRunner().invoke(web, ["--allow-unauthenticated-loopback"])

    assert result.exit_code == 0
    assert web_app._API_KEY == ""
    assert web_app._ALLOW_UNAUTHENTICATED_LOOPBACK is True
    run.assert_called_once_with(
        web_app.app,
        debug=False,
        host="127.0.0.1",
        port=5000,
        allow_unsafe_werkzeug=True,
    )


def test_unauthenticated_switch_cannot_enable_public_bind(monkeypatch) -> None:
    run = MagicMock()
    monkeypatch.delenv("DEEPR_API_KEY", raising=False)
    monkeypatch.setattr(web_app.socketio, "run", run)

    result = CliRunner().invoke(
        web,
        ["--host", "0.0.0.0", "--allow-unauthenticated-loopback"],
    )

    assert result.exit_code != 0
    assert "Werkzeug" in result.output
    run.assert_not_called()
