"""Information gain tracking per research phase.

Tracks how much new information is discovered in each phase
to help optimize research efficiency and detect saturation.

Usage:
    from deepr.observability.information_gain import InformationGainTracker

    tracker = InformationGainTracker()

    # Record findings for a phase
    metrics = tracker.record_phase_findings(
        phase=1,
        findings=["Finding 1", "Finding 2"],
        prior_context={"known_facts": [...]}
    )

    print(f"Information gain: {metrics.gain_score:.2f}")
"""

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


@dataclass
class InformationGainMetrics:
    """Metrics from information gain analysis."""

    phase: int
    gain_score: float  # 0.0 to 1.0
    novelty_rate: float  # Percentage of new information
    redundancy_rate: float  # Percentage of repeated information
    coverage_expansion: float  # How much we expanded knowledge
    topic_diversity: float  # Diversity of topics covered

    # Detailed breakdown
    new_entities: int
    new_topics: int
    total_findings: int
    unique_findings: int

    timestamp: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "gain_score": self.gain_score,
            "novelty_rate": self.novelty_rate,
            "redundancy_rate": self.redundancy_rate,
            "coverage_expansion": self.coverage_expansion,
            "topic_diversity": self.topic_diversity,
            "new_entities": self.new_entities,
            "new_topics": self.new_topics,
            "total_findings": self.total_findings,
            "unique_findings": self.unique_findings,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PriorContext:
    """Context from previous phases."""

    known_facts: list[str] = field(default_factory=list)
    known_entities: set[str] = field(default_factory=set)
    known_topics: set[str] = field(default_factory=set)
    content_hashes: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "known_facts_count": len(self.known_facts),
            "known_entities": list(self.known_entities),
            "known_topics": list(self.known_topics),
            "content_hashes_count": len(self.content_hashes),
        }


class InformationGainTracker:
    """Tracks information gain across research phases.

    Maintains a knowledge graph of discovered entities, topics, and facts
    to measure how much new information each phase contributes.

    Attributes:
        phases: List of InformationGainMetrics per phase
        cumulative_context: Accumulated knowledge from all phases
    """

    def __init__(self):
        """Initialize the tracker."""
        self.phases: list[InformationGainMetrics] = []
        self.cumulative_context = PriorContext()
        self._phase_findings: dict[int, list[str]] = {}

    def record_phase_findings(
        self,
        phase: int,
        findings: list[str],
        prior_context: Optional[dict[str, Any]] = None,
    ) -> InformationGainMetrics:
        """Record findings from a phase and calculate information gain.

        Args:
            phase: Phase number
            findings: List of finding texts
            prior_context: Optional context from prior phases

        Returns:
            InformationGainMetrics for this phase
        """
        if not findings:
            return InformationGainMetrics(
                phase=phase,
                gain_score=0.0,
                novelty_rate=0.0,
                redundancy_rate=1.0,
                coverage_expansion=0.0,
                topic_diversity=0.0,
                new_entities=0,
                new_topics=0,
                total_findings=0,
                unique_findings=0,
            )

        # Update prior context if provided
        if prior_context:
            self._update_context_from_dict(prior_context)

        # Extract entities and topics from findings
        new_entities = set()
        new_topics = set()
        new_hashes = set()
        unique_count = 0

        for finding in findings:
            # Calculate content hash for deduplication
            content_hash = hashlib.md5(finding.encode()).hexdigest()[:12]

            if content_hash not in self.cumulative_context.content_hashes:
                unique_count += 1
                new_hashes.add(content_hash)

            # Extract entities (capitalized phrases)
            entities = self._extract_entities(finding)
            for entity in entities:
                if entity not in self.cumulative_context.known_entities:
                    new_entities.add(entity)

            # Extract topics (key terms)
            topics = self._extract_topics(finding)
            for topic in topics:
                if topic not in self.cumulative_context.known_topics:
                    new_topics.add(topic)

        # Calculate metrics
        total = len(findings)
        novelty_rate = unique_count / total if total > 0 else 0.0
        redundancy_rate = 1.0 - novelty_rate

        # Coverage expansion: how many new entities/topics
        prior_knowledge_size = len(self.cumulative_context.known_entities) + len(self.cumulative_context.known_topics)
        new_knowledge = len(new_entities) + len(new_topics)
        coverage_expansion = new_knowledge / max(prior_knowledge_size + new_knowledge, 1)

        # Topic diversity using entropy
        topic_diversity = self._calculate_topic_diversity(findings)

        # Overall gain score
        gain_score = self._calculate_gain_score(
            novelty_rate=novelty_rate,
            coverage_expansion=coverage_expansion,
            topic_diversity=topic_diversity,
        )

        # Update cumulative context
        self.cumulative_context.known_entities.update(new_entities)
        self.cumulative_context.known_topics.update(new_topics)
        self.cumulative_context.content_hashes.update(new_hashes)
        self.cumulative_context.known_facts.extend(findings)

        # Store phase findings
        self._phase_findings[phase] = findings

        metrics = InformationGainMetrics(
            phase=phase,
            gain_score=gain_score,
            novelty_rate=novelty_rate,
            redundancy_rate=redundancy_rate,
            coverage_expansion=coverage_expansion,
            topic_diversity=topic_diversity,
            new_entities=len(new_entities),
            new_topics=len(new_topics),
            total_findings=total,
            unique_findings=unique_count,
        )

        self.phases.append(metrics)
        return metrics

    def get_cumulative_gain(self) -> float:
        """Get cumulative information gain across all phases.

        Returns:
            Total gain score (sum of phase gains)
        """
        return sum(p.gain_score for p in self.phases)

    def get_average_gain(self) -> float:
        """Get average information gain per phase.

        Returns:
            Average gain score
        """
        if not self.phases:
            return 0.0
        return self.get_cumulative_gain() / len(self.phases)

    def get_gain_trend(self) -> str:
        """Analyze trend in information gain.

        Returns:
            Trend description: 'increasing', 'decreasing', 'stable', or 'insufficient_data'
        """
        if len(self.phases) < 3:
            return "insufficient_data"

        recent = [p.gain_score for p in self.phases[-3:]]

        if all(recent[i] < recent[i + 1] for i in range(len(recent) - 1)):
            return "increasing"
        elif all(recent[i] > recent[i + 1] for i in range(len(recent) - 1)):
            return "decreasing"
        else:
            return "stable"

    def should_continue(self, threshold: float = 0.1) -> bool:
        """Determine if research should continue based on information gain.

        Args:
            threshold: Minimum gain to justify continuation

        Returns:
            True if research should continue
        """
        if not self.phases:
            return True

        # Check recent gain
        recent_gain = self.phases[-1].gain_score if self.phases else 1.0

        # Check trend
        trend = self.get_gain_trend()

        # Continue if gain is above threshold and not declining
        return recent_gain >= threshold or trend != "decreasing"

    def export_to_span(self, span) -> None:
        """Export metrics to an observability span.

        Args:
            span: Span object with set_attribute method
        """
        span.set_attribute("info_gain.phases_tracked", len(self.phases))
        span.set_attribute("info_gain.cumulative", self.get_cumulative_gain())
        span.set_attribute("info_gain.average", self.get_average_gain())
        span.set_attribute("info_gain.trend", self.get_gain_trend())
        span.set_attribute("info_gain.known_entities", len(self.cumulative_context.known_entities))
        span.set_attribute("info_gain.known_topics", len(self.cumulative_context.known_topics))

        if self.phases:
            latest = self.phases[-1]
            span.set_attribute("info_gain.latest_score", latest.gain_score)
            span.set_attribute("info_gain.latest_novelty", latest.novelty_rate)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of information gain tracking.

        Returns:
            Summary dictionary
        """
        return {
            "phases_tracked": len(self.phases),
            "cumulative_gain": self.get_cumulative_gain(),
            "average_gain": self.get_average_gain(),
            "trend": self.get_gain_trend(),
            "total_entities": len(self.cumulative_context.known_entities),
            "total_topics": len(self.cumulative_context.known_topics),
            "total_unique_findings": len(self.cumulative_context.content_hashes),
            "phase_metrics": [p.to_dict() for p in self.phases],
        }

    def reset(self):
        """Reset tracker for a new research session."""
        self.phases.clear()
        self.cumulative_context = PriorContext()
        self._phase_findings.clear()

    def _update_context_from_dict(self, context: dict[str, Any]):
        """Update cumulative context from a dictionary.

        Args:
            context: Dictionary with context data
        """
        if "known_facts" in context:
            self.cumulative_context.known_facts.extend(context["known_facts"])
        if "known_entities" in context:
            self.cumulative_context.known_entities.update(context["known_entities"])
        if "known_topics" in context:
            self.cumulative_context.known_topics.update(context["known_topics"])

    def _extract_entities(self, text: str) -> set[str]:
        """Extract named entities from text.

        Simple heuristic: capitalized multi-word phrases.

        Args:
            text: Text to extract from

        Returns:
            Set of entity strings
        """
        entities = set()

        # Find capitalized words/phrases
        pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
        matches = re.findall(pattern, text)

        for match in matches:
            # Filter common words
            if len(match) > 3 and match.lower() not in {"the", "this", "that", "with"}:
                entities.add(match)

        return entities

    def _extract_topics(self, text: str) -> set[str]:
        """Extract key topics from text.

        Args:
            text: Text to extract from

        Returns:
            Set of topic strings
        """
        # Simple tokenization and filtering
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        words = text.split()

        # Filter to substantive words
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "this",
            "that",
            "these",
            "those",
            "it",
            "its",
            "and",
            "or",
            "but",
            "if",
            "then",
            "else",
            "when",
            "where",
            "which",
            "who",
            "whom",
            "whose",
            "what",
            "how",
            "why",
            "for",
            "from",
            "with",
            "without",
            "about",
            "between",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "to",
            "of",
            "in",
            "on",
            "by",
            "at",
            "as",
            "not",
            "no",
            "yes",
            "also",
            "only",
            "just",
            "more",
            "most",
            "very",
            "such",
            "some",
            "any",
            "all",
            "each",
            "every",
            "both",
            "few",
            "many",
            "much",
            "other",
            "another",
        }

        topics = {w for w in words if len(w) > 4 and w not in stopwords}
        return topics

    def _calculate_topic_diversity(self, findings: list[str]) -> float:
        """Calculate topic diversity using entropy.

        Args:
            findings: List of finding texts

        Returns:
            Diversity score (0.0 to 1.0)
        """
        if not findings:
            return 0.0

        # Collect all topics
        all_topics: list[str] = []
        for finding in findings:
            all_topics.extend(self._extract_topics(finding))

        if not all_topics:
            return 0.0

        # Calculate entropy
        topic_counts = Counter(all_topics)
        total = len(all_topics)

        entropy = 0.0
        for count in topic_counts.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)

        # Normalize
        max_entropy = math.log2(len(topic_counts)) if len(topic_counts) > 1 else 1.0
        return entropy / max_entropy if max_entropy > 0 else 0.0

    def _calculate_gain_score(
        self,
        novelty_rate: float,
        coverage_expansion: float,
        topic_diversity: float,
    ) -> float:
        """Calculate overall information gain score.

        Args:
            novelty_rate: Rate of new information
            coverage_expansion: How much coverage expanded
            topic_diversity: Diversity of topics

        Returns:
            Combined gain score (0.0 to 1.0)
        """
        # Weighted combination
        score = novelty_rate * 0.4 + coverage_expansion * 0.35 + topic_diversity * 0.25
        return min(1.0, max(0.0, score))
