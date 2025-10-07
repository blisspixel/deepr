#!/usr/bin/env python3
"""
Local Environment Cleanup Script

Cleans up local development environment:
- Removes queue database
- Clears result files
- Clears logs
- Optional: Remove all generated data
"""

import sys
from pathlib import Path
import shutil


def cleanup_queue(force=False):
    """Remove queue database."""
    db_path = Path("queue/research_queue.db")

    if not db_path.exists():
        print("  No queue database to clean")
        return

    if not force:
        response = input(f"Delete queue database at {db_path}? (y/N): ")
        if response.lower() != 'y':
            print("  Skipped")
            return

    db_path.unlink()
    print(f"  ✓ Deleted {db_path}")


def cleanup_results(force=False):
    """Remove result files."""
    results_dir = Path("results")

    if not results_dir.exists():
        print("  No results directory to clean")
        return

    files = list(results_dir.glob("*"))
    if not files:
        print("  No result files to clean")
        return

    if not force:
        print(f"  Found {len(files)} result files")
        response = input(f"Delete all result files? (y/N): ")
        if response.lower() != 'y':
            print("  Skipped")
            return

    for file in files:
        if file.is_file():
            file.unlink()

    print(f"  ✓ Deleted {len(files)} result files")


def cleanup_logs(force=False):
    """Remove log files."""
    logs_dir = Path("logs")

    if not logs_dir.exists():
        print("  No logs directory to clean")
        return

    files = list(logs_dir.glob("*.log"))
    if not files:
        print("  No log files to clean")
        return

    if not force:
        print(f"  Found {len(files)} log files")
        response = input(f"Delete all log files? (y/N): ")
        if response.lower() != 'y':
            print("  Skipped")
            return

    for file in files:
        file.unlink()

    print(f"  ✓ Deleted {len(files)} log files")


def cleanup_uploads(force=False):
    """Remove uploaded files."""
    uploads_dir = Path("uploads")

    if not uploads_dir.exists():
        print("  No uploads directory to clean")
        return

    files = list(uploads_dir.glob("*"))
    if not files:
        print("  No uploaded files to clean")
        return

    if not force:
        print(f"  Found {len(files)} uploaded files")
        response = input(f"Delete all uploaded files? (y/N): ")
        if response.lower() != 'y':
            print("  Skipped")
            return

    for file in files:
        if file.is_file():
            file.unlink()

    print(f"  ✓ Deleted {len(files)} uploaded files")


def cleanup_all(force=False):
    """Remove all local data directories."""
    dirs = ["queue", "results", "logs", "uploads"]

    if not force:
        print("\n⚠  WARNING: This will delete ALL local data")
        response = input("Continue? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled")
            return

    for dir_name in dirs:
        dir_path = Path(dir_name)
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"  ✓ Deleted {dir_name}/")


def main():
    """Run cleanup based on arguments."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Clean up local Deepr environment"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Remove all local data directories"
    )
    parser.add_argument(
        "--queue",
        action="store_true",
        help="Clean queue database"
    )
    parser.add_argument(
        "--results",
        action="store_true",
        help="Clean result files"
    )
    parser.add_argument(
        "--logs",
        action="store_true",
        help="Clean log files"
    )
    parser.add_argument(
        "--uploads",
        action="store_true",
        help="Clean uploaded files"
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Skip confirmation prompts"
    )

    args = parser.parse_args()

    print("="*60)
    print("Deepr Local Environment Cleanup")
    print("="*60)
    print()

    # If no specific flags, clean everything except all
    if not any([args.all, args.queue, args.results, args.logs, args.uploads]):
        print("Cleaning standard items (queue, results, logs)...")
        print()
        print("Queue Database:")
        cleanup_queue(args.force)
        print()
        print("Result Files:")
        cleanup_results(args.force)
        print()
        print("Log Files:")
        cleanup_logs(args.force)
    else:
        if args.all:
            cleanup_all(args.force)
        else:
            if args.queue:
                print("Queue Database:")
                cleanup_queue(args.force)
                print()
            if args.results:
                print("Result Files:")
                cleanup_results(args.force)
                print()
            if args.logs:
                print("Log Files:")
                cleanup_logs(args.force)
                print()
            if args.uploads:
                print("Uploaded Files:")
                cleanup_uploads(args.force)
                print()

    print()
    print("="*60)
    print("Cleanup complete")
    print("="*60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
