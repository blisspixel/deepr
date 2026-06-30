"""Tests for CLI color-output policy."""

from __future__ import annotations

import os
import sys
import types

from rich.console import Console

from deepr.cli.color_policy import apply_no_color


def test_apply_no_color_updates_existing_rich_consoles(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    console_states = []
    for module in tuple(sys.modules.values()):
        namespace = getattr(module, "__dict__", None)
        if not namespace:
            continue
        for value in tuple(namespace.values()):
            if isinstance(value, Console):
                console_states.append((value, value.no_color))

    module_name = "tests.unit.test_cli._fake_color_console_module"
    fake_module = types.ModuleType(module_name)
    fake_module.console = Console(force_terminal=True)
    fake_module.console.no_color = False
    monkeypatch.setitem(sys.modules, module_name, fake_module)

    try:
        apply_no_color()

        assert fake_module.console.no_color is True
        assert os.environ["NO_COLOR"] == "1"
    finally:
        for console, no_color in console_states:
            console.no_color = no_color
