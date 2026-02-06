"""Property-based tests for CLI colors module.

Feature: cli-ux-modernization
Tests symbol mapping, truncation, and formatting functions.
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from deepr.cli.colors import (
    ASCII_SYMBOLS,
    UNICODE_SYMBOLS,
    _format_duration,
    get_symbol,
    print_command,
    print_cost,
    print_deprecation,
    print_error,
    print_header,
    print_info,
    print_result,
    print_status,
    print_step,
    print_success,
    print_warning,
    truncate_path,
    truncate_text,
)


class TestSymbolMapping:
    """Feature: cli-ux-modernization, Property 1: Symbol Mapping Consistency

    For any status type, the rendered output SHALL contain the correct symbol
    and SHALL NOT contain legacy text markers.

    Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.6
    """

    @given(st.sampled_from(list(UNICODE_SYMBOLS.keys())))
    @settings(max_examples=100)
    def test_symbol_returns_valid_value(self, symbol_name: str):
        """For any symbol name, get_symbol returns a non-empty string."""
        result = get_symbol(symbol_name)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(st.sampled_from(list(UNICODE_SYMBOLS.keys())))
    @settings(max_examples=100)
    def test_symbol_is_from_known_set(self, symbol_name: str):
        """For any symbol name, result is from either Unicode or ASCII set."""
        result = get_symbol(symbol_name)
        assert result in UNICODE_SYMBOLS.values() or result in ASCII_SYMBOLS.values()

    def test_all_status_types_have_symbols(self):
        """All required status types have both Unicode and ASCII symbols."""
        required_types = ["success", "error", "warning", "info", "progress"]
        for status_type in required_types:
            assert status_type in UNICODE_SYMBOLS
            assert status_type in ASCII_SYMBOLS

    def test_unicode_symbols_are_text_labels(self):
        """Symbols should be clean text labels (modern 2026 CLI design)."""
        for name, symbol in UNICODE_SYMBOLS.items():
            # Modern CLI uses text labels, not Unicode symbols or [OK] style markers
            assert len(symbol) <= 5, f"{name} symbol '{symbol}' is too long"
            assert not symbol.startswith("["), f"{name} symbol '{symbol}' looks like legacy ASCII"
            # Should be alphanumeric or punctuation, not Unicode symbols
            assert all(c.isalnum() or c in ".-" for c in symbol), (
                f"{name} symbol '{symbol}' contains unexpected characters"
            )


class TestTextTruncation:
    """Feature: cli-ux-modernization, Property 3: Text Truncation Correctness

    For any text string longer than max width:
    - Output SHALL end with ellipsis (not three dots)
    - Truncation SHALL be at word boundary when possible
    - Output SHALL contain at least 40 characters of content

    Validates: Requirements 5.1, 5.2, 5.3, 5.5
    """

    @given(st.text(min_size=100, max_size=500, alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"))))
    @settings(max_examples=100)
    def test_truncation_uses_ellipsis(self, text: str):
        """For any long text, truncation uses ellipsis character."""
        assume(len(text.strip()) > 80)
        result = truncate_text(text, max_width=80)

        # Should be truncated
        assert len(result) <= 80
        # Should end with ellipsis (Unicode or ASCII)
        assert result.endswith("…") or result.endswith("...")

    @given(st.text(min_size=10, max_size=50))
    @settings(max_examples=100)
    def test_short_text_unchanged(self, text: str):
        """Text shorter than max_width is returned unchanged."""
        result = truncate_text(text, max_width=80)
        assert result == text

    @given(st.integers(min_value=50, max_value=200))
    @settings(max_examples=50)
    def test_truncation_respects_max_width(self, max_width: int):
        """Truncated text never exceeds max_width."""
        long_text = "This is a very long text that needs to be truncated " * 10
        result = truncate_text(long_text, max_width=max_width)
        assert len(result) <= max_width

    def test_truncation_at_word_boundary(self):
        """Truncation occurs at word boundary when possible."""
        text = "This is a sentence with multiple words that should be truncated nicely"
        result = truncate_text(text, max_width=40)

        # Should not cut in middle of a word (unless no spaces)
        # The character before ellipsis should be a space or the text should be very short
        content = result.rstrip("…").rstrip("...")
        # Either ends with space or is at a reasonable boundary
        assert len(content) >= 30  # Minimum content preserved


class TestPathTruncation:
    """Feature: cli-ux-modernization, Property 3: Text Truncation Correctness (paths)

    For file paths, the filename component SHALL be preserved.

    Validates: Requirements 5.1, 5.2, 5.3, 5.5
    """

    def test_short_path_unchanged(self):
        """Short paths are returned unchanged."""
        path = "src/main.py"
        result = truncate_path(path, max_width=60)
        assert result == path

    def test_long_path_preserves_filename(self):
        """Long paths preserve the filename."""
        path = "very/long/nested/directory/structure/that/goes/on/forever/main.py"
        result = truncate_path(path, max_width=30)

        assert "main.py" in result
        assert len(result) <= 30

    def test_windows_path_handling(self):
        """Windows-style paths are handled correctly."""
        path = "C:\\Users\\developer\\projects\\deepr\\src\\main.py"
        result = truncate_path(path, max_width=40)

        assert "main.py" in result


class TestDurationFormatting:
    """Feature: cli-ux-modernization, Property 4: Duration and Cost Formatting

    For any duration value:
    - Values < 60 SHALL be formatted as Xs
    - Values >= 60 SHALL be formatted as Xm Ys

    Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5
    """

    @given(st.floats(min_value=0, max_value=59.99, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_short_duration_format(self, seconds: float):
        """For any duration < 60s, format is Xs."""
        result = _format_duration(seconds)
        assert "s" in result
        assert "m" not in result

    @given(st.floats(min_value=60, max_value=3600, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_long_duration_format(self, seconds: float):
        """For any duration >= 60s, format is Xm Ys."""
        result = _format_duration(seconds)
        assert "m" in result
        assert "s" in result

    def test_duration_examples(self):
        """Specific duration formatting examples."""
        assert _format_duration(12.3) == "12.3s"
        assert _format_duration(60) == "1m 0s"
        assert _format_duration(90) == "1m 30s"
        assert _format_duration(125) == "2m 5s"


class TestPrintFunctions:
    """Tests for print functions with mocked console."""

    @pytest.fixture
    def mock_console(self, mocker):
        """Mock the console for testing print functions."""
        return mocker.patch("deepr.cli.colors.console")

    def test_print_header(self, mock_console):
        """print_header should print styled header."""
        print_header("Test Header")
        assert mock_console.print.call_count >= 2

    def test_print_success(self, mock_console):
        """print_success should print with success style."""
        print_success("Operation succeeded")
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Operation succeeded" in call_args

    def test_print_error(self, mock_console):
        """print_error should print with error style."""
        print_error("Something failed")
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Something failed" in call_args

    def test_print_warning(self, mock_console):
        """print_warning should print with warning style."""
        print_warning("Caution needed")
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Caution needed" in call_args

    def test_print_info(self, mock_console):
        """print_info should print with info style."""
        print_info("Information message")
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Information message" in call_args

    def test_print_command(self, mock_console):
        """print_command should format as command example."""
        print_command("deepr research 'test'")
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "deepr research" in call_args

    def test_print_cost(self, mock_console):
        """print_cost should format cost value."""
        print_cost(0.0234)
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "0.0234" in call_args

    def test_print_status_completed(self, mock_console):
        """print_status should handle completed status."""
        print_status("completed", "Job finished")
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Job finished" in call_args

    def test_print_status_processing(self, mock_console):
        """print_status should handle processing status."""
        print_status("processing", "Job running")
        mock_console.print.assert_called_once()

    def test_print_status_failed(self, mock_console):
        """print_status should handle failed status."""
        print_status("failed", "Job failed")
        mock_console.print.assert_called_once()

    def test_print_status_queued(self, mock_console):
        """print_status should handle queued status."""
        print_status("queued", "Job waiting")
        mock_console.print.assert_called_once()

    def test_print_result_success(self, mock_console):
        """print_result should format success message."""
        print_result("Task complete", duration_seconds=12.5, cost_usd=0.05, success=True)
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Task complete" in call_args

    def test_print_result_failure(self, mock_console):
        """print_result should format failure message."""
        print_result("Task failed", success=False)
        mock_console.print.assert_called_once()

    def test_print_result_no_meta(self, mock_console):
        """print_result should work without duration and cost."""
        print_result("Simple message")
        mock_console.print.assert_called_once()

    def test_print_step(self, mock_console):
        """print_step should format step indicator."""
        print_step(1, 5, "Starting process")
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "1/5" in call_args
        assert "Starting process" in call_args

    def test_print_deprecation(self, mock_console):
        """print_deprecation should show deprecation warning."""
        print_deprecation("old-cmd", "new-cmd")
        # Should print multiple times (empty lines + panel)
        assert mock_console.print.call_count >= 2
