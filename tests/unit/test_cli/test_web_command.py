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
