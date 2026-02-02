"""Tests for auto-fallback on provider failures (ROADMAP 5.2).

Tests the fallback loop in _run_single() that automatically retries
with different providers when one fails, using the AutonomousProviderRouter.

All tests use mocks to avoid external API calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from deepr.cli.output import OutputContext, OutputMode
from deepr.cli.commands.run import (
    _run_single,
    _classify_provider_error,
    TraceFlags,
    MAX_FALLBACK_ATTEMPTS,
)
from deepr.core.errors import (
    ProviderError,
    ProviderTimeoutError,
    ProviderRateLimitError,
    ProviderAuthError,
    ProviderUnavailableError,
)


# Common mock patches applied to all fallback tests
COMMON_PATCHES = {
    "queue_enqueue": "deepr.cli.commands.run.SQLiteQueue",
    "provider_factory": "deepr.cli.commands.run._submit_to_provider",
    "budget": "deepr.cli.commands.run._check_budget",
    "router_cls": "deepr.observability.provider_router.AutonomousProviderRouter",
}


def _make_output_context(mode=OutputMode.QUIET):
    """Create a quiet output context for tests."""
    return OutputContext(mode=mode)


def _make_mock_router(fallback_result=("xai", "grok-4-fast")):
    """Create a mock AutonomousProviderRouter."""
    router = MagicMock()
    router.select_provider.return_value = ("openai", "o4-mini-deep-research")
    router.get_fallback.return_value = fallback_result
    router.record_result.return_value = None
    return router


@pytest.fixture
def mock_queue():
    """Mock SQLiteQueue to avoid DB operations."""
    with patch("deepr.cli.commands.run.SQLiteQueue") as mock_cls:
        queue = MagicMock()
        queue.enqueue = AsyncMock(return_value="research-test123")
        queue.update_status = AsyncMock()
        queue.update_results = AsyncMock()
        mock_cls.return_value = queue
        yield queue


@pytest.fixture
def mock_budget():
    """Mock budget check to always approve."""
    with patch("deepr.cli.commands.run._check_budget", return_value=True):
        yield


@pytest.fixture
def mock_router():
    """Mock AutonomousProviderRouter."""
    router = _make_mock_router()
    with patch("deepr.observability.provider_router.AutonomousProviderRouter", return_value=router):
        yield router


class TestClassifyProviderError:
    """Tests for _classify_provider_error() helper."""

    def test_timeout_keyword(self):
        """Exception with 'timeout' maps to ProviderTimeoutError."""
        with pytest.raises(ProviderTimeoutError):
            _classify_provider_error(Exception("Connection timed out"), "openai")

    def test_rate_limit_keyword(self):
        """Exception with 'rate limit' maps to ProviderRateLimitError."""
        with pytest.raises(ProviderRateLimitError):
            _classify_provider_error(Exception("Rate limit exceeded"), "openai")

    def test_auth_keyword(self):
        """Exception with 'auth' maps to ProviderAuthError."""
        with pytest.raises(ProviderAuthError):
            _classify_provider_error(Exception("Authentication failed"), "openai")

    def test_unavailable_keyword(self):
        """Exception with '503' maps to ProviderUnavailableError."""
        with pytest.raises(ProviderUnavailableError):
            _classify_provider_error(Exception("HTTP 503"), "openai")

    def test_generic_error_maps_to_base(self):
        """Unknown exceptions map to base ProviderError."""
        with pytest.raises(ProviderError):
            _classify_provider_error(Exception("Something weird"), "openai")

    def test_core_error_passes_through(self):
        """Core ProviderError subclasses re-raise as-is."""
        with pytest.raises(ProviderRateLimitError):
            _classify_provider_error(ProviderRateLimitError("openai"), "openai")


class TestFallbackOnRateLimit:
    """Test fallback triggers on rate limit errors."""

    @pytest.mark.asyncio
    async def test_fallback_on_rate_limit(self, mock_queue, mock_budget):
        """Rate limit error should trigger immediate fallback to next provider."""
        call_count = 0

        async def mock_submit(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            provider = args[3]  # provider is 4th positional arg
            if provider == "openai":
                raise ProviderRateLimitError("openai")
            # Fallback provider succeeds
            return

        router = _make_mock_router(fallback_result=("xai", "grok-4-fast"))

        with patch("deepr.observability.provider_router.AutonomousProviderRouter", return_value=router), \
             patch("deepr.cli.commands.run._submit_to_provider", side_effect=mock_submit), \
             patch("deepr.observability.metadata.MetadataEmitter") as mock_emitter_cls:
            emitter = MagicMock()
            emitter.tasks = []
            emitter.trace_context.spans = []
            emitter.get_total_cost.return_value = 0.0
            op = MagicMock()
            op.metadata.status = "running"
            emitter.start_task.return_value = op
            emitter.complete_task.return_value = None
            emitter.fail_task.return_value = None
            emitter.save_trace.return_value = None
            mock_emitter_cls.return_value = emitter

            await _run_single(
                "test query", "o4-mini-deep-research", "openai",
                False, False, (), None, True,
                _make_output_context(),
            )

            # Should have called submit twice: once for openai (failed), once for fallback
            assert call_count == 2
            # Router should have recorded failure for openai
            router.record_result.assert_any_call(
                "openai", "o4-mini-deep-research", success=False, error=pytest.approx(str(ProviderRateLimitError("openai")), abs=100)
            )


class TestFallbackOnTimeout:
    """Test timeout retry-then-fallback behavior."""

    @pytest.mark.asyncio
    async def test_timeout_retries_then_falls_back(self, mock_queue, mock_budget):
        """Timeout should retry same provider once, then fallback."""
        calls = []

        async def mock_submit(*args, **kwargs):
            provider = args[3]
            model = args[2]
            calls.append((provider, model))
            if provider == "openai":
                raise ProviderTimeoutError("openai", timeout_seconds=30)
            return

        router = _make_mock_router(fallback_result=("xai", "grok-4-fast"))

        with patch("deepr.observability.provider_router.AutonomousProviderRouter", return_value=router), \
             patch("deepr.cli.commands.run._submit_to_provider", side_effect=mock_submit), \
             patch("deepr.observability.metadata.MetadataEmitter") as mock_emitter_cls:
            emitter = MagicMock()
            emitter.tasks = []
            emitter.trace_context.spans = []
            op = MagicMock()
            op.metadata.status = "running"
            emitter.start_task.return_value = op
            emitter.save_trace.return_value = None
            mock_emitter_cls.return_value = emitter

            await _run_single(
                "test query", "o4-mini-deep-research", "openai",
                False, False, (), None, True,
                _make_output_context(),
            )

            # Should retry openai once, then fallback to xai
            assert len(calls) == 3  # openai, openai (retry), xai
            assert calls[0] == ("openai", "o4-mini-deep-research")
            assert calls[1] == ("openai", "o4-mini-deep-research")
            assert calls[2] == ("xai", "grok-4-fast")


class TestFallbackOnAuth:
    """Test auth error skips provider without retry."""

    @pytest.mark.asyncio
    async def test_auth_skips_provider(self, mock_queue, mock_budget):
        """Auth error should skip provider without retrying."""
        calls = []

        async def mock_submit(*args, **kwargs):
            provider = args[3]
            calls.append(provider)
            if provider == "openai":
                raise ProviderAuthError("openai")
            return

        router = _make_mock_router()

        with patch("deepr.observability.provider_router.AutonomousProviderRouter", return_value=router), \
             patch("deepr.cli.commands.run._submit_to_provider", side_effect=mock_submit), \
             patch("deepr.observability.metadata.MetadataEmitter") as mock_emitter_cls:
            emitter = MagicMock()
            emitter.tasks = []
            emitter.trace_context.spans = []
            op = MagicMock()
            op.metadata.status = "running"
            emitter.start_task.return_value = op
            emitter.save_trace.return_value = None
            mock_emitter_cls.return_value = emitter

            await _run_single(
                "test query", "o4-mini-deep-research", "openai",
                False, False, (), None, True,
                _make_output_context(),
            )

            # openai once (no retry), then fallback
            assert calls == ["openai", "xai"]


class TestNoFallbackFlag:
    """Test --no-fallback flag behavior."""

    @pytest.mark.asyncio
    async def test_no_fallback_fails_immediately(self, mock_queue, mock_budget):
        """With --no-fallback, should fail after first error without trying fallback."""
        calls = []

        async def mock_submit(*args, **kwargs):
            provider = args[3]
            calls.append(provider)
            raise ProviderRateLimitError("openai")

        router = _make_mock_router()

        with patch("deepr.observability.provider_router.AutonomousProviderRouter", return_value=router), \
             patch("deepr.cli.commands.run._submit_to_provider", side_effect=mock_submit), \
             patch("deepr.observability.metadata.MetadataEmitter") as mock_emitter_cls:
            emitter = MagicMock()
            emitter.tasks = []
            emitter.trace_context.spans = []
            op = MagicMock()
            op.metadata.status = "running"
            emitter.start_task.return_value = op
            emitter.save_trace.return_value = None
            mock_emitter_cls.return_value = emitter

            await _run_single(
                "test query", "o4-mini-deep-research", "openai",
                False, False, (), None, True,
                _make_output_context(),
                no_fallback=True,
            )

            # Only one attempt, no fallback
            assert calls == ["openai"]
            # Router should NOT have been asked for fallback
            router.get_fallback.assert_not_called()


class TestRouterSelection:
    """Test router-based provider selection."""

    @pytest.mark.asyncio
    async def test_user_provider_skips_router_selection(self, mock_queue, mock_budget):
        """Explicit --provider should bypass router.select_provider()."""
        router = _make_mock_router()

        with patch("deepr.observability.provider_router.AutonomousProviderRouter", return_value=router), \
             patch("deepr.cli.commands.run._submit_to_provider", new_callable=AsyncMock), \
             patch("deepr.observability.metadata.MetadataEmitter") as mock_emitter_cls:
            emitter = MagicMock()
            emitter.tasks = []
            emitter.trace_context.spans = []
            op = MagicMock()
            op.metadata.status = "running"
            emitter.start_task.return_value = op
            emitter.save_trace.return_value = None
            mock_emitter_cls.return_value = emitter

            await _run_single(
                "test query", "o4-mini-deep-research", "openai",
                False, False, (), None, True,
                _make_output_context(),
                user_specified_provider=True,
            )

            # Router should NOT have been called for initial selection
            router.select_provider.assert_not_called()

    @pytest.mark.asyncio
    async def test_router_selection_when_no_provider(self, mock_queue, mock_budget):
        """Without explicit --provider, router should select provider."""
        router = _make_mock_router()
        router.select_provider.return_value = ("xai", "grok-4-fast")

        submitted_providers = []

        async def mock_submit(*args, **kwargs):
            submitted_providers.append(args[3])  # provider

        with patch("deepr.observability.provider_router.AutonomousProviderRouter", return_value=router), \
             patch("deepr.cli.commands.run._submit_to_provider", side_effect=mock_submit), \
             patch("deepr.observability.metadata.MetadataEmitter") as mock_emitter_cls:
            emitter = MagicMock()
            emitter.tasks = []
            emitter.trace_context.spans = []
            op = MagicMock()
            op.metadata.status = "running"
            emitter.start_task.return_value = op
            emitter.save_trace.return_value = None
            mock_emitter_cls.return_value = emitter

            await _run_single(
                "test query", "o4-mini-deep-research", "openai",
                False, False, (), None, True,
                _make_output_context(),
                user_specified_provider=False,
            )

            # Router should have been called for initial selection
            router.select_provider.assert_called_once_with(task_type="research")
            # Provider used should be what router selected
            assert submitted_providers == ["xai"]


class TestVectorStoreDegradation:
    """Test vector store handling on fallback."""

    @pytest.mark.asyncio
    async def test_fallback_drops_vector_store(self, mock_queue, mock_budget):
        """Fallback from openai to xai should drop vector_store_id."""
        submitted_args = []

        async def mock_submit(*args, **kwargs):
            provider = args[3]
            vector_store_id = args[7]  # 8th positional arg
            submitted_args.append({"provider": provider, "vector_store_id": vector_store_id})
            if provider == "openai":
                raise ProviderUnavailableError("openai")
            return

        router = _make_mock_router(fallback_result=("xai", "grok-4-fast"))

        with patch("deepr.observability.provider_router.AutonomousProviderRouter", return_value=router), \
             patch("deepr.cli.commands.run._submit_to_provider", side_effect=mock_submit), \
             patch("deepr.cli.commands.run._create_and_enqueue_job", new_callable=AsyncMock) as mock_enqueue, \
             patch("deepr.observability.metadata.MetadataEmitter") as mock_emitter_cls:
            mock_enqueue.return_value = ("research-test123", MagicMock())
            emitter = MagicMock()
            emitter.tasks = []
            emitter.trace_context.spans = []
            op = MagicMock()
            op.metadata.status = "running"
            emitter.start_task.return_value = op
            emitter.save_trace.return_value = None
            mock_emitter_cls.return_value = emitter

            # Simulate having a vector_store_id (would have been set by file upload to openai)
            # We need to set vector_store_id in the function scope - we'll patch supports_vector_stores
            with patch("deepr.cli.commands.file_handler.handle_file_uploads") as mock_uploads:
                upload_result = MagicMock()
                upload_result.has_errors = False
                upload_result.vector_store_id = "vs_test123"
                upload_result.uploaded_ids = ["file_123"]
                upload_result.errors = []
                mock_uploads.return_value = upload_result

                with patch("deepr.config.load_config", return_value={}):
                    await _run_single(
                        "test query", "o4-mini-deep-research", "openai",
                        False, False, ("test.pdf",), None, True,
                        _make_output_context(),
                    )

            # First call (openai) should have vector_store_id
            assert submitted_args[0]["provider"] == "openai"
            assert submitted_args[0]["vector_store_id"] == "vs_test123"
            # Second call (xai) should have vector_store_id dropped
            assert submitted_args[1]["provider"] == "xai"
            assert submitted_args[1]["vector_store_id"] is None


class TestMaxFallbackAttempts:
    """Test fallback attempt limits."""

    @pytest.mark.asyncio
    async def test_max_fallback_attempts(self, mock_queue, mock_budget):
        """Should give up after MAX_FALLBACK_ATTEMPTS fallback attempts."""
        calls = []

        async def mock_submit(*args, **kwargs):
            provider = args[3]
            calls.append(provider)
            raise ProviderError(f"{provider} unavailable")

        # Router returns different fallbacks each time
        fallback_sequence = [
            ("xai", "grok-4-fast"),
            ("gemini", "gemini-2.5-flash"),
            ("anthropic", "claude-3-5-sonnet"),
            ("openai", "gpt-4o-mini"),  # Should not reach this
        ]
        call_idx = [0]

        def get_fallback(*args, **kwargs):
            if call_idx[0] < len(fallback_sequence):
                result = fallback_sequence[call_idx[0]]
                call_idx[0] += 1
                return result
            return None

        router = MagicMock()
        router.select_provider.return_value = ("openai", "o4-mini-deep-research")
        router.get_fallback.side_effect = get_fallback
        router.record_result.return_value = None

        with patch("deepr.observability.provider_router.AutonomousProviderRouter", return_value=router), \
             patch("deepr.cli.commands.run._submit_to_provider", side_effect=mock_submit), \
             patch("deepr.observability.metadata.MetadataEmitter") as mock_emitter_cls:
            emitter = MagicMock()
            emitter.tasks = []
            emitter.trace_context.spans = []
            op = MagicMock()
            op.metadata.status = "running"
            emitter.start_task.return_value = op
            emitter.save_trace.return_value = None
            mock_emitter_cls.return_value = emitter

            await _run_single(
                "test query", "o4-mini-deep-research", "openai",
                False, False, (), None, True,
                _make_output_context(),
            )

            # 1 initial + MAX_FALLBACK_ATTEMPTS fallbacks = 4 total attempts
            assert len(calls) == 1 + MAX_FALLBACK_ATTEMPTS


class TestSuccessRecording:
    """Test that successful results are recorded to router."""

    @pytest.mark.asyncio
    async def test_success_records_to_router(self, mock_queue, mock_budget):
        """Successful submission should record result to router."""
        router = _make_mock_router()

        with patch("deepr.observability.provider_router.AutonomousProviderRouter", return_value=router), \
             patch("deepr.cli.commands.run._submit_to_provider", new_callable=AsyncMock), \
             patch("deepr.observability.metadata.MetadataEmitter") as mock_emitter_cls:
            emitter = MagicMock()
            emitter.tasks = []
            emitter.trace_context.spans = []
            op = MagicMock()
            op.metadata.status = "running"
            emitter.start_task.return_value = op
            emitter.save_trace.return_value = None
            mock_emitter_cls.return_value = emitter

            await _run_single(
                "test query", "o4-mini-deep-research", "openai",
                False, False, (), None, True,
                _make_output_context(),
            )

            # Should have recorded success
            router.record_result.assert_called_once()
            call_kwargs = router.record_result.call_args
            assert call_kwargs[1]["success"] is True
            assert call_kwargs[0] == ("openai", "o4-mini-deep-research")


class TestFallbackTraceEvents:
    """Test that fallback events are emitted to trace."""

    @pytest.mark.asyncio
    async def test_fallback_event_in_trace(self, mock_queue, mock_budget):
        """Fallback should emit 'fallback_triggered' event to trace."""
        call_count = [0]

        async def mock_submit(*args, **kwargs):
            call_count[0] += 1
            provider = args[3]
            if provider == "openai":
                raise ProviderRateLimitError("openai")
            return

        router = _make_mock_router(fallback_result=("xai", "grok-4-fast"))

        with patch("deepr.observability.provider_router.AutonomousProviderRouter", return_value=router), \
             patch("deepr.cli.commands.run._submit_to_provider", side_effect=mock_submit), \
             patch("deepr.observability.metadata.MetadataEmitter") as mock_emitter_cls:
            emitter = MagicMock()
            emitter.tasks = []
            emitter.trace_context.spans = []
            op = MagicMock()
            op.metadata.status = "running"
            emitter.start_task.return_value = op
            emitter.save_trace.return_value = None
            mock_emitter_cls.return_value = emitter

            await _run_single(
                "test query", "o4-mini-deep-research", "openai",
                False, False, (), None, True,
                _make_output_context(),
            )

            # Should have emitted fallback event
            op.add_event.assert_called_once()
            event_name, event_attrs = op.add_event.call_args[0]
            assert event_name == "fallback_triggered"
            assert event_attrs["from_provider"] == "openai"
            assert event_attrs["to_provider"] == "xai"
            assert event_attrs["to_model"] == "grok-4-fast"
