"""Coverage-focused tests for the Gemini provider.

Targets previously-uncovered branches: cancel/upload/vector-store lifecycle,
response builders for both deep-research and regular jobs, poll-interval
heuristic, and the large-context cost tier.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.providers.base import ResearchRequest
from deepr.providers.gemini_provider import DEEP_RESEARCH_AGENT, GeminiProvider


@pytest.fixture
def provider():
    return GeminiProvider(api_key="test-key")


# ---------------------------------------------------------------------- #
# _calculate_cost — tiered pricing
# ---------------------------------------------------------------------- #


class TestCalculateCost:
    def test_deep_research_uses_flat_estimate(self, provider):
        assert provider._calculate_cost(0, 0, DEEP_RESEARCH_AGENT) == provider.deep_research_cost_estimate

    def test_small_prompt_no_multiplier(self, provider):
        # Under 200K input tokens — multiplier is 1.0
        cost = provider._calculate_cost(10_000, 10_000, "gemini-3.1-pro-preview")
        assert cost > 0

    def test_large_context_doubles_3_1_pro(self, provider):
        small = provider._calculate_cost(199_000, 10_000, "gemini-3.1-pro-preview")
        big = provider._calculate_cost(201_000, 10_000, "gemini-3.1-pro-preview")
        # The big-context multiplier is 2.0 on both input and output components.
        assert big > small * 1.9

    def test_large_context_does_not_affect_flash(self, provider):
        small = provider._calculate_cost(199_000, 10_000, "gemini-2.5-flash")
        big = provider._calculate_cost(201_000, 10_000, "gemini-2.5-flash")
        # Flash is not in the multiplier set — scaling should be near-linear
        # (no 2x jump).
        ratio = big / small if small else 1.0
        assert ratio < 1.5

    def test_unknown_model_falls_back_to_flash(self, provider):
        # Unknown model uses the flash price entry as fallback.
        cost_unknown = provider._calculate_cost(1000, 1000, "totally-fake-model")
        cost_flash = provider._calculate_cost(1000, 1000, "gemini-2.5-flash")
        assert cost_unknown == cost_flash


# ---------------------------------------------------------------------- #
# get_poll_interval
# ---------------------------------------------------------------------- #


class TestPollInterval:
    def test_first_minute_fast(self):
        assert GeminiProvider.get_poll_interval(5.0) == 5.0
        assert GeminiProvider.get_poll_interval(59.0) == 5.0

    def test_one_to_five_minute_medium(self):
        assert GeminiProvider.get_poll_interval(60.0) == 10.0
        assert GeminiProvider.get_poll_interval(299.0) == 10.0

    def test_after_five_minutes_slow(self):
        assert GeminiProvider.get_poll_interval(300.0) == 20.0
        assert GeminiProvider.get_poll_interval(1000.0) == 20.0


# ---------------------------------------------------------------------- #
# cancel_job — both job types
# ---------------------------------------------------------------------- #


class TestCancelJob:
    @pytest.mark.asyncio
    async def test_cancel_deep_research_in_progress(self, provider):
        provider._deep_research_jobs["dr1"] = {
            "status": "in_progress",
            "file_store_name": None,
        }
        ok = await provider.cancel_job("dr1")
        assert ok is True
        assert provider._deep_research_jobs["dr1"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_deep_research_with_file_store_triggers_cleanup(self, provider):
        provider._deep_research_jobs["dr2"] = {
            "status": "queued",
            "file_store_name": "fs_abc",
        }
        with patch.object(provider, "_cleanup_file_search_store") as cleanup:
            cleanup.return_value = None
            # _cleanup_file_search_store is async; make it an AsyncMock.
            from unittest.mock import AsyncMock

            cleanup_async = AsyncMock()
            with patch.object(provider, "_cleanup_file_search_store", new=cleanup_async):
                ok = await provider.cancel_job("dr2")
                assert ok is True
                cleanup_async.assert_awaited_once_with("fs_abc")

    @pytest.mark.asyncio
    async def test_cancel_deep_research_already_terminal_returns_false(self, provider):
        provider._deep_research_jobs["dr3"] = {"status": "completed"}
        ok = await provider.cancel_job("dr3")
        assert ok is False

    @pytest.mark.asyncio
    async def test_cancel_regular_job(self, provider):
        provider.jobs["j1"] = {"status": "in_progress"}
        ok = await provider.cancel_job("j1")
        assert ok is True
        assert provider.jobs["j1"]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_unknown_returns_false(self, provider):
        assert (await provider.cancel_job("missing")) is False


# ---------------------------------------------------------------------- #
# upload_document
# ---------------------------------------------------------------------- #


class TestUpload:
    @pytest.mark.asyncio
    async def test_upload_markdown_picks_markdown_mime(self, provider, tmp_path):
        p = tmp_path / "doc.md"
        p.write_text("# hi")

        # The genai Client is a real object with slot-restricted attributes,
        # so swap the entire client out for a MagicMock.
        class FakeFile:
            name = "files/abc"

        provider.client = MagicMock()
        provider.client.files.upload = MagicMock(return_value=FakeFile())
        fid = await provider.upload_document(str(p))
        assert fid == "files/abc"
        assert provider.client.files.upload.call_args.kwargs["config"]["mime_type"] == "text/markdown"

    @pytest.mark.asyncio
    async def test_upload_txt_picks_text_mime(self, provider, tmp_path):
        p = tmp_path / "doc.txt"
        p.write_text("plain")

        class FakeFile:
            name = "files/txt1"

        provider.client = MagicMock()
        provider.client.files.upload = MagicMock(return_value=FakeFile())
        await provider.upload_document(str(p))
        assert provider.client.files.upload.call_args.kwargs["config"]["mime_type"] == "text/plain"

    @pytest.mark.asyncio
    async def test_upload_wraps_os_errors(self, provider):
        from deepr.providers.base import ProviderError

        with pytest.raises(ProviderError, match="Failed to upload"):
            await provider.upload_document("/does/not/exist.txt")


# ---------------------------------------------------------------------- #
# Vector store (in-memory) lifecycle
# ---------------------------------------------------------------------- #


class TestVectorStore:
    @pytest.mark.asyncio
    async def test_create_vector_store_records(self, provider):
        vs = await provider.create_vector_store("name", ["f1", "f2"])
        assert vs.name == "name"
        assert vs.file_ids == ["f1", "f2"]
        assert vs.id in provider.vector_stores

    @pytest.mark.asyncio
    async def test_wait_for_vector_store_returns_true_when_files_present(self, provider):
        vs = await provider.create_vector_store("name", ["f1"])
        provider.client = MagicMock()
        provider.client.files.get = MagicMock(return_value=MagicMock())
        assert (await provider.wait_for_vector_store(vs.id)) is True

    @pytest.mark.asyncio
    async def test_wait_for_vector_store_unknown_returns_false(self, provider):
        assert (await provider.wait_for_vector_store("nope")) is False

    @pytest.mark.asyncio
    async def test_list_vector_stores_empty_returns_empty(self, provider):
        # Before any vector_stores attribute exists.
        assert (await provider.list_vector_stores()) == []

    @pytest.mark.asyncio
    async def test_list_vector_stores_returns_recorded(self, provider):
        await provider.create_vector_store("n1", [])
        await provider.create_vector_store("n2", [])
        out = await provider.list_vector_stores(limit=10)
        assert len(out) == 2

    @pytest.mark.asyncio
    async def test_delete_vector_store_unknown_returns_false(self, provider):
        # No vector_stores attribute yet => returns False
        assert (await provider.delete_vector_store("vs_ghost")) is False

    @pytest.mark.asyncio
    async def test_delete_vector_store_removes(self, provider):
        vs = await provider.create_vector_store("n", [])
        ok = await provider.delete_vector_store(vs.id)
        assert ok is True
        assert vs.id not in provider.vector_stores


# ---------------------------------------------------------------------- #
# _build_deep_research_response + _get_regular_job_status
# ---------------------------------------------------------------------- #


class TestResponseBuilders:
    def test_completed_deep_research_response_has_estimated_cost(self, provider):
        job_data = {
            "status": "completed",
            "search_queries_count": 100,  # 100 * $0.035 = $3.50
            "output": "report body",
            "citations": [{"url": "https://example.com"}],
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "completed_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        out = provider._build_deep_research_response("interaction_123", job_data)
        assert out.id == "interaction_123"
        assert out.status == "completed"
        assert out.usage.cost >= 3.5
        assert out.output[0]["type"] == "message"
        assert out.metadata["citations"][0]["url"] == "https://example.com"

    def test_failed_deep_research_response_no_usage(self, provider):
        job_data = {
            "status": "failed",
            "error": "agent crashed",
            "citations": [],
        }
        out = provider._build_deep_research_response("i_fail", job_data)
        assert out.status == "failed"
        assert out.usage is None
        assert out.error == "agent crashed"

    def test_regular_job_status_with_usage_and_thoughts(self, provider):
        request = ResearchRequest(prompt="p", model="m", system_message="s")
        provider.jobs["j1"] = {
            "status": "completed",
            "model": "gemini-2.5-flash",
            "usage": {"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200},
            "output": "final answer",
            "thoughts": "thinking trace",
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "completed_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "request": request,
        }
        out = provider._get_regular_job_status("j1")
        assert out.status == "completed"
        assert out.usage is not None
        assert out.usage.cost > 0
        # Thoughts inserted before the output_text part.
        assert out.output[0]["content"][0]["type"] == "reasoning"
        assert out.output[0]["content"][1]["type"] == "output_text"

    def test_regular_job_status_no_usage_no_output(self, provider):
        provider.jobs["j2"] = {
            "status": "queued",
            "model": "gemini-2.5-flash",
        }
        out = provider._get_regular_job_status("j2")
        assert out.status == "queued"
        assert out.usage is None
        assert out.output is None
