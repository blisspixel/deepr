"""Concurrent first use of the durable research reservation store (#296)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest
from filelock import FileLock

from deepr.experts.research_reservation_store import (
    ResearchReservationStore,
    ResearchReservationStoreError,
)


def test_concurrent_first_use_initializes_without_spurious_refusal(tmp_path: Path) -> None:
    failures: list[BaseException] = []
    rounds = 40
    workers = 4
    for index in range(rounds):
        path = tmp_path / f"round-{index}" / "research_reservations.db"
        barrier = threading.Barrier(workers)

        def initialize(target: Path = path, gate: threading.Barrier = barrier) -> None:
            gate.wait()
            try:
                ResearchReservationStore(target)
            except ResearchReservationStoreError as error:
                failures.append(error)

        threads = [threading.Thread(target=initialize) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert failures == []


def test_initialization_still_refuses_when_lock_cannot_be_acquired(tmp_path: Path) -> None:
    path = tmp_path / "research_reservations.db"
    holder = FileLock(str(path.with_name(f"{path.name}.init.lock")), thread_local=False)
    with holder, pytest.raises(ResearchReservationStoreError, match="initialization failed"):
        ResearchReservationStore(path, lock_timeout_seconds=0)


def test_initialized_store_uses_wal_and_current_schema(tmp_path: Path) -> None:
    path = tmp_path / "research_reservations.db"
    ResearchReservationStore(path)
    ResearchReservationStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        columns = {row[1] for row in connection.execute("PRAGMA table_info(research_cost_reservations)")}
    assert {"dispatch_binding_id", "request_envelope_sha256", "spend_wallet_id"} <= columns
