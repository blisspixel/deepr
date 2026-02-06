"""Tests for prompt refiner service."""

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.test_services.conftest import make_chat_response


class TestPromptRefiner:
    """Test PromptRefiner prompt optimization."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock OpenAI client."""
        return MagicMock()

    @pytest.fixture
    def refiner(self, mock_client, mock_openai_env):
        """Create PromptRefiner with mocked client."""
        with patch("deepr.services.prompt_refiner.OpenAI", return_value=mock_client):
            from deepr.services.prompt_refiner import PromptRefiner

            return PromptRefiner()

    def test_init_default_model(self, mock_openai_env):
        """Default model is gpt-5-mini."""
        with patch("deepr.services.prompt_refiner.OpenAI"):
            from deepr.services.prompt_refiner import PromptRefiner

            r = PromptRefiner()
            assert r.model == "gpt-5-mini"

    def test_init_custom_model(self, mock_openai_env):
        """Custom model accepted."""
        with patch("deepr.services.prompt_refiner.OpenAI"):
            from deepr.services.prompt_refiner import PromptRefiner

            r = PromptRefiner(model="gpt-5")
            assert r.model == "gpt-5"

    def test_refine_calls_chat_completions(self, refiner, mock_client):
        """refine() calls chat.completions.create."""
        mock_client.chat.completions.create.return_value = make_chat_response(
            {
                "refined_prompt": "Better prompt",
                "changes_made": ["Added date context"],
            }
        )
        refiner.refine("test prompt")
        mock_client.chat.completions.create.assert_called_once()

    def test_refine_uses_json_format(self, refiner, mock_client):
        """refine() requests JSON response format."""
        mock_client.chat.completions.create.return_value = make_chat_response(
            {
                "refined_prompt": "Better",
                "changes_made": [],
            }
        )
        refiner.refine("test")
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_refine_includes_current_date(self, refiner, mock_client):
        """System prompt contains current month/year."""
        mock_client.chat.completions.create.return_value = make_chat_response(
            {
                "refined_prompt": "Better",
                "changes_made": [],
            }
        )
        refiner.refine("test")
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        system_content = messages[0]["content"]
        # Should contain month name and year
        import datetime

        current = datetime.datetime.now().strftime("%B %Y")
        assert current in system_content

    def test_refine_returns_refined_prompt(self, refiner, mock_client):
        """Result contains refined_prompt key."""
        mock_client.chat.completions.create.return_value = make_chat_response(
            {
                "refined_prompt": "Improved query",
                "changes_made": ["clarity"],
            }
        )
        result = refiner.refine("test")
        assert result["refined_prompt"] == "Improved query"

    def test_refine_returns_changes_made(self, refiner, mock_client):
        """Result contains changes_made key."""
        mock_client.chat.completions.create.return_value = make_chat_response(
            {
                "refined_prompt": "Better",
                "changes_made": ["Added temporal context", "Structured output"],
            }
        )
        result = refiner.refine("test")
        assert len(result["changes_made"]) == 2

    def test_refine_preserves_original_prompt(self, refiner, mock_client):
        """Result includes the original_prompt."""
        mock_client.chat.completions.create.return_value = make_chat_response(
            {
                "refined_prompt": "Better",
                "changes_made": [],
            }
        )
        result = refiner.refine("my original query")
        assert result["original_prompt"] == "my original query"

    def test_refine_with_files_flag(self, refiner, mock_client):
        """has_files=True changes the system prompt."""
        mock_client.chat.completions.create.return_value = make_chat_response(
            {
                "refined_prompt": "Better",
                "changes_made": [],
            }
        )
        refiner.refine("test", has_files=True)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        system_content = call_kwargs["messages"][0]["content"]
        assert "Yes - user has provided documents" in system_content

    def test_refine_without_files_flag(self, refiner, mock_client):
        """has_files=False is the default."""
        mock_client.chat.completions.create.return_value = make_chat_response(
            {
                "refined_prompt": "Better",
                "changes_made": [],
            }
        )
        refiner.refine("test")
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        system_content = call_kwargs["messages"][0]["content"]
        assert "No" in system_content
