"""Tests for cost dashboard CLI commands (ROADMAP 4.3)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


def utc_now():
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(UTC)


from deepr.cli.main import cli
from deepr.observability.costs import CostAggregator, CostDashboard, CostEntry


@pytest.fixture
def runner():
    return CliRunner()


def _make_entries(days=7, base_cost=1.0, anomaly_day=None):
    """Create test cost entries over several days."""
    entries = []
    now = utc_now()
    for i in range(days):
        cost = base_cost
        if anomaly_day is not None and i == anomaly_day:
            cost = base_cost * 5  # >2x average
        entries.append(
            CostEntry(
                operation="research",
                provider="openai",
                cost=cost,
                model="gpt-5.2",
                timestamp=now - timedelta(days=days - 1 - i),
            )
        )
    return entries


def _make_dashboard_mock(entries=None, days=7, base_cost=1.0, anomaly_day=None):
    """Create a mock CostDashboard with test data."""
    if entries is None:
        entries = _make_entries(days, base_cost, anomaly_day)
    dashboard = MagicMock(spec=CostDashboard)
    dashboard.daily_limit = 10.0
    dashboard.monthly_limit = 100.0
    dashboard.alert_thresholds = [0.5, 0.8, 0.95]
    dashboard.entries = entries
    dashboard.aggregator = CostAggregator(entries)

    # Wire up get_daily_history to use real aggregator logic
    def get_daily_history(num_days):
        history = []
        today = utc_now().date()
        for i in range(num_days):
            target_date = today - timedelta(days=i)
            total = sum(e.cost for e in entries if e.date == target_date)
            history.append(
                {
                    "date": target_date.isoformat(),
                    "total": total,
                    "limit": 10.0,
                    "utilization": total / 10.0,
                }
            )
        return list(reversed(history))

    dashboard.get_daily_history = get_daily_history
    return dashboard


class TestShow:
    def test_current_authority_uses_atomic_settled_totals_and_active_holds(self):
        from deepr.cli.commands.costs import _current_cost_authority

        store = MagicMock()
        store.exposure_snapshot.return_value = SimpleNamespace(
            daily_settled_cost=1.0,
            weekly_settled_cost=2.0,
            monthly_settled_cost=3.0,
            active_cost=0.5,
            unresolved_count=1,
            unresolved_cost=0.25,
        )

        with (
            patch(
                "deepr.core.cost_caps.resolve_spend_caps",
                return_value={"per_job": 2.0, "daily": 5.0, "weekly": 10.0, "monthly": 10.0},
            ),
            patch("deepr.experts.research_reservation_store.ResearchReservationStore", return_value=store),
        ):
            summary = _current_cost_authority(daily_display_limit=20.0, monthly_display_limit=7.0)

        assert summary["daily_limit"] == 5.0
        assert summary["monthly_limit"] == 7.0
        assert summary["daily_settled"] == pytest.approx(1.0)
        assert summary["weekly_settled"] == pytest.approx(2.0)
        assert summary["monthly_settled"] == pytest.approx(3.0)
        assert summary["unresolved_holds"] == 1
        assert summary["unresolved_exposure"] == pytest.approx(0.25)
        assert summary["daily_exposure"] == pytest.approx(1.5)
        assert summary["weekly_exposure"] == pytest.approx(2.5)
        assert summary["monthly_exposure"] == pytest.approx(3.5)
        expected_headroom = min(2.0, 3.5, 7.5, 3.5)
        assert summary["authorizable_headroom"] == pytest.approx(max(0.0, expected_headroom))

    def test_current_authority_uses_wallet_total_drawdown(self):
        from deepr.cli.commands.costs import _current_cost_authority
        from deepr.core.cost_caps import OperatorBudget

        store = MagicMock()
        store.exposure_snapshot.return_value = SimpleNamespace(
            daily_settled_cost=0.01,
            weekly_settled_cost=20.01,
            monthly_settled_cost=20.01,
            total_settled_cost=41.17,
            active_cost=0.25,
            unresolved_count=0,
            unresolved_cost=0.0,
        )
        operator = OperatorBudget(
            configured=True,
            monthly_limit=50.0,
            frozen=False,
            spend_wallet_id="wallet-test",
            spend_wallet_authorized_usd=50.0,
            spend_wallet_settled_baseline_usd=41.16,
            authorization_valid=True,
        )
        with (
            patch("deepr.core.cost_caps.read_operator_budget_for_status", return_value=operator),
            patch(
                "deepr.core.cost_caps.resolve_spend_caps",
                return_value={"per_job": 20.0, "daily": 50.0, "weekly": 50.0, "monthly": 50.0},
            ),
            patch(
                "deepr.core.cost_caps.resolve_spend_policy",
                return_value=SimpleNamespace(calendar_periods=frozenset()),
            ),
            patch("deepr.experts.research_reservation_store.ResearchReservationStore", return_value=store),
        ):
            summary = _current_cost_authority()

        assert summary["authority_mode"] == "spend_wallet"
        assert summary["daily_settled"] == pytest.approx(0.01)
        assert summary["monthly_exposure"] == pytest.approx(0.26)
        assert summary["authorizable_headroom"] == pytest.approx(20.0)

    def test_show_renders_one_total_wallet(self, runner):
        summary = {
            "per_job_limit": 20.0,
            "daily_limit": 50.0,
            "weekly_limit": 50.0,
            "monthly_limit": 50.0,
            "daily_settled": 0.01,
            "weekly_settled": 0.01,
            "monthly_settled": 0.01,
            "active_holds": 0.0,
            "unresolved_holds": 0,
            "unresolved_exposure": 0.0,
            "daily_exposure": 0.01,
            "weekly_exposure": 0.01,
            "monthly_exposure": 0.01,
            "authorizable_headroom": 20.0,
            "authority_mode": "spend_wallet",
            "provider_hard_boundary_verified": False,
            "spend_wallet_authorized": 50.0,
            "spend_wallet_spent": 0.01,
            "spend_wallet_available": 49.99,
        }
        with patch("deepr.cli.commands.costs._current_cost_authority", return_value=summary):
            result = runner.invoke(cli, ["costs", "show"])

        assert result.exit_code == 0
        assert "Deepr metered-spend wallet" in result.output
        assert "Authorized credits: $50.00" in result.output
        assert "Wallet drawdown: $0.01 / $50.00" in result.output
        assert "Wallet available: $49.99" in result.output
        assert "does not draw down" in result.output
        assert "Provider hard boundary: not verified; paid API blocked" in result.output
        assert "wallet cannot replace provider prepaid-no-overage" in result.output
        assert "Today's Spending" not in result.output

    def test_command_line_limits_cannot_raise_effective_authority(self, runner):
        summary = {
            "per_job_limit": 2.0,
            "daily_limit": 2.0,
            "weekly_limit": 10.0,
            "monthly_limit": 10.0,
            "daily_settled": 0.2,
            "weekly_settled": 1.0,
            "monthly_settled": 1.0,
            "active_holds": 0.5,
            "unresolved_holds": 0,
            "unresolved_exposure": 0.0,
            "daily_exposure": 0.7,
            "weekly_exposure": 1.5,
            "monthly_exposure": 1.5,
            "authorizable_headroom": 1.3,
        }
        with patch("deepr.cli.commands.costs._current_cost_authority", return_value=summary) as current:
            result = runner.invoke(
                cli,
                ["costs", "show", "--daily-limit", "2", "--monthly-limit", "20"],
            )

        assert result.exit_code == 0
        assert "Exposure: $0.70 / $2.00" in result.output
        assert "Exposure: $1.50 / $10.00" in result.output
        assert "Active holds: $0.50" in result.output
        assert "Maximum currently authorizable new paid call: $1.30" in result.output
        current.assert_called_once_with(daily_display_limit=2.0, monthly_display_limit=20.0)

    def test_show_reports_live_hard_ceiling_alert(self, runner):
        summary = {
            "per_job_limit": 2.0,
            "daily_limit": 5.0,
            "weekly_limit": 10.0,
            "monthly_limit": 10.0,
            "daily_settled": 0.0,
            "weekly_settled": 10.0,
            "monthly_settled": 10.0,
            "active_holds": 0.25,
            "unresolved_holds": 0,
            "unresolved_exposure": 0.0,
            "daily_exposure": 0.25,
            "weekly_exposure": 10.25,
            "monthly_exposure": 10.25,
            "authorizable_headroom": 0.0,
        }
        with patch("deepr.cli.commands.costs._current_cost_authority", return_value=summary):
            result = runner.invoke(cli, ["costs", "show"])

        assert result.exit_code == 0
        assert "Monthly alert" in result.output
        assert "100% hard ceiling reached" in result.output

    def test_show_reports_positive_exposure_over_zero_ceiling(self, runner):
        summary = {
            "per_job_limit": 0.0,
            "daily_limit": 0.0,
            "weekly_limit": 0.0,
            "monthly_limit": 0.0,
            "daily_settled": 1.0,
            "weekly_settled": 38.52,
            "monthly_settled": 38.52,
            "active_holds": 0.0,
            "unresolved_holds": 0,
            "unresolved_exposure": 0.0,
            "daily_exposure": 1.0,
            "weekly_exposure": 38.52,
            "monthly_exposure": 38.52,
            "authorizable_headroom": 0.0,
        }
        with patch("deepr.cli.commands.costs._current_cost_authority", return_value=summary):
            result = runner.invoke(cli, ["costs", "show"])

        assert result.exit_code == 0
        assert result.output.count("OVER $0.00 CEILING") == 2
        assert "Utilization: 0.0%" not in result.output
        assert "paid API frozen at a $0.00 hard ceiling" in result.output


class TestLiveCostAlertsAndLimits:
    def test_alerts_recomputes_from_current_exposure(self, runner):
        summary = {
            "per_job_limit": 2.0,
            "daily_limit": 5.0,
            "weekly_limit": 10.0,
            "monthly_limit": 10.0,
            "daily_settled": 0.0,
            "weekly_settled": 8.0,
            "monthly_settled": 8.0,
            "active_holds": 0.5,
            "daily_exposure": 0.5,
            "weekly_exposure": 8.5,
            "monthly_exposure": 8.5,
            "authorizable_headroom": 1.5,
        }
        with patch("deepr.cli.commands.costs._current_cost_authority", return_value=summary):
            result = runner.invoke(cli, ["costs", "alerts"])

        assert result.exit_code == 0
        assert "80% warning threshold reached" in result.output
        assert "Settled plus active holds: $8.50" in result.output

    def test_legacy_daily_setter_is_rejected_as_non_authoritative(self, runner):
        result = runner.invoke(cli, ["costs", "limits", "--daily", "2"])

        assert result.exit_code == 1
        assert "legacy dashboard daily setter was not spend authority" in result.output
        assert "DEEPR_MAX_COST_PER_DAY" in result.output

    def test_monthly_setter_updates_authoritative_budget(self, runner):
        summary = {
            "per_job_limit": 2.0,
            "daily_limit": 5.0,
            "weekly_limit": 7.0,
            "monthly_limit": 7.0,
            "daily_settled": 0.0,
            "weekly_settled": 1.0,
            "monthly_settled": 1.0,
            "active_holds": 0.5,
            "daily_exposure": 0.5,
            "weekly_exposure": 1.5,
            "monthly_exposure": 1.5,
            "authorizable_headroom": 2.0,
        }
        config = {"monthly_limit": 10.0}

        def mutate(update):
            update(config)
            return config

        with (
            patch("deepr.cli.commands.budget.mutate_budget_config", side_effect=mutate),
            patch("deepr.cli.commands.costs._current_cost_authority", return_value=summary),
            patch(
                "deepr.core.cost_caps.resolve_spend_caps",
                return_value={"per_job": 2.0, "daily": 5.0, "weekly": 7.0, "monthly": 7.0},
            ),
        ):
            result = runner.invoke(cli, ["costs", "limits", "--monthly", "7"])

        assert result.exit_code == 0
        assert config["monthly_limit"] == 7.0
        assert "Authoritative monthly paid API budget set to $7.00" in result.output
        assert "Monthly hard ceiling: $7.00" in result.output


class TestTimeline:
    """Tests for deepr costs timeline command."""

    def test_timeline_output(self, runner):
        """Timeline command renders chart with daily data."""
        mock_dash = _make_dashboard_mock(days=7, base_cost=1.0)

        with patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash):
            result = runner.invoke(cli, ["costs", "timeline", "--days", "7"])

        assert result.exit_code == 0
        assert "Cost Timeline" in result.output
        assert "Average" in result.output

    def test_timeline_anomaly_detection(self, runner):
        """Days with >2x average cost are marked as anomalies."""
        mock_dash = _make_dashboard_mock(days=7, base_cost=1.0, anomaly_day=3)

        with patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash):
            result = runner.invoke(cli, ["costs", "timeline", "--days", "7"])

        assert result.exit_code == 0
        # Should have at least 1 anomaly
        assert "!" in result.output

    def test_timeline_empty(self, runner):
        """Timeline with no data shows message."""
        mock_dash = _make_dashboard_mock(entries=[])
        mock_dash.get_daily_history = lambda d: []

        with patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash):
            result = runner.invoke(cli, ["costs", "timeline"])

        assert result.exit_code == 0
        assert "No cost data" in result.output


class TestBreakdownPeriod:
    """Tests for --period flag on breakdown command."""

    def _make_period_dashboard(self):
        """Create dashboard with entries spanning multiple periods."""
        now = utc_now()
        entries = [
            CostEntry(operation="research", provider="openai", cost=1.0, timestamp=now),  # today
            CostEntry(operation="chat", provider="xai", cost=2.0, timestamp=now - timedelta(days=3)),  # this week
            CostEntry(
                operation="research", provider="gemini", cost=5.0, timestamp=now - timedelta(days=15)
            ),  # this month
            CostEntry(operation="research", provider="openai", cost=10.0, timestamp=now - timedelta(days=60)),  # older
        ]
        mock_dash = MagicMock(spec=CostDashboard)
        real_aggregator = CostAggregator(entries)
        mock_dash.get_breakdown_by_provider = real_aggregator.get_breakdown_by_provider
        mock_dash.get_breakdown_by_operation = real_aggregator.get_breakdown_by_operation
        mock_dash.get_breakdown_by_model = real_aggregator.get_breakdown_by_model
        return mock_dash

    def test_breakdown_period_today(self, runner):
        """--period today filters to today's entries only."""
        mock_dash = self._make_period_dashboard()

        with patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash):
            result = runner.invoke(cli, ["costs", "breakdown", "--by", "provider", "--period", "today"])

        assert result.exit_code == 0
        assert "Today" in result.output
        # Only today's $1.00 entry
        assert "$1.00" in result.output

    def test_breakdown_period_week(self, runner):
        """--period week filters to last 7 days."""
        mock_dash = self._make_period_dashboard()

        with patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash):
            result = runner.invoke(cli, ["costs", "breakdown", "--by", "provider", "--period", "week"])

        assert result.exit_code == 0
        assert "7 Days" in result.output

    def test_breakdown_period_all(self, runner):
        """--period all includes all entries."""
        mock_dash = self._make_period_dashboard()

        with patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash):
            result = runner.invoke(cli, ["costs", "breakdown", "--by", "provider", "--period", "all"])

        assert result.exit_code == 0
        # Rich may wrap "All Time" across lines; check both words present
        assert "All" in result.output
        assert "Time" in result.output
        # Total should include the $10.00 older entry
        assert "$18.00" in result.output


class TestExpertCosts:
    """Tests for deepr costs expert command."""

    def _make_expert_profile(self):
        mock_profile = MagicMock()
        mock_profile.total_research_cost = 15.50
        mock_profile.monthly_spending = 3.25
        mock_profile.monthly_learning_budget = 5.0
        mock_profile.research_triggered = 10
        mock_profile.conversations = 25
        return mock_profile

    def test_expert_costs_found(self, runner):
        """Display cost summary for a known expert."""
        mock_profile = self._make_expert_profile()
        mock_store_cls = MagicMock()
        mock_store_cls.return_value.load.return_value = mock_profile

        mock_dash = MagicMock(spec=CostDashboard)
        mock_dash.aggregator = CostAggregator([])

        with (
            patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash),
            patch("deepr.experts.profile.ExpertStore", mock_store_cls),
        ):
            result = runner.invoke(cli, ["costs", "expert", "Climate Expert"])

        assert result.exit_code == 0
        assert "15.50" in result.output
        assert "3.25" in result.output
        assert "Climate Expert" in result.output

    def test_expert_costs_not_found(self, runner):
        """Error message when expert doesn't exist."""
        mock_store_cls = MagicMock()
        mock_store_cls.return_value.load.return_value = None

        with patch("deepr.experts.profile.ExpertStore", mock_store_cls):
            result = runner.invoke(cli, ["costs", "expert", "NonExistent"])

        assert result.exit_code == 0
        assert "not found" in result.output

    def test_expert_breakdown_by_operation(self, runner):
        """Show per-operation cost breakdown for expert."""
        mock_profile = self._make_expert_profile()
        mock_store_cls = MagicMock()
        mock_store_cls.return_value.load.return_value = mock_profile

        now = utc_now()
        entries = [
            CostEntry(
                operation="research", provider="openai", cost=5.0, timestamp=now, metadata={"expert": "Climate Expert"}
            ),
            CostEntry(
                operation="chat", provider="openai", cost=2.0, timestamp=now, metadata={"expert": "Climate Expert"}
            ),
            CostEntry(
                operation="research", provider="xai", cost=3.0, timestamp=now, metadata={"expert": "Other Expert"}
            ),
        ]
        mock_dash = MagicMock(spec=CostDashboard)
        mock_dash.aggregator = CostAggregator(entries)

        with (
            patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash),
            patch("deepr.experts.profile.ExpertStore", mock_store_cls),
        ):
            result = runner.invoke(cli, ["costs", "expert", "Climate Expert"])

        assert result.exit_code == 0
        assert "$5.00" in result.output
        assert "$2.00" in result.output
        assert "research" in result.output
        assert "chat" in result.output


class TestCostAggregatorExpert:
    """Tests for expert-related CostAggregator methods."""

    def test_get_entries_by_expert(self):
        entries = [
            CostEntry(operation="research", provider="openai", cost=1.0, metadata={"expert": "Alice"}),
            CostEntry(operation="chat", provider="xai", cost=2.0, metadata={"expert": "Bob"}),
            CostEntry(operation="research", provider="gemini", cost=3.0, metadata={"expert": "Alice"}),
            CostEntry(operation="research", provider="openai", cost=4.0, metadata={}),
        ]
        agg = CostAggregator(entries)

        alice = agg.get_entries_by_expert("Alice")
        assert len(alice) == 2
        assert all(e.metadata.get("expert") == "Alice" for e in alice)

        bob = agg.get_entries_by_expert("Bob")
        assert len(bob) == 1

        nobody = agg.get_entries_by_expert("Nobody")
        assert len(nobody) == 0

    def test_get_expert_breakdown(self):
        entries = [
            CostEntry(operation="research", provider="openai", cost=5.0, metadata={"expert": "Alice"}),
            CostEntry(operation="chat", provider="openai", cost=2.0, metadata={"expert": "Alice"}),
            CostEntry(operation="research", provider="xai", cost=3.0, metadata={"expert": "Alice"}),
        ]
        agg = CostAggregator(entries)

        breakdown = agg.get_expert_breakdown("Alice")
        assert breakdown["research"] == 8.0
        assert breakdown["chat"] == 2.0


class TestSpendDecisionReadback:
    """Tests for deepr costs spend-decisions."""

    def _write_decisions(self, tmp_path, monkeypatch):
        from deepr.experts.spend_decisions import record_spend_decision

        monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "costs"))
        record_spend_decision(
            expert_name="Climate Expert",
            operation="expert_sync",
            topic="source drift",
            capacity_source="api_metered",
            estimated_cost=0.25,
            factors={"gap_closure": 0.8, "value": 0.7, "urgency": 0.6, "volatility": 0.9},
            decision={
                "allowed": True,
                "tier": "normal",
                "reason": "benefit 0.3024 >= hurdle 0.2500",
                "benefit": 0.3024,
                "hurdle": 0.25,
                "pausable": False,
            },
            now=datetime(2026, 7, 1, 1, 0, tzinfo=UTC),
        )
        record_spend_decision(
            expert_name="Rust Expert",
            operation="expert_sync",
            topic="edition drift",
            capacity_source="api_metered",
            estimated_cost=0.5,
            factors={"gap_closure": 0.6, "value": 0.5, "urgency": 0.5, "volatility": 0.5},
            decision={
                "allowed": False,
                "tier": "conserve",
                "reason": "benefit 0.0750 < hurdle 2.0000",
                "benefit": 0.075,
                "hurdle": 2.0,
                "pausable": True,
            },
            now=datetime(2026, 7, 1, 2, 0, tzinfo=UTC),
        )

    def test_spend_decisions_json_is_latest_first(self, runner, tmp_path, monkeypatch):
        self._write_decisions(tmp_path, monkeypatch)

        result = runner.invoke(cli, ["costs", "spend-decisions", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["schema_version"] == "deepr-cost-spend-decisions-v1"
        assert payload["kind"] == "deepr.costs.spend_decisions"
        assert payload["contract"]["read_only"] is True
        assert payload["contract"]["cost_usd"] == 0.0
        assert payload["count"] == 2
        assert payload["records"][0]["expert_name"] == "Rust Expert"
        assert payload["records"][0]["decision"]["allowed"] is False

    def test_spend_decisions_table_filters_deferred_expert(self, runner, tmp_path, monkeypatch):
        self._write_decisions(tmp_path, monkeypatch)

        result = runner.invoke(
            cli,
            ["costs", "spend-decisions", "--expert", "Rust Expert", "--decision", "deferred"],
        )

        assert result.exit_code == 0
        assert "Spend Decisions" in result.output
        assert "Rust" in result.output
        assert "deferred" in result.output
        assert "Climate" not in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestCostsDoctor:
    """Tests for deepr costs doctor command."""

    def test_costs_doctor_command_runs(self, runner):
        mock_dash = MagicMock(spec=CostDashboard)
        mock_dash.storage_path = Path("data/costs/cost_log.json")
        mock_dash.entries = [CostEntry(operation="research", provider="openai", cost=1.0)]

        mock_ledger = MagicMock()
        mock_ledger.get_health.return_value = {
            "path": "data/costs/cost_ledger.jsonl",
            "primary_write_path": "data/costs/cost_ledger.jsonl",
            "accounting_read_paths": ["data/costs/cost_ledger.jsonl"],
            "accounting_sources": [{"path": "data/costs/cost_ledger.jsonl", "event_count": 1, "total_cost_usd": 1.0}],
            "accounting_complete": True,
            "writable": True,
            "accounting_ready": True,
            "event_count": 1,
        }
        mock_ledger.with_locked_accounting_events.side_effect = lambda operation: (
            [] if operation is list else operation([MagicMock(cost_usd=1.0)])
        )

        with (
            patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash),
            patch("deepr.cli.commands.costs.CostLedger", return_value=mock_ledger) as ledger_class,
        ):
            result = runner.invoke(cli, ["costs", "doctor"])

        assert result.exit_code == 0
        ledger_class.assert_called_once_with()
        assert "Cost Tracking Doctor" in result.output
        assert "PASS" in result.output

    def test_costs_doctor_detects_drift(self, runner):
        mock_dash = MagicMock(spec=CostDashboard)
        mock_dash.storage_path = Path("data/costs/cost_log.json")
        mock_dash.entries = [CostEntry(operation="research", provider="openai", cost=1.0)]

        mock_ledger = MagicMock()
        mock_ledger.get_health.return_value = {
            "path": "data/costs/cost_ledger.jsonl",
            "primary_write_path": "data/costs/cost_ledger.jsonl",
            "accounting_read_paths": ["data/costs/cost_ledger.jsonl"],
            "accounting_sources": [{"path": "data/costs/cost_ledger.jsonl", "event_count": 1, "total_cost_usd": 2.0}],
            "accounting_complete": True,
            "writable": True,
            "accounting_ready": True,
            "event_count": 1,
        }
        mock_ledger.with_locked_accounting_events.side_effect = lambda operation: (
            [] if operation is list else operation([MagicMock(cost_usd=2.0)])
        )

        with (
            patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash),
            patch("deepr.cli.commands.costs.CostLedger", return_value=mock_ledger),
        ):
            result = runner.invoke(cli, ["costs", "doctor", "--drift-threshold", "0.1"])

        assert result.exit_code == 1
        assert "FAIL" in result.output
        assert "drift=$" in result.output

    def test_costs_doctor_detects_ledger_that_is_not_accounting_ready(self, runner):
        mock_dash = MagicMock(spec=CostDashboard)
        mock_dash.storage_path = Path("data/costs/cost_log.json")
        mock_dash.entries = []
        mock_ledger = MagicMock()
        mock_ledger.get_health.return_value = {
            "path": "data/costs/cost_ledger.jsonl",
            "writable": True,
            "accounting_ready": False,
            "error": "CostLedgerReadError: malformed event",
        }
        mock_ledger.with_locked_accounting_events.side_effect = lambda operation: operation([])

        with (
            patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash),
            patch("deepr.cli.commands.costs.CostLedger", return_value=mock_ledger),
        ):
            result = runner.invoke(cli, ["costs", "doctor"])

        assert result.exit_code == 1
        assert "Ledger accounting ready" in result.output
        assert "malformed event" in result.output
        assert "FAIL" in result.output

    def test_costs_doctor_reports_unknown_drift_when_ledger_is_unreadable(self, runner):
        mock_dash = MagicMock(spec=CostDashboard)
        mock_dash.storage_path = Path("data/costs/cost_log.json")
        mock_dash.entries = []
        mock_ledger = MagicMock()
        mock_ledger.get_health.return_value = {
            "path": "data/costs/cost_ledger.jsonl",
            "writable": True,
            "accounting_ready": False,
            "error": "CostLedgerReadError: malformed event",
        }
        mock_ledger.with_locked_accounting_events.side_effect = RuntimeError("malformed accounting event")

        with (
            patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash),
            patch("deepr.cli.commands.costs.CostLedger", return_value=mock_ledger),
        ):
            result = runner.invoke(cli, ["costs", "doctor"])

        assert result.exit_code == 1
        assert "UNKNOWN" in result.output
        assert "Canonical cost ledger is unreadable" in result.output
