"""Tests for prompt refiner service."""

from types import SimpleNamespace
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
        with (
            patch("deepr.services.prompt_refiner.OpenAI", return_value=mock_client),
            patch(
                "deepr.services.metered_call.execute_reserved_sync_call",
                side_effect=lambda **kwargs: kwargs["call"](),
            ),
        ):
            from deepr.services.prompt_refiner import PromptRefiner

            yield PromptRefiner()

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
        assert call_kwargs["max_completion_tokens"] == 1_200

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

    def test_reservation_failure_prevents_client_construction(self, mock_openai_env):
        """No provider object exists until durable admission succeeds."""
        from deepr.services.metered_call import MeteredCallAccountingError
        from deepr.services.prompt_refiner import PromptRefiner

        with (
            patch("deepr.services.prompt_refiner.OpenAI") as constructor,
            patch(
                "deepr.services.metered_call.reserve_configured_cost_ceiling",
                side_effect=OSError("reservation unavailable"),
            ),
        ):
            refiner = PromptRefiner()
            assert constructor.call_count == 0
            with pytest.raises(MeteredCallAccountingError, match="reservation failed"):
                refiner.refine("bounded prompt")
            assert constructor.call_count == 0

    def test_reserved_call_constructs_bounded_nonretrying_client(self, mock_openai_env):
        """Reservation and dispatch mark precede one bounded SDK call."""
        from deepr.services.prompt_refiner import PromptRefiner

        events: list[str] = []
        client = MagicMock()
        client.chat.completions.create.return_value = make_chat_response(
            {"refined_prompt": "Better", "changes_made": []}
        )
        reservation = SimpleNamespace(reservation_id="reservation-1", estimated_cost=0.25)

        def reserve(**_kwargs):
            events.append("reserve")
            return reservation

        def mark(_reservation):
            events.append("mark")

        def construct(**kwargs):
            events.append("construct")
            assert kwargs["max_retries"] == 0
            return client

        def settle(_reservation, **_kwargs):
            events.append("settle")

        with (
            patch("deepr.services.metered_call.reserve_configured_cost_ceiling", side_effect=reserve),
            patch("deepr.services.metered_call._mark_provider_dispatch", side_effect=mark),
            patch("deepr.services.metered_call.settle_research_cost", side_effect=settle),
            patch("deepr.services.prompt_refiner.OpenAI", side_effect=construct) as constructor,
        ):
            refiner = PromptRefiner()
            constructor.assert_not_called()
            refiner.refine("bounded prompt")

        assert events == ["reserve", "mark", "construct", "settle"]
        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_completion_tokens"] == 1_200
        assert client.chat.completions.create.call_count == 1

    def test_ambiguous_provider_failure_settles_full_ceiling_once(self, mock_openai_env):
        """A timeout is never replayed and consumes the conservative hold."""
        from deepr.services.prompt_refiner import PromptRefiner

        client = MagicMock()
        client.chat.completions.create.side_effect = TimeoutError("ambiguous provider outcome")
        reservation = SimpleNamespace(reservation_id="reservation-2", estimated_cost=0.25)

        with (
            patch(
                "deepr.services.metered_call.reserve_configured_cost_ceiling",
                return_value=reservation,
            ),
            patch("deepr.services.metered_call._mark_provider_dispatch"),
            patch("deepr.services.metered_call.settle_research_cost") as settle,
            patch("deepr.services.prompt_refiner.OpenAI", return_value=client),
        ):
            with pytest.raises(TimeoutError, match="ambiguous provider outcome"):
                PromptRefiner().refine("bounded prompt")

        assert client.chat.completions.create.call_count == 1
        settle.assert_called_once()
        assert settle.call_args.kwargs["actual_cost"] is None
        assert settle.call_args.kwargs["actual_cost_reported"] is False
        assert settle.call_args.kwargs["settlement_metadata"] == {
            "metered_call_settlement_reason": "provider_call_failed"
        }
