"""Tests for research planner service."""

import json
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.test_services.conftest import make_responses_response


class TestResearchPlanner:
    """Test ResearchPlanner planning logic."""

    @pytest.fixture
    def mock_client(self):
        return MagicMock()

    @pytest.fixture
    def planner(self, mock_client, mock_openai_env):
        with patch("deepr.services.research_planner.OpenAI", return_value=mock_client):
            with patch("deepr.services.research_planner.DefaultAzureCredential"):
                with patch("deepr.services.research_planner.get_bearer_token_provider"):
                    from deepr.services.research_planner import ResearchPlanner

                    return ResearchPlanner()

    def test_init_valid_models(self, mock_openai_env):
        """All GPT-5 variants accepted."""
        with patch("deepr.services.research_planner.OpenAI"):
            with patch("deepr.services.research_planner.DefaultAzureCredential"):
                with patch("deepr.services.research_planner.get_bearer_token_provider"):
                    from deepr.services.research_planner import ResearchPlanner

                    for model in ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5-chat"]:
                        p = ResearchPlanner(model=model)
                        assert p.model == model

    def test_init_invalid_model_raises(self, mock_openai_env):
        """Non-GPT-5 models raise ValueError."""
        with patch("deepr.services.research_planner.OpenAI"):
            with patch("deepr.services.research_planner.DefaultAzureCredential"):
                with patch("deepr.services.research_planner.get_bearer_token_provider"):
                    from deepr.services.research_planner import ResearchPlanner

                    with pytest.raises(ValueError, match="Invalid model"):
                        ResearchPlanner(model="gpt-4")

    def test_init_azure_mode(self, mock_openai_env):
        """Azure mode creates client with base_url."""
        with patch("deepr.services.research_planner.OpenAI") as mock_cls:
            with patch("deepr.services.research_planner.DefaultAzureCredential"):
                with patch("deepr.services.research_planner.get_bearer_token_provider", return_value="token"):
                    from deepr.services.research_planner import ResearchPlanner

                    ResearchPlanner(use_azure=True, azure_endpoint="https://myendpoint.openai.azure.com")
                    call_kwargs = mock_cls.call_args[1]
                    assert "myendpoint" in call_kwargs["base_url"]

    def test_plan_research_returns_list(self, planner, mock_client):
        """plan_research returns list of task dicts."""
        tasks = [
            {"title": "Background", "prompt": "Research background"},
            {"title": "Analysis", "prompt": "Analyze trends"},
        ]
        mock_client.responses.create.return_value = make_responses_response(json.dumps(tasks))
        result = planner.plan_research("Test scenario")
        assert isinstance(result, list)
        assert len(result) == 2

    def test_plan_research_clamps_max_tasks(self, planner, mock_client):
        """max_tasks is clamped to 1-10."""
        tasks = [{"title": f"Task {i}", "prompt": f"Do {i}"} for i in range(15)]
        mock_client.responses.create.return_value = make_responses_response(json.dumps(tasks))
        result = planner.plan_research("Scenario", max_tasks=15)
        assert len(result) <= 10

    def test_plan_research_validates_structure(self, planner, mock_client):
        """Each task must have title and prompt."""
        tasks = [
            {"title": "Valid", "prompt": "Has both fields"},
            {"title_only": "Invalid"},  # Missing prompt
            {"title": "Also valid", "prompt": "Yes"},
        ]
        mock_client.responses.create.return_value = make_responses_response(json.dumps(tasks))
        result = planner.plan_research("Scenario")
        assert len(result) == 2  # Only 2 valid tasks

    def test_plan_research_caps_title_length(self, planner, mock_client):
        """Title capped at 100 chars."""
        tasks = [{"title": "x" * 200, "prompt": "Valid prompt"}]
        mock_client.responses.create.return_value = make_responses_response(json.dumps(tasks))
        result = planner.plan_research("Scenario")
        assert len(result[0]["title"]) <= 100

    def test_plan_research_caps_prompt_length(self, planner, mock_client):
        """Prompt capped at 1000 chars."""
        tasks = [{"title": "Title", "prompt": "y" * 2000}]
        mock_client.responses.create.return_value = make_responses_response(json.dumps(tasks))
        result = planner.plan_research("Scenario")
        assert len(result[0]["prompt"]) <= 1000

    def test_plan_research_with_context(self, planner, mock_client):
        """Context is appended to user prompt."""
        tasks = [{"title": "T", "prompt": "P"}]
        mock_client.responses.create.return_value = make_responses_response(json.dumps(tasks))
        planner.plan_research("Scenario", context="Extra context here")
        call_kwargs = mock_client.responses.create.call_args[1]
        user_msg = next(m for m in call_kwargs["input"] if m["role"] == "user")
        assert "Extra context here" in user_msg["content"]

    def test_plan_research_json_in_code_block(self, planner, mock_client):
        """Handles ```json wrapped response."""
        tasks = [{"title": "T", "prompt": "P"}]
        wrapped = f"```json\n{json.dumps(tasks)}\n```"
        mock_client.responses.create.return_value = make_responses_response(wrapped)
        result = planner.plan_research("Scenario")
        assert len(result) == 1

    def test_plan_research_invalid_json_fallback(self, planner, mock_client):
        """Falls back to _fallback_plan on invalid JSON."""
        mock_client.responses.create.return_value = make_responses_response("Not JSON at all")
        result = planner.plan_research("Test scenario", max_tasks=3)
        assert isinstance(result, list)
        assert len(result) <= 3
        # Fallback tasks contain generic research angles
        assert any("Background" in t.get("title", "") for t in result)

    def test_plan_research_empty_list_fallback(self, planner, mock_client):
        """Empty validated list triggers fallback."""
        # All tasks invalid (no title/prompt)
        tasks = [{"bad": "structure"}]
        mock_client.responses.create.return_value = make_responses_response(json.dumps(tasks))
        result = planner.plan_research("Scenario", max_tasks=2)
        assert isinstance(result, list)
        assert len(result) > 0  # Fallback provides tasks

    def test_plan_research_not_a_list_fallback(self, planner, mock_client):
        """Non-list JSON triggers fallback."""
        mock_client.responses.create.return_value = make_responses_response(json.dumps({"not": "a list"}))
        result = planner.plan_research("Scenario")
        assert isinstance(result, list)


class TestResearchPlannerFallback:
    """Test _fallback_plan generation."""

    @pytest.fixture
    def planner(self, mock_openai_env):
        with patch("deepr.services.research_planner.OpenAI"):
            with patch("deepr.services.research_planner.DefaultAzureCredential"):
                with patch("deepr.services.research_planner.get_bearer_token_provider"):
                    from deepr.services.research_planner import ResearchPlanner

                    return ResearchPlanner()

    def test_fallback_returns_tasks(self, planner):
        """Fallback plan returns list of task dicts."""
        result = planner._fallback_plan("Test scenario", 5)
        assert isinstance(result, list)
        assert len(result) == 5
        for task in result:
            assert "title" in task
            assert "prompt" in task

    def test_fallback_respects_max(self, planner):
        """Honors max_tasks parameter."""
        result = planner._fallback_plan("Scenario", 2)
        assert len(result) == 2

    def test_fallback_includes_scenario(self, planner):
        """Scenario text appears in prompts."""
        result = planner._fallback_plan("Quantum computing analysis", 3)
        for task in result:
            assert "Quantum computing" in task["prompt"]


class TestCreatePlanner:
    """Test create_planner factory function."""

    def test_create_openai(self, mock_openai_env):
        """Creates ResearchPlanner for openai."""
        with patch("deepr.services.research_planner.OpenAI"):
            with patch("deepr.services.research_planner.DefaultAzureCredential"):
                with patch("deepr.services.research_planner.get_bearer_token_provider"):
                    from deepr.services.research_planner import create_planner

                    p = create_planner(provider="openai")
                    assert p.use_azure is False

    def test_create_azure(self, mock_openai_env):
        """Creates ResearchPlanner with use_azure=True."""
        with patch("deepr.services.research_planner.OpenAI"):
            with patch("deepr.services.research_planner.DefaultAzureCredential"):
                with patch("deepr.services.research_planner.get_bearer_token_provider"):
                    from deepr.services.research_planner import create_planner

                    p = create_planner(provider="azure", azure_endpoint="https://test.openai.azure.com")
                    assert p.use_azure is True
