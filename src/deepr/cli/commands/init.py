"""`deepr init` - guided first-run setup.

Detects provider keys, creates or patches the selected per-user configuration
file, sets a budget ceiling, and prints safe next commands. Explicit project
configuration uses DEEPR_ENV_FILE or --local-env.

Security: API keys are entered through hidden prompts, never echoed, and only
ever written to the selected private ``.env``. ``--yes`` runs
non-interactively (no secret prompts) so the command is safe in scripts and CI.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

import click

from deepr.cli.colors import console, print_next, print_section_header, print_success
from deepr.config import (
    configuration_env_path,
    ensure_configuration_env_file,
    read_configuration_env_file,
    upsert_configuration_env_file,
)

# Provider label, env var, and where to get a key. Order is the recommended
# setup order (cheapest-to-validate first); mirrors README + doctor.
_PROVIDERS: list[tuple[str, str, str]] = [
    ("Gemini", "GEMINI_API_KEY", "https://aistudio.google.com/app/apikey"),
    ("OpenAI", "OPENAI_API_KEY", "https://platform.openai.com/api-keys"),
    ("xAI Grok", "XAI_API_KEY", "https://console.x.ai/"),
    ("Anthropic", "ANTHROPIC_API_KEY", "https://console.anthropic.com/settings/keys"),
]

# Canonical budget env vars (deepr/config.py reads these).
_BUDGET_JOB = "DEEPR_MAX_COST_PER_JOB"
_BUDGET_DAY = "DEEPR_MAX_COST_PER_DAY"
_BUDGET_MONTH = "DEEPR_MAX_COST_PER_MONTH"
_DEFAULT_JOB_BUDGET = 1.0
_DEFAULT_DAY_BUDGET = 2.0
_DEFAULT_MONTH_BUDGET = 5.0

# Data-location env vars (ADR 0004). Experts and reports receive explicit
# children, while DEEPR_DATA_DIR also roots operational runtime artifacts.
# A synced root therefore requires sequential use across all Deepr services.
_DATA_DIR = "DEEPR_DATA_DIR"
_EXPERTS_PATH = "DEEPR_EXPERTS_PATH"
_REPORTS_PATH = "DEEPR_REPORTS_PATH"


def _resolve_data_dir_updates(env_file: dict[str, str], *, yes: bool, data_dir: str | None) -> dict[str, str]:
    """Decide data-location env updates for a relocatable Deepr data root.

    A chosen directory sets DEEPR_DATA_DIR plus explicit experts/reports
    subpaths so all three roots follow it. Blank input preserves the split
    defaults: experts under ~/.deepr/experts, reports under data/reports, and
    operational state under data. Never overwrite an existing DEEPR_DATA_DIR
    silently.
    """
    chosen = data_dir
    if chosen is None and not yes and not env_file.get(_DATA_DIR):
        entered = click.prompt(
            "\nDeepr data folder (blank keeps existing split defaults; synced folders require one device at a time)",
            default="",
            show_default=False,
        ).strip()
        chosen = entered or None
    if not chosen:
        return {}
    base = Path(chosen).expanduser().resolve()
    return {
        _DATA_DIR: str(base),
        _EXPERTS_PATH: str(base / "experts"),
        _REPORTS_PATH: str(base / "reports"),
    }


def _key_is_set(value: str | None) -> bool:
    """True when ``value`` is a real key, not empty or a placeholder."""
    if not value or not value.strip():
        return False
    return "your-" not in value.lower()


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse a dotenv file without changing the process environment."""
    return read_configuration_env_file(path)


def _upsert_env(path: Path, updates: dict[str, str]) -> None:
    """Update existing keys in place, append new ones, preserving the rest."""
    upsert_configuration_env_file(path, updates)


def _resolved(env_file: dict[str, str], var: str) -> str | None:
    """A var's effective value: process environment wins, then the .env file."""
    return os.getenv(var) or env_file.get(var)


def _ensure_env_file(env_path: Path, example_path: Path | None = None) -> bool:
    """Create a private stub, or copy an explicitly scoped local example."""
    return ensure_configuration_env_file(env_path, example_path)


def _collect_provider_keys(env_file: dict[str, str], *, yes: bool) -> dict[str, str]:
    """Report detected keys; in interactive mode, prompt (hidden) for missing ones."""
    updates: dict[str, str] = {}
    console.print("\nCloud API keys (optional - metered; skip if you'll use local or subscription capacity):")
    for label, var, url in _PROVIDERS:
        if _key_is_set(_resolved(env_file, var)):
            console.print(f"  [success]+[/success] {label}: detected")
            continue
        if yes:
            console.print(f"  [muted]-[/muted] {label}: not set  ({var}, get one at {url})")
            continue
        console.print(f"  [warning]-[/warning] {label}: not set  (get one at {url})")
        if not click.confirm(f"    Add a key for {label} now?", default=False):
            continue
        key = click.prompt(f"    {var}", hide_input=True, default="", show_default=False).strip()
        if key:
            updates[var] = key
            env_file[var] = key  # so the summary counts it
    return updates


def _resolve_budget_updates(env_file: dict[str, str], *, yes: bool, budget: float | None) -> dict[str, str]:
    """Decide budget-ceiling env updates without clobbering existing values."""
    updates: dict[str, str] = {}
    current_job = env_file.get(_BUDGET_JOB)
    if budget is not None:
        updates[_BUDGET_JOB] = f"{budget}"
    elif not yes:
        default_budget = float(current_job) if current_job else _DEFAULT_JOB_BUDGET
        chosen = click.prompt("\nPer-job budget ceiling (USD)", type=float, default=default_budget)
        updates[_BUDGET_JOB] = f"{chosen}"
    elif not current_job:
        updates[_BUDGET_JOB] = f"{_DEFAULT_JOB_BUDGET}"
    # Ensure daily/monthly caps exist so the cost gate always has a ceiling.
    if not env_file.get(_BUDGET_DAY):
        updates[_BUDGET_DAY] = f"{_DEFAULT_DAY_BUDGET}"
    if not env_file.get(_BUDGET_MONTH):
        updates[_BUDGET_MONTH] = f"{_DEFAULT_MONTH_BUDGET}"
    return updates


class _CapacityPresence(NamedTuple):
    local: bool
    plan_adapter: bool
    unadapted_plan: bool
    api: bool


def _report_capacity(env_file: dict[str, str]) -> _CapacityPresence:
    """Show detected sources without claiming workflow execution eligibility.

    Returns source-specific evidence. Presence never proves that an arbitrary
    workflow can execute.
    """
    from deepr.backends.capacity import BackendKind, detect_capacity
    from deepr.backends.plan_quota.adapters import get_adapter_by_executable

    merged = {**{k: v for k, v in env_file.items() if v}, **os.environ}
    sources = detect_capacity(env=merged)
    groups = (
        (BackendKind.LOCAL, "Local models"),
        (BackendKind.PLAN_QUOTA, "Plan-style CLI installations"),
        (BackendKind.API_METERED, "Cloud API keys"),
    )
    console.print("\nDetected capacity sources (execution eligibility is workflow-specific):")
    available = [source for source in sources if source.available]
    for kind, label in groups:
        detected = [source for source in available if source.kind == kind]
        if detected:
            evidence = "; ".join(f"{source.name} ({source.marginal_cost}; {source.detail})" for source in detected)
            console.print(f"  [success]+[/success] {label}: {evidence}")
        else:
            console.print(f"  [muted]- {label}: none detected[/muted]")
        for source in (item for item in sources if item.kind == kind and item.local_generation is not None):
            proof = source.local_generation
            console.print(f"    Local generation: {proof.status}. {proof.detail}")
    console.print("  [muted]Detection does not bypass workflow-specific safety or spend gates.[/muted]")
    plan_sources = [source for source in available if source.kind == BackendKind.PLAN_QUOTA]
    return _CapacityPresence(
        local=any(source.kind == BackendKind.LOCAL for source in available),
        plan_adapter=any(get_adapter_by_executable(source.backend_id) for source in plan_sources),
        unadapted_plan=any(not get_adapter_by_executable(source.backend_id) for source in plan_sources),
        api=any(source.kind == BackendKind.API_METERED for source in available),
    )


def _print_summary(env_file: dict[str, str], presence: _CapacityPresence) -> None:
    """Print evidence-matched readiness and no-spend next actions."""
    console.print("")
    if not any(presence):
        console.print("[warning]No capacity detected yet.[/warning] Deepr needs ONE of these (cheapest first):")
        _print_local_setup()
        console.print("  - Plan-style CLI on PATH: cost and adapter posture vary; inspect before use")
        console.print("  - Cloud API key in .env: OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY  (metered)")
        print_next("deepr doctor --skip-connectivity", also=True)
        return
    print_success("Capacity sources detected. Workflow-specific gates still decide execution.")
    console.print(f"Requested per-job budget ceiling: ${float(env_file.get(_BUDGET_JOB, _DEFAULT_JOB_BUDGET)):.2f}")
    console.print(
        "Numeric ceilings do not authorize paid execution; inspect effective limits with `deepr config show`."
    )
    data_dir = env_file.get(_DATA_DIR)
    if data_dir:
        console.print(f"Data location: {data_dir} (experts + research; portable across machines)")
    console.print("\nNext steps:")
    console.print("  deepr doctor --skip-connectivity          # local diagnostics, no provider calls")
    if presence.local:
        console.print("  deepr capacity next --task-class sync     # safe local maintenance guidance")
    if presence.plan_adapter:
        console.print("  deepr capacity fleet                      # registered plan adapters only")
    if presence.unadapted_plan:
        console.print("  Installed plan-style CLIs without a registered adapter remain inventory-only.")
    if presence.api:
        console.print('  deepr research "Your question here" --auto --preview  # no-spend API preview')


def _print_local_setup() -> None:
    """Show documented weight size and an estimate, never assume hardware fit."""
    from deepr.backends.local_fit import detect_vram_bytes, estimate_fit

    vram = detect_vram_bytes()
    console.print("  - Local model: install Ollama (https://ollama.com), with cloud disabled persistently.")
    console.print("    Library example: qwen3.8:27b, about 18 GB download (checked 2026-10-18).")
    if vram > 0:
        fit = estimate_fit(
            name="qwen3.8:27b", weight_bytes=18_000_000_000, param_b=27, context_tokens=8192, vram_bytes=vram
        )
        console.print(f"    Estimated fit at 8K context: {fit.explain()}")
        if fit.fits:
            console.print("    Optional download: ollama pull qwen3.8:27b; larger contexts need more memory.")
        else:
            console.print("    Choose a smaller model for this hardware; CPU offload may be slow.")
    else:
        console.print(
            "    GPU capacity unknown. Check memory before downloading; 18 GB is not the runtime requirement."
        )
    print_next("deepr capacity")
    print_next("deepr capacity next --task-class sync", also=True)
    console.print("    Model size and fit do not establish answer quality. See https://ollama.com/library/qwen3.8.")


@click.command(name="init")
@click.option("-y", "--yes", is_flag=True, help="Non-interactive: accept defaults, no secret prompts.")
@click.option("--local-env", is_flag=True, help="Write this folder's .env; select it later with DEEPR_ENV_FILE.")
@click.option(
    "--budget",
    type=float,
    default=None,
    help=f"Per-job budget ceiling in USD (default ${_DEFAULT_JOB_BUDGET:.0f}).",
)
@click.option(
    "--data-dir",
    "data_dir",
    default=None,
    help="Folder for experts + research (e.g. a synced OneDrive/Dropbox dir to share across machines).",
)
def init(yes: bool, budget: float | None, data_dir: str | None, local_env: bool):
    """Guided setup: detect keys, write ~/.deepr/.env, set a ceiling.

    Examples:

    \b
        deepr init                       # interactive wizard
        deepr init --yes                 # scriptable: defaults, no prompts
        deepr init --budget 3            # set the per-job ceiling
        deepr init --data-dir ~/OneDrive/deepr   # portable experts + research
    """
    if not yes and not click.get_text_stream("stdin").isatty():
        raise click.UsageError("Interactive setup requires a terminal. Use deepr init --yes for noninteractive setup.")
    from deepr import __version__
    from deepr.cli.startup_banner import show_startup_banner

    show_startup_banner(console, version=__version__)
    print_section_header("Deepr setup")

    env_path = configuration_env_path(local=local_env)
    created = _ensure_env_file(env_path, Path(".env.example") if local_env else None)
    env_file = _read_env_file(env_path)
    console.print(f"\nConfig file: [bold]{env_path.resolve()}[/bold]" + ("  (created)" if created else ""))
    if local_env:
        console.print("Set DEEPR_ENV_FILE to this absolute path for later commands; ambient .env files are not loaded.")

    updates: dict[str, str] = {}
    updates.update(_collect_provider_keys(env_file, yes=yes))
    updates.update(_resolve_budget_updates(env_file, yes=yes, budget=budget))
    updates.update(_resolve_data_dir_updates(env_file, yes=yes, data_dir=data_dir))

    if updates:
        _upsert_env(env_path, updates)
        env_file.update(updates)

    _print_summary(env_file, _report_capacity(env_file))
