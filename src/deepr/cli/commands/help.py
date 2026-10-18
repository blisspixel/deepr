"""Help commands for Deepr CLI.

Provides intent-based command guides and documentation.
"""

import click
from rich.panel import Panel
from rich.table import Table

from deepr.cli.colors import make_console

console = make_console()


@click.group()
def help():
    """Get help on Deepr commands and concepts."""
    pass


@help.command(name="verbs")
def verbs():
    """Display intent-based command guide.

    Shows all semantic commands organized by what you want to accomplish.
    """
    console.print()
    console.print(
        Panel.fit(
            "[bold]Deepr Semantic Commands[/bold]\n\nCommands are organized by intent - what you want to accomplish.",
            border_style="accent",
        )
    )
    console.print()

    # RESEARCH section
    console.print("[accent]RESEARCH[/accent] - Find information")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Command", style="success")
    table.add_column("Description")
    table.add_row('deepr research "topic"', "Auto-detect research mode")
    table.add_row('deepr check "claim"', "Verify a fact quickly")
    table.add_row('deepr agentic research "topic"', "Autonomous multi-step workflow")
    console.print(table)
    console.print()

    # LEARN section
    console.print("[accent]LEARN[/accent] - Build understanding")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Command", style="success")
    table.add_column("Description")
    table.add_row('deepr learn "topic"', "Multi-phase structured learning")
    table.add_row('deepr learn "topic" --phases 4', "Specify number of learning phases")
    console.print(table)
    console.print()

    # MAKE section
    console.print("[accent]MAKE[/accent] - Create artifacts")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Command", style="success")
    table.add_column("Description")
    table.add_row('deepr make docs "topic"', "Generate documentation")
    table.add_row('deepr make strategy "topic"', "Strategic analysis")
    console.print(table)
    console.print()

    # EXPERT section
    console.print("[accent]EXPERT[/accent] - Domain expertise")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Command", style="success")
    table.add_column("Description")
    table.add_row('deepr expert make "name"', "Create domain expert")
    table.add_row('deepr expert consult "question" -e "name" --local', "Consult stored expert state at $0")
    table.add_row('deepr expert learn "name" "topic"', "Add knowledge to expert")
    table.add_row("deepr expert list", "List all experts")
    table.add_row('deepr expert info "name"', "Show expert details")
    table.add_row('deepr expert route-gaps "name" --execute --scheduled', "Fill gaps with owned/prepaid capacity")
    console.print(table)
    console.print()

    # TEAM section
    console.print("[accent]TEAM[/accent] - Multiple perspectives")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Command", style="success")
    table.add_column("Description")
    table.add_row('deepr team "question"', "Multi-perspective analysis")
    table.add_row('deepr team "question" --perspectives 8', "Specify number of perspectives")
    console.print(table)
    console.print()

    # Footer
    console.print("[muted]Use --help on any command for details[/muted]")
    console.print("[muted]Example: deepr research --help[/muted]")
    console.print()


@help.command(name="providers")
def providers():
    """Show available AI providers and their models."""
    console.print()
    console.print(
        Panel.fit(
            "[bold]AI Providers[/bold]\n\nDeepr supports multiple AI providers for different tasks.",
            border_style="accent",
        )
    )
    console.print()

    from deepr.cli.commands.research_support import _PROVIDER_DEFAULT_MODELS
    from deepr.cli.model_choices import is_shutdown, model_note, retained_task_models
    from deepr.providers.registry import MODEL_CAPABILITIES
    from deepr.providers.reviewed_catalog import REVIEWED_CAPABILITIES

    table = Table(title="Retained defaults and reviewed candidates")
    table.add_column("Use", style="accent")
    table.add_column("Model")
    table.add_column("Status")
    for task, (provider, model) in retained_task_models().items():
        if is_shutdown(model):
            continue
        table.add_row(task.replace("_", " "), f"{provider}/{model}", model_note(model) or "Retained task default")
    for provider, model in _PROVIDER_DEFAULT_MODELS.items():
        if provider == "grok" or is_shutdown(model):
            continue
        table.add_row(f"{provider} research", model, model_note(model) or "Retained provider default")
    for key in REVIEWED_CAPABILITIES:
        cap = MODEL_CAPABILITIES.get(key)
        if cap is None or cap.selection_blocked or is_shutdown(cap.model):
            continue
        table.add_row(
            cap.provider, cap.model, "Preview only; adapter validation pending" if cap.preview_only else "Registered"
        )
    console.print(table)
    console.print("\nRetained defaults are not a claim of provider currency or tested answer quality.")
    console.print("Use deepr providers list for all contracts and lifecycle notes.")
    console.print("Use deepr capacity for execution eligibility; provider registration grants no spend authority.")


@help.command(name="costs")
def costs():
    """Show cost guidance for different operations."""
    console.print()
    console.print(
        Panel.fit(
            "[bold]Cost Guidance[/bold]\n\nEstimated costs for different research operations.", border_style="accent"
        )
    )
    console.print()

    table = Table(title="Estimated Costs")
    table.add_column("Operation", style="accent")
    table.add_column("Cost Range")
    table.add_column("Time")

    table.add_row("deepr check", "$0.01-$0.05", "10-30 sec")
    table.add_row("deepr research (focus)", "$0.50-$2.00", "5-15 min")
    table.add_row("deepr research (deep)", "$2.00-$5.00", "15-30 min")
    table.add_row("deepr learn (3 phases)", "$5.00-$15.00", "45-90 min")
    table.add_row("deepr team (6 perspectives)", "$1.00-$5.00", "20-40 min")
    table.add_row("deepr expert make --learn", "$1.00-$5.00", "1-2 hours")

    console.print(table)
    console.print()

    console.print("[bold]Budget Controls:[/bold]")
    console.print("  - Set budget: deepr budget set 5")
    console.print("  - Check status: deepr budget status")
    console.print("  - Per-operation: --budget flag")
    console.print()
    console.print("[muted]Actual costs vary by provider, model, and query complexity[/muted]")
    console.print()
