"""ThoughtStream - Structured decision records with dual sink architecture.

Provides visible thinking for expert reasoning while maintaining security:
- Public display: Structured decision records (not raw chain-of-thought)
- Private audit: Full JSONL logs for debugging and analysis
- Redaction: Prevents prompt injection leakage and sensitive data exposure

Usage:
    stream = ThoughtStream(expert_name="quantum_expert", verbose=True)

    with stream.planning("Analyzing query complexity"):
        # ... reasoning code ...
        stream.emit(ThoughtType.PLAN_STEP, "Breaking into 3 sub-questions")

    stream.decision("Using vector search", confidence=0.9, evidence=["doc1.md"])
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


class ThoughtType(Enum):
    """Types of structured decision records."""

    PLAN_STEP = "plan_step"  # Planning phase step
    TOOL_CALL = "tool_call"  # Tool invocation
    EVIDENCE_FOUND = "evidence_found"  # Evidence discovered
    CONFIDENCE = "confidence"  # Confidence assessment
    DECISION = "decision"  # Final decision made
    SEARCH = "search"  # Search operation
    SYNTHESIS = "synthesis"  # Synthesizing information
    ERROR = "error"  # Error encountered


@dataclass
class Thought:
    """A structured thought/decision record.

    Attributes:
        thought_type: Category of thought
        public_text: Safe text for user display (redacted)
        private_payload: Full details for audit logs (may contain sensitive data)
        confidence: Optional confidence score (0.0-1.0)
        evidence_refs: Optional list of evidence source IDs
        timestamp: When the thought occurred
        metadata: Additional structured data
    """

    thought_type: ThoughtType
    public_text: str
    private_payload: Optional[dict[str, Any]] = None
    confidence: Optional[float] = None
    evidence_refs: Optional[list[str]] = None
    timestamp: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "thought_type": self.thought_type.value,
            "public_text": self.public_text,
            "private_payload": self.private_payload,
            "confidence": self.confidence,
            "evidence_refs": self.evidence_refs,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class RedactionRules:
    """Rules for redacting sensitive content from public display.

    Prevents:
    - Prompt injection leakage
    - API key exposure
    - System prompt exposure
    - Private context leakage
    """

    # Patterns that indicate prompt injection attempts
    INJECTION_PATTERNS = [
        r"ignore\s+(previous|all|above)\s+instructions?",
        r"ignore\s+all\s+previous\s+instructions?",
        r"please\s+ignore\s+all\s+previous",
        r"disregard\s+(previous|all|above)",
        r"forget\s+(everything|all|previous)",
        r"new\s+instructions?:",
        r"system\s*:\s*",
        r"<\|?system\|?>",
        r"\[INST\]",
        r"<<SYS>>",
        r"print\s+(your\s+)?(system\s+)?prompt",
        r"reveal\s+(your\s+)?(system\s+)?prompt",
        r"show\s+(me\s+)?(your\s+)?instructions?",
        r"what\s+are\s+your\s+instructions?",
    ]

    # Patterns for sensitive data
    SENSITIVE_PATTERNS = [
        r"(sk-[a-zA-Z0-9]{20,})",  # OpenAI API keys
        r"(xai-[a-zA-Z0-9]{20,})",  # xAI API keys
        r"(AIza[a-zA-Z0-9_-]{30,})",  # Google API keys (30+ chars after AIza)
        r"([a-f0-9]{32})",  # Generic 32-char hex (potential secrets)
        r"(Bearer\s+[a-zA-Z0-9._-]+)",  # Bearer tokens
        r"(password\s*[=:]\s*\S+)",  # Passwords
        r"(api[_-]?key\s*[=:]\s*\S+)",  # API keys in config
    ]

    # System prompt indicators
    SYSTEM_PROMPT_PATTERNS = [
        r"you\s+are\s+an?\s+AI",
        r"you\s+are\s+a\s+helpful",
        r"your\s+role\s+is",
        r"as\s+an?\s+AI\s+assistant",
        r"CRITICAL\s+RULES?:",
        r"IMPORTANT\s+INSTRUCTIONS?:",
    ]

    @classmethod
    def redact(cls, text: str) -> str:
        """Redact sensitive content from text.

        Args:
            text: Raw text that may contain sensitive content

        Returns:
            Redacted text safe for public display
        """
        if not text:
            return text

        redacted = text

        # Check for and redact injection attempts
        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, redacted, re.IGNORECASE):
                redacted = re.sub(pattern, "[REDACTED: potential injection]", redacted, flags=re.IGNORECASE)

        # Redact sensitive data patterns
        for pattern in cls.SENSITIVE_PATTERNS:
            redacted = re.sub(pattern, "[REDACTED: sensitive]", redacted)

        # Redact system prompt content
        for pattern in cls.SYSTEM_PROMPT_PATTERNS:
            if re.search(pattern, redacted, re.IGNORECASE):
                # Don't show system prompt content in public display
                redacted = re.sub(pattern, "[REDACTED: internal]", redacted, flags=re.IGNORECASE)

        return redacted

    @classmethod
    def is_safe(cls, text: str) -> bool:
        """Check if text is safe for public display.

        Args:
            text: Text to check

        Returns:
            True if text contains no sensitive patterns
        """
        if not text:
            return True

        # Check all pattern categories
        all_patterns = cls.INJECTION_PATTERNS + cls.SENSITIVE_PATTERNS + cls.SYSTEM_PROMPT_PATTERNS

        for pattern in all_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return False

        return True


class ThoughtStream:
    """Dual-sink thought stream for expert reasoning visibility.

    Emits structured decision records to:
    1. Rich terminal (public, redacted)
    2. JSONL log file (private, full audit trail)

    Attributes:
        expert_name: Name of the expert
        verbose: Show thoughts in terminal
        quiet: Hide all output except final answers
        log_path: Path to JSONL log file
    """

    # Color scheme for thought types
    COLORS = {
        ThoughtType.PLAN_STEP: "cyan",
        ThoughtType.TOOL_CALL: "yellow",
        ThoughtType.EVIDENCE_FOUND: "green",
        ThoughtType.CONFIDENCE: "blue",
        ThoughtType.DECISION: "magenta",
        ThoughtType.SEARCH: "yellow",
        ThoughtType.SYNTHESIS: "cyan",
        ThoughtType.ERROR: "red",
    }

    # Icons for thought types
    ICONS = {
        ThoughtType.PLAN_STEP: "📋",
        ThoughtType.TOOL_CALL: "🔧",
        ThoughtType.EVIDENCE_FOUND: "📄",
        ThoughtType.CONFIDENCE: "📊",
        ThoughtType.DECISION: "✅",
        ThoughtType.SEARCH: "🔍",
        ThoughtType.SYNTHESIS: "🧠",
        ThoughtType.ERROR: "❌",
    }

    def __init__(self, expert_name: str, verbose: bool = False, quiet: bool = False, log_dir: Optional[Path] = None):
        """Initialize ThoughtStream.

        Args:
            expert_name: Name of the expert for logging
            verbose: Show detailed thoughts in terminal
            quiet: Hide all thoughts (only final answers)
            log_dir: Directory for JSONL logs (default: data/experts/{name}/logs)
        """
        self.expert_name = expert_name
        self.verbose = verbose
        self.quiet = quiet
        self.console = Console()

        # Set up log directory
        if log_dir is None:
            log_dir = Path("data/experts") / expert_name / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create session log file
        session_id = _utc_now().strftime("%Y%m%d_%H%M%S")
        self.log_path = log_dir / f"thoughts_{session_id}.jsonl"

        # Track thoughts for this session
        self.thoughts: list[Thought] = []
        self.decision_records: list = []  # list[DecisionRecord]

        # Callbacks for external consumers (e.g. WebSocket events)
        self._callbacks: list = []  # list[Callable[[Thought], None]]

        # Current phase for grouping
        self._current_phase: Optional[str] = None

    def add_callback(self, callback) -> None:
        """Register a callback that is invoked on every emitted thought.

        The callback receives the ``Thought`` object.  Exceptions inside
        callbacks are caught and logged to avoid crashing the chat loop.
        """
        self._callbacks.append(callback)

    def emit(
        self,
        thought_type: ThoughtType,
        public_text: str,
        private_payload: Optional[dict[str, Any]] = None,
        confidence: Optional[float] = None,
        evidence_refs: Optional[list[str]] = None,
        **metadata,
    ) -> Thought:
        """Emit a thought to both sinks.

        Args:
            thought_type: Category of thought
            public_text: Text safe for user display
            private_payload: Full details for audit (may be sensitive)
            confidence: Optional confidence score
            evidence_refs: Optional evidence source IDs
            **metadata: Additional structured data

        Returns:
            The created Thought object
        """
        # Apply redaction to public text
        safe_text = RedactionRules.redact(public_text)

        # Create thought record
        thought = Thought(
            thought_type=thought_type,
            public_text=safe_text,
            private_payload=private_payload,
            confidence=confidence,
            evidence_refs=evidence_refs,
            metadata={"phase": self._current_phase, "expert": self.expert_name, **metadata},
        )

        # Store in session
        self.thoughts.append(thought)

        # Write to JSONL log (full, unredacted for audit)
        self._write_to_log(thought, original_text=public_text)

        # Invoke external callbacks (e.g. WebSocket thought events)
        for cb in self._callbacks:
            try:
                cb(thought)
            except Exception as cb_err:
                logger.debug("ThoughtStream callback error: %s", cb_err)

        # Display in terminal (redacted)
        if not self.quiet:
            self._display_thought(thought)

        return thought

    def _write_to_log(self, thought: Thought, original_text: Optional[str] = None):
        """Write thought to JSONL log file.

        Args:
            thought: Thought to log
            original_text: Original unredacted text (for audit)
        """
        try:
            log_entry = thought.to_dict()

            # Include original text in private log if different from redacted
            if original_text and original_text != thought.public_text:
                log_entry["original_text"] = original_text

            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.debug("Failed to write thought log to %s: %s", self.log_path, e)

    def _display_thought(self, thought: Thought):
        """Display thought in terminal using Rich.

        Args:
            thought: Thought to display
        """
        if self.quiet:
            return

        # Only show detailed thoughts in verbose mode
        if not self.verbose and thought.thought_type not in [ThoughtType.DECISION, ThoughtType.ERROR]:
            return

        color = self.COLORS.get(thought.thought_type, "white")
        icon = self.ICONS.get(thought.thought_type, "•")

        # Build display text
        text = Text()
        text.append(f"{icon} ", style=color)
        text.append(thought.public_text, style=color)

        # Add confidence if present
        if thought.confidence is not None:
            conf_color = "green" if thought.confidence > 0.8 else "yellow" if thought.confidence > 0.5 else "red"
            text.append(f" ({thought.confidence:.0%})", style=conf_color)

        # Add evidence count if present
        if thought.evidence_refs:
            text.append(f" [{len(thought.evidence_refs)} sources]", style="dim")

        # Display based on type
        if thought.thought_type == ThoughtType.DECISION:
            # Decisions get a panel
            self.console.print(Panel(text, title="Decision", border_style=color))
        elif thought.thought_type == ThoughtType.ERROR:
            # Errors get a panel
            self.console.print(Panel(text, title="Error", border_style="red"))
        else:
            # Other thoughts are inline
            self.console.print(text)

    @contextmanager
    def planning(self, description: str):
        """Context manager for planning phase.

        Args:
            description: Description of what's being planned

        Yields:
            None
        """
        self._current_phase = "planning"
        self.emit(
            ThoughtType.PLAN_STEP,
            f"Planning: {description}",
            private_payload={"phase_start": "planning", "description": description},
        )
        try:
            yield
        finally:
            self._current_phase = None

    @contextmanager
    def searching(self, query: str):
        """Context manager for search phase.

        Args:
            query: Search query

        Yields:
            None
        """
        self._current_phase = "searching"
        self.emit(
            ThoughtType.SEARCH,
            f"Searching: {query[:100]}{'...' if len(query) > 100 else ''}",
            private_payload={"phase_start": "searching", "query": query},
        )
        try:
            yield
        finally:
            self._current_phase = None

    def decision(
        self,
        decision_text: str,
        confidence: float,
        evidence: Optional[list[str]] = None,
        reasoning: Optional[str] = None,
    ):
        """Record a decision.

        Args:
            decision_text: The decision made
            confidence: Confidence in the decision (0.0-1.0)
            evidence: Evidence supporting the decision
            reasoning: Private reasoning (for audit only)
        """
        self.emit(
            ThoughtType.DECISION,
            decision_text,
            private_payload={"reasoning": reasoning} if reasoning else None,
            confidence=confidence,
            evidence_refs=evidence,
        )

    def evidence(self, source_id: str, summary: str, relevance: float = 1.0):
        """Record evidence found.

        Args:
            source_id: ID of the evidence source
            summary: Brief summary of the evidence
            relevance: Relevance score (0.0-1.0)
        """
        self.emit(
            ThoughtType.EVIDENCE_FOUND,
            f"Found: {summary[:100]}{'...' if len(summary) > 100 else ''}",
            private_payload={"source_id": source_id, "full_summary": summary},
            confidence=relevance,
            evidence_refs=[source_id],
        )

    def tool_call(self, tool_name: str, args: Optional[dict[str, Any]] = None, result_summary: Optional[str] = None):
        """Record a tool call.

        Args:
            tool_name: Name of the tool called
            args: Arguments passed (will be redacted in public display)
            result_summary: Brief summary of result
        """
        public = f"Calling {tool_name}"
        if result_summary:
            public += f": {result_summary[:50]}{'...' if len(result_summary) > 50 else ''}"

        self.emit(
            ThoughtType.TOOL_CALL, public, private_payload={"tool": tool_name, "args": args, "result": result_summary}
        )

    def error(self, message: str, details: Optional[dict[str, Any]] = None):
        """Record an error.

        Args:
            message: Error message
            details: Additional error details (for audit)
        """
        self.emit(ThoughtType.ERROR, f"Error: {message}", private_payload=details)

    def record_decision(
        self,
        decision_type: str,
        title: str,
        rationale: str,
        confidence: float = 0.0,
        alternatives: Optional[list[str]] = None,
        evidence_refs: Optional[list[str]] = None,
        cost_impact: float = 0.0,
        **context,
    ) -> None:
        """Record a structured DecisionRecord alongside a Thought.

        Creates a DecisionRecord, appends to self.decision_records,
        AND calls self.decision() for backward compatibility.

        Args:
            decision_type: DecisionType value string (e.g. "routing", "stop")
            title: Short label (< 80 chars)
            rationale: Why this was chosen
            confidence: 0.0-1.0
            alternatives: Other options considered
            evidence_refs: Source/span IDs
            cost_impact: USD impact
            **context: Additional context (job_id, expert_name, span_id)
        """
        from deepr.core.contracts import DecisionRecord, DecisionType

        try:
            dtype = DecisionType(decision_type)
        except ValueError:
            dtype = DecisionType.ROUTING

        record = DecisionRecord.create(
            decision_type=dtype,
            title=title,
            rationale=rationale,
            confidence=confidence,
            alternatives=alternatives or [],
            evidence_refs=evidence_refs or [],
            cost_impact=cost_impact,
            context=context,
        )
        self.decision_records.append(record)

        # Backward compat: also emit as a Thought
        self.decision(title, confidence=confidence, evidence=evidence_refs, reasoning=rationale)

    def get_decision_records(self) -> list[dict[str, Any]]:
        """Return serialized decision records.

        Returns:
            List of DecisionRecord dictionaries.
        """
        return [r.to_dict() for r in self.decision_records]

    def get_trace(self) -> list[dict[str, Any]]:
        """Get the full thought trace for this session.

        Returns:
            List of thought dictionaries
        """
        return [t.to_dict() for t in self.thoughts]

    def get_public_trace(self) -> list[dict[str, Any]]:
        """Get redacted thought trace safe for sharing.

        Returns:
            List of thought dictionaries with private_payload removed
        """
        trace = []
        for thought in self.thoughts:
            entry = thought.to_dict()
            entry.pop("private_payload", None)
            trace.append(entry)
        return trace

    def generate_decision_summary(self) -> str:
        """Generate a human-readable summary of decisions and reasoning.

        Creates a natural language narrative of the decision-making process
        suitable for display with --why flag or storing as decision.md.

        Returns:
            Markdown-formatted decision summary
        """
        if not self.thoughts:
            return "No decisions recorded for this session."

        lines = [
            f"# Decision Log: {self.expert_name}",
            "",
            f"*Session: {self.thoughts[0].timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}*",
            "",
        ]

        # Group thoughts by phase
        current_phase = None
        decisions = []
        evidence_used = []
        tools_called = []

        for thought in self.thoughts:
            phase = thought.metadata.get("phase")

            # Track phase changes
            if phase and phase != current_phase:
                if current_phase:
                    lines.append("")
                current_phase = phase
                lines.append(f"## {phase.title()} Phase")
                lines.append("")

            # Summarize based on type
            if thought.thought_type == ThoughtType.PLAN_STEP:
                lines.append(f"- {thought.public_text}")

            elif thought.thought_type == ThoughtType.SEARCH:
                tools_called.append(("search", thought.public_text))
                lines.append(f"- 🔍 {thought.public_text}")

            elif thought.thought_type == ThoughtType.TOOL_CALL:
                tool_name = thought.private_payload.get("tool", "unknown") if thought.private_payload else "tool"
                tools_called.append((tool_name, thought.public_text))
                lines.append(f"- 🔧 {thought.public_text}")

            elif thought.thought_type == ThoughtType.EVIDENCE_FOUND:
                if thought.evidence_refs:
                    evidence_used.extend(thought.evidence_refs)
                conf_str = f" ({thought.confidence:.0%})" if thought.confidence else ""
                lines.append(f"- 📄 {thought.public_text}{conf_str}")

            elif thought.thought_type == ThoughtType.DECISION:
                decisions.append(thought)
                conf_str = f" (confidence: {thought.confidence:.0%})" if thought.confidence else ""
                lines.append("")
                lines.append(f"**Decision:** {thought.public_text}{conf_str}")
                if thought.evidence_refs:
                    lines.append(f"  - Based on: {', '.join(thought.evidence_refs)}")
                lines.append("")

            elif thought.thought_type == ThoughtType.ERROR:
                lines.append(f"- ❌ {thought.public_text}")

        # Add typed decisions section if available
        if self.decision_records:
            lines.extend(["", "## Typed Decisions", ""])
            for rec in self.decision_records:
                lines.append(
                    f"- **[{rec.decision_type.value}]** {rec.title} "
                    f"(confidence: {rec.confidence:.0%}, cost: ${rec.cost_impact:.4f})"
                )
                if rec.rationale:
                    lines.append(f"  - Rationale: {rec.rationale}")
                if rec.alternatives:
                    lines.append(f"  - Alternatives: {', '.join(rec.alternatives)}")

        # Add summary section
        lines.extend(
            [
                "",
                "---",
                "",
                "## Summary",
                "",
            ]
        )

        if decisions:
            lines.append(f"**Total Decisions:** {len(decisions)}")
            avg_conf = sum(d.confidence for d in decisions if d.confidence) / max(
                len([d for d in decisions if d.confidence]), 1
            )
            if avg_conf > 0:
                lines.append(f"**Average Confidence:** {avg_conf:.0%}")

        if tools_called:
            lines.append(f"**Tools Used:** {len(tools_called)}")
            tool_counts = {}
            for tool_name, _ in tools_called:
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
            for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
                lines.append(f"  - {tool}: {count}x")

        if evidence_used:
            unique_evidence = list(set(evidence_used))
            lines.append(f"**Evidence Sources:** {len(unique_evidence)}")
            for source in unique_evidence[:5]:  # Show max 5
                lines.append(f"  - {source}")
            if len(unique_evidence) > 5:
                lines.append(f"  - ... and {len(unique_evidence) - 5} more")

        return "\n".join(lines)

    def save_decision_log(self, path: Path) -> None:
        """Save decision log as markdown + JSON files.

        Args:
            path: Path to save the decision log (e.g., reports/{job_id}/decisions.md)
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        summary = self.generate_decision_summary()

        with open(path, "w", encoding="utf-8") as f:
            f.write(summary)

        # Also save structured decisions as JSON alongside the markdown
        if self.decision_records:
            json_path = path.with_suffix(".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.get_decision_records(), f, indent=2)

    def get_why_summary(self) -> str:
        """Get a concise one-line summary for --why flag output.

        Returns:
            Single line explaining key decisions
        """
        decisions = [t for t in self.thoughts if t.thought_type == ThoughtType.DECISION]

        if not decisions:
            return "No explicit decisions recorded."

        # Get the most recent/important decision
        last_decision = decisions[-1]
        conf_str = f" ({last_decision.confidence:.0%})" if last_decision.confidence else ""

        parts = [f"Decision: {last_decision.public_text}{conf_str}"]

        # Add tool usage summary
        tools = [t for t in self.thoughts if t.thought_type == ThoughtType.TOOL_CALL]
        if tools:
            tool_names = set()
            for t in tools:
                if t.private_payload and "tool" in t.private_payload:
                    tool_names.add(t.private_payload["tool"])
            if tool_names:
                parts.append(f"Tools: {', '.join(sorted(tool_names))}")

        # Add evidence count
        evidence = [t for t in self.thoughts if t.thought_type == ThoughtType.EVIDENCE_FOUND]
        if evidence:
            parts.append(f"Evidence: {len(evidence)} sources")

        return " | ".join(parts)
