"""Diagnostics command for troubleshooting Deepr configuration."""

import asyncio
import os
import tempfile
from pathlib import Path

import click

from deepr.cli.async_runner import run_async_command
from deepr.config import load_config


class DiagnosticCheck:
    """A single diagnostic check."""

    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category
        self.passed = False
        self.message = ""
        self.details: list[str] = []
        # Severity shown when this check does NOT pass: "error" is a real
        # problem; "warning" is advisory (e.g. a dated deprecation); "info" is
        # not a problem (an optional feature not configured, a first-run state).
        # Only "error" counts against the health summary, so a working setup
        # with optional pieces unset reads as healthy instead of crying wolf.
        self.failure_severity = "error"

    @property
    def severity(self) -> str:
        return "ok" if self.passed else self.failure_severity


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
        check.failure_severity = "info"
        check.message = "Not configured (optional)"
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
        check.failure_severity = "info"
        check.message = "Not configured (optional)"
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
        check.failure_severity = "info"
        check.message = "Not configured (optional)"
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
        check.failure_severity = "info"
        check.message = "Not configured (optional)"
        check.details.append("Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT in .env")
    checks.append(check)

    # Anthropic (Claude)
    check = DiagnosticCheck("Anthropic API Key", "API Keys")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key and anthropic_key != "your-anthropic-api-key":
        check.passed = True
        check.message = "Configured"
        check.details.append(f"Key: {anthropic_key[:8]}...{anthropic_key[-4:]}")
    else:
        check.failure_severity = "info"
        check.message = "Not configured (optional)"
        check.details.append("Set ANTHROPIC_API_KEY in .env")
    checks.append(check)

    # Any single provider is enough; the only real error is having none. Each
    # provider above is individually optional (info), so this is the check that
    # actually fails a keyless setup.
    summary = DiagnosticCheck("At least one provider configured", "API Keys")
    if any(c.passed for c in checks):
        summary.passed = True
        summary.message = "Yes"
    else:
        summary.message = "No provider keys found"
        summary.details.append("Add one of OPENAI / GEMINI / XAI / ANTHROPIC_API_KEY (run `deepr init`)")
    checks.append(summary)

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

    # Gemini (uses google-genai SDK, not the deprecated google.generativeai)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and gemini_key != "your-gemini-api-key":
        check = DiagnosticCheck("Gemini API Connection", "Connectivity")
        try:
            from google import genai

            client = genai.Client(api_key=gemini_key)
            # Simple test: list models (makes API call to verify connectivity + key)
            model_list = list(client.models.list())
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

        if not await asyncio.to_thread(db_path.exists):
            # First run: the queue DB is created on the first job. Not a problem.
            check.failure_severity = "info"
            check.message = "Not initialized yet (created on first job)"
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
        # "no such table" means the file exists but the schema has not been
        # created yet (also a first-run state), not a failure to fix.
        if "no such table" in str(e).lower():
            check.failure_severity = "info"
            check.message = "Not initialized yet (created on first job)"
        else:
            check.message = f"Cannot access: {str(e)[:50]}"
            check.details.append(str(e))
    checks.append(check)

    return checks


async def check_deprecated_models(config) -> list[DiagnosticCheck]:
    """Check if any configured default models are deprecated."""
    from deepr.config import AppConfig
    from deepr.routing.deprecation import check_deprecation

    checks = []

    try:
        app_config = AppConfig.from_env()
        models_to_check = {
            "Default Model": app_config.provider.default_model,
            "Deep Research Model": app_config.provider.deep_research_model,
        }

        for label, model in models_to_check.items():
            if not model:
                continue
            dep_entry = check_deprecation(model)
            if dep_entry:
                check = DiagnosticCheck(f"{label}: {model}", "Deprecated Models")
                check.passed = False
                # A dated sunset is a real deadline (warning); a deprecation
                # with no sunset is informational - the alias is still served
                # and the runtime deliberately does not warn on it, so doctor
                # should not flag it as a problem either.
                if dep_entry.sunset_date:
                    check.failure_severity = "warning"
                    check.message = f"Deprecated (retires {dep_entry.sunset_date})"
                else:
                    check.failure_severity = "info"
                    check.message = "Newer pinned version available (still served)"
                check.details.append(f"Successor: {dep_entry.new_model}")
                check.details.append(dep_entry.warning)
                checks.append(check)

        if not checks:
            check = DiagnosticCheck("Model Deprecation", "Deprecated Models")
            check.passed = True
            check.message = "No deprecated models in use"
            checks.append(check)

    except Exception as e:
        check = DiagnosticCheck("Model Deprecation", "Deprecated Models")
        check.message = f"Check failed: {str(e)[:50]}"
        check.details.append(str(e))
        checks.append(check)

    return checks


def _summarize(checks: list[DiagnosticCheck]) -> dict[str, int]:
    """Count checks by outcome. Only ``errors`` are real problems; ``warnings``
    are advisory and ``info`` (optional features, first-run state) are not."""
    return {
        "total": len(checks),
        "passed": sum(1 for c in checks if c.passed),
        "errors": sum(1 for c in checks if c.severity == "error"),
        "warnings": sum(1 for c in checks if c.severity == "warning"),
        "info": sum(1 for c in checks if c.severity == "info"),
    }


def print_checks(checks: list[DiagnosticCheck]):
    """Print diagnostic checks in a formatted way."""
    from deepr.cli.colors import console, get_symbol

    # Group by category
    categories: dict[str, list[DiagnosticCheck]] = {}
    for check in checks:
        if check.category not in categories:
            categories[check.category] = []
        categories[check.category].append(check)

    # Display style per severity. "info" is neutral (optional/first-run state),
    # not a failure - it must not read like a red error.
    style = {
        "ok": ("success", "green"),
        "warning": ("warning", "yellow"),
        "info": ("info", "dim"),
        "error": ("error", "red"),
    }

    # Print each category
    for category, category_checks in categories.items():
        console.print()
        console.print(f"[bold cyan]{category}[/bold cyan]")

        for check in category_checks:
            symbol_name, color = style.get(check.severity, ("error", "red"))
            symbol = get_symbol(symbol_name)
            console.print(f"  [{color}]{symbol}[/{color}] {check.name}: {check.message}")

            if check.details:
                for detail in check.details:
                    console.print(f"      [dim]{detail}[/dim]")

    # Summary: only real errors count against the bill of health. Warnings are
    # advisory; info items (optional features, first-run state) are not problems.
    counts = _summarize(checks)

    console.print()
    console.print(f"[bold]Summary:[/bold] {counts['passed']}/{counts['total']} checks passed")

    if counts["errors"]:
        console.print(
            f"\n[red]{get_symbol('error')}[/red] {counts['errors']} issue(s) need attention. See details above."
        )
    elif counts["warnings"]:
        console.print(
            f"\n[yellow]{get_symbol('warning')}[/yellow] No blocking issues; {counts['warnings']} advisory warning(s)."
        )
    else:
        console.print(f"\n[green]{get_symbol('success')}[/green] All good. Optional items above are not problems.")


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
        with click.progressbar(length=7, label="Running checks") as bar:
            all_checks.extend(await check_api_keys(config))
            bar.update(1)

            if not skip_connectivity:
                all_checks.extend(await check_provider_connectivity(config))
            bar.update(1)

            all_checks.extend(await check_filesystem())
            bar.update(1)

            all_checks.extend(check_storage_locations())
            bar.update(1)

            all_checks.extend(await check_database(config))
            bar.update(1)

            all_checks.extend(await check_deprecated_models(config))
            bar.update(1)

            all_checks.extend(check_native_instruments())
            bar.update(1)

        # Print results
        print_checks(all_checks)
        print_next_step(all_checks)

    # Run async checks
    run_async_command(run_diagnostics())


def print_next_step(checks: list[DiagnosticCheck]) -> None:
    """Closing guidance: the single next command for the user's current state.

    Complements ``deepr init`` - a keyless setup is pointed at the wizard
    rather than left at a bare pass/fail summary.
    """
    key_checks = [c for c in checks if c.category == "API Keys"]
    if not key_checks:
        return
    if not any(c.passed for c in key_checks):
        click.echo("\nNo provider keys detected. Run `deepr init` for guided setup")
        click.echo("(or add OPENAI_API_KEY / GEMINI_API_KEY / XAI_API_KEY / ANTHROPIC_API_KEY to .env).")
    else:
        click.echo('\nSetup looks good. Try: deepr research "Your question here" --auto')


def check_native_instruments() -> list[DiagnosticCheck]:
    """Lightweight check for auto-discovered first-party native instruments (Phase 2b)."""
    checks = []

    # Recon (the pilot first-class instrument)
    check = DiagnosticCheck("Recon (native domain intel)", "Native Instruments")
    try:
        from deepr.mcp.client.config_loader import discover_recon_profile

        profile = discover_recon_profile()
        if profile and profile.enabled:
            check.passed = True
            check.message = "Auto-discovered (first-class)"
            check.details.append("recon-tool MCP server available via `recon mcp`")
            check.details.append("Auto-probed in expert chat when domains appear (cost $0)")
        else:
            # Optional add-on; absence is not a problem.
            check.failure_severity = "info"
            check.message = "Not installed (optional)"
            check.details.append("Install with: pip install -U recon-tool")
            check.details.append("Enables zero-config passive recon for experts")
    except Exception as e:
        check.failure_severity = "info"
        check.message = "Probe error"
        check.details.append(str(e)[:60])
    checks.append(check)

    return checks


def check_storage_locations() -> list[DiagnosticCheck]:
    """Show where experts and research are stored (portable-data visibility).

    These are the artifacts that follow you across machines when DEEPR_DATA_DIR
    points at a synced folder (ADR 0004). Informational, never a failure.
    """
    from deepr.config import experts_root, load_config

    experts = DiagnosticCheck("Experts", "Storage")
    experts.passed = True
    experts.message = str(experts_root())
    experts.details.append("Set DEEPR_DATA_DIR (or DEEPR_EXPERTS_PATH) to a synced folder to share across machines")

    reports = DiagnosticCheck("Research reports", "Storage")
    reports.passed = True
    reports.message = str(load_config()["results_dir"])

    return [experts, reports]


if __name__ == "__main__":
    doctor()
