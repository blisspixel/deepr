"""Tests for deepr.backends.waterfall - backend selection ($0, no I/O).

``local_model_fn`` and the admissions ``path``/``now`` are injected, so these
exercise the full waterfall logic with no Ollama and no real ledger.
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


def _choose(task_class, *, model, path, now=T0):
    return choose_maintenance_backend(task_class, now=now, local_model_fn=lambda: model, admissions_path=path)


class TestChoose:
    def test_no_local_model_falls_to_metered(self, tmp_path):
        choice = _choose("sync", model=None, path=tmp_path / "a.jsonl")
        assert choice.backend == BACKEND_API_METERED
        assert not choice.is_local
        assert "no local model" in choice.reason

    def test_local_present_but_unadmitted_falls_to_metered(self, tmp_path):
        choice = _choose("sync", model="llama3.1", path=tmp_path / "a.jsonl")
        assert choice.backend == BACKEND_API_METERED
        assert "not admitted" in choice.reason
        # The reason coaches the exact admit command.
        assert "deepr capacity admit llama3.1" in choice.reason

    def test_admitted_local_is_chosen(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", now=T0, path=p)
        choice = _choose("sync", model="llama3.1", path=p)
        assert choice.backend == BACKEND_LOCAL
        assert choice.is_local
        assert choice.model == "llama3.1"
        assert "owned capacity before metered API" in choice.reason

    def test_admission_is_task_class_scoped(self, tmp_path):
        p = tmp_path / "a.jsonl"
        record_admission("llama3.1", "sync", now=T0, path=p)
        # Admitted for sync, not absorb.
        assert _choose("absorb", model="llama3.1", path=p).backend == BACKEND_API_METERED
        assert _choose("sync", model="llama3.1", path=p).backend == BACKEND_LOCAL
