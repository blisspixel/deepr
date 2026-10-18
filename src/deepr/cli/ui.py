"""Modern terminal UI utilities for expert chat interface.

Uses rich library for modern 2026 CLI design:
- Clean Unicode characters instead of ASCII walls
- Token-by-token streaming responses
- Real-time tool use indicators
- Adaptive intelligence based on query complexity
"""

import os
import re
import sys
from collections.abc import AsyncIterator
from enum import Enum

from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner

from deepr.cli.colors import make_console

# Rich detects the actual terminal; redirected Windows output stays plain.
console = make_console()


class QueryComplexity(Enum):
    """Query complexity levels for adaptive intelligence."""

    SIMPLE = "simple"  # Greetings, thanks, simple acknowledgments
    MODERATE = "moderate"  # Factual questions, clarifications
    COMPLEX = "complex"  # Multi-part, requires reasoning, strategic


def classify_query_complexity(query: str) -> QueryComplexity:
    """Classify query complexity to optimize processing.

    Simple queries skip heavy reasoning and tool calls.
    Moderate queries use light search.
    Complex queries use full reasoning and multiple tools.

    Args:
        query: User's query string

    Returns:
        QueryComplexity enum value
    """
    query_lower = query.lower().strip()

    # Simple: greetings, acknowledgments, single-word responses
    simple_patterns = [
        r"^hi$",
        r"^hello$",
        r"^hey$",
        r"^thanks?$",
        r"^thank you$",
        r"^ok$",
        r"^okay$",
        r"^yes$",
        r"^no$",
        r"^bye$",
        r"^goodbye$",
        r"^help$",
        r"^quit$",
        r"^exit$",
    ]

    if any(re.match(pattern, query_lower) for pattern in simple_patterns):
        return QueryComplexity.SIMPLE

    # Complex: long queries, multiple questions, strategic keywords
    complex_indicators = [
        "how would you",
        "what do you believe",
        "compare",
        "design",
        "architecture",
        "strategy",
        "why",
        "explain",
        "analyze",
        "multiple",
        "several",
        "both",
        "pros and cons",
    ]

    # Check length and complexity indicators
    word_count = len(query.split())
    has_multiple_sentences = query.count(".") > 1 or query.count("?") > 1
    has_complex_keywords = any(indicator in query_lower for indicator in complex_indicators)

    if word_count > 15 or has_multiple_sentences or has_complex_keywords:
        return QueryComplexity.COMPLEX

    # Default to moderate for everything else
    return QueryComplexity.MODERATE


def print_welcome(expert_name: str, domain: str, documents: int, updated_date: str, knowledge_age_days: int):
    """Print modern welcome screen for expert chat.

    Args:
        expert_name: Name of the expert
        domain: Expert's domain description
        documents: Number of documents in knowledge base
        updated_date: Last update date (YYYY-MM-DD format)
        knowledge_age_days: Age of knowledge in days
    """
    # Determine knowledge freshness
    if knowledge_age_days == 0:
        freshness = "[success]fresh[/success]"
    elif knowledge_age_days <= 7:
        freshness = "[warning]recent[/warning]"
    elif knowledge_age_days <= 30:
        freshness = f"[warning]{knowledge_age_days} days old[/warning]"
    else:
        freshness = f"[error]{knowledge_age_days} days old[/error]"

    # Create welcome panel
    content = f"""[bold]{documents} documents[/bold] - Updated {updated_date} - Knowledge: {freshness}
Domain: {domain}

Commands: [accent]/help[/accent] [accent]/status[/accent] [accent]/quit[/accent]"""

    panel = Panel(content, title=f"[accent]{expert_name}[/accent]", border_style="accent", padding=(1, 2))

    console.print()
    console.print(panel)
    console.print()


def print_user_input(message: str):
    """Print user input with formatting.

    Args:
        message: User's message
    """
    console.print(f"[bold]You:[/bold] {message}")
    console.print()


def print_thinking(action: str, with_spinner: bool = True):
    """Print thinking indicator with optional spinner.

    Args:
        action: Description of what the expert is doing
        with_spinner: Whether to show spinner animation
    """
    if with_spinner:
        # Use modern spinner - "dots" works well on Windows Terminal and most modern terminals
        # Fall back to "line" only on legacy cmd.exe
        spinner_type = "dots" if os.environ.get("WT_SESSION") or sys.platform != "win32" else "line"
        return Live(
            Spinner(spinner_type, text=f"[accent][/accent] [muted]{action}[/muted]"),
            console=console,
            refresh_per_second=8,
        )
    else:
        console.print(f"[muted]| {action}[/muted]")


def print_tool_use(tool_name: str, details: str):
    """Print tool use indicator without spinner.

    Args:
        tool_name: Name of the tool being used
        details: Additional details about tool use
    """
    console.print(f"[muted]| {details}[/muted]")


def print_divider():
    """Print a subtle divider line."""
    console.print("[muted]" + "─" * 60 + "[/muted]")


def print_tool_summary(tool_name: str, duration: float, cost: float):
    """Print summary of tool use at the end of response.

    Args:
        tool_name: Name of tool used
        duration: Duration in seconds
        cost: Cost in USD
    """
    console.print()
    console.print(f"[muted]{tool_name} - {duration:.1f}s - ${cost:.3f}[/muted]")
    print_divider()


def stream_response(expert_name: str, text: str):
    """Stream expert response with modern formatting.

    This is a simple version that prints the full text at once.
    For true token-by-token streaming, use stream_response_async.

    Args:
        expert_name: Name of the expert
        text: Response text
    """
    console.print(f"[accent]{expert_name}[/accent]")
    console.print()

    # Render as markdown for better formatting
    md = Markdown(text)
    console.print(md)
    console.print()


async def stream_response_async(expert_name: str, text_stream: AsyncIterator[str]):
    """Stream expert response token-by-token with modern formatting.

    Args:
        expert_name: Name of the expert
        text_stream: Async iterator yielding text chunks
    """
    console.print(f"[accent]{expert_name}[/accent]")
    console.print()

    # Accumulate full text for markdown rendering
    full_text = ""

    async for chunk in text_stream:
        full_text += chunk
        # Print chunk immediately for streaming effect
        console.print(chunk, end="")

    console.print()
    console.print()


def print_error(error_message: str):
    """Print error message with formatting.

    Args:
        error_message: Error message to display
    """
    console.print(f"[error]Error:[/error] {error_message}")
    console.print()


def print_session_summary(messages_count: int, cost: float, research_jobs: int, model: str):
    """Print session summary with statistics.

    Args:
        messages_count: Number of messages exchanged
        cost: Total cost accumulated
        research_jobs: Number of research jobs triggered
        model: Model used for the session
    """
    console.print()
    print_divider()
    console.print("[bold]Session Summary[/bold]")
    console.print(f"Messages: {messages_count}")
    console.print(f"Cost: ${cost:.4f}")
    if research_jobs > 0:
        console.print(f"Research jobs: {research_jobs}")
    console.print(f"Model: {model}")
    print_divider()


def print_command_help():
    """Print help text for available commands (grouped by category)."""
    from deepr.experts.commands import CommandRegistry

    registry = CommandRegistry.get_instance()
    groups = registry.commands_by_category()

    console.print()
    console.print("[bold]Available Commands[/bold]")
    console.print()
    for cat, cmds in groups.items():
        console.print(f"[bold]{cat.value}[/bold]")
        for cmd in cmds:
            arg_str = f" {cmd.args}" if cmd.args else ""
            aliases = f" ({', '.join('/' + a for a in cmd.aliases)})" if cmd.aliases else ""
            console.print(f"  [accent]/{cmd.name}{arg_str}[/accent]{aliases} - {cmd.description}")
        console.print()
    console.print("Use / (web) or \\ (CLI) prefix for commands. Just type to chat.")
    console.print()


def print_mode_indicator(mode_name: str):
    """Print a colored mode badge.

    Args:
        mode_name: Current chat mode name
    """
    console.print(f"[info][{mode_name}][/info]", end=" ")


def print_status(
    expert_name: str,
    messages_count: int,
    cost: float,
    budget: float | None,
    research_jobs: int,
    model: str,
    documents: int,
    daily_spent: float = 0.0,
    daily_limit: float = 0.0,
    monthly_spent: float = 0.0,
    monthly_limit: float = 0.0,
):
    """Print current session status with cost safety info.

    Args:
        expert_name: Name of the expert
        messages_count: Number of messages exchanged
        cost: Total cost accumulated
        budget: Budget limit, or None when authority is unavailable
        research_jobs: Number of research jobs triggered
        model: Model being used
        documents: Number of documents in knowledge base
        daily_spent: Total spent today
        daily_limit: Daily spending limit
        monthly_spent: Total spent this month
        monthly_limit: Monthly spending limit
    """
    console.print()
    console.print("[bold]Chat Session Status[/bold]")
    console.print(f"Expert: {expert_name}")
    console.print(f"Messages: {messages_count}")
    budget_status = f" / ${budget:.2f}" if budget is not None else " (budget unavailable)"
    console.print(f"Session cost: ${cost:.4f}{budget_status}")
    console.print(f"Research jobs: {research_jobs}")
    console.print(f"Model: {model}")
    console.print(f"Knowledge base: {documents} documents")

    # Show daily/monthly spending if available
    if daily_limit > 0:
        daily_pct = (daily_spent / daily_limit * 100) if daily_limit > 0 else 0
        daily_color = "success" if daily_pct < 50 else "warning" if daily_pct < 80 else "error"
        console.print(
            f"Daily spending: [{daily_color}]${daily_spent:.2f}[/{daily_color}] / ${daily_limit:.2f} ({daily_pct:.0f}%)"
        )

    if monthly_limit > 0:
        monthly_pct = (monthly_spent / monthly_limit * 100) if monthly_limit > 0 else 0
        monthly_color = "success" if monthly_pct < 50 else "warning" if monthly_pct < 80 else "error"
        console.print(
            f"Monthly spending: [{monthly_color}]${monthly_spent:.2f}[/{monthly_color}] / ${monthly_limit:.2f} ({monthly_pct:.0f}%)"
        )

    console.print()


def print_trace(reasoning_trace: list):
    """Print reasoning trace for transparency.

    Args:
        reasoning_trace: List of reasoning steps
    """
    if not reasoning_trace:
        console.print("[muted]No reasoning trace available yet.[/muted]")
        return

    console.print()
    console.print("[bold]Reasoning Trace:[/bold]")
    console.print()

    for i, step in enumerate(reasoning_trace, 1):
        step_type = step.get("step", "unknown")
        timestamp = step.get("timestamp", "unknown")

        console.print(f"[bold]{i}. {step_type}[/bold] [muted]({timestamp})[/muted]")

        if step_type == "model_routing":
            console.print(f"   Query: {step.get('query', 'N/A')}")
            console.print(f"   Selected: {step.get('selected_provider', 'N/A')}/{step.get('selected_model', 'N/A')}")
            console.print(f"   Confidence: {step.get('confidence', 0.0):.2f}")
            if step.get("reasoning_effort"):
                console.print(f"   Reasoning effort: {step.get('reasoning_effort')}")

        elif step_type == "search_knowledge_base":
            console.print(f"   Query: {step.get('query', 'N/A')}")
            reasoning = step.get("reasoning")
            if reasoning:
                console.print(f"   [accent]Reasoning:[/accent] {reasoning}")
            console.print(f"   Results: {step.get('results_count', 0)} documents")
            sources = step.get("sources", [])
            if sources:
                console.print(f"   Sources: {', '.join(sources[:3])}")

        elif step_type in ["quick_lookup", "standard_research", "deep_research"]:
            console.print(f"   Query: {step.get('query', 'N/A')}")
            reasoning = step.get("reasoning")
            if reasoning:
                console.print(f"   [accent]Reasoning:[/accent] {reasoning}")
            console.print(f"   Cost: ${step.get('cost', 0.0):.4f}")

        console.print()
