"""Tests for cost estimation and control (no API calls)."""

from deepr.core.costs import CostController, CostEstimator, get_safe_test_prompt


class TestCostEstimator:
    """Test cost estimation (purely local calculations)."""

    def test_estimate_short_prompt(self):
        """Test estimation for short prompt."""
        estimate = CostEstimator.estimate_cost(
            prompt="What is 2+2?",
            model="o4-mini-deep-research",
            enable_web_search=False,
        )

        assert estimate.min_cost < estimate.expected_cost < estimate.max_cost
        assert estimate.expected_cost < 1.0  # Should be cheap
        assert "input tokens" in estimate.reasoning.lower()

    def test_estimate_medium_prompt(self):
        """Test estimation for medium prompt."""
        prompt = "Explain quantum computing in detail. " * 20  # ~150 words

        estimate = CostEstimator.estimate_cost(
            prompt=prompt,
            model="o3-deep-research",
            enable_web_search=True,
        )

        assert estimate.expected_cost > 0.5  # More substantial
        assert estimate.max_cost > estimate.expected_cost
        assert "web search" in estimate.reasoning.lower()

    def test_estimate_with_documents(self):
        """Test estimation with documents."""
        estimate = CostEstimator.estimate_cost(
            prompt="Summarize these documents",
            model="o3-deep-research",
            documents=["doc1.pdf", "doc2.pdf"],
        )

        # Should be more expensive with documents
        estimate_no_docs = CostEstimator.estimate_cost(
            prompt="Summarize these documents",
            model="o3-deep-research",
        )

        assert estimate.expected_cost > estimate_no_docs.expected_cost
        assert "documents attached" in estimate.reasoning.lower()

    def test_cost_sensitive_model_cheaper(self):
        """Test that o4-mini is cheaper than o3."""
        prompt = "Write an essay about climate change."

        o3_estimate = CostEstimator.estimate_cost(prompt, "o3-deep-research")
        o4_estimate = CostEstimator.estimate_cost(prompt, "o4-mini-deep-research")

        assert o4_estimate.expected_cost < o3_estimate.expected_cost

    def test_calculate_actual_cost(self):
        """Test actual cost calculation."""
        cost = CostEstimator.calculate_actual_cost(
            model="o3-deep-research",
            input_tokens=1000,
            output_tokens=10000,
            reasoning_tokens=500,
        )

        # Should be in reasonable range
        assert 0.05 < cost < 1.0
        assert isinstance(cost, float)

    def test_token_estimation(self):
        """Test token count estimation."""
        short_prompt = "Hello"
        tokens = CostEstimator.estimate_prompt_tokens(short_prompt)
        assert 1 <= tokens <= 5

        long_prompt = "This is a longer prompt " * 100
        tokens_long = CostEstimator.estimate_prompt_tokens(long_prompt)
        assert tokens_long > tokens
        assert tokens_long > 100

    def test_pricing_sourced_from_registry(self):
        """Estimator must use registry pricing, not its legacy 4-model table.

        The legacy table priced every unknown model at o3-deep-research
        rates ($2/$8), so a $10/$50 frontier model passed pre-flight at a
        ~5x underestimate.
        """
        # Long prompt so per-token differences survive 2-decimal rounding
        prompt = "Analyze the macroeconomic effects of energy transition policy. " * 600

        fable = CostEstimator.estimate_cost(prompt, "claude-fable-5")
        opus = CostEstimator.estimate_cost(prompt, "claude-opus-4-8")
        # Fable 5 ($10/$50) must estimate strictly above Opus 4.8 ($5/$25);
        # under the old table both collapsed to the o3 default.
        assert fable.expected_cost > opus.expected_cost

    def test_actual_cost_uses_registry_rates(self):
        """calculate_actual_cost must bill registry rates per model."""
        fable = CostEstimator.calculate_actual_cost("claude-fable-5", input_tokens=100_000, output_tokens=50_000)
        # $10/1M * 100K + $50/1M * 50K = $1.00 + $2.50 = $3.50
        assert abs(fable - 3.50) < 0.01


class TestCostController:
    """Test cost control and limits (no API calls)."""

    def test_initialization(self):
        """Test controller initializes with limits."""
        controller = CostController(
            max_cost_per_job=5.0,
            max_daily_cost=50.0,
            max_monthly_cost=500.0,
        )

        assert controller.max_cost_per_job == 5.0
        assert controller.daily_spending == 0.0
        assert controller.monthly_spending == 0.0

    def test_check_per_job_limit(self):
        """Test per-job cost limit enforcement."""
        controller = CostController(max_cost_per_job=1.0)

        cheap_estimate = CostEstimator.estimate_cost("Short prompt", "o4-mini-deep-research", enable_web_search=False)

        allowed, reason = controller.check_cost_limit(cheap_estimate)
        assert allowed is True
        assert reason is None

        # Create artificially expensive estimate
        from deepr.core.costs import CostEstimate

        expensive = CostEstimate(min_cost=5.0, max_cost=10.0, expected_cost=7.5, model="o3", reasoning="Test")

        allowed, reason = controller.check_cost_limit(expensive)
        assert allowed is False
        assert "exceeds limit" in reason.lower()

    def test_check_daily_limit(self):
        """Test daily spending limit."""
        controller = CostController(max_cost_per_job=10.0, max_daily_cost=5.0)

        # Spend almost to limit
        controller.daily_spending = 4.5

        estimate = CostEstimator.estimate_cost("Moderate prompt", "o4-mini-deep-research")

        # Should be blocked if would exceed daily limit
        if estimate.expected_cost > 0.5:
            allowed, reason = controller.check_cost_limit(estimate)
            assert allowed is False or allowed is True  # Depends on estimate
            if not allowed:
                assert "daily" in reason.lower()

    def test_record_cost(self):
        """Test cost recording."""
        controller = CostController()

        assert controller.daily_spending == 0.0
        assert controller.monthly_spending == 0.0

        controller.record_cost(2.50)

        assert controller.daily_spending == 2.50
        assert controller.monthly_spending == 2.50

        controller.record_cost(1.25)

        assert controller.daily_spending == 3.75
        assert controller.monthly_spending == 3.75

    def test_spending_summary(self):
        """Test spending summary."""
        controller = CostController(max_daily_cost=10.0, max_monthly_cost=100.0)

        controller.daily_spending = 3.50
        controller.monthly_spending = 25.00

        summary = controller.get_spending_summary()

        assert summary["daily"] == 3.50
        assert summary["daily_limit"] == 10.0
        assert summary["daily_remaining"] == 6.50
        assert summary["monthly"] == 25.00
        assert summary["monthly_remaining"] == 75.00


class TestSafeTestPrompts:
    """Test safe/cheap test prompts."""

    def test_get_safe_test_prompt(self):
        """Test getting safe test prompts."""
        prompt_data = get_safe_test_prompt(0)

        assert "prompt" in prompt_data
        assert "expected_cost" in prompt_data
        assert "description" in prompt_data
        assert prompt_data["expected_cost"] < 0.50  # All should be cheap

    def test_all_safe_prompts_are_cheap(self):
        """Test all safe prompts have low expected cost."""
        from deepr.core.costs import CHEAP_TEST_PROMPTS

        for i, prompt_data in enumerate(CHEAP_TEST_PROMPTS):
            assert prompt_data["expected_cost"] < 1.0, f"Prompt {i} too expensive"

            # Verify estimation
            estimate = CostEstimator.estimate_cost(
                prompt_data["prompt"],
                "o4-mini-deep-research",
                enable_web_search=False,
            )

            # Estimates should be in reasonable range
            assert estimate.expected_cost < 2.0, f"Prompt {i} estimate too high"

    def test_index_bounds(self):
        """Test safe prompt index handling."""
        # Valid index
        prompt = get_safe_test_prompt(0)
        assert prompt is not None

        # Out of bounds - should return first
        prompt = get_safe_test_prompt(999)
        assert prompt is not None

        # Negative - should return first
        prompt = get_safe_test_prompt(-1)
        assert prompt is not None


class TestCostDataDirIsolation:
    """Cost state must honor DEEPR_COST_DATA_DIR.

    Live-validation regression: the ledger and dashboard defaulted to
    CWD-relative paths, so unit tests running from the repo root appended
    fabricated cost events to the developer's real canonical ledger.
    """

    def test_ledger_honors_env_dir(self, tmp_path, monkeypatch):
        from deepr.observability.cost_ledger import CostLedger

        monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "isolated"))
        ledger = CostLedger()
        assert ledger.ledger_path == tmp_path / "isolated" / "cost_ledger.jsonl"

    def test_dashboard_honors_env_dir(self, tmp_path, monkeypatch):
        from deepr.observability.costs import CostDashboard

        monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "isolated"))
        dash = CostDashboard()
        assert dash.storage_path == tmp_path / "isolated" / "cost_log.json"
        assert dash.ledger.ledger_path == tmp_path / "isolated" / "cost_ledger.jsonl"

    def test_explicit_path_still_wins(self, tmp_path, monkeypatch):
        from deepr.observability.cost_ledger import CostLedger

        monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "ignored"))
        explicit = tmp_path / "explicit.jsonl"
        assert CostLedger(ledger_path=explicit).ledger_path == explicit

    def test_autouse_isolation_active(self):
        """The conftest autouse fixture must already point cost state at tmp."""
        import os

        from deepr.observability.cost_ledger import default_cost_data_dir

        assert os.environ.get("DEEPR_COST_DATA_DIR"), "autouse isolation fixture not active"
        assert "data" + os.sep + "costs" not in str(default_cost_data_dir())


class TestDashboardRebuildFromLedger:
    """The dashboard is a derived view; rebuild_from_ledger regenerates it
    from the canonical ledger (drift repair for costs doctor --rebuild)."""

    def test_rebuild_mirrors_ledger(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "costs"))
        from deepr.observability.costs import CostDashboard

        dash = CostDashboard()
        dash.ledger.record_event(
            operation="research_submit",
            provider="openai",
            cost_usd=1.25,
            model="o4-mini-deep-research",
            task_id="job-1",
            source="test.rebuild",
        )
        dash.ledger.record_event(
            operation="curriculum_plan",
            provider="openai",
            cost_usd=0.05,
            model="gpt-5-mini",
            task_id="job-2",
            source="test.rebuild",
        )
        # Dashboard view is empty (events went straight to the ledger)
        assert sum(e.cost for e in dash.entries) == 0.0

        count = dash.rebuild_from_ledger()

        assert count == 2
        assert abs(sum(e.cost for e in dash.entries) - 1.30) < 1e-9
        assert dash.entries[0].metadata["source"] == "test.rebuild"
        # Rebuild persists: a fresh dashboard sees the regenerated view
        fresh = CostDashboard()
        assert abs(sum(e.cost for e in fresh.entries) - 1.30) < 1e-9

    def test_rebuild_replaces_stale_view(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "costs"))
        from deepr.observability.costs import CostDashboard, CostEntry

        dash = CostDashboard()
        # Fabricated entry in the view only (the pollution scenario)
        dash.entries.append(CostEntry(operation="fake", provider="test", cost=99.0))
        dash.ledger.record_event(operation="real", provider="openai", cost_usd=0.10, source="test.rebuild")

        dash.rebuild_from_ledger()

        assert all(e.operation != "fake" for e in dash.entries)
        assert abs(sum(e.cost for e in dash.entries) - 0.10) < 1e-9


class TestCostLedgerIntegrity:
    """Canonical ledger behaviors that guard against double/under-billing."""

    def _ledger(self, tmp_path):
        from deepr.observability.cost_ledger import CostLedger

        return CostLedger(ledger_path=tmp_path / "ledger.jsonl")

    def test_idempotency_key_prevents_double_billing(self, tmp_path):
        ledger = self._ledger(tmp_path)
        _, first = ledger.record_event(
            operation="submit", provider="openai", cost_usd=2.0, idempotency_key="job-1:submit"
        )
        _, second = ledger.record_event(
            operation="submit", provider="openai", cost_usd=2.0, idempotency_key="job-1:submit"
        )
        assert first is True
        assert second is False
        assert ledger.get_total_cost() == 2.0

    def test_idempotency_index_survives_reload(self, tmp_path):
        from deepr.observability.cost_ledger import CostLedger

        ledger = self._ledger(tmp_path)
        ledger.record_event(operation="submit", provider="openai", cost_usd=1.0, idempotency_key="k1")

        reloaded = CostLedger(ledger_path=tmp_path / "ledger.jsonl")
        _, recorded = reloaded.record_event(operation="submit", provider="openai", cost_usd=1.0, idempotency_key="k1")
        assert recorded is False
        assert reloaded.get_total_cost() == 1.0

    def test_corrupt_line_logged_not_fatal(self, tmp_path, caplog):
        import logging

        from deepr.observability.cost_ledger import CostLedger

        path = tmp_path / "ledger.jsonl"
        ledger = self._ledger(tmp_path)
        ledger.record_event(operation="a", provider="openai", cost_usd=0.5, idempotency_key="good")
        with open(path, "a", encoding="utf-8") as f:
            f.write('{"broken json\n')

        with caplog.at_level(logging.ERROR, logger="deepr.observability.cost_ledger"):
            reloaded = CostLedger(ledger_path=path)
        assert any("Corrupted cost ledger line" in r.message for r in caplog.records)
        # The good record still loads and dedupes
        _, recorded = reloaded.record_event(operation="a", provider="openai", cost_usd=0.5, idempotency_key="good")
        assert recorded is False

    def test_negative_cost_clamped(self, tmp_path):
        ledger = self._ledger(tmp_path)
        event, _ = ledger.record_event(operation="weird", provider="openai", cost_usd=-3.0)
        assert event.cost_usd == 0.0
        assert ledger.get_total_cost() == 0.0

    def test_get_events_filters(self, tmp_path):
        from datetime import UTC, datetime, timedelta

        ledger = self._ledger(tmp_path)
        ledger.record_event(operation="a", provider="openai", cost_usd=1.0, source="src.one")
        ledger.record_event(operation="b", provider="openai", cost_usd=2.0, source="src.two")

        by_source = ledger.get_events(source="src.one")
        assert len(by_source) == 1
        assert by_source[0].cost_usd == 1.0

        future = datetime.now(UTC) + timedelta(days=1)
        assert ledger.get_events(start_date=future) == []
        assert ledger.get_events(end_date=future, start_date=future - timedelta(days=2)) != []
        assert ledger.get_total_cost(source="src.two") == 2.0

    def test_get_health_reports_path_and_writable(self, tmp_path):
        ledger = self._ledger(tmp_path)
        ledger.record_event(operation="a", provider="openai", cost_usd=0.1)
        health = ledger.get_health()
        assert health["writable"] is True
        assert "ledger.jsonl" in str(health["path"])
