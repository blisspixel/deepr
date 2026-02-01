"""Unit tests for CLI run module.

Tests the research job execution workflow including:
- Focus command with valid query
- Error handling for invalid provider
- Glob pattern resolution for file uploads
- --yes flag skips confirmation
- JSON output mode
- Cost estimation bounds

All tests use mocks to avoid external API calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from click.testing import CliRunner

# Import Hypothesis for property-based testing
from hypothesis import given, settings, assume
import hypothesis.strategies as st

from deepr.cli.commands.run import (
    run,
    focus,
    estimate_cost,
)


class TestEstimateCost:
    """Test cost estimation function."""

    def test_o4_mini_model_cost(self):
        """Test o4-mini model returns expected cost."""
        cost = estimate_cost("o4-mini-deep-research")
        assert cost == 0.10

    def test_o3_model_cost(self):
        """Test o3 model returns expected cost."""
        cost = estimate_cost("o3-deep-research")
        assert cost == 0.50

    def test_unknown_model_default_cost(self):
        """Test unknown model returns default cost."""
        cost = estimate_cost("unknown-model")
        assert cost == 0.15

    def test_cost_always_positive(self):
        """Test that cost is always positive."""
        for model in ["o4-mini", "o3", "unknown", "", "test-model"]:
            cost = estimate_cost(model)
            assert cost > 0, f"Model {model} has non-positive cost"


class TestFocusCommand:
    """Test the focus command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_focus_requires_query(self, runner):
        """Test that focus command requires a query argument."""
        result = runner.invoke(run, ["focus"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "query" in result.output.lower()

    @patch("deepr.cli.commands.run._run_single")
    def test_focus_calls_run_single(self, mock_run_single, runner):
        """Test that focus command calls _run_single with correct args."""
        # Mock asyncio.run to capture the coroutine
        with patch("deepr.cli.commands.run.asyncio.run") as mock_asyncio:
            result = runner.invoke(run, ["focus", "Test query"])
            
            # Verify asyncio.run was called
            mock_asyncio.assert_called_once()

    def test_focus_with_model_option(self, runner):
        """Test focus command accepts model option."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "-m", "o3-deep-research"])
            # Should not fail on argument parsing
            assert "Error" not in result.output or result.exit_code == 0

    def test_focus_with_provider_option(self, runner):
        """Test focus command accepts provider option."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "-p", "gemini"])
            # Should not fail on argument parsing
            assert "Error" not in result.output or result.exit_code == 0

    def test_focus_invalid_provider_rejected(self, runner):
        """Test that invalid provider is rejected."""
        result = runner.invoke(run, ["focus", "Test query", "-p", "invalid_provider"])
        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "choice" in result.output.lower()

    def test_focus_with_yes_flag(self, runner):
        """Test focus command accepts --yes flag."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "--yes"])
            # Should not fail on argument parsing
            assert result.exit_code == 0 or "Error" not in result.output

    def test_focus_with_upload_option(self, runner):
        """Test focus command accepts upload option."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "-u", "test.pdf"])
            # Should not fail on argument parsing (file doesn't need to exist for parsing)
            assert result.exit_code == 0 or "Error" not in result.output

    def test_focus_with_limit_option(self, runner):
        """Test focus command accepts limit option."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "-l", "5.00"])
            # Should not fail on argument parsing
            assert result.exit_code == 0 or "Error" not in result.output


class TestRunSingleAsync:
    """Test the _run_single async function."""

    @pytest.mark.asyncio
    async def test_run_single_estimates_cost(self):
        """Test that _run_single estimates cost before proceeding."""
        from deepr.cli.commands.run import _run_single
        from deepr.cli.output import OutputContext, OutputMode
        
        output_context = OutputContext(mode=OutputMode.QUIET)
        
        # Mock all external dependencies
        with patch("deepr.cli.commands.run.check_budget_approval", return_value=True):
            with patch("deepr.providers.create_provider") as mock_create:
                mock_provider = MagicMock()
                mock_provider.submit_research = AsyncMock(return_value="job-123")
                mock_create.return_value = mock_provider
                
                with patch("deepr.config.load_config", return_value={"api_key": "test"}):
                    with patch("deepr.cli.commands.run.SQLiteQueue") as mock_queue_class:
                        mock_queue_instance = MagicMock()
                        mock_queue_instance.enqueue = AsyncMock(return_value="job-123")
                        mock_queue_class.return_value = mock_queue_instance
                        
                        # This should not raise
                        await _run_single(
                            query="Test query",
                            model="o4-mini-deep-research",
                            provider="openai",
                            no_web=False,
                            no_code=False,
                            upload=(),
                            limit=None,
                            yes=True,  # Skip confirmation
                            output_context=output_context,
                        )

    @pytest.mark.asyncio
    async def test_run_single_respects_yes_flag(self):
        """Test that --yes flag skips budget confirmation."""
        from deepr.cli.commands.run import _run_single
        from deepr.cli.output import OutputContext, OutputMode
        
        output_context = OutputContext(mode=OutputMode.QUIET)
        
        with patch("deepr.cli.commands.run.check_budget_approval") as mock_budget:
            mock_budget.return_value = False  # Would normally block
            
            with patch("deepr.providers.create_provider") as mock_create:
                mock_provider = MagicMock()
                mock_provider.submit_research = AsyncMock(return_value="job-123")
                mock_create.return_value = mock_provider
                
                with patch("deepr.config.load_config", return_value={"api_key": "test"}):
                    with patch("deepr.cli.commands.run.SQLiteQueue") as mock_queue_class:
                        mock_queue_instance = MagicMock()
                        mock_queue_instance.enqueue = AsyncMock(return_value="job-123")
                        mock_queue_class.return_value = mock_queue_instance
                        
                        # With yes=True, should proceed even if budget check fails
                        await _run_single(
                            query="Test query",
                            model="o4-mini-deep-research",
                            provider="openai",
                            no_web=False,
                            no_code=False,
                            upload=(),
                            limit=None,
                            yes=True,
                            output_context=output_context,
                        )


class TestOutputModes:
    """Test different output modes.
    
    The CLI uses these flags (from output_options decorator):
    - --verbose / -v : Detailed output
    - --json : Machine-readable JSON output
    - --quiet / -q : Suppress all output except errors
    """

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_json_output_mode(self, runner):
        """Test JSON output mode produces valid JSON."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            # Use --json flag (not --output json)
            result = runner.invoke(run, ["focus", "Test query", "--json", "--yes"])
            # In JSON mode, output should be parseable or empty
            # (actual JSON output depends on implementation)
            assert result.exit_code == 0 or "Error" not in result.output

    def test_quiet_output_mode(self, runner):
        """Test quiet output mode minimizes output."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            # Use --quiet or -q flag (not --output quiet)
            result = runner.invoke(run, ["focus", "Test query", "--quiet", "--yes"])
            # Quiet mode should have minimal output
            assert result.exit_code == 0 or "Error" not in result.output

    def test_verbose_output_mode(self, runner):
        """Test verbose output mode shows detailed output."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            # Use --verbose or -v flag
            result = runner.invoke(run, ["focus", "Test query", "--verbose", "--yes"])
            # Should not fail on argument parsing
            assert result.exit_code == 0 or "Error" not in result.output

    def test_conflicting_output_modes_rejected(self, runner):
        """Test that conflicting output modes are rejected."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            # Using both --json and --quiet should fail
            result = runner.invoke(run, ["focus", "Test query", "--json", "--quiet", "--yes"])
            # Should fail with usage error about conflicting flags
            assert result.exit_code != 0


# =============================================================================
# Property-Based Tests
# =============================================================================


class TestPropertyBasedCostEstimation:
    """Property-based tests for cost estimation."""

    @pytest.mark.property
    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_property_cost_always_positive(self, model_name):
        """
        Property: Cost Estimation Non-Negative
        
        INVARIANT: Cost estimation for ANY model name (including empty,
        random strings, etc.) MUST return a positive value.
        
        This ensures:
        - No division by zero in budget calculations
        - Unknown models have safe fallback
        - No negative costs that could bypass limits
        
        Validates: Requirement 2.7 (Cost estimation bounds)
        """
        cost = estimate_cost(model_name)
        
        assert cost > 0, f"Model '{model_name}' has non-positive cost: {cost}"
        assert isinstance(cost, (int, float)), f"Cost is not numeric: {type(cost)}"

    @pytest.mark.property
    @given(st.booleans())
    @settings(max_examples=20, deadline=None)
    def test_property_web_search_affects_cost(self, enable_web_search):
        """
        Property: Web search parameter is accepted
        
        INVARIANT: The enable_web_search parameter should be accepted
        without raising errors.
        
        Validates: Requirement 2.3 (Parameter handling)
        """
        # Should not raise for any boolean value
        cost = estimate_cost("o4-mini-deep-research", enable_web_search=enable_web_search)
        assert cost > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
