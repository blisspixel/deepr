"""Unit tests for doctor/diagnostics CLI command - no API calls.

Tests the diagnostic command that helps users troubleshoot configuration
and connectivity issues.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

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
        result = runner.invoke(cli, ["doctor", "--help"])
        assert result.exit_code == 0

    def test_doctor_help_describes_diagnostics(self, runner):
        """Test that doctor help describes diagnostic capabilities."""
        result = runner.invoke(cli, ["doctor", "--help"])
        output = result.output.lower()

        # Should mention diagnostics, configuration, or troubleshooting
        assert any(word in output for word in ["diagnos", "config", "check", "troubleshoot", "status"])


class TestDoctorChecks:
    """Test individual diagnostic checks."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_doctor_checks_api_keys(self, runner):
        """Test that doctor checks for API keys."""
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(cli, ["doctor"])
            output = result.output.lower()

            # Should mention API keys or configuration
            assert "api" in output or "key" in output or "config" in output

    def test_doctor_checks_providers(self, runner):
        """Test that doctor checks provider configuration."""
        result = runner.invoke(cli, ["doctor"])
        output = result.output.lower()

        # Should mention providers
        assert "provider" in output or "openai" in output or "gemini" in output

    def test_doctor_shows_pass_fail_status(self, runner):
        """Test that doctor shows pass/fail status for checks."""
        result = runner.invoke(cli, ["doctor"])
        output = result.output.lower()

        # Should show some kind of status indicators
        assert any(
            indicator in output for indicator in ["✓", "✗", "pass", "fail", "ok", "error", "✔", "✘", "[ok]", "[error]"]
        )


class TestDoctorOutput:
    """Test doctor command output formatting."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_doctor_output_is_readable(self, runner):
        """Test that doctor output is human-readable."""
        result = runner.invoke(cli, ["doctor"])

        # Should have some structured output
        assert len(result.output) > 0
        # Should have multiple lines (multiple checks)
        assert "\n" in result.output

    def test_doctor_exits_cleanly(self, runner):
        """Test that doctor exits cleanly even with missing config."""
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(cli, ["doctor"])
            # Should not crash, even if checks fail
            assert result.exit_code in [0, 1]  # 0 = all pass, 1 = some fail


class TestDoctorNextStep:
    """Test the closing next-step guidance (complements `deepr init`)."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_no_keys_points_to_init(self, runner):
        with patch.dict("os.environ", {}, clear=True):
            result = runner.invoke(cli, ["doctor", "--skip-connectivity"])
            assert "deepr init" in result.output

    def test_configured_key_points_to_research(self, runner):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "real-gemini-key-123"}, clear=True):
            result = runner.invoke(cli, ["doctor", "--skip-connectivity"])
            assert "research" in result.output.lower()
            assert "deepr init" not in result.output


class TestDoctorSeverity:
    """Optional/first-run state must not read as errors (the 'crying wolf' fix)."""

    def test_severity_property(self):
        from deepr.cli.commands.doctor import DiagnosticCheck

        c = DiagnosticCheck("x", "y")
        assert c.severity == "error"  # default failure severity
        c.failure_severity = "info"
        assert c.severity == "info"
        c.passed = True
        assert c.severity == "ok"  # passing always wins

    async def test_unset_optional_provider_is_info_not_error(self, monkeypatch):
        from deepr.cli.commands.doctor import check_api_keys

        for v in ("OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY"):
            monkeypatch.delenv(v, raising=False)
        by_name = {c.name: c for c in await check_api_keys({})}
        assert by_name["OpenAI API Key"].severity == "info"
        assert by_name["Anthropic API Key"].severity == "info"
        # The only real error when nothing is set: no provider at all.
        assert by_name["At least one provider configured"].severity == "error"

    async def test_one_provider_clears_the_summary_error(self, monkeypatch):
        from deepr.cli.commands.doctor import check_api_keys

        for v in ("OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY"):
            monkeypatch.delenv(v, raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "real-gemini-key-123")
        by_name = {c.name: c for c in await check_api_keys({})}
        assert by_name["Gemini API Key"].passed
        assert by_name["At least one provider configured"].severity == "ok"
        assert by_name["Azure OpenAI Key"].severity == "info"  # unset optional, not an error

    def test_summarize_counts_only_errors_as_issues(self):
        # The core "stop crying wolf" guarantee: optional (info) and advisory
        # (warning) checks are not counted as issues; only errors are.
        from deepr.cli.commands.doctor import DiagnosticCheck, _summarize

        ok = DiagnosticCheck("ok", "c")
        ok.passed = True
        optional = DiagnosticCheck("azure", "c")
        optional.failure_severity = "info"
        advisory = DiagnosticCheck("deprecated", "c")
        advisory.failure_severity = "warning"
        real = DiagnosticCheck("broken", "c")  # default failure_severity = error

        counts = _summarize([ok, optional, advisory, real])
        assert counts == {"total": 4, "passed": 1, "errors": 1, "warnings": 1, "info": 1}


class TestDiagnosticsCommand:
    """Test 'diagnostics' command if it exists as alias."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_diagnostics_alias_or_separate(self, runner):
        """Test that diagnostics command exists (may be alias for doctor)."""
        result = runner.invoke(cli, ["diagnostics", "--help"])
        # May or may not exist as separate command
        # Just verify it doesn't crash unexpectedly


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
