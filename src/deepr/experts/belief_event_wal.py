"""Fail-closed consistency checks for the belief event log.

``events.jsonl`` is fsynced before ``beliefs.json``. A crash between those
writes leaves durable events that ``_load`` would otherwise ignore. Events
do not always carry a full ``Belief`` snapshot, so this module refuses writes
when the log is ahead of or unreadable relative to the snapshot instead of
replaying a partial graph.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def event_log_conflicts_with_snapshot(
    events_path: Path,
    *,
    snapshot_exists: bool,
    latest_change: datetime | None,
) -> bool:
    """Return True when the event log must not be ignored.

    True means: malformed log, events without a snapshot, or the latest event
    timestamp is strictly after the snapshot's latest change record.
    """
    if not events_path.exists():
        return False
    last_ts: datetime | None = None
    try:
        with open(events_path, encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if not isinstance(data, dict):
                    return True
                if "belief_id" not in data or "change_type" not in data:
                    return True
                timestamp_raw = data.get("timestamp")
                if not isinstance(timestamp_raw, str) or not timestamp_raw:
                    return True
                last_ts = datetime.fromisoformat(timestamp_raw)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return True
    if last_ts is None:
        return False
    if not snapshot_exists or latest_change is None:
        return True
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=UTC)
    if latest_change.tzinfo is None:
        latest_change = latest_change.replace(tzinfo=UTC)
    return last_ts > latest_change
