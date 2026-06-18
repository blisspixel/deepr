"""Tests for deepr.backends.waterfall - backend selection ($0, no I/O).

``available_models_fn`` and the admissions ``path``/``now`` are injected, so
these exercise the full waterfall logic with no Ollama and no real ledger.
Selection is admission-driven: an admitted model is used only if it is also
currently available.
"""

from __future__ import annotations

from datetime import UTC, datetime

from deepr.backends.admission import record_admission
from deepr.backends.waterfall import (
    BACKEND_API_METERED,
    BACKEND_LOCAL,
    choose_maintenance_backend,
)

T0 = datetime(2026, 6, 13, tzinfo=UTC)


def _choose(task_class, *, available, path, now=T0):
    return choose_maintenance_backend(
        task_class, now=now, available_models_fn=lambda: list(available), admissions_path=path
    )


class TestChoose:
    def test_nothing_admitted_falls_to_metered(self, tmp_path):
        choice = _choose("sync", available=["llama3.1"], path=tmp_path / "a.jsonl")
        assert choice.backend == BACKEND_API_METERED
        assert not choice.is_local
        assert "no local model admitted" in choice.reason

    def test_admitted_but_ollama_unreachable(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", score=0.8, now=T0, path=p)
        choice = _choose("sync", available=[], path=p)
        assert choice.backend == BACKEND_API_METERED
        assert "not reachable" in choice.reason

    def test_admitted_but_model_not_loaded(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", score=0.8, now=T0, path=p)
        # Ollama is up but serving a different model.
        choice = _choose("sync", available=["other-model"], path=p)
        assert choice.backend == BACKEND_API_METERED
        assert "unavailable" in choice.reason

    def test_admitted_and_available_is_chosen(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", score=0.8, now=T0, path=p)
        choice = _choose("sync", available=["llama3.1", "other"], path=p)
        assert choice.backend == BACKEND_LOCAL
        assert choice.is_local
        assert choice.model == "llama3.1"
        assert "quality 0.800 clears floor 0.700" in choice.reason
        assert "owned capacity before metered API" in choice.reason

    def test_scoreless_admission_does_not_auto_route(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", now=T0, path=p)
        choice = _choose("sync", available=["llama3.1"], path=p)
        assert choice.backend == BACKEND_API_METERED
        assert "unknown" in choice.reason

    def test_low_score_admission_does_not_auto_route(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", score=0.6, now=T0, path=p)
        choice = _choose("sync", available=["llama3.1"], path=p)
        assert choice.backend == BACKEND_API_METERED
        assert "below_floor" in choice.reason

    def test_admission_is_task_class_scoped(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", score=0.8, now=T0, path=p)
        assert _choose("absorb", available=["llama3.1"], path=p).backend == BACKEND_API_METERED
        assert _choose("sync", available=["llama3.1"], path=p).backend == BACKEND_LOCAL

    def test_env_pref_breaks_tie_among_admitted(self, tmp_path, monkeypatch):
        p = tmp_path / "a.jsonl"
        record_admission("model-a", "absorb", score=0.9, now=T0, path=p)
        record_admission("model-b", "absorb", score=0.8, now=T0, path=p)
        monkeypatch.setenv("DEEPR_LOCAL_MODEL", "model-b")
        choice = _choose("absorb", available=["model-a", "model-b"], path=p)
        assert choice.model == "model-b"

    def test_env_pref_ignored_when_not_admitted(self, tmp_path, monkeypatch):
        p = tmp_path / "a.jsonl"
        record_admission("model-a", "absorb", score=0.8, now=T0, path=p)
        monkeypatch.setenv("DEEPR_LOCAL_MODEL", "not-admitted")
        choice = _choose("absorb", available=["model-a", "not-admitted"], path=p)
        # Falls back to the admitted+available one, not the env pref.
        assert choice.model == "model-a"

    def test_env_pref_ignored_when_it_fails_quality(self, tmp_path, monkeypatch):
        p = tmp_path / "a.jsonl"
        record_admission("model-a", "absorb", score=0.8, now=T0, path=p)
        record_admission("model-b", "absorb", score=0.6, now=T0, path=p)
        monkeypatch.setenv("DEEPR_LOCAL_MODEL", "model-b")
        choice = _choose("absorb", available=["model-a", "model-b"], path=p)
        assert choice.model == "model-a"
