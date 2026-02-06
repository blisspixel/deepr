"""Real-time progress tracking for long-running research operations.

Provides polling-based progress updates with phase detection and
partial result streaming when supported by the provider.

Usage:
    from deepr.cli.realtime_progress import ResearchProgressTracker

    tracker = ResearchProgressTracker(provider)

    # Track a research job with live updates
    result = await tracker.track_job(
        job_id="job123",
        poll_interval=5,
        show_partial=True
    )
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn
from rich.table import Table
from rich.text import Text

from deepr.providers.base import DeepResearchProvider, ResearchResponse


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class ResearchPhase(Enum):
    """Phases of a deep research operation."""

    QUEUED = "queued"
    INITIALIZING = "initializing"
    SEARCHING = "searching"
    ANALYZING = "analyzing"
    SYNTHESIZING = "synthesizing"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


# Phase order for progress calculation
PHASE_ORDER = [
    ResearchPhase.QUEUED,
    ResearchPhase.INITIALIZING,
    ResearchPhase.SEARCHING,
    ResearchPhase.ANALYZING,
    ResearchPhase.SYNTHESIZING,
    ResearchPhase.FINALIZING,
    ResearchPhase.COMPLETED,
]


@dataclass
class PhaseUpdate:
    """Update for a research phase."""

    phase: ResearchPhase
    message: str
    timestamp: datetime = field(default_factory=_utc_now)
    details: Optional[str] = None
    progress_pct: float = 0.0


@dataclass
class ProgressState:
    """Current state of research progress."""

    job_id: str
    current_phase: ResearchPhase
    phase_history: list[PhaseUpdate] = field(default_factory=list)
    partial_output: Optional[str] = None
    estimated_completion_pct: float = 0.0
    elapsed_seconds: float = 0.0
    poll_count: int = 0
    last_status: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "current_phase": self.current_phase.value,
            "phase_history": [
                {"phase": p.phase.value, "message": p.message, "timestamp": p.timestamp.isoformat()}
                for p in self.phase_history
            ],
            "estimated_completion_pct": self.estimated_completion_pct,
            "elapsed_seconds": self.elapsed_seconds,
            "poll_count": self.poll_count,
        }


class ResearchProgressTracker:
    """Tracks research progress with real-time updates.

    Polls the provider status API and displays progress with:
    - Phase detection based on status and timing
    - Progress bar showing estimated completion
    - Partial result display when available
    - Phase transition messages

    Attributes:
        provider: DeepResearchProvider instance
        console: Rich console for output
    """

    # Default poll interval in seconds
    DEFAULT_POLL_INTERVAL = 5

    # Phase timing estimates (seconds) for progress calculation
    PHASE_TIMING = {
        ResearchPhase.QUEUED: 5,
        ResearchPhase.INITIALIZING: 10,
        ResearchPhase.SEARCHING: 60,
        ResearchPhase.ANALYZING: 90,
        ResearchPhase.SYNTHESIZING: 60,
        ResearchPhase.FINALIZING: 15,
    }

    def __init__(
        self,
        provider: DeepResearchProvider,
        console: Optional[Console] = None,
    ):
        """Initialize the progress tracker.

        Args:
            provider: Provider to poll for status
            console: Optional Rich console
        """
        self.provider = provider
        self.console = console or Console()
        self._callbacks: list[Callable[[ProgressState], None]] = []

    def add_callback(self, callback: Callable[[ProgressState], None]):
        """Add a callback for progress updates.

        Args:
            callback: Function called with ProgressState on each update
        """
        self._callbacks.append(callback)

    async def track_job(
        self,
        job_id: str,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = 600,
        show_partial: bool = True,
        quiet: bool = False,
    ) -> ResearchResponse:
        """Track a research job with live progress updates.

        Args:
            job_id: Job identifier to track
            poll_interval: Seconds between status polls
            timeout: Maximum seconds to wait
            show_partial: Show partial results when available
            quiet: Suppress progress output

        Returns:
            Final ResearchResponse

        Raises:
            TimeoutError: If timeout exceeded
            Exception: If job fails
        """
        state = ProgressState(
            job_id=job_id,
            current_phase=ResearchPhase.QUEUED,
        )

        start_time = _utc_now()

        if not quiet:
            await self._track_with_display(state, poll_interval, timeout, show_partial, start_time)
        else:
            await self._track_quietly(state, poll_interval, timeout, start_time)

        # Get final result
        response = await self.provider.get_status(job_id)

        if response.status == "failed":
            raise Exception(f"Research job failed: {response.error or 'Unknown error'}")

        return response

    async def _track_with_display(
        self,
        state: ProgressState,
        poll_interval: float,
        timeout: float,
        show_partial: bool,
        start_time: datetime,
    ):
        """Track with live Rich display."""
        with Live(self._render_progress(state), console=self.console, refresh_per_second=2) as live:
            while True:
                # Check timeout
                state.elapsed_seconds = (_utc_now() - start_time).total_seconds()
                if state.elapsed_seconds > timeout:
                    raise TimeoutError(f"Research timed out after {timeout}s")

                # Poll status
                response = await self.provider.get_status(state.job_id)
                state.poll_count += 1
                state.last_status = response.status

                # Detect phase from response
                new_phase = self._detect_phase(response, state)
                if new_phase != state.current_phase:
                    self._record_phase_transition(state, new_phase)

                # Update progress estimate
                state.estimated_completion_pct = self._estimate_progress(state)

                # Check for partial output
                if show_partial and response.output:
                    state.partial_output = self._extract_partial_output(response)

                # Update display
                live.update(self._render_progress(state))

                # Notify callbacks
                for callback in self._callbacks:
                    callback(state)

                # Check completion
                if response.status in ("completed", "failed", "cancelled"):
                    if response.status == "failed":
                        state.error = response.error
                    break

                await asyncio.sleep(poll_interval)

    async def _track_quietly(
        self,
        state: ProgressState,
        poll_interval: float,
        timeout: float,
        start_time: datetime,
    ):
        """Track without display output."""
        while True:
            state.elapsed_seconds = (_utc_now() - start_time).total_seconds()
            if state.elapsed_seconds > timeout:
                raise TimeoutError(f"Research timed out after {timeout}s")

            response = await self.provider.get_status(state.job_id)
            state.poll_count += 1
            state.last_status = response.status

            new_phase = self._detect_phase(response, state)
            if new_phase != state.current_phase:
                self._record_phase_transition(state, new_phase)

            state.estimated_completion_pct = self._estimate_progress(state)

            for callback in self._callbacks:
                callback(state)

            if response.status in ("completed", "failed", "cancelled"):
                break

            await asyncio.sleep(poll_interval)

    def _detect_phase(
        self,
        response: ResearchResponse,
        state: ProgressState,
    ) -> ResearchPhase:
        """Detect current phase from response and timing.

        Args:
            response: Current status response
            state: Current progress state

        Returns:
            Detected ResearchPhase
        """
        status = response.status

        if status == "completed":
            return ResearchPhase.COMPLETED
        if status == "failed":
            return ResearchPhase.FAILED
        if status == "queued":
            return ResearchPhase.QUEUED

        # For in_progress, estimate phase from elapsed time
        if status == "in_progress":
            elapsed = state.elapsed_seconds

            cumulative = 0
            for phase in PHASE_ORDER[1:-1]:  # Skip QUEUED and COMPLETED
                phase_time = self.PHASE_TIMING.get(phase, 30)
                cumulative += phase_time
                if elapsed < cumulative:
                    return phase

            return ResearchPhase.FINALIZING

        return state.current_phase

    def _record_phase_transition(
        self,
        state: ProgressState,
        new_phase: ResearchPhase,
    ):
        """Record a phase transition.

        Args:
            state: Current state
            new_phase: New phase
        """
        messages = {
            ResearchPhase.INITIALIZING: "Initializing research context...",
            ResearchPhase.SEARCHING: "Searching for relevant information...",
            ResearchPhase.ANALYZING: "Analyzing gathered information...",
            ResearchPhase.SYNTHESIZING: "Synthesizing findings...",
            ResearchPhase.FINALIZING: "Finalizing report...",
            ResearchPhase.COMPLETED: "Research complete!",
            ResearchPhase.FAILED: "Research failed",
        }

        state.phase_history.append(
            PhaseUpdate(
                phase=new_phase,
                message=messages.get(new_phase, f"Phase: {new_phase.value}"),
            )
        )
        state.current_phase = new_phase

    def _estimate_progress(self, state: ProgressState) -> float:
        """Estimate overall progress percentage.

        Args:
            state: Current state

        Returns:
            Progress percentage (0-100)
        """
        if state.current_phase == ResearchPhase.COMPLETED:
            return 100.0
        if state.current_phase == ResearchPhase.FAILED:
            return state.estimated_completion_pct

        # Calculate based on phase order
        try:
            phase_index = PHASE_ORDER.index(state.current_phase)
        except ValueError:
            return 0.0

        # Base progress from phase
        base_progress = (phase_index / len(PHASE_ORDER)) * 100

        # Add within-phase progress based on timing
        phase_time = self.PHASE_TIMING.get(state.current_phase, 30)
        time_in_phase = state.elapsed_seconds - sum(
            self.PHASE_TIMING.get(PHASE_ORDER[i], 0) for i in range(phase_index)
        )
        within_phase_progress = min(time_in_phase / phase_time, 0.95) * (100 / len(PHASE_ORDER))

        return min(99.0, base_progress + within_phase_progress)

    def _extract_partial_output(self, response: ResearchResponse) -> Optional[str]:
        """Extract partial output from response if available.

        Args:
            response: Current response

        Returns:
            Partial output text or None
        """
        if not response.output:
            return None

        # Try to extract text from output blocks
        texts = []
        for block in response.output:
            if block.get("type") == "message":
                for content in block.get("content", []):
                    if text := content.get("text"):
                        texts.append(text[:200])  # Truncate for preview

        if texts:
            return texts[0] + ("..." if len(texts[0]) >= 200 else "")

        return None

    def _render_progress(self, state: ProgressState) -> Panel:
        """Render progress display.

        Args:
            state: Current progress state

        Returns:
            Rich Panel with progress info
        """
        # Build progress content
        content = Table.grid(padding=(0, 2))
        content.add_column(style="bold cyan", justify="right")
        content.add_column()

        # Phase indicator
        phase_text = Text()
        for _i, phase in enumerate(PHASE_ORDER[:-1]):  # Exclude COMPLETED
            if phase == state.current_phase:
                phase_text.append(f"● {phase.value} ", style="bold green")
            elif PHASE_ORDER.index(phase) < PHASE_ORDER.index(state.current_phase):
                phase_text.append(f"✓ {phase.value} ", style="dim green")
            else:
                phase_text.append(f"○ {phase.value} ", style="dim")

        content.add_row("Phase:", phase_text)

        # Progress bar
        progress_bar = Progress(
            BarColumn(bar_width=40),
            TaskProgressColumn(),
            transient=True,
        )
        progress_bar.add_task("", total=100, completed=state.estimated_completion_pct)

        content.add_row("Progress:", progress_bar)

        # Elapsed time
        mins, secs = divmod(int(state.elapsed_seconds), 60)
        content.add_row("Elapsed:", f"{mins}m {secs}s")

        # Current message
        if state.phase_history:
            content.add_row("Status:", state.phase_history[-1].message)

        # Partial output preview
        if state.partial_output:
            content.add_row("Preview:", Text(state.partial_output, style="dim italic"))

        # Error if any
        if state.error:
            content.add_row("Error:", Text(state.error, style="bold red"))

        return Panel(
            content,
            title=f"[bold]Research Progress[/bold] ({state.job_id[:8]}...)",
            border_style="cyan",
        )


async def track_research_progress(
    provider: DeepResearchProvider,
    job_id: str,
    poll_interval: float = 5,
    timeout: float = 600,
    quiet: bool = False,
) -> ResearchResponse:
    """Convenience function to track research progress.

    Args:
        provider: Provider instance
        job_id: Job to track
        poll_interval: Poll interval in seconds
        timeout: Timeout in seconds
        quiet: Suppress output

    Returns:
        Final ResearchResponse
    """
    tracker = ResearchProgressTracker(provider)
    return await tracker.track_job(
        job_id=job_id,
        poll_interval=poll_interval,
        timeout=timeout,
        quiet=quiet,
    )
