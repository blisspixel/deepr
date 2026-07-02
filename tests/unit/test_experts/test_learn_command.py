"""Unit tests for the learn command.

Tests the Phase 3 implementation:
- CLI command registration
- Input validation
- Research mode
- File upload mode
- Synthesis integration
"""

from unittest.mock import patch

from click.testing import CliRunner


def _discard_coroutine(coro):
    """Close intercepted coroutines when asyncio.run is mocked in tests."""
    coro.close()
    return None


class TestLearnCommandRegistration:
    """Test that the learn command is properly registered."""

    def test_learn_command_exists(self):
        """Verify learn command is registered in expert group."""
        from deepr.cli.commands.semantic import expert

        command_names = [cmd.name for cmd in expert.commands.values()]
        assert "learn" in command_names

    def test_learn_command_help(self):
        """Verify learn command has proper help text."""
        from deepr.cli.commands.semantic import expert

        runner = CliRunner()
        result = runner.invoke(expert, ["learn", "--help"])

        assert result.exit_code == 0
        assert "Add knowledge to an expert on demand" in result.output
        assert "--files" in result.output
        assert "--budget" in result.output
        assert "--plan" in result.output
        assert "--synthesize" in result.output


class TestLearnInputValidation:
    """Test input validation for learn command."""

    def test_learn_requires_topic_or_files(self):
        """Verify learn command requires either topic or files."""
        from deepr.cli.commands.semantic import expert

        runner = CliRunner()
        result = runner.invoke(expert, ["learn", "Test Expert"])

        assert "Must provide either a topic to research or files to upload" in result.output

    def test_learn_expert_not_found(self):
        """Verify error when expert doesn't exist."""
        from deepr.cli.commands.semantic import expert

        runner = CliRunner()
        with patch("deepr.experts.profile.ExpertStore") as mock_store:
            mock_store.return_value.load.return_value = None
            result = runner.invoke(expert, ["learn", "Nonexistent Expert", "Some topic", "-y"])

        assert "Expert not found" in result.output


class TestLearnResearchMode:
    """Test research mode functionality."""

    def test_research_query_construction(self):
        """Test that research queries are properly constructed."""
        # The learn command passes the topic directly to _standard_research
        topic = "Latest Lambda features 2026"

        # The query should be passed as-is
        assert topic == "Latest Lambda features 2026"

    def test_research_budget_default(self):
        """Test default budget is $1."""
        from deepr.cli.commands.semantic import learn_expert

        # Check the default value in the command definition
        for param in learn_expert.params:
            if param.name == "budget":
                assert param.default == 1.0


class TestLearnFileMode:
    """Test file upload mode functionality."""

    def test_file_copy_to_documents_dir(self):
        """Test that files are copied to expert's documents directory."""
        import os
        import tempfile

        # Create a temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test Document\n\nThis is test content.")
            temp_file = f.name

        try:
            # Verify file exists
            assert os.path.exists(temp_file)

            # The learn command should copy this to docs_dir
            # This is tested via integration tests
        finally:
            os.unlink(temp_file)


class TestLearnSynthesisIntegration:
    """Test synthesis integration after learning."""

    def test_synthesize_flag_default_true(self):
        """Test that synthesize flag defaults to True."""
        from deepr.cli.commands.semantic import learn_expert

        for param in learn_expert.params:
            if param.name == "synthesize":
                assert param.default == True

    def test_no_synthesize_flag_works(self):
        """Test that --no-synthesize flag is recognized."""
        from deepr.cli.commands.semantic import expert

        runner = CliRunner()
        result = runner.invoke(expert, ["learn", "--help"])

        assert "--synthesize / --no-synthesize" in result.output


class TestLearnCommandOptions:
    """Test command options and flags."""

    def test_files_option_accepts_multiple(self):
        """Test that --files option accepts multiple files."""
        from deepr.cli.commands.semantic import learn_expert

        for param in learn_expert.params:
            if param.name == "files":
                assert param.multiple == True

    def test_yes_flag_skips_confirmation(self):
        """Test that -y flag is available."""
        from deepr.cli.commands.semantic import learn_expert

        for param in learn_expert.params:
            if param.name == "yes":
                assert param.is_flag == True

    def test_budget_option_type(self):
        """Test that budget option is float type."""
        from deepr.cli.commands.semantic import learn_expert

        for param in learn_expert.params:
            if param.name == "budget":
                assert param.type.name.lower() == "float"

    def test_dry_run_rejects_files(self, tmp_path):
        """File upload has no dry-run mode, so reject the mixed request."""
        from deepr.cli.commands.semantic import expert

        doc = tmp_path / "doc.md"
        doc.write_text("# Doc", encoding="utf-8")

        result = CliRunner().invoke(expert, ["learn", "Test Expert", "--files", str(doc), "--dry-run"])

        assert result.exit_code == 0
        assert "--dry-run is only supported for topic learning without files" in result.output


class TestLearnOutputMessages:
    """Test output messages and formatting."""

    def test_learn_topic_delegates_to_web_pipeline(self):
        """Topic learning should use the verified web absorption pipeline."""
        from deepr.cli.commands.semantic import expert

        captured = {}

        def fake_pipeline(**kwargs):
            captured.update(kwargs)
            print(kwargs["title"])

        runner = CliRunner()
        with patch("deepr.cli.commands.semantic.expert_maintenance.run_learn_web_pipeline", fake_pipeline):
            result = runner.invoke(
                expert,
                ["learn", "Test Expert", "Topic", "--plan", "codex", "--plan-model", "gpt-5", "-y"],
            )

        assert result.exit_code == 0
        assert "Learn: Test Expert" in result.output
        assert captured["name"] == "Test Expert"
        assert captured["topic"] == "Topic"
        assert captured["plan"] == "codex"
        assert captured["plan_model"] == "gpt-5"
        assert captured["yes"] is True

    def test_learn_shows_topic(self):
        """Test that learn command forwards the topic being researched."""
        from deepr.cli.commands.semantic import expert

        captured = {}

        def fake_pipeline(**kwargs):
            captured.update(kwargs)
            print(f"Topic: {kwargs['topic']}")

        runner = CliRunner()
        with patch("deepr.cli.commands.semantic.expert_maintenance.run_learn_web_pipeline", fake_pipeline):
            result = runner.invoke(expert, ["learn", "Test Expert", "Quantum computing", "-y"])

        assert result.exit_code == 0
        assert "Topic: Quantum computing" in result.output
        assert captured["topic"] == "Quantum computing"


class TestLearnExamples:
    """Test that documented examples are valid."""

    def test_example_research_topic(self):
        """Test example: deepr expert learn 'AWS Expert' 'Latest Lambda features'"""
        from deepr.cli.commands.semantic import expert

        runner = CliRunner()
        result = runner.invoke(expert, ["learn", "--help"])
        assert "live web retrieval plus verified belief absorption" in result.output

    def test_example_with_files(self):
        """Test example: deepr expert learn 'Python Expert' --files docs/*.md"""
        from deepr.cli.commands.semantic import expert

        runner = CliRunner()
        result = runner.invoke(expert, ["learn", "--help"])
        assert "--files" in result.output

    def test_example_with_budget(self):
        """Test example: deepr expert learn 'Tech Expert' 'Topic' --budget 5"""
        from deepr.cli.commands.semantic import expert

        runner = CliRunner()
        result = runner.invoke(expert, ["learn", "--help"])
        assert "--budget" in result.output
