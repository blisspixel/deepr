"""Metadata-only plan-quota availability probes.

These probes collect quota metadata, not model answers. They must stay separate
from plan-quota execution so availability checks can run at $0 and without
touching provider generation paths.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from deepr.backends.capacity import CostModel
from deepr.backends.quota_ledger import QuotaWindowKind
from deepr.backends.quota_snapshot import QuotaSnapshot, QuotaWindowSnapshot

CLAUDE_QUOTA_BACKEND_ID = "claude"
CLAUDE_QUOTA_DISPLAY_NAME = "Claude Code"
CLAUDE_USAGE_ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_USAGE_TIMEOUT_SECONDS = 10.0
CODEX_QUOTA_BACKEND_ID = "codex"
CODEX_QUOTA_DISPLAY_NAME = "Codex"
CODEX_RECENT_ROLLOUT_LIMIT = 5


class QuotaProbeUnsupportedError(ValueError):
    """Raised when a live quota probe has not been implemented for a backend."""


def supported_quota_probe_backends() -> tuple[str, ...]:
    return (CODEX_QUOTA_BACKEND_ID, CLAUDE_QUOTA_BACKEND_ID)


def collect_plan_quota_snapshot(
    backend_id: str,
    *,
    now: datetime | None = None,
    codex_sessions_dir: Path | None = None,
    claude_config_dir: Path | None = None,
    claude_http_get: Any | None = None,
) -> QuotaSnapshot:
    """Collect a metadata-only quota snapshot for ``backend_id``."""
    if backend_id == CODEX_QUOTA_BACKEND_ID:
        return collect_codex_quota_snapshot(sessions_dir=codex_sessions_dir, now=now)
    if backend_id == CLAUDE_QUOTA_BACKEND_ID:
        return collect_claude_quota_snapshot(config_dir=claude_config_dir, now=now, http_get=claude_http_get)
    raise QuotaProbeUnsupportedError(f"no live quota probe for {backend_id!r}")


def default_codex_sessions_dir(*, home: Path | None = None) -> Path:
    return (home or Path.home()) / ".codex" / "sessions"


def default_claude_credentials_path(
    *,
    config_dir: Path | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the Claude Code OAuth credentials file path for this machine."""
    if config_dir is not None:
        return config_dir / ".credentials.json"
    env_map = os.environ if env is None else env
    configured = env_map.get("CLAUDE_CONFIG_DIR")
    if configured and configured.strip():
        return Path(configured).expanduser() / ".credentials.json"
    return (home or Path.home()) / ".claude" / ".credentials.json"


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


def collect_claude_quota_snapshot(
    *,
    config_dir: Path | None = None,
    now: datetime | None = None,
    http_get: Any | None = None,
    timeout_seconds: float = CLAUDE_USAGE_TIMEOUT_SECONDS,
) -> QuotaSnapshot:
    """Read Claude Code usage windows from the read-only OAuth usage endpoint.

    This is an explicit metadata refresh, not a model call. It reuses the
    Claude Code OAuth token on the current machine only long enough to call the
    same usage endpoint Claude Code uses, then records normalized usage windows.
    The token is never returned, logged, or written to Deepr state.
    """
    stamp = now or datetime.now(UTC)
    credentials_path = default_claude_credentials_path(config_dir=config_dir)
    oauth = _read_claude_oauth(credentials_path)
    if not oauth["ok"]:
        return _claude_error_snapshot(str(oauth["error"]), stamp)

    token = str(oauth["access_token"])
    plan = _string_or_none(oauth.get("plan"))
    getter = http_get or httpx.get
    try:
        response = getter(
            CLAUDE_USAGE_ENDPOINT,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
                "anthropic-version": "2023-06-01",
            },
            timeout=timeout_seconds,
        )
    except (httpx.HTTPError, TimeoutError, OSError) as exc:
        return _claude_error_snapshot(f"usage endpoint request failed: {exc}", stamp, plan=plan)

    status_code = int(getattr(response, "status_code", 0))
    if status_code == 401:
        return _claude_error_snapshot(
            "Claude Code OAuth token expired or unauthorized; re-run claude login", stamp, plan=plan
        )
    if status_code == 429:
        retry_after = _response_header(response, "retry-after")
        detail = "Claude usage endpoint rate-limited"
        if retry_after:
            detail = f"{detail}; retry after {retry_after}s"
        return _claude_error_snapshot(detail, stamp, plan=plan, metadata={"retry_after": retry_after})
    if status_code != 200:
        return _claude_error_snapshot(f"Claude usage endpoint returned HTTP {status_code}", stamp, plan=plan)

    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return _claude_error_snapshot(f"Claude usage endpoint returned invalid JSON: {exc}", stamp, plan=plan)
    if not isinstance(data, dict):
        return _claude_error_snapshot("Claude usage endpoint returned a non-object payload", stamp, plan=plan)

    return _claude_snapshot_from_usage(data, stamp, plan=plan)


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


def _claude_error_snapshot(
    error: str,
    stamp: datetime,
    *,
    plan: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> QuotaSnapshot:
    return QuotaSnapshot(
        backend_id=CLAUDE_QUOTA_BACKEND_ID,
        display_name=CLAUDE_QUOTA_DISPLAY_NAME,
        account_id=plan or "unknown",
        plan=plan,
        cost_model=CostModel.ROLLING_WINDOW,
        ok=False,
        error=error,
        as_of=stamp,
        metadata=metadata or {},
    )


def _read_claude_oauth(credentials_path: Path) -> dict[str, object]:
    if not credentials_path.exists():
        return {"ok": False, "error": f"no Claude Code credentials file: {credentials_path}"}
    try:
        raw = json.loads(credentials_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"cannot read Claude Code credentials: {exc}"}
    if not isinstance(raw, dict):
        return {"ok": False, "error": "Claude Code credentials file is not a JSON object"}
    oauth = raw.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return {"ok": False, "error": "Claude Code credentials file has no claudeAiOauth object"}
    token = _string_or_none(oauth.get("accessToken"))
    if token is None:
        return {"ok": False, "error": "Claude Code credentials file has no OAuth access token"}
    return {
        "ok": True,
        "access_token": token,
        "plan": _string_or_none(oauth.get("subscriptionType")),
    }


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


def _claude_snapshot_from_usage(data: dict[str, Any], stamp: datetime, *, plan: str | None) -> QuotaSnapshot:
    windows = tuple(_claude_windows(data))
    response_plan = _string_or_none(data.get("subscription_type") or data.get("subscriptionType"))
    effective_plan = response_plan or plan
    return QuotaSnapshot(
        backend_id=CLAUDE_QUOTA_BACKEND_ID,
        display_name=CLAUDE_QUOTA_DISPLAY_NAME,
        account_id=effective_plan or "default",
        plan=effective_plan,
        cost_model=CostModel.ROLLING_WINDOW,
        ok=True,
        windows=windows,
        as_of=stamp,
        metadata={"source": "claude_oauth_usage"},
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


def _claude_windows(data: dict[str, Any]) -> Iterable[QuotaWindowSnapshot]:
    specs = (
        ("five_hour", "5h", QuotaWindowKind.ROLLING_5H),
        ("seven_day", "weekly", QuotaWindowKind.WEEKLY),
        ("seven_day_opus", "opus", QuotaWindowKind.WEEKLY),
    )
    for key, label, kind in specs:
        block = data.get(key)
        if not isinstance(block, dict):
            continue
        used_fraction = _percent_to_fraction(block.get("utilization"))
        if used_fraction is None:
            continue
        yield QuotaWindowSnapshot(
            label=label,
            window_kind=kind,
            used_fraction=used_fraction,
            reset_at=_iso_to_datetime(block.get("resets_at")),
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


def _iso_to_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _response_header(response: object, name: str) -> str | None:
    headers = getattr(response, "headers", {})
    if not hasattr(headers, "get"):
        return None
    value = headers.get(name) or headers.get(name.title())
    return _string_or_none(value)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
