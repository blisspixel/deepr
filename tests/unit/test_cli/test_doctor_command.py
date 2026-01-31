"""Unit tests for doctor/diagnostics CLI command - no API calls.

Tests the diagnostic command that helps users troubleshoot configuration
and connectivity issues.
"""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.cli.main import cli


class TestDoctorCommandStructure:
    """Test doctor command structure and help text."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_doctor_command_exists(self, runner):
        """Test that 'doctor' command exists."""
        result = runner.invoke(cli, ['doctor', '--help'])
        assert result.exit_code == 0

    def test_doctor_help_describes_diagnostics(self, runner):
        """Test that doctor help describes diagnostic capabilities."""
        result = runner.invoke(cli, ['doctor', '--help'])
        output = result.output.lower()
        
        # Should mention diagnostics, configuration, or troubleshooting
        assert any(word in output for word in ['diagnos', 'config', 'check', 'troubleshoot', 'status'])


class TestDoctorChecks:
    """Test individual diagnostic checks."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_doctor_checks_api_keys(self, runner):
        """Test that doctor checks for API keys."""
        with patch.dict('os.environ', {}, clear=True):
            result = runner.invoke(cli, ['doctor'])
            output = result.output.lower()
            
            # Should mention API keys or configuration
            assert 'api' in output or 'key' in output or 'config' in output

    def test_doctor_checks_providers(self, runner):
        """Test that doctor checks provider configuration."""
        result = runner.invoke(cli, ['doctor'])
        output = result.output.lower()
        
        # Should mention providers
        assert 'provider' in output or 'openai' in output or 'gemini' in output

    def test_doctor_shows_pass_fail_status(self, runner):
        """Test that doctor shows pass/fail status for checks."""
        result = runner.invoke(cli, ['doctor'])
        output = result.output.lower()
        
        # Should show some kind of status indicators
        assert any(indicator in output for indicator in ['✓', '✗', 'pass', 'fail', 'ok', 'error', '✔', '✘', '[ok]', '[error]'])


class TestDoctorOutput:
    """Test doctor command output formatting."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_doctor_output_is_readable(self, runner):
        """Test that doctor output is human-readable."""
        result = runner.invoke(cli, ['doctor'])
        
        # Should have some structured output
        assert len(result.output) > 0
        # Should have multiple lines (multiple checks)
        assert '\n' in result.output

    def test_doctor_exits_cleanly(self, runner):
        """Test that doctor exits cleanly even with missing config."""
        with patch.dict('os.environ', {}, clear=True):
            result = runner.invoke(cli, ['doctor'])
            # Should not crash, even if checks fail
            assert result.exit_code in [0, 1]  # 0 = all pass, 1 = some fail


class TestDiagnosticsCommand:
    """Test 'diagnostics' command if it exists as alias."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_diagnostics_alias_or_separate(self, runner):
        """Test that diagnostics command exists (may be alias for doctor)."""
        result = runner.invoke(cli, ['diagnostics', '--help'])
        # May or may not exist as separate command
        # Just verify it doesn't crash unexpectedly


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
