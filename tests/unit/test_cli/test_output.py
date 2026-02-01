"""Property-based tests for CLI output module.

Feature: minimal-default-output
Tests output mode handling, duration formatting, cost formatting, and output rendering.
"""

import json
import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck
import hypothesis

from deepr.cli.output import (
    OutputMode,
    OutputContext,
    OutputModeConflictError,
    OperationResult,
    format_duration,
    parse_duration,
    format_cost,
    parse_cost,
)


class TestOutputModeMutualExclusivity:
    """Feature: minimal-default-output, Property 13: Output mode mutual exclusivity
    
    For any combination of two or more output flags (--verbose, --json, --quiet),
    the CLI SHALL reject the command with an error message indicating the
    conflicting flags and exit with non-zero status.
    
    Validates: Requirements 5.1, 5.2, 5.3, 5.4
    """
    
    @given(
        verbose=st.booleans(),
        json_output=st.booleans(),
        quiet=st.booleans()
    )
    @settings(max_examples=100)
    def test_mutual_exclusivity_property(self, verbose: bool, json_output: bool, quiet: bool):
        """For any flag combination, at most one flag can be True without error."""
        flags_set = sum([verbose, json_output, quiet])
        
        if flags_set > 1:
            # Should raise error when multiple flags are set
            with pytest.raises(OutputModeConflictError) as exc_info:
                OutputContext.from_flags(verbose=verbose, json_output=json_output, quiet=quiet)
            
            # Error message should mention the conflicting flags
            error_msg = str(exc_info.value)
            assert "Cannot use" in error_msg
            assert "Choose one output mode" in error_msg
        else:
            # Should succeed when 0 or 1 flag is set
            context = OutputContext.from_flags(verbose=verbose, json_output=json_output, quiet=quiet)
            assert isinstance(context, OutputContext)
            assert isinstance(context.mode, OutputMode)
    
    def test_verbose_and_quiet_conflict(self):
        """--verbose and --quiet cannot be used together."""
        with pytest.raises(OutputModeConflictError) as exc_info:
            OutputContext.from_flags(verbose=True, json_output=False, quiet=True)
        
        assert "--verbose" in str(exc_info.value)
        assert "--quiet" in str(exc_info.value)
    
    def test_json_and_verbose_conflict(self):
        """--json and --verbose cannot be used together."""
        with pytest.raises(OutputModeConflictError) as exc_info:
            OutputContext.from_flags(verbose=True, json_output=True, quiet=False)
        
        assert "--verbose" in str(exc_info.value)
        assert "--json" in str(exc_info.value)
    
    def test_json_and_quiet_conflict(self):
        """--json and --quiet cannot be used together."""
        with pytest.raises(OutputModeConflictError) as exc_info:
            OutputContext.from_flags(verbose=False, json_output=True, quiet=True)
        
        assert "--json" in str(exc_info.value)
        assert "--quiet" in str(exc_info.value)
    
    def test_all_three_flags_conflict(self):
        """All three flags cannot be used together."""
        with pytest.raises(OutputModeConflictError):
            OutputContext.from_flags(verbose=True, json_output=True, quiet=True)
    
    def test_no_flags_defaults_to_minimal(self):
        """No flags defaults to MINIMAL mode."""
        context = OutputContext.from_flags(verbose=False, json_output=False, quiet=False)
        assert context.mode == OutputMode.MINIMAL
    
    def test_verbose_flag_sets_verbose_mode(self):
        """--verbose flag sets VERBOSE mode."""
        context = OutputContext.from_flags(verbose=True, json_output=False, quiet=False)
        assert context.mode == OutputMode.VERBOSE
    
    def test_json_flag_sets_json_mode(self):
        """--json flag sets JSON mode."""
        context = OutputContext.from_flags(verbose=False, json_output=True, quiet=False)
        assert context.mode == OutputMode.JSON
    
    def test_quiet_flag_sets_quiet_mode(self):
        """--quiet flag sets QUIET mode."""
        context = OutputContext.from_flags(verbose=False, json_output=False, quiet=True)
        assert context.mode == OutputMode.QUIET
    
    def test_env_var_backward_compatibility(self, monkeypatch):
        """DEEPR_VERBOSE=true defaults to verbose mode when no flags provided."""
        monkeypatch.setenv("DEEPR_VERBOSE", "true")
        context = OutputContext.from_flags(verbose=False, json_output=False, quiet=False)
        assert context.mode == OutputMode.VERBOSE
    
    def test_explicit_flag_overrides_env_var(self, monkeypatch):
        """Explicit flags override DEEPR_VERBOSE environment variable."""
        monkeypatch.setenv("DEEPR_VERBOSE", "true")
        
        # --quiet should override env var
        context = OutputContext.from_flags(verbose=False, json_output=False, quiet=True)
        assert context.mode == OutputMode.QUIET
        
        # --json should override env var
        context = OutputContext.from_flags(verbose=False, json_output=True, quiet=False)
        assert context.mode == OutputMode.JSON



class TestOperationResult:
    """Tests for OperationResult dataclass and JSON serialization.
    
    Validates: Requirements 3.2, 3.3
    """
    
    def test_success_result_to_json(self):
        """Successful result serializes with all required fields."""
        result = OperationResult(
            success=True,
            duration_seconds=135.5,
            cost_usd=0.42,
            report_path="reports/abc123/",
            job_id="research-abc123def456"
        )
        
        json_str = result.to_json()
        data = json.loads(json_str)
        
        assert data["status"] == "success"
        assert data["duration_seconds"] == 135.5
        assert data["cost_usd"] == 0.42
        assert data["report_path"] == "reports/abc123/"
        assert data["job_id"] == "research-abc123def456"
    
    def test_error_result_to_json(self):
        """Failed result serializes with error fields."""
        result = OperationResult(
            success=False,
            duration_seconds=10.0,
            cost_usd=0.0,
            error="API rate limit exceeded",
            error_code="RATE_LIMIT"
        )
        
        json_str = result.to_json()
        data = json.loads(json_str)
        
        assert data["status"] == "error"
        assert data["error"] == "API rate limit exceeded"
        assert data["error_code"] == "RATE_LIMIT"
        # Success fields should not be present
        assert "duration_seconds" not in data
        assert "cost_usd" not in data
    
    def test_success_result_with_missing_optional_fields(self):
        """Success result handles missing optional fields."""
        result = OperationResult(
            success=True,
            duration_seconds=10.0,
            cost_usd=0.0
        )
        
        json_str = result.to_json()
        data = json.loads(json_str)
        
        assert data["status"] == "success"
        assert data["report_path"] == ""
        assert data["job_id"] == ""
    
    def test_error_result_with_missing_error_details(self):
        """Error result handles missing error details."""
        result = OperationResult(
            success=False,
            duration_seconds=5.0,
            cost_usd=0.0
        )
        
        json_str = result.to_json()
        data = json.loads(json_str)
        
        assert data["status"] == "error"
        assert data["error"] == "Unknown error"
        assert data["error_code"] == "UNKNOWN"



class TestDurationFormattingCorrectness:
    """Feature: minimal-default-output, Property 1: Duration formatting correctness
    
    For any duration in seconds (0 to 86400), the formatted output SHALL:
    - Use {seconds}s format for durations that round to < 60 seconds
    - Use {minutes}m {seconds}s format for durations that round to 60-3599 seconds
    - Use {hours}h {minutes}m format for durations that round to >= 3600 seconds
    - Round fractional seconds to whole numbers
    
    Note: The format is determined by the ROUNDED value, not the input value.
    For example, 59.5 rounds to 60, so it uses minutes format.
    
    Validates: Requirements 1.2, 6.1, 6.2, 6.3, 6.4
    """
    
    @given(st.floats(min_value=0, max_value=59.49, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_seconds_only_format(self, seconds: float):
        """For any duration that rounds to < 60s, format is {seconds}s."""
        assume(round(seconds) < 60)  # Ensure rounded value is in range
        result = format_duration(seconds)
        
        # Should end with 's'
        assert result.endswith("s")
        # Should not contain 'm' or 'h'
        assert "m" not in result
        assert "h" not in result
        # Should be a valid integer followed by 's'
        assert result[:-1].isdigit()
    
    @given(st.floats(min_value=60, max_value=3599.49, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_minutes_seconds_format(self, seconds: float):
        """For any duration that rounds to 60-3599s, format is {minutes}m {seconds}s."""
        rounded = round(seconds)
        assume(60 <= rounded < 3600)  # Ensure rounded value is in range
        result = format_duration(seconds)
        
        # Should contain 'm' and 's'
        assert "m" in result
        assert "s" in result
        # Should not contain 'h'
        assert "h" not in result
        # Should match pattern like "2m 15s"
        parts = result.split("m ")
        assert len(parts) == 2
        assert parts[0].isdigit()
        assert parts[1].endswith("s")
        assert parts[1][:-1].isdigit()
    
    @given(st.floats(min_value=3600, max_value=86400, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_hours_minutes_format(self, seconds: float):
        """For any duration that rounds to >= 3600s, format is {hours}h {minutes}m."""
        assume(round(seconds) >= 3600)  # Ensure rounded value is in range
        result = format_duration(seconds)
        
        # Should contain 'h' and 'm'
        assert "h" in result
        assert "m" in result
        # Should not contain 's' (hours format omits seconds)
        assert "s" not in result
        # Should match pattern like "1h 30m"
        parts = result.split("h ")
        assert len(parts) == 2
        assert parts[0].isdigit()
        assert parts[1].endswith("m")
        assert parts[1][:-1].isdigit()
    
    def test_rounding_to_whole_seconds(self):
        """Fractional seconds are rounded to whole numbers."""
        # 45.4 should round to 45
        assert format_duration(45.4) == "45s"
        # 45.6 should round to 46
        assert format_duration(45.6) == "46s"
        # 45.5 should round to 46 (Python's round-half-to-even)
        assert format_duration(45.5) == "46s"
    
    def test_boundary_values(self):
        """Test boundary values between format ranges."""
        # Just under 60 seconds
        assert format_duration(59) == "59s"
        # Exactly 60 seconds
        assert format_duration(60) == "1m 0s"
        # Just under 1 hour
        assert format_duration(3599) == "59m 59s"
        # Exactly 1 hour
        assert format_duration(3600) == "1h 0m"
    
    def test_zero_duration(self):
        """Zero duration formats correctly."""
        assert format_duration(0) == "0s"


class TestDurationRoundTrip:
    """Feature: minimal-default-output, Property 2: Duration formatting round trip
    
    For any duration in seconds (0 to 86400), formatting then parsing the duration
    SHALL produce a value within acceptable tolerance of the original:
    - For seconds/minutes format: within 1 second (due to rounding)
    - For hours format: within 60 seconds (hours format omits seconds)
    
    Validates: Requirements 6.1, 6.2, 6.3, 6.4
    """
    
    @given(st.floats(min_value=0, max_value=3599.49, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_round_trip_seconds_minutes_format(self, seconds: float):
        """For seconds/minutes format, round trip is within 1 second."""
        assume(round(seconds) < 3600)  # Stay in seconds/minutes range
        formatted = format_duration(seconds)
        parsed = parse_duration(formatted)
        
        # Should be within 1 second of the rounded original
        expected = round(seconds)
        assert abs(parsed - expected) <= 1
    
    @given(st.floats(min_value=3600, max_value=86400, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_round_trip_hours_format(self, seconds: float):
        """For hours format, round trip is within 60 seconds (seconds are omitted)."""
        assume(round(seconds) >= 3600)  # Stay in hours range
        formatted = format_duration(seconds)
        parsed = parse_duration(formatted)
        
        # Hours format omits seconds, so tolerance is up to 60 seconds
        expected = round(seconds)
        assert abs(parsed - expected) <= 60
    
    @given(st.integers(min_value=0, max_value=3599))
    @settings(max_examples=100)
    def test_round_trip_exact_for_integers_under_hour(self, seconds: int):
        """For integer seconds under 1 hour, round trip is exact."""
        formatted = format_duration(float(seconds))
        parsed = parse_duration(formatted)
        
        # For integers in seconds/minutes range, should be exact
        assert parsed == seconds
    
    def test_parse_various_formats(self):
        """parse_duration handles all format variations."""
        assert parse_duration("45s") == 45
        assert parse_duration("2m 15s") == 135
        assert parse_duration("1h 30m") == 5400
        assert parse_duration("0s") == 0



class TestCostFormattingCorrectness:
    """Feature: minimal-default-output, Property 3: Cost formatting correctness
    
    For any cost in USD (0.00 to 10000.00), the formatted output SHALL:
    - Start with a dollar sign prefix
    - Have exactly two decimal places
    - Use period as decimal separator regardless of locale
    
    Validates: Requirements 1.3, 7.1, 7.4
    """
    
    @given(st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_dollar_sign_prefix(self, cost: float):
        """For any cost, formatted output starts with dollar sign."""
        result = format_cost(cost)
        assert result.startswith("$")
    
    @given(st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_exactly_two_decimal_places(self, cost: float):
        """For any cost, formatted output has exactly two decimal places."""
        result = format_cost(cost)
        
        # Remove dollar sign
        numeric_part = result[1:]
        
        # Should have exactly one decimal point
        assert numeric_part.count(".") == 1
        
        # Should have exactly 2 digits after decimal
        decimal_part = numeric_part.split(".")[1]
        assert len(decimal_part) == 2
        assert decimal_part.isdigit()
    
    @given(st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_period_decimal_separator(self, cost: float):
        """For any cost, period is used as decimal separator (not comma)."""
        result = format_cost(cost)
        
        # Should contain period
        assert "." in result
        # Should not contain comma (some locales use comma as decimal separator)
        assert "," not in result
    
    def test_zero_cost(self):
        """Zero cost formats as $0.00."""
        assert format_cost(0) == "$0.00"
        assert format_cost(0.0) == "$0.00"
    
    def test_sub_cent_cost(self):
        """Sub-cent costs round appropriately."""
        assert format_cost(0.001) == "$0.00"
        assert format_cost(0.004) == "$0.00"
        # Note: 0.005 may round to $0.01 due to floating point representation
        # The exact behavior depends on the floating point representation
        assert format_cost(0.006) == "$0.01"
        assert format_cost(0.009) == "$0.01"
    
    def test_typical_costs(self):
        """Typical cost values format correctly."""
        assert format_cost(0.42) == "$0.42"
        assert format_cost(1.50) == "$1.50"
        assert format_cost(10.00) == "$10.00"
        assert format_cost(123.45) == "$123.45"


class TestCostRoundTrip:
    """Feature: minimal-default-output, Property 4: Cost formatting round trip
    
    For any cost in USD (0.00 to 10000.00), formatting then parsing the cost
    SHALL produce a value within $0.01 of the original (due to rounding to
    two decimal places).
    
    Validates: Requirements 7.1, 7.2, 7.3, 7.4
    """
    
    @given(st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_round_trip_within_tolerance(self, cost: float):
        """Format then parse produces value within $0.01 of original."""
        formatted = format_cost(cost)
        parsed = parse_cost(formatted)
        
        # Should be within $0.01 of the original (due to 2 decimal place rounding)
        assert abs(parsed - cost) <= 0.01
    
    @given(st.integers(min_value=0, max_value=1000000))
    @settings(max_examples=100)
    def test_round_trip_exact_for_cents(self, cents: int):
        """For exact cent values, round trip is exact."""
        cost = cents / 100.0
        formatted = format_cost(cost)
        parsed = parse_cost(formatted)
        
        # For exact cent values, should be exact
        assert abs(parsed - cost) < 0.001
    
    def test_parse_various_formats(self):
        """parse_cost handles various formats."""
        assert parse_cost("$0.42") == 0.42
        assert parse_cost("$10.00") == 10.00
        assert parse_cost("$0.00") == 0.00
        assert parse_cost("$123.45") == 123.45


# Import OutputFormatter for testing
from deepr.cli.output import OutputFormatter
from io import StringIO
from unittest.mock import patch, MagicMock
import re


class TestOutputFormatterModeAware:
    """Tests for OutputFormatter mode-aware rendering.
    
    Task 5.1: Create OutputFormatter class with mode-aware rendering
    Validates: Requirements 1.4, 2.1, 2.2, 2.3
    """
    
    def test_formatter_accepts_output_context(self):
        """OutputFormatter initializes with OutputContext."""
        context = OutputContext(mode=OutputMode.MINIMAL)
        formatter = OutputFormatter(context)
        
        assert formatter.context == context
        assert formatter.context.mode == OutputMode.MINIMAL
    
    def test_formatter_has_console(self):
        """OutputFormatter has console for output."""
        context = OutputContext(mode=OutputMode.MINIMAL)
        formatter = OutputFormatter(context)
        
        assert formatter._console is not None
        assert formatter._stderr_console is not None
    
    def test_start_operation_verbose_mode(self):
        """start_operation shows progress in verbose mode."""
        context = OutputContext(mode=OutputMode.VERBOSE)
        formatter = OutputFormatter(context)
        
        # Should not raise
        formatter.start_operation("Processing...")
        
        # Should have started progress
        assert formatter._progress is not None
        
        # Cleanup
        if formatter._progress:
            formatter._progress.stop()
    
    def test_start_operation_minimal_mode(self):
        """start_operation shows minimal progress in minimal mode."""
        context = OutputContext(mode=OutputMode.MINIMAL)
        formatter = OutputFormatter(context)
        
        formatter.start_operation("Processing...")
        
        # Should have started progress
        assert formatter._progress is not None
        
        # Cleanup
        if formatter._progress:
            formatter._progress.stop()
    
    def test_start_operation_json_mode_no_progress(self):
        """start_operation shows nothing in JSON mode."""
        context = OutputContext(mode=OutputMode.JSON)
        formatter = OutputFormatter(context)
        
        formatter.start_operation("Processing...")
        
        # Should NOT have started progress
        assert formatter._progress is None
    
    def test_start_operation_quiet_mode_no_progress(self):
        """start_operation shows nothing in quiet mode."""
        context = OutputContext(mode=OutputMode.QUIET)
        formatter = OutputFormatter(context)
        
        formatter.start_operation("Processing...")
        
        # Should NOT have started progress
        assert formatter._progress is None
    
    def test_progress_verbose_only(self):
        """progress() only outputs in verbose mode."""
        # Verbose mode - should output
        context = OutputContext(mode=OutputMode.VERBOSE)
        formatter = OutputFormatter(context)
        # progress() uses console.print, which we can't easily capture
        # but we can verify it doesn't raise
        formatter.progress("Step 1 complete")
        
        # Other modes - should not output (no-op)
        for mode in [OutputMode.MINIMAL, OutputMode.JSON, OutputMode.QUIET]:
            context = OutputContext(mode=mode)
            formatter = OutputFormatter(context)
            formatter.progress("Step 1 complete")  # Should not raise


class TestOutputFormatterMinimalMode:
    """Tests for OutputFormatter minimal mode output.
    
    Task 5.2: Implement minimal mode output in OutputFormatter
    Validates: Requirements 1.1, 1.2, 1.3, 1.5
    """
    
    def test_minimal_success_output_format(self, capsys):
        """Minimal success output has correct format."""
        context = OutputContext(mode=OutputMode.MINIMAL)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=True,
            duration_seconds=135.0,
            cost_usd=0.42,
            report_path="reports/abc123"
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        # Check output contains key elements
        assert "Research complete" in captured.out
        assert "2m 15s" in captured.out
        assert "$0.42" in captured.out
        assert "reports/abc123/" in captured.out
    
    def test_minimal_error_output_format(self, capsys):
        """Minimal error output has correct format."""
        context = OutputContext(mode=OutputMode.MINIMAL)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=False,
            duration_seconds=10.0,
            cost_usd=0.0,
            error="API rate limit exceeded"
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        assert "Research failed" in captured.out
        assert "API rate limit exceeded" in captured.out
    
    def test_minimal_path_ends_with_slash(self, capsys):
        """Minimal output ensures path ends with slash."""
        context = OutputContext(mode=OutputMode.MINIMAL)
        formatter = OutputFormatter(context)
        
        # Path without trailing slash
        result = OperationResult(
            success=True,
            duration_seconds=60.0,
            cost_usd=0.10,
            report_path="reports/test"
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        assert "reports/test/" in captured.out
    
    def test_minimal_path_already_has_slash(self, capsys):
        """Minimal output doesn't double slash."""
        context = OutputContext(mode=OutputMode.MINIMAL)
        formatter = OutputFormatter(context)
        
        # Path with trailing slash
        result = OperationResult(
            success=True,
            duration_seconds=60.0,
            cost_usd=0.10,
            report_path="reports/test/"
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        assert "reports/test/" in captured.out
        assert "reports/test//" not in captured.out


class TestMinimalOutputFormatProperty:
    """Feature: minimal-default-output, Property 9: Minimal output format consistency
    
    Task 5.3: Write property test for minimal output format
    
    For any successful OperationResult, the minimal output SHALL match
    a consistent format with properly formatted duration and cost.
    
    Validates: Requirements 1.1, 1.5
    """
    
    @given(
        duration=st.floats(min_value=0, max_value=86400, allow_nan=False, allow_infinity=False),
        cost=st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False),
        path=st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789/_-")
    )
    @settings(max_examples=100, suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture])
    def test_minimal_output_format_consistency(self, duration: float, cost: float, path: str, capsys):
        """For any successful result, minimal output has consistent format."""
        assume(len(path.strip()) > 0)  # Non-empty path
        
        context = OutputContext(mode=OutputMode.MINIMAL)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=True,
            duration_seconds=duration,
            cost_usd=cost,
            report_path=path
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        output = captured.out
        
        # Should contain "Research complete"
        assert "Research complete" in output
        
        # Should contain formatted duration (ends with s, m, or h)
        assert re.search(r'\d+[smh]', output) is not None
        
        # Should contain formatted cost (dollar sign and decimals)
        assert re.search(r'\$\d+\.\d{2}', output) is not None
        
        # Should contain path with trailing slash
        assert "->" in output or "→" in output


class TestOutputFormatterJSONMode:
    """Tests for OutputFormatter JSON mode output.
    
    Task 5.4: Implement JSON mode output in OutputFormatter
    Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
    """
    
    def test_json_success_output(self, capsys):
        """JSON mode outputs valid JSON for success."""
        context = OutputContext(mode=OutputMode.JSON)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=True,
            duration_seconds=135.5,
            cost_usd=0.42,
            report_path="reports/abc123/",
            job_id="research-abc123"
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        
        assert data["status"] == "success"
        assert data["duration_seconds"] == 135.5
        assert data["cost_usd"] == 0.42
        assert data["report_path"] == "reports/abc123/"
        assert data["job_id"] == "research-abc123"
    
    def test_json_error_output(self, capsys):
        """JSON mode outputs valid JSON for error."""
        context = OutputContext(mode=OutputMode.JSON)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=False,
            duration_seconds=10.0,
            cost_usd=0.0,
            error="API rate limit exceeded",
            error_code="RATE_LIMIT"
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        
        assert data["status"] == "error"
        assert data["error"] == "API rate limit exceeded"
        assert data["error_code"] == "RATE_LIMIT"
    
    def test_json_no_progress_output(self, capsys):
        """JSON mode suppresses progress output."""
        context = OutputContext(mode=OutputMode.JSON)
        formatter = OutputFormatter(context)
        
        formatter.start_operation("Processing...")
        formatter.progress("Step 1")
        formatter.progress("Step 2")
        
        result = OperationResult(
            success=True,
            duration_seconds=10.0,
            cost_usd=0.01,
            report_path="reports/test/"
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        
        # Output should be valid JSON only
        data = json.loads(captured.out.strip())
        assert data["status"] == "success"
        
        # Should not contain progress messages
        assert "Processing" not in captured.out
        assert "Step 1" not in captured.out
        assert "Step 2" not in captured.out


class TestJSONOutputValidity:
    """Feature: minimal-default-output, Property 5: JSON output validity
    
    Task 5.5: Write property test for JSON validity
    
    For any OperationResult (success or failure), the JSON output SHALL be
    valid JSON that can be parsed by a standard JSON parser.
    
    Validates: Requirements 3.1, 3.6
    """
    
    @given(
        success=st.booleans(),
        duration=st.floats(min_value=0, max_value=86400, allow_nan=False, allow_infinity=False),
        cost=st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False),
        path=st.text(min_size=0, max_size=100),
        job_id=st.text(min_size=0, max_size=50),
        error=st.text(min_size=0, max_size=200),
        error_code=st.text(min_size=0, max_size=50)
    )
    @settings(max_examples=100, suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture])
    def test_json_output_always_valid(
        self, success: bool, duration: float, cost: float,
        path: str, job_id: str, error: str, error_code: str, capsys
    ):
        """For any result, JSON output is valid JSON."""
        context = OutputContext(mode=OutputMode.JSON)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=success,
            duration_seconds=duration,
            cost_usd=cost,
            report_path=path if success else None,
            job_id=job_id if success else None,
            error=error if not success else None,
            error_code=error_code if not success else None
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        
        # Should be valid JSON
        try:
            data = json.loads(captured.out.strip())
            assert isinstance(data, dict)
        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON output: {e}")


class TestJSONOutputCompletenessSuccess:
    """Feature: minimal-default-output, Property 6: JSON output completeness (success)
    
    Task 5.6: Write property test for JSON completeness (success)
    
    For any successful OperationResult, the parsed JSON output SHALL contain
    all required fields: status, duration_seconds, cost_usd, report_path, job_id.
    
    Validates: Requirements 3.2
    """
    
    @given(
        duration=st.floats(min_value=0, max_value=86400, allow_nan=False, allow_infinity=False),
        cost=st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False),
        path=st.text(min_size=0, max_size=100),
        job_id=st.text(min_size=0, max_size=50)
    )
    @settings(max_examples=100, suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture])
    def test_json_success_has_all_fields(
        self, duration: float, cost: float, path: str, job_id: str, capsys
    ):
        """For any success result, JSON has all required fields."""
        context = OutputContext(mode=OutputMode.JSON)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=True,
            duration_seconds=duration,
            cost_usd=cost,
            report_path=path,
            job_id=job_id
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        
        # All required fields must be present
        assert "status" in data
        assert data["status"] == "success"
        assert "duration_seconds" in data
        assert "cost_usd" in data
        assert "report_path" in data
        assert "job_id" in data


class TestJSONOutputCompletenessError:
    """Feature: minimal-default-output, Property 7: JSON output completeness (error)
    
    Task 5.7: Write property test for JSON completeness (error)
    
    For any failed OperationResult, the parsed JSON output SHALL contain
    all required fields: status, error, error_code.
    
    Validates: Requirements 3.3
    """
    
    @given(
        duration=st.floats(min_value=0, max_value=86400, allow_nan=False, allow_infinity=False),
        error=st.text(min_size=0, max_size=200),
        error_code=st.text(min_size=0, max_size=50)
    )
    @settings(max_examples=100, suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture])
    def test_json_error_has_all_fields(
        self, duration: float, error: str, error_code: str, capsys
    ):
        """For any error result, JSON has all required fields."""
        context = OutputContext(mode=OutputMode.JSON)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=False,
            duration_seconds=duration,
            cost_usd=0.0,
            error=error,
            error_code=error_code
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        
        # All required fields must be present
        assert "status" in data
        assert data["status"] == "error"
        assert "error" in data
        assert "error_code" in data


class TestJSONOutputPurity:
    """Feature: minimal-default-output, Property 8: JSON output purity
    
    Task 5.8: Write property test for JSON output purity
    
    For any operation in JSON mode, the stdout output SHALL contain only
    the JSON object with no additional text, spinners, or progress indicators.
    
    Validates: Requirements 3.4, 3.5
    """
    
    @given(
        success=st.booleans(),
        duration=st.floats(min_value=0, max_value=86400, allow_nan=False, allow_infinity=False),
        cost=st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100, suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture])
    def test_json_output_is_pure(self, success: bool, duration: float, cost: float, capsys):
        """JSON output contains only the JSON object, nothing else."""
        context = OutputContext(mode=OutputMode.JSON)
        formatter = OutputFormatter(context)
        
        # Simulate full operation lifecycle
        formatter.start_operation("Processing...")
        formatter.progress("Step 1")
        formatter.progress("Step 2")
        
        result = OperationResult(
            success=success,
            duration_seconds=duration,
            cost_usd=cost,
            report_path="reports/test/" if success else None,
            error="Test error" if not success else None,
            error_code="TEST" if not success else None
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        output = captured.out.strip()
        
        # Output should start with { and end with }
        assert output.startswith("{"), f"Output doesn't start with {{: {output[:50]}"
        assert output.endswith("}"), f"Output doesn't end with }}: {output[-50:]}"
        
        # Should be valid JSON
        data = json.loads(output)
        assert isinstance(data, dict)
        
        # Should not contain progress indicators
        assert "Processing" not in output
        assert "Step 1" not in output
        assert "Step 2" not in output


class TestOutputFormatterQuietMode:
    """Tests for OutputFormatter quiet mode output.
    
    Task 5.9: Implement quiet mode output in OutputFormatter
    Validates: Requirements 4.1, 4.2
    """
    
    def test_quiet_success_no_stdout(self, capsys):
        """Quiet mode produces no stdout on success."""
        context = OutputContext(mode=OutputMode.QUIET)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=True,
            duration_seconds=135.5,
            cost_usd=0.42,
            report_path="reports/abc123/"
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        assert captured.out == ""
    
    def test_quiet_error_to_stderr(self, capsys):
        """Quiet mode outputs errors to stderr."""
        context = OutputContext(mode=OutputMode.QUIET)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=False,
            duration_seconds=10.0,
            cost_usd=0.0,
            error="API rate limit exceeded"
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "API rate limit exceeded" in captured.err
    
    def test_quiet_no_progress(self, capsys):
        """Quiet mode shows no progress."""
        context = OutputContext(mode=OutputMode.QUIET)
        formatter = OutputFormatter(context)
        
        formatter.start_operation("Processing...")
        formatter.progress("Step 1")
        
        captured = capsys.readouterr()
        assert captured.out == ""


class TestQuietModeStdoutSilence:
    """Feature: minimal-default-output, Property 10: Quiet mode stdout silence
    
    Task 5.10: Write property test for quiet mode stdout silence
    
    For any successful operation in quiet mode, the stdout output SHALL be empty.
    
    Validates: Requirements 4.1
    """
    
    @given(
        duration=st.floats(min_value=0, max_value=86400, allow_nan=False, allow_infinity=False),
        cost=st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False),
        path=st.text(min_size=0, max_size=100),
        job_id=st.text(min_size=0, max_size=50)
    )
    @settings(max_examples=100, suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture])
    def test_quiet_success_stdout_empty(
        self, duration: float, cost: float, path: str, job_id: str, capsys
    ):
        """For any successful operation in quiet mode, stdout is empty."""
        context = OutputContext(mode=OutputMode.QUIET)
        formatter = OutputFormatter(context)
        
        # Full operation lifecycle
        formatter.start_operation("Processing...")
        formatter.progress("Working...")
        
        result = OperationResult(
            success=True,
            duration_seconds=duration,
            cost_usd=cost,
            report_path=path,
            job_id=job_id
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        assert captured.out == "", f"Expected empty stdout, got: {captured.out}"


class TestQuietModeStderrErrors:
    """Feature: minimal-default-output, Property 11: Quiet mode stderr errors
    
    Task 5.11: Write property test for quiet mode stderr errors
    
    For any failed operation in quiet mode, the stderr output SHALL contain
    only the error message and nothing else.
    
    Validates: Requirements 4.2
    """
    
    @given(
        duration=st.floats(min_value=0, max_value=86400, allow_nan=False, allow_infinity=False),
        error=st.text(min_size=1, max_size=200, alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?-_")
    )
    @settings(max_examples=100, suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture])
    def test_quiet_error_stderr_only(self, duration: float, error: str, capsys):
        """For any failed operation in quiet mode, error goes to stderr only."""
        assume(len(error.strip()) > 0)  # Non-empty error
        
        context = OutputContext(mode=OutputMode.QUIET)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=False,
            duration_seconds=duration,
            cost_usd=0.0,
            error=error
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        
        # stdout should be empty
        assert captured.out == "", f"Expected empty stdout, got: {captured.out}"
        
        # stderr should contain the error
        assert error in captured.err or "Unknown error" in captured.err


class TestOutputFormatterVerboseMode:
    """Tests for OutputFormatter verbose mode output.
    
    Task 5.12: Implement verbose mode output in OutputFormatter
    Validates: Requirements 2.1, 2.2, 2.3
    """
    
    def test_verbose_success_detailed_output(self, capsys):
        """Verbose mode shows detailed success output."""
        context = OutputContext(mode=OutputMode.VERBOSE)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=True,
            duration_seconds=135.5,
            cost_usd=0.42,
            report_path="reports/abc123/",
            job_id="research-abc123"
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        
        # Should contain detailed information
        assert "Research Complete" in captured.out
        assert "Duration" in captured.out
        assert "Cost" in captured.out
        assert "Report" in captured.out
        assert "Job ID" in captured.out
    
    def test_verbose_error_detailed_output(self, capsys):
        """Verbose mode shows detailed error output."""
        context = OutputContext(mode=OutputMode.VERBOSE)
        formatter = OutputFormatter(context)
        
        result = OperationResult(
            success=False,
            duration_seconds=10.0,
            cost_usd=0.0,
            error="API rate limit exceeded",
            error_code="RATE_LIMIT"
        )
        
        formatter.complete(result)
        
        captured = capsys.readouterr()
        
        # Should contain detailed error information
        assert "Research Failed" in captured.out
        assert "Error" in captured.out
        assert "API rate limit exceeded" in captured.out
        assert "Code" in captured.out
        assert "RATE_LIMIT" in captured.out
    
    def test_verbose_progress_messages(self, capsys):
        """Verbose mode shows progress messages."""
        context = OutputContext(mode=OutputMode.VERBOSE)
        formatter = OutputFormatter(context)
        
        # Progress messages should not raise
        formatter.progress("Step 1 complete")
        formatter.progress("Step 2 complete")
        
        # Note: Rich console output may not be captured by capsys
        # This test verifies the method doesn't raise


class TestOutputFormatterErrorMethod:
    """Tests for OutputFormatter.error() method."""
    
    def test_error_method_minimal_mode(self, capsys):
        """error() method works in minimal mode."""
        context = OutputContext(mode=OutputMode.MINIMAL)
        formatter = OutputFormatter(context)
        
        formatter.error("Something went wrong", code="ERR001")
        
        captured = capsys.readouterr()
        assert "Something went wrong" in captured.out
    
    def test_error_method_json_mode(self, capsys):
        """error() method outputs JSON in JSON mode."""
        context = OutputContext(mode=OutputMode.JSON)
        formatter = OutputFormatter(context)
        
        formatter.error("Something went wrong", code="ERR001")
        
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        
        assert data["status"] == "error"
        assert data["error"] == "Something went wrong"
        assert data["error_code"] == "ERR001"
    
    def test_error_method_quiet_mode(self, capsys):
        """error() method outputs to stderr in quiet mode."""
        context = OutputContext(mode=OutputMode.QUIET)
        formatter = OutputFormatter(context)
        
        formatter.error("Something went wrong")
        
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Something went wrong" in captured.err


# Import for Click decorator tests
import click
from click.testing import CliRunner
from deepr.cli.output import output_options


class TestOutputOptionsDecorator:
    """Tests for output_options Click decorator.
    
    Task 7.4: Write integration test for decorator with Click command
    Validates: Requirements 2.4, 4.3, 5.1, 5.2, 5.3, 5.4
    """
    
    def test_decorator_adds_verbose_flag(self):
        """Decorator adds --verbose/-v flag to command."""
        @click.command()
        @output_options
        def test_cmd(output_context: OutputContext):
            click.echo(f"mode={output_context.mode.value}")
        
        runner = CliRunner()
        
        # Test --verbose
        result = runner.invoke(test_cmd, ["--verbose"])
        assert result.exit_code == 0
        assert "mode=verbose" in result.output
        
        # Test -v alias
        result = runner.invoke(test_cmd, ["-v"])
        assert result.exit_code == 0
        assert "mode=verbose" in result.output
    
    def test_decorator_adds_json_flag(self):
        """Decorator adds --json flag to command."""
        @click.command()
        @output_options
        def test_cmd(output_context: OutputContext):
            click.echo(f"mode={output_context.mode.value}")
        
        runner = CliRunner()
        result = runner.invoke(test_cmd, ["--json"])
        assert result.exit_code == 0
        assert "mode=json" in result.output
    
    def test_decorator_adds_quiet_flag(self):
        """Decorator adds --quiet/-q flag to command."""
        @click.command()
        @output_options
        def test_cmd(output_context: OutputContext):
            click.echo(f"mode={output_context.mode.value}")
        
        runner = CliRunner()
        
        # Test --quiet
        result = runner.invoke(test_cmd, ["--quiet"])
        assert result.exit_code == 0
        assert "mode=quiet" in result.output
        
        # Test -q alias
        result = runner.invoke(test_cmd, ["-q"])
        assert result.exit_code == 0
        assert "mode=quiet" in result.output
    
    def test_decorator_defaults_to_minimal(self):
        """No flags defaults to minimal mode."""
        @click.command()
        @output_options
        def test_cmd(output_context: OutputContext):
            click.echo(f"mode={output_context.mode.value}")
        
        runner = CliRunner()
        result = runner.invoke(test_cmd, [])
        assert result.exit_code == 0
        assert "mode=minimal" in result.output
    
    def test_decorator_rejects_conflicting_flags(self):
        """Decorator rejects conflicting output flags."""
        @click.command()
        @output_options
        def test_cmd(output_context: OutputContext):
            click.echo("should not reach here")
        
        runner = CliRunner()
        
        # --verbose and --quiet conflict
        result = runner.invoke(test_cmd, ["--verbose", "--quiet"])
        assert result.exit_code != 0
        assert "Cannot use" in result.output or "Error" in result.output
        
        # --json and --verbose conflict
        result = runner.invoke(test_cmd, ["--json", "--verbose"])
        assert result.exit_code != 0
        
        # --json and --quiet conflict
        result = runner.invoke(test_cmd, ["--json", "--quiet"])
        assert result.exit_code != 0
    
    def test_decorator_passes_output_context(self):
        """Decorator passes OutputContext to command."""
        received_context = None
        
        @click.command()
        @output_options
        def test_cmd(output_context: OutputContext):
            nonlocal received_context
            received_context = output_context
            click.echo("done")
        
        runner = CliRunner()
        result = runner.invoke(test_cmd, ["--verbose"])
        
        assert result.exit_code == 0
        assert received_context is not None
        assert isinstance(received_context, OutputContext)
        assert received_context.mode == OutputMode.VERBOSE
        assert received_context.start_time is not None
    
    def test_decorator_env_var_backward_compatibility(self, monkeypatch):
        """DEEPR_VERBOSE env var defaults to verbose when no flags."""
        @click.command()
        @output_options
        def test_cmd(output_context: OutputContext):
            click.echo(f"mode={output_context.mode.value}")
        
        runner = CliRunner()
        
        # With env var set
        result = runner.invoke(test_cmd, [], env={"DEEPR_VERBOSE": "true"})
        assert result.exit_code == 0
        assert "mode=verbose" in result.output
    
    def test_decorator_explicit_flag_overrides_env_var(self):
        """Explicit flags override DEEPR_VERBOSE env var."""
        @click.command()
        @output_options
        def test_cmd(output_context: OutputContext):
            click.echo(f"mode={output_context.mode.value}")
        
        runner = CliRunner()
        
        # --quiet should override env var
        result = runner.invoke(test_cmd, ["--quiet"], env={"DEEPR_VERBOSE": "true"})
        assert result.exit_code == 0
        assert "mode=quiet" in result.output


class TestExitCodeConsistency:
    """Feature: minimal-default-output, Property 12: Exit code consistency
    
    Task 7.3: Write property test for exit code consistency
    
    For any operation, the exit code SHALL be:
    - 0 for successful operations
    - Non-zero for failed operations
    
    Validates: Requirements 4.4, 8.3
    """
    
    def test_success_exit_code_zero(self):
        """Successful operations return exit code 0."""
        @click.command()
        @output_options
        def test_cmd(output_context: OutputContext):
            formatter = OutputFormatter(output_context)
            result = OperationResult(
                success=True,
                duration_seconds=10.0,
                cost_usd=0.01,
                report_path="reports/test/"
            )
            formatter.complete(result)
        
        runner = CliRunner()
        
        # Test all modes
        for flags in [[], ["--verbose"], ["--json"], ["--quiet"]]:
            result = runner.invoke(test_cmd, flags)
            assert result.exit_code == 0, f"Expected exit code 0 for flags {flags}, got {result.exit_code}"
    
    def test_error_with_sys_exit_returns_nonzero(self):
        """Operations that call sys.exit(1) return non-zero exit code."""
        @click.command()
        @output_options
        def test_cmd(output_context: OutputContext):
            formatter = OutputFormatter(output_context)
            formatter.error("Something went wrong")
            raise SystemExit(1)
        
        runner = CliRunner()
        result = runner.invoke(test_cmd, [])
        assert result.exit_code != 0
    
    @given(
        mode=st.sampled_from([OutputMode.MINIMAL, OutputMode.VERBOSE, OutputMode.JSON, OutputMode.QUIET])
    )
    @settings(max_examples=20)
    def test_exit_code_consistent_across_modes(self, mode: OutputMode):
        """Exit code is consistent regardless of output mode."""
        @click.command()
        @output_options
        def success_cmd(output_context: OutputContext):
            formatter = OutputFormatter(output_context)
            result = OperationResult(
                success=True,
                duration_seconds=10.0,
                cost_usd=0.01,
                report_path="reports/test/"
            )
            formatter.complete(result)
        
        runner = CliRunner()
        
        # Map mode to flag
        flag_map = {
            OutputMode.MINIMAL: [],
            OutputMode.VERBOSE: ["--verbose"],
            OutputMode.JSON: ["--json"],
            OutputMode.QUIET: ["--quiet"]
        }
        
        result = runner.invoke(success_cmd, flag_map[mode])
        assert result.exit_code == 0, f"Expected exit code 0 for mode {mode}, got {result.exit_code}"
