"""Unit tests for budget CLI commands - no API calls.

Tests the budget command structure, parameter validation, and display logic
without making any external API calls.
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.cli.main import cli


class TestBudgetCommandStructure:
    """Test budget command structure and help text."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_command_exists(self, runner):
        """Test that 'budget' command exists."""
        result = runner.invoke(cli, ["budget", "--help"])
        assert result.exit_code == 0
        assert "budget" in result.output.lower()

    def test_budget_command_shows_subcommands(self, runner):
        """Test that budget command lists subcommands."""
        result = runner.invoke(cli, ["budget", "--help"])
        assert result.exit_code == 0

        output = result.output.lower()
        # Should have set and status subcommands
        assert "set" in output
        assert "status" in output


class TestBudgetSetCommand:
    """Test 'budget set' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_set_help(self, runner):
        """Test that 'budget set' help works."""
        result = runner.invoke(cli, ["budget", "set", "--help"])
        assert result.exit_code == 0

    def test_budget_set_requires_amount(self, runner):
        """Test that 'budget set' requires an amount."""
        result = runner.invoke(cli, ["budget", "set"])
        # Should fail or show error about missing amount
        assert result.exit_code != 0

    def test_budget_set_accepts_amount(self, runner):
        """Test that 'budget set' accepts an amount argument."""
        result = runner.invoke(cli, ["budget", "set", "10.00"])
        assert result.exit_code == 0

    def test_budget_set_validates_numeric_amount(self, runner):
        """Test that 'budget set' validates numeric amounts."""
        result = runner.invoke(cli, ["budget", "set", "abc"])
        # Should reject non-numeric amounts
        assert result.exit_code != 0

    def test_budget_set_zero_freezes_paid_api(self, runner):
        """Test that 'budget set 0' creates a hard paid freeze."""
        result = runner.invoke(cli, ["budget", "set", "0"])
        assert result.exit_code == 0
        assert "paid api dispatch frozen" in result.output.lower()

    def test_budget_set_rejects_unlimited(self, runner):
        """Unlimited paid autonomy is not a valid budget state."""
        result = runner.invoke(cli, ["budget", "set", "--", "-1"])
        assert result.exit_code == 2
        assert "not in the range" in result.output.lower()


class TestBudgetStatusCommand:
    """Test 'budget status' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_status_exists(self, runner):
        """Test that budget status command exists."""
        result = runner.invoke(cli, ["budget", "status", "--help"])
        assert result.exit_code == 0

    def test_budget_status_shows_info(self, runner):
        """Test that 'budget status' shows budget information."""
        with patch("deepr.cli.commands.budget.load_budget_config") as mock_load:
            mock_load.return_value = {"monthly_limit": 50.0, "monthly_spending": 10.0, "current_month": "2026-01"}
            result = runner.invoke(cli, ["budget", "status"])
            assert result.exit_code == 0
            # Should show budget info
            assert "$" in result.output

    def test_budget_status_displays_effective_tighter_authority(self, runner):
        with (
            patch(
                "deepr.cli.commands.budget.load_budget_config",
                return_value={"monthly_limit": 50.0, "monthly_spending": 2.0, "current_month": "2026-07"},
            ),
            patch("deepr.cli.commands.budget.resolve_spend_caps", return_value={"monthly": 10.0}),
            patch("deepr.cli.commands.budget._ledger_month_spend", return_value=2.0),
            patch("deepr.cli.commands.budget._durable_active_cost", return_value=0.0),
        ):
            result = runner.invoke(cli, ["budget", "status"])

        assert result.exit_code == 0
        assert "$2.00 / $10.00" in result.output
        assert "Configured monthly budget: $50.00; tighter policy is active" in result.output

    def test_budget_status_counts_active_holds_in_exposure(self, runner):
        with (
            patch(
                "deepr.cli.commands.budget.load_budget_config",
                return_value={"monthly_limit": 10.0, "monthly_spending": 0.0, "current_month": "2026-07"},
            ),
            patch("deepr.cli.commands.budget.resolve_spend_caps", return_value={"monthly": 10.0}),
            patch("deepr.cli.commands.budget._ledger_month_spend", return_value=2.0),
            patch("deepr.cli.commands.budget._durable_active_cost", return_value=0.5),
        ):
            result = runner.invoke(cli, ["budget", "status"])

        assert result.exit_code == 0
        assert "Settled this month: $2.00" in result.output
        assert "Active durable holds: $0.50" in result.output
        assert "Budget: $2.50 / $10.00" in result.output
        assert "Remaining: $7.50" in result.output

    def test_budget_status_fails_closed_when_holds_are_unreadable(self, runner):
        with (
            patch(
                "deepr.cli.commands.budget.load_budget_config",
                return_value={"monthly_limit": 10.0, "monthly_spending": 0.0, "current_month": "2026-07"},
            ),
            patch("deepr.cli.commands.budget.resolve_spend_caps", return_value={"monthly": 10.0}),
            patch("deepr.cli.commands.budget._ledger_month_spend", return_value=2.0),
            patch("deepr.cli.commands.budget._durable_active_cost", return_value=None),
        ):
            result = runner.invoke(cli, ["budget", "status"])

        assert result.exit_code == 0
        assert "Active durable holds: UNKNOWN" in result.output
        assert "Paid API blocked" in result.output
        assert "Remaining: $0.00 (fail closed)" in result.output


class TestBudgetHistoryCommand:
    """Test 'budget history' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_history_exists(self, runner):
        """Test that budget history command exists."""
        result = runner.invoke(cli, ["budget", "history", "--help"])
        assert result.exit_code == 0

    def test_budget_history_limit_option(self, runner):
        """Test that --limit option exists."""
        result = runner.invoke(cli, ["budget", "history", "--help"])
        assert "--limit" in result.output or "-n" in result.output

    def test_budget_history_reads_canonical_ledger(self, runner):
        event = SimpleNamespace(
            timestamp=datetime(2026, 7, 1, 0, 22, tzinfo=UTC),
            cost_usd=1.25,
            provider="openai",
            model="gpt-5",
            operation="research_completion",
            source="test.canonical",
            task_id="research_job-123",
            session_id="",
        )
        ledger = MagicMock()
        ledger.with_locked_accounting_events.side_effect = lambda operation: operation([event])

        with (
            patch("deepr.observability.cost_ledger.CostLedger", return_value=ledger),
            patch("deepr.cli.commands.budget._durable_active_cost", return_value=0.5),
        ):
            result = runner.invoke(cli, ["budget", "history"])

        assert result.exit_code == 0
        assert "openai/gpt-5" in result.output
        assert "research_completion | test.canonical | research_job-123" in result.output
        assert "Total all-time settled spending: $1.250000" in result.output
        assert "Active durable holds: $0.500000" in result.output

    def test_budget_history_fails_closed_when_ledger_is_unreadable(self, runner):
        ledger = MagicMock()
        ledger.with_locked_accounting_events.side_effect = OSError("ledger unavailable")

        with patch("deepr.observability.cost_ledger.CostLedger", return_value=ledger):
            result = runner.invoke(cli, ["budget", "history"])

        assert result.exit_code == 1
        assert "Canonical cost ledger is unreadable" in result.output


class TestBudgetSafetyCommand:
    """Test 'budget safety' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_safety_exists(self, runner):
        """Test that budget safety command exists."""
        result = runner.invoke(cli, ["budget", "safety", "--help"])
        assert result.exit_code == 0

    def test_budget_safety_shows_limits(self, runner):
        """Test that budget safety shows cost limits."""
        result = runner.invoke(cli, ["budget", "safety"])
        output = result.output.lower()
        # Should mention limits or safety
        assert "limit" in output or "safety" in output or "daily" in output


class TestBudgetFreezeCommands:
    """Manual freezes cannot be cleared without proven headroom."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_freeze_persists_fail_closed_state(self, runner):
        config = {"monthly_limit": 10.0, "monthly_spending": 2.0}

        def mutate(callback):
            callback(config)
            return config

        with patch("deepr.cli.commands.budget.mutate_budget_config", side_effect=mutate):
            result = runner.invoke(cli, ["budget", "freeze", "--reason", "operator stop"])

        assert result.exit_code == 0
        assert config["paid_api_frozen"] is True
        assert config["freeze_reason"] == "operator stop"

    def test_unfreeze_refuses_exhausted_month(self, runner):
        config = {
            "monthly_limit": 10.0,
            "monthly_spending": 9.0,
            "paid_api_frozen": True,
        }

        def mutate(callback):
            callback(config)
            return config

        with (
            patch("deepr.cli.commands.budget.mutate_budget_config", side_effect=mutate),
            patch("deepr.cli.commands.budget._ledger_month_spend", return_value=10.0),
        ):
            result = runner.invoke(cli, ["budget", "unfreeze"])

        assert result.exit_code == 1
        assert "exhausted" in result.output.lower()
        assert config["paid_api_frozen"] is True

    def test_unfreeze_requires_readable_canonical_ledger(self, runner):
        config = {
            "monthly_limit": 10.0,
            "monthly_spending": 1.0,
            "paid_api_frozen": True,
        }

        original = dict(config)

        def mutate(callback):
            callback(config)
            return config

        with (
            patch("deepr.cli.commands.budget.mutate_budget_config", side_effect=mutate),
            patch("deepr.cli.commands.budget._ledger_month_spend", return_value=None),
        ):
            result = runner.invoke(cli, ["budget", "unfreeze"])

        assert result.exit_code == 1
        assert "unreadable" in result.output.lower()
        assert config == original

    def test_unfreeze_succeeds_only_with_positive_headroom(self, runner):
        config = {
            "monthly_limit": 10.0,
            "monthly_spending": 1.0,
            "paid_api_frozen": True,
            "freeze_reason": "operator stop",
            "frozen_at": "2026-07-25T00:00:00",
        }

        def mutate(callback):
            callback(config)
            return config

        with (
            patch("deepr.cli.commands.budget.mutate_budget_config", side_effect=mutate),
            patch("deepr.cli.commands.budget._ledger_month_spend", return_value=2.0),
        ):
            result = runner.invoke(cli, ["budget", "unfreeze"])

        assert result.exit_code == 0
        assert config["paid_api_frozen"] is False
        assert config["freeze_reason"] == ""
        assert "frozen_at" not in config

    def test_concurrent_record_and_limit_update_cannot_clear_freeze(self):
        from deepr.cli.commands.budget import load_budget_config, mutate_budget_config, record_spending

        def freeze_update():
            def update(config):
                config["paid_api_frozen"] = True
                config["freeze_reason"] = "concurrency test"

            mutate_budget_config(update)

        def limit_update():
            mutate_budget_config(lambda config: config.__setitem__("monthly_limit", 10.0))

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(freeze_update),
                executor.submit(limit_update),
                executor.submit(record_spending, 0.25, "job-race", "race test"),
            ]
            for future in futures:
                future.result(timeout=2)

        config = load_budget_config()
        assert config["paid_api_frozen"] is True
        assert config["monthly_limit"] == 10.0
        assert config["monthly_spending"] == pytest.approx(0.25)
        assert config["history"][-1]["job_id"] == "job-race"


class TestBudgetValidation:
    """Test budget validation logic."""

    def test_validate_budget_accepts_valid_amounts(self):
        """Test that validation accepts valid budget amounts without confirmation."""
        from deepr.cli.validation import validate_budget

        # Should accept amounts below warn threshold without prompting
        assert validate_budget(5.0) == 5.0
        assert validate_budget(0.5) == 0.5

    def test_validate_budget_rejects_negative(self):
        """Test that validation rejects negative amounts (except -1 for unlimited)."""
        import click

        from deepr.cli.validation import validate_budget

        # Negative amounts below min_budget should be rejected
        with pytest.raises(click.UsageError):
            validate_budget(-5.0, min_budget=0.0)

    def test_validate_budget_accepts_zero_with_zero_min(self):
        """Test that validation accepts zero when min_budget is 0."""
        from deepr.cli.validation import validate_budget

        # Zero should be accepted when min_budget is 0
        assert validate_budget(0.0, min_budget=0.0) == 0.0

    def test_validate_budget_rejects_below_min(self):
        """Test that validation rejects amounts below min_budget."""
        import click

        from deepr.cli.validation import validate_budget

        with pytest.raises(click.UsageError):
            validate_budget(0.1, min_budget=0.5)

    def test_validate_budget_accepts_at_min(self):
        """Test that validation accepts amounts at min_budget."""
        from deepr.cli.validation import validate_budget

        assert validate_budget(0.5, min_budget=0.5) == 0.5

    @pytest.mark.parametrize("invalid", [True, -0.01, float("inf"), float("nan")])
    def test_record_spending_rejects_invalid_cost(self, invalid):
        from deepr.cli.commands.budget import record_spending

        with pytest.raises(ValueError, match="finite non-negative"):
            record_spending(invalid, "job", "invalid")


class TestBudgetDisplay:
    """Test budget display formatting."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_status_displays_currency_format(self, runner):
        """Test that budget status displays amounts in currency format."""
        with patch("deepr.cli.commands.budget.load_budget_config") as mock_load:
            mock_load.return_value = {"monthly_limit": 50.0, "monthly_spending": 10.0, "current_month": "2026-01"}
            result = runner.invoke(cli, ["budget", "status"])

            # Should display dollar amounts
            assert "$" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
