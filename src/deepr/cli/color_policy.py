"""Runtime color-output policy for the CLI."""

from __future__ import annotations

import os
import sys

from rich.console import Console


def apply_no_color() -> None:
    """Disable Rich color output for existing and future CLI consoles."""
    os.environ["NO_COLOR"] = os.environ.get("NO_COLOR") or "1"
    for module in tuple(sys.modules.values()):
        if module is None:
            continue
        namespace = getattr(module, "__dict__", None)
        if not namespace:
            continue
        for value in tuple(namespace.values()):
            if isinstance(value, Console):
                value.no_color = True


__all__ = ["apply_no_color"]
