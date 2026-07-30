"""Fail-closed compatibility entry point for legacy documentation analysis."""

from __future__ import annotations

ANALYSIS_EXECUTION_ENABLED = False


def main() -> int:
    """Refuse the obsolete raw paid-model path before any imports or reads."""
    print(
        "BLOCKED [documentation_gap_analysis_disabled]: the legacy script has "
        "no durable reservation, exact request grant, or settlement path. Use "
        '`deepr expert consult "Which documentation gaps matter most?" --local`.'
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
