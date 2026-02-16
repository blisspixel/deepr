"""Belief system for expert consciousness.

Implements belief objects with:
- Claim, confidence, evidence tracking
- Belief revision with conflict resolution
- Confidence decay over time
- Cross-expert knowledge sharing

Usage:
    from deepr.experts.beliefs import Belief, BeliefStore

    belief = Belief(
        claim="Python 3.12 supports pattern matching",
        confidence=0.95,
        evidence_refs=["doc_001", "doc_002"],
        domain="python"
    )

    store = BeliefStore(expert_name="python_expert")
    store.add_belief(belief)
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from deepr.core.contracts import Claim


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class ConflictResolution(Enum):
    """Conflict resolution strategies."""

    NEWER_WINS = "newer_wins"
    HIGHER_CONFIDENCE = "higher_confidence"
    MERGE = "merge"
    ASK_USER = "ask_user"
    ADJUDICATE = "adjudicate"


@dataclass
class Belief:
    """A belief held by an expert.

    Attributes:
        claim: The belief statement
        confidence: Confidence level 0-1
        evidence_refs: References to supporting evidence
        domain: Knowledge domain
        created_at: When belief was formed
        updated_at: When belief was last updated
        contradictions_with: IDs of contradicting beliefs
        source_type: How belief was acquired
        decay_rate: Confidence decay rate per day
        history: History of belief changes
    """

    claim: str
    confidence: float
    evidence_refs: list[str] = field(default_factory=list)
    domain: str = ""
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    contradictions_with: list[str] = field(default_factory=list)
    source_type: str = "learned"  # learned, inferred, user_provided
    decay_rate: float = 0.01  # Per day
    history: list[dict[str, Any]] = field(default_factory=list)
    id: str = field(default="")

    def __post_init__(self):
        if not self.id:
            import hashlib

            content = f"{self.claim}:{self.domain}:{self.created_at.isoformat()}"
            self.id = hashlib.sha256(content.encode()).hexdigest()[:12]

    def get_current_confidence(self) -> float:
        """Get confidence with decay applied.

        Returns:
            Current confidence after decay
        """
        days_elapsed = (datetime.now(timezone.utc) - self.updated_at).days
        decayed = self.confidence * math.exp(-self.decay_rate * days_elapsed)
        return max(0.0, min(1.0, decayed))

    def update_confidence(self, new_confidence: float, reason: str = ""):
        """Update belief confidence.

        Args:
            new_confidence: New confidence value
            reason: Reason for update
        """
        self.history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "old_confidence": self.confidence,
                "new_confidence": new_confidence,
                "reason": reason,
            }
        )
        self.confidence = new_confidence
        self.updated_at = datetime.now(timezone.utc)

    def add_evidence(self, evidence_ref: str):
        """Add evidence reference.

        Args:
            evidence_ref: Reference to evidence
        """
        if evidence_ref not in self.evidence_refs:
            self.evidence_refs.append(evidence_ref)
            self.updated_at = datetime.now(timezone.utc)

    def add_contradiction(self, belief_id: str):
        """Mark contradiction with another belief.

        Args:
            belief_id: ID of contradicting belief
        """
        if belief_id not in self.contradictions_with:
            self.contradictions_with.append(belief_id)

    def is_stale(self, threshold: float = 0.3) -> bool:
        """Check if belief is stale.

        Args:
            threshold: Confidence threshold for staleness

        Returns:
            True if current confidence below threshold
        """
        return self.get_current_confidence() < threshold

    def to_claim(self) -> "Claim":
        """Convert to canonical Claim type.

        Returns:
            Claim with confidence decay applied.
        """
        from deepr.core.contracts import Claim, Source, TrustClass

        sources = [Source.create(title=ref, trust_class=TrustClass.TERTIARY) for ref in self.evidence_refs]
        return Claim(
            id=self.id,
            statement=self.claim,
            domain=self.domain,
            confidence=self.get_current_confidence(),
            sources=sources,
            created_at=self.created_at,
            updated_at=self.updated_at,
            contradicts=list(self.contradictions_with),
            tags=[self.source_type] if self.source_type else [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "claim": self.claim,
            "confidence": self.confidence,
            "evidence_refs": self.evidence_refs,
            "domain": self.domain,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "contradictions_with": self.contradictions_with,
            "source_type": self.source_type,
            "decay_rate": self.decay_rate,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Belief":
        return cls(
            id=data.get("id", ""),
            claim=data["claim"],
            confidence=data["confidence"],
            evidence_refs=data.get("evidence_refs", []),
            domain=data.get("domain", ""),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if "updated_at" in data
            else datetime.now(timezone.utc),
            contradictions_with=data.get("contradictions_with", []),
            source_type=data.get("source_type", "learned"),
            decay_rate=data.get("decay_rate", 0.01),
            history=data.get("history", []),
        )


@dataclass
class BeliefChange:
    """Record of a belief change.

    Attributes:
        belief_id: ID of changed belief
        change_type: Type of change
        old_claim: Previous claim (if changed)
        new_claim: New claim
        old_confidence: Previous confidence
        new_confidence: New confidence
        reason: Reason for change
        evidence: Evidence that triggered change
        timestamp: When change occurred
    """

    belief_id: str
    change_type: str  # created, updated, revised, archived
    new_claim: str
    new_confidence: float
    old_claim: str = ""
    old_confidence: float = 0.0
    reason: str = ""
    evidence: str = ""
    timestamp: datetime = field(default_factory=_utc_now)

    def to_expression(self) -> str:
        """Generate natural language expression of change.

        Returns:
            Human-readable description of belief change
        """
        if self.change_type == "created":
            return f"I now believe that {self.new_claim} (confidence: {self.new_confidence:.0%})"

        if self.change_type == "revised" and self.old_claim:
            return (
                f"I used to think {self.old_claim}, "
                f"but now I believe {self.new_claim} "
                f"because {self.reason or 'new evidence'}"
            )

        if self.change_type == "updated":
            conf_change = self.new_confidence - self.old_confidence
            direction = "more" if conf_change > 0 else "less"
            return (
                f"I'm now {direction} confident that {self.new_claim} "
                f"({self.old_confidence:.0%} → {self.new_confidence:.0%})"
            )

        if self.change_type == "archived":
            return f"I no longer hold the belief that {self.old_claim}"

        return f"Belief updated: {self.new_claim}"


class BeliefStore:
    """Store and manage beliefs for an expert.

    Attributes:
        expert_name: Name of the expert
        beliefs: Dictionary of beliefs by ID
        domain_index: Index of beliefs by domain
        conflict_resolution: Default conflict resolution strategy
    """

    def __init__(
        self,
        expert_name: str,
        storage_dir: Optional[Path] = None,
        conflict_resolution: ConflictResolution = ConflictResolution.HIGHER_CONFIDENCE,
    ):
        """Initialize belief store.

        Args:
            expert_name: Name of the expert
            storage_dir: Directory for storage
            conflict_resolution: Default conflict resolution strategy
        """
        self.expert_name = expert_name
        self.conflict_resolution = conflict_resolution

        if storage_dir is None:
            storage_dir = Path("data/experts") / expert_name / "beliefs"
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.storage_path = self.storage_dir / "beliefs.json"
        self.changes_path = self.storage_dir / "changes.json"

        self.beliefs: dict[str, Belief] = {}
        self.domain_index: dict[str, set[str]] = {}
        self.changes: list[BeliefChange] = []

        self._load()

    def add_belief(self, belief: Belief, check_conflicts: bool = True) -> tuple[Belief, Optional[BeliefChange]]:
        """Add a belief to the store.

        Args:
            belief: Belief to add
            check_conflicts: Whether to check for conflicts

        Returns:
            Tuple of (added/updated belief, change record)
        """
        # Check for existing similar belief
        existing = self._find_similar(belief)

        if existing:
            # Resolve conflict
            return self._resolve_conflict(existing, belief)

        # Check for contradictions
        if check_conflicts:
            contradictions = self._find_contradictions(belief)
            for contra in contradictions:
                belief.add_contradiction(contra.id)
                contra.add_contradiction(belief.id)

        # Add belief
        self.beliefs[belief.id] = belief
        self._index_belief(belief)

        change = BeliefChange(
            belief_id=belief.id, change_type="created", new_claim=belief.claim, new_confidence=belief.confidence
        )
        self.changes.append(change)

        self._save()
        return belief, change

    def update_belief(
        self,
        belief_id: str,
        new_confidence: Optional[float] = None,
        new_evidence: Optional[str] = None,
        reason: str = "",
    ) -> Optional[BeliefChange]:
        """Update an existing belief.

        Args:
            belief_id: ID of belief to update
            new_confidence: New confidence value
            new_evidence: New evidence reference
            reason: Reason for update

        Returns:
            BeliefChange record or None
        """
        if belief_id not in self.beliefs:
            return None

        belief = self.beliefs[belief_id]
        old_confidence = belief.confidence

        if new_confidence is not None:
            belief.update_confidence(new_confidence, reason)

        if new_evidence:
            belief.add_evidence(new_evidence)

        change = BeliefChange(
            belief_id=belief_id,
            change_type="updated",
            old_claim=belief.claim,
            new_claim=belief.claim,
            old_confidence=old_confidence,
            new_confidence=belief.confidence,
            reason=reason,
            evidence=new_evidence or "",
        )
        self.changes.append(change)

        self._save()
        return change

    def revise_belief(
        self, belief_id: str, new_claim: str, new_confidence: float, reason: str, evidence: str = ""
    ) -> Optional[BeliefChange]:
        """Revise a belief with new information.

        Args:
            belief_id: ID of belief to revise
            new_claim: New claim statement
            new_confidence: New confidence
            reason: Reason for revision
            evidence: Supporting evidence

        Returns:
            BeliefChange record or None
        """
        if belief_id not in self.beliefs:
            return None

        belief = self.beliefs[belief_id]
        old_claim = belief.claim
        old_confidence = belief.confidence

        # Update belief
        belief.claim = new_claim
        belief.update_confidence(new_confidence, reason)
        if evidence:
            belief.add_evidence(evidence)

        change = BeliefChange(
            belief_id=belief_id,
            change_type="revised",
            old_claim=old_claim,
            new_claim=new_claim,
            old_confidence=old_confidence,
            new_confidence=new_confidence,
            reason=reason,
            evidence=evidence,
        )
        self.changes.append(change)

        self._save()
        return change

    def archive_belief(self, belief_id: str, reason: str = "") -> Optional[BeliefChange]:
        """Archive a belief (soft delete).

        Args:
            belief_id: ID of belief to archive
            reason: Reason for archiving

        Returns:
            BeliefChange record or None
        """
        if belief_id not in self.beliefs:
            return None

        belief = self.beliefs[belief_id]

        change = BeliefChange(
            belief_id=belief_id,
            change_type="archived",
            old_claim=belief.claim,
            new_claim="",
            old_confidence=belief.confidence,
            new_confidence=0.0,
            reason=reason,
        )
        self.changes.append(change)

        # Remove from active beliefs
        del self.beliefs[belief_id]
        self._unindex_belief(belief)

        self._save()
        return change

    def get_beliefs_by_domain(self, domain: str) -> list[Belief]:
        """Get all beliefs in a domain.

        Args:
            domain: Domain to query

        Returns:
            List of beliefs in domain
        """
        belief_ids = self.domain_index.get(domain, set())
        return [self.beliefs[bid] for bid in belief_ids if bid in self.beliefs]

    def get_stale_beliefs(self, threshold: float = 0.3) -> list[Belief]:
        """Get beliefs that have become stale.

        Args:
            threshold: Confidence threshold

        Returns:
            List of stale beliefs
        """
        return [b for b in self.beliefs.values() if b.is_stale(threshold)]

    def get_contradictions(self, belief_id: str) -> list[Belief]:
        """Get beliefs that contradict a given belief.

        Args:
            belief_id: ID of belief

        Returns:
            List of contradicting beliefs
        """
        if belief_id not in self.beliefs:
            return []

        belief = self.beliefs[belief_id]
        return [self.beliefs[cid] for cid in belief.contradictions_with if cid in self.beliefs]

    def get_recent_changes(self, limit: int = 10) -> list[BeliefChange]:
        """Get recent belief changes.

        Args:
            limit: Maximum changes to return

        Returns:
            List of recent changes
        """
        return self.changes[-limit:]

    def _find_similar(self, belief: Belief) -> Optional[Belief]:
        """Find similar existing belief.

        Args:
            belief: Belief to compare

        Returns:
            Similar belief or None
        """
        # Simple similarity: same domain and overlapping words
        domain_beliefs = self.get_beliefs_by_domain(belief.domain)

        belief_words = set(belief.claim.lower().split())

        for existing in domain_beliefs:
            existing_words = set(existing.claim.lower().split())
            overlap = len(belief_words & existing_words)
            similarity = overlap / max(len(belief_words), len(existing_words), 1)

            if similarity > 0.7:
                return existing

        return None

    def _find_contradictions(self, belief: Belief) -> list[Belief]:
        """Find beliefs that might contradict.

        Args:
            belief: Belief to check

        Returns:
            List of potentially contradicting beliefs
        """
        # Simple heuristic: same domain, contains negation words
        contradictions = []
        negation_words = {"not", "no", "never", "false", "incorrect", "wrong"}

        belief_words = set(belief.claim.lower().split())
        has_negation = bool(belief_words & negation_words)

        for existing in self.get_beliefs_by_domain(belief.domain):
            existing_words = set(existing.claim.lower().split())
            existing_negation = bool(existing_words & negation_words)

            # Check for opposite polarity on similar topics
            content_overlap = len(belief_words & existing_words - negation_words)
            if content_overlap > 2 and has_negation != existing_negation:
                contradictions.append(existing)

        return contradictions

    def _resolve_conflict(self, existing: Belief, new: Belief) -> tuple[Belief, Optional[BeliefChange]]:
        """Resolve conflict between beliefs.

        Args:
            existing: Existing belief
            new: New belief

        Returns:
            Tuple of (resolved belief, change record)
        """
        if self.conflict_resolution == ConflictResolution.NEWER_WINS:
            # Replace with new belief
            change = self.revise_belief(existing.id, new.claim, new.confidence, "Newer information available")
            return self.beliefs[existing.id], change

        if self.conflict_resolution == ConflictResolution.HIGHER_CONFIDENCE:
            if new.confidence > existing.confidence:
                change = self.revise_belief(existing.id, new.claim, new.confidence, "Higher confidence evidence")
                return self.beliefs[existing.id], change
            else:
                # Keep existing, but note the new evidence
                existing.add_evidence(f"conflicting:{new.id}")
                return existing, None

        if self.conflict_resolution == ConflictResolution.MERGE:
            # Merge evidence, average confidence
            merged_confidence = (existing.confidence + new.confidence) / 2
            for ref in new.evidence_refs:
                existing.add_evidence(ref)
            existing.update_confidence(merged_confidence, "Merged with new evidence")

            change = BeliefChange(
                belief_id=existing.id,
                change_type="updated",
                old_claim=existing.claim,
                new_claim=existing.claim,
                old_confidence=existing.confidence,
                new_confidence=merged_confidence,
                reason="Merged beliefs",
            )
            self.changes.append(change)
            self._save()
            return existing, change

        # ASK_USER - return both for user decision
        return existing, None

    def _index_belief(self, belief: Belief):
        """Add belief to domain index."""
        if belief.domain not in self.domain_index:
            self.domain_index[belief.domain] = set()
        self.domain_index[belief.domain].add(belief.id)

    def _unindex_belief(self, belief: Belief):
        """Remove belief from domain index."""
        if belief.domain in self.domain_index:
            self.domain_index[belief.domain].discard(belief.id)

    def _save(self):
        """Save beliefs to disk."""
        data = {
            "beliefs": {bid: b.to_dict() for bid, b in self.beliefs.items()},
            "changes": [
                {
                    "belief_id": c.belief_id,
                    "change_type": c.change_type,
                    "old_claim": c.old_claim,
                    "new_claim": c.new_claim,
                    "old_confidence": c.old_confidence,
                    "new_confidence": c.new_confidence,
                    "reason": c.reason,
                    "evidence": c.evidence,
                    "timestamp": c.timestamp.isoformat(),
                }
                for c in self.changes[-100:]  # Keep last 100 changes
            ],
        }

        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load(self):
        """Load beliefs from disk."""
        if not self.storage_path.exists():
            return

        with open(self.storage_path, encoding="utf-8") as f:
            data = json.load(f)

        self.beliefs = {bid: Belief.from_dict(bdata) for bid, bdata in data.get("beliefs", {}).items()}

        # Rebuild domain index
        for belief in self.beliefs.values():
            self._index_belief(belief)

        # Load changes
        for cdata in data.get("changes", []):
            self.changes.append(
                BeliefChange(
                    belief_id=cdata["belief_id"],
                    change_type=cdata["change_type"],
                    old_claim=cdata.get("old_claim", ""),
                    new_claim=cdata["new_claim"],
                    old_confidence=cdata.get("old_confidence", 0.0),
                    new_confidence=cdata["new_confidence"],
                    reason=cdata.get("reason", ""),
                    evidence=cdata.get("evidence", ""),
                    timestamp=datetime.fromisoformat(cdata["timestamp"])
                    if "timestamp" in cdata
                    else datetime.now(timezone.utc),
                )
            )


class SharedBeliefStore:
    """Shared belief store for cross-expert knowledge sharing.

    Beliefs are namespaced by domain to prevent conflicts.
    Each expert can contribute and consume shared beliefs.

    Attributes:
        storage_dir: Directory for shared storage
        domain_stores: Per-domain belief stores
        domain_velocities: Domain velocity for TTL calculation
    """

    # Default domain velocities (days until stale)
    DEFAULT_VELOCITIES = {
        "technology": 90,
        "science": 365,
        "business": 180,
        "general": 365,
        "current_events": 7,
        "regulations": 180,
    }

    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize shared belief store.

        Args:
            storage_dir: Directory for storage
        """
        if storage_dir is None:
            storage_dir = Path("data/shared/beliefs")
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.storage_path = self.storage_dir / "shared_beliefs.json"
        self.domain_stores: dict[str, dict[str, Belief]] = {}
        self.contributors: dict[str, set[str]] = {}  # belief_id -> expert_names

        self._load()

    def share_belief(self, belief: Belief, expert_name: str, min_confidence: float = 0.7) -> bool:
        """Share a belief from an expert.

        Args:
            belief: Belief to share
            expert_name: Name of contributing expert
            min_confidence: Minimum confidence to share

        Returns:
            True if belief was shared
        """
        # Only share high-confidence beliefs
        if belief.get_current_confidence() < min_confidence:
            return False

        domain = belief.domain or "general"

        if domain not in self.domain_stores:
            self.domain_stores[domain] = {}

        # Check for existing similar belief
        existing = self._find_similar_in_domain(belief, domain)

        if existing:
            # Merge evidence and update confidence
            for ref in belief.evidence_refs:
                existing.add_evidence(ref)

            # Weighted average based on number of contributors
            num_contributors = len(self.contributors.get(existing.id, set()))
            new_confidence = (existing.confidence * num_contributors + belief.confidence) / (num_contributors + 1)
            existing.update_confidence(new_confidence, f"Corroborated by {expert_name}")

            # Track contributor
            if existing.id not in self.contributors:
                self.contributors[existing.id] = set()
            self.contributors[existing.id].add(expert_name)
        else:
            # Add new shared belief
            self.domain_stores[domain][belief.id] = belief
            self.contributors[belief.id] = {expert_name}

        self._save()
        return True

    def get_shared_beliefs(self, domain: str, min_confidence: float = 0.5, exclude_stale: bool = True) -> list[Belief]:
        """Get shared beliefs for a domain.

        Args:
            domain: Domain to query
            min_confidence: Minimum confidence threshold
            exclude_stale: Whether to exclude stale beliefs

        Returns:
            List of shared beliefs
        """
        if domain not in self.domain_stores:
            return []

        beliefs = []
        stale_threshold = self._get_stale_threshold(domain)

        for belief in self.domain_stores[domain].values():
            current_conf = belief.get_current_confidence()

            if current_conf < min_confidence:
                continue

            if exclude_stale and belief.is_stale(stale_threshold):
                continue

            beliefs.append(belief)

        return sorted(beliefs, key=lambda b: b.get_current_confidence(), reverse=True)

    def import_to_expert(self, expert_store: BeliefStore, domain: str, max_beliefs: int = 10) -> int:
        """Import shared beliefs to an expert's store.

        Args:
            expert_store: Expert's belief store
            domain: Domain to import from
            max_beliefs: Maximum beliefs to import

        Returns:
            Number of beliefs imported
        """
        shared = self.get_shared_beliefs(domain)[:max_beliefs]
        imported = 0

        for belief in shared:
            # Create copy for expert
            expert_belief = Belief(
                claim=belief.claim,
                confidence=belief.confidence * 0.9,  # Slight discount for shared
                evidence_refs=belief.evidence_refs.copy(),
                domain=belief.domain,
                source_type="shared",
            )

            expert_store.add_belief(expert_belief, check_conflicts=True)
            imported += 1

        return imported

    def get_contributors(self, belief_id: str) -> set[str]:
        """Get experts who contributed to a belief.

        Args:
            belief_id: ID of belief

        Returns:
            Set of expert names
        """
        return self.contributors.get(belief_id, set())

    def cleanup_stale(self) -> int:
        """Remove stale beliefs from shared store.

        Returns:
            Number of beliefs removed
        """
        removed = 0

        for domain, beliefs in list(self.domain_stores.items()):
            threshold = self._get_stale_threshold(domain)

            stale_ids = [bid for bid, belief in beliefs.items() if belief.is_stale(threshold)]

            for bid in stale_ids:
                del beliefs[bid]
                if bid in self.contributors:
                    del self.contributors[bid]
                removed += 1

        if removed > 0:
            self._save()

        return removed

    def _find_similar_in_domain(self, belief: Belief, domain: str) -> Optional[Belief]:
        """Find similar belief in domain.

        Args:
            belief: Belief to compare
            domain: Domain to search

        Returns:
            Similar belief or None
        """
        if domain not in self.domain_stores:
            return None

        belief_words = set(belief.claim.lower().split())

        for existing in self.domain_stores[domain].values():
            existing_words = set(existing.claim.lower().split())
            overlap = len(belief_words & existing_words)
            similarity = overlap / max(len(belief_words), len(existing_words), 1)

            if similarity > 0.7:
                return existing

        return None

    def _get_stale_threshold(self, domain: str) -> float:
        """Get staleness threshold for domain.

        Args:
            domain: Domain name

        Returns:
            Confidence threshold for staleness
        """
        velocity_days = self.DEFAULT_VELOCITIES.get(domain, 365)
        # Faster domains have higher staleness threshold
        return 0.5 if velocity_days < 30 else 0.3

    def _save(self):
        """Save shared beliefs to disk."""
        data = {
            "domains": {
                domain: {bid: b.to_dict() for bid, b in beliefs.items()}
                for domain, beliefs in self.domain_stores.items()
            },
            "contributors": {bid: list(experts) for bid, experts in self.contributors.items()},
        }

        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load(self):
        """Load shared beliefs from disk."""
        if not self.storage_path.exists():
            return

        with open(self.storage_path, encoding="utf-8") as f:
            data = json.load(f)

        for domain, beliefs in data.get("domains", {}).items():
            self.domain_stores[domain] = {bid: Belief.from_dict(bdata) for bid, bdata in beliefs.items()}

        self.contributors = {bid: set(experts) for bid, experts in data.get("contributors", {}).items()}
