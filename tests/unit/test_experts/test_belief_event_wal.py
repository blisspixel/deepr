"""Fail-closed belief event log vs snapshot checks."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deepr.experts.belief_event_wal import event_log_conflicts_with_snapshot
from deepr.experts.beliefs import Belief, BeliefStore, BeliefStoreError


def _event_line(*, timestamp: datetime, claim: str = "ahead") -> str:
    return json.dumps(
        {
            "belief_id": "b1",
            "change_type": "created",
            "new_claim": claim,
            "new_confidence": 0.9,
            "timestamp": timestamp.isoformat(),
        }
    )


def test_missing_log_does_not_conflict(tmp_path: Path) -> None:
    assert (
        event_log_conflicts_with_snapshot(tmp_path / "events.jsonl", snapshot_exists=True, latest_change=None) is False
    )


def test_events_without_snapshot_conflict(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(_event_line(timestamp=datetime.now(UTC)) + "\n", encoding="utf-8")
    assert event_log_conflicts_with_snapshot(path, snapshot_exists=False, latest_change=None) is True


def test_malformed_event_line_conflicts(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("{not-json\n", encoding="utf-8")
    assert (
        event_log_conflicts_with_snapshot(path, snapshot_exists=True, latest_change=datetime.now(UTC)) is True
    )


def test_event_ahead_of_snapshot_conflicts(tmp_path: Path) -> None:
    older = datetime.now(UTC)
    newer = older + timedelta(seconds=1)
    path = tmp_path / "events.jsonl"
    path.write_text(_event_line(timestamp=newer) + "\n", encoding="utf-8")
    assert event_log_conflicts_with_snapshot(path, snapshot_exists=True, latest_change=older) is True
    assert event_log_conflicts_with_snapshot(path, snapshot_exists=True, latest_change=newer) is False


def test_store_refuses_writes_when_events_exist_without_snapshot(tmp_path: Path) -> None:
    storage_dir = tmp_path / "beliefs"
    storage_dir.mkdir()
    (storage_dir / "events.jsonl").write_text(_event_line(timestamp=datetime.now(UTC)) + "\n", encoding="utf-8")

    store = BeliefStore(expert_name="test", storage_dir=storage_dir)
    assert store._unreadable is True
    with pytest.raises(BeliefStoreError, match="unreadable"):
        store.add_belief(Belief(claim="should not write", confidence=0.9, domain="d"))
    assert not (storage_dir / "beliefs.json").exists()


def test_store_refuses_writes_when_event_log_is_ahead(tmp_path: Path) -> None:
    store = BeliefStore(expert_name="test", storage_dir=tmp_path / "beliefs")
    store.add_belief(Belief(claim="original", confidence=0.9, domain="d"))
    latest = store.changes[-1].timestamp
    ahead = latest + timedelta(seconds=5)
    with store.events_path.open("a", encoding="utf-8") as handle:
        handle.write(_event_line(timestamp=ahead, claim="not in snapshot") + "\n")

    reopened = BeliefStore(expert_name="test", storage_dir=tmp_path / "beliefs")
    assert reopened._unreadable is True
    original = store.storage_path.read_text(encoding="utf-8")
    with pytest.raises(BeliefStoreError, match="unreadable"):
        reopened.add_belief(Belief(claim="another", confidence=0.8, domain="d"))
    assert reopened.storage_path.read_text(encoding="utf-8") == original
