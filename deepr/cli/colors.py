"""CLI color utilities for modern, colorful terminal output.

Uses rich for beautiful formatting and colorama for Windows compatibility.
Modern 2026 CLI design: Unicode symbols, minimal separators, clean typography.
"""

import os
import sys
from typing import Optional

import click
from rich.box import ASCII
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.theme import Theme


def _detect_unicode_support() -> bool:
    """Detect if terminal supports Unicode.
    
    Returns True for modern terminals (Windows Terminal, most Unix terminals).
    Returns False for legacy cmd.exe or when DEEPR_FORCE_ASCII is set.
    """
    # Check for explicit override
    if os.environ.get("DEEPR_FORCE_ASCII"):
        return False

    if sys.platform == "win32":
        # Windows Terminal and modern terminals support Unicode
        # Legacy cmd.exe does not
        return bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"))

    # Unix-like systems generally support Unicode
    encoding = getattr(sys.stdout, 'encoding', '') or ''
    return encoding.lower() in ("utf-8", "utf8", "")


# Unicode symbols for modern CLI output
UNICODE_SYMBOLS = {
    "success": "OK",
    "error": "ERROR",
    "warning": "WARN",
    "info": "INFO",
    "progress": "...",
    "bullet": "-",
    "sub_bullet": "-",
    "ellipsis": "...",
    "skip": "SKIP",
}

# ASCII fallback for legacy terminals
ASCII_SYMBOLS = {
    "success": "OK",
    "error": "ERROR",
    "warning": "WARN",
    "info": "INFO",
    "progress": "...",
    "bullet": "-",
    "sub_bullet": "-",
    "ellipsis": "...",
    "skip": "SKIP",
}

# Detect once at module load
_UNICODE_SUPPORTED = _detect_unicode_support()


def get_symbol(name: str) -> str:
    """Get the appropriate symbol for the current terminal.
    
    Args:
        name: Symbol name (success, error, warning, info, progress, bullet, etc.)
        
    Returns:
        Unicode symbol or ASCII fallback based on terminal support.
    """
    symbols = UNICODE_SYMBOLS if _UNICODE_SUPPORTED else ASCII_SYMBOLS
    return symbols.get(name, name)

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
    """Print a section header with modern styling."""
    console.print()
    console.print(f"[bold cyan]{text}[/bold cyan]")
    console.print()


def print_success(text: str):
    """Print success message."""
    console.print(f"[success]{text}[/success]")


def print_error(text: str):
    """Print error message."""
    console.print(f"[error]{text}[/error]")


def print_warning(text: str):
    """Print warning message."""
    console.print(f"[warning]{text}[/warning]")


def print_info(text: str):
    """Print info message."""
    console.print(f"[info]{text}[/info]")


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
        console.print(f"[status_completed]{message}[/status_completed]")
    elif status_lower == "processing":
        console.print(f"[status_processing]{message}[/status_processing]")
    elif status_lower == "failed":
        console.print(f"[status_failed]{message}[/status_failed]")
    else:
        console.print(f"[status_queued]{message}[/status_queued]")


def print_result(message: str, duration_seconds: Optional[float] = None, cost_usd: Optional[float] = None, success: bool = True):
    """Print operation result with optional duration and cost.
    
    Args:
        message: Result message
        duration_seconds: Optional duration in seconds
        cost_usd: Optional cost in USD
        success: Whether operation succeeded (default True)
        
    Example output: Research complete (12.3s, $0.0234)
    """
    color = "success" if success else "error"

    parts = [f"[{color}]{message}[/{color}]"]

    meta_parts = []
    if duration_seconds is not None:
        meta_parts.append(_format_duration(duration_seconds))
    if cost_usd is not None:
        meta_parts.append(f"${cost_usd:.4f}")

    if meta_parts:
        parts.append(f"[dim]({', '.join(meta_parts)})[/dim]")

    console.print(" ".join(parts))


def _format_duration(seconds: float) -> str:
    """Format duration in human-readable form.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted string like "12.3s" or "2m 15s"
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"


def print_step(current: int, total: int, message: str):
    """Print a numbered step indicator.
    
    Args:
        current: Current step number (1-indexed)
        total: Total number of steps
        message: Step description
        
    Example output: Step 1/5 Generating curriculum
    """
    console.print(f"[dim]Step {current}/{total}[/dim] {message}")


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


def truncate_text(text: str, max_width: int = 80) -> str:
    """Truncate text intelligently at word boundaries.
    
    Args:
        text: Text to truncate
        max_width: Maximum width (default 80)
        
    Returns:
        Truncated text with ellipsis if needed
    """
    if len(text) <= max_width:
        return text

    ellipsis = get_symbol("ellipsis")
    ellipsis_len = len(ellipsis)

    # Calculate available space for text (excluding ellipsis)
    available = max_width - ellipsis_len
    if available <= 0:
        return ellipsis[:max_width]

    # Find last space before available space
    truncate_at = text.rfind(" ", 0, available)
    if truncate_at == -1 or truncate_at < available // 2:
        # No good word boundary, just truncate
        truncate_at = available

    return text[:truncate_at].rstrip() + ellipsis


def truncate_path(path: str, max_width: int = 60) -> str:
    """Truncate file path preserving filename.
    
    Args:
        path: File path to truncate
        max_width: Maximum width (default 60)
        
    Returns:
        Truncated path with ellipsis if needed
    """
    if len(path) <= max_width:
        return path

    ellipsis = get_symbol("ellipsis")

    # Normalize path separators
    parts = path.replace("\\", "/").split("/")
    filename = parts[-1]

    if len(filename) >= max_width - 3:
        # Filename itself is too long
        return ellipsis + filename[-(max_width - 1):]

    # Keep first dir and filename, truncate middle
    if len(parts) > 2:
        return f"{parts[0]}/{ellipsis}/{filename}"
    return ellipsis + "/" + filename


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

        # Truncate prompt with modern ellipsis
        prompt = truncate_text(job.prompt, max_width=50)

        # Format cost
        cost = f"${job.cost:.4f}" if job.cost else "-"

        table.add_row(
            f"[{status_style}]{status}[/{status_style}]",
            truncate_text(job.id, max_width=14),
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


# Modern section header (replaces === separators)
def print_section_header(title: str, subtitle: str = None):
    """Print a modern section header (replaces === separators).
    
    Args:
        title: Main section title
        subtitle: Optional subtitle
        
    Example output:
        
        Research Results
        Query: What is the meaning of life?
        
    """
    console.print()
    console.print(f"[bold cyan]{title}[/bold cyan]")
    if subtitle:
        console.print(f"[dim]{subtitle}[/dim]")
    console.print()


def print_key_value(key: str, value: str, indent: int = 0):
    """Print a key-value pair with consistent formatting.
    
    Args:
        key: Label/key
        value: Value to display
        indent: Number of spaces to indent (default 0)
    """
    prefix = "  " * indent
    console.print(f"{prefix}[dim]{key}:[/dim] {value}")


def print_list_item(text: str, indent: int = 0):
    """Print a bullet list item.
    
    Args:
        text: Item text
        indent: Indentation level (0 = top level, 1+ = nested)
    """
    prefix = "  " * indent
    bullet = get_symbol("bullet") if indent == 0 else get_symbol("sub_bullet")
    console.print(f"{prefix}[dim]{bullet}[/dim] {text}")


def print_error_with_suggestion(summary: str, details: str = None, suggestion: str = None):
    """Print formatted error message with optional details and suggestion.

    Args:
        summary: Error summary (one line)
        details: Optional detailed error message
        suggestion: Optional "Try:" suggestion

    Example output:
        Error: Expert not found: Python Expert
          No expert with that name exists
          Try: deepr expert list
    """
    console.print(f"[error]Error: {summary}[/error]")

    if details:
        for line in details.split("\n"):
            console.print(f"  [dim]{line}[/dim]")

    if suggestion:
        console.print(f"  [cyan]Try:[/cyan] {suggestion}")


def _supports_hyperlinks() -> bool:
    """Check if terminal supports OSC 8 hyperlinks.

    Returns True for modern terminals (iTerm2, Windows Terminal, Konsole, etc.)
    """
    # Check for explicit override
    if os.environ.get("DEEPR_NO_HYPERLINKS"):
        return False

    # Windows Terminal supports hyperlinks
    if os.environ.get("WT_SESSION"):
        return True

    # iTerm2 supports hyperlinks
    if os.environ.get("ITERM_SESSION_ID"):
        return True

    # Check TERM_PROGRAM for known supporting terminals
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    if term_program in ("iterm.app", "hyper", "vscode", "wezterm"):
        return True

    # Check for VTE-based terminals (GNOME Terminal, etc.)
    if os.environ.get("VTE_VERSION"):
        return True

    return False


def make_hyperlink(url: str, text: Optional[str] = None) -> str:
    """Create a clickable hyperlink for supported terminals.

    Uses OSC 8 escape sequences for terminal hyperlinks.
    Falls back to plain text in unsupported terminals.

    Args:
        url: The URL or file path to link to
        text: Display text (defaults to URL)

    Returns:
        String with OSC 8 hyperlink or plain text
    """
    display_text = text or url

    if not _supports_hyperlinks():
        return display_text

    # OSC 8 hyperlink format: \033]8;;URL\033\\TEXT\033]8;;\033\\
    return f"\033]8;;{url}\033\\{display_text}\033]8;;\033\\"


def print_report_link(report_path: str, label: Optional[str] = None):
    """Print a clickable link to a report file.

    Args:
        report_path: Path to the report file or directory
        label: Optional label (defaults to path)
    """
    from pathlib import Path

    path = Path(report_path)
    display = label or str(path)

    # Convert to file:// URL for hyperlink
    try:
        file_url = path.resolve().as_uri()
        link = make_hyperlink(file_url, display)
        console.print(f"[dim]Report:[/dim] {link}")
    except Exception:
        console.print(f"[dim]Report:[/dim] {display}")


def print_truncated(
    lines: list,
    max_lines: int = 10,
    flag_name: str = "--full",
    show_count: bool = True
):
    """Print lines with truncation and hint to see more.

    Args:
        lines: List of lines to print
        max_lines: Maximum lines to show before truncating
        flag_name: Flag name to suggest for full output
        show_count: Show count of hidden lines

    Example output:
        line 1
        line 2
        ...
        [dim](+15 more, use --full to see all)[/dim]
    """
    if len(lines) <= max_lines:
        for line in lines:
            console.print(line)
        return

    # Print first max_lines
    for line in lines[:max_lines]:
        console.print(line)

    # Print truncation hint
    hidden = len(lines) - max_lines
    if show_count:
        console.print(f"[dim](+{hidden} more, use {flag_name} to see all)[/dim]")
    else:
        console.print(f"[dim](use {flag_name} to see all)[/dim]")
