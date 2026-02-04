"""Context pruning for long research sessions.

Intelligently prunes context to stay within token budgets while
preserving the most relevant and recent information.

Usage:
    from deepr.services.context_pruner import ContextPruner

    pruner = ContextPruner()

    # Prune context items to fit budget
    pruned_items, decision = pruner.prune(
        context_items=items,
        current_query="quantum computing applications",
        token_budget=4000
    )
"""

import re
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


@dataclass
class ContextItem:
    """A single item of context to potentially include."""
    id: str
    text: str
    source: str
    timestamp: datetime
    phase: int
    importance: float = 0.5
    tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.tokens == 0:
            # Rough token estimate: ~4 chars per token
            self.tokens = len(self.text) // 4 + 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "phase": self.phase,
            "importance": self.importance,
            "tokens": self.tokens,
            "metadata": self.metadata,
        }


@dataclass
class PruningDecision:
    """Record of pruning decisions made."""
    original_count: int
    pruned_count: int
    original_tokens: int
    final_tokens: int
    budget: int
    items_removed: List[str]  # IDs of removed items
    removal_reasons: Dict[str, str]  # ID -> reason
    strategy_used: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_count": self.original_count,
            "pruned_count": self.pruned_count,
            "original_tokens": self.original_tokens,
            "final_tokens": self.final_tokens,
            "budget": self.budget,
            "items_removed": self.items_removed,
            "removal_reasons": self.removal_reasons,
            "strategy_used": self.strategy_used,
            "tokens_saved": self.original_tokens - self.final_tokens,
            "removal_rate": len(self.items_removed) / max(self.original_count, 1),
        }


class ContextPruner:
    """Prunes context to fit within token budgets.

    Uses multiple strategies:
    1. Relevance scoring (TF-IDF-like) to current query
    2. Recency weighting (newer is more valuable)
    3. Importance scoring (pre-computed from source quality)
    4. Deduplication (remove near-duplicates)

    Attributes:
        recency_weight: Weight for recency in scoring (0-1)
        relevance_weight: Weight for relevance in scoring (0-1)
        importance_weight: Weight for importance in scoring (0-1)
        dedup_threshold: Similarity threshold for deduplication
    """

    def __init__(
        self,
        recency_weight: float = 0.3,
        relevance_weight: float = 0.4,
        importance_weight: float = 0.3,
        dedup_threshold: float = 0.8,
    ):
        """Initialize the pruner.

        Args:
            recency_weight: Weight for recency scoring
            relevance_weight: Weight for query relevance
            importance_weight: Weight for item importance
            dedup_threshold: Jaccard similarity threshold for deduplication
        """
        self.recency_weight = recency_weight
        self.relevance_weight = relevance_weight
        self.importance_weight = importance_weight
        self.dedup_threshold = dedup_threshold

    def prune(
        self,
        context_items: List[ContextItem],
        current_query: str,
        token_budget: int,
        preserve_recent_phases: int = 1,
    ) -> Tuple[List[ContextItem], PruningDecision]:
        """Prune context items to fit token budget.

        Args:
            context_items: List of context items to prune
            current_query: Current research query for relevance scoring
            token_budget: Maximum tokens allowed
            preserve_recent_phases: Number of recent phases to always preserve

        Returns:
            Tuple of (pruned items list, PruningDecision)
        """
        if not context_items:
            return [], PruningDecision(
                original_count=0,
                pruned_count=0,
                original_tokens=0,
                final_tokens=0,
                budget=token_budget,
                items_removed=[],
                removal_reasons={},
                strategy_used="empty_input",
            )

        original_count = len(context_items)
        original_tokens = sum(item.tokens for item in context_items)

        # If already within budget, return as-is
        if original_tokens <= token_budget:
            return context_items, PruningDecision(
                original_count=original_count,
                pruned_count=original_count,
                original_tokens=original_tokens,
                final_tokens=original_tokens,
                budget=token_budget,
                items_removed=[],
                removal_reasons={},
                strategy_used="no_pruning_needed",
            )

        # Step 1: Remove duplicates
        items, dup_reasons = self._remove_duplicates(context_items)

        # Step 2: Score remaining items
        scored_items = []
        for item in items:
            score = self.score_item(item, current_query, _utc_now())
            scored_items.append((item, score))

        # Sort by score (highest first)
        scored_items.sort(key=lambda x: x[1], reverse=True)

        # Step 3: Determine which phases to preserve
        max_phase = max(item.phase for item in items) if items else 0
        preserved_phases = set(range(max(1, max_phase - preserve_recent_phases + 1), max_phase + 1))

        # Step 4: Select items within budget
        selected = []
        current_tokens = 0
        removed = []
        removal_reasons = dict(dup_reasons)

        # First, add preserved phase items
        for item, score in scored_items:
            if item.phase in preserved_phases:
                if current_tokens + item.tokens <= token_budget:
                    selected.append(item)
                    current_tokens += item.tokens
                else:
                    removed.append(item.id)
                    removal_reasons[item.id] = "budget_exceeded_preserved_phase"

        # Then add highest-scoring remaining items
        for item, score in scored_items:
            if item.phase not in preserved_phases:
                if current_tokens + item.tokens <= token_budget:
                    selected.append(item)
                    current_tokens += item.tokens
                else:
                    removed.append(item.id)
                    removal_reasons[item.id] = f"low_score_{score:.2f}"

        # Sort selected by phase and timestamp for coherent output
        selected.sort(key=lambda x: (x.phase, x.timestamp))

        return selected, PruningDecision(
            original_count=original_count,
            pruned_count=len(selected),
            original_tokens=original_tokens,
            final_tokens=current_tokens,
            budget=token_budget,
            items_removed=removed,
            removal_reasons=removal_reasons,
            strategy_used="score_based_pruning",
        )

    def score_item(
        self,
        item: ContextItem,
        query: str,
        now: datetime,
    ) -> float:
        """Score a context item for relevance.

        Args:
            item: Context item to score
            query: Current query for relevance
            now: Current time for recency

        Returns:
            Score between 0 and 1
        """
        # Recency score (exponential decay)
        recency_score = self._calculate_recency_score(item.timestamp, now)

        # Relevance score (term overlap)
        relevance_score = self._calculate_relevance_score(item.text, query)

        # Importance score (from item metadata)
        importance_score = item.importance

        # Weighted combination
        score = (
            self.recency_weight * recency_score +
            self.relevance_weight * relevance_score +
            self.importance_weight * importance_score
        )

        return min(1.0, max(0.0, score))

    def _calculate_recency_score(
        self,
        timestamp: datetime,
        now: datetime,
    ) -> float:
        """Calculate recency score with exponential decay.

        Args:
            timestamp: Item timestamp
            now: Current time

        Returns:
            Recency score (0-1)
        """
        # Make timestamps tz-aware if they aren't
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        age_seconds = (now - timestamp).total_seconds()

        # Decay with half-life of 1 hour
        half_life = 3600
        score = math.exp(-0.693 * age_seconds / half_life)

        return min(1.0, max(0.0, score))

    def _calculate_relevance_score(self, text: str, query: str) -> float:
        """Calculate relevance score based on term overlap.

        Args:
            text: Item text
            query: Query to compare against

        Returns:
            Relevance score (0-1)
        """
        # Tokenize
        text_tokens = self._tokenize(text)
        query_tokens = self._tokenize(query)

        if not query_tokens:
            return 0.5  # Neutral if no query

        # Calculate term frequency overlap
        text_counter = Counter(text_tokens)
        query_set = set(query_tokens)

        # Count matching terms
        matches = sum(1 for t in query_set if t in text_counter)
        overlap = matches / len(query_set)

        # Boost for exact phrase matches
        query_lower = query.lower()
        if query_lower in text.lower():
            overlap = min(1.0, overlap + 0.3)

        return overlap

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text for comparison.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens
        """
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        tokens = [t for t in text.split() if len(t) > 2]
        return tokens

    def _remove_duplicates(
        self,
        items: List[ContextItem],
    ) -> Tuple[List[ContextItem], Dict[str, str]]:
        """Remove near-duplicate items.

        Args:
            items: List of items to deduplicate

        Returns:
            Tuple of (deduplicated items, removal reasons dict)
        """
        unique = []
        removal_reasons = {}

        for item in items:
            is_dup = False

            for existing in unique:
                similarity = self._jaccard_similarity(item.text, existing.text)
                if similarity >= self.dedup_threshold:
                    # Keep the one with higher importance
                    if item.importance > existing.importance:
                        unique.remove(existing)
                        unique.append(item)
                        removal_reasons[existing.id] = f"duplicate_of_{item.id}"
                    else:
                        removal_reasons[item.id] = f"duplicate_of_{existing.id}"
                    is_dup = True
                    break

            if not is_dup:
                unique.append(item)

        return unique, removal_reasons

    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-1)
        """
        tokens1 = set(self._tokenize(text1))
        tokens2 = set(self._tokenize(text2))

        if not tokens1 or not tokens2:
            return 0.0

        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        return intersection / union if union > 0 else 0.0


class AdaptivePruner(ContextPruner):
    """Adaptive pruner that learns from usage patterns.

    Extends ContextPruner with:
    - Learning which items are actually used
    - Adjusting weights based on feedback
    - Caching relevance scores
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._usage_history: Dict[str, int] = {}  # item_id -> use count
        self._score_cache: Dict[str, float] = {}

    def record_usage(self, item_id: str):
        """Record that an item was actually used.

        Args:
            item_id: ID of the used item
        """
        self._usage_history[item_id] = self._usage_history.get(item_id, 0) + 1

    def score_item(
        self,
        item: ContextItem,
        query: str,
        now: datetime,
    ) -> float:
        """Score item with usage history bonus.

        Args:
            item: Item to score
            query: Current query
            now: Current time

        Returns:
            Adjusted score
        """
        base_score = super().score_item(item, query, now)

        # Boost for historically useful items
        usage_count = self._usage_history.get(item.id, 0)
        usage_bonus = min(0.2, usage_count * 0.05)

        return min(1.0, base_score + usage_bonus)

    def reset_history(self):
        """Reset usage history."""
        self._usage_history.clear()
        self._score_cache.clear()
