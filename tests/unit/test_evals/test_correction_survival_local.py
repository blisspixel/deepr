"""Local answers for the correction-survival diagnostic: production dispatch, pinned digest."""

import asyncio
from types import SimpleNamespace

import pytest

from deepr.evals import correction_survival as cs
from deepr.evals.correction_survival_cases import CASES
from deepr.evals.correction_survival_local import LocalAnswerer
from deepr.experts.semantic_model_gate import _mark_zero_dollar_client


class _Native:
    def __init__(self, digests):
        self.digests = list(digests)
        self.last_attested_digest = ""
        self.pinned_digest = ""
        self.timeout = 0.0
        self.requests = []

    async def attest_model(self, model):
        self.last_attested_digest = self.digests[0]
        return self.last_attested_digest

    async def complete(self, request):
        self.requests.append(request)
        # The real backend re-attests on every dispatch; the last digest is what the daemon serves now.
        self.last_attested_digest = self.digests[-1]
        return SimpleNamespace(
            message=SimpleNamespace(content="Local answer."),
            stop_reason="stop",
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3),
            provider_request_id="",
        )


def _answerer(monkeypatch, digests, *, pin=""):
    native = _mark_zero_dollar_client(_Native(digests), capacity_source="local")
    backend = SimpleNamespace(client=native, model="fixture:27b")
    monkeypatch.setattr("deepr.experts.consult.build_synthesis_backend", lambda **kwargs: backend)
    return LocalAnswerer("fixture:27b", digest=pin), native


def test_answers_go_through_the_production_system_prompt_and_budget(monkeypatch):
    from deepr.experts.council import LOCAL_SYNTHESIS_OUTPUT_TOKENS, SYNTHESIS_SYSTEM_PROMPT

    answerer, native = _answerer(monkeypatch, ["d1"])
    assert asyncio.run(answerer.attest()) == "d1"
    assert answerer.identity == "local:fixture:27b@d1"
    assert asyncio.run(answerer("user prompt")) == "Local answer."
    request = native.requests[0]
    assert request.messages == [
        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
        {"role": "user", "content": "user prompt"},
    ]
    assert request.extra["max_tokens"] == LOCAL_SYNTHESIS_OUTPUT_TOKENS
    assert answerer.calls[0]["status"] == "returned"
    assert answerer.calls[0]["observed_digest"] == "d1"
    assert answerer.calls[0]["cost_usd"] == 0.0


def test_a_pinned_digest_that_differs_refuses_before_any_answer(monkeypatch):
    answerer, native = _answerer(monkeypatch, ["other"], pin="d1")
    with pytest.raises(RuntimeError, match="differs from the pinned"):
        asyncio.run(answerer.attest())
    assert native.requests == []


def test_a_digest_change_mid_run_fails_the_attempt(monkeypatch):
    answerer, _ = _answerer(monkeypatch, ["d1", "d2"])
    asyncio.run(answerer.attest())
    with pytest.raises(RuntimeError, match="digest changed"):
        asyncio.run(answerer("prompt"))
    assert answerer.calls[-1]["error_type"] == "DigestChanged"


def test_run_records_each_dispatch_with_its_attempt(monkeypatch, tmp_path):
    answerer, _ = _answerer(monkeypatch, ["d1"])
    asyncio.run(answerer.attest())
    seen = []
    run = asyncio.run(
        cs.run_diagnostic(
            tmp_path / "run",
            completion=answerer,
            model_identity=answerer.identity,
            cases=CASES[:1],
            on_attempt=lambda attempt, done, total: seen.append((done, total)),
        )
    )
    assert run["model_identity"] == "local:fixture:27b@d1"
    assert seen == [(1, 3), (2, 3), (3, 3)]
    for attempt in run["attempts"]:
        assert attempt["dispatch"]["status"] == "returned"
        assert attempt["dispatch"]["prompt_sha256"] == attempt["prompt_sha256"]
