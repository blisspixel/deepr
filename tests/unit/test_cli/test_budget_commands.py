"""Unit tests for budget CLI commands - no API calls.

Tests the budget command structure, parameter validation, and display logic
without making any external API calls.
"""

import sys
from pathlib import Path
from unittest.mock import patch

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
        with patch("deepr.cli.commands.budget.save_budget_config") as mock_save:
            with patch("deepr.cli.commands.budget.load_budget_config") as mock_load:
                mock_load.return_value = {"monthly_limit": 0, "monthly_spending": 0}
                result = runner.invoke(cli, ["budget", "set", "10.00"])
                # Should accept the amount
                assert result.exit_code == 0

    def test_budget_set_validates_numeric_amount(self, runner):
        """Test that 'budget set' validates numeric amounts."""
        result = runner.invoke(cli, ["budget", "set", "abc"])
        # Should reject non-numeric amounts
        assert result.exit_code != 0

    def test_budget_set_accepts_zero_for_confirm_mode(self, runner):
        """Test that 'budget set 0' enables confirm-every-job mode."""
        with patch("deepr.cli.commands.budget.save_budget_config") as mock_save:
            with patch("deepr.cli.commands.budget.load_budget_config") as mock_load:
                mock_load.return_value = {"monthly_limit": 0, "monthly_spending": 0}
                result = runner.invoke(cli, ["budget", "set", "0"])
                assert result.exit_code == 0
                assert "confirm every job" in result.output.lower()

    def test_budget_set_accepts_negative_one_for_unlimited(self, runner):
        """Test that 'budget set -- -1' enables unlimited mode (using -- to pass negative)."""
        with patch("deepr.cli.commands.budget.save_budget_config") as mock_save:
            with patch("deepr.cli.commands.budget.load_budget_config") as mock_load:
                mock_load.return_value = {"monthly_limit": 0, "monthly_spending": 0}
                # Use -- to indicate end of options, allowing -1 as argument
                result = runner.invoke(cli, ["budget", "set", "--", "-1"])
                assert result.exit_code == 0
                assert "unlimited" in result.output.lower()


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
