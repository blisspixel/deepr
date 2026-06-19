"""Tests for deepr.backends.local - local Ollama backend ($0, no live server).

Uses fake AsyncOpenAI-shaped clients so these run with no Ollama and no network.
"""

from __future__ import annotations

import pytest

from deepr.backends import local


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

        async def context_builder(_query):
            return _Context()

        fn = local.make_local_research_fn("qwen", client=_FakeClient(content="ok"), context_builder=context_builder)
        result = await fn("q", 1.0)
        assert result["fresh_context"] == {"source_count": 1}

    async def test_errors_are_reported_not_raised(self):
        fn = local.make_local_research_fn("qwen", client=_FakeClient(error=RuntimeError("boom")))
        result = await fn("q", 1.0)
        assert result["cost"] == 0.0
        assert result["answer"] == ""
        assert "boom" in result["error"]


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
