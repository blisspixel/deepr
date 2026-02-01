"""Help commands for Deepr CLI.

Provides intent-based command guides and documentation.
"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


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
    console.print(Panel.fit(
        "[bold]Deepr Semantic Commands[/bold]\n\n"
        "Commands are organized by intent - what you want to accomplish.",
        border_style="cyan"
    ))
    console.print()
    
    # RESEARCH section
    console.print("[bold cyan]RESEARCH[/bold cyan] - Find information")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Command", style="green")
    table.add_column("Description")
    table.add_row("deepr research \"topic\"", "Auto-detect research mode")
    table.add_row("deepr check \"claim\"", "Verify a fact quickly")
    table.add_row("deepr agentic research \"topic\"", "Autonomous multi-step workflow")
    console.print(table)
    console.print()
    
    # LEARN section
    console.print("[bold cyan]LEARN[/bold cyan] - Build understanding")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Command", style="green")
    table.add_column("Description")
    table.add_row("deepr learn \"topic\"", "Multi-phase structured learning")
    table.add_row("deepr learn \"topic\" --phases 4", "Specify number of learning phases")
    console.print(table)
    console.print()
    
    # MAKE section
    console.print("[bold cyan]MAKE[/bold cyan] - Create artifacts")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Command", style="green")
    table.add_column("Description")
    table.add_row("deepr make docs \"topic\"", "Generate documentation")
    table.add_row("deepr make strategy \"topic\"", "Strategic analysis")
    console.print(table)
    console.print()
    
    # EXPERT section
    console.print("[bold cyan]EXPERT[/bold cyan] - Domain expertise")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Command", style="green")
    table.add_column("Description")
    table.add_row("deepr expert make \"name\"", "Create domain expert")
    table.add_row("deepr expert chat \"name\"", "Chat with expert")
    table.add_row("deepr expert learn \"name\" \"topic\"", "Add knowledge to expert")
    table.add_row("deepr expert list", "List all experts")
    table.add_row("deepr expert info \"name\"", "Show expert details")
    table.add_row("deepr expert fill-gaps \"name\"", "Research knowledge gaps")
    console.print(table)
    console.print()
    
    # TEAM section
    console.print("[bold cyan]TEAM[/bold cyan] - Multiple perspectives")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Command", style="green")
    table.add_column("Description")
    table.add_row("deepr team \"question\"", "Multi-perspective analysis")
    table.add_row("deepr team \"question\" --perspectives 8", "Specify number of perspectives")
    console.print(table)
    console.print()
    
    # Footer
    console.print("[dim]Use --help on any command for details[/dim]")
    console.print("[dim]Example: deepr research --help[/dim]")
    console.print()


@help.command(name="providers")
def providers():
    """Show available AI providers and their models."""
    console.print()
    console.print(Panel.fit(
        "[bold]AI Providers[/bold]\n\n"
        "Deepr supports multiple AI providers for different tasks.",
        border_style="cyan"
    ))
    console.print()
    
    # Provider table
    table = Table(title="Available Providers")
    table.add_column("Provider", style="cyan")
    table.add_column("Models")
    table.add_column("Best For")
    
    table.add_row(
        "openai",
        "gpt-5, gpt-5.2, o4-mini-deep-research",
        "Deep research, synthesis, complex reasoning"
    )
    table.add_row(
        "xai",
        "grok-4-fast, grok-4",
        "Quick lookups, fact checking, general queries"
    )
    table.add_row(
        "gemini",
        "gemini-2.0-flash, gemini-2.0-pro",
        "Multimodal tasks, long context"
    )
    table.add_row(
        "azure",
        "(your deployments)",
        "Enterprise deployments with Azure OpenAI"
    )
    
    console.print(table)
    console.print()
    
    console.print("[bold]Default Routing:[/bold]")
    console.print("  - Deep research: openai/o4-mini-deep-research")
    console.print("  - Quick operations: xai/grok-4-fast")
    console.print()
    console.print("[dim]Override with --provider and --model flags[/dim]")
    console.print()


@help.command(name="costs")
def costs():
    """Show cost guidance for different operations."""
    console.print()
    console.print(Panel.fit(
        "[bold]Cost Guidance[/bold]\n\n"
        "Estimated costs for different research operations.",
        border_style="cyan"
    ))
    console.print()
    
    table = Table(title="Estimated Costs")
    table.add_column("Operation", style="cyan")
    table.add_column("Cost Range")
    table.add_column("Time")
    
    table.add_row("deepr check", "$0.01-$0.05", "10-30 sec")
    table.add_row("deepr research (focus)", "$0.50-$2.00", "5-15 min")
    table.add_row("deepr research (deep)", "$2.00-$5.00", "15-30 min")
    table.add_row("deepr learn (3 phases)", "$5.00-$15.00", "45-90 min")
    table.add_row("deepr team (6 perspectives)", "$3.00-$10.00", "20-40 min")
    table.add_row("deepr expert make --learn", "$10.00-$20.00", "1-2 hours")
    
    console.print(table)
    console.print()
    
    console.print("[bold]Budget Controls:[/bold]")
    console.print("  - Set budget: deepr budget set 5")
    console.print("  - Check status: deepr budget status")
    console.print("  - Per-operation: --budget flag")
    console.print()
    console.print("[dim]Actual costs vary by provider, model, and query complexity[/dim]")
    console.print()
