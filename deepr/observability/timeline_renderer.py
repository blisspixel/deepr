"""CLI timeline visualization for temporal knowledge tracking.

Renders research timelines in the terminal with colored output
showing finding evolution, hypothesis changes, and phase transitions.

Usage:
    from deepr.observability.timeline_renderer import TimelineRenderer
    from deepr.observability.temporal_tracker import TemporalKnowledgeTracker

    tracker = TemporalKnowledgeTracker()
    # ... record findings ...

    renderer = TimelineRenderer()
    renderer.render_timeline(tracker)
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from deepr.observability.temporal_tracker import (
    TemporalKnowledgeTracker,
    TemporalFinding,
    Hypothesis,
    HypothesisEvolution,
    FindingType,
    EvolutionType,
)


# ANSI color codes for terminal output
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Finding types
    FACT = "\033[94m"       # Blue
    OBSERVATION = "\033[96m"  # Cyan
    INFERENCE = "\033[93m"   # Yellow
    HYPOTHESIS = "\033[95m"  # Magenta
    CONTRADICTION = "\033[91m"  # Red
    CONFIRMATION = "\033[92m"  # Green

    # Evolution types
    STRENGTHENED = "\033[92m"  # Green
    WEAKENED = "\033[91m"      # Red
    MODIFIED = "\033[93m"      # Yellow
    INVALIDATED = "\033[91m"   # Red
    CREATED = "\033[94m"       # Blue

    # Structure
    PHASE = "\033[96m"       # Cyan
    TIME = "\033[90m"        # Gray
    BORDER = "\033[90m"      # Gray


@dataclass
class TimelineEntry:
    """A single entry in the timeline."""
    timestamp: datetime
    phase: int
    entry_type: str  # 'finding', 'hypothesis_create', 'hypothesis_update'
    data: Any
    color: str


class TimelineRenderer:
    """Renders temporal knowledge timelines for CLI display.

    Provides multiple visualization modes:
    - Full timeline with all events
    - Phase-by-phase summary
    - Hypothesis evolution charts
    - Confidence trend visualization
    """

    def __init__(self, use_colors: bool = True, max_width: int = 80):
        """Initialize the renderer.

        Args:
            use_colors: Whether to use ANSI colors
            max_width: Maximum line width for output
        """
        self.use_colors = use_colors
        self.max_width = max_width

    def render_timeline(
        self,
        tracker: TemporalKnowledgeTracker,
        phase_filter: Optional[int] = None,
        show_hypotheses: bool = True,
        compact: bool = False,
    ) -> str:
        """Render the full timeline.

        Args:
            tracker: TemporalKnowledgeTracker with data
            phase_filter: Optional phase to filter to
            show_hypotheses: Whether to include hypothesis evolution
            compact: Use compact mode with less detail

        Returns:
            Formatted timeline string
        """
        lines = []

        # Header
        lines.append(self._header("Research Timeline"))
        lines.append(self._dim(f"Job ID: {tracker.job_id}"))
        lines.append("")

        # Collect all events
        events = self._collect_events(tracker, phase_filter)

        if not events:
            lines.append("No events to display.")
            return "\n".join(lines)

        # Group by phase
        phases: Dict[int, List[TimelineEntry]] = {}
        for event in events:
            if event.phase not in phases:
                phases[event.phase] = []
            phases[event.phase].append(event)

        # Render each phase
        for phase_num in sorted(phases.keys()):
            phase_events = phases[phase_num]
            lines.append(self._phase_header(phase_num, len(phase_events)))

            for event in phase_events:
                if compact:
                    lines.append(self._render_event_compact(event))
                else:
                    lines.extend(self._render_event(event))

            lines.append("")

        # Summary
        lines.append(self._header("Summary"))
        lines.extend(self._render_summary(tracker))

        return "\n".join(lines)

    def render_hypothesis_evolution(
        self,
        tracker: TemporalKnowledgeTracker,
        hypothesis_id: Optional[str] = None,
    ) -> str:
        """Render hypothesis evolution visualization.

        Args:
            tracker: TemporalKnowledgeTracker with data
            hypothesis_id: Optional specific hypothesis to show

        Returns:
            Formatted evolution string
        """
        lines = []
        lines.append(self._header("Hypothesis Evolution"))

        hypotheses = tracker.hypotheses
        if hypothesis_id:
            if hypothesis_id in hypotheses:
                hypotheses = {hypothesis_id: hypotheses[hypothesis_id]}
            else:
                return f"Hypothesis {hypothesis_id} not found."

        for h_id, hypothesis in hypotheses.items():
            lines.append("")
            lines.append(self._hypothesis_header(hypothesis))
            lines.extend(self._render_evolution_history(hypothesis))

        return "\n".join(lines)

    def render_confidence_chart(
        self,
        tracker: TemporalKnowledgeTracker,
        hypothesis_id: str,
        width: int = 40,
    ) -> str:
        """Render ASCII confidence trend chart.

        Args:
            tracker: TemporalKnowledgeTracker with data
            hypothesis_id: Hypothesis to chart
            width: Chart width in characters

        Returns:
            ASCII chart string
        """
        trend = tracker.get_confidence_trend(hypothesis_id)

        if not trend:
            return f"No trend data for hypothesis {hypothesis_id}"

        lines = []
        lines.append(self._header(f"Confidence Trend: {hypothesis_id}"))
        lines.append("")

        # ASCII bar chart
        for point in trend:
            conf = point["confidence"]
            bar_width = int(conf * width)
            bar = "█" * bar_width + "░" * (width - bar_width)

            color = Colors.RESET
            if conf >= 0.7:
                color = Colors.STRENGTHENED
            elif conf <= 0.3:
                color = Colors.WEAKENED

            lines.append(
                f"{self._colorize(bar, color)} "
                f"{conf:.2f} ({point['evolution_type']})"
            )

        return "\n".join(lines)

    def render_phase_summary(
        self,
        tracker: TemporalKnowledgeTracker,
    ) -> str:
        """Render phase-by-phase summary.

        Args:
            tracker: TemporalKnowledgeTracker with data

        Returns:
            Formatted summary string
        """
        lines = []
        lines.append(self._header("Phase Summary"))

        for phase_num in sorted(tracker.phase_summaries.keys()):
            summary = tracker.phase_summaries[phase_num]
            lines.append("")
            lines.append(self._phase_header(phase_num, summary["finding_count"]))

            # Finding type breakdown
            for ftype, count in summary.get("finding_types", {}).items():
                color = self._get_finding_type_color(FindingType(ftype))
                lines.append(f"  {self._colorize(ftype, color)}: {count}")

            avg_conf = summary.get("avg_confidence", 0)
            conf_bar = self._confidence_bar(avg_conf, 20)
            lines.append(f"  Avg Confidence: {conf_bar} {avg_conf:.2f}")

        return "\n".join(lines)

    def _collect_events(
        self,
        tracker: TemporalKnowledgeTracker,
        phase_filter: Optional[int],
    ) -> List[TimelineEntry]:
        """Collect all events into timeline entries.

        Args:
            tracker: Tracker with data
            phase_filter: Optional phase filter

        Returns:
            Sorted list of TimelineEntry
        """
        events = []

        # Add findings
        for finding in tracker.findings:
            if phase_filter is not None and finding.phase != phase_filter:
                continue

            events.append(TimelineEntry(
                timestamp=finding.timestamp,
                phase=finding.phase,
                entry_type="finding",
                data=finding,
                color=self._get_finding_type_color(finding.finding_type),
            ))

        # Add hypothesis events
        for hypothesis in tracker.hypotheses.values():
            for evolution in hypothesis.evolution_history:
                # Determine phase from triggering finding or default to created phase
                phase = hypothesis.phase_created
                if evolution.triggering_finding_id:
                    triggering = tracker._finding_index.get(evolution.triggering_finding_id)
                    if triggering:
                        phase = triggering.phase

                if phase_filter is not None and phase != phase_filter:
                    continue

                events.append(TimelineEntry(
                    timestamp=evolution.timestamp,
                    phase=phase,
                    entry_type="hypothesis_update",
                    data=evolution,
                    color=self._get_evolution_color(evolution.evolution_type),
                ))

        # Sort by timestamp
        return sorted(events, key=lambda e: e.timestamp)

    def _render_event(self, event: TimelineEntry) -> List[str]:
        """Render a single event with full details.

        Args:
            event: TimelineEntry to render

        Returns:
            List of formatted lines
        """
        lines = []
        time_str = event.timestamp.strftime("%H:%M:%S")

        if event.entry_type == "finding":
            finding = event.data
            type_str = finding.finding_type.value.upper()

            lines.append(
                f"  {self._dim(time_str)} "
                f"{self._colorize(f'[{type_str}]', event.color)} "
            )
            # Truncate text if too long
            text = finding.text[:self.max_width - 25]
            if len(finding.text) > self.max_width - 25:
                text += "..."
            lines.append(f"    {text}")

            if finding.source:
                lines.append(f"    {self._dim('Source:')} {finding.source}")

            conf_bar = self._confidence_bar(finding.confidence, 10)
            lines.append(f"    {self._dim('Confidence:')} {conf_bar} {finding.confidence:.2f}")

        elif event.entry_type == "hypothesis_update":
            evolution = event.data
            evo_type = evolution.evolution_type.value.upper()

            lines.append(
                f"  {self._dim(time_str)} "
                f"{self._colorize(f'[{evo_type}]', event.color)} "
                f"Hypothesis {evolution.hypothesis_id}"
            )
            lines.append(f"    {evolution.reason}")

            if evolution.new_state:
                conf = evolution.new_state.confidence
                conf_bar = self._confidence_bar(conf, 10)
                lines.append(f"    {self._dim('New confidence:')} {conf_bar} {conf:.2f}")

        return lines

    def _render_event_compact(self, event: TimelineEntry) -> str:
        """Render a single event in compact mode.

        Args:
            event: TimelineEntry to render

        Returns:
            Single formatted line
        """
        time_str = event.timestamp.strftime("%H:%M")

        if event.entry_type == "finding":
            finding = event.data
            type_char = finding.finding_type.value[0].upper()
            text = finding.text[:40] + "..." if len(finding.text) > 40 else finding.text
            return f"  {self._dim(time_str)} {self._colorize(type_char, event.color)} {text}"

        elif event.entry_type == "hypothesis_update":
            evolution = event.data
            evo_char = evolution.evolution_type.value[0].upper()
            return (
                f"  {self._dim(time_str)} "
                f"{self._colorize(evo_char, event.color)} "
                f"H:{evolution.hypothesis_id} - {evolution.reason[:30]}"
            )

        return ""

    def _render_evolution_history(self, hypothesis: Hypothesis) -> List[str]:
        """Render evolution history for a hypothesis.

        Args:
            hypothesis: Hypothesis to render

        Returns:
            List of formatted lines
        """
        lines = []

        for i, evolution in enumerate(hypothesis.evolution_history):
            color = self._get_evolution_color(evolution.evolution_type)
            prefix = "├──" if i < len(hypothesis.evolution_history) - 1 else "└──"

            conf = evolution.new_state.confidence
            conf_bar = self._confidence_bar(conf, 15)

            lines.append(
                f"  {self._dim(prefix)} "
                f"{self._colorize(evolution.evolution_type.value, color)} "
                f"{conf_bar} {conf:.2f}"
            )
            lines.append(f"  │   {evolution.reason}")

        return lines

    def _render_summary(self, tracker: TemporalKnowledgeTracker) -> List[str]:
        """Render overall summary statistics.

        Args:
            tracker: Tracker with data

        Returns:
            List of formatted lines
        """
        lines = []

        total_findings = len(tracker.findings)
        total_hypotheses = len(tracker.hypotheses)
        active_hypotheses = len([h for h in tracker.hypotheses.values()
                                 if h.current_state.confidence > 0])

        lines.append(f"  Total Findings: {total_findings}")
        lines.append(f"  Hypotheses: {active_hypotheses} active / {total_hypotheses} total")
        lines.append(f"  Phases: {len(tracker.phase_summaries)}")

        # Finding type distribution
        type_counts: Dict[str, int] = {}
        for finding in tracker.findings:
            t = finding.finding_type.value
            type_counts[t] = type_counts.get(t, 0) + 1

        if type_counts:
            lines.append("")
            lines.append("  Finding Types:")
            for ftype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
                pct = count / total_findings * 100
                color = self._get_finding_type_color(FindingType(ftype))
                lines.append(f"    {self._colorize(ftype, color)}: {count} ({pct:.0f}%)")

        return lines

    def _header(self, text: str) -> str:
        """Create a header line."""
        return self._colorize(f"═══ {text} ═══", Colors.BORDER + Colors.BOLD)

    def _phase_header(self, phase: int, event_count: int) -> str:
        """Create a phase header."""
        return self._colorize(f"── Phase {phase} ({event_count} events) ──", Colors.PHASE)

    def _hypothesis_header(self, hypothesis: Hypothesis) -> str:
        """Create a hypothesis header."""
        conf = hypothesis.current_state.confidence
        status = "ACTIVE" if conf > 0 else "INVALIDATED"
        return self._colorize(
            f"─ {hypothesis.id}: {status} (conf: {conf:.2f}) ─",
            Colors.HYPOTHESIS
        )

    def _confidence_bar(self, confidence: float, width: int) -> str:
        """Create an ASCII confidence bar.

        Args:
            confidence: Confidence value (0-1)
            width: Bar width in characters

        Returns:
            ASCII bar string
        """
        filled = int(confidence * width)
        bar = "█" * filled + "░" * (width - filled)

        if confidence >= 0.7:
            return self._colorize(bar, Colors.STRENGTHENED)
        elif confidence <= 0.3:
            return self._colorize(bar, Colors.WEAKENED)
        else:
            return self._colorize(bar, Colors.MODIFIED)

    def _colorize(self, text: str, color: str) -> str:
        """Apply color to text if colors are enabled.

        Args:
            text: Text to colorize
            color: ANSI color code

        Returns:
            Colorized text (or plain text if colors disabled)
        """
        if not self.use_colors:
            return text
        return f"{color}{text}{Colors.RESET}"

    def _dim(self, text: str) -> str:
        """Make text dim."""
        return self._colorize(text, Colors.DIM)

    def _get_finding_type_color(self, finding_type: FindingType) -> str:
        """Get color for a finding type."""
        color_map = {
            FindingType.FACT: Colors.FACT,
            FindingType.OBSERVATION: Colors.OBSERVATION,
            FindingType.INFERENCE: Colors.INFERENCE,
            FindingType.HYPOTHESIS: Colors.HYPOTHESIS,
            FindingType.CONTRADICTION: Colors.CONTRADICTION,
            FindingType.CONFIRMATION: Colors.CONFIRMATION,
        }
        return color_map.get(finding_type, Colors.RESET)

    def _get_evolution_color(self, evolution_type: EvolutionType) -> str:
        """Get color for an evolution type."""
        color_map = {
            EvolutionType.CREATED: Colors.CREATED,
            EvolutionType.STRENGTHENED: Colors.STRENGTHENED,
            EvolutionType.WEAKENED: Colors.WEAKENED,
            EvolutionType.MODIFIED: Colors.MODIFIED,
            EvolutionType.INVALIDATED: Colors.INVALIDATED,
            EvolutionType.MERGED: Colors.MODIFIED,
            EvolutionType.SPLIT: Colors.MODIFIED,
        }
        return color_map.get(evolution_type, Colors.RESET)
