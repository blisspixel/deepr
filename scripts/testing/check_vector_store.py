"""Fail-closed compatibility stub for legacy vector-store metadata checks."""

EXTERNAL_METADATA_EXECUTION_ENABLED = False


def main() -> int:
    """Refuse direct hosted-storage metadata traffic."""
    print("BLOCKED: direct hosted vector-store metadata traffic is disabled.")
    print("Hosted storage accounting is not available in v2.40.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
