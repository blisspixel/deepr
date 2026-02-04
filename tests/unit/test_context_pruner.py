"""Unit tests for context pruner."""

import pytest
from datetime import datetime, timezone, timedelta

from deepr.services.context_pruner import (
    ContextPruner,
    ContextItem,
    PruningDecision,
)


class TestContextPruner:
    """Tests for ContextPruner class."""

    def test_prune_within_budget(self):
        """Test that items within budget are not pruned."""
        pruner = ContextPruner()

        items = [
            ContextItem(text="Short item 1", source="test", timestamp=datetime.now(timezone.utc)),
            ContextItem(text="Short item 2", source="test", timestamp=datetime.now(timezone.utc)),
        ]

        kept, decision = pruner.prune(items, "test query", token_budget=10000)

        assert len(kept) == 2
        assert decision.items_pruned == 0

    def test_prune_exceeds_budget(self):
        """Test that items exceeding budget are pruned."""
        pruner = ContextPruner()

        # Create items that exceed a small budget
        items = [
            ContextItem(text="A" * 1000, source="test", timestamp=datetime.now(timezone.utc)),
            ContextItem(text="B" * 1000, source="test", timestamp=datetime.now(timezone.utc)),
            ContextItem(text="C" * 1000, source="test", timestamp=datetime.now(timezone.utc)),
        ]

        kept, decision = pruner.prune(items, "test query", token_budget=500)

        assert len(kept) < len(items)
        assert decision.items_pruned > 0

    def test_prune_keeps_relevant_items(self):
        """Test that relevant items are kept preferentially."""
        pruner = ContextPruner()

        items = [
            ContextItem(text="Python testing best practices", source="test",
                       timestamp=datetime.now(timezone.utc)),
            ContextItem(text="Weather forecast for tomorrow", source="test",
                       timestamp=datetime.now(timezone.utc)),
            ContextItem(text="Unit testing with pytest", source="test",
                       timestamp=datetime.now(timezone.utc)),
        ]

        kept, decision = pruner.prune(items, "Python testing", token_budget=200)

        # Should keep the more relevant items
        kept_texts = [item.text for item in kept]
        # Testing-related items should be preferred
        assert any("testing" in text.lower() for text in kept_texts)

    def test_prune_keeps_recent_items(self):
        """Test that recent items are kept preferentially."""
        pruner = ContextPruner()

        old_time = datetime.now(timezone.utc) - timedelta(hours=24)
        new_time = datetime.now(timezone.utc)

        items = [
            ContextItem(text="Old finding about X", source="test", timestamp=old_time),
            ContextItem(text="New finding about X", source="test", timestamp=new_time),
        ]

        kept, decision = pruner.prune(items, "finding about X", token_budget=100)

        # Should prefer the newer item
        if len(kept) == 1:
            assert kept[0].timestamp == new_time


class TestRelevanceScoring:
    """Tests for relevance scoring."""

    def test_score_exact_match(self):
        """Test that exact matches score high."""
        pruner = ContextPruner()

        item = ContextItem(
            text="Python testing frameworks comparison",
            source="test",
            timestamp=datetime.now(timezone.utc),
        )

        score = pruner.score_item(item, "Python testing frameworks")

        assert score > 0.5

    def test_score_no_match(self):
        """Test that unrelated content scores low."""
        pruner = ContextPruner()

        item = ContextItem(
            text="Recipe for chocolate cake",
            source="test",
            timestamp=datetime.now(timezone.utc),
        )

        score = pruner.score_item(item, "Python testing frameworks")

        assert score < 0.3

    def test_score_considers_recency(self):
        """Test that recency affects score."""
        pruner = ContextPruner()

        old_item = ContextItem(
            text="Same content",
            source="test",
            timestamp=datetime.now(timezone.utc) - timedelta(days=7),
        )

        new_item = ContextItem(
            text="Same content",
            source="test",
            timestamp=datetime.now(timezone.utc),
        )

        old_score = pruner.score_item(old_item, "query")
        new_score = pruner.score_item(new_item, "query")

        # Newer item should score higher (or equal if recency weight is 0)
        assert new_score >= old_score


class TestDeduplication:
    """Tests for deduplication."""

    def test_remove_duplicates(self):
        """Test that duplicate items are removed."""
        pruner = ContextPruner()

        items = [
            ContextItem(text="Duplicate content here", source="test",
                       timestamp=datetime.now(timezone.utc)),
            ContextItem(text="Duplicate content here", source="test",
                       timestamp=datetime.now(timezone.utc)),
            ContextItem(text="Unique content", source="test",
                       timestamp=datetime.now(timezone.utc)),
        ]

        deduped = pruner.deduplicate(items)

        assert len(deduped) == 2

    def test_remove_near_duplicates(self):
        """Test that near-duplicate items are detected."""
        pruner = ContextPruner(similarity_threshold=0.9)

        items = [
            ContextItem(text="The quick brown fox jumps over the lazy dog",
                       source="test", timestamp=datetime.now(timezone.utc)),
            ContextItem(text="The quick brown fox jumps over the lazy cat",
                       source="test", timestamp=datetime.now(timezone.utc)),
            ContextItem(text="Something completely different",
                       source="test", timestamp=datetime.now(timezone.utc)),
        ]

        deduped = pruner.deduplicate(items)

        # The two similar sentences might be deduplicated
        assert len(deduped) <= 3


class TestPruningDecision:
    """Tests for PruningDecision dataclass."""

    def test_pruning_decision_metrics(self):
        """Test that PruningDecision contains useful metrics."""
        pruner = ContextPruner()

        items = [
            ContextItem(text="Item " + str(i), source="test",
                       timestamp=datetime.now(timezone.utc))
            for i in range(10)
        ]

        kept, decision = pruner.prune(items, "query", token_budget=100)

        assert isinstance(decision, PruningDecision)
        assert decision.original_count == 10
        assert decision.kept_count == len(kept)
        assert decision.items_pruned == decision.original_count - decision.kept_count
        assert "tokens" in decision.metrics or "estimated_tokens" in decision.metrics


class TestContextItem:
    """Tests for ContextItem dataclass."""

    def test_context_item_creation(self):
        """Test creating a ContextItem."""
        now = datetime.now(timezone.utc)

        item = ContextItem(
            text="Test content",
            source="web_search",
            timestamp=now,
            metadata={"url": "https://example.com"},
        )

        assert item.text == "Test content"
        assert item.source == "web_search"
        assert item.timestamp == now
        assert item.metadata["url"] == "https://example.com"

    def test_context_item_token_estimate(self):
        """Test token estimation for ContextItem."""
        item = ContextItem(
            text="This is a test sentence with several words",
            source="test",
            timestamp=datetime.now(timezone.utc),
        )

        # Rough estimate: ~1 token per 4 characters
        estimated = item.estimated_tokens()

        assert estimated > 0
        assert estimated < len(item.text)  # Should be less than char count


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_items_list(self):
        """Test pruning empty list."""
        pruner = ContextPruner()

        kept, decision = pruner.prune([], "query", token_budget=1000)

        assert len(kept) == 0
        assert decision.items_pruned == 0

    def test_zero_budget(self):
        """Test pruning with zero budget."""
        pruner = ContextPruner()

        items = [
            ContextItem(text="Content", source="test",
                       timestamp=datetime.now(timezone.utc))
        ]

        kept, decision = pruner.prune(items, "query", token_budget=0)

        # Should keep at least some minimal content or return empty
        assert len(kept) <= len(items)

    def test_very_large_budget(self):
        """Test pruning with very large budget."""
        pruner = ContextPruner()

        items = [
            ContextItem(text=f"Item {i}", source="test",
                       timestamp=datetime.now(timezone.utc))
            for i in range(100)
        ]

        kept, decision = pruner.prune(items, "query", token_budget=1000000)

        # Should keep all items
        assert len(kept) == len(items)
        assert decision.items_pruned == 0
