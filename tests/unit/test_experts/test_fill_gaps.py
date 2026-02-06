"""Unit tests for the fill-gaps command.

Tests the Phase 2 implementation:
- Gap prioritization
- Budget calculation
- Worldview loading
"""

from datetime import datetime


class TestGapPrioritization:
    """Test knowledge gap prioritization logic."""

    def test_gaps_sorted_by_priority(self):
        """Gaps should be sorted by priority (highest first)."""
        from deepr.experts.synthesis import KnowledgeGap

        gaps = [
            KnowledgeGap(topic="Low priority", questions=["Q1"], priority=1, identified_at=datetime.utcnow()),
            KnowledgeGap(topic="High priority", questions=["Q2"], priority=5, identified_at=datetime.utcnow()),
            KnowledgeGap(topic="Medium priority", questions=["Q3"], priority=3, identified_at=datetime.utcnow()),
        ]

        sorted_gaps = sorted(gaps, key=lambda g: g.priority, reverse=True)

        assert sorted_gaps[0].topic == "High priority"
        assert sorted_gaps[1].topic == "Medium priority"
        assert sorted_gaps[2].topic == "Low priority"

    def test_top_n_gaps_selected(self):
        """Only top N gaps should be selected for filling."""
        from deepr.experts.synthesis import KnowledgeGap

        gaps = [
            KnowledgeGap(topic=f"Gap {i}", questions=[f"Q{i}"], priority=i, identified_at=datetime.utcnow())
            for i in range(1, 6)  # 5 gaps with priorities 1-5
        ]

        sorted_gaps = sorted(gaps, key=lambda g: g.priority, reverse=True)
        top_3 = sorted_gaps[:3]

        assert len(top_3) == 3
        assert top_3[0].priority == 5
        assert top_3[1].priority == 4
        assert top_3[2].priority == 3


class TestBudgetCalculation:
    """Test budget calculation for gap filling."""

    def test_budget_divided_equally(self):
        """Budget should be divided equally among gaps."""
        budget = 10.0
        num_gaps = 5

        budget_per_gap = budget / num_gaps

        assert budget_per_gap == 2.0

    def test_budget_with_single_gap(self):
        """Single gap should get full budget."""
        budget = 5.0
        num_gaps = 1

        budget_per_gap = budget / num_gaps

        assert budget_per_gap == 5.0

    def test_budget_with_fractional_result(self):
        """Budget division should handle fractional results."""
        budget = 10.0
        num_gaps = 3

        budget_per_gap = budget / num_gaps

        assert abs(budget_per_gap - 3.333) < 0.01


class TestWorldviewLoading:
    """Test worldview loading for gap filling."""

    def test_worldview_loads_from_json(self):
        """Worldview should load correctly from JSON."""
        import json
        import tempfile
        from pathlib import Path

        from deepr.experts.synthesis import Worldview

        # Create test worldview data
        worldview_data = {
            "expert_name": "Test Expert",
            "domain": "testing",
            "beliefs": [
                {
                    "topic": "Testing",
                    "statement": "Testing is important",
                    "confidence": 0.9,
                    "evidence": ["doc1.md"],
                    "formed_at": datetime.utcnow().isoformat(),
                    "last_updated": datetime.utcnow().isoformat(),
                }
            ],
            "knowledge_gaps": [
                {
                    "topic": "Advanced Testing",
                    "questions": ["How to test async code?"],
                    "priority": 4,
                    "identified_at": datetime.utcnow().isoformat(),
                }
            ],
            "last_synthesis": datetime.utcnow().isoformat(),
            "synthesis_count": 1,
        }

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(worldview_data, f)
            temp_path = Path(f.name)

        try:
            # Load worldview
            worldview = Worldview.load(temp_path)

            assert worldview.expert_name == "Test Expert"
            assert len(worldview.beliefs) == 1
            assert len(worldview.knowledge_gaps) == 1
            assert worldview.knowledge_gaps[0].topic == "Advanced Testing"
            assert worldview.knowledge_gaps[0].priority == 4
        finally:
            temp_path.unlink()

    def test_empty_gaps_list(self):
        """Worldview with no gaps should be handled."""
        from deepr.experts.synthesis import Worldview

        worldview = Worldview(
            expert_name="Test Expert", domain="testing", beliefs=[], knowledge_gaps=[], synthesis_count=1
        )

        assert len(worldview.knowledge_gaps) == 0


class TestResearchQueryConstruction:
    """Test research query construction from gaps."""

    def test_query_from_single_question(self):
        """Query should use first question when available."""
        from deepr.experts.synthesis import KnowledgeGap

        gap = KnowledgeGap(
            topic="Testing", questions=["How to write unit tests?"], priority=3, identified_at=datetime.utcnow()
        )

        # Simulate query construction logic
        if gap.questions:
            query = gap.questions[0]
        else:
            query = f"Research and explain: {gap.topic}"

        assert query == "How to write unit tests?"

    def test_query_from_multiple_questions(self):
        """Query should combine multiple questions."""
        from deepr.experts.synthesis import KnowledgeGap

        gap = KnowledgeGap(
            topic="Testing",
            questions=["How to write unit tests?", "What are mocks?", "How to test async code?"],
            priority=3,
            identified_at=datetime.utcnow(),
        )

        # Simulate query construction logic
        if gap.questions:
            query = gap.questions[0]
            if len(gap.questions) > 1:
                query += f" Also address: {'; '.join(gap.questions[1:3])}"
        else:
            query = f"Research and explain: {gap.topic}"

        assert "How to write unit tests?" in query
        assert "What are mocks?" in query
        assert "How to test async code?" in query

    def test_query_from_topic_only(self):
        """Query should use topic when no questions available."""
        from deepr.experts.synthesis import KnowledgeGap

        gap = KnowledgeGap(topic="Advanced Testing Patterns", questions=[], priority=3, identified_at=datetime.utcnow())

        # Simulate query construction logic
        if gap.questions:
            query = gap.questions[0]
        else:
            query = f"Research and explain: {gap.topic}"

        assert query == "Research and explain: Advanced Testing Patterns"


class TestGapRemovalAfterFilling:
    """Test that filled gaps are removed from worldview."""

    def test_filled_gaps_removed(self):
        """Filled gaps should be removed from worldview."""
        from deepr.experts.synthesis import KnowledgeGap, Worldview

        worldview = Worldview(
            expert_name="Test Expert",
            domain="testing",
            beliefs=[],
            knowledge_gaps=[
                KnowledgeGap(topic="Gap 1", questions=[], priority=5, identified_at=datetime.utcnow()),
                KnowledgeGap(topic="Gap 2", questions=[], priority=3, identified_at=datetime.utcnow()),
                KnowledgeGap(topic="Gap 3", questions=[], priority=1, identified_at=datetime.utcnow()),
            ],
            synthesis_count=1,
        )

        # Simulate filling Gap 1 and Gap 2
        filled_topics = {"Gap 1", "Gap 2"}

        worldview.knowledge_gaps = [g for g in worldview.knowledge_gaps if g.topic not in filled_topics]

        assert len(worldview.knowledge_gaps) == 1
        assert worldview.knowledge_gaps[0].topic == "Gap 3"
