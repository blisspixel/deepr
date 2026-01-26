#!/usr/bin/env python3
"""
Local Environment Setup Script

Sets up the local development environment for Deepr:
- Creates necessary directories
- Initializes SQLite queue database
- Creates default configuration
- Validates Python dependencies
"""

import sys
from pathlib import Path
import sqlite3
import json

# Add parent directory to path to import deepr modules
sys.path.insert(0, str(Path(__file__).parent.parent))
from deepr.cli.colors import console, print_header, print_success, print_error, print_warning


def create_directories():
    """Create required local directories."""
    dirs = [
        "queue",
        "results",
        "logs",
        "uploads",
    ]

    console.print("[bold]Creating local directories...[/bold]")
    for dir_name in dirs:
        path = Path(dir_name)
        path.mkdir(exist_ok=True)
        console.print(f"  [dim]{dir_name}/[/dim]")


def initialize_database():
    """Initialize SQLite queue database."""
    db_path = Path("queue/research_queue.db")

    if db_path.exists():
        response = input(f"Database already exists at {db_path}. Recreate? (y/N): ")
        if response.lower() != 'y':
            print("  Skipping database initialization")
            return

    print("Initializing SQLite database...")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            status TEXT NOT NULL,
            priority INTEGER DEFAULT 1,
            model TEXT,
            enable_web_search INTEGER DEFAULT 1,
            file_ids TEXT,
            config TEXT,
            results TEXT,
            estimated_cost REAL,
            actual_cost REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            claimed_by TEXT,
            claimed_at TEXT
        )
    """)

    # Create indices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_priority ON jobs(priority DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_created ON jobs(created_at)")

    conn.commit()
    conn.close()

    console.print(f"  [success]Database initialized at {db_path}[/success]")


def create_config_template():
    """Create .env template if it doesn't exist."""
    env_path = Path(".env")
    env_example_path = Path(".env.example")

    template = """# Deepr Local Configuration

# Provider Configuration
DEEPR_PROVIDER=openai
# DEEPR_PROVIDER=azure

# OpenAI Configuration (if using openai provider)
OPENAI_API_KEY=your_openai_api_key_here

# Azure Configuration (if using azure provider)
# AZURE_OPENAI_API_KEY=your_azure_key_here
# AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
# AZURE_OPENAI_API_VERSION=2024-05-01-preview

# Storage Configuration
DEEPR_STORAGE=local
# DEEPR_STORAGE=blob

# Queue Configuration
DEEPR_QUEUE=local
# DEEPR_QUEUE=azure

# Cost Limits (USD)
DEEPR_MAX_COST_PER_JOB=5.00
DEEPR_MAX_COST_PER_DAY=25.00
DEEPR_MAX_COST_PER_MONTH=200.00

# Model Configuration
DEEPR_DEFAULT_MODEL=o4-mini-deep-research
DEEPR_ENABLE_WEB_SEARCH=true

# Local Paths
DEEPR_QUEUE_DB_PATH=queue/research_queue.db
DEEPR_RESULTS_DIR=results
DEEPR_UPLOADS_DIR=uploads
"""

    if not env_example_path.exists():
        print("Creating .env.example template...")
        env_example_path.write_text(template)
        console.print("  [success].env.example created[/success]")

    if not env_path.exists():
        print("Creating .env file...")
        env_path.write_text(template)
        console.print("  [success].env created[/success] [dim](EDIT THIS FILE with your API keys)[/dim]")
    else:
        print("  .env already exists (not overwriting)")


def check_dependencies():
    """Check if required Python packages are installed."""
    required = [
        "openai",
        "pydantic",
        "python-dotenv",
        "aiofiles",
    ]

    missing = []
    for package in required:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing.append(package)

    if missing:
        console.print("\n[warning]Missing required packages:[/warning]")
        for pkg in missing:
            console.print(f"  [error]{pkg}[/error]")
        console.print("\n[dim]Install with: pip install -r requirements.txt[/dim]")
        return False

    print_success("All required packages installed")
    return True


def main():
    """Run local setup."""
    print_header("Deepr Local Setup")

    try:
        create_directories()
        print()

        initialize_database()
        print()

        create_config_template()
        print()

        deps_ok = check_dependencies()

        print()
        if deps_ok:
            print_success("Local setup complete!")
            console.print()
            console.print("[bold]Next steps:[/bold]")
            console.print("  [dim]1.[/dim] Edit .env with your API keys")
            console.print("  [dim]2.[/dim] Run: python -m deepr.cli status")
            console.print("  [dim]3.[/dim] Run: python -m deepr.cli research 'your prompt'")
        else:
            print_error("Setup incomplete - install missing dependencies")
            return 1

        return 0

    except Exception as e:
        print_error(f"Setup failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
