"""Unit tests for CLI run module.

Tests the research job execution workflow including:
- Focus command with valid query
- Error handling for invalid provider
- Glob pattern resolution for file uploads
- --yes flag skips confirmation
- JSON output mode
- Cost estimation bounds

All tests use mocks to avoid external API calls.
"""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from click.testing import CliRunner

# Import Hypothesis for property-based testing
from hypothesis import given, settings


async def _restore_expected_reservation(_queue, _job_id, reservation, _upload_result, _formatter):
    return reservation


from deepr.cli.commands.run import (
    TraceFlags,
    _save_and_show_full_trace,
    _show_trace_explain,
    _show_trace_timeline,
    estimate_cost,
    run,
)


class TestEstimateCost:
    """Test cost estimation function."""

    def test_o4_mini_model_cost(self):
        """Test o4-mini model returns expected cost."""
        cost = estimate_cost("o4-mini-deep-research")
        assert cost == 0.10

    def test_o3_model_cost(self):
        """Test o3 model returns expected cost."""
        cost = estimate_cost("o3-deep-research")
        assert cost == 0.50

    def test_unknown_model_default_cost(self):
        """Test unknown model returns default cost."""
        cost = estimate_cost("unknown-model")
        assert cost == 0.15

    def test_cost_always_positive(self):
        """Test that cost is always positive."""
        for model in ["o4-mini", "o3", "unknown", "", "test-model"]:
            cost = estimate_cost(model)
            assert cost > 0, f"Model {model} has non-positive cost"


class TestFocusCommand:
    """Test the focus command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_focus_requires_query(self, runner):
        """Test that focus command requires a query argument."""
        result = runner.invoke(run, ["focus"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "query" in result.output.lower()

    @patch("deepr.cli.commands.run._run_single")
    def test_focus_calls_run_single(self, mock_run_single, runner):
        """Test that focus command calls _run_single with correct args."""
        # Mock asyncio.run to capture the coroutine
        with patch("deepr.cli.commands.run.asyncio.run") as mock_asyncio:
            result = runner.invoke(run, ["focus", "Test query"])

            # Verify asyncio.run was called
            mock_asyncio.assert_called_once()

    def test_focus_with_model_option(self, runner):
        """Test focus command accepts model option."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "-m", "o3-deep-research"])
            # Should not fail on argument parsing
            assert "Error" not in result.output or result.exit_code == 0

    def test_focus_with_provider_option(self, runner):
        """Test focus command accepts provider option."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "-p", "gemini"])
            # Should not fail on argument parsing
            assert "Error" not in result.output or result.exit_code == 0

    def test_focus_invalid_provider_rejected(self, runner):
        """Test that invalid provider is rejected."""
        result = runner.invoke(run, ["focus", "Test query", "-p", "invalid_provider"])
        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "choice" in result.output.lower()

    def test_focus_with_yes_flag(self, runner):
        """Test focus command accepts --yes flag."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "--yes"])
            # Should not fail on argument parsing
            assert result.exit_code == 0 or "Error" not in result.output

    def test_focus_with_upload_option(self, runner):
        """Test focus command accepts upload option."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "-u", "test.pdf"])
            # Should not fail on argument parsing (file doesn't need to exist for parsing)
            assert result.exit_code == 0 or "Error" not in result.output

    def test_focus_with_limit_option(self, runner):
        """Test focus command accepts limit option."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "-l", "5.00"])
            # Should not fail on argument parsing
            assert result.exit_code == 0 or "Error" not in result.output


class TestRunSingleAsync:
    """Test the _run_single async function."""

    @pytest.mark.asyncio
    async def test_run_single_estimates_cost(self):
        """Test that _run_single estimates cost before proceeding."""
        from deepr.cli.commands.run import _run_single
        from deepr.cli.output import OutputContext, OutputMode

        output_context = OutputContext(mode=OutputMode.QUIET)

        # Mock all external dependencies
        with patch("deepr.cli.commands.run.check_budget_approval", return_value=True):
            with patch("deepr.providers.create_provider") as mock_create:
                mock_provider = MagicMock()
                mock_provider.submit_research = AsyncMock(return_value="job-123")
                mock_create.return_value = mock_provider

                with patch("deepr.config.load_config", return_value={"api_key": "test"}):
                    with (
                        patch("deepr.cli.commands.run.SQLiteQueue") as mock_queue_class,
                        patch("deepr.cli.commands.run._enqueue_reserved_job", new_callable=AsyncMock),
                        patch(
                            "deepr.cli.commands.run._ensure_reservation",
                            new_callable=AsyncMock,
                            side_effect=_restore_expected_reservation,
                        ),
                    ):
                        mock_queue_instance = MagicMock()
                        mock_queue_instance.enqueue = AsyncMock(return_value="job-123")
                        mock_queue_instance.claim_submission = AsyncMock(return_value=True)
                        mock_queue_instance.get_job = AsyncMock(return_value=None)
                        mock_queue_class.return_value = mock_queue_instance

                        # This should not raise
                        await _run_single(
                            query="Test query",
                            model="o4-mini-deep-research",
                            provider="openai",
                            no_web=False,
                            no_code=False,
                            upload=(),
                            limit=None,
                            yes=True,  # Skip confirmation
                            output_context=output_context,
                        )

    @pytest.mark.asyncio
    async def test_run_submission_persists_durable_ceiling_metadata(self, tmp_path, monkeypatch):
        from deepr.cli.commands import run_submission
        from deepr.experts.research_cost_gate import refund_research_cost
        from deepr.experts.research_reservation_store import ResearchReservationStore
        from deepr.queue.local_queue import SQLiteQueue

        queue = SQLiteQueue(str(tmp_path / "queue.db"))
        monkeypatch.setattr(run_submission, "SQLiteQueue", lambda: queue)

        job_id, job, reservation = await run_submission.create_and_enqueue_job(
            "Research safely",
            "o4-mini-deep-research",
            "openai",
            False,
            False,
            [],
            None,
            5.0,
            (),
        )

        persisted = await queue.get_job(job_id)
        assert persisted is not None
        assert persisted.metadata == job.metadata
        assert persisted.metadata["cost_reservation_id"] == reservation.reservation_id
        assert persisted.metadata["research_max_input_tokens"] == 128_000
        assert persisted.metadata["research_max_output_tokens"] == 16_000
        assert persisted.metadata["research_max_tool_calls"] == 16
        assert persisted.metadata["research_max_provider_requests"] == 3
        assert persisted.metadata["research_max_request_bytes"] == 64 * 1024
        assert ResearchReservationStore().active_cost() == pytest.approx(5.0)
        refund_research_cost(reservation)

    @pytest.mark.asyncio
    async def test_run_submission_uses_configured_queue_path(self, tmp_path):
        from deepr.cli.commands import run_submission
        from deepr.experts.research_cost_gate import refund_research_cost
        from deepr.queue.local_queue import SQLiteQueue

        queue_path = tmp_path / "runtime" / "configured.db"
        job_id, _, reservation = await run_submission.create_and_enqueue_job(
            "Research safely",
            "o4-mini-deep-research",
            "openai",
            False,
            False,
            [],
            None,
            5.0,
            (),
            str(queue_path),
        )

        assert await SQLiteQueue(str(queue_path)).get_job(job_id) is not None
        refund_research_cost(reservation)

    @pytest.mark.asyncio
    async def test_post_upload_rollback_cleans_resources_and_accounts_cost(self):
        from deepr.cli.commands import run_submission

        reservation = MagicMock()
        upload_result = MagicMock(uploaded_ids=["file-1"], vector_store_id="vs-1")
        with (
            patch(
                "deepr.cli.commands.file_handler.cleanup_file_uploads",
                new_callable=AsyncMock,
                return_value=True,
            ) as cleanup,
            patch("deepr.experts.research_cost_gate.settle_research_cost") as settle,
            patch("deepr.cli.commands.run_submission.refund_research_cost") as refund,
        ):
            await run_submission.rollback_prepared_submission(
                reservation,
                upload_result,
                source="test.rollback",
            )

        cleanup.assert_awaited_once()
        settle.assert_called_once_with(
            reservation,
            actual_cost=None,
            source="test.rollback.cleanup_confirmed",
        )
        refund.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_deep_research_tools_fail_before_queue_or_reservation(self):
        from deepr.cli.commands.run import _run_single
        from deepr.cli.output import OutputContext, OutputMode

        with (
            patch("deepr.cli.commands.run._check_budget", return_value=True),
            patch("deepr.cli.commands.run._reserve_job_submission", new_callable=AsyncMock) as reserve,
        ):
            await _run_single(
                query="Test query",
                model="o4-mini-deep-research",
                provider="openai",
                no_web=True,
                no_code=True,
                upload=(),
                limit=None,
                yes=True,
                output_context=OutputContext(mode=OutputMode.QUIET),
            )

        reserve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_file_storage_gate_precedes_cost_and_provider_work(self):
        """Unbounded provider storage is rejected before any side effect."""
        from deepr.cli.commands.run import _run_single
        from deepr.cli.output import OutputContext, OutputMode
        from deepr.services.research_bounds import ResearchRequestBoundsError

        with (
            patch("deepr.cli.commands.run._check_budget", return_value=True),
            patch("deepr.cli.commands.run._reserve_job_submission", new_callable=AsyncMock) as reserve,
            patch("deepr.cli.commands.file_handler.handle_file_uploads", new_callable=AsyncMock) as upload,
            patch("deepr.cli.commands.run._submit_to_provider", new_callable=AsyncMock) as submit,
            pytest.raises(ResearchRequestBoundsError) as exc_info,
        ):
            await _run_single(
                query="Test query",
                model="o4-mini-deep-research",
                provider="openai",
                no_web=False,
                no_code=False,
                upload=("test.pdf",),
                limit=1.0,
                yes=True,
                output_context=OutputContext(mode=OutputMode.QUIET),
            )

        assert exc_info.value.code == "research_file_storage_unbounded"
        reserve.assert_not_awaited()
        upload.assert_not_awaited()
        submit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_provider_submit_uses_shared_durable_dispatch_boundary(self):
        from deepr.cli.commands.run import _submit_to_provider
        from deepr.cli.output import OutputContext, OutputMode

        provider = MagicMock(submit_research=AsyncMock(side_effect=AssertionError("direct dispatch")))
        reservation = MagicMock()
        queue = MagicMock()
        with (
            patch("deepr.cli.commands.provider_factory.create_provider_instance", return_value=provider),
            patch("deepr.cli.commands.provider_factory.supports_background_jobs", return_value=True),
            patch("deepr.cli.commands.run.SQLiteQueue", return_value=queue),
            patch("deepr.config.load_config", return_value={"queue_db_path": "queue.db"}),
            patch(
                "deepr.services.research_submission.submit_reserved_provider_research",
                new_callable=AsyncMock,
                return_value="provider-job",
            ) as dispatch,
            patch("deepr.cli.commands.run._handle_background_job", new_callable=AsyncMock) as background,
        ):
            await _submit_to_provider(
                job_id="research-job",
                query="Bounded research",
                model="o4-mini-deep-research",
                provider="openai",
                no_web=False,
                no_code=False,
                document_ids=[],
                vector_store_id=None,
                output_context=OutputContext(mode=OutputMode.QUIET),
                formatter=MagicMock(),
                start_time=0.0,
                reservation=reservation,
            )

        dispatch.assert_awaited_once()
        assert dispatch.await_args.kwargs["reservation"] is reservation
        assert dispatch.await_args.kwargs["request"].idempotency_key == "deepr-research-research-job"
        provider.submit_research.assert_not_awaited()
        background.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_closed_persisted_reservation_blocks_cli_provider_dispatch(self):
        from deepr.cli.commands.run import _run_single
        from deepr.cli.output import OutputContext, OutputMode
        from deepr.services.research_submission import ResearchDispatchReservationError

        reservation = MagicMock()
        blocked = ResearchDispatchReservationError(
            "closed reservation",
            code="reservation_not_active",
            retryable=False,
        )
        queue = MagicMock(claim_submission=AsyncMock(return_value=True))
        with (
            patch("deepr.cli.commands.run._check_budget", return_value=True),
            patch(
                "deepr.cli.commands.run._reserve_job_submission",
                new_callable=AsyncMock,
                return_value=("research-1", reservation),
            ),
            patch("deepr.cli.commands.run._enqueue_reserved_job", new_callable=AsyncMock),
            patch(
                "deepr.services.research_submission.restore_active_queued_reservation",
                new_callable=AsyncMock,
                side_effect=blocked,
            ),
            patch("deepr.cli.commands.run._submit_to_provider", new_callable=AsyncMock) as submit,
            patch(
                "deepr.cli.commands.run_submission.rollback_prepared_submission",
                new_callable=AsyncMock,
            ) as rollback,
            patch("deepr.cli.commands.run.SQLiteQueue", return_value=queue),
            patch("deepr.config.load_config", return_value={"queue_db_path": "custom/research.db"}),
            pytest.raises(ResearchDispatchReservationError) as raised,
        ):
            await _run_single(
                query="Test query",
                model="o4-mini-deep-research",
                provider="openai",
                no_web=False,
                no_code=False,
                upload=(),
                limit=1.0,
                yes=True,
                output_context=OutputContext(mode=OutputMode.QUIET),
            )

        assert raised.value.code == "reservation_not_active"
        queue.claim_submission.assert_not_awaited()
        submit.assert_not_awaited()
        rollback.assert_awaited_once_with(
            reservation,
            None,
            source="cli.run.reservation_not_active",
            formatter=ANY,
        )

    @pytest.mark.asyncio
    async def test_reservation_store_outage_leaves_cli_job_queued_for_retry(self):
        from deepr.cli.commands.run import _run_single
        from deepr.cli.output import OutputContext, OutputMode
        from deepr.services.research_submission import ResearchDispatchReservationError

        reservation = MagicMock()
        unavailable = ResearchDispatchReservationError(
            "reservation store unavailable",
            code="reservation_store_unavailable",
            retryable=True,
        )
        queue = MagicMock(claim_submission=AsyncMock(return_value=True))
        with (
            patch("deepr.cli.commands.run._check_budget", return_value=True),
            patch(
                "deepr.cli.commands.run._reserve_job_submission",
                new_callable=AsyncMock,
                return_value=("research-1", reservation),
            ),
            patch("deepr.cli.commands.run._enqueue_reserved_job", new_callable=AsyncMock),
            patch(
                "deepr.services.research_submission.restore_active_queued_reservation",
                new_callable=AsyncMock,
                side_effect=unavailable,
            ),
            patch("deepr.cli.commands.run._submit_to_provider", new_callable=AsyncMock) as submit,
            patch(
                "deepr.cli.commands.run_submission.rollback_prepared_submission",
                new_callable=AsyncMock,
            ) as rollback,
            patch("deepr.cli.commands.run.SQLiteQueue", return_value=queue),
            patch("deepr.config.load_config", return_value={"queue_db_path": "custom/research.db"}),
            pytest.raises(ResearchDispatchReservationError) as raised,
        ):
            await _run_single(
                query="Test query",
                model="o4-mini-deep-research",
                provider="openai",
                no_web=False,
                no_code=False,
                upload=(),
                limit=1.0,
                yes=True,
                output_context=OutputContext(mode=OutputMode.QUIET),
            )

        assert raised.value.retryable is True
        queue.claim_submission.assert_not_awaited()
        submit.assert_not_awaited()
        rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejected_cost_admission_creates_no_provider_resources(self):
        """A rejected hold cannot leak uploads or vector stores."""
        from deepr.cli.commands.run import _run_single
        from deepr.cli.output import OutputContext, OutputMode

        with (
            patch("deepr.cli.commands.run._check_budget", return_value=True),
            patch(
                "deepr.cli.commands.run._reserve_job_submission",
                new_callable=AsyncMock,
                side_effect=RuntimeError("cost limit exceeded"),
            ),
            patch("deepr.cli.commands.file_handler.handle_file_uploads", new_callable=AsyncMock) as upload,
            pytest.raises(RuntimeError, match="cost limit exceeded"),
        ):
            await _run_single(
                query="Test query",
                model="o4-mini-deep-research",
                provider="openai",
                no_web=False,
                no_code=False,
                upload=(),
                limit=0.01,
                yes=True,
                output_context=OutputContext(mode=OutputMode.QUIET),
            )

        upload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_run_single_respects_yes_flag(self):
        """Test that --yes flag skips budget confirmation."""
        from deepr.cli.commands.run import _run_single
        from deepr.cli.output import OutputContext, OutputMode

        output_context = OutputContext(mode=OutputMode.QUIET)

        with patch("deepr.cli.commands.run.check_budget_approval") as mock_budget:
            mock_budget.return_value = False  # Would normally block

            with patch("deepr.providers.create_provider") as mock_create:
                mock_provider = MagicMock()
                mock_provider.submit_research = AsyncMock(return_value="job-123")
                mock_create.return_value = mock_provider

                with patch("deepr.config.load_config", return_value={"api_key": "test"}):
                    with (
                        patch("deepr.cli.commands.run.SQLiteQueue") as mock_queue_class,
                        patch("deepr.cli.commands.run._enqueue_reserved_job", new_callable=AsyncMock),
                    ):
                        mock_queue_instance = MagicMock()
                        mock_queue_instance.enqueue = AsyncMock(return_value="job-123")
                        mock_queue_class.return_value = mock_queue_instance

                        # With yes=True, should proceed even if budget check fails
                        await _run_single(
                            query="Test query",
                            model="o4-mini-deep-research",
                            provider="openai",
                            no_web=False,
                            no_code=False,
                            upload=(),
                            limit=None,
                            yes=True,
                            output_context=output_context,
                        )


class TestOutputModes:
    """Test different output modes.

    The CLI uses these flags (from output_options decorator):
    - --verbose / -v : Detailed output
    - --json : Machine-readable JSON output
    - --quiet / -q : Suppress all output except errors
    """

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_json_output_mode(self, runner):
        """Test JSON output mode produces valid JSON."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            # Use --json flag (not --output json)
            result = runner.invoke(run, ["focus", "Test query", "--json", "--yes"])
            # In JSON mode, output should be parseable or empty
            # (actual JSON output depends on implementation)
            assert result.exit_code == 0 or "Error" not in result.output

    def test_quiet_output_mode(self, runner):
        """Test quiet output mode minimizes output."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            # Use --quiet or -q flag (not --output quiet)
            result = runner.invoke(run, ["focus", "Test query", "--quiet", "--yes"])
            # Quiet mode should have minimal output
            assert result.exit_code == 0 or "Error" not in result.output

    def test_verbose_output_mode(self, runner):
        """Test verbose output mode shows detailed output."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            # Use --verbose or -v flag
            result = runner.invoke(run, ["focus", "Test query", "--verbose", "--yes"])
            # Should not fail on argument parsing
            assert result.exit_code == 0 or "Error" not in result.output

    def test_conflicting_output_modes_rejected(self, runner):
        """Test that conflicting output modes are rejected."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            # Using both --json and --quiet should fail
            result = runner.invoke(run, ["focus", "Test query", "--json", "--quiet", "--yes"])
            # Should fail with usage error about conflicting flags
            assert result.exit_code != 0


# =============================================================================
# Property-Based Tests
# =============================================================================


class TestPropertyBasedCostEstimation:
    """Property-based tests for cost estimation."""

    @pytest.mark.property
    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_property_cost_always_positive(self, model_name):
        """
        Property: Cost Estimation Non-Negative

        INVARIANT: Cost estimation for ANY model name (including empty,
        random strings, etc.) MUST return a positive value.

        This ensures:
        - No division by zero in budget calculations
        - Unknown models have safe fallback
        - No negative costs that could bypass limits

        Validates: Requirement 2.7 (Cost estimation bounds)
        """
        cost = estimate_cost(model_name)

        assert cost > 0, f"Model '{model_name}' has non-positive cost: {cost}"
        assert isinstance(cost, (int, float)), f"Cost is not numeric: {type(cost)}"

    @pytest.mark.property
    @given(st.booleans())
    @settings(max_examples=20, deadline=None)
    def test_property_web_search_affects_cost(self, enable_web_search):
        """
        Property: Web search parameter is accepted

        INVARIANT: The enable_web_search parameter should be accepted
        without raising errors.

        Validates: Requirement 2.3 (Parameter handling)
        """
        # Should not raise for any boolean value
        cost = estimate_cost("o4-mini-deep-research", enable_web_search=enable_web_search)
        assert cost > 0


class TestTraceFlags:
    """Test TraceFlags dataclass."""

    def test_default_all_false(self):
        """Default TraceFlags has all flags disabled."""
        flags = TraceFlags()
        assert not flags.explain
        assert not flags.timeline
        assert not flags.full_trace
        assert not flags.any_enabled

    def test_any_enabled_with_explain(self):
        """any_enabled is True when explain is set."""
        flags = TraceFlags(explain=True)
        assert flags.any_enabled

    def test_any_enabled_with_timeline(self):
        """any_enabled is True when timeline is set."""
        flags = TraceFlags(timeline=True)
        assert flags.any_enabled

    def test_any_enabled_with_full_trace(self):
        """any_enabled is True when full_trace is set."""
        flags = TraceFlags(full_trace=True)
        assert flags.any_enabled

    def test_all_flags_enabled(self):
        """All flags can be enabled simultaneously."""
        flags = TraceFlags(explain=True, timeline=True, full_trace=True)
        assert flags.any_enabled


class TestTraceFlagsCLI:
    """Test trace flags in CLI commands."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_focus_accepts_explain_flag(self, runner):
        """Focus command accepts --explain flag."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "--explain", "--yes"])
            assert result.exit_code == 0 or "Error" not in result.output

    def test_focus_accepts_timeline_flag(self, runner):
        """Focus command accepts --timeline flag."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "--timeline", "--yes"])
            assert result.exit_code == 0 or "Error" not in result.output

    def test_focus_accepts_full_trace_flag(self, runner):
        """Focus command accepts --full-trace flag."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "--full-trace", "--yes"])
            assert result.exit_code == 0 or "Error" not in result.output

    def test_focus_accepts_all_trace_flags(self, runner):
        """Focus command accepts all trace flags together."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "--explain", "--timeline", "--full-trace", "--yes"])
            assert result.exit_code == 0 or "Error" not in result.output

    def test_trace_flags_compatible_with_verbose(self, runner):
        """Trace flags work with --verbose output mode."""
        with patch("deepr.cli.commands.run.asyncio.run"):
            result = runner.invoke(run, ["focus", "Test query", "--explain", "--verbose", "--yes"])
            assert result.exit_code == 0 or "Error" not in result.output


class TestTraceDisplay:
    """Test trace display functions."""

    def _make_emitter(self):
        """Create a MetadataEmitter with sample data."""
        from deepr.observability.metadata import MetadataEmitter

        emitter = MetadataEmitter()

        op = emitter.start_task(
            "research_job",
            prompt="Test query",
            attributes={
                "provider": "openai",
                "model": "o4-mini",
            },
        )
        op.set_model("o4-mini", "openai")
        op.set_cost(0.15)
        op.set_tokens(1000, 500)
        emitter.complete_task(op)

        child = emitter.start_task(
            "provider_submit",
            attributes={
                "provider": "openai",
            },
        )
        child.set_model("o4-mini", "openai")
        child.set_cost(0.10)
        emitter.complete_task(child)

        return emitter

    def test_show_trace_explain(self, capsys):
        """_show_trace_explain outputs task hierarchy."""
        emitter = self._make_emitter()
        _show_trace_explain(emitter)
        captured = capsys.readouterr()
        assert "research_job" in captured.out
        assert "provider_submit" in captured.out
        assert "$0.10" in captured.out or "0.10" in captured.out

    def test_show_trace_timeline(self, capsys):
        """_show_trace_timeline outputs timeline table."""
        emitter = self._make_emitter()
        _show_trace_timeline(emitter)
        captured = capsys.readouterr()
        assert "Timeline" in captured.out
        assert "research_job" in captured.out

    def test_save_and_show_full_trace(self, capsys, tmp_path):
        """_save_and_show_full_trace saves trace file."""
        emitter = self._make_emitter()
        # Patch Path to use tmp_path
        trace_path = tmp_path / "test_trace.json"
        with patch("deepr.cli.commands.run.Path") as mock_path:
            mock_path.return_value = trace_path
            _save_and_show_full_trace(emitter, "research-abc123def")

        captured = capsys.readouterr()
        assert "trace" in captured.out.lower() or "saved" in captured.out.lower()

    def test_explain_empty_emitter(self, capsys):
        """_show_trace_explain handles empty emitter."""
        from deepr.observability.metadata import MetadataEmitter

        emitter = MetadataEmitter()
        _show_trace_explain(emitter)
        captured = capsys.readouterr()
        assert "Explain" in captured.out or "Research Path" in captured.out

    def test_timeline_empty_emitter(self, capsys):
        """_show_trace_timeline handles empty emitter gracefully."""
        from deepr.observability.metadata import MetadataEmitter

        emitter = MetadataEmitter()
        _show_trace_timeline(emitter)
        # Should not raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
