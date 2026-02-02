"""Tests for team architect service."""

import json
import pytest
from unittest.mock import patch, MagicMock
from tests.unit.test_services.conftest import make_chat_response


class TestTeamArchitect:
    """Test TeamArchitect team design."""

    @pytest.fixture
    def mock_client(self):
        return MagicMock()

    @pytest.fixture
    def architect(self, mock_client):
        with patch("deepr.services.team_architect.OpenAI", return_value=mock_client):
            from deepr.services.team_architect import TeamArchitect
            return TeamArchitect(api_key="test-key")

    def test_init_with_api_key(self):
        """Direct API key accepted."""
        with patch("deepr.services.team_architect.OpenAI"):
            from deepr.services.team_architect import TeamArchitect
            a = TeamArchitect(api_key="direct-key")
            assert a.api_key == "direct-key"

    def test_init_with_env_key(self, mock_openai_env):
        """Falls back to OPENAI_API_KEY env."""
        with patch("deepr.services.team_architect.OpenAI"):
            from deepr.services.team_architect import TeamArchitect
            a = TeamArchitect()
            assert a.api_key == "sk-test-key-not-real"

    def test_init_no_key_raises(self, monkeypatch):
        """No API key raises ValueError."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with patch("deepr.services.team_architect.OpenAI"):
            from deepr.services.team_architect import TeamArchitect
            with pytest.raises(ValueError, match="OPENAI_API_KEY not found"):
                TeamArchitect()

    def test_design_team_returns_list(self, architect, mock_client):
        """design_team returns list of team member dicts."""
        mock_client.chat.completions.create.return_value = make_chat_response({
            "team": [
                {"role": "Analyst", "focus": "Data", "perspective": "data-driven", "rationale": "Need data"},
            ],
            "team_rationale": "Good team",
        })
        result = architect.design_team("Should we pivot?")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["role"] == "Analyst"

    def test_design_team_calls_api(self, architect, mock_client):
        """design_team calls chat.completions.create."""
        mock_client.chat.completions.create.return_value = make_chat_response({
            "team": [], "team_rationale": "",
        })
        architect.design_team("Question")
        mock_client.chat.completions.create.assert_called_once()

    def test_design_team_uses_json_format(self, architect, mock_client):
        """Uses response_format json_object."""
        mock_client.chat.completions.create.return_value = make_chat_response({
            "team": [], "team_rationale": "",
        })
        architect.design_team("Question")
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_design_team_with_context(self, architect, mock_client):
        """Context is included in the prompt."""
        mock_client.chat.completions.create.return_value = make_chat_response({
            "team": [], "team_rationale": "",
        })
        architect.design_team("Question", context="We are a startup")
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        user_msg = call_kwargs["messages"][1]["content"]
        assert "We are a startup" in user_msg

    def test_design_team_with_perspective_lens(self, architect, mock_client):
        """Perspective lens text appears in prompt."""
        mock_client.chat.completions.create.return_value = make_chat_response({
            "team": [], "team_rationale": "",
        })
        architect.design_team("Question", perspective_lens="Japanese business culture")
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        user_msg = call_kwargs["messages"][1]["content"]
        assert "Japanese business culture" in user_msg

    def test_design_team_adversarial_mode(self, architect, mock_client):
        """Adversarial mode adds skeptical emphasis to prompt."""
        mock_client.chat.completions.create.return_value = make_chat_response({
            "team": [], "team_rationale": "",
        })
        architect.design_team("Question", adversarial=True)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        user_msg = call_kwargs["messages"][1]["content"]
        assert "ADVERSARIAL" in user_msg

    def test_design_team_with_company(self, architect, mock_client):
        """research_company triggers _research_company_people."""
        # First call = company research, second = team design
        mock_client.chat.completions.create.side_effect = [
            make_chat_response({"executives": [], "board": [], "summary": "A company"}),
            make_chat_response({"team": [{"role": "Lead"}], "team_rationale": ""}),
        ]
        result = architect.design_team("Question", research_company="Acme Corp")
        assert mock_client.chat.completions.create.call_count == 2

    def test_research_company_people_success(self, architect, mock_client):
        """Returns parsed JSON on success."""
        intel = {"executives": [{"name": "Jane Doe", "role": "CEO"}], "board": [], "summary": "Tech company"}
        mock_client.chat.completions.create.return_value = make_chat_response(intel)
        result = architect._research_company_people("TestCo")
        assert result["executives"][0]["name"] == "Jane Doe"

    def test_research_company_people_error(self, architect, mock_client):
        """Returns None on exception."""
        mock_client.chat.completions.create.side_effect = Exception("API error")
        result = architect._research_company_people("FailCo")
        assert result is None


class TestTeamSynthesizer:
    """Test TeamSynthesizer synthesis logic."""

    @pytest.fixture
    def mock_client(self):
        return MagicMock()

    @pytest.fixture
    def synthesizer(self, mock_client):
        with patch("deepr.services.team_architect.OpenAI", return_value=mock_client):
            from deepr.services.team_architect import TeamSynthesizer
            return TeamSynthesizer(api_key="test-key")

    def test_init_with_api_key(self):
        """Direct API key accepted."""
        with patch("deepr.services.team_architect.OpenAI"):
            from deepr.services.team_architect import TeamSynthesizer
            s = TeamSynthesizer(api_key="direct-key")
            assert s.api_key == "direct-key"

    def test_init_no_key_raises(self, monkeypatch):
        """No API key raises ValueError."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with patch("deepr.services.team_architect.OpenAI"):
            from deepr.services.team_architect import TeamSynthesizer
            with pytest.raises(ValueError, match="OPENAI_API_KEY not found"):
                TeamSynthesizer()

    def test_synthesize_calls_api(self, synthesizer, mock_client):
        """synthesize calls chat.completions.create."""
        mock_client.chat.completions.create.return_value = make_chat_response("# Synthesis Report")
        synthesizer.synthesize_with_conflict_analysis("Q", [])
        mock_client.chat.completions.create.assert_called_once()

    def test_synthesize_returns_string(self, synthesizer, mock_client):
        """Returns markdown content string."""
        mock_client.chat.completions.create.return_value = make_chat_response("# Report\n\nFindings here")
        result = synthesizer.synthesize_with_conflict_analysis("Q", [])
        assert isinstance(result, str)
        assert "Report" in result

    def test_synthesize_includes_team_results(self, synthesizer, mock_client):
        """Team findings appear in prompt."""
        mock_client.chat.completions.create.return_value = make_chat_response("Report")
        team_results = [
            {
                "team_member": {"role": "Analyst", "perspective": "data", "focus": "market"},
                "result": "Market is growing 20%",
            },
        ]
        synthesizer.synthesize_with_conflict_analysis("Question", team_results)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        user_msg = call_kwargs["messages"][1]["content"]
        assert "Analyst" in user_msg
        assert "Market is growing" in user_msg

    def test_synthesize_empty_results(self, synthesizer, mock_client):
        """Handles empty team_results list."""
        mock_client.chat.completions.create.return_value = make_chat_response("Empty synthesis")
        result = synthesizer.synthesize_with_conflict_analysis("Q", [])
        assert isinstance(result, str)

    def test_build_synthesis_prompt_format(self, synthesizer):
        """Prompt contains required sections."""
        prompt = synthesizer._build_synthesis_prompt("Test Q", [])
        assert "# Research Question" in prompt
        assert "Test Q" in prompt
        assert "## Team Findings" in prompt

    def test_build_synthesis_prompt_attributions(self, synthesizer):
        """Team member roles appear in prompt."""
        results = [
            {
                "team_member": {"role": "Market Expert", "perspective": "data-driven", "focus": "trends"},
                "result": "Key findings",
            },
        ]
        prompt = synthesizer._build_synthesis_prompt("Q", results)
        assert "Market Expert" in prompt
        assert "data-driven" in prompt
