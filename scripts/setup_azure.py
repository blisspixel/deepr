#!/usr/bin/env python3
"""Reference-only Azure setup entry point.

Azure Storage and Service Bus have account-level costs that Deepr cannot cap or
settle through its application cost ledger. This script deliberately performs
no authentication, file writes, or resource operations.
"""

from __future__ import annotations

import sys

BLOCK_MESSAGE = (
    "BLOCKED: Azure setup cannot enforce the operator's total dollar ceiling. "
    "Review the reference templates manually under deploy/ and establish "
    "provider-side billing controls before provisioning outside Deepr."
)


def main() -> int:
    """Fail closed before any cloud CLI, credential read, or file write."""
    print(BLOCK_MESSAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
