"""Tests for deepr.cli.main entrypoint behavior."""

import importlib


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


def test_main_routes_no_args_to_interactive(monkeypatch):
    main_module = importlib.import_module("deepr.cli.main")
    fake_cli = _FakeCLI()
    monkeypatch.setattr(main_module, "cli", fake_cli)
    monkeypatch.setattr(main_module.sys, "argv", ["deepr"])

    main_module.main()

    assert len(fake_cli.main_calls) == 1
    _args, kwargs = fake_cli.main_calls[0]
    assert kwargs["args"] == ["interactive"]
    assert kwargs["prog_name"] == "deepr"
    assert kwargs["standalone_mode"] is False
    assert fake_cli.call_count == 0


def test_main_uses_cli_for_explicit_args(monkeypatch):
    main_module = importlib.import_module("deepr.cli.main")
    fake_cli = _FakeCLI()
    monkeypatch.setattr(main_module, "cli", fake_cli)
    monkeypatch.setattr(main_module.sys, "argv", ["deepr", "status"])

    main_module.main()

    assert fake_cli.call_count == 1
    assert fake_cli.main_calls == []
