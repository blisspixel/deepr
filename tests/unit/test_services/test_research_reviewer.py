"""Tests for research reviewer service."""

import json
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.test_services.conftest import make_responses_response


class TestResearchReviewer:
    """Test ResearchReviewer review and planning logic."""

    @pytest.fixture
    def mock_client(self):
        return MagicMock()

    @pytest.fixture
    def reviewer(self, mock_client, mock_openai_env):
        with patch("deepr.services.research_reviewer.OpenAI", return_value=mock_client):
            from deepr.services.research_reviewer import ResearchReviewer

            return ResearchReviewer()

    def test_init_default_model(self, mock_openai_env):
        """Default model is gpt-5."""
        with patch("deepr.services.research_reviewer.OpenAI"):
            from deepr.services.research_reviewer import ResearchReviewer

            r = ResearchReviewer()
            assert r.model == "gpt-5"

    def test_init_valid_models(self, mock_openai_env):
        """All valid models accepted."""
        with patch("deepr.services.research_reviewer.OpenAI"):
            from deepr.services.research_reviewer import ResearchReviewer

            for model in ["gpt-5", "gpt-5-mini", "gpt-5-nano"]:
                r = ResearchReviewer(model=model)
                assert r.model == model

    def test_init_invalid_model_raises(self, mock_openai_env):
        """Invalid model raises ValueError."""
        with patch("deepr.services.research_reviewer.OpenAI"):
            from deepr.services.research_reviewer import ResearchReviewer

            with pytest.raises(ValueError, match="Invalid model"):
                ResearchReviewer(model="gpt-4")

    def test_review_and_plan_next_calls_api(self, reviewer, mock_client):
        """review_and_plan_next calls responses.create."""
        response_data = json.dumps(
            {
                "status": "continue",
                "analysis": "Need more data",
                "next_tasks": [{"title": "Task 1", "prompt": "Do X", "rationale": "Why"}],
            }
        )
        mock_client.responses.create.return_value = make_responses_response(response_data)
        reviewer.review_and_plan_next("Test scenario", [], current_phase=1)
        mock_client.responses.create.assert_called_once()

    def test_review_and_plan_next_continue(self, reviewer, mock_client):
        """Returns status='continue' with tasks when more research needed."""
        response_data = json.dumps(
            {
                "status": "continue",
                "analysis": "Gaps found",
                "next_tasks": [{"title": "Fill gap", "prompt": "Research X", "rationale": "Missing"}],
            }
        )
        mock_client.responses.create.return_value = make_responses_response(response_data)
        result = reviewer.review_and_plan_next("Scenario", [], current_phase=1)
        assert result["status"] == "continue"
        assert len(result["next_tasks"]) == 1

    def test_review_and_plan_next_ready_synthesis(self, reviewer, mock_client):
        """Returns status='ready_for_synthesis' when research is complete."""
        response_data = json.dumps(
            {
                "status": "ready_for_synthesis",
                "analysis": "Sufficient data",
                "next_tasks": [{"title": "Synthesize", "prompt": "Combine all", "rationale": "Ready"}],
            }
        )
        mock_client.responses.create.return_value = make_responses_response(response_data)
        result = reviewer.review_and_plan_next("Scenario", [], current_phase=2)
        assert result["status"] == "ready_for_synthesis"

    def test_review_and_plan_next_sets_phase(self, reviewer, mock_client):
        """phase = current_phase + 1."""
        response_data = json.dumps(
            {
                "status": "continue",
                "analysis": "More needed",
                "next_tasks": [],
            }
        )
        mock_client.responses.create.return_value = make_responses_response(response_data)
        result = reviewer.review_and_plan_next("Scenario", [], current_phase=3)
        assert result["phase"] == 4

    def test_review_and_plan_next_json_parse_error(self, reviewer, mock_client):
        """Falls back to synthesis on invalid JSON."""
        mock_client.responses.create.return_value = make_responses_response("Not valid JSON {{{")
        result = reviewer.review_and_plan_next("Scenario", [], current_phase=1)
        assert result["status"] == "ready_for_synthesis"
        assert result["phase"] == 2
        assert len(result["next_tasks"]) == 1
        assert "synthesis" in result["next_tasks"][0]["title"].lower()

    def test_summarize_truncates_long_results(self, reviewer):
        """Results longer than 2000 chars are truncated."""
        results = [{"title": "Long", "result": "x" * 3000}]
        summary = reviewer._summarize_completed_research(results)
        assert "...(truncated)" in summary

    def test_summarize_numbered_tasks(self, reviewer):
        """Each task is numbered correctly."""
        results = [
            {"title": "First", "result": "Data 1"},
            {"title": "Second", "result": "Data 2"},
        ]
        summary = reviewer._summarize_completed_research(results)
        assert "## Task 1: First" in summary
        assert "## Task 2: Second" in summary

    def test_extract_response_text_output_text(self, reviewer):
        """Handles response with output_text attribute."""
        mock_resp = MagicMock()
        mock_resp.output_text = "Direct text"
        assert reviewer._extract_response_text(mock_resp) == "Direct text"

    def test_extract_response_text_output_list(self, reviewer):
        """Handles response with output array of messages."""
        mock_content = MagicMock()
        mock_content.type = "output_text"
        mock_content.text = "From output list"
        mock_item = MagicMock()
        mock_item.type = "message"
        mock_item.content = [mock_content]
        mock_resp = MagicMock(spec=[])  # No output_text attribute
        mock_resp.output = [mock_item]
        assert reviewer._extract_response_text(mock_resp) == "From output list"

    def test_extract_response_text_fallback(self, reviewer):
        """Falls back to str(response) when no known format."""
        mock_resp = MagicMock(spec=[])  # No output_text
        mock_resp.output = []
        result = reviewer._extract_response_text(mock_resp)
        assert isinstance(result, str)
        assert len(result) > 0


class TestResearchReviewerHelpers:
    """Test helper methods."""

    def test_should_continue_true(self):
        """status='continue' returns True."""
        from deepr.services.research_reviewer import ResearchReviewer

        # Call as static-like (doesn't need client)
        assert ResearchReviewer.should_continue(None, {"status": "continue"}) is True

    def test_should_continue_false(self):
        """Other statuses return False."""
        from deepr.services.research_reviewer import ResearchReviewer

        assert ResearchReviewer.should_continue(None, {"status": "ready_for_synthesis"}) is False
        assert ResearchReviewer.should_continue(None, {"status": "done"}) is False

    def test_is_ready_for_synthesis_true(self):
        """status='ready_for_synthesis' returns True."""
        from deepr.services.research_reviewer import ResearchReviewer

        assert ResearchReviewer.is_ready_for_synthesis(None, {"status": "ready_for_synthesis"}) is True

    def test_is_ready_for_synthesis_false(self):
        """Other statuses return False."""
        from deepr.services.research_reviewer import ResearchReviewer

        assert ResearchReviewer.is_ready_for_synthesis(None, {"status": "continue"}) is False
