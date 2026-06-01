"""Tests for deepr.experts.reflection.ReflectionEngine.

The engine splits perception (LLM scores dimensions) from decision (code derives
the verdict from thresholds), so the verdict logic is tested deterministically
with a fake client.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from deepr.experts.reflection import (
    ReflectionDimension,
    ReflectionEngine,
    ReflectionError,
    _verdict_from_scores,
)


class _FakeClient:
    def __init__(self, content: str):
        self._content = content
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))])


def _dims(*scores: float) -> list[ReflectionDimension]:
    names = ["grounding", "completeness", "calibration", "directness"]
    return [ReflectionDimension(n, s, "", []) for n, s in zip(names, scores)]


def _payload(*scores: float, followups: list[str] | None = None) -> str:
    names = ["grounding", "completeness", "calibration", "directness"]
    return json.dumps(
        {
            "dimensions": [{"name": n, "score": s, "assessment": "x", "issues": []} for n, s in zip(names, scores)],
            "followups": followups or [],
        }
    )


class TestVerdictThresholds:
    def test_strong_accepts(self):
        verdict, overall = _verdict_from_scores(_dims(0.9, 0.85, 0.8, 0.9))
        assert verdict == "accept"
        assert overall > 0.8

    def test_mixed_revises(self):
        verdict, _ = _verdict_from_scores(_dims(0.8, 0.7, 0.6, 0.7))
        assert verdict == "revise"

    def test_weak_re_researches(self):
        verdict, _ = _verdict_from_scores(_dims(0.4, 0.3, 0.5, 0.4))
        assert verdict == "re_research"

    def test_critical_floor_forces_re_research(self):
        # One critically-low dimension drags an otherwise-strong answer down.
        verdict, _ = _verdict_from_scores(_dims(0.95, 0.95, 0.3, 0.95))
        assert verdict == "re_research"

    def test_empty_is_re_research(self):
        assert _verdict_from_scores([])[0] == "re_research"


class TestReflect:
    @pytest.mark.asyncio
    async def test_empty_inputs_raise(self):
        eng = ReflectionEngine(client=_FakeClient("{}"))
        with pytest.raises(ReflectionError):
            await eng.reflect("", "answer")
        with pytest.raises(ReflectionError):
            await eng.reflect("question", "  ")

    @pytest.mark.asyncio
    async def test_depth_zero_skips(self):
        eng = ReflectionEngine(client=_FakeClient("{}"))
        report = await eng.reflect("q", "a", depth=0)
        assert report.verdict == "skipped"
        assert report.dimensions == []
        assert report.depth == 0

    @pytest.mark.asyncio
    async def test_full_pass_accepts_strong_answer(self):
        eng = ReflectionEngine(client=_FakeClient(_payload(0.9, 0.85, 0.8, 0.9, followups=["check 2027 data"])))
        report = await eng.reflect("Will X happen?", "A well-cited answer.")
        assert report.verdict == "accept"
        assert len(report.dimensions) == 4
        assert report.followups == ["check 2027 data"]

    @pytest.mark.asyncio
    async def test_missing_dimensions_filled_conservatively(self):
        # Model omits two dimensions -> they default to 0.0 -> re_research.
        partial = json.dumps({"dimensions": [{"name": "grounding", "score": 0.9, "assessment": "ok"}]})
        eng = ReflectionEngine(client=_FakeClient(partial))
        report = await eng.reflect("q", "a")
        assert len(report.dimensions) == 4
        assert report.verdict == "re_research"

    @pytest.mark.asyncio
    async def test_bad_json_raises(self):
        eng = ReflectionEngine(client=_FakeClient("not json"))
        with pytest.raises(ReflectionError):
            await eng.reflect("q", "a")

    @pytest.mark.asyncio
    async def test_score_clamped(self):
        eng = ReflectionEngine(client=_FakeClient(_payload(5.0, 0.9, 0.9, 0.9)))
        report = await eng.reflect("q", "a")
        assert report.dimensions[0].score == 1.0

    @pytest.mark.asyncio
    async def test_to_dict_shape(self):
        eng = ReflectionEngine(client=_FakeClient(_payload(0.8, 0.8, 0.8, 0.8)))
        d = (await eng.reflect("q", "a")).to_dict()
        assert set(d) >= {"question", "verdict", "overall_score", "dimensions", "followups", "depth"}

    def test_get_client_without_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ReflectionError):
            ReflectionEngine()._get_client()
