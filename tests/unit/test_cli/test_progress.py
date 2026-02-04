"""Tests for CLI progress feedback module.

Tests cover:
- ProgressFeedback class methods
- Operation context manager
- Status and message functions
- Long operation warnings
"""

import time
import pytest
from unittest.mock import patch, MagicMock

from deepr.cli.progress import (
    ProgressFeedback,
    with_progress,
    complete,
    error,
    status,
)


class TestProgressFeedback:
    """Tests for ProgressFeedback class."""

    def test_initialization(self):
        """ProgressFeedback should initialize with correct defaults."""
        progress = ProgressFeedback()

        assert progress.start_time is None
        assert progress.phase == ""
        assert progress._warned_long_operation is False

    def test_long_operation_threshold(self):
        """ProgressFeedback should have threshold constant."""
        progress = ProgressFeedback()

        assert progress.LONG_OPERATION_THRESHOLD == 15.0

    @patch("deepr.cli.progress.console")
    def test_phase_complete_with_cost(self, mock_console):
        """phase_complete should include cost when provided."""
        progress = ProgressFeedback()
        progress.start_time = time.time()

        progress.phase_complete("Done", cost=1.50)

        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Done" in call_args
        assert "$1.50" in call_args

    @patch("deepr.cli.progress.console")
    def test_phase_complete_without_cost(self, mock_console):
        """phase_complete should work without cost."""
        progress = ProgressFeedback()
        progress.start_time = time.time()

        progress.phase_complete("Done")

        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Done" in call_args
        assert "$" not in call_args

    @patch("deepr.cli.progress.console")
    def test_phase_complete_no_start_time(self, mock_console):
        """phase_complete should handle missing start_time gracefully."""
        progress = ProgressFeedback()

        progress.phase_complete("Done")

        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "0.0s" in call_args

    @patch("deepr.cli.progress.console")
    def test_phase_error(self, mock_console):
        """phase_error should show error with red marker."""
        progress = ProgressFeedback()

        progress.phase_error("Something failed")

        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Something failed" in call_args
        assert "red" in call_args

    @patch("deepr.cli.progress.console")
    def test_long_operation_warning(self, mock_console):
        """long_operation_warning should show warning message."""
        progress = ProgressFeedback()

        progress.long_operation_warning()

        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Still working" in call_args

    @patch("deepr.cli.progress.console")
    def test_long_operation_warning_only_once(self, mock_console):
        """long_operation_warning should only warn once."""
        progress = ProgressFeedback()

        progress.long_operation_warning()
        progress.long_operation_warning()
        progress.long_operation_warning()

        # Should only be called once
        assert mock_console.print.call_count == 1

    @patch("deepr.cli.progress.console")
    def test_check_long_operation_no_start(self, mock_console):
        """check_long_operation should not warn if not started."""
        progress = ProgressFeedback()

        progress.check_long_operation()

        mock_console.print.assert_not_called()

    @patch("deepr.cli.progress.console")
    def test_check_long_operation_short(self, mock_console):
        """check_long_operation should not warn for short operations."""
        progress = ProgressFeedback()
        progress.start_time = time.time()

        progress.check_long_operation()

        mock_console.print.assert_not_called()

    @patch("deepr.cli.progress.console")
    def test_check_long_operation_long(self, mock_console):
        """check_long_operation should warn for long operations."""
        progress = ProgressFeedback()
        # Set start time to well in the past
        progress.start_time = time.time() - 20.0

        progress.check_long_operation()

        mock_console.print.assert_called_once()

    @patch("deepr.cli.progress.console")
    def test_status_message(self, mock_console):
        """status should show dimmed message."""
        progress = ProgressFeedback()

        progress.status("Processing item 1")

        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Processing item 1" in call_args
        assert "dim" in call_args

    @patch("deepr.cli.progress.console")
    def test_info_message(self, mock_console):
        """info should show cyan info message."""
        progress = ProgressFeedback()

        progress.info("Important information")

        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Important information" in call_args
        assert "cyan" in call_args


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    @patch("deepr.cli.progress._default_progress")
    def test_complete_function(self, mock_progress):
        """complete() should call phase_complete on default progress."""
        complete("Done", cost=2.0)

        mock_progress.phase_complete.assert_called_once_with("Done", 2.0)

    @patch("deepr.cli.progress._default_progress")
    def test_error_function(self, mock_progress):
        """error() should call phase_error on default progress."""
        error("Failed")

        mock_progress.phase_error.assert_called_once_with("Failed")

    @patch("deepr.cli.progress._default_progress")
    def test_status_function(self, mock_progress):
        """status() should call status on default progress."""
        status("Working...")

        mock_progress.status.assert_called_once_with("Working...")


class TestOperationContextManager:
    """Tests for operation context manager."""

    @patch("deepr.cli.progress.Progress")
    @patch("deepr.cli.progress.console")
    def test_operation_sets_start_time(self, mock_console, mock_progress_class):
        """operation should set start_time when entered."""
        mock_progress = MagicMock()
        mock_progress_class.return_value.__enter__ = MagicMock(return_value=mock_progress)
        mock_progress_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_progress.add_task.return_value = 0

        progress = ProgressFeedback()

        with progress.operation("Testing"):
            assert progress.start_time is not None
            assert progress.phase == "Testing"

    @patch("deepr.cli.progress.Progress")
    @patch("deepr.cli.progress.console")
    def test_operation_resets_warning_flag(self, mock_console, mock_progress_class):
        """operation should reset warning flag."""
        mock_progress = MagicMock()
        mock_progress_class.return_value.__enter__ = MagicMock(return_value=mock_progress)
        mock_progress_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_progress.add_task.return_value = 0

        progress = ProgressFeedback()
        progress._warned_long_operation = True

        with progress.operation("Testing"):
            assert progress._warned_long_operation is False

    @patch("deepr.cli.progress._default_progress")
    def test_with_progress_function(self, mock_progress):
        """with_progress should return operation context manager."""
        mock_context = MagicMock()
        mock_progress.operation.return_value = mock_context

        result = with_progress("Testing")

        mock_progress.operation.assert_called_once_with("Testing")
        assert result == mock_context
