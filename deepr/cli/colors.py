"""CLI color utilities for modern, colorful terminal output.

Uses rich for beautiful formatting and colorama for Windows compatibility.
"""

from rich.console import Console
from rich.theme import Theme
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.markdown import Markdown
from rich.box import ASCII
import click

# Initialize rich console with custom theme
custom_theme = Theme({
    "info": "cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "dim": "dim white",
    "highlight": "bold cyan",
    "command": "bold magenta",
    "provider": "bold blue",
    "cost": "yellow",
    "status_queued": "dim white",
    "status_processing": "bold cyan",
    "status_completed": "bold green",
    "status_failed": "bold red",
})

console = Console(theme=custom_theme)


def print_header(text: str):
    """Print a section header."""
    console.print(f"\n[bold cyan]{text}[/bold cyan]")
    console.print("[dim]" + "-" * len(text) + "[/dim]")


def print_success(text: str):
    """Print success message."""
    console.print(f"[success][OK][/success] {text}")


def print_error(text: str):
    """Print error message."""
    console.print(f"[error][X][/error] {text}")


def print_warning(text: str):
    """Print warning message."""
    console.print(f"[warning][!][/warning] {text}")


def print_info(text: str):
    """Print info message."""
    console.print(f"[info][i][/info] {text}")


def print_command(text: str):
    """Print command example."""
    console.print(f"[command]$[/command] [dim]{text}[/dim]")


def print_cost(amount: float):
    """Print cost with formatting."""
    console.print(f"[cost]Cost: ${amount:.4f}[/cost]")


def print_status(status: str, message: str):
    """Print job status with color."""
    status_lower = status.lower()
    if status_lower == "completed":
        console.print(f"[status_completed][OK][/status_completed] {message}")
    elif status_lower == "processing":
        console.print(f"[status_processing][>>][/status_processing] {message}")
    elif status_lower == "failed":
        console.print(f"[status_failed][X][/status_failed] {message}")
    else:
        console.print(f"[status_queued][ ][/status_queued] {message}")


def print_deprecation(old_cmd: str, new_cmd: str):
    """Print deprecation warning."""
    console.print()
    console.print(Panel(
        f"[warning]Command '[command]{old_cmd}[/command]' is deprecated.[/warning]\n"
        f"[info]Use '[command]{new_cmd}[/command]' instead.[/info]",
        title="[yellow]Deprecation Warning[/yellow]",
        border_style="yellow"
    ))
    console.print()


def print_job_table(jobs: list):
    """Print jobs in a formatted table."""
    table = Table(show_header=True, header_style="bold cyan", box=ASCII)
    table.add_column("Status", style="dim", width=12)
    table.add_column("Job ID", style="cyan", width=14)
    table.add_column("Model", style="blue", width=20)
    table.add_column("Prompt", style="white", width=50)
    table.add_column("Cost", style="yellow", width=10)

    for job in jobs:
        # Status indicator
        status = job.status.value.upper()
        if job.status.value == "completed":
            status_style = "status_completed"
        elif job.status.value == "processing":
            status_style = "status_processing"
        elif job.status.value == "failed":
            status_style = "status_failed"
        else:
            status_style = "status_queued"

        # Truncate prompt
        prompt = job.prompt[:47] + "..." if len(job.prompt) > 50 else job.prompt

        # Format cost
        cost = f"${job.cost:.4f}" if job.cost else "-"

        table.add_row(
            f"[{status_style}]{status}[/{status_style}]",
            job.id[:12] + "...",
            job.model,
            prompt,
            cost
        )

    console.print(table)


def print_markdown(text: str):
    """Print markdown-formatted text."""
    md = Markdown(text)
    console.print(md)


def print_panel(text: str, title: str = None, style: str = "cyan"):
    """Print text in a panel."""
    console.print(Panel(text, title=title, border_style=style))


def create_spinner(text: str):
    """Create a progress spinner for long operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    )


def print_provider_info(provider: str, model: str, estimated_cost: float):
    """Print provider configuration info."""
    console.print()
    console.print(Panel(
        f"[provider]Provider:[/provider] {provider}\n"
        f"[dim]Model:[/dim] {model}\n"
        f"[cost]Estimated cost:[/cost] ${estimated_cost:.2f}",
        title="[bold]Research Configuration[/bold]",
        border_style="blue"
    ))
    console.print()


# Click style helpers (for compatibility with existing click.echo calls)
def style_success(text: str) -> str:
    """Style text as success (for click.echo)."""
    return click.style(text, fg="green", bold=True)


def style_error(text: str) -> str:
    """Style text as error (for click.echo)."""
    return click.style(text, fg="red", bold=True)


def style_warning(text: str) -> str:
    """Style text as warning (for click.echo)."""
    return click.style(text, fg="yellow", bold=True)


def style_info(text: str) -> str:
    """Style text as info (for click.echo)."""
    return click.style(text, fg="cyan")


def style_dim(text: str) -> str:
    """Style text as dim (for click.echo)."""
    return click.style(text, fg="white", dim=True)


def style_command(text: str) -> str:
    """Style text as command (for click.echo)."""
    return click.style(text, fg="magenta", bold=True)
