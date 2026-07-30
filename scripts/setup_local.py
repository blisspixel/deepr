#!/usr/bin/env python3
"""Prepare a tidy local-first Deepr checkout without external calls."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Allow execution from a source checkout without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deepr.cli.colors import console, print_error, print_header, print_success

RUNTIME_DIRECTORIES = (
    Path("data/queue"),
    Path("data/reports"),
    Path("data/uploads"),
    Path("data/logs"),
)

LOCAL_ENV_TEMPLATE = """# Deepr local-first configuration
DEEPR_DATA_DIR=data
DEEPR_REPORTS_PATH=data/reports
DEEPR_QUEUE_DB_PATH=data/queue/research_queue.db

# The authoritative monthly ceiling must never exceed $5.
DEEPR_MAX_COST_PER_JOB=1
DEEPR_MAX_COST_PER_DAY=2
DEEPR_MAX_COST_PER_MONTH=5

# Paid provider keys are optional and do not authorize dispatch in v2.40.
# OPENAI_API_KEY=
# GEMINI_API_KEY=
# XAI_API_KEY=
# ANTHROPIC_API_KEY=
"""


def create_directories() -> None:
    """Create runtime directories only under the ignored data root."""
    console.print("[bold]Creating local runtime directories...[/bold]")
    for path in RUNTIME_DIRECTORIES:
        path.mkdir(parents=True, exist_ok=True)
        console.print(f"  [dim]{path.as_posix()}/[/dim]")


def create_config_template() -> None:
    """Create a minimal local .env without overwriting operator state."""
    env_path = Path(".env")
    if env_path.exists():
        console.print("  [dim].env already exists; left unchanged[/dim]")
        return
    env_path.write_text(LOCAL_ENV_TEMPLATE, encoding="utf-8")
    console.print("  [success].env created with local paths and a $5 ceiling[/success]")


def check_dependencies() -> bool:
    """Check importable package names without importing provider clients."""
    required = {
        "aiofiles": "aiofiles",
        "dotenv": "python-dotenv",
        "pydantic": "pydantic",
    }
    missing = [package for module, package in required.items() if importlib.util.find_spec(module) is None]
    if missing:
        console.print("\n[warning]Missing required packages:[/warning]")
        for package in missing:
            console.print(f"  [error]{package}[/error]")
        console.print('\n[dim]Install with: uv pip install -e ".[dev,full]"[/dim]')
        return False
    print_success("Required local packages are installed")
    return True


def main() -> int:
    """Run a local, offline, idempotent setup."""
    print_header("Deepr Local Setup")
    try:
        create_directories()
        create_config_template()
        if not check_dependencies():
            print_error("Setup incomplete - install missing dependencies")
            return 1
    except Exception as exc:
        print_error(f"Setup failed: {exc}")
        return 1

    print_success("Local setup complete")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("  [dim]1.[/dim] Start Ollama and pull a local model")
    console.print("  [dim]2.[/dim] Run: deepr capacity")
    console.print("  [dim]3.[/dim] Run: deepr doctor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
