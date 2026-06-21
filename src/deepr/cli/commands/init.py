"""`deepr init` - guided first-run setup.

Collapses the manual setup path (copy .env.example, hand-edit a key, set a
budget, run doctor) into one command. It detects which provider keys are
already in the environment, creates or patches the (gitignored) ``.env`` in
the current directory, sets a budget ceiling, and prints the exact first
command to run.

Security: API keys are entered through hidden prompts, never echoed, and only
ever written to ``.env`` (which is gitignored). ``--yes`` runs
non-interactively (no secret prompts) so the command is safe in scripts and CI.
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from deepr.cli.colors import console, print_section_header, print_success

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
_DEFAULT_JOB_BUDGET = 5.0
_DEFAULT_DAY_BUDGET = 25.0
_DEFAULT_MONTH_BUDGET = 200.0

# Data-location env vars (ADR 0004). DEEPR_DATA_DIR is the one knob; experts
# and reports derive from it. Point it at a synced folder (OneDrive/Dropbox/
# iCloud) and your experts + research follow you across machines.
_DATA_DIR = "DEEPR_DATA_DIR"
_EXPERTS_PATH = "DEEPR_EXPERTS_PATH"
_REPORTS_PATH = "DEEPR_REPORTS_PATH"


def _resolve_data_dir_updates(env_file: dict[str, str], *, yes: bool, data_dir: str | None) -> dict[str, str]:
    """Decide data-location env updates so experts + reports can be portable.

    A chosen directory sets DEEPR_DATA_DIR plus explicit experts/reports
    subpaths (so both follow it). Blank/unset keeps the default ./data
    (backward compatible). Never overwrites an existing DEEPR_DATA_DIR silently.
    """
    chosen = data_dir
    if chosen is None and not yes and not env_file.get(_DATA_DIR):
        entered = click.prompt(
            "\nData folder for experts + research (blank = ./data; or a synced "
            "folder like ~/OneDrive/deepr to share across machines)",
            default="",
            show_default=False,
        ).strip()
        chosen = entered or None
    if not chosen:
        return {}
    base = chosen.rstrip("/\\")
    return {
        _DATA_DIR: base,
        _EXPERTS_PATH: f"{base}/experts",
        _REPORTS_PATH: f"{base}/reports",
    }


def _key_is_set(value: str | None) -> bool:
    """True when ``value`` is a real key, not empty or a placeholder."""
    if not value or not value.strip():
        return False
    return "your-" not in value.lower()


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse a ``.env`` file into a dict (ignores comments and blank lines)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        values[key.strip()] = val.strip()
    return values


def _upsert_env(path: Path, updates: dict[str, str]) -> None:
    """Update existing keys in place, append new ones, preserving the rest."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key is not None and key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    for key, val in remaining.items():
        out.append(f"{key}={val}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _resolved(env_file: dict[str, str], var: str) -> str | None:
    """A var's effective value: process environment wins, then the .env file."""
    return os.getenv(var) or env_file.get(var)


def _ensure_env_file(env_path: Path, example_path: Path) -> bool:
    """Create ``.env`` from the example (or a stub) if missing. Returns created?"""
    if env_path.exists():
        return False
    if example_path.exists():
        env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        env_path.write_text("# Deepr configuration\n", encoding="utf-8")
    return True


def _collect_provider_keys(env_file: dict[str, str], *, yes: bool) -> dict[str, str]:
    """Report detected keys; in interactive mode, prompt (hidden) for missing ones."""
    updates: dict[str, str] = {}
    console.print("\nCloud API keys (optional - metered; skip if you'll use local or subscription capacity):")
    for label, var, url in _PROVIDERS:
        if _key_is_set(_resolved(env_file, var)):
            console.print(f"  [green]+[/green] {label}: detected")
            continue
        if yes:
            console.print(f"  [dim]-[/dim] {label}: not set  ({var}, get one at {url})")
            continue
        console.print(f"  [yellow]-[/yellow] {label}: not set  (get one at {url})")
        if not click.confirm(f"    Add a {label} key now?", default=False):
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


def _report_capacity(env_file: dict[str, str]) -> bool:
    """Show what Deepr can run on, cheapest-first, across all three tiers.

    Deepr is capability-adaptive: it works with whatever you have - a local
    Ollama model ($0), a subscription CLI you already pay for (prepaid), or a
    cloud API key (metered) - and routes cheapest-first. Returns True if any
    capacity is available, so setup is "ready" without forcing an API key.
    Cross-platform (Mac/Linux/Windows): detection is HTTP probe + PATH lookup.
    """
    from deepr.backends.capacity import BackendKind, detect_capacity

    merged = {**os.environ, **{k: v for k, v in env_file.items() if v}}
    sources = detect_capacity(env=merged)
    groups = [
        (BackendKind.LOCAL, "Local models", "free at the margin"),
        (BackendKind.PLAN_QUOTA, "Subscription CLIs", "prepaid - accounts you already have"),
        (BackendKind.API_METERED, "Cloud API keys", "metered - paid per call"),
    ]
    console.print("\nWhat Deepr can run on (it routes cheapest-first: local -> quota -> metered):")
    any_available = False
    for kind, label, note in groups:
        available = [s.name for s in sources if s.kind == kind and s.available]
        if available:
            any_available = True
            console.print(f"  [green]+[/green] {label} [dim]({note})[/dim]: {', '.join(available)}")
        else:
            console.print(f"  [dim]- {label} ({note}): none detected[/dim]")
    return any_available


def _print_summary(env_file: dict[str, str], has_capacity: bool) -> None:
    """Print readiness (any capacity tier), the budget, and the next command."""
    console.print("")
    if not has_capacity:
        console.print("[yellow]No capacity detected yet.[/yellow] Deepr needs ONE of these (cheapest first):")
        console.print(
            "  - Local model: install Ollama (https://ollama.com), then `ollama pull qwen2.5-coder:32b`  ($0)"
        )
        console.print("  - Subscription CLI on PATH: codex / claude / opencode / ...  (prepaid)")
        console.print("  - Cloud API key in .env: OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY  (metered)")
        console.print("Then: deepr doctor")
        return
    print_success("Ready - Deepr will use the cheapest capacity available (local -> quota -> metered).")
    console.print(f"Per-job budget ceiling: ${float(env_file.get(_BUDGET_JOB, _DEFAULT_JOB_BUDGET)):.2f}")
    data_dir = env_file.get(_DATA_DIR)
    if data_dir:
        console.print(f"Data location: {data_dir} (experts + research; portable across machines)")
    console.print("\nNext steps:")
    console.print("  deepr capacity        # see exactly what Deepr will run on")
    console.print('  deepr research "Your question here" --auto')
    console.print("  deepr doctor          # verify connectivity")


@click.command(name="init")
@click.option("-y", "--yes", is_flag=True, help="Non-interactive: accept defaults, no secret prompts.")
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
def init(yes: bool, budget: float | None, data_dir: str | None):
    """Guided first-run setup: detect keys, write .env, set a budget.

    Examples:
        deepr init                       # interactive wizard
        deepr init --yes                 # scriptable: defaults, no prompts
        deepr init --budget 3            # set the per-job ceiling
        deepr init --data-dir ~/OneDrive/deepr   # portable experts + research
    """
    print_section_header("Deepr setup")

    env_path = Path(".env")
    created = _ensure_env_file(env_path, Path(".env.example"))
    env_file = _read_env_file(env_path)
    console.print(f"\nConfig file: [bold]{env_path.resolve()}[/bold]" + ("  (created)" if created else ""))

    updates: dict[str, str] = {}
    updates.update(_collect_provider_keys(env_file, yes=yes))
    updates.update(_resolve_budget_updates(env_file, yes=yes, budget=budget))
    updates.update(_resolve_data_dir_updates(env_file, yes=yes, data_dir=data_dir))

    if updates:
        _upsert_env(env_path, updates)
        env_file.update(updates)

    has_capacity = _report_capacity(env_file)
    _print_summary(env_file, has_capacity)
