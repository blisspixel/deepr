"""Fail-closed compatibility entry point for the obsolete job monitor."""

MONITOR_EXECUTION_ENABLED = False


def main() -> int:
    """Refuse an unbounded polling workflow without durable settlement."""
    print(
        "BLOCKED: obsolete monitor used unbounded polling and non-canonical "
        "storage. Use `deepr status JOB_ID` for one bounded read."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
