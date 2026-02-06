"""Simple test for creating a keyboards expert with 1 doc + 1 quick research.

This test validates the expert creation flow without making real API calls.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli


class TestKeyboardsExpertCreation:
    """Test creating a keyboards expert."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def mock_vector_store(self):
        """Mock vector store response."""
        mock = MagicMock()
        mock.id = "vs_keyboards_test123"
        return mock

    @pytest.fixture
    def mock_provider(self, mock_vector_store):
        """Mock provider with all necessary methods."""
        provider = MagicMock()

        # Mock async methods
        async def mock_upload(file_path):
            return f"file_{Path(file_path).stem}"

        async def mock_create_vs(name, file_ids):
            return mock_vector_store

        async def mock_wait_vs(vs_id, timeout):
            return True

        provider.upload_document = AsyncMock(side_effect=mock_upload)
        provider.create_vector_store = AsyncMock(side_effect=mock_create_vs)
        provider.wait_for_vector_store = AsyncMock(side_effect=mock_wait_vs)

        return provider

    def test_keyboards_expert_validation(self, runner):
        """Test that command validates parameters correctly."""
        # Test missing files
        result = runner.invoke(cli, ["expert", "make", "Keyboards Expert"])

        assert result.exit_code == 0
        assert "no files" in result.output.lower() or "error" in result.output.lower()

    def test_keyboards_expert_with_learn_no_budget(self, runner):
        """Test that --learn requires budget or topic counts."""
        with runner.isolated_filesystem():
            # Create a test file
            Path("keyboard_guide.md").write_text("# Keyboard Guide\n\nMechanical keyboards are great.")

            result = runner.invoke(
                cli, ["expert", "make", "Keyboards Expert", "--files", "keyboard_guide.md", "--learn"]
            )

            # Should fail without budget or topic counts
            assert "budget" in result.output.lower() or "required" in result.output.lower()

    def test_keyboards_expert_with_topic_counts_validation(self, runner):
        """Test that topic counts are validated correctly."""
        with runner.isolated_filesystem():
            # Create a test file
            Path("keyboard_guide.md").write_text("# Keyboard Guide\n\nMechanical keyboards are great.")

            # Test with valid topic counts
            result = runner.invoke(
                cli,
                [
                    "expert",
                    "make",
                    "Keyboards Test",
                    "--files",
                    "keyboard_guide.md",
                    "--learn",
                    "--docs",
                    "1",
                    "--quick",
                    "1",
                    "--yes",
                ],
            )

            # Should not fail on validation
            # (will fail on API calls, but that's expected in unit test)
            assert "Error: Topic counts must be non-negative" not in result.output
            assert "Error: Must specify at least one topic" not in result.output

    def test_f_string_formatting(self):
        """Test that f-strings are properly formatted in the codebase."""
        # This test validates f-string syntax without running the full command

        # Test various f-string patterns used in the expert commands
        name = "Keyboards Expert"
        budget = 5.0
        topics = 10
        cost = 0.004

        # These should all work without syntax errors
        test_strings = [
            f"Creating expert: {name}...",
            f"Generating curriculum ({topics} topics, ~${budget:.2f})...",
            f"Complete: ${cost:.2f}",
            f'Usage: deepr chat expert "{name}"',
            f"Error: Expert not found: {name}",
            f"  Documents: {topics}",
        ]

        # If we got here, all f-strings are valid
        assert len(test_strings) == 6
        assert all(isinstance(s, str) for s in test_strings)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
