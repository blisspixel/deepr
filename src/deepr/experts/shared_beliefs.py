"""Cross-expert shared belief storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from deepr.config import experts_root

if TYPE_CHECKING:
    from deepr.experts.beliefs import Belief, BeliefStore


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

    def __init__(self, storage_dir: Path | None = None):
        """Initialize shared belief store.

        Args:
            storage_dir: Directory for storage
        """
        if storage_dir is None:
            storage_dir = experts_root().parent / "shared" / "beliefs"
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

    def get_shared_beliefs(
        self,
        domain: str,
        min_confidence: float = 0.5,
        exclude_stale: bool = True,
    ) -> list[Belief]:
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

        from deepr.experts.beliefs import Belief

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

    def _find_similar_in_domain(self, belief: Belief, domain: str) -> Belief | None:
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

    def _save(self) -> None:
        """Save shared beliefs to disk."""
        data = {
            "domains": {
                domain: {bid: belief.to_dict() for bid, belief in beliefs.items()}
                for domain, beliefs in self.domain_stores.items()
            },
            "contributors": {bid: list(experts) for bid, experts in self.contributors.items()},
        }

        from deepr.utils.atomic_io import atomic_write_json

        atomic_write_json(self.storage_path, data)

    def _load(self) -> None:
        """Load shared beliefs from disk."""
        if not self.storage_path.exists():
            return

        from deepr.experts.beliefs import Belief

        with open(self.storage_path, encoding="utf-8") as file:
            data = json.load(file)

        for domain, beliefs in data.get("domains", {}).items():
            self.domain_stores[domain] = {bid: Belief.from_dict(bdata) for bid, bdata in beliefs.items()}

        self.contributors = {bid: set(experts) for bid, experts in data.get("contributors", {}).items()}
