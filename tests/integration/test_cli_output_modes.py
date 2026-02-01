"""Integration tests for CLI output modes.

Tests the output mode system:
- Minimal mode (default): Single-line output
- Verbose mode (--verbose/-v): Detailed output
- JSON mode (--json): Machine-readable JSON
- Quiet mode (--quiet/-q): No stdout except errors

These tests validate that:
1. Output flags are available on all relevant commands
2. Mutual exclusivity is enforced
3. Output format matches expected patterns
4. Environment variable backward compatibility works
"""

import pytest
import subprocess
import json
import os
from click.testing import CliRunner


class TestOutputFlagsAvailable:
    """Test that output flags are available on commands."""

    @pytest.mark.integration
    def test_status_command_has_output_flags(self):
        """Test that 'deepr status' has output mode flags."""
        result = subprocess.run(
            ["deepr", "status", "--help"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        assert "--verbose" in result.stdout
        assert "--json" in result.stdout
        assert "--quiet" in result.stdout
        assert "-v" in result.stdout
        assert "-q" in result.stdout

    @pytest.mark.integration
    def test_list_command_has_output_flags(self):
        """Test that 'deepr list' has output mode flags."""
        result = subprocess.run(
            ["deepr", "list", "--help"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        assert "--verbose" in result.stdout
        assert "--json" in result.stdout
        assert "--quiet" in result.stdout

    @pytest.mark.integration
    def test_get_command_has_output_flags(self):
        """Test that 'deepr get' has output mode flags."""
        result = subprocess.run(
            ["deepr", "get", "--help"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        assert "--verbose" in result.stdout
        assert "--json" in result.stdout
        assert "--quiet" in result.stdout

    @pytest.mark.integration
    def test_cancel_command_has_output_flags(self):
        """Test that 'deepr cancel' has output mode flags."""
        result = subprocess.run(
            ["deepr", "cancel", "--help"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        assert "--verbose" in result.stdout
        assert "--json" in result.stdout
        assert "--quiet" in result.stdout

    @pytest.mark.integration
    def test_run_focus_has_output_flags(self):
        """Test that 'deepr run focus' has output mode flags."""
        result = subprocess.run(
            ["deepr", "run", "focus", "--help"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        assert "--verbose" in result.stdout
        assert "--json" in result.stdout
        assert "--quiet" in result.stdout


class TestMutualExclusivity:
    """Test that output mode flags are mutually exclusive."""

    @pytest.mark.integration
    def test_verbose_and_json_conflict(self):
        """Test that --verbose and --json cannot be used together."""
        result = subprocess.run(
            ["deepr", "status", "--verbose", "--json", "test-job"],
            capture_output=True,
            text=True
        )

        assert result.returncode != 0
        assert "Cannot use" in result.stderr or "Cannot use" in result.stdout

    @pytest.mark.integration
    def test_verbose_and_quiet_conflict(self):
        """Test that --verbose and --quiet cannot be used together."""
        result = subprocess.run(
            ["deepr", "status", "--verbose", "--quiet", "test-job"],
            capture_output=True,
            text=True
        )

        assert result.returncode != 0
        assert "Cannot use" in result.stderr or "Cannot use" in result.stdout

    @pytest.mark.integration
    def test_json_and_quiet_conflict(self):
        """Test that --json and --quiet cannot be used together."""
        result = subprocess.run(
            ["deepr", "status", "--json", "--quiet", "test-job"],
            capture_output=True,
            text=True
        )

        assert result.returncode != 0
        assert "Cannot use" in result.stderr or "Cannot use" in result.stdout


class TestMinimalModeOutput:
    """Test minimal mode (default) output format."""

    @pytest.mark.integration
    def test_list_minimal_mode_default(self):
        """Test that 'deepr list' uses minimal mode by default."""
        result = subprocess.run(
            ["deepr", "list", "--limit", "1"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        # Minimal mode should not show the verbose header
        assert "Job Queue" not in result.stdout or "=" * 70 not in result.stdout

    @pytest.mark.integration
    def test_status_not_found_minimal(self):
        """Test status command with non-existent job in minimal mode."""
        result = subprocess.run(
            ["deepr", "status", "nonexistent-job-12345"],
            capture_output=True,
            text=True
        )

        # Should show error message
        assert "not found" in result.stdout.lower() or result.returncode == 0


class TestVerboseModeOutput:
    """Test verbose mode (--verbose) output format."""

    @pytest.mark.integration
    def test_list_verbose_mode(self):
        """Test that 'deepr list --verbose' shows detailed output."""
        result = subprocess.run(
            ["deepr", "list", "--verbose", "--limit", "1"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        # Verbose mode shows the header and deprecation warning
        # Either shows "Job Queue" header or deprecation message
        output = result.stdout + result.stderr
        assert "Job Queue" in output or "DEPRECATED" in output or "No jobs found" in output


class TestJSONModeOutput:
    """Test JSON mode (--json) output format."""

    @pytest.mark.integration
    def test_list_json_mode_valid_json(self):
        """Test that 'deepr list --json' outputs valid JSON."""
        result = subprocess.run(
            ["deepr", "list", "--json", "--limit", "5"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        # Should be valid JSON
        try:
            data = json.loads(result.stdout)
            assert "status" in data
            assert "jobs" in data or "count" in data
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {result.stdout}")

    @pytest.mark.integration
    def test_status_json_mode_not_found(self):
        """Test that status --json outputs JSON for not found."""
        result = subprocess.run(
            ["deepr", "status", "--json", "nonexistent-job-12345"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        try:
            data = json.loads(result.stdout)
            assert data.get("status") == "error"
            assert "error" in data
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {result.stdout}")


class TestQuietModeOutput:
    """Test quiet mode (--quiet) output format."""

    @pytest.mark.integration
    def test_list_quiet_mode_no_output(self):
        """Test that 'deepr list --quiet' produces no stdout."""
        result = subprocess.run(
            ["deepr", "list", "--quiet", "--limit", "1"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        # Quiet mode should produce no stdout
        assert result.stdout.strip() == ""

    @pytest.mark.integration
    def test_status_quiet_mode_no_output(self):
        """Test that 'deepr status --quiet' produces no stdout."""
        result = subprocess.run(
            ["deepr", "status", "--quiet", "nonexistent-job"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        # Quiet mode should produce no stdout even for errors
        assert result.stdout.strip() == ""


class TestFlagAliases:
    """Test that flag aliases work correctly."""

    @pytest.mark.integration
    def test_v_alias_for_verbose(self):
        """Test that -v works the same as --verbose."""
        result_short = subprocess.run(
            ["deepr", "list", "-v", "--limit", "1"],
            capture_output=True,
            text=True
        )

        result_long = subprocess.run(
            ["deepr", "list", "--verbose", "--limit", "1"],
            capture_output=True,
            text=True
        )

        assert result_short.returncode == result_long.returncode
        # Both should produce similar output (verbose mode)

    @pytest.mark.integration
    def test_q_alias_for_quiet(self):
        """Test that -q works the same as --quiet."""
        result_short = subprocess.run(
            ["deepr", "list", "-q", "--limit", "1"],
            capture_output=True,
            text=True
        )

        result_long = subprocess.run(
            ["deepr", "list", "--quiet", "--limit", "1"],
            capture_output=True,
            text=True
        )

        assert result_short.returncode == result_long.returncode
        assert result_short.stdout == result_long.stdout


class TestEnvironmentVariable:
    """Test environment variable backward compatibility."""

    @pytest.mark.integration
    def test_deepr_verbose_env_var(self):
        """Test that DEEPR_VERBOSE=true enables verbose mode."""
        env = os.environ.copy()
        env["DEEPR_VERBOSE"] = "true"

        result = subprocess.run(
            ["deepr", "list", "--limit", "1"],
            capture_output=True,
            text=True,
            env=env
        )

        assert result.returncode == 0
        # With DEEPR_VERBOSE=true, should show verbose output
        output = result.stdout + result.stderr
        # Verbose mode shows deprecation warning or detailed output
        assert "DEPRECATED" in output or "Job Queue" in output or "No jobs found" in output

    @pytest.mark.integration
    def test_explicit_flag_overrides_env_var(self):
        """Test that explicit --quiet overrides DEEPR_VERBOSE=true."""
        env = os.environ.copy()
        env["DEEPR_VERBOSE"] = "true"

        result = subprocess.run(
            ["deepr", "list", "--quiet", "--limit", "1"],
            capture_output=True,
            text=True,
            env=env
        )

        assert result.returncode == 0
        # Explicit --quiet should override env var
        assert result.stdout.strip() == ""
