"""Tests for deepr.backends.admission - eval-gated local admission ($0, no I/O).

Every test passes an explicit ledger ``path`` and ``now`` so it is hermetic:
no real ledger, no wall-clock, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deepr.backends.admission import (
    DEFAULT_ADMISSION_DAYS,
    Admission,
    AdmissionEvidenceError,
    active_admission,
    default_capacity_data_dir,
    is_admitted,
    latest_local_eval_artifact,
    list_active,
    load_events,
    load_local_eval_evidence,
    record_admission,
    resolve_local_eval_artifact,
    revoke_admission,
)

T0 = datetime(2026, 6, 13, tzinfo=UTC)


class TestRecordAndCheck:
    def test_admit_then_admitted(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        record_admission("llama3.1", "sync", now=T0, path=p)
        assert is_admitted("llama3.1", "sync", now=T0, path=p)

    def test_unadmitted_pair_is_not_admitted(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        record_admission("llama3.1", "sync", now=T0, path=p)
        # Different task class and different model are independent.
        assert not is_admitted("llama3.1", "absorb", now=T0, path=p)
        assert not is_admitted("qwen2.5", "sync", now=T0, path=p)

    def test_default_lifetime(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        adm = record_admission("llama3.1", "sync", now=T0, path=p)
        assert adm.expires_at == T0 + timedelta(days=DEFAULT_ADMISSION_DAYS)

    def test_missing_file_is_empty(self, tmp_path):
        p = tmp_path / "nope.jsonl"
        assert load_events(p) == []
        assert not is_admitted("m", "sync", now=T0, path=p)


class TestExpiry:
    def test_expired_admission_is_inactive(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        record_admission("llama3.1", "sync", days=30, now=T0, path=p)
        assert is_admitted("llama3.1", "sync", now=T0 + timedelta(days=29), path=p)
        assert not is_admitted("llama3.1", "sync", now=T0 + timedelta(days=31), path=p)

    def test_boundary_is_exclusive_at_expiry(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        adm = record_admission("m", "sync", days=10, now=T0, path=p)
        assert not is_admitted("m", "sync", now=adm.expires_at, path=p)


class TestRevoke:
    def test_revoke_overrides_earlier_admit(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        record_admission("m", "sync", now=T0, path=p)
        revoke_admission("m", "sync", now=T0 + timedelta(days=1), path=p)
        assert not is_admitted("m", "sync", now=T0 + timedelta(days=2), path=p)

    def test_readmit_after_revoke(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        record_admission("m", "sync", now=T0, path=p)
        revoke_admission("m", "sync", now=T0 + timedelta(days=1), path=p)
        record_admission("m", "sync", now=T0 + timedelta(days=2), path=p)
        assert is_admitted("m", "sync", now=T0 + timedelta(days=3), path=p)

    def test_latest_event_wins_regardless_of_append_order(self, tmp_path):
        # Append a revoke with an earlier recorded_at after a later admit; the
        # admit (more recent recorded_at) must still win.
        p = tmp_path / "adm.jsonl"
        record_admission("m", "sync", now=T0 + timedelta(days=5), path=p)
        revoke_admission("m", "sync", now=T0, path=p)  # older timestamp
        assert is_admitted("m", "sync", now=T0 + timedelta(days=6), path=p)


class TestListActive:
    def test_lists_only_live_sorted(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        record_admission("qwen2.5", "absorb", now=T0, path=p)
        record_admission("llama3.1", "sync", now=T0, path=p)
        record_admission("old", "sync", days=1, now=T0, path=p)  # will be expired
        active = list_active(now=T0 + timedelta(days=2), path=p)
        names = [(a.model, a.task_class) for a in active]
        assert names == [("llama3.1", "sync"), ("qwen2.5", "absorb")]


class TestPersistenceAndShape:
    def test_round_trips_score_and_note(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        record_admission("m", "sync", score=0.74, note="reviewed dry-run", now=T0, path=p)
        adm = active_admission("m", "sync", now=T0, path=p)
        assert adm is not None and adm.score == 0.74 and adm.note == "reviewed dry-run"

    def test_corrupt_line_skipped_not_fatal(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        record_admission("m", "sync", now=T0, path=p)
        with p.open("a", encoding="utf-8") as f:
            f.write("{ not json\n")
        # Still readable; the good event survives.
        assert is_admitted("m", "sync", now=T0, path=p)

    def test_admission_to_from_dict(self):
        a = Admission("m", "sync", recorded_at=T0, expires_at=T0 + timedelta(days=90))
        assert Admission.from_dict(a.to_dict()) == a


class TestDataDir:
    def test_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path / "cap"))
        assert default_capacity_data_dir() == tmp_path / "cap"

    def test_default_is_machine_local(self, monkeypatch):
        monkeypatch.delenv("DEEPR_CAPACITY_DATA_DIR", raising=False)
        assert default_capacity_data_dir().as_posix().endswith("data/capacity")


def _artifact(
    tmp_path,
    *,
    winner="good-local",
    cost=0.0,
    score=0.82,
    error="",
    comparison_model="good-local",
    comparison_cost=0.0,
):
    import json

    path = tmp_path / "local_compare.json"
    path.write_text(
        json.dumps(
            {
                "methodology_version": "1.0",
                "generated_at": "2026-06-18T00:00:00+00:00",
                "prompt_set": "agentic-loops",
                "judge_model": "judge-local",
                "winner": winner,
                "cost": cost,
                "comparisons": [
                    {
                        "model": comparison_model,
                        "average_score": score,
                        "average_latency_ms": 12,
                        "cost": comparison_cost,
                        "prompt_results": [
                            {
                                "prompt_id": "p1",
                                "task_class": "agentic_loop",
                                "answer": "bounded answer",
                                "latency_ms": 12,
                                "verdict": {"score": score, "reason": "ok", "raw": "{}"},
                                "error": error,
                            }
                        ],
                    },
                    {
                        "model": "weak-local",
                        "average_score": 0.2,
                        "average_latency_ms": 10,
                        "cost": 0.0,
                        "prompt_results": [
                            {
                                "prompt_id": "p1",
                                "task_class": "agentic_loop",
                                "answer": "weak answer",
                                "latency_ms": 10,
                                "verdict": {"score": 0.2, "reason": "weak", "raw": "{}"},
                                "error": "",
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


class TestLocalEvalEvidence:
    def test_loads_winner_from_saved_local_eval_artifact(self, tmp_path):
        path = _artifact(tmp_path)

        evidence = load_local_eval_evidence(path, min_score=0.7)

        assert evidence.model == "good-local"
        assert evidence.score == 0.82
        assert evidence.prompt_count == 1
        assert evidence.task_classes == ("agentic_loop",)
        assert "score=0.820" in evidence.note()

    def test_loads_explicit_model_from_saved_local_eval_artifact(self, tmp_path):
        path = _artifact(tmp_path)

        evidence = load_local_eval_evidence(path, model="weak-local", min_score=0.1)

        assert evidence.model == "weak-local"
        assert evidence.score == 0.2

    def test_rejects_missing_model(self, tmp_path):
        path = _artifact(tmp_path)

        with pytest.raises(AdmissionEvidenceError, match="was not found"):
            load_local_eval_evidence(path, model="missing")

    def test_rejects_low_score(self, tmp_path):
        path = _artifact(tmp_path, score=0.5)

        with pytest.raises(AdmissionEvidenceError, match="below required minimum"):
            load_local_eval_evidence(path, min_score=0.7)

    def test_rejects_nonzero_cost(self, tmp_path):
        path = _artifact(tmp_path, cost=0.01)

        with pytest.raises(AdmissionEvidenceError, match="zero-cost"):
            load_local_eval_evidence(path)

    def test_rejects_nonzero_comparison_cost(self, tmp_path):
        path = _artifact(tmp_path, comparison_cost=0.01)

        with pytest.raises(AdmissionEvidenceError, match="zero-cost local model comparisons"):
            load_local_eval_evidence(path)

    def test_rejects_prompt_errors(self, tmp_path):
        path = _artifact(tmp_path, error="candidate failed")

        with pytest.raises(AdmissionEvidenceError, match="failed prompt"):
            load_local_eval_evidence(path)

    def test_resolves_latest_local_eval_artifact(self, tmp_path):
        bench = tmp_path / "benchmarks"
        bench.mkdir()
        old = _artifact(bench, comparison_model="old-local")
        old.rename(bench / "local_compare_20260618_120000.json")
        new = _artifact(bench, comparison_model="new-local")
        latest = bench / "local_compare_20260618_130000.json"
        new.rename(latest)

        assert latest_local_eval_artifact(bench) == latest
        assert resolve_local_eval_artifact("latest", benchmarks_dir=bench) == latest
