"""Tests for deepr.backends.admission - eval-gated local admission ($0, no I/O).

Every test passes an explicit ledger ``path`` and ``now`` so it is hermetic:
no real ledger, no wall-clock, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deepr.backends.admission import (
    DEFAULT_ADMISSION_DAYS,
    Admission,
    active_admission,
    default_capacity_data_dir,
    is_admitted,
    list_active,
    load_events,
    record_admission,
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
