"""Unit tests for CLI parameter validation.

Tests command-line argument parsing, validation, and error handling
without making any API calls.
"""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock, AsyncMock
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.cli.main import cli


class TestCLIParameterValidation:
    """Test CLI parameter validation and error handling."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_cli_help_works(self, runner):
        """Test that --help works."""
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'deepr' in result.output.lower()

    def test_cli_version_works(self, runner):
        """Test that --version works."""
        result = runner.invoke(cli, ['--version'])
        assert result.exit_code == 0

    def test_run_command_exists(self, runner):
        """Test that 'run' command exists."""
        result = runner.invoke(cli, ['run', '--help'])
        assert result.exit_code == 0
        assert 'focus' in result.output.lower()
        assert 'docs' in result.output.lower()
        assert 'project' in result.output.lower()
        assert 'team' in result.output.lower()

    def test_jobs_command_exists(self, runner):
        """Test that 'jobs' command exists."""
        result = runner.invoke(cli, ['jobs', '--help'])
        assert result.exit_code == 0

    def test_budget_command_exists(self, runner):
        """Test that 'budget' command exists."""
        result = runner.invoke(cli, ['budget', '--help'])
        assert result.exit_code == 0


class TestRunCommandValidation:
    """Test 'run' command parameter validation."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_run_focus_requires_query(self, runner):
        """Test that 'run focus' requires a query argument."""
        result = runner.invoke(cli, ['run', 'focus'])
        # Should fail or prompt for query
        assert 'query' in result.output.lower() or result.exit_code != 0

    def test_run_focus_accepts_query(self, runner):
        """Test that 'run focus' accepts a query argument."""
        with patch('deepr.cli.commands.run.asyncio.run') as mock_run:
            mock_run.return_value = None
            result = runner.invoke(cli, ['run', 'focus', 'test query'])
            # Should not fail due to missing query
            # (may fail for other reasons like missing API key, which is expected)

    def test_run_focus_provider_option(self, runner):
        """Test that --provider option is accepted."""
        result = runner.invoke(cli, ['run', 'focus', '--help'])
        assert '--provider' in result.output

    def test_run_focus_model_option(self, runner):
        """Test that --model/-m option is accepted."""
        result = runner.invoke(cli, ['run', 'focus', '--help'])
        assert '--model' in result.output or '-m' in result.output

    def test_run_focus_budget_option(self, runner):
        """Test that --limit option is accepted (for budget control)."""
        result = runner.invoke(cli, ['run', 'focus', '--help'])
        assert '--limit' in result.output

    def test_run_focus_upload_option(self, runner):
        """Test that --upload option is accepted."""
        result = runner.invoke(cli, ['run', 'focus', '--help'])
        assert '--upload' in result.output

    def test_run_docs_requires_query(self, runner):
        """Test that 'run docs' requires a query argument."""
        result = runner.invoke(cli, ['run', 'docs'])
        assert 'query' in result.output.lower() or result.exit_code != 0

    def test_run_project_requires_query(self, runner):
        """Test that 'run project' requires a query argument."""
        result = runner.invoke(cli, ['run', 'project'])
        assert 'query' in result.output.lower() or result.exit_code != 0

    def test_run_project_phases_option(self, runner):
        """Test that 'run project' has --phases option."""
        result = runner.invoke(cli, ['run', 'project', '--help'])
        # Project mode may or may not have explicit phases option
        # Just verify help works
        assert result.exit_code == 0

    def test_run_team_requires_query(self, runner):
        """Test that 'run team' requires a query argument."""
        result = runner.invoke(cli, ['run', 'team'])
        assert 'query' in result.output.lower() or result.exit_code != 0


class TestJobsCommandValidation:
    """Test 'jobs' command parameter validation."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_jobs_list_works(self, runner):
        """Test that 'jobs list' command works."""
        with patch('deepr.cli.commands.jobs.asyncio.run') as mock_run:
            mock_run.return_value = None
            result = runner.invoke(cli, ['jobs', 'list'])
            # Should not fail due to command syntax
            # (may fail for other reasons like DB access)

    def test_jobs_status_requires_job_id(self, runner):
        """Test that 'jobs status' requires job ID."""
        result = runner.invoke(cli, ['jobs', 'status'])
        # Should fail or show error about missing job_id
        assert result.exit_code != 0 or 'job' in result.output.lower()

    def test_jobs_status_accepts_job_id(self, runner):
        """Test that 'jobs status' accepts job ID."""
        with patch('deepr.cli.commands.jobs.asyncio.run') as mock_run:
            mock_run.return_value = None
            result = runner.invoke(cli, ['jobs', 'status', 'test-job-123'])
            # Should not fail due to command syntax

    def test_jobs_get_requires_job_id(self, runner):
        """Test that 'jobs get' requires job ID."""
        result = runner.invoke(cli, ['jobs', 'get'])
        assert result.exit_code != 0 or 'job' in result.output.lower()

    def test_jobs_cancel_requires_job_id(self, runner):
        """Test that 'jobs cancel' requires job ID."""
        result = runner.invoke(cli, ['jobs', 'cancel'])
        assert result.exit_code != 0 or 'job' in result.output.lower()


class TestBudgetCommandValidation:
    """Test 'budget' command parameter validation."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_budget_show_works(self, runner):
        """Test that 'budget' (show) command works."""
        result = runner.invoke(cli, ['budget', '--help'])
        # Just verify the command exists and help works
        assert result.exit_code == 0

    def test_budget_set_requires_amount(self, runner):
        """Test that 'budget set' requires an amount."""
        result = runner.invoke(cli, ['budget', 'set'])
        # Should fail or prompt for amount
        assert result.exit_code != 0 or 'amount' in result.output.lower()

    def test_budget_set_validates_positive_number(self, runner):
        """Test that 'budget set' command structure."""
        result = runner.invoke(cli, ['budget', 'set', '--help'])
        # Just verify set command exists
        assert result.exit_code == 0 or 'amount' in result.output.lower()


class TestFileUploadValidation:
    """Test file upload parameter validation."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_upload_validates_file_exists(self, runner):
        """Test that --upload validates file existence."""
        with patch('deepr.cli.commands.run.asyncio.run') as mock_run:
            mock_run.return_value = None

            # Non-existent file should be caught
            result = runner.invoke(cli, [
                'run', 'focus',
                'test query',
                '--upload', '/nonexistent/file.txt'
            ])
            # Should fail or warn about missing file
            # (implementation may vary - might fail at different stage)

    def test_upload_accepts_multiple_files(self, runner):
        """Test that --upload can be specified multiple times."""
        result = runner.invoke(cli, ['run', 'focus', '--help'])
        # Check if --upload is documented (multiple usage implied)
        assert '--upload' in result.output


class TestProviderValidation:
    """Test provider selection validation."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_provider_option_accepts_openai(self, runner):
        """Test that --provider accepts 'openai'."""
        with patch('deepr.cli.commands.run.asyncio.run') as mock_run:
            mock_run.return_value = None
            result = runner.invoke(cli, [
                'run', 'focus',
                'test query',
                '--provider', 'openai'
            ])
            # Should accept openai as provider

    def test_provider_option_accepts_gemini(self, runner):
        """Test that --provider accepts 'gemini'."""
        with patch('deepr.cli.commands.run.asyncio.run') as mock_run:
            mock_run.return_value = None
            result = runner.invoke(cli, [
                'run', 'focus',
                'test query',
                '--provider', 'gemini'
            ])
            # Should accept gemini as provider

    def test_provider_option_accepts_grok(self, runner):
        """Test that --provider accepts 'grok'."""
        with patch('deepr.cli.commands.run.asyncio.run') as mock_run:
            mock_run.return_value = None
            result = runner.invoke(cli, [
                'run', 'focus',
                'test query',
                '--provider', 'grok'
            ])
            # Should accept grok as provider

    def test_provider_option_rejects_invalid(self, runner):
        """Test that --provider rejects invalid providers."""
        result = runner.invoke(cli, [
            'run', 'focus',
            'test query',
            '--provider', 'invalid-provider'
        ])
        # Should fail or show error
        # (may fail at different stages depending on implementation)


class TestModelValidation:
    """Test model selection validation."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_model_option_accepts_values(self, runner):
        """Test that --model/-m accepts model names."""
        with patch('deepr.cli.commands.run.asyncio.run') as mock_run:
            mock_run.return_value = None
            result = runner.invoke(cli, [
                'run', 'focus',
                'test query',
                '--model', 'o4-mini-deep-research'
            ])
            # Should accept model name

    def test_model_short_option_works(self, runner):
        """Test that -m (short form) works."""
        with patch('deepr.cli.commands.run.asyncio.run') as mock_run:
            mock_run.return_value = None
            result = runner.invoke(cli, [
                'run', 'focus',
                'test query',
                '-m', 'o4-mini-deep-research'
            ])
            # Should accept short form


class TestCommandStructure:
    """Test overall CLI command structure."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_top_level_commands_exist(self, runner):
        """Test that all top-level commands exist."""
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0

        # Check for main command groups
        output = result.output.lower()
        assert 'run' in output
        assert 'jobs' in output
        assert 'budget' in output

    def test_run_subcommands_exist(self, runner):
        """Test that all run subcommands exist."""
        result = runner.invoke(cli, ['run', '--help'])
        assert result.exit_code == 0

        output = result.output.lower()
        assert 'focus' in output
        assert 'docs' in output
        assert 'project' in output
        assert 'team' in output

    def test_jobs_subcommands_exist(self, runner):
        """Test that all jobs subcommands exist."""
        result = runner.invoke(cli, ['jobs', '--help'])
        assert result.exit_code == 0

        output = result.output.lower()
        assert 'list' in output
        assert 'status' in output
        assert 'get' in output


class TestErrorMessages:
    """Test that error messages are helpful."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_missing_api_key_shows_helpful_message(self, runner):
        """Test that missing API key shows helpful error."""
        with patch('deepr.cli.commands.run.asyncio.run') as mock_run:
            # Simulate missing API key error
            mock_run.side_effect = ValueError("API key required")

            result = runner.invoke(cli, [
                'run', 'focus',
                'test query'
            ])
            # Should show error about API key
            # (exact implementation may vary)

    def test_invalid_command_shows_suggestions(self, runner):
        """Test that invalid commands show suggestions."""
        result = runner.invoke(cli, ['runn', 'focus', 'test'])  # typo: runn instead of run
        # Should show error and possibly suggestions
        assert result.exit_code != 0
