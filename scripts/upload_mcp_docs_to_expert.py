"""Retired unsafe hosted-vector-store upload script.

Hosted files and vector stores can create persistent charges. The old script
performed both writes without reservation, retention bounds, cleanup, or ledger
settlement, so it must remain unavailable until storage pricing is part of the
shared durable transaction.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "Disabled: this legacy upload cannot prove bounded storage cost and cleanup. "
        "Use local expert documents and an explicit local or plan absorb workflow.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
