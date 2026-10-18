"""Diagnostics command for troubleshooting Deepr configuration."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

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
        self.unverified = False
        self.visible = True

    @property
    def severity(self) -> str:
        return "ok" if self.passed else self.failure_severity


async def check_local_ollama(*, skip_connectivity: bool) -> list[DiagnosticCheck]:
    """Report owned generation proof without treating skipped checks as ready."""
    check = DiagnosticCheck("Local Ollama generation", "Local Capacity")
    if skip_connectivity:
        check.failure_severity = "info"
        check.unverified = True
        check.message = "Unverified: provider connectivity checks were skipped"
        check.details.append("Run `deepr capacity` for read-only local cloud/model proof; it performs no inference.")
        return [check]
    from deepr.backends.capacity import observe_local_ollama_generation

    proof = await asyncio.to_thread(observe_local_ollama_generation)
    check.passed = proof.status == "ready"
    check.message = f"{proof.status}: {proof.detail}"
    check.details.append(f"Cloud disabled: {proof.cloud_disabled}; source: {proof.cloud_source or 'unknown'}")
    if proof.status == "ready":
        from deepr.backends.drm import observe_ollama_residency

        resident = await asyncio.to_thread(observe_ollama_residency)
        for model in resident:
            check.details.append(
                f"{model['model']}: {model['gpu_residency_percent']:g}% GPU residency reported by Ollama /api/ps"
            )
        if not resident:
            check.details.append(
                "No measured running-model GPU residency is available; execution placement is unknown."
            )
    if proof.reason == "unreachable" and not os.getenv("OLLAMA_HOST"):
        check.failure_severity = "info"
        check.unverified = True
    return [check]


def check_configuration_sources() -> list[DiagnosticCheck]:
    """Name the files read at startup without probing providers or showing keys."""
    from deepr.config import configuration_source_summary, load_configuration_environment

    observed = load_configuration_environment()
    check = DiagnosticCheck("Configuration files", "Configuration")
    check.passed = True
    check.message = configuration_source_summary()
    check.details.extend(f"Not found: {path}" for path in observed.missing_files)
    check.details.extend(f"{name}: {source}" for name, source in sorted(observed.variables.items()))
    return [check]


_PROVIDER_CHECKS = (
    ("OpenAI", "openai"),
    ("Gemini", "gemini"),
    ("xAI Grok", "xai"),
    ("Anthropic", "anthropic"),
    ("Azure OpenAI", "azure"),
    ("OpenRouter", "openrouter"),
)


async def check_api_keys(config) -> list[DiagnosticCheck]:
    """Inspect stored credentials without releasing keys or constructing clients."""
    from deepr.cli.commands.provider_factory import credential_presence

    checks = []
    for label, provider in _PROVIDER_CHECKS:
        present, variable = credential_presence(provider)
        check = DiagnosticCheck(f"{label} API Key" if provider != "azure" else "Azure OpenAI Key", "API Keys")
        check.failure_severity = "info"
        check.passed = present
        check.visible = present
        check.message = (
            "Stored credential detected (validity and authority unverified)" if present else "Not configured (optional)"
        )
        if present:
            check.details.append(f"Source: stored/process/quarantined {variable}; no key was released or checked")
        checks.append(check)
    summary = DiagnosticCheck("Metered API capacity", "API Keys")
    summary.failure_severity = "info"
    summary.passed = any(check.passed for check in checks)
    summary.message = (
        "Stored credentials detected; provider execution and spend gates still apply"
        if summary.passed
        else "No metered API keys; inspect local and explicit plan capacity with deepr capacity"
    )
    checks.append(summary)
    return checks


async def check_provider_connectivity(config) -> list[DiagnosticCheck]:
    """Report configured providers without making external metadata requests."""
    from deepr.cli.commands.provider_factory import credential_presence

    checks = []
    for label, provider in _PROVIDER_CHECKS:
        if not credential_presence(provider)[0]:
            continue
        check = DiagnosticCheck(
            f"{label} API Connectivity" if provider != "azure" else "Azure OpenAI Connectivity", "Connectivity"
        )
        check.failure_severity = "info"
        check.unverified = True
        check.message = "Configured; live metadata request blocked"
        check.details.append(
            "External connectivity is not tested because Deepr cannot prove endpoint or proxy marginal cost"
        )
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
    """Check queue connectivity and surface stale lifecycle candidates."""
    checks: list[DiagnosticCheck] = []

    check = DiagnosticCheck("Job Database", "Database")
    try:
        from deepr.queue.diagnostics import inspect_queue

        # Use queue_db_path from config, or default
        db_path = Path(config.get("queue_db_path", "queue/research_queue.db"))
        check.details.append(f"Path: {db_path}")

        diagnostics = await asyncio.to_thread(inspect_queue, db_path)
        if not diagnostics.initialized:
            check.failure_severity = "info"
            check.message = "Not initialized yet (created on first job)"
        else:
            check.passed = True
            check.message = f"Connected ({diagnostics.total} jobs)"
            check.details.append(f"Total jobs: {diagnostics.total}")

            lifecycle = DiagnosticCheck("Queue Lifecycle", "Database")
            stale = diagnostics.stale_queued_candidates
            if stale:
                lifecycle.failure_severity = "warning"
                lifecycle.message = f"{stale} stale queued candidate(s)"
                lifecycle.details.append("Queued with zero attempts for more than 24 hours; no rows were changed")
                lifecycle.details.append(
                    f"Reservation metadata references: {diagnostics.stale_with_reservation_metadata}"
                )
                if diagnostics.oldest_stale_submitted_at:
                    lifecycle.details.append(f"Oldest submitted: {diagnostics.oldest_stale_submitted_at}")
                lifecycle.details.append("Inspect job and reservation state before cancelling anything")
                lifecycle.details.append("List: deepr jobs list --status queued")
                lifecycle.details.append("Cancel one job only after inspection: deepr jobs cancel <job_id>")
                lifecycle.details.append("Spend holds may need: deepr costs doctor (matched / disposed / unexplained)")
            else:
                lifecycle.passed = True
                lifecycle.message = "No queued zero-attempt rows older than 24 hours"
            checks.append(lifecycle)
    except Exception as e:
        check.message = f"Cannot access: {str(e)[:50]}"
        check.details.append(str(e))
    checks.insert(0, check)

    return checks


async def check_deprecated_models(config) -> list[DiagnosticCheck]:
    """Check if any configured default models are deprecated."""
    from deepr.config import AppConfig
    from deepr.routing.deprecation import check_deprecation

    checks = []

    try:
        app_config = AppConfig.from_env()
        models_to_check = {
            "Default Model": (app_config.provider.default_provider, app_config.provider.default_model),
            "Deep Research Model": (
                app_config.provider.deep_research_provider,
                app_config.provider.deep_research_model,
            ),
        }

        from deepr.cli.commands.provider_factory import credential_presence

        for label, (provider, model) in models_to_check.items():
            if not model or not credential_presence(provider)[0]:
                continue
            from deepr.providers.registry_pricing import get_resolved_model_capability

            capability = get_resolved_model_capability(model)
            if capability and capability.access_note:
                check = DiagnosticCheck(f"{label}: {model}", "Model Access")
                check.passed = False
                check.failure_severity = "warning"
                check.message = "Prior-user access only; account eligibility unverified"
                check.details.append(capability.access_note)
                checks.append(check)
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
        "required": sum(1 for c in checks if c.failure_severity == "error" and not c.unverified),
        "required_passed": sum(1 for c in checks if c.failure_severity == "error" and c.passed and not c.unverified),
        "advisory": sum(1 for c in checks if c.failure_severity == "warning" and not c.unverified),
        "optional": sum(1 for c in checks if c.failure_severity == "info" and not c.unverified),
        "unverified": sum(1 for c in checks if c.unverified),
    }


def _capacity_summary(checks: list[DiagnosticCheck]) -> dict[str, str | bool]:
    local = next((check for check in checks if check.name == "Local Ollama generation"), None)
    state = "ready" if local and local.passed else "unverified" if local is None or local.unverified else "unavailable"
    headline = (
        "Local capacity proof is ready; generation has not been exercised by doctor."
        if state == "ready"
        else f"Executable capacity not established. Local generation: {state}."
    )
    return {"local_capacity_proof": state, "generation_tested": False, "headline": headline}


def _check_payload(check: DiagnosticCheck) -> dict[str, object]:
    return {
        "name": check.name,
        "category": check.category,
        "passed": check.passed,
        "severity": check.severity,
        "failure_severity": check.failure_severity,
        "unverified": check.unverified,
        "message": check.message,
        "details": check.details,
        "visible": check.visible,
    }


def print_checks(checks: list[DiagnosticCheck], *, show_all: bool = False):
    """Print diagnostic checks in a formatted way."""
    from deepr.cli.colors import console, get_symbol

    console.print(_capacity_summary(checks)["headline"])

    # Group by category
    categories: dict[str, list[DiagnosticCheck]] = {}
    for check in checks:
        if not show_all and (
            not check.visible
            or (check.failure_severity == "info" and check.category not in {"API Keys", "Local Capacity"})
        ):
            continue
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
    console.print(
        f"[bold]Summary:[/bold] {counts['required_passed']}/{counts['required']} required checks passed; "
        f"{counts['advisory']} advisory, {counts['optional']} optional, {counts['unverified']} unverified"
    )

    if counts["errors"]:
        console.print(
            f"\n[red]{get_symbol('error')}[/red] {counts['errors']} issue(s) need attention. See details above."
        )
    elif counts["warnings"]:
        console.print(
            f"\n[yellow]{get_symbol('warning')}[/yellow] No blocking issues; {counts['warnings']} advisory warning(s)."
        )
    else:
        unchecked = counts["unverified"] > 0
        message = (
            "No blocking configuration issues; skipped or blocked checks remain unverified."
            if unchecked
            else "Required configuration checks passed; optional items are not blocking."
        )
        console.print(f"\n{message}")


def diagnostic_report(checks: list[DiagnosticCheck]) -> dict[str, Any]:
    """One diagnostic result, independent of progress and presentation."""
    from deepr.cli.output import OperationResult

    counts = _summarize(checks)
    payload = {
        "schema_version": "deepr-doctor-v1",
        "status": "error" if counts["errors"] else "success",
        "counts": counts,
        "capacity": _capacity_summary(checks),
        "checks": [_check_payload(check) for check in checks],
    }
    if counts["errors"]:
        failure = OperationResult(
            False,
            0,
            0,
            error="Diagnostics found one or more errors.",
            error_code="DOCTOR_CHECKS_FAILED",
            category="config",
        )
        payload.update(failure.error_payload(hint="deepr doctor --all"))
    return payload


@click.command()
@click.option("--skip-connectivity", is_flag=True, help="Skip all provider network calls (recommended first run)")
@click.option("--json", "json_output", is_flag=True, help="Emit diagnostic checks and counts as JSON.")
@click.option("--all", "show_all", is_flag=True, help="Include optional integration details in the human view.")
def doctor(skip_connectivity: bool, json_output: bool, show_all: bool):
    """Run diagnostics to check Deepr configuration and connectivity.

    Checks:
    - Provider API keys are configured
    - Owned local Ollama cloud/model proof (unless --skip-connectivity)
    - File system read/write permissions
    - Database access

    Examples:
        deepr doctor --skip-connectivity
        deepr doctor  # read-only local proof; external provider calls remain blocked
    """
    if not json_output:
        click.echo("Running Deepr diagnostics...\n")
    if skip_connectivity and not json_output:
        click.echo("Offline mode: provider connectivity checks are skipped.\n")

    async def run_diagnostics() -> list[DiagnosticCheck]:
        all_checks = []

        # Load config
        try:
            config = load_config()
            all_checks.extend(check_configuration_sources())
        except Exception as exc:
            raise click.ClickException("Could not load configuration. Review local settings and retry.") from exc

        # Run all checks
        with click.progressbar(length=10, label="Running checks", file=click.get_text_stream("stderr")) as bar:
            all_checks.extend(await check_api_keys(config))
            bar.update(1)

            all_checks.extend(await check_local_ollama(skip_connectivity=skip_connectivity))
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

            all_checks.extend(check_spend_integrity())
            bar.update(1)

            all_checks.extend(check_mcp_conformance())
            all_checks.extend(check_mcp_host_wiring())
            bar.update(1)

        return all_checks

    from deepr.cli.output import OperationResult

    try:
        checks = run_async_command(run_diagnostics())
    except click.ClickException as exc:
        if not json_output:
            raise
        failure = OperationResult(False, 0, 0, error=str(exc), error_code="DOCTOR_CONFIG_FAILED", category="config")
        click.echo(json.dumps(failure.error_payload(hint="deepr config show")))
        raise click.exceptions.Exit(1) from exc
    payload = diagnostic_report(checks)
    counts = payload["counts"]
    if json_output:
        click.echo(json.dumps(payload, indent=2))
    else:
        print_checks(checks, show_all=show_all)
        print_next_step(checks)
    if counts["errors"]:
        error = (
            click.exceptions.Exit(1) if json_output else click.ClickException("Diagnostics found one or more errors.")
        )
        raise error


def print_next_step(checks: list[DiagnosticCheck]) -> None:
    """Closing guidance: the single next command for the user's current state.

    Complements ``deepr init`` by deriving the next no-spend action from the
    strongest diagnostic evidence available.
    """
    errors = [check for check in checks if check.severity == "error"]
    stale_queue = any(check.name == "Queue Lifecycle" and check.severity == "warning" for check in checks)
    if errors:
        click.echo("\nResolve the ERROR checks above before starting new work.")
        if any(check.category == "Connectivity" for check in errors):
            click.echo("For an offline-only diagnosis, rerun `deepr doctor --skip-connectivity`.")
        if stale_queue:
            _print_stale_queue_guidance()
        return
    if stale_queue:
        _print_stale_queue_guidance()
        return
    if any(check.severity == "warning" for check in checks):
        click.echo("\nReview the WARN checks above before starting new work.")
        return

    metered = next((check for check in checks if check.name == "Metered API capacity"), None)
    if metered is None:
        return
    if not metered.passed:
        click.echo("\nNo metered API keys are configured. Local and plan workflows require their own capacity proof.")
        click.echo("Next: deepr capacity")
    else:
        click.echo(
            "\nNo blocking configuration errors. Execution proof remains separate. "
            'Preview a route: deepr research "Your question here" --preview'
        )


def _print_stale_queue_guidance() -> None:
    click.echo("\nReview stale queued work before starting more jobs:")
    click.echo("  deepr jobs list --status queued")
    click.echo("  deepr costs doctor")


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

    checks.append(_check_local_gpu_headroom())
    return checks


def _check_local_gpu_headroom() -> DiagnosticCheck:
    """Report GPU memory and what is holding it ($0, read-only).

    Free VRAM decides which local model can run entirely on GPU. A card whose
    memory is largely held by desktop applications silently forces a weaker
    model or a CPU spill, and neither is visible from Deepr's output otherwise.
    Advisory only: a busy desktop is a normal state, not a fault.
    """
    check = DiagnosticCheck("Local GPU headroom", "Native Instruments")
    check.failure_severity = "info"
    try:
        from deepr.backends.local_capacity import probe_local_gpu_occupancy
        from deepr.backends.vram_report import collect_vram_report

        report = collect_vram_report()
        occupancy = probe_local_gpu_occupancy()
        check.details.append(occupancy.detail)
        if report.total_bytes <= 0:
            check.message = (
                f"{report.gpu_name}: memory unknown"
                if report.gpu_name
                else "GPU memory measurement unavailable (optional)"
            )
            check.details.append("Execution placement is unknown; absent NVIDIA support does not imply CPU execution.")
            if report.detail:
                check.details.append(report.detail)
            return check

        check.passed = True
        free_gb = report.free_bytes / 1e9
        check.message = f"{free_gb:.1f} GB free of {report.total_bytes / 1e9:.1f} GB"
        if report.processes:
            check.details.append(
                f"{len(report.processes)} process(es) attached, holding {report.used_bytes / 1e9:.1f} GB."
            )
        candidates = report.reclaimable_candidates
        if candidates and report.used_bytes > 2_000_000_000:
            check.details.append("Closing these would return VRAM: " + ", ".join(candidates[:6]))
        check.details.append(
            "Dedicated VRAM and shared system memory are distinct; use measured Ollama residency for model placement."
            if report.shared_memory
            else "Free VRAM helps estimate model fit; running-model placement requires Ollama residency evidence."
        )
        if report.detail:
            check.details.append(report.detail)
    except Exception as e:
        check.message = "Probe error"
        check.details.append(str(e)[:60])
    return check


def check_mcp_conformance() -> list[DiagnosticCheck]:
    """Offline dual-era MCP host-interop posture ($0, no network, no model)."""
    check = DiagnosticCheck("MCP offline conformance", "MCP")
    try:
        from deepr.mcp.conformance import run_offline_mcp_conformance

        report = run_offline_mcp_conformance()
        payload = report.to_dict()
        summary = payload.get("summary") if isinstance(payload, dict) else {}
        protocol = payload.get("protocol") if isinstance(payload, dict) else {}
        failed = summary.get("failed_checks") if isinstance(summary, dict) else []
        modern = protocol.get("modern", "?") if isinstance(protocol, dict) else "?"
        check_count = (
            summary.get("check_count", len(report.checks)) if isinstance(summary, dict) else len(report.checks)
        )
        if report.ok:
            check.passed = True
            check.message = f"ok ({check_count} checks; modern {modern})"
            check.details.append("Run: deepr mcp conformance --json")
            check.details.append("No network, no model, $0; form and side-effect posture only")
        else:
            check.message = f"failed: {', '.join(failed) if failed else 'unknown'}"
            check.details.append("Run: deepr mcp conformance --json")
            for item in report.checks:
                if item.status != "passed":
                    check.details.append(f"{item.name}: {item.detail}")
    except Exception as exc:
        check.message = f"probe error: {type(exc).__name__}"
        check.details.append(str(exc)[:120])
        check.details.append("Run: deepr mcp conformance --json")
    return [check]


def check_mcp_host_wiring() -> list[DiagnosticCheck]:
    """Project host wiring for coding agents (stdio MCP, $0, no network)."""
    import shutil
    from pathlib import Path

    check = DiagnosticCheck("MCP host project wiring", "MCP")
    try:
        from deepr.mcp.host_install import probe_project_mcp_json

        probe = probe_project_mcp_json(Path.cwd())
        claude = shutil.which("claude")
        if probe.get("has_server"):
            check.passed = True
            check.message = f"project .mcp.json has deepr ({probe.get('path')})"
            check.details.append("Restart host session after config changes so tools load")
            check.details.append("Verify: claude mcp list  (expect deepr Connected)")
        elif probe.get("present"):
            check.message = "project .mcp.json present but deepr server missing"
            check.details.append(str(probe.get("detail")))
            check.details.append("Run: deepr mcp install-host --project .")
        else:
            check.message = "no project .mcp.json with deepr"
            check.details.append("Coding hosts need install + session restart, not only a pasted brief")
            check.details.append("Run: deepr mcp install-host --project .")
            check.details.append("Then: deepr mcp host-brief")
        if claude:
            check.details.append(f"claude CLI on PATH: {claude}")
        else:
            check.details.append("claude CLI not on PATH; .mcp.json still usable by hosts that read it")
        # Advisory: missing host wiring is not a broken Deepr core.
        if not check.passed:
            check.passed = True
            check.message = f"advisory: {check.message}"
    except Exception as exc:
        check.passed = True
        check.message = f"advisory probe error: {type(exc).__name__}"
        check.details.append(str(exc)[:120])
    return [check]


def check_storage_locations() -> list[DiagnosticCheck]:
    """Show where experts and research are stored (portable-data visibility).

    These artifacts can follow a user across machines when DEEPR_DATA_DIR
    points at a synced folder (ADR 0004). Generic file sync is safe only for
    sequential device use; it is not a concurrent-write protocol.
    """
    from deepr.config import experts_root, load_config

    experts = DiagnosticCheck("Experts", "Storage")
    experts.passed = True
    experts.message = str(experts_root().expanduser().resolve())
    experts.details.append("Set DEEPR_DATA_DIR (or DEEPR_EXPERTS_PATH) to move portable state across machines")
    experts.details.append("A synced DEEPR_DATA_DIR includes runtime state; stop Deepr services before switching")
    experts.details.append("Use one writer at a time and wait for sync to finish before switching devices")

    reports = DiagnosticCheck("Research reports", "Storage")
    reports.passed = True
    reports.message = str(Path(load_config()["results_dir"]).expanduser().resolve())

    return [experts, reports]


if __name__ == "__main__":
    doctor()


def check_spend_integrity() -> list[DiagnosticCheck]:
    """Spend truth checks: the display, the gate, and the disk must agree.

    A $37.79 campaign once ran while the budget display showed $0.00 (the
    session counter never saw spend from other entry points) and none of its
    artifacts survived. These checks make both failure modes loud in the one
    command people actually run when something feels off.
    """
    checks: list[DiagnosticCheck] = []

    # 1. Ledger-reconciled month spend vs the configured monthly budget.
    check = DiagnosticCheck("Monthly spend vs budget", "Spend")
    try:
        from deepr.cli.commands.budget import _ledger_month_spend, load_budget_config

        config = load_budget_config()
        limit = float(config.get("monthly_limit", 0) or 0)
        counter = float(config.get("monthly_spending", 0.0) or 0.0)
        ledger = _ledger_month_spend()
        if ledger is None:
            check.passed = False
            check.message = "Canonical cost ledger could not be read; real spend is unverifiable"
            check.details.append("Metered auto-approval fails closed until the ledger is readable")
        else:
            spent = max(counter, ledger)
            if spent > limit:
                check.passed = False
                check.message = f"OVER BUDGET: ${spent:.2f} spent against a ${limit:.2f}/month budget"
                check.details.append(
                    "Metered dispatch should be blocked; verify with a preview before trusting any -y run"
                )
            else:
                check.passed = True
                check.message = f"${spent:.2f} spent this month" + (f" of ${limit:.2f} budget" if limit > 0 else "")
            if ledger - counter > 0.01:
                check.details.append(
                    f"${ledger - counter:.2f} was recorded by other entry points and never hit the session counter; "
                    "the ledger is canonical"
                )
    except Exception as exc:
        check.passed = False
        check.message = f"Could not reconcile spend: {exc}"
    checks.append(check)

    # 2. Unexplained spend: settled money with no report and no disposition.
    check = DiagnosticCheck("Paid artifacts on disk", "Spend")
    try:
        from datetime import UTC, datetime, timedelta
        from pathlib import Path

        from deepr.cli.commands.costs import _doctor_classify
        from deepr.observability.cost_ledger import CostLedger
        from deepr.observability.spend_dispositions import latest_dispositions_by_event_key

        root = Path(load_config()["results_dir"])
        dir_names = [d.name for d in root.iterdir() if d.is_dir()] if root.exists() else []
        cutoff = datetime.now(UTC) - timedelta(days=45)
        events = CostLedger().with_locked_accounting_events(list)
        matched, disposed, unexplained = _doctor_classify(
            events,
            dir_names,
            cutoff,
            dispositions_by_key=latest_dispositions_by_event_key(),
        )
        unexplained_total = sum(e["cost_usd"] for e in unexplained)
        disposed_total = sum(e["cost_usd"] for e in disposed)
        matched_total = sum(e["cost_usd"] for e in matched)
        if unexplained_total > 0.005:
            check.passed = False
            check.message = (
                f"${unexplained_total:.2f} of settled spend is unexplained (no artifact and no disposition, 45 days)"
            )
            check.details.append("Run: deepr costs doctor")
            check.details.append("Investigate: deepr costs dispose-unexplained")
        else:
            check.passed = True
            check.message = (
                f"No unexplained spend (${matched_total:.2f} matched, ${disposed_total:.2f} disposed, 45 days)"
            )
    except Exception as exc:
        check.passed = False
        check.message = f"Artifact accounting state is UNKNOWN: {exc}"
        check.details.append("Paid API dispatch must remain blocked until the canonical ledger is readable")
    checks.append(check)

    return checks
