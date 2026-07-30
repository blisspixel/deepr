"""Fail-closed compatibility entry point for obsolete research integration."""

EXTERNAL_METADATA_EXECUTION_ENABLED = False


def main() -> int:
    print("BLOCKED: obsolete integration bypasses canonical bounded reconciliation and durable settlement.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
