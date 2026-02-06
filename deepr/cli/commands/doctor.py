"""Diagnostics command for troubleshooting Deepr configuration."""

import asyncio
import os
import tempfile
from pathlib import Path

import click

from deepr.config import load_config


class DiagnosticCheck:
    """A single diagnostic check."""

    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category
        self.passed = False
        self.message = ""
        self.details = []


async def check_api_keys(config) -> list[DiagnosticCheck]:
    """Check if API keys are configured."""
    checks = []

    # OpenAI
    check = DiagnosticCheck("OpenAI API Key", "API Keys")
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and openai_key != "your-openai-api-key":
        check.passed = True
        check.message = "Configured"
        masked = openai_key[:8] + "..." + openai_key[-4:]
        check.details.append(f"Key: {masked}")
    else:
        check.message = "Not configured"
        check.details.append("Set OPENAI_API_KEY in .env")
    checks.append(check)

    # Gemini
    check = DiagnosticCheck("Gemini API Key", "API Keys")
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and gemini_key != "your-gemini-api-key":
        check.passed = True
        check.message = "Configured"
        masked = gemini_key[:8] + "..." + gemini_key[-4:]
        check.details.append(f"Key: {masked}")
    else:
        check.message = "Not configured"
        check.details.append("Set GEMINI_API_KEY in .env")
    checks.append(check)

    # xAI Grok
    check = DiagnosticCheck("xAI Grok API Key", "API Keys")
    xai_key = os.getenv("XAI_API_KEY")
    if xai_key and xai_key != "your-xai-api-key":
        check.passed = True
        check.message = "Configured"
        masked = xai_key[:8] + "..." + xai_key[-4:]
        check.details.append(f"Key: {masked}")
    else:
        check.message = "Not configured"
        check.details.append("Set XAI_API_KEY in .env")
    checks.append(check)

    # Azure
    check = DiagnosticCheck("Azure OpenAI Key", "API Keys")
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if azure_key and azure_key != "your-azure-key":
        check.passed = True
        check.message = "Configured"
        masked = azure_key[:8] + "..." + azure_key[-4:]
        check.details.append(f"Key: {masked}")
        if azure_endpoint:
            check.details.append(f"Endpoint: {azure_endpoint}")
    else:
        check.message = "Not configured"
        check.details.append("Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT in .env")
    checks.append(check)

    return checks


async def check_provider_connectivity(config) -> list[DiagnosticCheck]:
    """Test basic connectivity to configured providers."""
    checks = []

    # OpenAI
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and openai_key != "your-openai-api-key":
        check = DiagnosticCheck("OpenAI API Connection", "Connectivity")
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=openai_key)
            # Simple test: list models
            models = await client.models.list()
            check.passed = True
            check.message = "Connected successfully"
            check.details.append(f"Available models: {len(models.data)}")
        except Exception as e:
            check.message = f"Connection failed: {str(e)[:50]}"
            check.details.append(str(e))
        checks.append(check)

    # Gemini
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and gemini_key != "your-gemini-api-key":
        check = DiagnosticCheck("Gemini API Connection", "Connectivity")
        try:
            import google.generativeai as genai

            genai.configure(api_key=gemini_key)
            # Simple test: list models
            models = genai.list_models()
            model_list = list(models)
            check.passed = True
            check.message = "Connected successfully"
            check.details.append(f"Available models: {len(model_list)}")
        except Exception as e:
            check.message = f"Connection failed: {str(e)[:50]}"
            check.details.append(str(e))
        checks.append(check)

    # xAI Grok
    xai_key = os.getenv("XAI_API_KEY")
    if xai_key and xai_key != "your-xai-api-key":
        check = DiagnosticCheck("xAI Grok Connection", "Connectivity")
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=xai_key, base_url="https://api.x.ai/v1")
            # Simple test: list models
            models = await client.models.list()
            check.passed = True
            check.message = "Connected successfully"
            check.details.append(f"Available models: {len(models.data)}")
        except Exception as e:
            check.message = f"Connection failed: {str(e)[:50]}"
            check.details.append(str(e))
        checks.append(check)

    # Azure
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if azure_key and azure_key != "your-azure-key":
        check = DiagnosticCheck("Azure OpenAI Connection", "Connectivity")
        try:
            from openai import AsyncAzureOpenAI

            client = AsyncAzureOpenAI(api_key=azure_key, azure_endpoint=azure_endpoint, api_version="2024-10-21")
            # Azure doesn't support models.list() easily, so just mark as configured
            check.passed = True
            check.message = "Configured (connectivity test skipped)"
            check.details.append("Azure OpenAI client initialized")
        except Exception as e:
            check.message = f"Configuration error: {str(e)[:50]}"
            check.details.append(str(e))
        checks.append(check)

    return checks


async def check_filesystem() -> list[DiagnosticCheck]:
    """Check file system permissions."""
    checks = []

    # Check temp directory
    check = DiagnosticCheck("Temp Directory", "Filesystem")
    try:
        temp_dir = Path(tempfile.gettempdir())
        check.details.append(f"Path: {temp_dir}")

        # Test write
        test_file = temp_dir / "deepr_test.tmp"
        test_file.write_text("test")
        test_file.unlink()

        check.passed = True
        check.message = "Writable"
    except Exception as e:
        check.message = f"Cannot write: {str(e)[:50]}"
        check.details.append(str(e))
    checks.append(check)

    # Check current directory
    check = DiagnosticCheck("Current Directory", "Filesystem")
    try:
        cwd = Path.cwd()
        check.details.append(f"Path: {cwd}")

        # Test write
        test_file = cwd / ".deepr_test.tmp"
        test_file.write_text("test")
        test_file.unlink()

        check.passed = True
        check.message = "Writable"
    except Exception as e:
        check.message = f"Cannot write: {str(e)[:50]}"
        check.details.append(str(e))
    checks.append(check)

    # Check .deepr directory
    check = DiagnosticCheck(".deepr Directory", "Filesystem")
    try:
        home = Path.home()
        deepr_dir = home / ".deepr"
        check.details.append(f"Path: {deepr_dir}")

        if not deepr_dir.exists():
            deepr_dir.mkdir(parents=True)
            check.details.append("Created directory")

        # Test write
        test_file = deepr_dir / "test.tmp"
        test_file.write_text("test")
        test_file.unlink()

        check.passed = True
        check.message = "Writable"
    except Exception as e:
        check.message = f"Cannot access: {str(e)[:50]}"
        check.details.append(str(e))
    checks.append(check)

    return checks


async def check_database(config) -> list[DiagnosticCheck]:
    """Check database connectivity."""
    checks = []

    check = DiagnosticCheck("Job Database", "Database")
    try:
        import sqlite3

        # Use queue_db_path from config, or default
        db_path = Path(config.get("queue_db_path", "queue/research_queue.db"))
        check.details.append(f"Path: {db_path}")

        if not db_path.exists():
            check.message = "Database not initialized"
            check.details.append("Run 'deepr jobs list' to initialize")
        else:
            # Test connection
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM jobs")
            count = cursor.fetchone()[0]
            conn.close()

            check.passed = True
            check.message = f"Connected ({count} jobs)"
            check.details.append(f"Total jobs: {count}")
    except Exception as e:
        check.message = f"Cannot access: {str(e)[:50]}"
        check.details.append(str(e))
    checks.append(check)

    return checks


def print_checks(checks: list[DiagnosticCheck]):
    """Print diagnostic checks in a formatted way."""
    from deepr.cli.colors import console, get_symbol

    # Group by category
    categories: dict[str, list[DiagnosticCheck]] = {}
    for check in checks:
        if check.category not in categories:
            categories[check.category] = []
        categories[check.category].append(check)

    # Print each category
    for category, category_checks in categories.items():
        console.print()
        console.print(f"[bold cyan]{category}[/bold cyan]")

        for check in category_checks:
            symbol = get_symbol("success") if check.passed else get_symbol("error")
            color = "green" if check.passed else "red"

            console.print(f"  [{color}]{symbol}[/{color}] {check.name}: {check.message}")

            if check.details:
                for detail in check.details:
                    console.print(f"      [dim]{detail}[/dim]")

    # Summary
    total = len(checks)
    passed = sum(1 for c in checks if c.passed)
    failed = total - passed

    console.print()
    console.print(f"[bold]Summary:[/bold] {passed}/{total} checks passed")

    if failed > 0:
        symbol = get_symbol("warning")
        console.print(f"\n[yellow]{symbol}[/yellow] {failed} issue(s) found. See details above.")
    else:
        symbol = get_symbol("success")
        console.print(f"\n[green]{symbol}[/green] All checks passed!")


@click.command()
@click.option("--skip-connectivity", is_flag=True, help="Skip network connectivity tests")
def doctor(skip_connectivity: bool):
    """Run diagnostics to check Deepr configuration and connectivity.

    Checks:
    - Provider API keys are configured
    - Network connectivity to providers (unless --skip-connectivity)
    - File system read/write permissions
    - Database access

    Examples:
        deepr doctor
        deepr doctor --skip-connectivity
    """
    click.echo("Running Deepr diagnostics...\n")

    async def run_diagnostics():
        all_checks = []

        # Load config
        try:
            config = load_config()
        except Exception as e:
            click.echo(f"Error loading configuration: {e}")
            return

        # Run all checks
        with click.progressbar(length=4, label="Running checks") as bar:
            all_checks.extend(await check_api_keys(config))
            bar.update(1)

            if not skip_connectivity:
                all_checks.extend(await check_provider_connectivity(config))
            bar.update(1)

            all_checks.extend(await check_filesystem())
            bar.update(1)

            all_checks.extend(await check_database(config))
            bar.update(1)

        # Print results
        print_checks(all_checks)

    # Run async checks
    asyncio.run(run_diagnostics())


if __name__ == "__main__":
    doctor()
