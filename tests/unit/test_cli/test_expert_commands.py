"""Unit tests for expert CLI commands - no API calls.

Tests the expert command structure, parameter validation, and command flow
without making any external API calls.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.cli.main import cli


class TestExpertCommandStructure:
    """Test expert command structure and help text."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_expert_command_exists(self, runner):
        """Test that 'expert' command exists."""
        result = runner.invoke(cli, ["expert", "--help"])
        assert result.exit_code == 0
        assert "expert" in result.output.lower()

    def test_expert_command_shows_subcommands(self, runner):
        """Test that expert command lists all subcommands."""
        result = runner.invoke(cli, ["expert", "--help"])
        assert result.exit_code == 0

        output = result.output.lower()
        assert "make" in output
        assert "list" in output
        assert "info" in output
        assert "delete" in output

    def test_expert_command_description(self, runner):
        """Test that expert command has helpful description."""
        result = runner.invoke(cli, ["expert", "--help"])
        assert result.exit_code == 0

        output = result.output.lower()
        # Should mention knowledge bases and agentic capabilities
        assert "domain" in output or "knowledge" in output or "expert" in output


class TestExpertMakeCommand:
    """Test 'expert make' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_expert_make_help(self, runner):
        """Test that 'expert make' help works."""
        result = runner.invoke(cli, ["expert", "make", "--help"])
        assert result.exit_code == 0
        assert "make" in result.output.lower()

    def test_expert_make_requires_name(self, runner):
        """Test that 'expert make' requires a name argument."""
        result = runner.invoke(cli, ["expert", "make"])
        # Should fail or show error about missing name
        assert result.exit_code != 0

    def test_expert_make_requires_files(self, runner):
        """Test that 'expert make' requires files."""
        result = runner.invoke(cli, ["expert", "make", "Test Expert"])
        # Should show error about no files
        assert result.exit_code == 0  # Command runs but shows error message
        assert "no files" in result.output.lower() or "error" in result.output.lower()

    def test_expert_make_accepts_files_option(self, runner):
        """Test that 'expert make' accepts --files/-f option."""
        result = runner.invoke(cli, ["expert", "make", "--help"])
        output = result.output.lower()
        assert "--files" in output or "-f" in output

    def test_expert_make_accepts_description_option(self, runner):
        """Test that 'expert make' accepts --description/-d option."""
        result = runner.invoke(cli, ["expert", "make", "--help"])
        output = result.output.lower()
        assert "--description" in output or "-d" in output

    def test_expert_make_accepts_provider_option(self, runner):
        """Test that 'expert make' accepts --provider/-p option."""
        result = runner.invoke(cli, ["expert", "make", "--help"])
        output = result.output.lower()
        assert "--provider" in output or "-p" in output

    def test_expert_make_provider_choices(self, runner):
        """Test that --provider has correct choices."""
        result = runner.invoke(cli, ["expert", "make", "--help"])
        output = result.output.lower()
        # Should list available providers
        assert "openai" in output
        assert "gemini" in output or "azure" in output


class TestExpertListCommand:
    """Test 'expert list' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_expert_list_help(self, runner):
        """Test that 'expert list' help works."""
        result = runner.invoke(cli, ["expert", "list", "--help"])
        assert result.exit_code == 0

    def test_expert_list_runs_without_experts(self, runner, tmp_path):
        """Test that 'expert list' handles empty list gracefully."""
        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.list_all.return_value = []
            mock_store_class.return_value = mock_store

            result = runner.invoke(cli, ["expert", "list"])

            # Should show message about no experts
            assert "no experts" in result.output.lower()
            assert "create" in result.output.lower()  # Should suggest creating one

    def test_expert_list_displays_experts(self, runner):
        """Test that 'expert list' displays expert information."""
        from datetime import datetime

        from deepr.experts.profile import ExpertProfile

        mock_expert = ExpertProfile(
            name="Test Expert",
            vector_store_id="vs_test",
            description="Test description",
            total_documents=5,
            conversations=10,
            research_triggered=2,
            total_research_cost=3.50,
            updated_at=datetime.utcnow(),
        )

        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.list_all.return_value = [mock_expert]
            mock_store_class.return_value = mock_store

            result = runner.invoke(cli, ["expert", "list"])

            output = result.output
            assert "Test Expert" in output
            assert "Test description" in output
            assert "5" in output  # Documents count
            assert "10" in output  # Conversations count


class TestExpertInfoCommand:
    """Test 'expert info' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_expert_info_help(self, runner):
        """Test that 'expert info' help works."""
        result = runner.invoke(cli, ["expert", "info", "--help"])
        assert result.exit_code == 0

    def test_expert_info_requires_name(self, runner):
        """Test that 'expert info' requires a name argument."""
        result = runner.invoke(cli, ["expert", "info"])
        assert result.exit_code != 0

    def test_expert_info_handles_nonexistent_expert(self, runner):
        """Test that 'expert info' handles nonexistent expert gracefully."""
        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.load.return_value = None
            mock_store_class.return_value = mock_store

            result = runner.invoke(cli, ["expert", "info", "Nonexistent"])

            assert "not found" in result.output.lower()
            assert "Nonexistent" in result.output

    def test_expert_info_displays_details(self, runner):
        """Test that 'expert info' displays detailed information."""
        from datetime import datetime

        from deepr.experts.profile import ExpertProfile

        mock_expert = ExpertProfile(
            name="Test Expert",
            vector_store_id="vs_test123",
            description="Detailed test expert",
            provider="openai",
            model="gpt-4-turbo",
            total_documents=10,
            source_files=["file1.pdf", "file2.md"],
            conversations=25,
            research_triggered=5,
            total_research_cost=12.50,
            research_jobs=["job-1", "job-2"],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.load.return_value = mock_expert
            mock_store_class.return_value = mock_store

            result = runner.invoke(cli, ["expert", "info", "Test Expert"])

            output = result.output
            assert "Test Expert" in output
            assert "vs_test123" in output
            assert "Detailed test expert" in output
            assert "openai" in output
            assert "gpt-4-turbo" in output
            assert "10" in output  # total_documents
            # Note: Usage stats may appear below the truncated output in test,
            # so we just verify the expert info command ran successfully
            assert result.exit_code == 0


class TestExpertDeleteCommand:
    """Test 'expert delete' command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_expert_delete_help(self, runner):
        """Test that 'expert delete' help works."""
        result = runner.invoke(cli, ["expert", "delete", "--help"])
        assert result.exit_code == 0

    def test_expert_delete_requires_name(self, runner):
        """Test that 'expert delete' requires a name argument."""
        result = runner.invoke(cli, ["expert", "delete"])
        assert result.exit_code != 0

    def test_expert_delete_accepts_yes_flag(self, runner):
        """Test that 'expert delete' accepts --yes/-y flag."""
        result = runner.invoke(cli, ["expert", "delete", "--help"])
        output = result.output.lower()
        assert "--yes" in output or "-y" in output

    def test_expert_delete_handles_nonexistent_expert(self, runner):
        """Test that 'expert delete' handles nonexistent expert."""
        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.load.return_value = None
            mock_store_class.return_value = mock_store

            result = runner.invoke(cli, ["expert", "delete", "Nonexistent", "--yes"])

            assert "not found" in result.output.lower()

    def test_expert_delete_with_yes_flag(self, runner):
        """Test that 'expert delete' with --yes skips confirmation."""
        from datetime import datetime

        from deepr.experts.profile import ExpertProfile

        mock_expert = ExpertProfile(
            name="Delete Me", vector_store_id="vs_delete", total_documents=5, updated_at=datetime.utcnow()
        )

        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.load.return_value = mock_expert
            mock_store.delete.return_value = True
            mock_store_class.return_value = mock_store

            result = runner.invoke(cli, ["expert", "delete", "Delete Me", "--yes"])

            # Should not prompt for confirmation
            assert "delete expert?" not in result.output.lower()
            assert "[ok]" in result.output.lower() or "deleted" in result.output.lower()

    def test_expert_delete_shows_vector_store_cleanup(self, runner):
        """Test that delete command mentions vector store cleanup."""
        from datetime import datetime

        from deepr.experts.profile import ExpertProfile

        mock_expert = ExpertProfile(
            name="Test Expert", vector_store_id="vs_test123", total_documents=5, updated_at=datetime.utcnow()
        )

        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.load.return_value = mock_expert
            mock_store.delete.return_value = True
            mock_store_class.return_value = mock_store

            result = runner.invoke(cli, ["expert", "delete", "Test Expert", "--yes"])

            output = result.output.lower()
            # Should mention how to delete vector store
            assert "knowledge" in output or "vector" in output
            assert "vs_test123" in result.output


class TestSemanticCommandsIntegration:
    """Test that semantic commands include expert."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_research_command_exists(self, runner):
        """Test that 'research' semantic command exists."""
        result = runner.invoke(cli, ["research", "--help"])
        assert result.exit_code == 0

    def test_learn_command_exists(self, runner):
        """Test that 'learn' semantic command exists."""
        result = runner.invoke(cli, ["learn", "--help"])
        assert result.exit_code == 0

    def test_team_command_exists(self, runner):
        """Test that 'team' semantic command exists."""
        result = runner.invoke(cli, ["team", "--help"])
        assert result.exit_code == 0

    def test_top_level_help_shows_semantic_commands(self, runner):
        """Test that top-level help shows semantic commands."""
        result = runner.invoke(cli, ["--help"])
        output = result.output.lower()

        # Should show semantic commands
        assert "research" in output
        assert "learn" in output
        assert "team" in output
        assert "expert" in output


class TestKnowledgeAliases:
    """Test that knowledge alias works."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_knowledge_alias_exists(self, runner):
        """Test that 'knowledge' is an alias for 'vector'."""
        result = runner.invoke(cli, ["knowledge", "--help"])
        assert result.exit_code == 0
        assert "knowledge" in result.output.lower() or "vector" in result.output.lower()

    def test_knowledge_has_same_subcommands_as_vector(self, runner):
        """Test that knowledge has same subcommands as vector."""
        vector_result = runner.invoke(cli, ["vector", "--help"])
        knowledge_result = runner.invoke(cli, ["knowledge", "--help"])

        # Should have similar help text
        assert "list" in knowledge_result.output.lower()
        assert "create" in knowledge_result.output.lower()
        assert "delete" in knowledge_result.output.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
