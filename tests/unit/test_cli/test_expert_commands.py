"""Unit tests for expert CLI commands - no API calls.

Tests the expert command structure, parameter validation, and command flow
without making any external API calls.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
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
            assert "Name:" in output
            assert "Description:" in output
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
        assert "--scheduled" in result.output

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
            patch("deepr.experts.loop_runs.record_loop_run") as mock_record,
        ):
            loop_run = MagicMock()
            loop_run.to_dict.return_value = {"run_id": "loop_health_complete"}
            mock_record.return_value = loop_run
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
            assert mock_record.call_args.kwargs["verifier_outcome"] == "needs_attention"

    def test_health_check_json_output(self, runner):
        import json

        from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason

        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.experts.health_check.ExpertHealthChecker") as mock_checker,
            patch("deepr.experts.loop_runs.record_loop_run") as mock_record,
        ):
            loop_run = MagicMock()
            loop_run.to_dict.return_value = {"run_id": "loop_health_complete"}
            mock_record.return_value = loop_run
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
            assert payload["loop_run"]["run_id"] == "loop_health_complete"
            assert mock_record.call_args.kwargs["status"] == LoopRunStatus.WAITING
            assert mock_record.call_args.kwargs["stop_reason"] == LoopStopReason.CAPACITY_UNAVAILABLE

    def test_health_check_scheduled_json_includes_action_plan(self, runner):
        import json

        from deepr.cli.commands.semantic.expert_health_schedule import (
            HEALTH_CHECK_ACTION_PLAN_KIND,
            HEALTH_CHECK_ACTION_PLAN_SCHEMA_VERSION,
        )

        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.experts.health_check.ExpertHealthChecker") as mock_checker,
            patch("deepr.experts.loop_runs.record_loop_run") as mock_record,
        ):
            loop_run = MagicMock()
            loop_run.to_dict.return_value = {"run_id": "loop_health"}
            mock_record.return_value = loop_run
            mock_store = MagicMock()
            mock_store.load.return_value = MagicMock(name="Test Expert")
            mock_store_class.return_value = mock_store
            mock_checker.return_value.run.return_value = self._stub_report()

            result = runner.invoke(cli, ["expert", "health-check", "Test Expert", "--scheduled", "--json"])

            assert result.exit_code == 0
            payload = json.loads(result.output)
            assert payload["schema_version"] == HEALTH_CHECK_ACTION_PLAN_SCHEMA_VERSION
            assert payload["kind"] == HEALTH_CHECK_ACTION_PLAN_KIND
            assert payload["scheduled"] is True
            plan = payload["scheduled_action_plan"]
            assert plan["status"] == "waiting_for_capacity"
            assert plan["actions"][0]["scheduler_status"] == "waiting_for_capacity"
            assert payload["loop_run"]["run_id"] == "loop_health"

    def test_scheduled_health_ready_actions_record_pending_loop(self):
        from deepr.cli.commands.semantic.expert_health_schedule import scheduled_health_payload
        from deepr.experts.health_check import HealthFinding, HealthReport, RecommendedAction
        from deepr.experts.loop_runs import LoopRunStatus

        report = HealthReport(
            expert_name="Test Expert",
            domain="ai",
            status="needs_attention",
            findings=[HealthFinding("freshness", "warning", "Local action available.")],
            actions=[
                RecommendedAction(
                    category="freshness",
                    description="Run a local cleanup",
                    command="deepr expert cleanup Test Expert",
                    estimated_cost=0.0,
                    approval_tier="notify",
                )
            ],
        )

        with patch("deepr.experts.loop_runs.record_loop_run") as mock_record:
            loop_run = MagicMock()
            loop_run.to_dict.return_value = {"run_id": "loop_health_ready"}
            mock_record.return_value = loop_run

            payload = scheduled_health_payload(report)

        assert payload["scheduled_action_plan"]["status"] == "ready"
        assert payload["loop_run"]["run_id"] == "loop_health_ready"
        assert mock_record.call_args.kwargs["status"] == LoopRunStatus.PENDING
        assert mock_record.call_args.kwargs["stop_reason"] is None

    def test_scheduled_archive_waits_for_confirmation_without_mutating(self, runner, tmp_path):
        import json
        from datetime import UTC, datetime

        from deepr.cli.commands.semantic.expert_health_schedule import (
            HEALTH_CHECK_ARCHIVE_CONFIRMATION_KIND,
            HEALTH_CHECK_ARCHIVE_CONFIRMATION_SCHEMA_VERSION,
        )

        beliefs_dir = tmp_path / "Test Expert" / "beliefs"
        beliefs_dir.mkdir(parents=True)
        candidate = MagicMock()
        candidate.id = "b1"
        candidate.claim = "Stale claim"
        candidate.get_current_confidence.return_value = 0.12
        candidate.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
        candidate.retrieval_count = 0

        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.config.experts_root", return_value=tmp_path),
            patch("deepr.experts.beliefs.BeliefStore") as mock_belief_store_class,
            patch("deepr.experts.loop_runs.record_loop_run") as mock_record,
        ):
            loop_run = MagicMock()
            loop_run.to_dict.return_value = {"run_id": "loop_health_archive"}
            mock_record.return_value = loop_run
            mock_store = MagicMock()
            mock_store.load.return_value = MagicMock(name="Test Expert")
            mock_store_class.return_value = mock_store
            belief_store = MagicMock()
            belief_store.archive_candidates.return_value = [candidate]
            mock_belief_store_class.return_value = belief_store

            result = runner.invoke(
                cli,
                [
                    "expert",
                    "health-check",
                    "Test Expert",
                    "--archive-stale",
                    "--scheduled",
                    "--json",
                ],
            )

        assert result.exit_code == 0
        belief_store.archive_stale.assert_not_called()
        payload = json.loads(result.output)
        assert payload["schema_version"] == HEALTH_CHECK_ARCHIVE_CONFIRMATION_SCHEMA_VERSION
        assert payload["kind"] == HEALTH_CHECK_ARCHIVE_CONFIRMATION_KIND
        assert payload["status"] == "waiting_for_confirmation"
        assert payload["action"] == "archive_stale"
        assert payload["count"] == 1
        assert payload["loop_run"]["run_id"] == "loop_health_archive"

    def test_completed_health_archive_records_accepted_changes(self):
        from deepr.cli.commands.semantic.expert_health_loop import record_completed_health_archive
        from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason

        with patch("deepr.experts.loop_runs.record_loop_run") as mock_record:
            record_completed_health_archive("Test Expert", archived_count=2)

        assert mock_record.call_args.kwargs["status"] == LoopRunStatus.COMPLETED
        assert mock_record.call_args.kwargs["stop_reason"] == LoopStopReason.VERIFIER_PASSED
        assert mock_record.call_args.kwargs["accepted_changes"] == 2
        assert mock_record.call_args.kwargs["capacity_source"] == "local"


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
            patch("deepr.experts.loop_runs.record_loop_run") as mock_record,
        ):
            loop_run = MagicMock()
            loop_run.to_dict.return_value = {"run_id": "loop_reflect_complete"}
            mock_record.return_value = loop_run
            profile = MagicMock(domain="ai")
            profile.name = "AI Expert"
            mock_store = MagicMock()
            mock_store.load.return_value = profile
            mock_store_class.return_value = mock_store
            mock_idx.return_value.get_report_by_job_id.return_value = MagicMock(prompt="Will X?")
            mock_idx.return_value.get_report_content.return_value = "report body"
            inst = MagicMock()
            inst.reflect = AsyncMock(return_value=stub)
            mock_engine.return_value = inst

            result = runner.invoke(cli, ["expert", "reflect", "AI Expert", "job1", "--json"])
            assert result.exit_code == 0
            import json

            payload = json.loads(result.output)
            assert payload["verdict"] == "accept"
            assert payload["loop_run"]["run_id"] == "loop_reflect_complete"
            assert mock_record.call_args.kwargs["status"].value == "completed"
            assert mock_record.call_args.kwargs["stop_reason"].value == "verifier_passed"
            assert mock_record.call_args.kwargs["verifier_outcome"] == "accept"
            assert mock_record.call_args.kwargs["verifier_score"] == 0.84

    def test_scheduled_json_waits_before_reflection_engine(self, runner):
        from deepr.cli.commands.semantic.expert_reflect_schedule import (
            SCHEDULED_REFLECTION_WAIT_KIND,
            SCHEDULED_REFLECTION_WAIT_SCHEMA_VERSION,
        )

        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
            patch("deepr.experts.reflection.ReflectionEngine") as mock_engine,
            patch("deepr.experts.loop_runs.record_loop_run") as mock_record,
        ):
            loop_run = MagicMock()
            loop_run.to_dict.return_value = {"run_id": "loop_reflect"}
            mock_record.return_value = loop_run
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
        assert payload["schema_version"] == SCHEDULED_REFLECTION_WAIT_SCHEMA_VERSION
        assert payload["kind"] == SCHEDULED_REFLECTION_WAIT_KIND
        assert payload["status"] == "waiting_for_capacity"
        assert payload["expert_name"] == "AI Expert"
        assert payload["report_id"] == "job1"
        assert payload["pending_work"] == ["reflection_evaluation", "followup_research"]
        assert payload["next_actions"][0]["status"] == "wait"
        assert payload["loop_run"]["run_id"] == "loop_reflect"

    def test_execute_followups_records_reflection_loop_metrics(self, runner):
        from deepr.experts.reflection import ReflectionReport

        stub = ReflectionReport(
            question="Will X?",
            verdict="accept",
            overall_score=0.9,
            dimensions=[],
            followups=["alpha follow-up"],
        )
        fill_outcome = SimpleNamespace(
            status="filled",
            topic="alpha follow-up",
            absorbed=1,
            flagged=1,
            cost=0.05,
            detail="",
        )
        fill_result = SimpleNamespace(outcomes=[fill_outcome], total_cost=0.05)

        class FakeGapFillEngine:
            def __init__(self, profile):
                assert profile.name == "AI Expert"

            async def execute(self, routes, **kwargs):
                assert [route.topic for route in routes] == ["alpha follow-up"]
                assert kwargs["budget"] == 0.5
                return fill_result

        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
            patch("deepr.experts.reflection.ReflectionEngine") as mock_engine,
            patch("deepr.experts.gap_fill.GapFillEngine", FakeGapFillEngine),
            patch("deepr.experts.loop_runs.record_loop_run") as mock_record,
        ):
            profile = MagicMock(domain="ai")
            profile.name = "AI Expert"
            mock_store = MagicMock()
            mock_store.load.return_value = profile
            mock_store_class.return_value = mock_store
            mock_idx.return_value.get_report_by_job_id.return_value = MagicMock(prompt="Will X?")
            mock_idx.return_value.get_report_content.return_value = "report body"
            inst = MagicMock()
            inst.reflect = AsyncMock(return_value=stub)
            mock_engine.return_value = inst

            result = runner.invoke(
                cli,
                [
                    "expert",
                    "reflect",
                    "AI Expert",
                    "job1",
                    "--execute-followups",
                    "--budget",
                    "0.50",
                    "--yes",
                ],
            )

        assert result.exit_code == 0
        assert "Follow-up execution" in result.output
        assert mock_record.call_args.kwargs["status"].value == "completed"
        assert mock_record.call_args.kwargs["stop_reason"].value == "verifier_passed"
        assert mock_record.call_args.kwargs["accepted_changes"] == 2
        assert mock_record.call_args.kwargs["budget_spent"] == 0.05

    def test_research_reflection_verdict_records_verifier_failure(self):
        from deepr.cli.commands.semantic.expert_reflection_loop import record_completed_reflection_loop
        from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason

        report = SimpleNamespace(
            verdict="re_research",
            overall_score=0.32,
            model="gpt-5-mini",
        )

        with patch("deepr.experts.loop_runs.record_loop_run") as mock_record:
            record_completed_reflection_loop(
                "AI Expert",
                "job1",
                report,
                budget=1.0,
                execute_followups=False,
            )

        assert mock_record.call_args.kwargs["status"] == LoopRunStatus.FAILED
        assert mock_record.call_args.kwargs["stop_reason"] == LoopStopReason.VERIFIER_FAILED
        assert mock_record.call_args.kwargs["rejected_changes"] == 1
        assert mock_record.call_args.kwargs["next_action"]["status"] == "revise_or_research"


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
        from deepr.cli.commands.semantic.expert_gap_routes import (
            SCHEDULED_GAP_FILL_WAIT_KIND,
            SCHEDULED_GAP_FILL_WAIT_SCHEMA_VERSION,
        )
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
            patch("deepr.experts.loop_runs.record_loop_run") as mock_record,
        ):
            loop_run = MagicMock()
            loop_run.to_dict.return_value = {"run_id": "loop_gap"}
            mock_record.return_value = loop_run
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
        assert payload["schema_version"] == SCHEDULED_GAP_FILL_WAIT_SCHEMA_VERSION
        assert payload["kind"] == SCHEDULED_GAP_FILL_WAIT_KIND
        assert payload["status"] == "waiting_for_capacity"
        assert payload["routes"][0]["topic"] == "open model benchmark drift"
        assert payload["next_actions"][0]["status"] == "wait"
        assert payload["loop_run"]["run_id"] == "loop_gap"

    def test_execute_records_completed_gap_fill_loop(self, runner):
        from deepr.experts.gap_router import GapRoute
        from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason

        expert = MagicMock()
        expert.name = "AI Strategy Expert"
        expert.get_manifest.return_value.top_gaps.return_value = [MagicMock()]
        route = GapRoute(
            topic="open model benchmark drift",
            instrument="research",
            available=True,
            estimated_cost=0.25,
            rationale="general research",
            suggestion="",
            ev_cost_ratio=2.0,
        )
        outcome = SimpleNamespace(status="filled", topic=route.topic, absorbed=2, flagged=1, cost=0.17, detail="")

        class FakeResult:
            outcomes = [outcome]
            total_cost = 0.17

            def to_dict(self):
                return {
                    "expert_name": "AI Strategy Expert",
                    "outcomes": [{"topic": route.topic, "status": "filled"}],
                    "total_cost": 0.17,
                    "filled_count": 1,
                }

        class FakeGapFillEngine:
            def __init__(self, profile):
                assert profile is expert

            async def execute(self, received_routes, **kwargs):
                assert received_routes == [route]
                assert kwargs["budget"] == 0.5
                assert kwargs["dry_run"] is False
                return FakeResult()

        with (
            patch("deepr.experts.profile.ExpertStore") as mock_store_class,
            patch("deepr.experts.gap_router.GapRouter") as mock_router_class,
            patch("deepr.experts.gap_fill.GapFillEngine", FakeGapFillEngine),
            patch("deepr.experts.loop_runs.record_loop_run") as mock_record,
        ):
            loop_run = MagicMock()
            loop_run.to_dict.return_value = {"run_id": "loop_gap_complete"}
            mock_record.return_value = loop_run
            mock_store = MagicMock()
            mock_store.load.return_value = expert
            mock_store_class.return_value = mock_store
            mock_router_class.return_value.route.return_value = [route]

            result = runner.invoke(
                cli,
                [
                    "expert",
                    "route-gaps",
                    "AI Strategy Expert",
                    "--execute",
                    "--budget",
                    "0.50",
                    "--yes",
                    "--json",
                ],
            )

        assert result.exit_code == 0
        import json

        payload = json.loads(result.output)
        assert payload["loop_run"]["run_id"] == "loop_gap_complete"
        assert mock_record.call_args.kwargs["status"] == LoopRunStatus.COMPLETED
        assert mock_record.call_args.kwargs["stop_reason"] == LoopStopReason.VERIFIER_PASSED
        assert mock_record.call_args.kwargs["budget_spent"] == 0.17
        assert mock_record.call_args.kwargs["capacity_source"] == "api_metered"
        assert mock_record.call_args.kwargs["accepted_changes"] == 3

    def test_failed_gap_fill_records_tool_failure(self):
        from deepr.cli.commands.semantic.expert_gap_routes import _record_completed_gap_fill_loop
        from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason

        result = SimpleNamespace(
            total_cost=0.02,
            outcomes=[SimpleNamespace(status="failed", absorbed=0, flagged=0, detail="provider down")],
        )

        with patch("deepr.experts.loop_runs.record_loop_run") as mock_record:
            _record_completed_gap_fill_loop("AI Strategy Expert", result, budget=0.5, scheduled=False)

        assert mock_record.call_args.kwargs["status"] == LoopRunStatus.FAILED
        assert mock_record.call_args.kwargs["stop_reason"] == LoopStopReason.TOOL_FAILURE
        assert mock_record.call_args.kwargs["rejected_changes"] == 1
        assert mock_record.call_args.kwargs["next_action"]["status"] == "inspect"


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
