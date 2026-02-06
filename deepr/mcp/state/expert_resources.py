"""
Expert Resources for MCP.

Exposes expert profiles, beliefs, and knowledge gaps as MCP Resources.
Enables Claude to inspect expert state before querying.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ExpertProfile:
    """Expert profile resource data."""

    expert_id: str
    name: str
    domain: str
    description: str
    document_count: int = 0
    conversation_count: int = 0
    total_cost: float = 0.0
    created_at: Optional[datetime] = None
    last_refresh: Optional[datetime] = None
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "expert_id": self.expert_id,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "document_count": self.document_count,
            "conversation_count": self.conversation_count,
            "total_cost": self.total_cost,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "capabilities": self.capabilities,
        }


@dataclass
class ExpertBelief:
    """A single belief held by an expert."""

    text: str
    confidence: float  # 0.0 to 1.0
    source: Optional[str] = None
    added_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "source": self.source,
            "added_at": self.added_at.isoformat(),
        }


@dataclass
class ExpertBeliefs:
    """Collection of expert beliefs/knowledge."""

    expert_id: str
    beliefs: list[ExpertBelief] = field(default_factory=list)
    overall_confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "expert_id": self.expert_id,
            "beliefs": [b.to_dict() for b in self.beliefs],
            "overall_confidence": self.overall_confidence,
            "belief_count": len(self.beliefs),
        }

    def add_belief(self, text: str, confidence: float, source: Optional[str] = None) -> None:
        """
        Add a belief and recalculate overall confidence.

        Args:
            text: The belief text
            confidence: Confidence score (clamped to 0.0-1.0)
            source: Optional source citation

        Note:
            Confidence values outside 0.0-1.0 are clamped to valid range.
        """
        # Clamp confidence to valid range
        clamped_confidence = max(0.0, min(1.0, confidence))

        self.beliefs.append(ExpertBelief(text=text, confidence=clamped_confidence, source=source))
        self._recalculate_confidence()

    def _recalculate_confidence(self) -> None:
        """Recalculate overall confidence as weighted average."""
        if not self.beliefs:
            self.overall_confidence = 0.0
            return

        total = sum(b.confidence for b in self.beliefs)
        self.overall_confidence = total / len(self.beliefs)


@dataclass
class KnowledgeGap:
    """A gap in expert knowledge."""

    topic: str
    severity: str  # "low", "medium", "high"
    suggested_research: Optional[str] = None
    identified_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "severity": self.severity,
            "suggested_research": self.suggested_research,
            "identified_at": self.identified_at.isoformat(),
        }


@dataclass
class ExpertGaps:
    """Collection of knowledge gaps for an expert."""

    expert_id: str
    gaps: list[KnowledgeGap] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "expert_id": self.expert_id,
            "gaps": [g.to_dict() for g in self.gaps],
            "gap_count": len(self.gaps),
            "high_priority_count": len([g for g in self.gaps if g.severity == "high"]),
        }

    def add_gap(self, topic: str, severity: str = "medium", suggested_research: Optional[str] = None) -> None:
        """Add a knowledge gap."""
        self.gaps.append(KnowledgeGap(topic=topic, severity=severity, suggested_research=suggested_research))


class ExpertResourceManager:
    """
    Manages expert resources for MCP exposure.

    Provides access to expert profiles, beliefs, and knowledge gaps
    as MCP Resources that can be subscribed to.
    """

    def __init__(self):
        self._profiles: dict[str, ExpertProfile] = {}
        self._beliefs: dict[str, ExpertBeliefs] = {}
        self._gaps: dict[str, ExpertGaps] = {}

    def register_expert(self, expert_id: str, name: str, domain: str, description: str, **kwargs) -> ExpertProfile:
        """
        Register an expert and create associated resources.

        Args:
            expert_id: Unique expert identifier
            name: Expert name
            domain: Domain of expertise
            description: Expert description
            **kwargs: Additional profile fields

        Returns:
            Created ExpertProfile
        """
        profile = ExpertProfile(expert_id=expert_id, name=name, domain=domain, description=description, **kwargs)

        self._profiles[expert_id] = profile
        self._beliefs[expert_id] = ExpertBeliefs(expert_id=expert_id)
        self._gaps[expert_id] = ExpertGaps(expert_id=expert_id)

        return profile

    def get_profile(self, expert_id: str) -> Optional[ExpertProfile]:
        """Get expert profile."""
        return self._profiles.get(expert_id)

    def get_beliefs(self, expert_id: str) -> Optional[ExpertBeliefs]:
        """Get expert beliefs."""
        return self._beliefs.get(expert_id)

    def get_gaps(self, expert_id: str) -> Optional[ExpertGaps]:
        """Get expert knowledge gaps."""
        return self._gaps.get(expert_id)

    def add_belief(self, expert_id: str, text: str, confidence: float, source: Optional[str] = None) -> bool:
        """
        Add a belief to an expert.

        Args:
            expert_id: Expert identifier
            text: The belief text
            confidence: Confidence score (0.0-1.0, values outside range are clamped)
            source: Optional source citation

        Returns:
            True if added, False if expert not found

        Note:
            Empty text is rejected. Confidence is clamped to valid range.
        """
        if not text or not text.strip():
            return False

        beliefs = self._beliefs.get(expert_id)
        if not beliefs:
            return False

        beliefs.add_belief(text, confidence, source)
        return True

    def add_gap(
        self, expert_id: str, topic: str, severity: str = "medium", suggested_research: Optional[str] = None
    ) -> bool:
        """
        Add a knowledge gap to an expert.

        Returns:
            True if added, False if expert not found
        """
        gaps = self._gaps.get(expert_id)
        if not gaps:
            return False

        gaps.add_gap(topic, severity, suggested_research)
        return True

    def update_profile_stats(
        self,
        expert_id: str,
        document_count: Optional[int] = None,
        conversation_count: Optional[int] = None,
        total_cost: Optional[float] = None,
    ) -> bool:
        """
        Update expert profile statistics.

        Returns:
            True if updated, False if expert not found
        """
        profile = self._profiles.get(expert_id)
        if not profile:
            return False

        if document_count is not None:
            profile.document_count = document_count
        if conversation_count is not None:
            profile.conversation_count = conversation_count
        if total_cost is not None:
            profile.total_cost = total_cost

        return True

    def list_experts(self) -> list[ExpertProfile]:
        """List all registered experts."""
        return list(self._profiles.values())

    def remove_expert(self, expert_id: str) -> bool:
        """
        Remove an expert and all associated resources.

        Returns:
            True if removed, False if not found
        """
        if expert_id not in self._profiles:
            return False

        del self._profiles[expert_id]
        self._beliefs.pop(expert_id, None)
        self._gaps.pop(expert_id, None)

        return True

    def get_resource_uri(self, expert_id: str, resource_type: str) -> str:
        """
        Get the MCP resource URI for an expert resource.

        Args:
            expert_id: Expert identifier
            resource_type: "profile", "beliefs", or "gaps"

        Returns:
            Resource URI string
        """
        return f"deepr://experts/{expert_id}/{resource_type}"

    def resolve_uri(self, uri: str) -> Optional[dict]:
        """
        Resolve a resource URI to its data.

        Args:
            uri: Resource URI like "deepr://experts/abc/profile"

        Returns:
            Resource data dict or None if not found
        """
        import re

        pattern = r"^deepr://experts/(?P<id>[a-zA-Z0-9_-]+)/(?P<type>profile|beliefs|gaps)$"
        match = re.match(pattern, uri)

        if not match:
            return None

        expert_id = match.group("id")
        resource_type = match.group("type")

        if resource_type == "profile":
            profile = self.get_profile(expert_id)
            return profile.to_dict() if profile else None
        elif resource_type == "beliefs":
            beliefs = self.get_beliefs(expert_id)
            return beliefs.to_dict() if beliefs else None
        elif resource_type == "gaps":
            gaps = self.get_gaps(expert_id)
            return gaps.to_dict() if gaps else None

        return None
