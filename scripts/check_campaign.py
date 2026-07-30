"""Fail-closed compatibility stub for legacy campaign metadata checks."""

EXTERNAL_METADATA_EXECUTION_ENABLED = False


def main() -> int:
    """Refuse direct provider metadata traffic."""
    print("BLOCKED: direct provider campaign status checks are disabled.")
    print("Use the bounded canonical job status surface for already tracked jobs.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
