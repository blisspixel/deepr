#!/usr/bin/env python3
"""
Comprehensive Test Validation Script

Runs all local tests without making API calls:
- Cost estimation tests
- Queue system tests
- Provider tests (mocked)
- Storage tests
- Configuration tests

Validates code without spending money on APIs.
"""

import sys
import subprocess
from pathlib import Path


def run_command(cmd, description):
    """Run command and report results."""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")

    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    return result.returncode == 0


def main():
    """Run all test suites."""
    print("="*60)
    print("Deepr Local Test Validation")
    print("="*60)
    print("\nRunning all tests without API calls...")

    results = {}

    # 1. Cost estimation tests
    results['costs'] = run_command(
        "python -m pytest tests/unit/test_costs.py -v",
        "1. Cost Estimation Tests"
    )

    # 2. Queue system tests
    results['queue'] = run_command(
        "python -m pytest tests/unit/test_queue/test_local_queue.py -v",
        "2. Queue System Tests"
    )

    # 3. Provider tests (unit only, skip integration)
    results['providers'] = run_command(
        "python -m pytest tests/unit/test_providers/ -v -m 'not integration'",
        "3. Provider Tests (Mocked)"
    )

    # 4. Storage tests
    results['storage'] = run_command(
        "python -m pytest tests/unit/test_storage/ -v",
        "4. Storage Backend Tests"
    )

    # 5. Configuration tests
    results['config'] = run_command(
        "python -m pytest tests/unit/test_config.py -v",
        "5. Configuration Tests"
    )

    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)

    total = len(results)
    passed = sum(1 for v in results.values() if v)

    for test_name, success in results.items():
        status = "PASS" if success else "FAIL"
        symbol = "✓" if success else "✗"
        print(f"  {symbol} {test_name.ljust(20)} {status}")

    print()
    print(f"Total: {passed}/{total} test suites passed")
    print("="*60)

    if passed == total:
        print("\n✓ All tests passed - code validated locally without API costs")
        return 0
    else:
        print(f"\n✗ {total - passed} test suite(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
