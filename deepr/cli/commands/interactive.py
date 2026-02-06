"""Interactive mode - guided research workflow with modern TUI.

Provides an interactive menu when deepr is invoked with no arguments.
Uses Rich for beautiful terminal UI with panels, tables, and styled prompts.
"""

from typing import Any, Dict, List

import click
from rich import box
from rich.box import ROUNDED
from rich.panel import Panel
from rich.table import Table

from deepr.cli.colors import (
    console,
    print_error,
    print_header,
    print_key_value,
    print_success,
    print_warning,
    truncate_text,
)


def _get_recent_prompts(limit: int = 5) -> List[str]:
    """Get recent research prompts from job history."""
    try:
        from deepr.queue import SQLiteQueue

        queue = SQLiteQueue()
        jobs = queue.list_jobs(limit=limit * 2)  # Get extra in case of duplicates
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


def _get_available_models() -> List[Dict[str, Any]]:
    """Get available models with cost estimates."""
    return [
        {
            "name": "o4-mini-deep-research",
            "provider": "OpenAI",
            "description": "Fast deep research",
            "cost": "$1-3",
            "speed": "Fast (1-2 min)",
        },
        {
            "name": "o3-deep-research",
            "provider": "OpenAI",
            "description": "Thorough deep research",
            "cost": "$2-5",
            "speed": "Medium (2-5 min)",
        },
        {
            "name": "deep-research-pro-preview-12-2025",
            "provider": "Gemini",
            "description": "Google Deep Research Agent",
            "cost": "$1-2",
            "speed": "Slow (5-20 min)",
        },
        {
            "name": "grok-4-fast",
            "provider": "xAI",
            "description": "Quick factual queries",
            "cost": "$0.01",
            "speed": "Very fast",
        },
    ]


def _print_welcome():
    """Print welcome banner and status."""
    console.print()
    console.print(
        Panel(
            "[bold cyan]Deepr[/bold cyan] [dim]v2.7[/dim]\n[dim]Deep research automation platform[/dim]",
            box=ROUNDED,
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()


def _print_main_menu() -> int:
    """Print main menu and get selection."""
    menu_items = [
        ("1", "Research", "Submit a new research query"),
        ("2", "Experts", "Chat with domain experts"),
        ("3", "Jobs", "View job queue and history"),
        ("4", "Costs", "View spending and budgets"),
        ("5", "Config", "Settings and API keys"),
        ("6", "Help", "Commands and documentation"),
        ("q", "Quit", "Exit interactive mode"),
    ]

    table = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
        collapse_padding=True,
    )
    table.add_column("Key", style="bold cyan", width=3)
    table.add_column("Action", style="bold", width=12)
    table.add_column("Description", style="dim")

    for key, action, desc in menu_items:
        table.add_row(f"[{key}]", action, desc)

    console.print(table)
    console.print()

    choice = click.prompt(
        click.style("Select", fg="cyan"),
        type=str,
        default="1",
        show_default=False,
    )

    if choice.lower() == "q":
        return 0
    try:
        return int(choice)
    except ValueError:
        return -1


def _research_menu():
    """Research submission menu with query history and model selection."""
    print_header("Research")

    # Show recent queries for quick selection
    recent = _get_recent_prompts(5)
    if recent:
        console.print("[dim]Recent queries:[/dim]")
        for i, prompt in enumerate(recent, 1):
            console.print(f"  [{i}] {truncate_text(prompt, 70)}")
        console.print("  [n] New query")
        console.print()

        choice = click.prompt(
            click.style("Select or enter new query", fg="cyan"),
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
            prompt = click.prompt(click.style("Query", fg="cyan"))
    else:
        prompt = click.prompt(click.style("Query", fg="cyan"))

    if not prompt or len(prompt) < 10:
        print_error("Query too short (min 10 characters)")
        return

    # Model selection with costs
    console.print()
    console.print("[dim]Select model:[/dim]")

    models = _get_available_models()
    table = Table(show_header=True, box=box.SIMPLE, header_style="bold")
    table.add_column("#", width=3)
    table.add_column("Model", style="cyan")
    table.add_column("Provider")
    table.add_column("Cost", style="yellow")
    table.add_column("Speed", style="dim")

    for i, m in enumerate(models, 1):
        table.add_row(str(i), m["name"], m["provider"], m["cost"], m["speed"])

    console.print(table)
    console.print()

    model_choice = click.prompt(click.style("Model", fg="cyan"), type=int, default=1)
    if 1 <= model_choice <= len(models):
        model = models[model_choice - 1]["name"]
    else:
        model = "o4-mini-deep-research"

    # Web search option
    web_search = click.confirm(click.style("Enable web search?", fg="cyan"), default=True)

    # Cost estimate
    console.print()
    console.print("[dim]Estimating cost...[/dim]")

    from deepr.core.costs import CostEstimator

    estimate = CostEstimator.estimate_cost(prompt=prompt, model=model, enable_web_search=web_search)

    console.print()
    console.print(
        Panel(
            f"[bold]Estimated Cost:[/bold] [yellow]${estimate.expected_cost:.2f}[/yellow]\n"
            f"[dim]Range: ${estimate.min_cost:.2f} - ${estimate.max_cost:.2f}[/dim]",
            title="Cost Estimate",
            border_style="yellow",
        )
    )
    console.print()

    if not click.confirm(
        click.style(f"Submit job for ~${estimate.expected_cost:.2f}?", fg="cyan"),
        default=True,
    ):
        print_warning("Cancelled")
        return

    # Submit job
    _submit_research_job(prompt, model, web_search, estimate.expected_cost)


def _submit_research_job(prompt: str, model: str, web_search: bool, estimated_cost: float):
    """Submit a research job to the queue."""
    import uuid
    from datetime import datetime, timezone

    from deepr.queue import JobStatus, ResearchJob, SQLiteQueue

    queue = SQLiteQueue()

    job = ResearchJob(
        id=str(uuid.uuid4()),
        prompt=prompt,
        model=model,
        provider="openai" if "o3" in model or "o4" in model else "gemini",
        priority=3,
        enable_web_search=web_search,
        status=JobStatus.PENDING,
        submitted_at=datetime.now(timezone.utc),
    )

    queue.enqueue(job)

    print_success("Job submitted!")
    console.print()
    print_key_value("Job ID", job.id)
    print_key_value("Model", model)
    print_key_value("Est. Cost", f"${estimated_cost:.2f}")
    console.print()
    console.print(f"[dim]Track status:[/dim] deepr jobs status {job.id[:8]}")


def _experts_menu():
    """Expert management menu."""
    print_header("Domain Experts")

    console.print("[dim]Options:[/dim]")
    console.print("  [1] List experts")
    console.print("  [2] Chat with expert")
    console.print("  [3] Create new expert")
    console.print("  [4] Back")
    console.print()

    choice = click.prompt(click.style("Select", fg="cyan"), type=int, default=1)

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
            console.print("[dim]No experts found. Create one with 'deepr expert make'[/dim]")
            return

        profiles = list(experts_dir.glob("*/profile.json"))
        if not profiles:
            console.print("[dim]No experts found. Create one with 'deepr expert make'[/dim]")
            return

        table = Table(show_header=True, box=box.SIMPLE, header_style="bold")
        table.add_column("Expert", style="cyan")
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
        print_warning("Expert system not available. Install with: pip install -e '.[docs]'")


def _chat_with_expert():
    """Start chat with an expert."""
    expert_name = click.prompt(click.style("Expert name", fg="cyan"))
    console.print()
    console.print(f"[dim]Starting chat with '{expert_name}'...[/dim]")
    console.print(f'[dim]Run: deepr expert chat "{expert_name}"[/dim]')


def _create_expert():
    """Create a new expert."""
    console.print()
    console.print("[dim]To create an expert, run:[/dim]")
    console.print('  deepr expert make "Expert Name" --files docs/*.md')


def _jobs_menu():
    """Job queue management menu."""
    print_header("Jobs")

    try:
        from deepr.queue import JobStatus, SQLiteQueue

        queue = SQLiteQueue()
        jobs = queue.list_jobs(limit=20)

        if not jobs:
            console.print("[dim]No jobs in queue[/dim]")
            return

        # Stats
        pending = sum(1 for j in jobs if j.status == JobStatus.PENDING)
        running = sum(1 for j in jobs if j.status == JobStatus.IN_PROGRESS)
        completed = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
        failed = sum(1 for j in jobs if j.status == JobStatus.FAILED)

        console.print(
            f"[dim]Pending:[/dim] {pending}  "
            f"[dim]Running:[/dim] {running}  "
            f"[green]Completed:[/green] {completed}  "
            f"[red]Failed:[/red] {failed}"
        )
        console.print()

        # Recent jobs table
        table = Table(show_header=True, box=box.SIMPLE, header_style="bold")
        table.add_column("Status", width=12)
        table.add_column("ID", width=10)
        table.add_column("Query", width=50)
        table.add_column("Cost", width=8, justify="right")

        status_styles = {
            JobStatus.PENDING: "dim",
            JobStatus.IN_PROGRESS: "cyan",
            JobStatus.COMPLETED: "green",
            JobStatus.FAILED: "red",
        }

        for job in jobs[:10]:
            style = status_styles.get(job.status, "dim")
            cost = f"${job.cost:.2f}" if job.cost else "-"
            table.add_row(
                f"[{style}]{job.status.value.upper()}[/{style}]",
                job.id[:8],
                truncate_text(job.prompt, 50),
                cost,
            )

        console.print(table)
        console.print()
        console.print("[dim]View details: deepr jobs status <job-id>[/dim]")
    except Exception as e:
        print_error(f"Failed to load jobs: {e}")


def _costs_menu():
    """Cost tracking menu."""
    print_header("Costs")

    console.print("[dim]Cost Commands:[/dim]")
    console.print("  deepr costs show        - Current spending summary")
    console.print("  deepr costs timeline    - Spending over time")
    console.print("  deepr costs breakdown   - By model/provider")
    console.print("  deepr budget set <amt>  - Set budget limit")
    console.print()

    # Try to show quick summary
    try:
        from deepr.queue import SQLiteQueue

        queue = SQLiteQueue()
        jobs = queue.list_jobs(limit=100)
        total_cost = sum(j.cost or 0 for j in jobs)

        if total_cost > 0:
            console.print(f"[dim]Total spent (recent):[/dim] [yellow]${total_cost:.2f}[/yellow]")
    except Exception:
        pass


def _config_menu():
    """Configuration menu."""
    print_header("Configuration")

    console.print("[dim]Config Commands:[/dim]")
    console.print("  deepr config show       - View current settings")
    console.print("  deepr config set        - Update settings")
    console.print("  deepr doctor            - Verify setup")
    console.print("  deepr providers status  - Provider health")
    console.print()

    # Quick doctor check
    if click.confirm(click.style("Run quick health check?", fg="cyan"), default=False):
        console.print()
        console.print("[dim]Running deepr doctor...[/dim]")
        console.print("[dim]Run 'deepr doctor' for full diagnostics[/dim]")


def _help_menu():
    """Help and documentation menu."""
    print_header("Help")

    console.print("[bold]Quick Reference[/bold]")
    console.print()

    commands = [
        ("deepr research <query>", "Submit research query"),
        ("deepr learn <topic>", "Multi-phase learning"),
        ("deepr team <question>", "Multi-perspective analysis"),
        ("deepr expert chat <name>", "Chat with domain expert"),
        ("deepr jobs list", "View job queue"),
        ("deepr costs show", "View spending"),
        ("deepr doctor", "Verify setup"),
    ]

    for cmd, desc in commands:
        console.print(f"  [cyan]{cmd:<30}[/cyan] {desc}")

    console.print()
    console.print("[dim]Full docs: https://github.com/blisspixel/deepr[/dim]")


@click.command()
def interactive():
    """
    Start interactive mode for guided research.

    Launches when deepr is invoked with no arguments.
    Provides a menu-driven interface for research operations.

    Example:
        deepr           # Opens interactive mode
        deepr interactive  # Same as above
    """
    _print_welcome()

    while True:
        try:
            choice = _print_main_menu()

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
                _help_menu()
            else:
                print_error("Invalid option")

            console.print()

        except (KeyboardInterrupt, click.Abort):
            console.print()
            print_warning("Cancelled")
            break
        except EOFError:
            break
