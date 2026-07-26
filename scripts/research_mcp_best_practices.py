"""Retired unsafe one-off paid research script.

The previous implementation constructed an OpenAI client and started deep
research with web search without consent, a finite request envelope, a durable
reservation, or canonical settlement. Keep this path fail-closed so an old
copied command cannot create an untracked bill.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "Disabled: this legacy script cannot prove a bounded, tracked paid transaction. "
        "Use 'deepr research --preview' and then an explicit bounded research command.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
