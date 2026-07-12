"""Tests for deepr.backends.local - local Ollama backend ($0, no live server).

Uses fake AsyncOpenAI-shaped clients so these run with no Ollama and no network.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from deepr.backends import local
from deepr.backends.fresh_context import FreshContext, FreshContextConfig, FreshSource, deep_fresh_context_config


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content=None, error=None):
        self._content = content
        self._error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content=None, error=None):
        self.completions = _FakeCompletions(content, error)


class _FakeClient:
    def __init__(self, content=None, error=None):
        self.chat = _FakeChat(content, error)


class TestResearchFn:
    async def test_returns_answer_and_zero_cost(self):
        fn = local.make_local_research_fn("qwen", client=_FakeClient(content="the answer"))
        result = await fn("what changed?", 5.0)
        assert result == {"answer": "the answer", "cost": 0.0}

    async def test_injects_context_builder_output(self):
        async def context_builder(query):
            assert query == "what changed?"
            return "## Fresh retrieval context\n[S1] Source\nURL: https://example.com\nnew facts"

        client = _FakeClient(content="the answer")
        fn = local.make_local_research_fn("qwen", client=client, context_builder=context_builder)
        result = await fn("what changed?", 5.0)
        prompt = client.chat.completions.calls[0]["messages"][0]["content"]
        assert result == {"answer": "the answer", "cost": 0.0}
        assert "Fresh retrieval context" in prompt
        assert "what changed?" in prompt
        assert "cite source labels" in prompt
        assert "name meaningful gaps" in prompt

    async def test_reports_context_metadata(self):
        class _Context:
            def to_prompt_context(self):
                return "ctx"

            def to_metadata(self):
                return {"source_count": 1}

            def to_source_pack(self, *, include_content: bool = False):
                assert include_content is True  # sync persister needs full text for snapshots
                return {"schema_version": "deepr.source_pack.v1", "source_count": 1}

        async def context_builder(_query):
            return _Context()

        fn = local.make_local_research_fn("qwen", client=_FakeClient(content="ok"), context_builder=context_builder)
        result = await fn("q", 1.0)
        assert result["fresh_context"] == {"source_count": 1}
        assert result["source_pack"] == {"schema_version": "deepr.source_pack.v1", "source_count": 1}

    async def test_passes_prior_source_pack_to_context_builder_when_supported(self):
        prior_pack = {"sources": [{"url": "https://example.com", "etag": '"abc"'}]}
        seen = {}

        async def context_builder(query, *, prior_source_pack=None):
            seen["query"] = query
            seen["prior_source_pack"] = prior_source_pack
            return "ctx"

        fn = local.make_local_research_fn("qwen", client=_FakeClient(content="ok"), context_builder=context_builder)
        result = await fn("q", 1.0, prior_source_pack=prior_pack)

        assert result["answer"] == "ok"
        assert seen == {"query": "q", "prior_source_pack": prior_pack}

    async def test_uses_concise_retrieval_query_but_keeps_full_answer_prompt(self):
        seen = []

        async def context_builder(query):
            seen.append(query)
            return "ctx"

        client = _FakeClient(content="ok")
        fn = local.make_local_research_fn("qwen", client=client, context_builder=context_builder)
        result = await fn(
            "Provide a comprehensive answer with detailed synthesis instructions.",
            1.0,
            retrieval_query="concise topic Focus: bounded focus",
        )

        assert result["answer"] == "ok"
        assert seen == ["concise topic Focus: bounded focus"]
        prompt = client.chat.completions.calls[0]["messages"][0]["content"]
        assert "Provide a comprehensive answer with detailed synthesis instructions." in prompt
        assert "concise topic Focus: bounded focus" not in prompt

    @pytest.mark.parametrize(
        ("mode", "config", "source_count", "required"),
        [
            ("fresh", FreshContextConfig(), 1, 2),
            ("deep", deep_fresh_context_config(), 2, 3),
        ],
    )
    async def test_under_ready_context_skips_local_model_and_returns_evidence(
        self,
        mode,
        config,
        source_count,
        required,
    ):
        context = FreshContext(
            query="search-discovered topic",
            generated_at="2026-07-11T00:00:00Z",
            mode=mode,
            prompt_config=config,
            sources=tuple(
                FreshSource(
                    title=f"Source {index}",
                    url=f"https://example.com/{index}",
                    content=f"Fetched page {index}",
                )
                for index in range(source_count)
            ),
        )

        async def context_builder(_query):
            return context

        client = _FakeClient(content="must not be used")
        fn = local.make_local_research_fn("qwen", client=client, context_builder=context_builder)
        result = await fn("full answer prompt", 1.0)

        assert client.chat.completions.calls == []
        assert result["answer"] == ""
        assert result["cost"] == 0.0
        assert result["error_code"] == "fresh_context_not_ready"
        assert result["retryable"] is True
        assert result["no_metered_fallback"] is True
        assert result["context_preflight"]["required_source_count"] == required
        assert result["fresh_context"]["retrieved_source_count"] == source_count
        assert len(result["source_pack"]["sources"]) == source_count
        assert "No generation backend was called" in result["error"]

    async def test_errors_are_reported_not_raised(self):
        fn = local.make_local_research_fn("qwen", client=_FakeClient(error=RuntimeError("boom")))
        result = await fn("q", 1.0)
        assert result["cost"] == 0.0
        assert result["answer"] == ""
        assert "boom" in result["error"]


class _FakeEmbeddingRow:
    def __init__(self, index, embedding):
        self.index = index
        self.embedding = embedding


class _FakeEmbeddingResponse:
    def __init__(self, rows):
        self.data = rows


class _FakeEmbeddings:
    def __init__(self, rows=None, error=None):
        self._rows = rows or []
        self._error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return _FakeEmbeddingResponse(self._rows)


class _FakeEmbeddingClient:
    def __init__(self, rows=None, error=None):
        self.embeddings = _FakeEmbeddings(rows, error)


class TestLocalEmbedder:
    async def test_returns_vectors_in_claim_order(self):
        rows = [
            _FakeEmbeddingRow(1, [0.0, 1.0]),
            _FakeEmbeddingRow(0, [1.0, 0.0]),
        ]
        client = _FakeEmbeddingClient(rows=rows)
        embed = local.make_local_embedder("nomic-embed-text", client=client)

        vectors = await embed(["first claim", "second claim"])

        assert vectors == [(1.0, 0.0), (0.0, 1.0)]
        call = client.embeddings.calls[0]
        assert call["model"] == "nomic-embed-text"
        assert call["input"] == ["first claim", "second claim"]
        assert call["extra_body"] == {"keep_alive": local._KEEP_ALIVE}

    async def test_empty_input_short_circuits_without_a_call(self):
        client = _FakeEmbeddingClient(rows=[])
        embed = local.make_local_embedder("nomic-embed-text", client=client)

        assert await embed([]) == []
        assert client.embeddings.calls == []

    async def test_vector_count_mismatch_raises(self):
        client = _FakeEmbeddingClient(rows=[_FakeEmbeddingRow(0, [1.0])])
        embed = local.make_local_embedder("nomic-embed-text", client=client)

        with pytest.raises(RuntimeError, match="returned 1 vector"):
            await embed(["one", "two"])

    async def test_transport_errors_propagate(self):
        client = _FakeEmbeddingClient(error=ConnectionError("refused"))
        embed = local.make_local_embedder("nomic-embed-text", client=client)

        with pytest.raises(ConnectionError, match="refused"):
            await embed(["claim"])

    def test_blank_model_is_rejected(self):
        with pytest.raises(ValueError, match="embedding model is required"):
            local.make_local_embedder("  ", client=_FakeEmbeddingClient())


class TestProbe:
    async def test_ok(self):
        result = await local.probe_local("qwen", client=_FakeClient(content="OK"))
        assert result["ok"] is True
        assert result["model"] == "qwen"
        assert result["reply"] == "OK"
        assert "latency_ms" in result

    async def test_no_model_available(self, monkeypatch):
        monkeypatch.setattr(local, "default_local_model", lambda base_url=None: None)
        result = await local.probe_local(client=_FakeClient(content="OK"))
        assert result["ok"] is False
        assert "no local model" in result["error"]

    async def test_failure_reported(self):
        result = await local.probe_local("qwen", client=_FakeClient(error=ConnectionError("refused")))
        assert result["ok"] is False
        assert "refused" in result["error"]


class TestDefaultModel:
    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DEEPR_LOCAL_MODEL", "my-model:7b")
        assert local.default_local_model() == "my-model:7b"

    def test_parsed_from_status(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_MODEL", raising=False)
        monkeypatch.setattr(local, "ollama_status", lambda base_url=None: (True, "2 model(s): foo:1b, bar:7b"))
        assert local.default_local_model() == "foo:1b"

    def test_none_when_not_running(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_MODEL", raising=False)
        monkeypatch.setattr(local, "ollama_status", lambda base_url=None: (False, "not reachable"))
        assert local.default_local_model() is None

    async def test_async_env_override_avoids_probe(self, monkeypatch):
        monkeypatch.setenv("DEEPR_LOCAL_MODEL", "my-model:7b")

        assert await local.default_local_model_async() == "my-model:7b"

    async def test_async_probe_returns_first_model(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_MODEL", raising=False)

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"models": [{"name": "first:7b"}, {"name": "second:14b"}]}

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def get(self, url):
                assert url.endswith("/api/tags")
                return FakeResponse()

        import httpx

        monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: FakeClient())

        assert await local.default_local_model_async() == "first:7b"

    async def test_async_probe_propagates_cancellation(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_MODEL", raising=False)

        class CancelledClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def get(self, _url):
                raise asyncio.CancelledError

        import httpx

        monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: CancelledClient())

        with pytest.raises(asyncio.CancelledError):
            await local.default_local_model_async()


class TestMaintenanceModel:
    def test_explicit_model_overrides_recorded_profile_model(self, monkeypatch):
        monkeypatch.setattr(local, "default_local_model", lambda base_url=None: "global-model")
        profile = SimpleNamespace(provider="local", model="profile-model")

        assert local.resolve_local_maintenance_model(profile, explicit_model="command-model") == "command-model"

    def test_local_profile_model_precedes_global_default(self, monkeypatch):
        monkeypatch.setattr(local, "default_local_model", lambda base_url=None: "global-model")
        profile = SimpleNamespace(provider="local", model="profile-model")

        assert local.resolve_local_maintenance_model(profile) == "profile-model"

    @pytest.mark.parametrize(
        "profile",
        [
            SimpleNamespace(provider="openai", model="gpt-5.5"),
            SimpleNamespace(provider="local", model="ollama"),
            SimpleNamespace(provider="local", model=""),
        ],
    )
    def test_nonlocal_and_placeholder_profiles_keep_global_default(self, monkeypatch, profile):
        monkeypatch.setattr(local, "default_local_model", lambda base_url=None: "global-model")

        assert local.resolve_local_maintenance_model(profile) == "global-model"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestOllamaChatClientTimeout:
    """Local generation may run for many minutes; the client must not abort it
    at the OpenAI SDK's 600s default. (User requirement: slow local = fine.)"""

    def _capture(self, monkeypatch):
        captured = {}

        class FakeAsyncOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        import openai

        monkeypatch.setattr(openai, "AsyncOpenAI", FakeAsyncOpenAI)
        return captured

    def test_default_timeout_is_generous(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_TIMEOUT", raising=False)
        captured = self._capture(monkeypatch)
        local.ollama_chat_client()
        assert captured["timeout"] == 3600.0  # not the 600s SDK default

    def test_timeout_env_override(self, monkeypatch):
        monkeypatch.setenv("DEEPR_LOCAL_TIMEOUT", "7200")
        captured = self._capture(monkeypatch)
        local.ollama_chat_client()
        assert captured["timeout"] == 7200.0

    def test_explicit_timeout_wins(self, monkeypatch):
        captured = self._capture(monkeypatch)
        local.ollama_chat_client(timeout=120.0)
        assert captured["timeout"] == 120.0
