"""Fail-closed compatibility entry point for obsolete provider status reads."""

EXTERNAL_METADATA_EXECUTION_ENABLED = False


def main() -> int:
    print(
        "BLOCKED: obsolete expert status utility bypasses canonical bounded reconciliation. Use `deepr status JOB_ID`."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
