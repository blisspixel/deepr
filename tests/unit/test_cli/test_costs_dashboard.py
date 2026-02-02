"""Tests for cost dashboard CLI commands (ROADMAP 4.3)."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.observability.costs import CostEntry, CostDashboard, CostAggregator


@pytest.fixture
def runner():
    return CliRunner()


def _make_entries(days=7, base_cost=1.0, anomaly_day=None):
    """Create test cost entries over several days."""
    entries = []
    now = datetime.utcnow()
    for i in range(days):
        cost = base_cost
        if anomaly_day is not None and i == anomaly_day:
            cost = base_cost * 5  # >2x average
        entries.append(CostEntry(
            operation="research",
            provider="openai",
            cost=cost,
            model="gpt-5.2",
            timestamp=now - timedelta(days=days - 1 - i),
        ))
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
        today = datetime.utcnow().date()
        for i in range(num_days):
            target_date = today - timedelta(days=i)
            total = sum(e.cost for e in entries if e.date == target_date)
            history.append({
                "date": target_date.isoformat(),
                "total": total,
                "limit": 10.0,
                "utilization": total / 10.0,
            })
        return list(reversed(history))

    dashboard.get_daily_history = get_daily_history
    return dashboard


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
        now = datetime.utcnow()
        entries = [
            CostEntry(operation="research", provider="openai", cost=1.0,
                      timestamp=now),  # today
            CostEntry(operation="chat", provider="xai", cost=2.0,
                      timestamp=now - timedelta(days=3)),  # this week
            CostEntry(operation="research", provider="gemini", cost=5.0,
                      timestamp=now - timedelta(days=15)),  # this month
            CostEntry(operation="research", provider="openai", cost=10.0,
                      timestamp=now - timedelta(days=60)),  # older
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

        with patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash), \
             patch("deepr.experts.profile.ExpertStore", mock_store_cls):
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

        now = datetime.utcnow()
        entries = [
            CostEntry(operation="research", provider="openai", cost=5.0,
                      timestamp=now, metadata={"expert": "Climate Expert"}),
            CostEntry(operation="chat", provider="openai", cost=2.0,
                      timestamp=now, metadata={"expert": "Climate Expert"}),
            CostEntry(operation="research", provider="xai", cost=3.0,
                      timestamp=now, metadata={"expert": "Other Expert"}),
        ]
        mock_dash = MagicMock(spec=CostDashboard)
        mock_dash.aggregator = CostAggregator(entries)

        with patch("deepr.cli.commands.costs.CostDashboard", return_value=mock_dash), \
             patch("deepr.experts.profile.ExpertStore", mock_store_cls):
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
            CostEntry(operation="research", provider="openai", cost=1.0,
                      metadata={"expert": "Alice"}),
            CostEntry(operation="chat", provider="xai", cost=2.0,
                      metadata={"expert": "Bob"}),
            CostEntry(operation="research", provider="gemini", cost=3.0,
                      metadata={"expert": "Alice"}),
            CostEntry(operation="research", provider="openai", cost=4.0,
                      metadata={}),
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
            CostEntry(operation="research", provider="openai", cost=5.0,
                      metadata={"expert": "Alice"}),
            CostEntry(operation="chat", provider="openai", cost=2.0,
                      metadata={"expert": "Alice"}),
            CostEntry(operation="research", provider="xai", cost=3.0,
                      metadata={"expert": "Alice"}),
        ]
        agg = CostAggregator(entries)

        breakdown = agg.get_expert_breakdown("Alice")
        assert breakdown["research"] == 8.0
        assert breakdown["chat"] == 2.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
