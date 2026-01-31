"""Progress feedback system for CLI operations.

Provides unified progress feedback with:
- Animated spinners for network waits
- Phase completion messages with timing and cost
- Long operation warnings
- Rich library integration for consistent output
"""

import time
from contextlib import contextmanager
from typing import Optional, Generator
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.console import Console

console = Console()


class ProgressFeedback:
    """Unified progress feedback for CLI operations.
    
    Usage:
        progress = ProgressFeedback()
        
        with progress.operation("Uploading files..."):
            # do work
            pass
        
        progress.phase_complete("Upload complete", cost=0.15)
    """
    
    # Threshold for showing "still working" message
    LONG_OPERATION_THRESHOLD = 15.0  # seconds
    
    def __init__(self):
        self.start_time: Optional[float] = None
        self.phase: str = ""
        self._warned_long_operation = False
    
    @contextmanager
    def operation(self, description: str) -> Generator[Progress, None, None]:
        """Context manager for operations with spinner.
        
        Args:
            description: Description to show during operation
            
        Yields:
            Rich Progress object for advanced usage
        """
        self.start_time = time.time()
        self.phase = description
        self._warned_long_operation = False
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task(description, total=None)
            
            try:
                yield progress
            finally:
                elapsed = time.time() - self.start_time
                progress.update(task, completed=True)
    
    def phase_complete(self, message: str, cost: Optional[float] = None) -> None:
        """Mark phase complete with optional cost.
        
        Args:
            message: Completion message
            cost: Optional cost in dollars
        """
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        cost_str = f", ${cost:.2f}" if cost else ""
        console.print(f"[green]✓[/green] {message} ({elapsed:.1f}s{cost_str})")
    
    def phase_error(self, message: str) -> None:
        """Mark phase as failed.
        
        Args:
            message: Error message
        """
        console.print(f"[red]✗[/red] {message}")
    
    def long_operation_warning(self) -> None:
        """Show warning for long operations.
        
        Only shows once per operation to avoid spam.
        """
        if not self._warned_long_operation:
            console.print("[dim]Still working... Ctrl+C to cancel (uploads are safe)[/dim]")
            self._warned_long_operation = True
    
    def check_long_operation(self) -> None:
        """Check if operation is taking long and warn if needed."""
        if self.start_time:
            elapsed = time.time() - self.start_time
            if elapsed > self.LONG_OPERATION_THRESHOLD:
                self.long_operation_warning()
    
    def status(self, message: str) -> None:
        """Show status message during operation.
        
        Args:
            message: Status message
        """
        console.print(f"[dim]{message}[/dim]")
    
    def info(self, message: str) -> None:
        """Show info message.
        
        Args:
            message: Info message
        """
        console.print(f"[cyan]ℹ[/cyan] {message}")


# Convenience functions for simple usage
_default_progress = ProgressFeedback()


def with_progress(description: str):
    """Decorator/context manager for operations with progress feedback.
    
    Usage:
        with with_progress("Processing..."):
            do_work()
    """
    return _default_progress.operation(description)


def complete(message: str, cost: Optional[float] = None) -> None:
    """Mark operation complete."""
    _default_progress.phase_complete(message, cost)


def error(message: str) -> None:
    """Mark operation failed."""
    _default_progress.phase_error(message)


def status(message: str) -> None:
    """Show status message."""
    _default_progress.status(message)
