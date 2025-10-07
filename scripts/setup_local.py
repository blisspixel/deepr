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


def create_directories():
    """Create required local directories."""
    dirs = [
        "queue",
        "results",
        "logs",
        "uploads",
    ]

    print("Creating local directories...")
    for dir_name in dirs:
        path = Path(dir_name)
        path.mkdir(exist_ok=True)
        print(f"  ✓ {dir_name}/")


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

    print(f"  ✓ Database initialized at {db_path}")


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
DEEPR_MAX_COST_PER_JOB=10.00
DEEPR_MAX_COST_PER_DAY=100.00
DEEPR_MAX_COST_PER_MONTH=1000.00

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
        print(f"  ✓ .env.example created")

    if not env_path.exists():
        print("Creating .env file...")
        env_path.write_text(template)
        print(f"  ✓ .env created (EDIT THIS FILE with your API keys)")
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
        print("\nMissing required packages:")
        for pkg in missing:
            print(f"  ✗ {pkg}")
        print("\nInstall with: pip install -r requirements.txt")
        return False

    print("\n✓ All required packages installed")
    return True


def main():
    """Run local setup."""
    print("="*60)
    print("Deepr Local Environment Setup")
    print("="*60)
    print()

    try:
        create_directories()
        print()

        initialize_database()
        print()

        create_config_template()
        print()

        deps_ok = check_dependencies()

        print()
        print("="*60)
        if deps_ok:
            print("✓ Local setup complete!")
            print()
            print("Next steps:")
            print("  1. Edit .env with your API keys")
            print("  2. Run: python -m deepr.cli status")
            print("  3. Run: python -m deepr.cli research 'your prompt'")
        else:
            print("⚠ Setup incomplete - install missing dependencies")
            return 1
        print("="*60)

        return 0

    except Exception as e:
        print(f"\n✗ Setup failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
