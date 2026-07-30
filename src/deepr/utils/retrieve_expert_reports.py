"""Fail-closed compatibility entry point for obsolete report retrieval."""

EXTERNAL_METADATA_EXECUTION_ENABLED = False


def main() -> int:
    print("BLOCKED: obsolete report retrieval bypasses canonical reconciliation and cost settlement.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
