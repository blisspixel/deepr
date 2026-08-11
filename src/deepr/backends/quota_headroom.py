"""How much of each plan is left, read without spending any of it.

Deepr's own availability check dispatches a real request to each backend and
reads the reply. That works, and it spends quota to discover whether there is
quota, which is the wrong trade when the answer is "almost none".

quotabot reads provider metadata and makes no model calls, so the same
question costs nothing. When it is installed Deepr uses it to order and gate
dispatch; when it is not, everything degrades to plain round-robin, because a
missing optional tool must not become a hard dependency of the $0 path.

Ordering by headroom rather than by speed is deliberate. Round-robin across
four plans is fair and blind: it sends work to a plan at 95% of its five-hour
window as readily as to one at 4% of its week, which exhausts the tight one
and then fails over. Headroom ordering finishes the same run without touching
the plan that was about to cap.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

_CACHE_TTL_S = 120.0
"""Long enough that a fan-out reads it once, short enough to notice a cap.

Re-reading per dispatch would turn a free check into a per-request subprocess
launch, which is its own kind of spam even when no tokens are spent."""

_EXHAUSTED_AT = 97.0
"""Percent used above which a plan is skipped rather than merely deprioritized."""

_cache: tuple[float, dict[str, PlanHeadroom]] | None = None


@dataclass
class PlanHeadroom:
    """What is left on one plan, and when the tightest window resets."""

    provider: str
    ok: bool = True
    used_percent: float = 0.0
    """The tightest window's usage. A five-hour cap binds before a weekly one."""
    window_label: str = ""
    resets_in_s: float = 0.0
    plan: str = ""
    windows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def headroom(self) -> float:
        """Fraction of the tightest window still available, 0.0 to 1.0."""
        return max(0.0, min(1.0, (100.0 - self.used_percent) / 100.0))

    @property
    def is_exhausted(self) -> bool:
        return not self.ok or self.used_percent >= _EXHAUSTED_AT

    def describe(self) -> str:
        if not self.ok:
            return f"{self.provider}: unavailable"
        if not self.window_label:
            return f"{self.provider}: no window reported"
        minutes = int(self.resets_in_s / 60)
        return f"{self.provider}: {self.used_percent:.0f}% of {self.window_label} used, resets in {minutes}m"


def _tightest_window(windows: list[dict[str, Any]], now: float) -> tuple[float, str, float]:
    """The window closest to its cap, since that is the one that will bind."""
    best = (0.0, "", 0.0)
    for window in windows or []:
        try:
            used = float(window.get("used_percent", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if used >= best[0]:
            resets = float(window.get("resets_at", now) or now) - now
            best = (used, str(window.get("label", "")), max(0.0, resets))
    return best


def parse_snapshot(payload: dict[str, Any], *, now: float | None = None) -> dict[str, PlanHeadroom]:
    """Turn a quotabot snapshot into per-provider headroom."""
    moment = now if now is not None else time.time()
    out: dict[str, PlanHeadroom] = {}
    for entry in payload.get("providers") or []:
        provider = str(entry.get("provider", "")).strip().lower()
        if not provider:
            continue
        windows = entry.get("windows") or []
        used, label, resets = _tightest_window(windows, moment)
        out[provider] = PlanHeadroom(
            provider=provider,
            ok=bool(entry.get("ok", True)),
            used_percent=used,
            window_label=label,
            resets_in_s=resets,
            plan=str(entry.get("plan") or ""),
            windows=windows,
        )
    return out


def read_headroom(*, force: bool = False, timeout_s: float = 25.0) -> dict[str, PlanHeadroom]:
    """Current headroom per provider, or empty when quotabot is unavailable.

    Never raises. An absent or broken quota tool means Deepr does not know how
    much is left, which is the state it was already in, not a reason to stop.
    """
    global _cache
    now = time.time()
    if not force and _cache is not None and now - _cache[0] < _CACHE_TTL_S:
        return _cache[1]

    # Fixed argv with no interpolation, and the executable is resolved rather
    # than left to PATH order at spawn time. Nothing from a corpus, a prompt or
    # a config reaches this command line.
    executable = shutil.which("quotabot")
    if not executable:
        return {}
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, resolved path, no shell
            [executable, "--json"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}

    if completed.returncode != 0 or not completed.stdout.strip():
        return {}
    try:
        parsed = parse_snapshot(json.loads(completed.stdout), now=now)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}

    _cache = (now, parsed)
    return parsed


def order_by_headroom(names: list[str] | tuple[str, ...], headroom: dict[str, PlanHeadroom]) -> list[str]:
    """Most headroom first. Unknown plans keep their given order, in the middle.

    A provider quotabot does not report is not assumed empty and not assumed
    full; it sorts as if half used, so an unmeasured plan is neither preferred
    nor starved.
    """
    ordered = list(names)
    if not headroom:
        return ordered

    def key(name: str) -> tuple[float, int]:
        plan = headroom.get(name.lower())
        return (-(plan.headroom if plan else 0.5), ordered.index(name))

    return sorted(ordered, key=key)


def exhausted(names: list[str] | tuple[str, ...], headroom: dict[str, PlanHeadroom]) -> list[str]:
    """Plans at or past their cap, so a caller can say what it skipped."""
    return [n for n in names if (plan := headroom.get(n.lower())) is not None and plan.is_exhausted]
