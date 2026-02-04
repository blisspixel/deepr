"""Entropy-based stopping criteria for research phases.

Provides intelligent stopping decisions based on:
- Information entropy of findings (diminishing returns detection)
- Auto-pivot detection when research drifts from original query
- Configurable thresholds via constants

Usage:
    from deepr.observability.stopping_criteria import EntropyStoppingCriteria

    stopping = EntropyStoppingCriteria()
    decision = stopping.evaluate(findings, phase_context)

    if decision.should_stop:
        print(f"Stopping: {decision.reason}")
    elif decision.pivot_suggestion:
        print(f"Consider pivoting to: {decision.pivot_suggestion}")
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
from collections import Counter
import re
import hashlib

from deepr.core.constants import (
    ENTROPY_THRESHOLD,
    MIN_INFORMATION_GAIN,
    ENTROPY_WINDOW_SIZE,
    MIN_ITERATIONS_BEFORE_STOP,
)


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


@dataclass
class Finding:
    """A single research finding."""
    text: str
    phase: int
    confidence: float = 0.5
    source: Optional[str] = None
    timestamp: datetime = field(default_factory=_utc_now)
    tokens: List[str] = field(default_factory=list)
    content_hash: str = ""

    def __post_init__(self):
        if not self.tokens:
            self.tokens = self._tokenize(self.text)
        if not self.content_hash:
            self.content_hash = hashlib.md5(self.text.encode()).hexdigest()[:12]

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple tokenization for entropy calculation."""
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        tokens = [t for t in text.split() if len(t) > 2]
        return tokens


@dataclass
class PhaseContext:
    """Context about the current research phase."""
    phase_num: int
    original_query: str
    current_focus: str
    total_findings: int = 0
    total_tokens_used: int = 0
    elapsed_seconds: float = 0.0
    prior_entropy: Optional[float] = None
    iteration_count: int = 0


@dataclass
class StoppingDecision:
    """Decision about whether to stop research."""
    should_stop: bool
    reason: str
    entropy: float
    information_gain: float
    pivot_suggestion: Optional[str] = None
    confidence: float = 0.5
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "should_stop": self.should_stop,
            "reason": self.reason,
            "entropy": self.entropy,
            "information_gain": self.information_gain,
            "pivot_suggestion": self.pivot_suggestion,
            "confidence": self.confidence,
            "metrics": self.metrics,
        }


class EntropyStoppingCriteria:
    """Entropy-based stopping criteria for research phases.

    Uses Shannon entropy to detect when findings are becoming repetitive
    (low information gain) and suggests when to stop or pivot research.

    Attributes:
        entropy_threshold: Stop when entropy drops below this value
        min_information_gain: Minimum new information per phase
        window_size: Number of recent findings to consider
        min_iterations: Minimum iterations before stopping allowed
    """

    def __init__(
        self,
        entropy_threshold: Optional[float] = None,
        min_information_gain: Optional[float] = None,
        window_size: Optional[int] = None,
        min_iterations: Optional[int] = None,
    ):
        """Initialize stopping criteria.

        Args:
            entropy_threshold: Override default entropy threshold
            min_information_gain: Override minimum information gain
            window_size: Override window size for recent findings
            min_iterations: Override minimum iterations before stop
        """
        self.entropy_threshold = entropy_threshold or ENTROPY_THRESHOLD
        self.min_information_gain = min_information_gain or MIN_INFORMATION_GAIN
        self.window_size = window_size or ENTROPY_WINDOW_SIZE
        self.min_iterations = min_iterations or MIN_ITERATIONS_BEFORE_STOP

        # Track history for trend analysis
        self._entropy_history: List[float] = []
        self._content_hashes: Set[str] = set()

    def evaluate(
        self,
        findings: List[Finding],
        phase_context: PhaseContext,
    ) -> StoppingDecision:
        """Evaluate whether to stop research.

        Args:
            findings: List of findings from current phase
            phase_context: Context about the current phase

        Returns:
            StoppingDecision with recommendation
        """
        if not findings:
            return StoppingDecision(
                should_stop=False,
                reason="No findings to evaluate",
                entropy=1.0,
                information_gain=1.0,
                confidence=0.1,
            )

        # Calculate entropy of recent findings
        recent = findings[-self.window_size:] if len(findings) > self.window_size else findings
        entropy = self.calculate_entropy(recent)

        # Calculate information gain
        info_gain = self._calculate_information_gain(findings, phase_context)

        # Track entropy trend
        self._entropy_history.append(entropy)

        # Calculate metrics
        metrics = {
            "entropy": entropy,
            "information_gain": info_gain,
            "unique_findings": self._count_unique(findings),
            "total_findings": len(findings),
            "duplicate_rate": self._calculate_duplicate_rate(findings),
            "entropy_trend": self._calculate_entropy_trend(),
            "iteration": phase_context.iteration_count,
        }

        # Check for auto-pivot
        pivot_suggestion = self.detect_auto_pivot(findings, phase_context.original_query)

        # Determine if we should stop
        should_stop = False
        reason = "Continue research"
        confidence = 0.5

        # Don't stop before minimum iterations
        if phase_context.iteration_count < self.min_iterations:
            return StoppingDecision(
                should_stop=False,
                reason=f"Minimum iterations not reached ({phase_context.iteration_count}/{self.min_iterations})",
                entropy=entropy,
                information_gain=info_gain,
                pivot_suggestion=pivot_suggestion,
                confidence=0.3,
                metrics=metrics,
            )

        # Check entropy threshold
        if entropy < self.entropy_threshold:
            should_stop = True
            reason = f"Entropy ({entropy:.3f}) below threshold ({self.entropy_threshold})"
            confidence = 0.8

        # Check information gain
        elif info_gain < self.min_information_gain:
            should_stop = True
            reason = f"Information gain ({info_gain:.3f}) below threshold ({self.min_information_gain})"
            confidence = 0.7

        # Check for declining entropy trend
        elif self._is_entropy_declining():
            should_stop = True
            reason = "Entropy consistently declining (diminishing returns)"
            confidence = 0.6

        # Check for high duplicate rate
        elif metrics["duplicate_rate"] > 0.5:
            should_stop = True
            reason = f"High duplicate rate ({metrics['duplicate_rate']:.1%})"
            confidence = 0.75

        return StoppingDecision(
            should_stop=should_stop,
            reason=reason,
            entropy=entropy,
            information_gain=info_gain,
            pivot_suggestion=pivot_suggestion,
            confidence=confidence,
            metrics=metrics,
        )

    def calculate_entropy(self, findings: List[Finding]) -> float:
        """Calculate Shannon entropy of findings.

        Higher entropy = more diverse/new information
        Lower entropy = repetitive/redundant information

        Args:
            findings: List of findings to analyze

        Returns:
            Normalized entropy value (0.0 to 1.0)
        """
        if not findings:
            return 1.0

        # Collect all tokens
        all_tokens = []
        for finding in findings:
            all_tokens.extend(finding.tokens)

        if not all_tokens:
            return 1.0

        # Calculate token frequencies
        token_counts = Counter(all_tokens)
        total = len(all_tokens)

        # Calculate Shannon entropy
        entropy = 0.0
        for count in token_counts.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)

        # Normalize by maximum possible entropy
        max_entropy = math.log2(len(token_counts)) if len(token_counts) > 1 else 1.0
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0

        return min(1.0, max(0.0, normalized_entropy))

    def detect_auto_pivot(
        self,
        findings: List[Finding],
        original_query: str,
    ) -> Optional[str]:
        """Detect if research has drifted and suggest pivot.

        Args:
            findings: Current findings
            original_query: Original research query

        Returns:
            Suggested pivot topic, or None if no drift detected
        """
        if len(findings) < 3:
            return None

        # Extract key terms from original query
        query_tokens = set(Finding._tokenize(original_query))

        # Extract dominant topics from recent findings
        recent = findings[-5:]
        topic_counts: Counter = Counter()

        for finding in recent:
            for token in finding.tokens:
                if len(token) > 4:  # Focus on substantive words
                    topic_counts[token] += 1

        # Find topics that appear frequently but weren't in original query
        emerging_topics = []
        for topic, count in topic_counts.most_common(10):
            if topic not in query_tokens and count >= 2:
                emerging_topics.append(topic)

        if len(emerging_topics) >= 2:
            # Calculate drift score
            original_coverage = sum(
                1 for t in query_tokens
                if any(t in f.text.lower() for f in recent)
            )
            drift_score = 1 - (original_coverage / max(len(query_tokens), 1))

            if drift_score > 0.5:
                pivot_suggestion = ", ".join(emerging_topics[:3])
                return f"Consider pivoting to: {pivot_suggestion}"

        return None

    def _calculate_information_gain(
        self,
        findings: List[Finding],
        context: PhaseContext,
    ) -> float:
        """Calculate information gain from new findings.

        Args:
            findings: Current findings
            context: Phase context with prior entropy

        Returns:
            Information gain score (0.0 to 1.0)
        """
        if context.prior_entropy is None:
            return 1.0  # First phase, maximum gain

        current_entropy = self.calculate_entropy(findings)

        # New unique content adds information
        new_hashes = {f.content_hash for f in findings} - self._content_hashes
        uniqueness_bonus = len(new_hashes) / max(len(findings), 1)

        # Update tracked hashes
        self._content_hashes.update(new_hashes)

        # Combine entropy and uniqueness
        info_gain = (current_entropy * 0.6) + (uniqueness_bonus * 0.4)

        return min(1.0, max(0.0, info_gain))

    def _count_unique(self, findings: List[Finding]) -> int:
        """Count unique findings by content hash."""
        return len({f.content_hash for f in findings})

    def _calculate_duplicate_rate(self, findings: List[Finding]) -> float:
        """Calculate rate of duplicate findings."""
        if not findings:
            return 0.0

        unique = self._count_unique(findings)
        return 1 - (unique / len(findings))

    def _calculate_entropy_trend(self) -> str:
        """Determine entropy trend from history."""
        if len(self._entropy_history) < 3:
            return "insufficient_data"

        recent = self._entropy_history[-3:]
        if all(recent[i] > recent[i+1] for i in range(len(recent)-1)):
            return "declining"
        elif all(recent[i] < recent[i+1] for i in range(len(recent)-1)):
            return "increasing"
        else:
            return "stable"

    def _is_entropy_declining(self) -> bool:
        """Check if entropy has been consistently declining."""
        if len(self._entropy_history) < 3:
            return False

        return self._calculate_entropy_trend() == "declining"

    def reset(self):
        """Reset internal state for a new research session."""
        self._entropy_history.clear()
        self._content_hashes.clear()

    def export_to_span(self, span) -> None:
        """Export metrics to an observability span.

        Args:
            span: Span object with set_attribute method
        """
        span.set_attribute("stopping.entropy_history", self._entropy_history[-10:])
        span.set_attribute("stopping.unique_findings", len(self._content_hashes))
        span.set_attribute("stopping.entropy_trend", self._calculate_entropy_trend())
