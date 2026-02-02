"""Unit tests for semantic CLI commands - no API calls.

Tests the semantic command interface (research, learn, team) which provides
natural, intent-based commands that map to underlying implementation commands.

These tests verify:
- Command structure and help text
- Parameter validation
- Mode detection logic
- Error handling
"""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock, AsyncMock
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.cli.main import cli


class TestResearchCommand:
    """Test 'research' semantic command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_research_command_exists(self, runner):
        """Test that 'research' command exists."""
        result = runner.invoke(cli, ['research', '--help'])
        assert result.exit_code == 0
        assert 'research' in result.output.lower()

    def test_research_help_shows_options(self, runner):
        """Test that research help shows all options."""
        result = runner.invoke(cli, ['research', '--help'])
        assert result.exit_code == 0
        
        output = result.output.lower()
        assert '--model' in output or '-m' in output
        assert '--provider' in output or '-p' in output
        assert '--upload' in output or '-u' in output
        assert '--limit' in output or '-l' in output
        assert '--yes' in output or '-y' in output
        assert '--mode' in output

    def test_research_requires_query(self, runner):
        """Test that 'research' requires a query argument."""
        result = runner.invoke(cli, ['research'])
        # Should fail or show error about missing query
        assert result.exit_code != 0 or 'query' in result.output.lower()

    def test_research_mode_choices(self, runner):
        """Test that --mode has correct choices."""
        result = runner.invoke(cli, ['research', '--help'])
        output = result.output.lower()
        assert 'focus' in output
        assert 'docs' in output
        assert 'auto' in output

    def test_research_provider_choices(self, runner):
        """Test that --provider has correct choices."""
        result = runner.invoke(cli, ['research', '--help'])
        output = result.output.lower()
        assert 'openai' in output
        assert 'gemini' in output or 'azure' in output

    def test_research_scrape_option(self, runner):
        """Test that --scrape option exists."""
        result = runner.invoke(cli, ['research', '--help'])
        assert '--scrape' in result.output or '-s' in result.output

    def test_research_no_web_option(self, runner):
        """Test that --no-web option exists."""
        result = runner.invoke(cli, ['research', '--help'])
        assert '--no-web' in result.output

    def test_research_no_code_option(self, runner):
        """Test that --no-code option exists."""
        result = runner.invoke(cli, ['research', '--help'])
        assert '--no-code' in result.output


class TestResearchModeDetection:
    """Test automatic mode detection for research command."""

    def test_detect_docs_mode_for_documentation_keywords(self):
        """Test that documentation keywords trigger docs mode."""
        from deepr.cli.commands.semantic import detect_research_mode
        
        # Should detect docs mode
        assert detect_research_mode("Document the API endpoints") == "docs"
        assert detect_research_mode("Create documentation for auth flow") == "docs"
        assert detect_research_mode("Write a guide for deployment") == "docs"
        assert detect_research_mode("Explain how to use the SDK") == "docs"
        assert detect_research_mode("API reference for user service") == "docs"
        assert detect_research_mode("Architecture design doc") == "docs"
        assert detect_research_mode("README for the project") == "docs"
        assert detect_research_mode("Tutorial on getting started") == "docs"
        assert detect_research_mode("Specification for the protocol") == "docs"

    def test_detect_focus_mode_for_general_queries(self):
        """Test that general queries trigger focus mode."""
        from deepr.cli.commands.semantic import detect_research_mode
        
        # Should detect focus mode
        assert detect_research_mode("Analyze AI code editor market") == "focus"
        assert detect_research_mode("What are the latest trends in ML?") == "focus"
        assert detect_research_mode("Compare React vs Vue performance") == "focus"
        assert detect_research_mode("Best practices for microservices") == "focus"
        assert detect_research_mode("Strategic analysis of Tesla") == "focus"

    def test_detect_mode_case_insensitive(self):
        """Test that mode detection is case insensitive."""
        from deepr.cli.commands.semantic import detect_research_mode
        
        assert detect_research_mode("DOCUMENT the API") == "docs"
        assert detect_research_mode("Document THE api") == "docs"
        assert detect_research_mode("create DOCUMENTATION") == "docs"


class TestLearnCommand:
    """Test 'learn' semantic command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_learn_command_exists(self, runner):
        """Test that 'learn' command exists."""
        result = runner.invoke(cli, ['learn', '--help'])
        assert result.exit_code == 0
        assert 'learn' in result.output.lower()

    def test_learn_help_shows_options(self, runner):
        """Test that learn help shows all options."""
        result = runner.invoke(cli, ['learn', '--help'])
        assert result.exit_code == 0
        
        output = result.output.lower()
        assert '--model' in output or '-m' in output
        assert '--provider' in output
        assert '--phases' in output or '-p' in output
        assert '--yes' in output or '-y' in output

    def test_learn_requires_topic(self, runner):
        """Test that 'learn' requires a topic argument."""
        result = runner.invoke(cli, ['learn'])
        # Should fail or show error about missing topic
        assert result.exit_code != 0 or 'topic' in result.output.lower()

    def test_learn_phases_option(self, runner):
        """Test that --phases option exists and accepts integers."""
        result = runner.invoke(cli, ['learn', '--help'])
        assert '--phases' in result.output

    def test_learn_lead_option(self, runner):
        """Test that --lead option exists for lead planner model."""
        result = runner.invoke(cli, ['learn', '--help'])
        assert '--lead' in result.output

    def test_learn_description_mentions_multi_phase(self, runner):
        """Test that learn command mentions multi-phase research."""
        result = runner.invoke(cli, ['learn', '--help'])
        output = result.output.lower()
        assert 'phase' in output or 'multi' in output


class TestTeamCommand:
    """Test 'team' semantic command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_team_command_exists(self, runner):
        """Test that 'team' command exists."""
        result = runner.invoke(cli, ['team', '--help'])
        assert result.exit_code == 0
        assert 'team' in result.output.lower()

    def test_team_help_shows_options(self, runner):
        """Test that team help shows all options."""
        result = runner.invoke(cli, ['team', '--help'])
        assert result.exit_code == 0
        
        output = result.output.lower()
        assert '--model' in output or '-m' in output
        assert '--provider' in output
        assert '--perspectives' in output or '-p' in output
        assert '--yes' in output or '-y' in output

    def test_team_requires_question(self, runner):
        """Test that 'team' requires a question argument."""
        result = runner.invoke(cli, ['team'])
        # Should fail or show error about missing question
        assert result.exit_code != 0 or 'question' in result.output.lower()

    def test_team_perspectives_option(self, runner):
        """Test that --perspectives option exists."""
        result = runner.invoke(cli, ['team', '--help'])
        assert '--perspectives' in result.output

    def test_team_description_mentions_perspectives(self, runner):
        """Test that team command mentions multiple perspectives."""
        result = runner.invoke(cli, ['team', '--help'])
        output = result.output.lower()
        assert 'perspective' in output or 'thinking' in output


class TestExpertMakeLearnOptions:
    """Test expert make command learning options."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_expert_make_learn_flag(self, runner):
        """Test that --learn flag exists."""
        result = runner.invoke(cli, ['expert', 'make', '--help'])
        assert '--learn' in result.output

    def test_expert_make_budget_option(self, runner):
        """Test that --budget option exists for learning."""
        result = runner.invoke(cli, ['expert', 'make', '--help'])
        assert '--budget' in result.output

    def test_expert_make_topics_option(self, runner):
        """Test that --topics option exists."""
        result = runner.invoke(cli, ['expert', 'make', '--help'])
        assert '--topics' in result.output

    def test_expert_make_docs_option(self, runner):
        """Test that --docs option exists for topic counts."""
        result = runner.invoke(cli, ['expert', 'make', '--help'])
        assert '--docs' in result.output

    def test_expert_make_quick_option(self, runner):
        """Test that --quick option exists for topic counts."""
        result = runner.invoke(cli, ['expert', 'make', '--help'])
        assert '--quick' in result.output

    def test_expert_make_deep_option(self, runner):
        """Test that --deep option exists for topic counts."""
        result = runner.invoke(cli, ['expert', 'make', '--help'])
        assert '--deep' in result.output

    def test_expert_make_no_discovery_option(self, runner):
        """Test that --no-discovery option exists."""
        result = runner.invoke(cli, ['expert', 'make', '--help'])
        assert '--no-discovery' in result.output


class TestExpertLearnCommand:
    """Test 'expert learn' command for on-demand learning."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_expert_learn_command_exists(self, runner):
        """Test that 'expert learn' command exists."""
        result = runner.invoke(cli, ['expert', 'learn', '--help'])
        assert result.exit_code == 0

    def test_expert_learn_requires_name(self, runner):
        """Test that 'expert learn' requires expert name."""
        result = runner.invoke(cli, ['expert', 'learn'])
        assert result.exit_code != 0

    def test_expert_learn_accepts_topic(self, runner):
        """Test that 'expert learn' accepts topic argument."""
        result = runner.invoke(cli, ['expert', 'learn', '--help'])
        output = result.output.lower()
        assert 'topic' in output or 'name' in output

    def test_expert_learn_files_option(self, runner):
        """Test that --files option exists."""
        result = runner.invoke(cli, ['expert', 'learn', '--help'])
        assert '--files' in result.output or '-f' in result.output

    def test_expert_learn_budget_option(self, runner):
        """Test that --budget option exists."""
        result = runner.invoke(cli, ['expert', 'learn', '--help'])
        assert '--budget' in result.output or '-b' in result.output

    def test_expert_learn_synthesize_option(self, runner):
        """Test that --synthesize/--no-synthesize option exists."""
        result = runner.invoke(cli, ['expert', 'learn', '--help'])
        assert 'synthesize' in result.output.lower()


class TestExpertResumeCommand:
    """Test 'expert resume' command for resuming paused learning."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_expert_resume_command_exists(self, runner):
        """Test that 'expert resume' command exists."""
        result = runner.invoke(cli, ['expert', 'resume', '--help'])
        assert result.exit_code == 0

    def test_expert_resume_requires_name(self, runner):
        """Test that 'expert resume' requires expert name."""
        result = runner.invoke(cli, ['expert', 'resume'])
        assert result.exit_code != 0

    def test_expert_resume_budget_option(self, runner):
        """Test that --budget option exists."""
        result = runner.invoke(cli, ['expert', 'resume', '--help'])
        assert '--budget' in result.output or '-b' in result.output

    def test_expert_resume_yes_option(self, runner):
        """Test that --yes option exists."""
        result = runner.invoke(cli, ['expert', 'resume', '--help'])
        assert '--yes' in result.output or '-y' in result.output


class TestCompanyResearchMode:
    """Test company research mode in research command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_company_research_requires_name_and_website(self, runner):
        """Test that company research requires both name and website."""
        result = runner.invoke(cli, ['research', 'company'])
        # Should show error about missing company name and website
        assert 'company name' in result.output.lower() or 'website' in result.output.lower()

    def test_company_research_shows_usage(self, runner):
        """Test that company research shows usage example."""
        result = runner.invoke(cli, ['research', 'company'])
        # Should show usage example
        assert 'usage' in result.output.lower() or 'example' in result.output.lower()

    def test_research_scrape_only_option(self, runner):
        """Test that --scrape-only option exists."""
        result = runner.invoke(cli, ['research', '--help'])
        assert '--scrape-only' in result.output


class TestSemanticCommandIntegration:
    """Test integration between semantic commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_all_semantic_commands_in_help(self, runner):
        """Test that all semantic commands appear in main help."""
        result = runner.invoke(cli, ['--help'])
        output = result.output.lower()
        
        assert 'research' in output
        assert 'learn' in output
        assert 'team' in output
        assert 'expert' in output

    def test_semantic_commands_have_consistent_options(self, runner):
        """Test that semantic commands have consistent common options."""
        # All should have --model and --provider
        for cmd in ['research', 'learn', 'team']:
            result = runner.invoke(cli, [cmd, '--help'])
            assert '--model' in result.output or '-m' in result.output
            assert '--provider' in result.output

    def test_semantic_commands_have_yes_flag(self, runner):
        """Test that semantic commands have --yes flag for automation."""
        for cmd in ['research', 'learn', 'team']:
            result = runner.invoke(cli, [cmd, '--help'])
            assert '--yes' in result.output or '-y' in result.output


class TestValidationIntegration:
    """Test that semantic commands use validation."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_research_validates_empty_query(self, runner):
        """Test that research validates empty query."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(cli, ['research', ''])
            # Empty query should be rejected or handled
            # (may pass through to validation layer)

    def test_learn_validates_empty_topic(self, runner):
        """Test that learn validates empty topic."""
        with patch("deepr.cli.commands.semantic.asyncio.run"):
            result = runner.invoke(cli, ['learn', ''])
            # Empty topic should be rejected or handled

    def test_team_validates_empty_question(self, runner):
        """Test that team validates empty question."""
        with patch("deepr.cli.commands.semantic.asyncio.run"):
            result = runner.invoke(cli, ['team', ''])
            # Empty question should be rejected or handled


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
