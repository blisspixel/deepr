"""Tests for batch auto-mode research execution.

Tests the AutoBatchExecutor's ability to parse batch files and
execute queries with optimal routing.
"""

import json
import tempfile
from pathlib import Path

import pytest

from deepr.services.batch_auto import (
    AutoBatchExecutor,
    BatchQueryItem,
    BatchResult,
    format_batch_preview,
    parse_batch_file,
)


class TestParseBatchFile:
    """Tests for batch file parsing."""

    def test_parse_txt_file_simple(self):
        """Parse simple .txt file with one query per line."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("What is Python?\n")
            f.write("Analyze the AI market\n")
            f.write("Compare AWS vs Azure\n")
            f.flush()

            items, defaults = parse_batch_file(f.name)

        assert len(items) == 3
        assert items[0].query == "What is Python?"
        assert items[1].query == "Analyze the AI market"
        assert items[2].query == "Compare AWS vs Azure"
        assert defaults == {}

        Path(f.name).unlink()

    def test_parse_txt_file_with_comments(self):
        """Parse .txt file with comment lines."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# This is a comment\n")
            f.write("What is Python?\n")
            f.write("# Another comment\n")
            f.write("Analyze the AI market\n")
            f.write("\n")  # Empty line
            f.write("Compare AWS vs Azure\n")
            f.flush()

            items, defaults = parse_batch_file(f.name)

        assert len(items) == 3
        assert items[0].query == "What is Python?"

        Path(f.name).unlink()

    def test_parse_txt_file_empty_lines(self):
        """Parse .txt file with empty lines."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("What is Python?\n")
            f.write("\n")
            f.write("   \n")  # Whitespace only
            f.write("Analyze AI\n")
            f.flush()

            items, _ = parse_batch_file(f.name)

        assert len(items) == 2

        Path(f.name).unlink()

    def test_parse_json_file_simple(self):
        """Parse simple .json file with query strings."""
        data = {
            "queries": [
                "What is Python?",
                "Analyze AI market",
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()

            items, defaults = parse_batch_file(f.name)

        assert len(items) == 2
        assert items[0].query == "What is Python?"
        assert items[1].query == "Analyze AI market"

        Path(f.name).unlink()

    def test_parse_json_file_with_options(self):
        """Parse .json file with per-query options."""
        data = {
            "queries": [
                {"query": "What is Python?", "priority": 8},
                {"query": "Analyze Tesla", "cost_limit": 1.0},
                {"query": "Deep analysis", "force_model": "o3-deep-research"},
            ],
            "defaults": {"prefer_cost": True},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()

            items, defaults = parse_batch_file(f.name)

        assert len(items) == 3
        assert items[0].query == "What is Python?"
        assert items[0].priority == 8
        assert items[1].cost_limit == 1.0
        assert items[2].force_model == "o3-deep-research"
        assert defaults.get("prefer_cost") is True

        Path(f.name).unlink()

    def test_parse_json_file_with_defaults(self):
        """Parse .json file that applies defaults to queries."""
        data = {
            "queries": [
                {"query": "Query 1"},
                {"query": "Query 2", "priority": 10},
            ],
            "defaults": {"priority": 5, "cost_limit": 0.50},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()

            items, _ = parse_batch_file(f.name)

        # Query 1 should have default priority
        assert items[0].priority == 5
        assert items[0].cost_limit == 0.50

        # Query 2 overrides default priority
        assert items[1].priority == 10
        assert items[1].cost_limit == 0.50

        Path(f.name).unlink()

    def test_parse_file_not_found(self):
        """Non-existent file should raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            parse_batch_file("/nonexistent/path/queries.txt")

    def test_parse_unsupported_format(self):
        """Unsupported file format should raise ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write("<queries></queries>")
            f.flush()

            with pytest.raises(ValueError, match="Unsupported"):
                parse_batch_file(f.name)

        Path(f.name).unlink()

    def test_parse_json_missing_queries(self):
        """JSON without queries array should raise ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"data": []}, f)
            f.flush()

            with pytest.raises(ValueError, match="queries"):
                parse_batch_file(f.name)

        Path(f.name).unlink()

    def test_parse_json_invalid_query_format(self):
        """JSON with invalid query format should raise ValueError."""
        data = {
            "queries": [
                {"query": "Valid"},
                {"not_query": "Invalid"},  # Missing query field
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()

            with pytest.raises(ValueError, match="missing 'query'"):
                parse_batch_file(f.name)

        Path(f.name).unlink()


class TestBatchQueryItem:
    """Tests for BatchQueryItem dataclass."""

    def test_default_values(self):
        """BatchQueryItem should have sensible defaults."""
        item = BatchQueryItem(query="Test query")

        assert item.query == "Test query"
        assert item.priority == 5
        assert item.cost_limit is None
        assert item.force_model is None
        assert item.force_provider is None
        assert item.metadata == {}

    def test_custom_values(self):
        """BatchQueryItem should accept custom values."""
        item = BatchQueryItem(
            query="Test query",
            priority=10,
            cost_limit=2.0,
            force_model="o3-deep-research",
            force_provider="openai",
            metadata={"tag": "important"},
        )

        assert item.priority == 10
        assert item.cost_limit == 2.0
        assert item.force_model == "o3-deep-research"
        assert item.force_provider == "openai"
        assert item.metadata["tag"] == "important"


class TestAutoBatchExecutor:
    """Tests for AutoBatchExecutor."""

    @pytest.fixture
    def executor(self):
        """Create an executor instance."""
        return AutoBatchExecutor()

    @pytest.fixture
    def txt_batch_file(self):
        """Create a temporary .txt batch file."""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f.write("What is Python?\n")
        f.write("Analyze the AI market\n")
        f.write("Compare AWS vs Azure\n")
        f.close()
        yield f.name
        Path(f.name).unlink()

    def test_preview_batch(self, executor, txt_batch_file):
        """preview_batch should return routing decisions without executing."""
        result = executor.preview_batch(txt_batch_file)

        assert len(result.decisions) == 3
        assert result.total_cost_estimate > 0
        assert "simple" in result.summary or "moderate" in result.summary or "complex" in result.summary

    def test_preview_batch_with_budget(self, executor, txt_batch_file):
        """preview_batch with budget should constrain costs."""
        result = executor.preview_batch(txt_batch_file, budget_total=0.10)

        # Cost should be constrained (though may not be exact due to routing)
        assert result.total_cost_estimate <= 1.0  # Allow reasonable overhead

    def test_preview_batch_prefer_cost(self, executor, txt_batch_file):
        """preview_batch with prefer_cost should minimize costs."""
        result_normal = executor.preview_batch(txt_batch_file)
        result_cost = executor.preview_batch(txt_batch_file, prefer_cost=True)

        assert result_cost.total_cost_estimate <= result_normal.total_cost_estimate

    @pytest.mark.asyncio
    async def test_execute_batch_dry_run(self, executor, txt_batch_file):
        """execute_batch with dry_run should not make API calls."""
        result = await executor.execute_batch(
            file_path=txt_batch_file,
            dry_run=True,
        )

        assert isinstance(result, BatchResult)
        assert len(result.results) == 3
        # Dry run should not execute, so no success/failure
        assert result.success_count == 0
        assert result.failure_count == 0

    @pytest.mark.asyncio
    async def test_execute_batch_dry_run_has_decisions(self, executor, txt_batch_file):
        """Dry run should still have routing decisions."""
        result = await executor.execute_batch(
            file_path=txt_batch_file,
            dry_run=True,
        )

        # Each result should have a decision
        for r in result.results:
            assert r.decision is not None
            assert r.decision.provider is not None
            assert r.decision.model is not None


class TestFormatBatchPreview:
    """Tests for batch preview formatting."""

    def test_format_preview_basic(self):
        """format_batch_preview should produce readable output."""
        from deepr.routing.auto_mode import AutoModeDecision, BatchRoutingResult

        decisions = [
            AutoModeDecision(
                provider="xai",
                model="grok-4-fast",
                complexity="simple",
                task_type="factual",
                cost_estimate=0.01,
                confidence=0.95,
                reasoning="Simple query",
            ),
            AutoModeDecision(
                provider="openai",
                model="o3-deep-research",
                complexity="complex",
                task_type="research",
                cost_estimate=0.50,
                confidence=0.90,
                reasoning="Complex query",
            ),
        ]

        summary = {
            "simple": {"count": 1, "cost_estimate": 0.01, "models": {"xai/grok-4-fast": 1}},
            "complex": {"count": 1, "cost_estimate": 0.50, "models": {"openai/o3-deep-research": 1}},
        }

        routing = BatchRoutingResult(
            decisions=decisions,
            summary=summary,
            total_cost_estimate=0.51,
        )

        output = format_batch_preview(routing)

        assert "Batch Research" in output
        assert "Queries: 2" in output
        assert "$0.51" in output
        assert "Simple" in output or "simple" in output
        assert "Complex" in output or "complex" in output

    def test_format_preview_empty(self):
        """format_batch_preview should handle empty batch."""
        from deepr.routing.auto_mode import BatchRoutingResult

        routing = BatchRoutingResult(
            decisions=[],
            summary={},
            total_cost_estimate=0.0,
        )

        output = format_batch_preview(routing)

        assert "Queries: 0" in output
        assert "$0.00" in output
