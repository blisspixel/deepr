"""Temporal knowledge tracking for research phases.

Tracks findings with timestamps and hypothesis evolution over time
to provide visibility into how understanding develops during research.

Usage:
    from deepr.observability.temporal_tracker import TemporalKnowledgeTracker

    tracker = TemporalKnowledgeTracker()

    # Record a finding
    finding = tracker.record_finding(
        text="Key discovery about topic X",
        phase=1,
        confidence=0.85,
        source="https://example.com/article"
    )

    # Update a hypothesis
    evolution = tracker.update_hypothesis(
        hypothesis_id="h1",
        new_text="Revised understanding based on findings",
        reason="New evidence from phase 2"
    )

    # Get timeline
    timeline = tracker.get_timeline()
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class FindingType(Enum):
    """Types of research findings."""

    FACT = "fact"
    OBSERVATION = "observation"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    CONTRADICTION = "contradiction"
    CONFIRMATION = "confirmation"


class EvolutionType(Enum):
    """Types of hypothesis evolution."""

    CREATED = "created"
    STRENGTHENED = "strengthened"
    WEAKENED = "weakened"
    MODIFIED = "modified"
    INVALIDATED = "invalidated"
    MERGED = "merged"
    SPLIT = "split"


@dataclass
class TemporalFinding:
    """A timestamped research finding."""

    id: str
    text: str
    phase: int
    confidence: float
    source: Optional[str]
    finding_type: FindingType
    timestamp: datetime
    related_findings: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "phase": self.phase,
            "confidence": self.confidence,
            "source": self.source,
            "finding_type": self.finding_type.value,
            "timestamp": self.timestamp.isoformat(),
            "related_findings": self.related_findings,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemporalFinding":
        return cls(
            id=data["id"],
            text=data["text"],
            phase=data["phase"],
            confidence=data["confidence"],
            source=data.get("source"),
            finding_type=FindingType(data["finding_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            related_findings=data.get("related_findings", []),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class HypothesisState:
    """State of a hypothesis at a point in time."""

    text: str
    confidence: float
    supporting_findings: List[str]
    contradicting_findings: List[str]
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "supporting_findings": self.supporting_findings,
            "contradicting_findings": self.contradicting_findings,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class HypothesisEvolution:
    """Record of how a hypothesis has evolved."""

    hypothesis_id: str
    evolution_type: EvolutionType
    old_state: Optional[HypothesisState]
    new_state: HypothesisState
    reason: str
    triggering_finding_id: Optional[str]
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "evolution_type": self.evolution_type.value,
            "old_state": self.old_state.to_dict() if self.old_state else None,
            "new_state": self.new_state.to_dict(),
            "reason": self.reason,
            "triggering_finding_id": self.triggering_finding_id,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Hypothesis:
    """A research hypothesis with its evolution history."""

    id: str
    current_state: HypothesisState
    evolution_history: List[HypothesisEvolution] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    phase_created: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "current_state": self.current_state.to_dict(),
            "evolution_history": [e.to_dict() for e in self.evolution_history],
            "created_at": self.created_at.isoformat(),
            "phase_created": self.phase_created,
        }


class TemporalKnowledgeTracker:
    """Tracks research findings and hypothesis evolution over time.

    Maintains a temporal record of:
    - All findings with timestamps and phases
    - Hypothesis evolution as understanding develops
    - Relationships between findings

    Attributes:
        findings: List of all temporal findings
        hypotheses: Dict of hypothesis ID to Hypothesis
        phase_summaries: Summary of each phase's contributions
    """

    def __init__(self, job_id: Optional[str] = None):
        """Initialize the tracker.

        Args:
            job_id: Optional job ID for correlation
        """
        self.job_id = job_id or str(uuid.uuid4())
        self.findings: List[TemporalFinding] = []
        self.hypotheses: Dict[str, Hypothesis] = {}
        self.phase_summaries: Dict[int, Dict[str, Any]] = {}
        self._finding_index: Dict[str, TemporalFinding] = {}

    def record_finding(
        self,
        text: str,
        phase: int,
        confidence: float = 0.5,
        source: Optional[str] = None,
        finding_type: FindingType = FindingType.FACT,
        related_findings: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TemporalFinding:
        """Record a new finding.

        Args:
            text: Finding text
            phase: Phase number when discovered
            confidence: Confidence score (0-1)
            source: Source URL or reference
            finding_type: Type of finding
            related_findings: IDs of related findings
            tags: Tags for categorization
            metadata: Additional metadata

        Returns:
            The recorded TemporalFinding
        """
        finding = TemporalFinding(
            id=str(uuid.uuid4())[:12],
            text=text,
            phase=phase,
            confidence=confidence,
            source=source,
            finding_type=finding_type,
            timestamp=_utc_now(),
            related_findings=related_findings or [],
            tags=tags or [],
            metadata=metadata or {},
        )

        self.findings.append(finding)
        self._finding_index[finding.id] = finding

        # Auto-detect contradictions and confirmations
        self._check_for_contradictions(finding)

        # Update phase summary
        self._update_phase_summary(phase, finding)

        return finding

    def create_hypothesis(
        self,
        text: str,
        phase: int,
        confidence: float = 0.5,
        supporting_findings: Optional[List[str]] = None,
    ) -> Hypothesis:
        """Create a new hypothesis.

        Args:
            text: Hypothesis text
            phase: Phase when hypothesis was formed
            confidence: Initial confidence
            supporting_findings: IDs of supporting findings

        Returns:
            The created Hypothesis
        """
        hypothesis_id = f"h_{str(uuid.uuid4())[:8]}"

        initial_state = HypothesisState(
            text=text,
            confidence=confidence,
            supporting_findings=supporting_findings or [],
            contradicting_findings=[],
            timestamp=_utc_now(),
        )

        hypothesis = Hypothesis(
            id=hypothesis_id,
            current_state=initial_state,
            phase_created=phase,
        )

        # Record creation evolution
        evolution = HypothesisEvolution(
            hypothesis_id=hypothesis_id,
            evolution_type=EvolutionType.CREATED,
            old_state=None,
            new_state=initial_state,
            reason="Initial hypothesis formation",
            triggering_finding_id=supporting_findings[0] if supporting_findings else None,
            timestamp=_utc_now(),
        )
        hypothesis.evolution_history.append(evolution)

        self.hypotheses[hypothesis_id] = hypothesis
        return hypothesis

    def update_hypothesis(
        self,
        hypothesis_id: str,
        new_text: str,
        reason: str,
        confidence: Optional[float] = None,
        evolution_type: Optional[EvolutionType] = None,
        triggering_finding_id: Optional[str] = None,
        add_supporting: Optional[List[str]] = None,
        add_contradicting: Optional[List[str]] = None,
    ) -> HypothesisEvolution:
        """Update an existing hypothesis.

        Args:
            hypothesis_id: ID of hypothesis to update
            new_text: New hypothesis text
            reason: Reason for the update
            confidence: New confidence (optional)
            evolution_type: Type of evolution (auto-detected if not provided)
            triggering_finding_id: Finding that triggered the update
            add_supporting: New supporting finding IDs
            add_contradicting: New contradicting finding IDs

        Returns:
            HypothesisEvolution record

        Raises:
            KeyError: If hypothesis not found
        """
        if hypothesis_id not in self.hypotheses:
            raise KeyError(f"Hypothesis {hypothesis_id} not found")

        hypothesis = self.hypotheses[hypothesis_id]
        old_state = hypothesis.current_state

        # Build new supporting/contradicting lists
        new_supporting = list(old_state.supporting_findings)
        new_contradicting = list(old_state.contradicting_findings)

        if add_supporting:
            new_supporting.extend(add_supporting)
        if add_contradicting:
            new_contradicting.extend(add_contradicting)

        # Determine new confidence
        new_confidence = confidence if confidence is not None else old_state.confidence

        # Auto-detect evolution type based on changes
        if evolution_type is None:
            if new_confidence > old_state.confidence:
                evolution_type = EvolutionType.STRENGTHENED
            elif new_confidence < old_state.confidence:
                evolution_type = EvolutionType.WEAKENED
            elif new_text != old_state.text:
                evolution_type = EvolutionType.MODIFIED
            else:
                evolution_type = EvolutionType.MODIFIED

        # Create new state
        new_state = HypothesisState(
            text=new_text,
            confidence=new_confidence,
            supporting_findings=new_supporting,
            contradicting_findings=new_contradicting,
            timestamp=_utc_now(),
        )

        # Record evolution
        evolution = HypothesisEvolution(
            hypothesis_id=hypothesis_id,
            evolution_type=evolution_type,
            old_state=old_state,
            new_state=new_state,
            reason=reason,
            triggering_finding_id=triggering_finding_id,
            timestamp=_utc_now(),
        )

        hypothesis.current_state = new_state
        hypothesis.evolution_history.append(evolution)

        return evolution

    def invalidate_hypothesis(
        self,
        hypothesis_id: str,
        reason: str,
        contradicting_finding_id: Optional[str] = None,
    ) -> HypothesisEvolution:
        """Invalidate a hypothesis.

        Args:
            hypothesis_id: ID of hypothesis to invalidate
            reason: Reason for invalidation
            contradicting_finding_id: Finding that invalidated it

        Returns:
            HypothesisEvolution record
        """
        return self.update_hypothesis(
            hypothesis_id=hypothesis_id,
            new_text=self.hypotheses[hypothesis_id].current_state.text,
            reason=reason,
            confidence=0.0,
            evolution_type=EvolutionType.INVALIDATED,
            triggering_finding_id=contradicting_finding_id,
            add_contradicting=[contradicting_finding_id] if contradicting_finding_id else None,
        )

    def get_timeline(
        self,
        phase: Optional[int] = None,
        finding_type: Optional[FindingType] = None,
    ) -> List[TemporalFinding]:
        """Get findings timeline.

        Args:
            phase: Filter by phase number
            finding_type: Filter by finding type

        Returns:
            List of findings sorted by timestamp
        """
        findings = self.findings

        if phase is not None:
            findings = [f for f in findings if f.phase == phase]

        if finding_type is not None:
            findings = [f for f in findings if f.finding_type == finding_type]

        return sorted(findings, key=lambda f: f.timestamp)

    def get_hypothesis_history(self, hypothesis_id: str) -> List[HypothesisEvolution]:
        """Get evolution history for a hypothesis.

        Args:
            hypothesis_id: ID of hypothesis

        Returns:
            List of evolution records
        """
        if hypothesis_id not in self.hypotheses:
            return []
        return self.hypotheses[hypothesis_id].evolution_history

    def get_phase_summary(self, phase: int) -> Dict[str, Any]:
        """Get summary for a specific phase.

        Args:
            phase: Phase number

        Returns:
            Summary dictionary
        """
        return self.phase_summaries.get(
            phase,
            {
                "phase": phase,
                "finding_count": 0,
                "avg_confidence": 0.0,
                "finding_types": {},
                "hypotheses_created": 0,
                "hypotheses_modified": 0,
            },
        )

    def get_confidence_trend(self, hypothesis_id: str) -> List[Dict[str, Any]]:
        """Get confidence trend for a hypothesis over time.

        Args:
            hypothesis_id: ID of hypothesis

        Returns:
            List of (timestamp, confidence) pairs
        """
        if hypothesis_id not in self.hypotheses:
            return []

        hypothesis = self.hypotheses[hypothesis_id]
        trend = []

        for evolution in hypothesis.evolution_history:
            trend.append(
                {
                    "timestamp": evolution.new_state.timestamp.isoformat(),
                    "confidence": evolution.new_state.confidence,
                    "evolution_type": evolution.evolution_type.value,
                }
            )

        return trend

    def export_for_job_manager(self) -> Dict[str, Any]:
        """Export temporal data for JobBeliefs integration.

        Returns:
            Dictionary suitable for JobBeliefs.temporal_findings
        """
        return {
            "job_id": self.job_id,
            "findings": [f.to_dict() for f in self.findings],
            "hypotheses": {h_id: h.to_dict() for h_id, h in self.hypotheses.items()},
            "phase_summaries": self.phase_summaries,
            "total_findings": len(self.findings),
            "active_hypotheses": len([h for h in self.hypotheses.values() if h.current_state.confidence > 0.0]),
        }

    def _check_for_contradictions(self, new_finding: TemporalFinding):
        """Check if new finding contradicts existing hypotheses.

        Args:
            new_finding: The new finding to check
        """
        # Simple heuristic: check for negation keywords in same topic area
        negation_words = {"not", "never", "no", "wrong", "false", "incorrect", "contrary"}
        new_words = set(new_finding.text.lower().split())

        for hypothesis in self.hypotheses.values():
            hypothesis_words = set(hypothesis.current_state.text.lower().split())

            # Check for topic overlap
            overlap = new_words & hypothesis_words
            if len(overlap) > 2:  # Some topic overlap
                # Check for negation
                if new_words & negation_words:
                    # Potential contradiction - add to contradicting findings
                    if new_finding.id not in hypothesis.current_state.contradicting_findings:
                        hypothesis.current_state.contradicting_findings.append(new_finding.id)
                        new_finding.finding_type = FindingType.CONTRADICTION
                        new_finding.related_findings.append(hypothesis.id)

    def _update_phase_summary(self, phase: int, finding: TemporalFinding):
        """Update summary for a phase.

        Args:
            phase: Phase number
            finding: New finding to include
        """
        if phase not in self.phase_summaries:
            self.phase_summaries[phase] = {
                "phase": phase,
                "finding_count": 0,
                "total_confidence": 0.0,
                "finding_types": {},
                "hypotheses_created": 0,
                "hypotheses_modified": 0,
            }

        summary = self.phase_summaries[phase]
        summary["finding_count"] += 1
        summary["total_confidence"] += finding.confidence
        summary["avg_confidence"] = summary["total_confidence"] / summary["finding_count"]

        finding_type = finding.finding_type.value
        summary["finding_types"][finding_type] = summary["finding_types"].get(finding_type, 0) + 1

    def reset(self):
        """Reset tracker for a new session."""
        self.findings.clear()
        self.hypotheses.clear()
        self.phase_summaries.clear()
        self._finding_index.clear()
