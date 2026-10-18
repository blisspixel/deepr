"""Interactive mode - guided research workflow with modern TUI.

Provides an interactive menu when deepr is invoked with no arguments.
Uses Rich for beautiful terminal UI with panels, tables, and styled prompts.
"""

import asyncio
import inspect
import shlex
from datetime import UTC
from typing import Any

import click
from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from deepr import __version__
from deepr.cli.colors import (
    console,
    print_error,
    print_header,
    print_key_value,
    print_next,
    print_success,
    print_warning,
    style_role,
    truncate_text,
)
from deepr.cli.startup_banner import show_startup_banner


def _resolve_maybe_awaitable(value: Any) -> Any:
    """Resolve sync values and awaitables from queue backends."""
    if not inspect.isawaitable(value):
        return value
    try:
        return asyncio.run(value)
    except RuntimeError:
        # Fallback for environments with an existing running loop.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(value)
        finally:
            loop.close()


def _get_recent_prompts(limit: int = 5) -> list[str]:
    """Get recent research prompts from job history."""
    try:
        from deepr.queue import SQLiteQueue

        queue = SQLiteQueue()
        jobs = _resolve_maybe_awaitable(queue.list_jobs(limit=limit * 2))  # Get extra in case of duplicates
        seen = set()
        prompts = []
        for job in jobs:
            if job.prompt not in seen:
                seen.add(job.prompt)
                prompts.append(job.prompt)
                if len(prompts) >= limit:
                    break
        return prompts
    except Exception:
        return []


def _get_available_models() -> list[dict[str, Any]]:
    """Get available models with cost estimates."""
    return [
        {
            "name": "gpt-5.6-sol",
            "provider": "OpenAI",
            "description": "Flagship substitute for shut-down deep research",
            "cost": "$4/$20 per MTok",
            "speed": "Varies",
        },
        {
            "name": "gpt-5.6-terra",
            "provider": "OpenAI",
            "description": "Balanced substitute for o4-mini",
            "cost": "$2/$12 per MTok",
            "speed": "Faster than Sol",
        },
        {
            "name": "deep-research-max-preview-04-2026",
            "provider": "Gemini",
            "description": "Gemini Deep Research Max",
            "cost": "$3-7",
            "speed": "Slow (5-20 min)",
        },
        {
            "name": "grok-4.3",
            "provider": "xAI",
            "description": "Quick factual queries",
            "cost": "$0.05",
            "speed": "Very fast",
        },
    ]


def _print_welcome(banner_override: str | None = None):
    """Print startup intro with motion-aware banner fallback."""
    show_startup_banner(console, version=__version__, override=banner_override)


def _parse_main_menu_choice(raw_choice: str) -> int:
    """Parse main menu input into a route code."""
    value = (raw_choice or "").strip().lower()
    if value.startswith("/"):
        value = value[1:]
    if value in {"q", "quit", "exit", "0"}:
        return 0
    aliases = {
        "?": 6,
        "h": 6,
        "help": 6,
        "r": 1,
        "research": 1,
        "e": 2,
        "experts": 2,
        "j": 3,
        "jobs": 3,
        "c": 4,
        "costs": 4,
        "g": 5,
        "config": 5,
    }
    if value in aliases:
        return aliases[value]
    # Light fuzzy intent matching for command-palette style input.
    if " " not in value:
        for alias, route in aliases.items():
            if len(value) >= 2 and alias.isalpha() and value.startswith(alias):
                return route
    if value == "":
        return -1
    try:
        return int(value)
    except ValueError:
        return -1


def _get_home_status() -> tuple[str, str, str]:
    """Return compact status triplet: provider, budget, queue."""
    provider_label = "provider: unknown"
    budget_label = "budget: n/a"
    queue_label = "queue: n/a"

    try:
        from deepr.core.settings import get_settings

        settings = get_settings()
        provider = (settings.default_provider or "").strip() or "auto"
        provider_label = f"provider: {provider}"
    except Exception:
        pass  # best-effort status enrichment for menu; non-fatal if settings unavailable

    try:
        from deepr.queue import JobStatus, SQLiteQueue

        queue = SQLiteQueue()
        jobs = _resolve_maybe_awaitable(queue.list_jobs(limit=200))
        queued = sum(1 for j in jobs if j.status == JobStatus.QUEUED)
        running = sum(1 for j in jobs if j.status == JobStatus.PROCESSING)
        queue_label = f"queue: {queued} queued, {running} running"

        total_spent = sum(j.cost or 0 for j in jobs)
        budget_label = f"spent: ${total_spent:.2f}"
    except Exception:
        pass  # best-effort queue/budget enrichment for menu; non-fatal on any queue error

    return provider_label, budget_label, queue_label


def _print_main_menu() -> str:
    """Print main menu and get action text."""
    primary_items = [
        ("1", "Research", "Submit a new research query"),
        ("2", "Experts", "Chat with domain experts"),
        ("3", "Jobs", "View job queue and history"),
    ]
    secondary_items = [
        ("4", "Costs", "View spending and budgets"),
        ("5", "Config", "Settings and API keys"),
        ("6", "Help", "Commands and documentation"),
        ("q", "Quit", "Exit interactive mode (q/quit/exit/0)"),
    ]

    provider_label, budget_label, queue_label = _get_home_status()
    status = Text()
    status.append("Status: ", style="muted")
    status.append(provider_label, style="info")
    status.append("  ·  ", style="muted")
    status.append(budget_label, style="money")
    status.append("  ·  ", style="muted")
    status.append(queue_label, style="info")
    console.print(status)
    console.print()

    table = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
        collapse_padding=True,
    )
    table.add_column("Key", style="accent", width=5, no_wrap=True)
    table.add_column("Action", style="bold", width=12)
    table.add_column("Description", style="muted")

    table.add_row("", "[muted]Primary[/muted]", "")
    for key, action, desc in primary_items:
        table.add_row(Text(f"[{key}]"), action, desc)
    table.add_row("", "[muted]Utility[/muted]", "")
    for key, action, desc in secondary_items:
        table.add_row(Text(f"[{key}]"), action, desc)

    quick = Text()
    quick.append("Type ", style="muted")
    quick.append("[r]", style="accent")
    quick.append("esearch ", style="muted")
    quick.append("[e]", style="accent")
    quick.append("xperts ", style="muted")
    quick.append("[j]", style="accent")
    quick.append("obs ", style="muted")
    quick.append("[c]", style="accent")
    quick.append("osts ", style="muted")
    quick.append("[g]", style="accent")
    quick.append("config ", style="muted")
    quick.append("[?]", style="accent")
    quick.append("help ", style="muted")
    quick.append("or ", style="muted")
    quick.append("[q]", style="accent")
    quick.append("uit", style="muted")
    console.print(quick)
    console.print("[muted]Pro mode:[/muted] type a command directly (example: jobs list, costs show)")
    console.print(table)
    console.print()

    from deepr.cli.companion import print_companion

    print_companion("idle", console=console)
    choice = click.prompt(
        style_role("Action", "accent"),
        type=str,
        default="",
        show_default=False,
    )

    return choice


def _run_direct_command(raw_action: str) -> bool:
    """Run a direct deepr command from interactive action input.

    Returns:
        True if input was handled (executed or intentionally ignored),
        False if it doesn't look like a command.
    """
    action = (raw_action or "").strip()
    if not action:
        return True

    if action.startswith("/"):
        action = action[1:].strip()
    if action.lower().startswith("deepr "):
        action = action[6:].strip()
    if not action:
        return True

    try:
        tokens = shlex.split(action)
    except ValueError as exc:
        print_error(f"Invalid command syntax: {exc}")
        return True

    if not tokens:
        return True
    if tokens[0] in {"interactive", "i"}:
        print_warning("Already in interactive mode.")
        return True

    try:
        from deepr.cli.main import cli

        cli.main(args=tokens, prog_name="deepr", standalone_mode=False)
        return True
    except click.ClickException as exc:
        exc.show()
        return True
    except SystemExit:
        return True
    except Exception as exc:
        print_error(f"Command failed: {exc}")
        return True


def _research_menu():
    """Research submission menu with query history and model selection."""
    print_header("Research")

    # Show recent queries for quick selection
    recent = _get_recent_prompts(5)
    if recent:
        console.print("[muted]Recent queries:[/muted]")
        for i, prompt in enumerate(recent, 1):
            console.print(f"  [{i}] {truncate_text(prompt, 70)}")
        console.print("  [n] New query")
        console.print()

        choice = click.prompt(
            style_role("Select or enter new query", "accent"),
            type=str,
            default="n",
        )

        if choice.lower() != "n" and choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(recent):
                prompt = recent[idx]
            else:
                prompt = choice  # Treat as new query
        else:
            prompt = click.prompt(style_role("Query", "accent"))
    else:
        prompt = click.prompt(style_role("Query", "accent"))

    if not prompt or len(prompt) < 10:
        print_error("Query too short (min 10 characters)")
        return

    # Model selection with costs
    console.print()
    console.print("[muted]Select model:[/muted]")

    models = _get_available_models()
    table = Table(show_header=True, box=box.SIMPLE, header_style="bold")
    table.add_column("#", width=3)
    table.add_column("Model", style="accent")
    table.add_column("Provider")
    table.add_column("Cost", style="money")
    table.add_column("Speed", style="muted")

    for i, m in enumerate(models, 1):
        table.add_row(str(i), m["name"], m["provider"], m["cost"], m["speed"])

    console.print(table)
    console.print()

    model_choice = click.prompt(style_role("Model", "accent"), type=int, default=1)
    if 1 <= model_choice <= len(models):
        model = models[model_choice - 1]["name"]
    else:
        model = "gpt-5.6-sol"

    # Web search option
    web_search = click.confirm(style_role("Enable web search?", "accent"), default=True)

    # Cost estimate
    console.print()
    console.print("[muted]Estimating cost...[/muted]")

    from deepr.core.costs import CostEstimator

    estimate = CostEstimator.estimate_cost(prompt=prompt, model=model, enable_web_search=web_search)

    console.print()
    console.print(
        Panel(
            f"[bold]Estimated Cost:[/bold] [money]${estimate.expected_cost:.2f}[/money]\n"
            f"[muted]Range: ${estimate.min_cost:.2f} - ${estimate.max_cost:.2f}[/muted]",
            title="Cost Estimate",
            border_style="warning",
        )
    )
    console.print()

    if not click.confirm(
        style_role(f"Submit job for ~${estimate.expected_cost:.2f}?", "accent"),
        default=True,
    ):
        print_warning("Cancelled")
        return

    # Submit job
    _submit_research_job(prompt, model, web_search, estimate.expected_cost)


def _submit_research_job(prompt: str, model: str, web_search: bool, estimated_cost: float):
    """Submit a research job to the queue."""
    import uuid
    from datetime import datetime

    from deepr.queue import JobStatus, ResearchJob, SQLiteQueue

    queue = SQLiteQueue()

    # Map the model name to its actual provider. The previous fallback
    # routed everything that wasn't o3/o4 to ``gemini`` - including Grok,
    # Claude, and any explicit GPT-5/GPT-4.1 selection - producing instant
    # auth failures or, worse, wrong-vendor charges.
    def _provider_for(m: str) -> str:
        lm = (m or "").lower()
        if "claude" in lm or lm.startswith("anthropic"):
            return "anthropic"
        if "grok" in lm or lm.startswith("xai"):
            return "xai"
        if "gemini" in lm or lm.startswith("google") or "deep-research-pro" in lm:
            return "gemini"
        # All OpenAI families (o3*, o4*, gpt-5*, gpt-4*, …) and the
        # generic fall-through belong to openai by default.
        return "openai"

    job = ResearchJob(
        id=str(uuid.uuid4()),
        prompt=prompt,
        model=model,
        provider=_provider_for(model),
        priority=3,
        enable_web_search=web_search,
        status=JobStatus.QUEUED,
        submitted_at=datetime.now(UTC),
    )

    _resolve_maybe_awaitable(queue.enqueue(job))

    print_success("Job submitted!")
    console.print()
    print_key_value("Job ID", job.id)
    print_key_value("Model", model)
    print_key_value("Est. Cost", f"${estimated_cost:.2f}")
    console.print()
    console.print(f"[muted]Track status:[/muted] deepr jobs status {job.id[:8]}")


def _experts_menu():
    """Expert management menu."""
    print_header("Domain Experts")
    console.print("[muted]Experts are optional. Use Research for one-off queries.[/muted]")
    console.print()

    console.print("[muted]Options:[/muted]")
    console.print("  [1] List experts")
    console.print("  [2] Chat with expert")
    console.print("  [3] Create new expert")
    console.print("  [4] Back")
    console.print()

    choice = click.prompt(style_role("Select", "accent"), type=int, default=1)

    if choice == 1:
        _list_experts()
    elif choice == 2:
        _chat_with_expert()
    elif choice == 3:
        _create_expert()
    elif choice == 4:
        return
    else:
        print_error("Invalid option")


def _list_experts():
    """List available experts."""
    try:
        from pathlib import Path

        from deepr.experts.profile import ExpertProfile

        experts_dir = Path("experts")
        if not experts_dir.exists():
            console.print("[muted]No experts yet.[/muted]")
            print_next('deepr expert make "My Expert" --files docs/*.md')
            return

        profiles = list(experts_dir.glob("*/profile.json"))
        if not profiles:
            console.print("[muted]No experts yet.[/muted]")
            print_next('deepr expert make "My Expert" --files docs/*.md')
            return

        table = Table(show_header=True, box=box.SIMPLE, header_style="bold")
        table.add_column("Expert", style="accent")
        table.add_column("Domain")
        table.add_column("Documents", justify="right")

        for profile_path in profiles:
            try:
                profile = ExpertProfile.load(profile_path.parent)
                table.add_row(
                    profile.name,
                    profile.domain or "-",
                    str(len(profile.documents) if profile.documents else 0),
                )
            except Exception:
                table.add_row(profile_path.parent.name, "-", "-")

        console.print(table)
    except ImportError:
        print_warning("Expert system not available. Next: pip install -e '.[docs]'")


def _chat_with_expert():
    """Start chat with an expert."""
    expert_name = click.prompt(style_role("Expert name", "accent"))
    console.print()
    console.print(f"[muted]Starting chat with '{expert_name}'...[/muted]")
    print_next(f'deepr expert consult "your question" -e "{expert_name}" --local')


def _create_expert():
    """Create a new expert."""
    console.print()
    console.print("[muted]To create an expert, run:[/muted]")
    console.print('  deepr expert make "Expert Name" --files docs/*.md')


def _jobs_menu():
    """Job queue management menu."""
    print_header("Jobs")

    try:
        from deepr.queue import JobStatus, SQLiteQueue

        queue = SQLiteQueue()
        jobs = _resolve_maybe_awaitable(queue.list_jobs(limit=20))

        if not jobs:
            console.print("[muted]No jobs in queue[/muted]")
            return

        # Stats
        pending = sum(1 for j in jobs if j.status == JobStatus.QUEUED)
        running = sum(1 for j in jobs if j.status == JobStatus.PROCESSING)
        completed = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in jobs if j.status == JobStatus.FAILED)

        console.print(
            f"[muted]Pending:[/muted] {pending}  "
            f"[muted]Running:[/muted] {running}  "
            f"[success]Completed:[/success] {completed}  "
            f"[error]Failed:[/error] {failed}"
        )
        console.print()

        # Recent jobs table
        table = Table(show_header=True, box=box.SIMPLE, header_style="bold")
        table.add_column("Status", width=12)
        table.add_column("ID", width=10)
        table.add_column("Query", width=50)
        table.add_column("Cost", width=8, justify="right")

        status_styles = {
            JobStatus.QUEUED: "muted",
            JobStatus.PROCESSING: "accent",
            JobStatus.COMPLETED: "success",
            JobStatus.FAILED: "error",
            JobStatus.CANCELLED: "warning",
        }

        for job in jobs[:10]:
            style = status_styles.get(job.status, "muted")
            cost = f"${job.cost:.2f}" if job.cost else "-"
            table.add_row(
                f"[{style}]{job.status.value.upper()}[/{style}]",
                job.id[:8],
                truncate_text(job.prompt, 50),
                cost,
            )

        console.print(table)
        console.print()
        console.print("[muted]View details: deepr jobs status <job-id>[/muted]")
    except Exception as e:
        print_error(f"Failed to load jobs: {e}")


def _costs_menu():
    """Cost tracking menu."""
    print_header("Costs")

    console.print("[muted]Cost Commands:[/muted]")
    console.print("  deepr costs show        - Current spending summary")
    console.print("  deepr costs timeline    - Spending over time")
    console.print("  deepr costs breakdown   - By model/provider")
    console.print("  deepr budget set <amt>  - Set budget limit")
    console.print()

    # Try to show quick summary
    try:
        from deepr.queue import SQLiteQueue

        queue = SQLiteQueue()
        jobs = _resolve_maybe_awaitable(queue.list_jobs(limit=100))
        total_cost = sum(j.cost or 0 for j in jobs)

        if total_cost > 0:
            console.print(f"[muted]Total spent (recent):[/muted] [money]${total_cost:.2f}[/money]")
    except Exception:
        pass  # best-effort cost summary for help text; non-fatal if queue unavailable


def _config_menu():
    """Configuration menu."""
    print_header("Configuration")

    console.print("[muted]Config Commands:[/muted]")
    console.print("  deepr config show       - View current settings")
    console.print("  deepr config set        - Update settings")
    console.print("  deepr doctor            - Verify setup")
    console.print("  deepr providers status  - Provider health")
    console.print()

    # Quick doctor check
    if click.confirm(style_role("Run quick health check?", "accent"), default=False):
        console.print()
        console.print("[muted]Running deepr doctor...[/muted]")
        console.print("[muted]Run 'deepr doctor' for full diagnostics[/muted]")


def _help_menu(ctx: click.Context | None = None):
    """Help and documentation menu."""
    print_header("Help")

    console.print("[bold]Quick Reference[/bold]")
    console.print()

    commands = [
        ("deepr research <query>", "Submit research query"),
        ("deepr learn <topic>", "Multi-phase learning"),
        ("deepr team <question>", "Multi-perspective analysis"),
        ('deepr expert consult "question" -e <name> --local', "Consult stored expert state at $0"),
        ("deepr jobs list", "View job queue"),
        ("deepr costs show", "View spending"),
        ("deepr doctor", "Verify setup"),
    ]

    for cmd, desc in commands:
        console.print(f"  [accent]{cmd:<30}[/accent] {desc}")

    console.print()
    console.print("[muted]Full docs: https://github.com/blisspixel/deepr[/muted]")
    if ctx is not None and ctx.parent is not None:
        if click.confirm(style_role("Show full command index?", "accent"), default=False):
            console.print()
            console.print("[bold]Full Command Index[/bold]")
            console.print(ctx.parent.get_help())


@click.command()
@click.option(
    "--banner",
    "banner_override",
    flag_value="on",
    default=None,
    help="Request startup banner; reduced motion and opt-outs still apply",
)
@click.option("--no-banner", "banner_override", flag_value="off", help="Skip startup banner")
@click.pass_context
def interactive(ctx: click.Context, banner_override: str | None):
    """
    Start interactive mode for guided research.

    Launches when deepr is invoked with no arguments.
    Provides a menu-driven interface for research operations.

    Example:
        deepr                    # Opens interactive mode
        deepr interactive        # Same as above
        deepr interactive --banner
        deepr interactive --no-banner
    """
    _print_welcome(banner_override=banner_override)

    while True:
        try:
            action = _print_main_menu()
            choice = _parse_main_menu_choice(action)

            if choice == 0:
                print_success("Goodbye!")
                break
            elif choice == 1:
                _research_menu()
            elif choice == 2:
                _experts_menu()
            elif choice == 3:
                _jobs_menu()
            elif choice == 4:
                _costs_menu()
            elif choice == 5:
                _config_menu()
            elif choice == 6:
                _help_menu(ctx)
            else:
                if not _run_direct_command(action):
                    print_error("Unknown action. Use 1-6, ?, q, or type a command like 'jobs list'.")

            console.print()

        except (KeyboardInterrupt, click.Abort):
            console.print()
            print_success("Goodbye!")
            break
        except EOFError:
            break
