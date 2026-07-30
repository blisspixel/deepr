#!/usr/bin/env python3
"""Fail-closed compatibility stub for legacy Azure teardown automation."""

CLOUD_MUTATION_EXECUTION_ENABLED = False


def main() -> int:
    """Refuse cloud mutation before authentication or subprocess creation."""
    print("BLOCKED: automated Azure teardown is not shipped in v2.40.")
    print("Use the Azure portal with human approval for existing resources.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
