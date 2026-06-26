"""Tests for Azure OpenAI provider.

Covers request construction, response parsing, retries, vector-store lifecycle,
and the safety net for ``response.model = None`` (R3 audit fix).
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIConnectionError, APITimeoutError, RateLimitError
from openai import APIError as OpenAIAPIError

from deepr.providers.azure_provider import AzureProvider
from deepr.providers.base import ProviderError, ResearchRequest, ToolConfig


def _make_api_error(message: str = "boom") -> OpenAIAPIError:
    """Construct a minimal OpenAI APIError that doesn't require a live request."""
    err = OpenAIAPIError.__new__(OpenAIAPIError)
    err.message = message
    err.request = MagicMock()
    err.body = None
    err.code = None
    err.type = None
    err.param = None
    return err


def _make_rate_limit_error() -> RateLimitError:
    err = RateLimitError.__new__(RateLimitError)
    err.message = "rate limited"
    err.request = MagicMock()
    err.body = None
    err.code = None
    err.type = None
    err.param = None
    return err


def _make_timeout_error() -> APITimeoutError:
    err = APITimeoutError.__new__(APITimeoutError)
    err.message = "timeout"
    err.request = MagicMock()
    return err


def _make_connection_error() -> APIConnectionError:
    err = APIConnectionError.__new__(APIConnectionError)
    err.message = "conn lost"
    err.request = MagicMock()
    return err


@pytest.fixture
def provider():
    return AzureProvider(api_key="azure-test", endpoint="https://example.openai.azure.com/")


class TestInit:
    def test_endpoint_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="endpoint is required"):
                AzureProvider(api_key="k")

    def test_endpoint_from_env(self):
        with patch.dict(os.environ, {"AZURE_OPENAI_ENDPOINT": "https://e.azure.com/"}):
            p = AzureProvider(api_key="k")
            assert p.endpoint == "https://e.azure.com/"

    def test_api_key_required_when_not_managed_identity(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="API key is required"):
                AzureProvider(endpoint="https://e.azure.com/")

    def test_api_key_from_env(self):
        with patch.dict(os.environ, {"AZURE_OPENAI_KEY": "env-key"}):
            p = AzureProvider(endpoint="https://e.azure.com/")
            assert p.api_key == "env-key"

    def test_managed_identity_path(self):
        with patch("deepr.providers.azure_provider.DefaultAzureCredential") as cred:
            cred.return_value = MagicMock()
            p = AzureProvider(endpoint="https://e.azure.com/", use_managed_identity=True)
            assert p.use_managed_identity is True
            assert p._credential is not None

    def test_default_deployment_mappings(self, provider):
        # The defaults route the four canonical keys to deployment names.
        assert provider.get_model_name("o3") == "o3-deep-research"
        assert provider.get_model_name("o4-mini") == "o4-mini-deep-research"
        assert provider.get_model_name("o3-deep-research") == "o3-deep-research"
        assert provider.get_model_name("o4-mini-deep-research") == "o4-mini-deep-research"

    def test_custom_deployment_mappings_override(self):
        p = AzureProvider(
            api_key="k",
            endpoint="https://e.azure.com/",
            deployment_mappings={"my-key": "my-azure-deploy"},
        )
        assert p.get_model_name("my-key") == "my-azure-deploy"

    def test_unknown_model_passes_through(self, provider):
        assert provider.get_model_name("some-unmapped") == "some-unmapped"


class TestSubmitResearch:
    @pytest.mark.asyncio
    async def test_submit_basic(self, provider):
        mock_resp = MagicMock(id="resp_xyz")
        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as create:
            create.return_value = mock_resp
            req = ResearchRequest(
                prompt="p",
                model="o3",
                system_message="sys",
                tools=[],
                metadata={},
            )
            jid = await provider.submit_research(req)
            assert jid == "resp_xyz"
            kwargs = create.call_args.kwargs
            # Deployment-name remapping
            assert kwargs["model"] == "o3-deep-research"
            assert kwargs["store"] is True
            assert kwargs["background"] is True

    @pytest.mark.asyncio
    async def test_submit_with_file_search_tool(self, provider):
        mock_resp = MagicMock(id="resp_fs")
        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as create:
            create.return_value = mock_resp
            req = ResearchRequest(
                prompt="p",
                model="o4-mini",
                system_message="sys",
                tools=[ToolConfig(type="file_search", vector_store_ids=["vs_1", "vs_2"])],
                metadata={},
            )
            await provider.submit_research(req)
            kwargs = create.call_args.kwargs
            tools = kwargs["tools"]
            assert tools[0]["type"] == "file_search"
            assert tools[0]["vector_store_ids"] == ["vs_1", "vs_2"]

    @pytest.mark.asyncio
    async def test_submit_with_code_interpreter_tool(self, provider):
        mock_resp = MagicMock(id="resp_ci")
        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as create:
            create.return_value = mock_resp
            req = ResearchRequest(
                prompt="p",
                model="o3",
                system_message="sys",
                tools=[ToolConfig(type="code_interpreter", container={"type": "auto"})],
                metadata={},
            )
            await provider.submit_research(req)
            kwargs = create.call_args.kwargs
            assert kwargs["tools"][0]["container"] == {"type": "auto"}

    @pytest.mark.asyncio
    async def test_submit_with_webhook_and_temperature(self, provider):
        mock_resp = MagicMock(id="resp_wh")
        with patch.object(provider.client.responses, "create", new_callable=AsyncMock) as create:
            create.return_value = mock_resp
            req = ResearchRequest(
                prompt="p",
                model="o3",
                system_message="sys",
                tools=[],
                metadata={},
                webhook_url="https://hook.example/notify",
                temperature=0.42,
            )
            await provider.submit_research(req)
            kwargs = create.call_args.kwargs
            assert kwargs["extra_headers"] == {"OpenAI-Hook-URL": "https://hook.example/notify"}
            assert kwargs["temperature"] == 0.42

    @pytest.mark.asyncio
    async def test_submit_retries_rate_limit(self, provider, monkeypatch):
        # Sleep should be neutralised so the test runs instantly.
        async def _no_sleep(*_a, **_k):
            return None

        monkeypatch.setattr("deepr.providers.azure_provider.asyncio.sleep", _no_sleep)
        mock_resp = MagicMock(id="resp_after_retry")
        seq = [_make_rate_limit_error(), _make_rate_limit_error(), mock_resp]

        async def _side(*_a, **_k):
            val = seq.pop(0)
            if isinstance(val, Exception):
                raise val
            return val

        with patch.object(provider.client.responses, "create", side_effect=_side):
            req = ResearchRequest(prompt="p", model="o3", system_message="s", tools=[], metadata=None)
            jid = await provider.submit_research(req)
            assert jid == "resp_after_retry"

    @pytest.mark.asyncio
    async def test_submit_retries_exhausted(self, provider, monkeypatch):
        async def _no_sleep(*_a, **_k):
            return None

        monkeypatch.setattr("deepr.providers.azure_provider.asyncio.sleep", _no_sleep)

        async def _always_throttle(*_a, **_k):
            raise _make_rate_limit_error()

        with patch.object(provider.client.responses, "create", side_effect=_always_throttle):
            req = ResearchRequest(prompt="p", model="o3", system_message="s", tools=[], metadata=None)
            with pytest.raises(ProviderError, match="Azure failed after 3 retries"):
                await provider.submit_research(req)

    @pytest.mark.asyncio
    async def test_submit_retries_on_timeout_and_connection(self, provider, monkeypatch):
        async def _no_sleep(*_a, **_k):
            return None

        monkeypatch.setattr("deepr.providers.azure_provider.asyncio.sleep", _no_sleep)
        seq = [_make_timeout_error(), _make_connection_error(), MagicMock(id="ok")]

        async def _side(*_a, **_k):
            val = seq.pop(0)
            if isinstance(val, Exception):
                raise val
            return val

        with patch.object(provider.client.responses, "create", side_effect=_side):
            req = ResearchRequest(prompt="p", model="o3", system_message="s", tools=[], metadata=None)
            assert (await provider.submit_research(req)) == "ok"

    @pytest.mark.asyncio
    async def test_submit_non_transient_error_raises_immediately(self, provider):
        async def _err(*_a, **_k):
            raise _make_api_error("invalid request")

        with patch.object(provider.client.responses, "create", side_effect=_err):
            req = ResearchRequest(prompt="p", model="o3", system_message="s", tools=[], metadata=None)
            with pytest.raises(ProviderError, match="Failed to submit research"):
                await provider.submit_research(req)


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_status_basic(self, provider):
        resp = MagicMock()
        resp.id = "j1"
        resp.status = "completed"
        resp.model = "o4-mini-deep-research"
        resp.usage = MagicMock(input_tokens=100, output_tokens=50, total_tokens=150, reasoning_tokens=10)
        resp.output = []
        resp.created_at = 1_700_000_000
        resp.completed_at = 1_700_000_500
        resp.metadata = {"k": "v"}
        resp.error = None
        with patch.object(provider.client.responses, "retrieve", new_callable=AsyncMock) as r:
            r.return_value = resp
            out = await provider.get_status("j1")
            assert out.id == "j1"
            assert out.status == "completed"
            assert out.usage.input_tokens == 100
            assert out.usage.output_tokens == 50
            assert out.created_at is not None
            assert out.completed_at is not None
            assert out.metadata == {"k": "v"}

    @pytest.mark.asyncio
    async def test_status_handles_none_model(self, provider):
        """R3 audit fix: response.model = None must not crash calculate_cost."""
        resp = MagicMock()
        resp.id = "j2"
        resp.status = "completed"
        resp.model = None  # The exact failing condition
        resp.usage = MagicMock(input_tokens=10, output_tokens=5, total_tokens=15, reasoning_tokens=0)
        resp.output = None
        resp.created_at = None
        resp.completed_at = None
        resp.metadata = None
        resp.error = None
        # No content attribute on usage means none of these getattr fallbacks fail.
        with patch.object(provider.client.responses, "retrieve", new_callable=AsyncMock) as r:
            r.return_value = resp
            out = await provider.get_status("j2")
            # Did not crash; UsageStats.cost is computed off the fallback "o4-mini-deep-research".
            assert out.usage is not None
            assert out.usage.input_tokens == 10

    @pytest.mark.asyncio
    async def test_status_prices_cached_input_tokens(self, provider):
        resp = MagicMock()
        resp.id = "j_cached"
        resp.status = "completed"
        resp.model = "gpt-5"
        resp.usage = MagicMock(
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            reasoning_tokens=0,
        )
        resp.usage.input_tokens_details = MagicMock(cached_tokens=400)
        resp.usage.output_tokens_details = MagicMock(reasoning_tokens=125)
        resp.output = []
        resp.created_at = None
        resp.completed_at = None
        resp.metadata = None
        resp.error = None

        with patch.object(provider.client.responses, "retrieve", new_callable=AsyncMock) as r:
            r.return_value = resp
            out = await provider.get_status("j_cached")

        assert out.usage is not None
        assert out.usage.cached_input_tokens == 400
        assert out.usage.reasoning_tokens == 125
        assert out.usage.cost == pytest.approx(0.0058)

    @pytest.mark.asyncio
    async def test_status_parses_output_blocks(self, provider):
        resp = MagicMock()
        resp.id = "j3"
        resp.status = "completed"
        resp.usage = None
        block = MagicMock()
        block.type = "message"
        item = MagicMock()
        item.type = "output_text"
        item.text = "hello"
        block.content = [item]
        resp.output = [block]
        resp.created_at = None
        resp.completed_at = None
        resp.model = "o3"
        resp.metadata = None
        resp.error = None
        with patch.object(provider.client.responses, "retrieve", new_callable=AsyncMock) as r:
            r.return_value = resp
            out = await provider.get_status("j3")
            assert out.output[0]["type"] == "message"
            assert out.output[0]["content"][0]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_status_api_error_wrapped(self, provider):
        async def _err(*_a, **_k):
            raise _make_api_error("not found")

        with patch.object(provider.client.responses, "retrieve", side_effect=_err):
            with pytest.raises(ProviderError, match="Failed to get status"):
                await provider.get_status("missing")


class TestCancelJob:
    @pytest.mark.asyncio
    async def test_cancel_success(self, provider):
        with patch.object(provider.client.responses, "cancel", new_callable=AsyncMock) as c:
            c.return_value = MagicMock()
            assert (await provider.cancel_job("j1")) is True
            c.assert_called_once_with("j1")

    @pytest.mark.asyncio
    async def test_cancel_api_error(self, provider):
        async def _err(*_a, **_k):
            raise _make_api_error("nope")

        with patch.object(provider.client.responses, "cancel", side_effect=_err):
            with pytest.raises(ProviderError, match="Failed to cancel"):
                await provider.cancel_job("j1")


class TestUploadDocument:
    @pytest.mark.asyncio
    async def test_upload_returns_file_id(self, provider, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("hi")
        with patch.object(provider.client.files, "create", new_callable=AsyncMock) as c:
            c.return_value = MagicMock(id="file_abc")
            fid = await provider.upload_document(str(f))
            assert fid == "file_abc"

    @pytest.mark.asyncio
    async def test_upload_os_error_wrapped(self, provider):
        # file_path doesn't exist - open() will raise FileNotFoundError (subclass of OSError)
        with pytest.raises(ProviderError, match="Failed to upload"):
            await provider.upload_document("/this/path/does/not/exist.txt")

    @pytest.mark.asyncio
    async def test_upload_api_error_wrapped(self, provider, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("data")

        async def _err(*_a, **_k):
            raise _make_api_error("rejected")

        with patch.object(provider.client.files, "create", side_effect=_err):
            with pytest.raises(ProviderError, match="Failed to upload"):
                await provider.upload_document(str(f))


class TestVectorStore:
    @pytest.mark.asyncio
    async def test_create_vector_store_attaches_files(self, provider):
        vs = MagicMock(id="vs_1")
        with (
            patch.object(provider.client.vector_stores, "create", new_callable=AsyncMock) as c,
            patch.object(provider.client.vector_stores.files, "create", new_callable=AsyncMock) as f,
        ):
            c.return_value = vs
            out = await provider.create_vector_store("name", ["f1", "f2"])
            assert out.id == "vs_1"
            assert out.file_ids == ["f1", "f2"]
            assert f.call_count == 2

    @pytest.mark.asyncio
    async def test_create_vector_store_api_error(self, provider):
        async def _err(*_a, **_k):
            raise _make_api_error("vs failed")

        with patch.object(provider.client.vector_stores, "create", side_effect=_err):
            with pytest.raises(ProviderError, match="Failed to create vector store"):
                await provider.create_vector_store("n", [])

    @pytest.mark.asyncio
    async def test_wait_for_vector_store_completes(self, provider, monkeypatch):
        async def _no_sleep(*_a, **_k):
            return None

        monkeypatch.setattr("deepr.providers.azure_provider.asyncio.sleep", _no_sleep)
        listing = MagicMock()
        listing.data = [MagicMock(status="completed"), MagicMock(status="completed")]
        with patch.object(provider.client.vector_stores.files, "list", new_callable=AsyncMock) as lst:
            lst.return_value = listing
            ok = await provider.wait_for_vector_store("vs_1", timeout=10, poll_interval=0.0)
            assert ok is True

    @pytest.mark.asyncio
    async def test_wait_for_vector_store_times_out(self, provider, monkeypatch):
        async def _no_sleep(*_a, **_k):
            return None

        monkeypatch.setattr("deepr.providers.azure_provider.asyncio.sleep", _no_sleep)

        # Make the event-loop clock jump forward on each .time() call so we exit
        # the wait loop via the timeout branch immediately.
        loop = asyncio.get_event_loop()
        baseline = loop.time()
        times = iter([baseline, baseline + 10_000])

        def _fake_time(self_):
            try:
                return next(times)
            except StopIteration:
                return baseline + 10_000

        listing = MagicMock()
        listing.data = [MagicMock(status="in_progress")]
        with (
            patch.object(provider.client.vector_stores.files, "list", new_callable=AsyncMock) as lst,
            patch("asyncio.get_event_loop") as gel,
        ):
            lst.return_value = listing
            fake_loop = MagicMock()
            fake_loop.time = lambda: next(times, baseline + 10_000)
            gel.return_value = fake_loop
            with pytest.raises(TimeoutError):
                await provider.wait_for_vector_store("vs_1", timeout=1, poll_interval=0.0)

    @pytest.mark.asyncio
    async def test_wait_for_vector_store_api_error_wrapped(self, provider):
        async def _err(*_a, **_k):
            raise _make_api_error("list failed")

        with patch.object(provider.client.vector_stores.files, "list", side_effect=_err):
            with pytest.raises(ProviderError, match="Failed to wait for vector store"):
                await provider.wait_for_vector_store("vs_1", timeout=1, poll_interval=0.0)

    @pytest.mark.asyncio
    async def test_delete_vector_store(self, provider):
        with patch.object(provider.client.vector_stores, "delete", new_callable=AsyncMock) as d:
            d.return_value = MagicMock()
            assert (await provider.delete_vector_store("vs_1")) is True
            d.assert_called_once_with("vs_1")

    @pytest.mark.asyncio
    async def test_delete_vector_store_api_error(self, provider):
        async def _err(*_a, **_k):
            raise _make_api_error("delete denied")

        with patch.object(provider.client.vector_stores, "delete", side_effect=_err):
            with pytest.raises(ProviderError, match="Failed to delete vector store"):
                await provider.delete_vector_store("vs_1")

    @pytest.mark.asyncio
    async def test_list_vector_stores_returns_stores(self, provider):
        store_a = MagicMock(id="vs_a", name="Store A")
        store_b = MagicMock(id="vs_b", name="Store B")
        listing = MagicMock(data=[store_a, store_b])
        files_a = MagicMock(data=[MagicMock(id="f1"), MagicMock(id="f2")])
        files_b = MagicMock(data=[])
        with (
            patch.object(provider.client.vector_stores, "list", new_callable=AsyncMock) as ls,
            patch.object(provider.client.vector_stores.files, "list", new_callable=AsyncMock) as flist,
        ):
            ls.return_value = listing
            flist.side_effect = [files_a, files_b]
            stores = await provider.list_vector_stores()
            assert len(stores) == 2
            assert stores[0].id == "vs_a"
            assert stores[0].file_ids == ["f1", "f2"]
            assert stores[1].file_ids == []

    @pytest.mark.asyncio
    async def test_list_vector_stores_api_error(self, provider):
        async def _err(*_a, **_k):
            raise _make_api_error("list denied")

        with patch.object(provider.client.vector_stores, "list", side_effect=_err):
            with pytest.raises(ProviderError, match="Failed to list vector stores"):
                await provider.list_vector_stores()
