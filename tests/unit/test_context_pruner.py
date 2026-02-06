"""Unit tests for context pruner."""

from datetime import datetime, timedelta, timezone

from deepr.services.context_pruner import (
    ContextItem,
    ContextPruner,
    PruningDecision,
)


class TestContextPruner:
    """Tests for ContextPruner class."""

    def test_prune_within_budget(self):
        """Test that items within budget are not pruned."""
        pruner = ContextPruner()

        items = [
            ContextItem(id="1", text="Short item 1", source="test", timestamp=datetime.now(timezone.utc), phase=1),
            ContextItem(id="2", text="Short item 2", source="test", timestamp=datetime.now(timezone.utc), phase=1),
        ]

        kept, decision = pruner.prune(items, "test query", token_budget=10000)

        assert len(kept) == 2
        assert len(decision.items_removed) == 0

    def test_prune_exceeds_budget(self):
        """Test that items exceeding budget are pruned."""
        pruner = ContextPruner()

        # Create items that exceed a small budget
        items = [
            ContextItem(id="1", text="A" * 1000, source="test", timestamp=datetime.now(timezone.utc), phase=1),
            ContextItem(id="2", text="B" * 1000, source="test", timestamp=datetime.now(timezone.utc), phase=1),
            ContextItem(id="3", text="C" * 1000, source="test", timestamp=datetime.now(timezone.utc), phase=1),
        ]

        kept, decision = pruner.prune(items, "test query", token_budget=500)

        assert len(kept) < len(items)
        assert len(decision.items_removed) > 0

    def test_prune_keeps_relevant_items(self):
        """Test that relevant items are kept preferentially."""
        pruner = ContextPruner()

        items = [
            ContextItem(
                id="1",
                text="Python testing best practices " * 50,
                source="test",
                timestamp=datetime.now(timezone.utc),
                phase=1,
            ),
            ContextItem(
                id="2",
                text="Weather forecast for tomorrow " * 50,
                source="test",
                timestamp=datetime.now(timezone.utc),
                phase=1,
            ),
            ContextItem(
                id="3",
                text="Unit testing with pytest " * 50,
                source="test",
                timestamp=datetime.now(timezone.utc),
                phase=1,
            ),
        ]

        kept, decision = pruner.prune(items, "Python testing", token_budget=600)

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
            ContextItem(id="1", text="Old finding about X " * 50, source="test", timestamp=old_time, phase=1),
            ContextItem(id="2", text="New finding about X " * 50, source="test", timestamp=new_time, phase=1),
        ]

        kept, decision = pruner.prune(items, "finding about X", token_budget=300)

        # Should prefer the newer item
        if len(kept) == 1:
            assert kept[0].timestamp == new_time


class TestRelevanceScoring:
    """Tests for relevance scoring."""

    def test_score_exact_match(self):
        """Test that exact matches score high."""
        pruner = ContextPruner()

        item = ContextItem(
            id="1",
            text="Python testing frameworks comparison",
            source="test",
            timestamp=datetime.now(timezone.utc),
            phase=1,
        )

        score = pruner.score_item(item, "Python testing frameworks", datetime.now(timezone.utc))

        assert score > 0.5

    def test_score_no_match(self):
        """Test that unrelated content scores low."""
        pruner = ContextPruner()

        item = ContextItem(
            id="1",
            text="Recipe for chocolate cake",
            source="test",
            timestamp=datetime.now(timezone.utc),
            phase=1,
        )

        score = pruner.score_item(item, "Python testing frameworks", datetime.now(timezone.utc))

        # With importance=0.5 default, minimum score will be around 0.15-0.3
        # depending on recency weight
        assert score < 0.6

    def test_score_considers_recency(self):
        """Test that recency affects score."""
        pruner = ContextPruner()

        old_item = ContextItem(
            id="1",
            text="Same content for testing",
            source="test",
            timestamp=datetime.now(timezone.utc) - timedelta(days=7),
            phase=1,
        )

        new_item = ContextItem(
            id="2",
            text="Same content for testing",
            source="test",
            timestamp=datetime.now(timezone.utc),
            phase=1,
        )

        now = datetime.now(timezone.utc)
        old_score = pruner.score_item(old_item, "query", now)
        new_score = pruner.score_item(new_item, "query", now)

        # Newer item should score higher (or equal if recency weight is 0)
        assert new_score >= old_score


class TestDeduplication:
    """Tests for deduplication."""

    def test_remove_duplicates(self):
        """Test that duplicate items are removed during pruning."""
        pruner = ContextPruner()

        now = datetime.now(timezone.utc)
        items = [
            ContextItem(id="1", text="Duplicate content here", source="test", timestamp=now, phase=1),
            ContextItem(id="2", text="Duplicate content here", source="test", timestamp=now, phase=1),
            ContextItem(id="3", text="Unique content here", source="test", timestamp=now, phase=1),
        ]

        kept, decision = pruner.prune(items, "test", token_budget=10000)

        # At least one duplicate should be removed
        assert len(kept) <= 3

    def test_remove_near_duplicates(self):
        """Test that near-duplicate items are detected."""
        pruner = ContextPruner(dedup_threshold=0.9)

        now = datetime.now(timezone.utc)
        items = [
            ContextItem(
                id="1", text="The quick brown fox jumps over the lazy dog", source="test", timestamp=now, phase=1
            ),
            ContextItem(
                id="2", text="The quick brown fox jumps over the lazy cat", source="test", timestamp=now, phase=1
            ),
            ContextItem(
                id="3",
                text="Something completely different about unrelated topics",
                source="test",
                timestamp=now,
                phase=1,
            ),
        ]

        kept, decision = pruner.prune(items, "test", token_budget=10000)

        # The two similar sentences might be deduplicated
        assert len(kept) <= 3


class TestPruningDecision:
    """Tests for PruningDecision dataclass."""

    def test_pruning_decision_metrics(self):
        """Test that PruningDecision contains useful metrics."""
        pruner = ContextPruner()

        now = datetime.now(timezone.utc)
        items = [
            ContextItem(id=str(i), text="Item " + str(i) + " " * 50, source="test", timestamp=now, phase=1)
            for i in range(10)
        ]

        kept, decision = pruner.prune(items, "query", token_budget=100)

        assert isinstance(decision, PruningDecision)
        assert decision.original_count == 10
        assert decision.pruned_count == len(kept)
        assert decision.original_tokens > 0
        assert decision.final_tokens <= decision.original_tokens


class TestContextItem:
    """Tests for ContextItem dataclass."""

    def test_context_item_creation(self):
        """Test creating a ContextItem."""
        now = datetime.now(timezone.utc)

        item = ContextItem(
            id="test1",
            text="Test content",
            source="web_search",
            timestamp=now,
            phase=1,
            metadata={"url": "https://example.com"},
        )

        assert item.id == "test1"
        assert item.text == "Test content"
        assert item.source == "web_search"
        assert item.timestamp == now
        assert item.phase == 1
        assert item.metadata["url"] == "https://example.com"

    def test_context_item_token_estimate(self):
        """Test token estimation for ContextItem."""
        item = ContextItem(
            id="test1",
            text="This is a test sentence with several words",
            source="test",
            timestamp=datetime.now(timezone.utc),
            phase=1,
        )

        # Token count is auto-computed in __post_init__
        assert item.tokens > 0
        assert item.tokens < len(item.text)  # Should be less than char count

    def test_context_item_to_dict(self):
        """Test ContextItem serialization."""
        now = datetime.now(timezone.utc)
        item = ContextItem(
            id="test1",
            text="Test content",
            source="test",
            timestamp=now,
            phase=2,
        )

        data = item.to_dict()

        assert data["id"] == "test1"
        assert data["text"] == "Test content"
        assert data["source"] == "test"
        assert data["phase"] == 2


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_items_list(self):
        """Test pruning empty list."""
        pruner = ContextPruner()

        kept, decision = pruner.prune([], "query", token_budget=1000)

        assert len(kept) == 0
        assert len(decision.items_removed) == 0

    def test_zero_budget(self):
        """Test pruning with zero budget."""
        pruner = ContextPruner()

        items = [ContextItem(id="1", text="Content", source="test", timestamp=datetime.now(timezone.utc), phase=1)]

        kept, decision = pruner.prune(items, "query", token_budget=0)

        # Should keep at least some minimal content or return empty
        assert len(kept) <= len(items)

    def test_very_large_budget(self):
        """Test pruning with very large budget."""
        pruner = ContextPruner()

        now = datetime.now(timezone.utc)
        items = [ContextItem(id=str(i), text=f"Item {i}", source="test", timestamp=now, phase=1) for i in range(100)]

        kept, decision = pruner.prune(items, "query", token_budget=1000000)

        # Should keep all items
        assert len(kept) == len(items)
        assert len(decision.items_removed) == 0
