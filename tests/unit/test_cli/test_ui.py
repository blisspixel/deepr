"""Tests for CLI UI module.

Tests cover:
- QueryComplexity enum
- classify_query_complexity function
- Various print functions with mocked console
"""

import pytest
from unittest.mock import patch, MagicMock

from deepr.cli.ui import (
    QueryComplexity,
    classify_query_complexity,
    print_welcome,
    print_user_input,
    print_thinking,
    print_tool_use,
    print_divider,
    print_tool_summary,
    stream_response,
    print_error,
)


class TestQueryComplexity:
    """Tests for QueryComplexity enum."""

    def test_simple_value(self):
        """SIMPLE should have correct value."""
        assert QueryComplexity.SIMPLE.value == "simple"

    def test_moderate_value(self):
        """MODERATE should have correct value."""
        assert QueryComplexity.MODERATE.value == "moderate"

    def test_complex_value(self):
        """COMPLEX should have correct value."""
        assert QueryComplexity.COMPLEX.value == "complex"


class TestClassifyQueryComplexity:
    """Tests for classify_query_complexity function."""

    # Simple queries
    def test_hi_is_simple(self):
        """'hi' should be classified as simple."""
        assert classify_query_complexity("hi") == QueryComplexity.SIMPLE

    def test_hello_is_simple(self):
        """'hello' should be classified as simple."""
        assert classify_query_complexity("hello") == QueryComplexity.SIMPLE

    def test_hey_is_simple(self):
        """'hey' should be classified as simple."""
        assert classify_query_complexity("hey") == QueryComplexity.SIMPLE

    def test_thanks_is_simple(self):
        """'thanks' should be classified as simple."""
        assert classify_query_complexity("thanks") == QueryComplexity.SIMPLE

    def test_thank_you_is_simple(self):
        """'thank you' should be classified as simple."""
        assert classify_query_complexity("thank you") == QueryComplexity.SIMPLE

    def test_ok_is_simple(self):
        """'ok' should be classified as simple."""
        assert classify_query_complexity("ok") == QueryComplexity.SIMPLE

    def test_yes_is_simple(self):
        """'yes' should be classified as simple."""
        assert classify_query_complexity("yes") == QueryComplexity.SIMPLE

    def test_no_is_simple(self):
        """'no' should be classified as simple."""
        assert classify_query_complexity("no") == QueryComplexity.SIMPLE

    def test_bye_is_simple(self):
        """'bye' should be classified as simple."""
        assert classify_query_complexity("bye") == QueryComplexity.SIMPLE

    def test_help_is_simple(self):
        """'help' should be classified as simple."""
        assert classify_query_complexity("help") == QueryComplexity.SIMPLE

    def test_quit_is_simple(self):
        """'quit' should be classified as simple."""
        assert classify_query_complexity("quit") == QueryComplexity.SIMPLE

    def test_exit_is_simple(self):
        """'exit' should be classified as simple."""
        assert classify_query_complexity("exit") == QueryComplexity.SIMPLE

    def test_simple_case_insensitive(self):
        """Simple detection should be case insensitive."""
        assert classify_query_complexity("HI") == QueryComplexity.SIMPLE
        assert classify_query_complexity("Hello") == QueryComplexity.SIMPLE
        assert classify_query_complexity("THANKS") == QueryComplexity.SIMPLE

    # Complex queries
    def test_how_would_you_is_complex(self):
        """'how would you' queries should be complex."""
        assert classify_query_complexity("how would you solve this?") == QueryComplexity.COMPLEX

    def test_compare_is_complex(self):
        """'compare' queries should be complex."""
        assert classify_query_complexity("compare these two approaches") == QueryComplexity.COMPLEX

    def test_analyze_is_complex(self):
        """'analyze' queries should be complex."""
        assert classify_query_complexity("analyze the performance data") == QueryComplexity.COMPLEX

    def test_explain_is_complex(self):
        """'explain' queries should be complex."""
        assert classify_query_complexity("explain how this works") == QueryComplexity.COMPLEX

    def test_architecture_is_complex(self):
        """'architecture' queries should be complex."""
        assert classify_query_complexity("what's the best architecture?") == QueryComplexity.COMPLEX

    def test_strategy_is_complex(self):
        """'strategy' queries should be complex."""
        assert classify_query_complexity("what strategy should we use?") == QueryComplexity.COMPLEX

    def test_pros_and_cons_is_complex(self):
        """'pros and cons' queries should be complex."""
        assert classify_query_complexity("what are the pros and cons?") == QueryComplexity.COMPLEX

    def test_long_query_is_complex(self):
        """Queries over 15 words should be complex."""
        long_query = "I need you to help me with this very long question that has many words in it"
        assert classify_query_complexity(long_query) == QueryComplexity.COMPLEX

    def test_multiple_questions_is_complex(self):
        """Multiple questions should be complex."""
        multi_q = "What is this? How does it work?"
        assert classify_query_complexity(multi_q) == QueryComplexity.COMPLEX

    # Moderate queries (default)
    def test_simple_question_is_moderate(self):
        """Simple factual questions should be moderate."""
        assert classify_query_complexity("what time is it?") == QueryComplexity.MODERATE

    def test_short_query_is_moderate(self):
        """Short queries without complexity indicators are moderate."""
        assert classify_query_complexity("tell me about Python") == QueryComplexity.MODERATE

    def test_single_word_not_simple_is_moderate(self):
        """Single words that aren't greetings should be moderate."""
        assert classify_query_complexity("Python") == QueryComplexity.MODERATE


class TestPrintFunctions:
    """Tests for print functions with mocked console."""

    @patch("deepr.cli.ui.console")
    def test_print_welcome(self, mock_console):
        """print_welcome should create panel with expert info."""
        print_welcome(
            expert_name="TestExpert",
            domain="Testing",
            documents=100,
            updated_date="2024-01-15",
            knowledge_age_days=5
        )

        # Should call print multiple times (empty lines + panel)
        assert mock_console.print.call_count >= 2

    @patch("deepr.cli.ui.console")
    def test_print_welcome_fresh_knowledge(self, mock_console):
        """print_welcome should show 'fresh' for age 0."""
        print_welcome("Expert", "Domain", 10, "2024-01-01", knowledge_age_days=0)
        assert mock_console.print.called

    @patch("deepr.cli.ui.console")
    def test_print_welcome_recent_knowledge(self, mock_console):
        """print_welcome should show 'recent' for age <= 7."""
        print_welcome("Expert", "Domain", 10, "2024-01-01", knowledge_age_days=5)
        assert mock_console.print.called

    @patch("deepr.cli.ui.console")
    def test_print_welcome_old_knowledge(self, mock_console):
        """print_welcome should show days for age > 30."""
        print_welcome("Expert", "Domain", 10, "2024-01-01", knowledge_age_days=45)
        assert mock_console.print.called

    @patch("deepr.cli.ui.console")
    def test_print_user_input(self, mock_console):
        """print_user_input should format user message."""
        print_user_input("test message")

        # Should print "You: message" and empty line
        assert mock_console.print.call_count == 2
        first_call = mock_console.print.call_args_list[0][0][0]
        assert "You" in first_call
        assert "test message" in first_call

    @patch("deepr.cli.ui.console")
    def test_print_tool_use(self, mock_console):
        """print_tool_use should print tool details."""
        print_tool_use("search", "Searching documents...")

        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Searching documents..." in call_args

    @patch("deepr.cli.ui.console")
    def test_print_divider(self, mock_console):
        """print_divider should print line divider."""
        print_divider()

        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "─" in call_args

    @patch("deepr.cli.ui.console")
    def test_print_tool_summary(self, mock_console):
        """print_tool_summary should show tool, duration, cost."""
        print_tool_summary("search", duration=1.5, cost=0.025)

        # Should print summary and divider
        assert mock_console.print.call_count >= 2

    @patch("deepr.cli.ui.console")
    def test_stream_response(self, mock_console):
        """stream_response should print expert name and markdown."""
        stream_response("TestExpert", "This is the response text.")

        # Should print expert name, empty lines, and markdown
        assert mock_console.print.call_count >= 3

    @patch("deepr.cli.ui.console")
    def test_print_error(self, mock_console):
        """print_error should format error message in red."""
        print_error("Something went wrong")

        assert mock_console.print.call_count == 2
        first_call = mock_console.print.call_args_list[0][0][0]
        assert "Error" in first_call
        assert "Something went wrong" in first_call

    @patch("deepr.cli.ui.console")
    @patch("deepr.cli.ui.Live")
    def test_print_thinking_with_spinner(self, mock_live, mock_console):
        """print_thinking should return Live context when spinner enabled."""
        result = print_thinking("Processing...", with_spinner=True)

        # Should return Live object
        mock_live.assert_called_once()

    @patch("deepr.cli.ui.console")
    def test_print_thinking_without_spinner(self, mock_console):
        """print_thinking should print directly when spinner disabled."""
        print_thinking("Processing...", with_spinner=False)

        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "Processing..." in call_args
