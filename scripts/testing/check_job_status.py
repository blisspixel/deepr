"""Fail-closed compatibility stub for legacy provider status checks."""

EXTERNAL_METADATA_EXECUTION_ENABLED = False


def main() -> int:
    """Refuse direct provider metadata traffic."""
    print("BLOCKED: direct provider job-status traffic is disabled.")
    print("Use deepr status for jobs already tracked in the canonical queue.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
