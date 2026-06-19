"""Unit tests for expert CLI commands - no API calls.

Tests the expert command structure, parameter validation, and command flow
without making any external API calls.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
        assert "--local" in result.output
        assert "--local-model" in result.output

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

    def test_expert_make_local_creates_profile_without_provider(self, runner, monkeypatch):
        """Local creation must not call provider vector store setup."""
        from deepr.experts.profile import ExpertStore

        monkeypatch.setenv("DEEPR_LOCAL_MODEL", "test-local-model")

        with patch("deepr.providers.create_provider") as create_provider:
            result = runner.invoke(
                cli,
                [
                    "expert",
                    "make",
                    "Local UX Expert",
                    "--local",
                    "-d",
                    "UI/UX for local agentic research tools",
                ],
            )

        assert result.exit_code == 0
        assert "Local expert created: Local UX Expert" in result.output
        create_provider.assert_not_called()

        profile = ExpertStore().load("Local UX Expert")
        assert profile is not None
        assert profile.provider == "local"
        assert profile.model == "test-local-model"
        assert profile.vector_store_id == "local-only:local_ux_expert"
        assert profile.total_documents == 0
        assert profile.monthly_learning_budget == 0.0

    def test_expert_make_local_copies_seed_files(self, runner, tmp_path, monkeypatch):
        """Seed documents become owned local expert documents."""
        from pathlib import Path

        from deepr.experts.profile import ExpertStore

        monkeypatch.setenv("DEEPR_LOCAL_MODEL", "test-local-model")
        source = tmp_path / "seed.md"
        source.write_text("# Seed\n\nLocal source material.", encoding="utf-8")

        result = runner.invoke(
            cli,
            [
                "expert",
                "make",
                "Local Docs Expert",
                "--local",
                "--files",
                str(source),
            ],
        )

        assert result.exit_code == 0
        profile = ExpertStore().load("Local Docs Expert")
        assert profile is not None
        assert profile.total_documents == 1
        copied = Path(profile.source_files[0])
        assert copied.name == "seed.md"
        assert copied.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
        assert copied.parent == ExpertStore().get_documents_dir("Local Docs Expert")

    def test_expert_make_local_rejects_api_backed_learning_options(self, runner):
        """Local make is only profile setup; learning runs through sync."""
        result = runner.invoke(cli, ["expert", "make", "Local Expert", "--local", "--learn", "--budget", "1"])

        assert result.exit_code == 0
        assert "--local creates a $0 profile only" in result.output
        assert "expert sync" in result.output


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
        from datetime import UTC, datetime

        from deepr.experts.profile import ExpertProfile

        mock_expert = ExpertProfile(
            name="Test Expert",
            vector_store_id="vs_test",
            description="Test description",
            total_documents=5,
            conversations=10,
            research_triggered=2,
            total_research_cost=3.50,
            updated_at=datetime.now(UTC),
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
        from datetime import UTC, datetime

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
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
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


class TestExpertHealthCheckCommand:
    """Test 'expert health-check' command (read-only, cost-$0 audit)."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def _stub_report(self):
        from deepr.experts.health_check import HealthFinding, HealthReport, RecommendedAction

        return HealthReport(
            expert_name="Test Expert",
            domain="ai",
            status="needs_attention",
            findings=[
                HealthFinding("freshness", "warning", "Knowledge is stale (200d old, threshold 90d)."),
                HealthFinding("coverage", "ok", "3 claim(s) across 2 document(s)."),
            ],
            actions=[
                RecommendedAction(
                    category="freshness",
                    description="Refresh knowledge to clear staleness",
                    command="deepr expert refresh Test Expert --budget 0.50",
                    estimated_cost=0.5,
                    approval_tier="notify",
                ),
            ],
        )

    def test_health_check_help(self, runner):
        result = runner.invoke(cli, ["expert", "health-check", "--help"])
        assert result.exit_code == 0
        assert "audit" in result.output.lower()

    def test_health_check_requires_name(self, runner):
        result = runner.invoke(cli, ["expert", "health-check"])
        assert result.exit_code != 0

    def test_health_check_handles_nonexistent_expert(self, runner):
        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.load.return_value = None
            mock_store_class.return_value = mock_store

            result = runner.invoke(cli, ["expert", "health-check", "Nonexistent"])

            assert "not found" in result.output.lower()
            assert result.exit_code == 2

    def test_health_check_displays_findings_and_actions(self, runner):
        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.experts.health_check.ExpertHealthChecker") as mock_checker,
        ):
            mock_store = MagicMock()
            mock_store.load.return_value = MagicMock(name="Test Expert")
            mock_store_class.return_value = mock_store
            mock_checker.return_value.run.return_value = self._stub_report()

            result = runner.invoke(cli, ["expert", "health-check", "Test Expert"])

            assert result.exit_code == 0
            out = result.output
            assert "NEEDS ATTENTION" in out
            assert "freshness" in out
            assert "deepr expert refresh Test Expert" in out

    def test_health_check_json_output(self, runner):
        import json

        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.experts.health_check.ExpertHealthChecker") as mock_checker,
        ):
            mock_store = MagicMock()
            mock_store.load.return_value = MagicMock(name="Test Expert")
            mock_store_class.return_value = mock_store
            mock_checker.return_value.run.return_value = self._stub_report()

            result = runner.invoke(cli, ["expert", "health-check", "Test Expert", "--json"])

            assert result.exit_code == 0
            payload = json.loads(result.output)
            assert payload["expert_name"] == "Test Expert"
            assert payload["status"] == "needs_attention"
            assert payload["findings"][0]["category"] == "freshness"


class TestExpertAbsorbCommand:
    """Test 'expert absorb' command (verification-gated, mutating)."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def _stub_result(self, dry_run=False):
        from deepr.experts.report_absorber import AbsorbedClaim, AbsorptionResult

        return AbsorptionResult(
            expert_name="Test Expert",
            report_id="rep1",
            dry_run=dry_run,
            total_candidates=2,
            absorbed=[AbsorbedClaim("A grounded claim", 0.9, "abc123", "would_add" if dry_run else "added")],
            rejected=[],
            estimated_cost=0.03,
        )

    def test_absorb_help(self, runner):
        result = runner.invoke(cli, ["expert", "absorb", "--help"])
        assert result.exit_code == 0
        assert "report" in result.output.lower()

    def test_absorb_requires_name_and_report(self, runner):
        result = runner.invoke(cli, ["expert", "absorb", "Only Name"])
        assert result.exit_code != 0

    def test_absorb_handles_nonexistent_expert(self, runner):
        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.load.return_value = None
            mock_store_class.return_value = mock_store

            result = runner.invoke(cli, ["expert", "absorb", "Nonexistent", "rep1", "--yes"])

            assert "not found" in result.output.lower()
            assert result.exit_code == 2

    def test_absorb_handles_missing_report(self, runner):
        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
        ):
            mock_store = MagicMock()
            mock_store.load.return_value = MagicMock(name="Test Expert")
            mock_store_class.return_value = mock_store
            mock_idx.return_value.get_report_content.return_value = None

            result = runner.invoke(cli, ["expert", "absorb", "Test Expert", "missing", "--yes"])

            assert "no report found" in result.output.lower()
            assert result.exit_code == 2

    def test_absorb_dry_run_does_not_save(self, runner):
        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
            patch("deepr.experts.report_absorber.ReportAbsorber") as mock_absorber,
        ):
            mock_store = MagicMock()
            mock_store.load.return_value = MagicMock(name="Test Expert")
            mock_store_class.return_value = mock_store
            mock_idx.return_value.get_report_content.return_value = "report body"
            inst = MagicMock()
            inst.absorb = AsyncMock(return_value=self._stub_result(dry_run=True))
            mock_absorber.return_value = inst

            result = runner.invoke(cli, ["expert", "absorb", "Test Expert", "rep1", "--dry-run", "--yes"])

            assert result.exit_code == 0
            assert "DRY RUN" in result.output
            mock_store.save.assert_not_called()

    def test_absorb_applies_and_saves(self, runner):
        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
            patch("deepr.experts.report_absorber.ReportAbsorber") as mock_absorber,
        ):
            mock_store = MagicMock()
            expert = MagicMock(name="Test Expert")
            expert.total_research_cost = 0.0
            mock_store.load.return_value = expert
            mock_store_class.return_value = mock_store
            mock_idx.return_value.get_report_content.return_value = "report body"
            inst = MagicMock()
            inst.absorb = AsyncMock(return_value=self._stub_result(dry_run=False))
            mock_absorber.return_value = inst

            result = runner.invoke(cli, ["expert", "absorb", "Test Expert", "rep1", "--yes", "--json"])

            assert result.exit_code == 0
            import json

            payload = json.loads(result.output)
            assert payload["report_id"] == "rep1"
            mock_store.save.assert_called_once()

    def test_absorb_cancel_at_prompt(self, runner):
        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
        ):
            mock_store = MagicMock()
            mock_store.load.return_value = MagicMock(name="Test Expert")
            mock_store_class.return_value = mock_store
            mock_idx.return_value.get_report_content.return_value = "report body"

            # Decline the confirmation prompt (no --yes).
            result = runner.invoke(cli, ["expert", "absorb", "Test Expert", "rep1"], input="n\n")

            assert "cancelled" in result.output.lower()


class TestExpertReflectCommand:
    """Test 'expert reflect' command (research-quality self-eval)."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_help(self, runner):
        result = runner.invoke(cli, ["expert", "reflect", "--help"])
        assert result.exit_code == 0
        assert "evaluate" in result.output.lower() or "verdict" in result.output.lower()
        assert "--scheduled" in result.output

    def test_nonexistent_expert(self, runner):
        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.load.return_value = None
            mock_store_class.return_value = mock_store
            result = runner.invoke(cli, ["expert", "reflect", "Ghost", "job1"])
            assert result.exit_code == 2

    def test_missing_report(self, runner):
        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
        ):
            mock_store = MagicMock()
            mock_store.load.return_value = MagicMock(domain="ai")
            mock_store_class.return_value = mock_store
            mock_idx.return_value.get_report_by_job_id.return_value = None
            mock_idx.return_value.get_report_content.return_value = None
            result = runner.invoke(cli, ["expert", "reflect", "AI Expert", "missing"])
            assert result.exit_code == 2
            assert "no report found" in result.output.lower()

    def test_json_output(self, runner):
        from deepr.experts.reflection import ReflectionReport

        stub = ReflectionReport(question="Will X?", verdict="accept", overall_score=0.84, dimensions=[], followups=[])
        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
            patch("deepr.experts.reflection.ReflectionEngine") as mock_engine,
        ):
            mock_store = MagicMock()
            mock_store.load.return_value = MagicMock(domain="ai")
            mock_store_class.return_value = mock_store
            mock_idx.return_value.get_report_by_job_id.return_value = MagicMock(prompt="Will X?")
            mock_idx.return_value.get_report_content.return_value = "report body"
            inst = MagicMock()
            inst.reflect = AsyncMock(return_value=stub)
            mock_engine.return_value = inst

            result = runner.invoke(cli, ["expert", "reflect", "AI Expert", "job1", "--json"])
            assert result.exit_code == 0
            import json

            assert json.loads(result.output)["verdict"] == "accept"

    def test_scheduled_json_waits_before_reflection_engine(self, runner):
        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
            patch("deepr.experts.reflection.ReflectionEngine") as mock_engine,
        ):
            profile = MagicMock(domain="ai")
            profile.name = "AI Expert"
            mock_store = MagicMock()
            mock_store.load.return_value = profile
            mock_store_class.return_value = mock_store
            mock_idx.return_value.get_report_by_job_id.return_value = MagicMock(prompt="Will X?")
            mock_idx.return_value.get_report_content.return_value = "report body"

            result = runner.invoke(
                cli,
                [
                    "expert",
                    "reflect",
                    "AI Expert",
                    "job1",
                    "--execute-followups",
                    "--scheduled",
                    "--json",
                ],
            )

        assert result.exit_code == 0
        mock_engine.assert_not_called()
        import json

        payload = json.loads(result.output)
        assert payload["status"] == "waiting_for_capacity"
        assert payload["expert_name"] == "AI Expert"
        assert payload["report_id"] == "job1"
        assert payload["pending_work"] == ["reflection_evaluation", "followup_research"]
        assert payload["next_actions"][0]["status"] == "wait"


class TestExpertRouteGapsCommand:
    """Test 'expert route-gaps' command (read-only gap-to-instrument routing)."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_help(self, runner):
        result = runner.invoke(cli, ["expert", "route-gaps", "--help"])
        assert result.exit_code == 0
        assert "route" in result.output.lower()
        assert "--scheduled" in result.output

    def test_nonexistent_expert(self, runner):
        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.load.return_value = None
            mock_store_class.return_value = mock_store
            result = runner.invoke(cli, ["expert", "route-gaps", "Ghost"])
            assert result.exit_code == 2
            assert "not found" in result.output.lower()

    def test_json_output(self, runner):
        from deepr.core.contracts import ExpertManifest, Gap

        expert = MagicMock()
        expert.name = "AI Strategy Expert"
        expert.get_manifest.return_value = ExpertManifest(
            expert_name="AI Strategy Expert",
            domain="ai",
            gaps=[Gap.create(topic="hiring signals and competitive strategy", ev_cost_ratio=2.0)],
        )
        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.experts.gap_router.shutil.which", return_value="/usr/bin/x"),
        ):
            mock_store = MagicMock()
            mock_store.load.return_value = expert
            mock_store_class.return_value = mock_store
            result = runner.invoke(cli, ["expert", "route-gaps", "AI Strategy Expert", "--json"])
            assert result.exit_code == 0
            import json

            payload = json.loads(result.output)
            assert payload["expert_name"] == "AI Strategy Expert"
            assert payload["routes"][0]["instrument"] == "primr"

    def test_scheduled_execute_waits_without_starting_gap_fill_engine(self, runner):
        from deepr.core.contracts import ExpertManifest, Gap
        from deepr.experts.gap_router import GapRoute

        expert = MagicMock()
        expert.name = "AI Strategy Expert"
        expert.get_manifest.return_value = ExpertManifest(
            expert_name="AI Strategy Expert",
            domain="ai",
            gaps=[Gap.create(topic="open model benchmark drift", ev_cost_ratio=2.0)],
        )
        route = GapRoute(
            topic="open model benchmark drift",
            instrument="research",
            available=True,
            estimated_cost=0.25,
            rationale="general research",
            suggestion="",
            ev_cost_ratio=2.0,
        )

        class ExplodingGapFillEngine:
            def __init__(self, *args, **kwargs):
                raise AssertionError("scheduled wait must not start gap-fill execution")

        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.experts.gap_router.GapRouter") as mock_router_class,
            patch("deepr.experts.gap_fill.GapFillEngine", ExplodingGapFillEngine),
        ):
            mock_store = MagicMock()
            mock_store.load.return_value = expert
            mock_store_class.return_value = mock_store
            mock_router_class.return_value.route.return_value = [route]

            result = runner.invoke(
                cli,
                ["expert", "route-gaps", "AI Strategy Expert", "--execute", "--scheduled", "--json"],
            )

        assert result.exit_code == 0
        import json

        payload = json.loads(result.output)
        assert payload["status"] == "waiting_for_capacity"
        assert payload["routes"][0]["topic"] == "open model benchmark drift"
        assert payload["next_actions"][0]["status"] == "wait"


class TestExpertExportSkillCommand:
    """Test 'expert export-skill' command (agentskills.io distribution)."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_help(self, runner):
        result = runner.invoke(cli, ["expert", "export-skill", "--help"])
        assert result.exit_code == 0
        assert "skill" in result.output.lower()

    def test_requires_name(self, runner):
        result = runner.invoke(cli, ["expert", "export-skill"])
        assert result.exit_code != 0

    def test_nonexistent_expert(self, runner):
        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.load.return_value = None
            mock_store_class.return_value = mock_store
            result = runner.invoke(cli, ["expert", "export-skill", "Ghost"])
            assert result.exit_code == 2
            assert "not found" in result.output.lower()

    def test_print_only_emits_skill_md(self, runner):
        from deepr.experts.profile import ExpertProfile

        expert = ExpertProfile(name="AI Strategy Expert", vector_store_id="vs", description="d", domain="ai")
        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.load.return_value = expert
            mock_store_class.return_value = mock_store
            result = runner.invoke(cli, ["expert", "export-skill", "AI Strategy Expert", "--print"])
            assert result.exit_code == 0
            assert "name: deepr-expert-ai-strategy-expert" in result.output
            assert "deepr_query_expert" in result.output

    def test_writes_file_to_output_dir(self, runner, tmp_path):
        from deepr.experts.profile import ExpertProfile

        expert = ExpertProfile(name="AI Strategy Expert", vector_store_id="vs", description="d", domain="ai")
        out = tmp_path / "myskill"
        with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
            mock_store = MagicMock()
            mock_store.load.return_value = expert
            mock_store_class.return_value = mock_store
            result = runner.invoke(cli, ["expert", "export-skill", "AI Strategy Expert", "-o", str(out)])
            assert result.exit_code == 0
            assert (out / "SKILL.md").exists()


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
        from datetime import UTC, datetime

        from deepr.experts.profile import ExpertProfile

        mock_expert = ExpertProfile(
            name="Delete Me", vector_store_id="vs_delete", total_documents=5, updated_at=datetime.now(UTC)
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
        from datetime import UTC, datetime

        from deepr.experts.profile import ExpertProfile

        mock_expert = ExpertProfile(
            name="Test Expert", vector_store_id="vs_test123", total_documents=5, updated_at=datetime.now(UTC)
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
