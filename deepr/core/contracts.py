"""Canonical types for the expert system.

Defines shared contracts used across CLI, web dashboard, and MCP server:
- Source: Provenance for a piece of evidence
- Claim: An atomic belief with confidence and sources
- Gap: A recognized knowledge gap with EV/cost scoring
- DecisionRecord: A structured decision made during research
- ExpertManifest: A complete snapshot of an expert's state

All types follow the Evidence pattern: dataclass + to_dict/from_dict.
Existing Belief/KnowledgeGap classes get adapter methods (to_claim/to_gap)
rather than being replaced.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class TrustClass(str, Enum):
    """Trust classification for sources."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"
    SELF_GENERATED = "self_generated"


class SupportClass(str, Enum):
    """How well a source supports its associated claim."""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    UNCERTAIN = "uncertain"


class DecisionType(str, Enum):
    """Types of decisions made during research."""

    ROUTING = "routing"
    STOP = "stop"
    PIVOT = "pivot"
    BUDGET = "budget"
    BELIEF_REVISION = "belief_revision"
    GAP_FILL = "gap_fill"
    CONFLICT_RESOLUTION = "conflict_resolution"
    SOURCE_SELECTION = "source_selection"


@dataclass
class Source:
    """Provenance for a piece of evidence.

    Attributes:
        id: Content-hash ID (SHA-256 first 12 chars)
        url: URL if available
        title: Source title or filename
        trust_class: primary | secondary | tertiary | self_generated
        content_hash: SHA-256 of source content (empty string if unavailable)
        extraction_method: How content was extracted (llm, scrape, manual, regex)
        retrieved_at: When this source was retrieved
    """

    id: str
    title: str
    trust_class: TrustClass
    extraction_method: str
    url: Optional[str] = None
    content_hash: str = ""
    retrieved_at: datetime = field(default_factory=_utc_now)
    support_class: Optional[SupportClass] = None

    @classmethod
    def create(
        cls, title: str, trust_class: TrustClass = TrustClass.TERTIARY, extraction_method: str = "llm", **kwargs
    ) -> "Source":
        """Create a Source with content-hash ID."""
        content = f"{title}:{kwargs.get('url', '')}:{kwargs.get('content_hash', '')}"
        id_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
        return cls(id=id_hash, title=title, trust_class=trust_class, extraction_method=extraction_method, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        d = {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "trust_class": self.trust_class.value,
            "content_hash": self.content_hash,
            "extraction_method": self.extraction_method,
            "retrieved_at": self.retrieved_at.isoformat(),
        }
        if self.support_class is not None:
            d["support_class"] = self.support_class.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Source":
        """Create from dictionary."""
        support_class = SupportClass(data["support_class"]) if data.get("support_class") else None
        return cls(
            id=data["id"],
            url=data.get("url"),
            title=data["title"],
            trust_class=TrustClass(data["trust_class"]),
            content_hash=data.get("content_hash", ""),
            extraction_method=data.get("extraction_method", "llm"),
            retrieved_at=datetime.fromisoformat(data["retrieved_at"]) if data.get("retrieved_at") else _utc_now(),
            support_class=support_class,
        )


@dataclass
class Claim:
    """An atomic declarative assertion with confidence and provenance.

    Attributes:
        id: Content-hash ID (SHA-256 first 12 chars of statement + domain)
        statement: The assertion text
        domain: Knowledge domain
        confidence: 0.0-1.0 (with decay applied)
        sources: Supporting Source objects
        created_at: When claim was first made
        updated_at: When claim was last updated
        contradicts: IDs of contradicting Claims
        supersedes: Claim ID this replaced
        tags: Categorization tags
    """

    id: str
    statement: str
    domain: str
    confidence: float
    sources: list[Source] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    contradicts: list[str] = field(default_factory=list)
    supersedes: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, statement: str, domain: str, confidence: float, **kwargs) -> "Claim":
        """Create a Claim with content-hash ID."""
        content = f"{statement}:{domain}"
        id_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
        return cls(id=id_hash, statement=statement, domain=domain, confidence=confidence, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "statement": self.statement,
            "domain": self.domain,
            "confidence": self.confidence,
            "sources": [s.to_dict() for s in self.sources],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "contradicts": self.contradicts,
            "supersedes": self.supersedes,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Claim":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            statement=data["statement"],
            domain=data["domain"],
            confidence=data["confidence"],
            sources=[Source.from_dict(s) for s in data.get("sources", [])],
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else _utc_now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else _utc_now(),
            contradicts=data.get("contradicts", []),
            supersedes=data.get("supersedes"),
            tags=data.get("tags", []),
        )


@dataclass
class Gap:
    """A recognized knowledge gap with EV/cost scoring.

    Attributes:
        id: Content-hash ID (SHA-256 first 12 chars of topic)
        topic: Subject of the gap
        questions: Unanswered questions
        priority: 1-5 (5 = most important)
        estimated_cost: USD to fill
        expected_value: 0.0-1.0
        ev_cost_ratio: expected_value / max(estimated_cost, 0.001)
        times_asked: How often users hit this gap
        identified_at: When gap was first found
        filled: Whether the gap has been resolved
        filled_at: When it was resolved
        filled_by_job: Job ID that resolved this
    """

    id: str
    topic: str
    questions: list[str] = field(default_factory=list)
    priority: int = 3
    estimated_cost: float = 0.0
    expected_value: float = 0.0
    ev_cost_ratio: float = 0.0
    times_asked: int = 0
    identified_at: datetime = field(default_factory=_utc_now)
    filled: bool = False
    filled_at: Optional[datetime] = None
    filled_by_job: Optional[str] = None

    @classmethod
    def create(cls, topic: str, **kwargs) -> "Gap":
        """Create a Gap with content-hash ID."""
        id_hash = hashlib.sha256(topic.encode()).hexdigest()[:12]
        return cls(id=id_hash, topic=topic, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "topic": self.topic,
            "questions": self.questions,
            "priority": self.priority,
            "estimated_cost": self.estimated_cost,
            "expected_value": self.expected_value,
            "ev_cost_ratio": self.ev_cost_ratio,
            "times_asked": self.times_asked,
            "identified_at": self.identified_at.isoformat(),
            "filled": self.filled,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "filled_by_job": self.filled_by_job,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Gap":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            topic=data["topic"],
            questions=data.get("questions", []),
            priority=data.get("priority", 3),
            estimated_cost=data.get("estimated_cost", 0.0),
            expected_value=data.get("expected_value", 0.0),
            ev_cost_ratio=data.get("ev_cost_ratio", 0.0),
            times_asked=data.get("times_asked", 0),
            identified_at=datetime.fromisoformat(data["identified_at"]) if data.get("identified_at") else _utc_now(),
            filled=data.get("filled", False),
            filled_at=datetime.fromisoformat(data["filled_at"]) if data.get("filled_at") else None,
            filled_by_job=data.get("filled_by_job"),
        )


@dataclass
class DecisionRecord:
    """A structured decision made during research.

    Attributes:
        id: UUID
        decision_type: Category of decision
        title: Short label (< 80 chars)
        rationale: Why this was chosen
        confidence: 0.0-1.0
        alternatives: Other options considered
        evidence_refs: Source/span IDs
        cost_impact: USD impact
        timestamp: When decision was made
        context: Additional context (job_id, expert_name, span_id, etc.)
    """

    id: str
    decision_type: DecisionType
    title: str
    rationale: str
    confidence: float = 0.0
    alternatives: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    cost_impact: float = 0.0
    timestamp: datetime = field(default_factory=_utc_now)
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, decision_type: DecisionType, title: str, rationale: str, **kwargs) -> "DecisionRecord":
        """Create a DecisionRecord with a UUID."""
        return cls(id=str(uuid.uuid4()), decision_type=decision_type, title=title, rationale=rationale, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "decision_type": self.decision_type.value,
            "title": self.title,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "alternatives": self.alternatives,
            "evidence_refs": self.evidence_refs,
            "cost_impact": self.cost_impact,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionRecord":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            decision_type=DecisionType(data["decision_type"]),
            title=data["title"],
            rationale=data["rationale"],
            confidence=data.get("confidence", 0.0),
            alternatives=data.get("alternatives", []),
            evidence_refs=data.get("evidence_refs", []),
            cost_impact=data.get("cost_impact", 0.0),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else _utc_now(),
            context=data.get("context", {}),
        )


@dataclass
class SourceValidation:
    """Result of validating a source against its claim."""

    source_id: str
    claim_id: str
    support_class: SupportClass
    explanation: str
    validated_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "claim_id": self.claim_id,
            "support_class": self.support_class.value,
            "explanation": self.explanation,
            "validated_at": self.validated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceValidation":
        return cls(
            source_id=data["source_id"],
            claim_id=data["claim_id"],
            support_class=SupportClass(data["support_class"]),
            explanation=data["explanation"],
            validated_at=datetime.fromisoformat(data["validated_at"]) if data.get("validated_at") else _utc_now(),
        )


@dataclass
class ConsensusResult:
    """Result of multi-provider consensus research."""

    query: str
    provider_responses: list[dict] = field(default_factory=list)
    agreement_score: float = 0.0
    consensus_answer: str = ""
    confidence: float = 0.0
    total_cost: float = 0.0
    decision_record: Optional[DecisionRecord] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "provider_responses": self.provider_responses,
            "agreement_score": self.agreement_score,
            "consensus_answer": self.consensus_answer,
            "confidence": self.confidence,
            "total_cost": self.total_cost,
            "decision_record": self.decision_record.to_dict() if self.decision_record else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConsensusResult":
        return cls(
            query=data["query"],
            provider_responses=data.get("provider_responses", []),
            agreement_score=data.get("agreement_score", 0.0),
            consensus_answer=data.get("consensus_answer", ""),
            confidence=data.get("confidence", 0.0),
            total_cost=data.get("total_cost", 0.0),
            decision_record=DecisionRecord.from_dict(data["decision_record"]) if data.get("decision_record") else None,
        )


@dataclass
class ExpertManifest:
    """Complete snapshot of an expert's state.

    Composes claims, gaps, decisions, and policies into a single typed payload.

    Attributes:
        expert_name: Name of the expert
        domain: Expert's domain
        claims: All claims held by the expert
        gaps: All knowledge gaps
        decisions: All decision records
        policies: Configuration (refresh_days, budget_cap, velocity)
        generated_at: When this manifest was created
    """

    expert_name: str
    domain: str
    claims: list[Claim] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    decisions: list[DecisionRecord] = field(default_factory=list)
    policies: dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=_utc_now)

    @property
    def claim_count(self) -> int:
        return len(self.claims)

    @property
    def open_gap_count(self) -> int:
        return sum(1 for g in self.gaps if not g.filled)

    @property
    def avg_confidence(self) -> float:
        if not self.claims:
            return 0.0
        return sum(c.confidence for c in self.claims) / len(self.claims)

    def top_gaps(self, n: int = 5) -> list[Gap]:
        """Return top N unfilled gaps by ev_cost_ratio descending."""
        unfilled = [g for g in self.gaps if not g.filled]
        return sorted(unfilled, key=lambda g: g.ev_cost_ratio, reverse=True)[:n]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "expert_name": self.expert_name,
            "domain": self.domain,
            "claims": [c.to_dict() for c in self.claims],
            "gaps": [g.to_dict() for g in self.gaps],
            "decisions": [d.to_dict() for d in self.decisions],
            "policies": self.policies,
            "generated_at": self.generated_at.isoformat(),
            "claim_count": self.claim_count,
            "open_gap_count": self.open_gap_count,
            "avg_confidence": self.avg_confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExpertManifest":
        """Create from dictionary."""
        return cls(
            expert_name=data["expert_name"],
            domain=data["domain"],
            claims=[Claim.from_dict(c) for c in data.get("claims", [])],
            gaps=[Gap.from_dict(g) for g in data.get("gaps", [])],
            decisions=[DecisionRecord.from_dict(d) for d in data.get("decisions", [])],
            policies=data.get("policies", {}),
            generated_at=datetime.fromisoformat(data["generated_at"]) if data.get("generated_at") else _utc_now(),
        )
