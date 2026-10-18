"""CLI color utilities for modern, colorful terminal output.

Uses rich for formatting. Windows color comes through Click, not a direct
colorama import.
"""

import os
import sys
from typing import Any

import click
from rich.box import ASCII
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape as _escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from deepr.cli.effects import branding_enabled, gradient_text, resolve_animation_policy


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
    encoding = getattr(sys.stdout, "encoding", "") or ""
    return encoding.lower() in ("utf-8", "utf8", "")


# One palette owner; commands select meanings instead of terminal colors.
ROLE_STYLES = {
    "text": "default",
    "accent": "cyan",
    "success": "green",
    "live": "green",
    "warning": "yellow",
    "destructive": "bold yellow",
    "error": "red",
    "info": "blue",
    "muted": "dim default",
    "money": "bold default",
    "quote": "italic dim default",
}
_COMPATIBILITY_ROLES = {
    "dim": "muted",
    "highlight": "accent",
    "command": "accent",
    "provider": "info",
    "cost": "money",
    "status_queued": "muted",
    "status_processing": "live",
    "status_completed": "success",
    "status_failed": "error",
    "bar.back": "muted",
    "bar.complete": "live",
    "bar.finished": "success",
    "bar.pulse": "live",
    "progress.description": "text",
    "progress.elapsed": "muted",
    "progress.remaining": "muted",
    "progress.percentage": "info",
    "status.spinner": "live",
    "markdown.h1": "accent",
    "markdown.h2": "accent",
    "markdown.h3": "accent",
    "markdown.link": "accent",
    "markdown.link_url": "muted",
    "markdown.block_quote": "quote",
}
custom_theme = Theme({**ROLE_STYLES, **{name: ROLE_STYLES[role] for name, role in _COMPATIBILITY_ROLES.items()}})
_STATUS_ROLES = {"ok": "success", "warning": "warning", "failed": "error", "skipped": "muted", "unverified": "warning"}
STATUS_WIDTH = max(map(len, _STATUS_ROLES))
_SYMBOLS = {
    "success": "ok",
    "error": "failed",
    "warning": "warning",
    "info": "info",
    "progress": "working",
    "bullet": "-",
    "sub_bullet": "-",
    "ellipsis": "...",
    "skip": "skipped",
}
# Preserve existing imports without maintaining two diverging label tables.
UNICODE_SYMBOLS = ASCII_SYMBOLS = _SYMBOLS
_UNICODE_SUPPORTED = _detect_unicode_support()


def get_symbol(name: str) -> str:
    """Return a readable state word or functional punctuation."""
    return _SYMBOLS.get(name, name)


def make_console(**options: Any) -> Console:
    """Use terminal palette colors and explicit highlighting on every CLI surface."""
    options.update(theme=custom_theme, color_system="auto", highlight=False)
    detected = Console(**options)
    if detected.color_system is None:
        return detected
    options["color_system"] = "standard"
    return Console(**options)


def status_text(status: str) -> Text:
    """One aligned diagnostic state, including when a caller supplies a plain console."""
    return Text(status.ljust(STATUS_WIDTH), style=ROLE_STYLES[_STATUS_ROLES[status]])


def style_role(text: str, role: str = "text") -> str:
    """Apply the same role through Click, honoring the process color opt-out."""
    if "NO_COLOR" in os.environ:
        return text
    style = Style.parse(ROLE_STYLES[role])
    color = style.color.name if style.color is not None and style.color.name != "default" else None
    return click.style(text, fg=color, bold=bool(style.bold), dim=bool(style.dim), italic=bool(style.italic))


def status_word(status: str) -> str:
    """The aligned diagnostic label for Click output, sharing the same role map."""
    return style_role(status.ljust(STATUS_WIDTH), _STATUS_ROLES[status])


console = make_console()
_ANIMATION_POLICY = resolve_animation_policy(console)


def print_header(text: str):
    """Print a section header with modern styling."""
    console.print()
    if branding_enabled(console):
        hue_shift = (os.times().elapsed % 12) / 12
        console.print(gradient_text(text, hue_offset=hue_shift))
    else:
        console.print(f"[accent]{text}[/accent]")
    console.print()


def print_brand_header(text: str):
    """Print a gradient brand-style header when advanced effects are enabled."""
    console.print()
    if branding_enabled(console):
        hue_shift = (os.times().elapsed % 12) / 12
        console.print(gradient_text(text, hue_offset=hue_shift))
    else:
        console.print(f"[accent]{text}[/accent]")
    console.print()


def _print_notice(text: str, role: str, label: str) -> None:
    """Keep explicitly labelled command guidance separate from notice styling."""
    before, separator, command = text.partition("Next: ")
    if separator:
        if before.strip():
            console.print(f"[{role}]{label}: {before.rstrip()}[/{role}]")
        print_next(command)
    else:
        console.print(f"[{role}]{label}: {text}[/{role}]")


def print_success(text: str):
    """Print a successful operation with a readable state word."""
    _print_notice(text, "success", "ok")


def print_error(text: str):
    """Print an error without inferring its exit classification."""
    _print_notice(text, "error", "error")


def print_warning(text: str):
    """Print an advisory warning with a readable state word."""
    _print_notice(text, "warning", "warning")


def print_info(text: str):
    """Print informational context with a readable label."""
    _print_notice(text, "info", "info")


def print_command(text: str):
    """Print command example."""
    console.print(f"[accent]$ {text}[/accent]")


def print_next(command: str, *, also: bool = False, indent: int = 0, target: Console | None = None) -> None:
    """Keep the complete next command in one explicit, palette-aware hint."""
    prefix = "Also" if also else "Next"
    output = target if target is not None else console
    output.print(Text(" " * indent + f"{prefix}: {command}", style=ROLE_STYLES["accent"]), soft_wrap=True)


def print_detail(detail: str, *, indent: int = 0, target: Console | None = None) -> None:
    """Render literal provenance or an explicitly prefixed next command."""
    prefix, separator, command = detail.partition(": ")
    if separator and prefix in {"Next", "Also"}:
        print_next(command, also=prefix == "Also", indent=indent, target=target)
    else:
        output = target if target is not None else console
        output.print(" " * indent + detail, style=ROLE_STYLES["muted"], markup=False)


def print_cost(amount: float):
    """Print cost with formatting."""
    console.print(f"[cost]Cost: ${amount:.4f}[/cost]")


def print_status(status: str, message: str):
    """Print job status with color."""
    status_lower = status.lower()
    if status_lower == "completed":
        console.print(f"[status_completed]completed: {message}[/status_completed]")
    elif status_lower == "processing":
        console.print(f"[status_processing]running: {message}[/status_processing]")
    elif status_lower == "failed":
        console.print(f"[status_failed]failed: {message}[/status_failed]")
    else:
        console.print(f"[status_queued]queued: {message}[/status_queued]")


def print_result(
    message: str, duration_seconds: float | None = None, cost_usd: float | None = None, success: bool = True
):
    """Print operation result with optional duration and cost.

    Args:
        message: Result message
        duration_seconds: Optional duration in seconds
        cost_usd: Optional cost in USD
        success: Whether operation succeeded (default True)

    Example output: Research complete (12.3s, $0.0234)
    """
    color = "success" if success else "error"

    label = "ok" if success else "failed"
    parts = [f"[{color}]{label}: {message}[/{color}]"]

    meta_parts = []
    if duration_seconds is not None:
        meta_parts.append(_format_duration(duration_seconds))
    if cost_usd is not None:
        meta_parts.append(f"${cost_usd:.4f}")

    if meta_parts:
        parts.append(f"[muted]({', '.join(meta_parts)})[/muted]")

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
    console.print(f"[muted]Step {current}/{total}[/muted] {message}")


def print_deprecation(old_cmd: str, new_cmd: str):
    """Print deprecation warning."""
    console.print()
    console.print(
        Panel(
            f"[warning]Command '[command]{old_cmd}[/command]' is deprecated.[/warning]\n"
            f"[info]Use '[command]{new_cmd}[/command]' instead.[/info]",
            title="[warning]Deprecation Warning[/warning]",
            border_style="warning",
        )
    )
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
        return ellipsis + filename[-(max_width - 1) :]

    # Keep first dir and filename, truncate middle
    if len(parts) > 2:
        return f"{parts[0]}/{ellipsis}/{filename}"
    return ellipsis + "/" + filename


def print_job_table(jobs: list):
    """Print jobs in a formatted table."""
    table = Table(show_header=True, header_style="accent", box=ASCII)
    table.add_column("Status", style="muted", width=12)
    table.add_column("Job ID", style="accent", width=14)
    table.add_column("Model", style="info", width=20)
    table.add_column("Prompt", style="text", width=50)
    table.add_column("Cost", style="money", width=10)

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
            f"[{status_style}]{status}[/{status_style}]", truncate_text(job.id, max_width=14), job.model, prompt, cost
        )

    console.print(table)


def print_markdown(text: str):
    """Print markdown-formatted text."""
    md = Markdown(text)
    console.print(md)


def print_panel(text: str, title: str | None = None, style: str = "accent"):
    """Print text in a panel."""
    console.print(Panel(text, title=title, border_style=style))


def create_spinner(text: str):
    """Create a progress spinner for long operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    )


def print_provider_info(provider: str, model: str, estimated_cost: float):
    """Print provider configuration info."""
    console.print()
    console.print(
        Panel(
            f"[provider]Provider:[/provider] {provider}\n"
            f"[muted]Model:[/muted] {model}\n"
            f"[cost]Estimated cost:[/cost] ${estimated_cost:.2f}",
            title="[bold]Research Configuration[/bold]",
            border_style="info",
        )
    )
    console.print()


# Click style helpers (for compatibility with existing click.echo calls)
def style_success(text: str) -> str:
    """Style text as success (for click.echo)."""
    return style_role(text, "success")


def style_error(text: str) -> str:
    """Style text as error (for click.echo)."""
    return style_role(text, "error")


def style_warning(text: str) -> str:
    """Style text as warning (for click.echo)."""
    return style_role(text, "warning")


def style_info(text: str) -> str:
    """Style text as info (for click.echo)."""
    return style_role(text, "info")


def style_dim(text: str) -> str:
    """Style text as dim (for click.echo)."""
    return style_role(text, "muted")


def style_command(text: str) -> str:
    """Style text as command (for click.echo)."""
    return style_role(text, "accent")


# Modern section header (replaces === separators)
def print_section_header(title: str, subtitle: str | None = None):
    """Print a modern section header (replaces === separators).

    Args:
        title: Main section title
        subtitle: Optional subtitle

    Example output:

        Research Results
        Query: What is the meaning of life?

    """
    console.print()
    console.print(f"[accent]{title}[/accent]")
    if subtitle:
        console.print(f"[muted]{subtitle}[/muted]")
    console.print()


def print_key_value(key: str, value: str, indent: int = 0):
    """Print a key-value pair with consistent formatting.

    Args:
        key: Label/key
        value: Value to display
        indent: Number of spaces to indent (default 0)
    """
    prefix = "  " * indent
    console.print(f"{prefix}[muted]{key}:[/muted] {value}")


def print_list_item(text: str, indent: int = 0):
    """Print a bullet list item.

    Args:
        text: Item text
        indent: Indentation level (0 = top level, 1+ = nested)
    """
    prefix = "  " * indent
    bullet = get_symbol("bullet") if indent == 0 else get_symbol("sub_bullet")
    console.print(f"{prefix}[muted]{bullet}[/muted] {text}")


def print_capacity_outlook(outlook: dict):
    """Render the non-probing $0/prepaid capacity outlook per maintenance task class.

    Shared by `deepr expert loop-status` and `deepr route explain`. Model and
    backend identifiers come from the admission ledger (operator data), so they
    are escaped before printing to the markup-enabled console: an unusual tag
    must never be swallowed as Rich markup or crash the human-readable view.
    Renders nothing when the outlook has no task classes.
    """
    task_classes = outlook.get("task_classes") or {}
    if not task_classes:
        return
    console.print("[muted]Next-run capacity (admitted, not a live probe):[/muted]")
    for task_class, entry in task_classes.items():
        rungs = []
        if entry.get("local_capacity_admitted"):
            rungs.append(f"$0 local ({_escape(', '.join(entry.get('admitted_local_models') or []))})")
        if entry.get("plan_capacity_admitted"):
            rungs.append(f"prepaid plan ({_escape(', '.join(entry.get('admitted_plan_backends') or []))})")
        summary = ", ".join(rungs) if rungs else "no automatic cheap capacity admitted"
        console.print(f"  [bold]{_escape(task_class)}[/bold]: {summary}")


def print_error_with_suggestion(summary: str, details: str | None = None, suggestion: str | None = None):
    """Print formatted error message with optional details and suggestion.

    Args:
        summary: Error summary (one line)
        details: Optional detailed error message
        suggestion: Optional next command

    Example output:
        Error: Expert not found: Python Expert
          No expert with that name exists
          Next: deepr expert list
    """
    console.print(f"[error]Error: {summary}[/error]")

    if details:
        for line in details.split("\n"):
            console.print(f"  [muted]{line}[/muted]")

    if suggestion:
        print_next(suggestion, indent=2)


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


def make_hyperlink(url: str, text: str | None = None) -> str:
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


def print_report_link(report_path: str, label: str | None = None):
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
        console.print(f"[muted]Report:[/muted] {link}")
    except Exception:
        console.print(f"[muted]Report:[/muted] {display}")


def print_truncated(lines: list, max_lines: int = 10, flag_name: str = "--full", show_count: bool = True):
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
        [muted](+15 more, use --full to see all)[/muted]
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
        console.print(f"[muted](+{hidden} more, use {flag_name} to see all)[/muted]")
    else:
        console.print(f"[muted](use {flag_name} to see all)[/muted]")
