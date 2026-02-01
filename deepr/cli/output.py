"""Unified output formatting for CLI commands.

Provides a tiered output system:
- MINIMAL (default): Single success line with duration, cost, path
- VERBOSE: Detailed output with progress messages
- JSON: Machine-readable JSON for scripting
- QUIET: No output except errors to stderr

Usage:
    @output_options
    def my_command(output_context: OutputContext, ...):
        formatter = OutputFormatter(output_context)
        formatter.start_operation("Processing...")
        # do work
        formatter.complete(result)
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn


class OutputMode(Enum):
    """Output verbosity modes for CLI."""
    MINIMAL = "minimal"   # Default: single success line
    VERBOSE = "verbose"   # Detailed output (current behavior)
    JSON = "json"         # Machine-readable JSON
    QUIET = "quiet"       # No output except errors


class OutputModeConflictError(click.UsageError):
    """Raised when conflicting output mode flags are provided."""
    pass


@dataclass
class OutputContext:
    """Context for a CLI operation's output.
    
    Attributes:
        mode: The output verbosity mode
        start_time: When the operation started (set automatically)
        job_id: Optional job identifier for the operation
    """
    mode: OutputMode = OutputMode.MINIMAL
    start_time: Optional[float] = field(default=None)
    job_id: Optional[str] = None
    
    def __post_init__(self):
        """Set start_time if not provided."""
        if self.start_time is None:
            self.start_time = time.time()
    
    @classmethod
    def from_flags(
        cls,
        verbose: bool = False,
        json_output: bool = False,
        quiet: bool = False
    ) -> "OutputContext":
        """Create context from CLI flags, validating mutual exclusivity.
        
        Args:
            verbose: Whether --verbose flag was provided
            json_output: Whether --json flag was provided
            quiet: Whether --quiet flag was provided
            
        Returns:
            OutputContext with appropriate mode
            
        Raises:
            OutputModeConflictError: If conflicting flags are provided
        """
        # Check for conflicts
        flags_set = []
        if verbose:
            flags_set.append("--verbose")
        if json_output:
            flags_set.append("--json")
        if quiet:
            flags_set.append("--quiet")
        
        if len(flags_set) > 1:
            raise OutputModeConflictError(
                f"Cannot use {flags_set[0]} with {flags_set[1]}. Choose one output mode."
            )
        
        # Determine mode
        if verbose:
            mode = OutputMode.VERBOSE
        elif json_output:
            mode = OutputMode.JSON
        elif quiet:
            mode = OutputMode.QUIET
        else:
            # Check environment variable for backward compatibility
            if os.environ.get("DEEPR_VERBOSE", "").lower() == "true":
                mode = OutputMode.VERBOSE
            else:
                mode = OutputMode.MINIMAL
        
        return cls(mode=mode)


@dataclass
class OperationResult:
    """Result of a CLI operation.
    
    Attributes:
        success: Whether the operation succeeded
        duration_seconds: How long the operation took
        cost_usd: Cost of the operation in USD
        report_path: Path to the generated report (if any)
        job_id: Job identifier (if any)
        error: Error message (if failed)
        error_code: Error code for programmatic handling (if failed)
    """
    success: bool
    duration_seconds: float
    cost_usd: float
    report_path: Optional[str] = None
    job_id: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    def to_json(self) -> str:
        """Serialize result to JSON string.
        
        Returns:
            JSON string with all relevant fields
        """
        if self.success:
            data = {
                "status": "success",
                "duration_seconds": self.duration_seconds,
                "cost_usd": self.cost_usd,
                "report_path": self.report_path or "",
                "job_id": self.job_id or ""
            }
        else:
            data = {
                "status": "error",
                "error": self.error or "Unknown error",
                "error_code": self.error_code or "UNKNOWN"
            }
        
        return json.dumps(data, ensure_ascii=False)


def format_duration(seconds: float) -> str:
    """Format duration as human-readable string.
    
    Args:
        seconds: Duration in seconds (0 to 86400)
        
    Returns:
        Formatted string:
        - "{seconds}s" for durations < 60 seconds
        - "{minutes}m {seconds}s" for durations 60-3599 seconds
        - "{hours}h {minutes}m" for durations >= 3600 seconds
        
    Examples:
        >>> format_duration(45.7)
        '46s'
        >>> format_duration(135.2)
        '2m 15s'
        >>> format_duration(3725.0)
        '1h 2m'
    """
    # Round to nearest second
    total_seconds = round(seconds)
    
    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        secs = total_seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def parse_duration(formatted: str) -> float:
    """Parse formatted duration back to seconds.
    
    Args:
        formatted: Duration string like "2m 15s", "45s", or "1h 30m"
        
    Returns:
        Duration in seconds
        
    Raises:
        ValueError: If format is not recognized
    """
    formatted = formatted.strip()
    total = 0.0
    
    # Handle hours
    if "h" in formatted:
        parts = formatted.split("h")
        total += float(parts[0].strip()) * 3600
        formatted = parts[1].strip() if len(parts) > 1 else ""
    
    # Handle minutes
    if "m" in formatted:
        parts = formatted.split("m")
        total += float(parts[0].strip()) * 60
        formatted = parts[1].strip() if len(parts) > 1 else ""
    
    # Handle seconds
    if "s" in formatted:
        parts = formatted.split("s")
        total += float(parts[0].strip())
    
    return total


def format_cost(cost_usd: float) -> str:
    """Format cost as dollar string.
    
    Args:
        cost_usd: Cost in USD (0.00 to 10000.00)
        
    Returns:
        Formatted string with dollar sign and exactly two decimal places.
        Uses period as decimal separator regardless of locale.
        
    Examples:
        >>> format_cost(0.42)
        '$0.42'
        >>> format_cost(0)
        '$0.00'
        >>> format_cost(0.001)
        '$0.00'
    """
    # Round to 2 decimal places and format with period separator
    return f"${cost_usd:.2f}"


def parse_cost(formatted: str) -> float:
    """Parse formatted cost back to float.
    
    Args:
        formatted: Cost string like "$0.42"
        
    Returns:
        Cost in USD
        
    Raises:
        ValueError: If format is not recognized
    """
    # Remove dollar sign and parse
    cleaned = formatted.strip().lstrip("$")
    return float(cleaned)



class OutputFormatter:
    """Unified output formatter respecting output mode.
    
    Handles all CLI output based on the configured mode:
    - MINIMAL: Single success/error line
    - VERBOSE: Detailed progress and results
    - JSON: Machine-readable JSON output
    - QUIET: No stdout, errors to stderr only
    
    Usage:
        context = OutputContext.from_flags(verbose=False, json_output=False, quiet=False)
        formatter = OutputFormatter(context)
        
        formatter.start_operation("Processing files...")
        # do work
        result = OperationResult(success=True, duration_seconds=135.5, cost_usd=0.42, ...)
        formatter.complete(result)
    """
    
    def __init__(self, context: OutputContext):
        """Initialize formatter with output context.
        
        Args:
            context: OutputContext specifying the output mode
        """
        self.context = context
        self._console = Console()
        self._stderr_console = Console(stderr=True)
        self._progress: Optional[Progress] = None
        self._progress_task = None
    
    def start_operation(self, description: str) -> None:
        """Begin an operation with appropriate feedback.
        
        Args:
            description: Description of the operation starting
        """
        if self.context.mode == OutputMode.VERBOSE:
            # Show spinner for verbose mode
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=self._console,
                transient=True
            )
            self._progress.start()
            self._progress_task = self._progress.add_task(description, total=None)
        elif self.context.mode == OutputMode.MINIMAL:
            # Show minimal spinner
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self._console,
                transient=True
            )
            self._progress.start()
            self._progress_task = self._progress.add_task(description, total=None)
        # JSON and QUIET modes show nothing during operation
    
    def progress(self, message: str) -> None:
        """Show progress message (verbose mode only).
        
        Args:
            message: Progress message to display
        """
        if self.context.mode == OutputMode.VERBOSE:
            self._console.print(f"[dim]{message}[/dim]")
    
    def complete(self, result: OperationResult) -> None:
        """Show completion with result.
        
        Args:
            result: The operation result to display
        """
        # Stop any running progress indicator
        if self._progress:
            self._progress.stop()
            self._progress = None
        
        if self.context.mode == OutputMode.JSON:
            self._complete_json(result)
        elif self.context.mode == OutputMode.QUIET:
            self._complete_quiet(result)
        elif self.context.mode == OutputMode.VERBOSE:
            self._complete_verbose(result)
        else:  # MINIMAL
            self._complete_minimal(result)
    
    def _complete_minimal(self, result: OperationResult) -> None:
        """Output minimal format result."""
        if result.success:
            duration = format_duration(result.duration_seconds)
            cost = format_cost(result.cost_usd)
            path = result.report_path or ""
            # Ensure path ends with / for directories
            if path and not path.endswith("/"):
                path = path + "/"
            self._console.print(
                f"[green]OK[/green] Research complete ({duration}, {cost}) -> {path}"
            )
        else:
            self._console.print(
                f"[red]ERROR[/red] Research failed: {result.error or 'Unknown error'}"
            )
    
    def _complete_verbose(self, result: OperationResult) -> None:
        """Output verbose format result."""
        if result.success:
            duration = format_duration(result.duration_seconds)
            cost = format_cost(result.cost_usd)
            self._console.print()
            self._console.print("[bold green]Research Complete[/bold green]")
            self._console.print(f"  Duration: {duration}")
            self._console.print(f"  Cost: {cost}")
            if result.report_path:
                self._console.print(f"  Report: {result.report_path}")
            if result.job_id:
                self._console.print(f"  Job ID: {result.job_id}")
            self._console.print()
        else:
            self._console.print()
            self._console.print("[bold red]Research Failed[/bold red]")
            self._console.print(f"  Error: {result.error or 'Unknown error'}")
            if result.error_code:
                self._console.print(f"  Code: {result.error_code}")
            self._console.print()
    
    def _complete_json(self, result: OperationResult) -> None:
        """Output JSON format result."""
        # JSON mode outputs only the JSON, nothing else
        print(result.to_json())
    
    def _complete_quiet(self, result: OperationResult) -> None:
        """Output quiet format result (errors to stderr only)."""
        if not result.success:
            self._stderr_console.print(result.error or "Unknown error")
    
    def error(self, message: str, code: Optional[str] = None) -> None:
        """Show error message.
        
        Args:
            message: Error message to display
            code: Optional error code
        """
        # Stop any running progress indicator
        if self._progress:
            self._progress.stop()
            self._progress = None
        
        if self.context.mode == OutputMode.JSON:
            result = OperationResult(
                success=False,
                duration_seconds=time.time() - (self.context.start_time or time.time()),
                cost_usd=0.0,
                error=message,
                error_code=code
            )
            print(result.to_json())
        elif self.context.mode == OutputMode.QUIET:
            self._stderr_console.print(message)
        else:
            self._console.print(f"[red]ERROR[/red] {message}")


# Type variable for decorator
F = TypeVar("F", bound=Callable[..., Any])


def output_options(f: F) -> F:
    """Decorator to add output mode options to a Click command.
    
    Adds --verbose/-v, --json, and --quiet/-q flags to the command.
    Validates mutual exclusivity and creates OutputContext.
    
    Usage:
        @click.command()
        @output_options
        def my_command(output_context: OutputContext, ...):
            formatter = OutputFormatter(output_context)
            ...
    """
    @click.option(
        "--verbose", "-v",
        is_flag=True,
        help="Show detailed output"
    )
    @click.option(
        "--json", "json_output",
        is_flag=True,
        help="Output as JSON for scripting"
    )
    @click.option(
        "--quiet", "-q",
        is_flag=True,
        help="Suppress all output except errors"
    )
    @wraps(f)
    def wrapper(*args, verbose: bool, json_output: bool, quiet: bool, **kwargs):
        try:
            output_context = OutputContext.from_flags(
                verbose=verbose,
                json_output=json_output,
                quiet=quiet
            )
        except OutputModeConflictError as e:
            raise click.UsageError(str(e))
        
        return f(*args, output_context=output_context, **kwargs)
    
    return wrapper  # type: ignore
