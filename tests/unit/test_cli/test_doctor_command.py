"""Unit tests for doctor/diagnostics CLI command - no API calls.

Tests the diagnostic command that helps users troubleshoot configuration
and connectivity issues.
"""

import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.cli.main import cli

_PROVIDER_ENV_VARS = (
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
)


@pytest.fixture(autouse=True)
def _clear_provider_environment(monkeypatch):
    """Remove developer keys without clearing the runtime-root isolation."""
    for name in _PROVIDER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


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
        result = runner.invoke(cli, ["doctor", "--skip-connectivity"])
        output = result.output.lower()

        # Should mention API keys or configuration
        assert "api" in output or "key" in output or "config" in output

    def test_doctor_checks_providers(self, runner):
        """Test that doctor checks provider configuration."""
        result = runner.invoke(cli, ["doctor", "--skip-connectivity"])
        output = result.output.lower()

        # Should mention providers
        assert "provider" in output or "openai" in output or "gemini" in output

    def test_doctor_shows_pass_fail_status(self, runner):
        """Test that doctor shows pass/fail status for checks."""
        result = runner.invoke(cli, ["doctor", "--skip-connectivity"])
        output = result.output.lower()

        # Should show some kind of status indicators
        indicators = ["ok", "error", "pass", "fail", "[ok]", "[error]"]
        assert any(indicator in output for indicator in indicators)

    def test_storage_guidance_warns_against_concurrent_device_writers(self):
        from deepr.cli.commands.doctor import check_storage_locations

        expert_check = check_storage_locations()[0]

        assert any("one writer at a time" in detail.lower() for detail in expert_check.details)
        assert any("wait for sync" in detail.lower() for detail in expert_check.details)

    async def test_database_check_surfaces_stale_queue_candidates_read_only(self, tmp_path):
        from deepr.cli.commands.doctor import check_database
        from deepr.queue import ResearchJob, SQLiteQueue

        db_path = tmp_path / "queue.db"
        queue = SQLiteQueue(db_path)
        stale = ResearchJob(
            id="stale",
            prompt="inspect only",
            submitted_at=datetime.now(UTC) - timedelta(days=2),
            metadata={"cost_reservation_id": "reservation-1"},
        )
        await queue.enqueue(stale)
        before = db_path.read_bytes()

        checks = {check.name: check for check in await check_database({"queue_db_path": str(db_path)})}

        assert checks["Job Database"].passed
        assert checks["Queue Lifecycle"].severity == "warning"
        assert "1 stale queued candidate" in checks["Queue Lifecycle"].message
        assert db_path.read_bytes() == before


class TestDoctorOutput:
    """Test doctor command output formatting."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_doctor_output_is_readable(self, runner):
        """Test that doctor output is human-readable."""
        result = runner.invoke(cli, ["doctor", "--skip-connectivity"])

        # Should have some structured output
        assert len(result.output) > 0
        # Should have multiple lines (multiple checks)
        assert "\n" in result.output

    def test_doctor_exits_cleanly(self, runner):
        """Test that doctor exits cleanly even with missing config."""
        result = runner.invoke(cli, ["doctor", "--skip-connectivity"])
        assert result.exit_code == 0

    def test_doctor_returns_nonzero_when_a_check_errors(self, runner, monkeypatch):
        from deepr.cli.commands import doctor as doctor_module

        async def failing_check():
            return [doctor_module.DiagnosticCheck("Broken filesystem", "Filesystem")]

        monkeypatch.setattr(doctor_module, "check_filesystem", failing_check)
        result = runner.invoke(cli, ["doctor", "--skip-connectivity"])

        assert result.exit_code == 1
        assert "Diagnostics found one or more errors" in result.output

    def test_configuration_failure_is_redacted_and_nonzero(self, runner, monkeypatch):
        from deepr.cli.commands import doctor as doctor_module

        secret = "configuration-secret-should-not-render"

        def fail_load():
            raise RuntimeError(secret)

        monkeypatch.setattr(doctor_module, "load_config", fail_load)
        result = runner.invoke(cli, ["doctor", "--skip-connectivity"])

        assert result.exit_code == 1
        assert "Could not load configuration" in result.output
        assert secret not in result.output

    def test_skip_connectivity_never_constructs_provider_clients(self, runner, monkeypatch):
        class ForbiddenClient:
            def __init__(self, **_):
                raise AssertionError("provider client constructed in offline mode")

        fake_openai = types.ModuleType("openai")
        fake_openai.AsyncOpenAI = ForbiddenClient
        fake_openai.AsyncAzureOpenAI = ForbiddenClient
        fake_genai = types.ModuleType("google.genai")
        fake_genai.Client = ForbiddenClient
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai
        monkeypatch.setitem(sys.modules, "openai", fake_openai)
        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
        for name in _PROVIDER_ENV_VARS:
            monkeypatch.setenv(name, "configured-test-value")

        result = runner.invoke(cli, ["doctor", "--skip-connectivity"])

        assert result.exit_code == 0
        assert "provider connectivity checks are skipped" in result.output
        assert "provider client constructed" not in result.output


class TestDoctorNextStep:
    """Test the closing next-step guidance (complements `deepr init`)."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_no_keys_points_to_capacity_inventory(self, capsys):
        from deepr.cli.commands.doctor import DiagnosticCheck, print_next_step

        metered = DiagnosticCheck("Metered API capacity", "API Keys")
        metered.failure_severity = "info"

        print_next_step([metered])

        output = capsys.readouterr().out
        assert "Next: deepr capacity" in output
        assert "capacity next" not in output
        assert "No metered API keys" in output

    def test_configured_key_points_to_research_preview(self, capsys):
        from deepr.cli.commands.doctor import DiagnosticCheck, print_next_step

        metered = DiagnosticCheck("Metered API capacity", "API Keys")
        metered.passed = True

        print_next_step([metered])

        output = capsys.readouterr().out
        assert "research" in output.lower()
        assert "--preview" in output
        assert "deepr init" not in output

    def test_error_blocks_success_and_new_work(self, capsys):
        from deepr.cli.commands.doctor import DiagnosticCheck, print_next_step

        configured = DiagnosticCheck("OpenAI API Key", "API Keys")
        configured.passed = True
        broken = DiagnosticCheck("OpenAI API Connection", "Connectivity")

        print_next_step([configured, broken])

        output = capsys.readouterr().out
        assert "Resolve the ERROR" in output
        assert "Setup looks good" not in output
        assert "research" not in output

    def test_stale_queue_warning_precedes_new_work(self, capsys):
        from deepr.cli.commands.doctor import DiagnosticCheck, print_next_step

        configured = DiagnosticCheck("OpenAI API Key", "API Keys")
        configured.passed = True
        stale = DiagnosticCheck("Queue Lifecycle", "Database")
        stale.failure_severity = "warning"

        print_next_step([configured, stale])

        output = capsys.readouterr().out
        assert "jobs list --status queued" in output
        assert "costs doctor" in output
        assert "research" not in output


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
        assert by_name["Metered API capacity"].severity == "info"
        assert "local" in by_name["Metered API capacity"].message.lower()

    async def test_one_provider_clears_the_summary_error(self, monkeypatch):
        from deepr.cli.commands.doctor import check_api_keys

        for v in ("OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY"):
            monkeypatch.delenv(v, raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "real-gemini-key-123")
        by_name = {c.name: c for c in await check_api_keys({})}
        assert by_name["Gemini API Key"].passed
        assert by_name["Metered API capacity"].severity == "ok"
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

    async def test_provider_exception_content_is_not_exposed(self, monkeypatch):
        from deepr.cli.commands.doctor import check_provider_connectivity

        secret = "provider-response-secret-should-not-render"

        class FailingModels:
            async def list(self):
                raise RuntimeError(secret)

        class FailingClient:
            models = FailingModels()

        class FailingGeminiModels:
            def list(self):
                raise RuntimeError(secret)

        class FailingGeminiClient:
            models = FailingGeminiModels()

        fake_openai = types.ModuleType("openai")
        fake_openai.AsyncOpenAI = lambda **_: FailingClient()
        fake_openai.AsyncAzureOpenAI = lambda **_: FailingClient()
        fake_genai = types.ModuleType("google.genai")
        fake_genai.Client = lambda **_: FailingGeminiClient()
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai
        monkeypatch.setitem(sys.modules, "openai", fake_openai)
        monkeypatch.setitem(sys.modules, "google", fake_google)
        monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
        for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY"):
            monkeypatch.setenv(name, "configured-test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "configured-test-key")
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)

        checks = await check_provider_connectivity({})
        rendered = " ".join(check.message + " " + " ".join(check.details) for check in checks)

        assert rendered.count("Connection check failed") == 3
        assert "Anthropic API Connectivity" in " ".join(check.name for check in checks)
        assert "not checked" in rendered.lower()
        assert secret not in rendered


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
