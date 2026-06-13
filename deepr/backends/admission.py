"""Eval-gated admission for local backends (capacity waterfall, v2.16).

The waterfall router prefers owned capacity (a local Ollama model at $0) over a
metered API - but only when that local model has been shown good enough for the
task. "It's free" must never override "it's good enough" (docs/design/
capacity-waterfall.md). An admission is the operator's explicit, dated record
that a given local model is acceptable for a given task class; the automatic
path uses local only while a live admission exists. ``--local`` stays a manual
override that needs no admission (the operator asked for it directly).

Admissions are machine-local, like the cost ledger: which local models exist
and how good they are depends on the hardware, so this never lives in the
portable experts dir (ADR 0004). Append-only JSONL, env-overridable via
``DEEPR_CAPACITY_DATA_DIR`` so tests isolate themselves from the real ledger.

Admissions expire (default 90 days): models and their quantizations change, so
an old admission must lapse and be re-earned rather than silently persist.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Task classes the maintenance commands admit against. Free-form strings are
# allowed, but these are the canonical ones so admit/check sites agree.
TASK_CLASS_SYNC = "sync"
TASK_CLASS_ABSORB = "absorb"

DEFAULT_ADMISSION_DAYS = 90


def default_capacity_data_dir() -> Path:
    """Resolve the machine-local capacity-data directory.

    Honors ``DEEPR_CAPACITY_DATA_DIR`` so deployments can relocate it and - as
    with the cost ledger - so the test suite isolates itself instead of writing
    admissions into the user's real ledger. Default is CWD-relative.
    """
    base = os.environ.get("DEEPR_CAPACITY_DATA_DIR", "").strip()
    return Path(base) if base else Path("data/capacity")


def admissions_path(path: Path | None = None) -> Path:
    return path or default_capacity_data_dir() / "admissions.jsonl"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Admission:
    """One admission-ledger event for a (model, task_class) pair.

    ``event`` is ``"admit"`` or ``"revoke"``; the most recent event for a pair
    decides whether it is currently admitted. ``expires_at`` is None for revoke.
    """

    model: str
    task_class: str
    recorded_at: datetime
    expires_at: datetime | None
    event: str = "admit"
    score: float | None = None
    note: str = ""

    def is_active(self, *, now: datetime) -> bool:
        """True if this event grants a live admission as of ``now``."""
        if self.event != "admit":
            return False
        return self.expires_at is None or now < self.expires_at

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "task_class": self.task_class,
            "recorded_at": self.recorded_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "event": self.event,
            "score": self.score,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Admission:
        exp = d.get("expires_at")
        return cls(
            model=str(d["model"]),
            task_class=str(d["task_class"]),
            recorded_at=datetime.fromisoformat(d["recorded_at"]),
            expires_at=datetime.fromisoformat(exp) if exp else None,
            event=str(d.get("event", "admit")),
            score=d.get("score"),
            note=str(d.get("note", "")),
        )


def load_events(path: Path | None = None) -> list[Admission]:
    """Read all admission events in recorded order. Missing file -> empty."""
    p = admissions_path(path)
    if not p.exists():
        return []
    events: list[Admission] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(Admission.from_dict(json.loads(line)))
        except (json.JSONDecodeError, KeyError, ValueError):
            # A corrupt line must not break routing; skip it.
            continue
    return events


def _append(event: Admission, path: Path | None = None) -> None:
    p = admissions_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event.to_dict()) + "\n")


def record_admission(
    model: str,
    task_class: str,
    *,
    days: int = DEFAULT_ADMISSION_DAYS,
    score: float | None = None,
    note: str = "",
    now: datetime | None = None,
    path: Path | None = None,
) -> Admission:
    """Admit ``model`` for ``task_class`` for ``days`` (operator acceptance)."""
    stamp = now or _utc_now()
    event = Admission(
        model=model,
        task_class=task_class,
        recorded_at=stamp,
        expires_at=stamp + timedelta(days=days),
        event="admit",
        score=score,
        note=note,
    )
    _append(event, path)
    return event


def revoke_admission(
    model: str, task_class: str, *, now: datetime | None = None, path: Path | None = None
) -> Admission:
    """Revoke any admission for ``model`` on ``task_class`` (takes effect now)."""
    event = Admission(
        model=model,
        task_class=task_class,
        recorded_at=now or _utc_now(),
        expires_at=None,
        event="revoke",
    )
    _append(event, path)
    return event


def _latest_per_pair(events: Iterable[Admission]) -> dict[tuple[str, str], Admission]:
    """The most recent event for each (model, task_class), by recorded_at."""
    latest: dict[tuple[str, str], Admission] = {}
    for e in events:
        key = (e.model, e.task_class)
        prev = latest.get(key)
        if prev is None or e.recorded_at >= prev.recorded_at:
            latest[key] = e
    return latest


def active_admission(
    model: str, task_class: str, *, now: datetime | None = None, path: Path | None = None
) -> Admission | None:
    """The live admission for (model, task_class), or None if none/expired/revoked."""
    stamp = now or _utc_now()
    latest = _latest_per_pair(load_events(path))
    event = latest.get((model, task_class))
    if event is None or not event.is_active(now=stamp):
        return None
    return event


def is_admitted(model: str, task_class: str, *, now: datetime | None = None, path: Path | None = None) -> bool:
    return active_admission(model, task_class, now=now, path=path) is not None


def list_active(*, now: datetime | None = None, path: Path | None = None) -> list[Admission]:
    """All currently-live admissions, sorted by model then task class."""
    stamp = now or _utc_now()
    live = [e for e in _latest_per_pair(load_events(path)).values() if e.is_active(now=stamp)]
    return sorted(live, key=lambda a: (a.model, a.task_class))
