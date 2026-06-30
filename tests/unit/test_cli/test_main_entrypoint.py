"""Tests for deepr.cli.main entrypoint behavior."""

import importlib
import io

from click.testing import CliRunner


class _FakeCLI:
    def __init__(self):
        self.main_calls = []
        self.call_count = 0

    def main(self, *args, **kwargs):
        self.main_calls.append((args, kwargs))
        return 0

    def __call__(self, *args, **kwargs):
        self.call_count += 1
        return 0


class _FakeStdin(io.StringIO):
    def __init__(self, tty: bool):
        super().__init__("")
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_main_routes_no_args_to_interactive_on_tty(monkeypatch):
    main_module = importlib.import_module("deepr.cli.main")
    fake_cli = _FakeCLI()
    monkeypatch.setattr(main_module, "cli", fake_cli)
    monkeypatch.setattr(main_module.sys, "argv", ["deepr"])
    monkeypatch.setattr(main_module.sys, "stdin", _FakeStdin(tty=True))

    main_module.main()

    assert len(fake_cli.main_calls) == 1
    _args, kwargs = fake_cli.main_calls[0]
    assert kwargs["args"] == ["interactive"]
    assert kwargs["prog_name"] == "deepr"
    assert kwargs["standalone_mode"] is False
    assert fake_cli.call_count == 0


def test_main_routes_no_args_to_help_when_not_a_tty(monkeypatch):
    """clig.dev: never launch interactive mode for a non-interactive caller."""
    main_module = importlib.import_module("deepr.cli.main")
    fake_cli = _FakeCLI()
    monkeypatch.setattr(main_module, "cli", fake_cli)
    monkeypatch.setattr(main_module.sys, "argv", ["deepr"])
    monkeypatch.setattr(main_module.sys, "stdin", _FakeStdin(tty=False))

    main_module.main()

    assert len(fake_cli.main_calls) == 1
    _args, kwargs = fake_cli.main_calls[0]
    assert kwargs["args"] == ["--help"]
    assert fake_cli.call_count == 0


def test_main_uses_cli_for_explicit_args(monkeypatch):
    main_module = importlib.import_module("deepr.cli.main")
    fake_cli = _FakeCLI()
    monkeypatch.setattr(main_module, "cli", fake_cli)
    monkeypatch.setattr(main_module.sys, "argv", ["deepr", "status"])

    main_module.main()

    assert fake_cli.call_count == 1
    assert fake_cli.main_calls == []


def test_root_no_color_option_applies_policy(monkeypatch):
    main_module = importlib.import_module("deepr.cli.main")
    calls = []
    monkeypatch.setattr(main_module, "apply_no_color", lambda: calls.append("applied"))

    result = CliRunner().invoke(main_module.cli, ["--no-color", "--help"])

    assert result.exit_code == 0
    assert calls == ["applied"]
    assert "--no-color" in result.output
