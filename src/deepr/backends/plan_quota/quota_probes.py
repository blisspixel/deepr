"""Metadata-only plan-quota availability probes.

These probes collect quota metadata, not model answers. They must stay separate
from plan-quota execution so availability checks can run at $0 and without
touching provider generation paths.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.backends.capacity import CostModel
from deepr.backends.quota_ledger import QuotaWindowKind
from deepr.backends.quota_snapshot import QuotaSnapshot, QuotaWindowSnapshot

CODEX_QUOTA_BACKEND_ID = "codex"
CODEX_QUOTA_DISPLAY_NAME = "Codex"
CODEX_RECENT_ROLLOUT_LIMIT = 5


class QuotaProbeUnsupportedError(ValueError):
    """Raised when a live quota probe has not been implemented for a backend."""


def supported_quota_probe_backends() -> tuple[str, ...]:
    return (CODEX_QUOTA_BACKEND_ID,)


def collect_plan_quota_snapshot(
    backend_id: str,
    *,
    now: datetime | None = None,
    codex_sessions_dir: Path | None = None,
) -> QuotaSnapshot:
    """Collect a metadata-only quota snapshot for ``backend_id``."""
    if backend_id == CODEX_QUOTA_BACKEND_ID:
        return collect_codex_quota_snapshot(sessions_dir=codex_sessions_dir, now=now)
    raise QuotaProbeUnsupportedError(f"no live quota probe for {backend_id!r}")


def default_codex_sessions_dir(*, home: Path | None = None) -> Path:
    return (home or Path.home()) / ".codex" / "sessions"


def collect_codex_quota_snapshot(
    *,
    sessions_dir: Path | None = None,
    now: datetime | None = None,
    recent_file_limit: int = CODEX_RECENT_ROLLOUT_LIMIT,
) -> QuotaSnapshot:
    """Read the newest Codex session rate-limit snapshot from local logs.

    Codex writes a ``rate_limits`` object into rollout JSONL files. Reading that
    object is a metadata read only: no network, no auth, no model call.
    """
    stamp = now or datetime.now(UTC)
    root = sessions_dir or default_codex_sessions_dir()
    if not root.exists():
        return _codex_error_snapshot(f"no Codex sessions directory: {root}", stamp)

    try:
        rollouts = _recent_rollout_files(root, limit=recent_file_limit)
    except OSError as exc:
        return _codex_error_snapshot(str(exc), stamp)

    if not rollouts:
        return _codex_error_snapshot(f"no rollout files under {root}", stamp)

    for file in rollouts:
        rate_limits = _last_rate_limits(file)
        if rate_limits is None:
            continue
        return _codex_snapshot_from_rate_limits(rate_limits, stamp, source_file=file)

    return _codex_error_snapshot(f"no rate_limits found in {len(rollouts)} recent rollout files", stamp)


def _codex_error_snapshot(error: str, stamp: datetime) -> QuotaSnapshot:
    return QuotaSnapshot(
        backend_id=CODEX_QUOTA_BACKEND_ID,
        display_name=CODEX_QUOTA_DISPLAY_NAME,
        account_id="unknown",
        cost_model=CostModel.ROLLING_WINDOW,
        ok=False,
        error=error,
        as_of=stamp,
    )


def _recent_rollout_files(root: Path, *, limit: int) -> list[Path]:
    files = [p for p in root.rglob("rollout-*.jsonl") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def _last_rate_limits(path: Path) -> dict[str, Any] | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

    for line in reversed(lines):
        if '"rate_limits"' not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        found = _find_key(obj, "rate_limits")
        if isinstance(found, dict):
            return found
    return None


def _find_key(value: object, key: str) -> object | None:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find_key(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_key(child, key)
            if found is not None:
                return found
    return None


def _codex_snapshot_from_rate_limits(
    rate_limits: dict[str, Any], stamp: datetime, *, source_file: Path
) -> QuotaSnapshot:
    plan = _string_or_none(rate_limits.get("plan_type"))
    windows = tuple(_codex_windows(rate_limits))
    return QuotaSnapshot(
        backend_id=CODEX_QUOTA_BACKEND_ID,
        display_name=CODEX_QUOTA_DISPLAY_NAME,
        account_id=plan or "default",
        plan=plan,
        cost_model=CostModel.ROLLING_WINDOW,
        ok=True,
        windows=windows,
        as_of=stamp,
        metadata={"source": "codex_rollout", "source_file": str(source_file)},
    )


def _codex_windows(rate_limits: dict[str, Any]) -> Iterable[QuotaWindowSnapshot]:
    specs = (
        ("primary", "5h", QuotaWindowKind.ROLLING_5H),
        ("secondary", "weekly", QuotaWindowKind.WEEKLY),
    )
    for key, fallback_label, kind in specs:
        window = rate_limits.get(key)
        if not isinstance(window, dict):
            continue
        yield QuotaWindowSnapshot(
            label=_codex_label(window.get("window_minutes"), fallback_label),
            window_kind=kind,
            used_fraction=_percent_to_fraction(window.get("used_percent")),
            reset_at=_epoch_to_datetime(window.get("resets_at")),
            unit_name="plan_request",
            metadata={"source_key": key},
        )


def _codex_label(minutes: object, fallback: str) -> str:
    if not isinstance(minutes, int | float):
        return fallback
    minute_count = int(minutes)
    if minute_count == 300:
        return "5h"
    if minute_count == 10080:
        return "weekly"
    if minute_count > 0 and minute_count % 1440 == 0:
        return f"{minute_count // 1440}d"
    if minute_count > 0 and minute_count % 60 == 0:
        return f"{minute_count // 60}h"
    return f"{minute_count}m" if minute_count > 0 else fallback


def _percent_to_fraction(value: object) -> float | None:
    if not isinstance(value, int | float):
        return None
    return float(value) / 100.0


def _epoch_to_datetime(value: object) -> datetime | None:
    if not isinstance(value, int | float):
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
