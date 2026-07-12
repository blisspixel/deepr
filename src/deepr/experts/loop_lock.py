"""Non-blocking per-(expert, verb) overlap guard and startup jitter.

State-changing expert verbs, including scheduled maintenance and explicit
absorption, can overlap across processes. Two hazards follow:

- *Overlap.* A cron firing and a manual run, or two overlapping cron firings,
  can execute the same verb on the same expert at once and race on its on-disk
  state (subscriptions, belief store, source packs). The second run should not
  fight the first; it should skip and exit cleanly.
- *Thundering herd.* A whole roster on one cadence can fire simultaneously and
  hammer a rate-limited plan-quota CLI. Spreading the starts avoids the spike.

This module guards both deterministically and at ``$0``:

- ``expert_verb_lock`` is a non-blocking advisory file lock keyed by
  (expert, verb). The second caller never blocks and never errors; it is told
  the lock is held so the verb can exit 0 with a recorded skip. Cross-platform
  via ``filelock`` - Windows is a first-class target, so no POSIX ``flock``.
- ``startup_jitter_seconds`` derives a stable, bounded per-expert offset so a
  roster sharing one cron minute spreads its starts instead of stampeding.

Both are pure workflow mechanics over side-effects and timing - no model
judgment - per docs/plans/AGENTIC_BALANCE.md (determinism guards side-effects,
not meaning).
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(text: str, fallback: str) -> str:
    return _NON_SLUG.sub("-", text.lower()).strip("-") or fallback


def _verb_lock_path(expert_name: str, verb: str, lock_dir: Path | None) -> Path:
    if lock_dir is None:
        from deepr.experts.paths import canonical_expert_dir

        # Same canonical (slug) directory as the expert's other sidecars, so the
        # lock is not orphaned in a separate display-named dir.
        lock_dir = canonical_expert_dir(expert_name) / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    # Key the lock by (expert, verb) in the filename, not just the directory, so
    # the guard is correct even when callers share one lock_dir.
    return lock_dir / f"{_slug(expert_name, 'expert')}__{_slug(verb, 'verb')}.lock"


@contextmanager
def expert_verb_lock(expert_name: str, verb: str, *, lock_dir: Path | None = None) -> Iterator[bool]:
    """Hold a non-blocking advisory lock for one (expert, verb).

    Yields ``True`` when the lock was acquired - the caller owns the verb and
    should proceed - and ``False`` immediately when another live process already
    holds it, so the caller should skip and exit 0. The lock is released on block
    exit (including on exception). Never blocks waiting and never raises on
    contention; an acquired lock is always released, so a crash frees it for the
    next run.
    """
    lock = FileLock(str(_verb_lock_path(expert_name, verb, lock_dir)), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        yield False
        return
    try:
        yield True
    finally:
        lock.release()


def startup_jitter_seconds(expert_name: str, max_seconds: float) -> float:
    """A stable, bounded startup offset in ``[0, max_seconds)`` for one expert.

    Deterministic in the expert name (a SHA-256 fraction), so the same expert
    always lands in the same slot and a roster sharing one cadence spreads out
    reproducibly instead of all firing at once. Returns ``0.0`` when
    ``max_seconds <= 0``.
    """
    if max_seconds <= 0:
        return 0.0
    digest = hashlib.sha256(expert_name.encode("utf-8")).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    return fraction * max_seconds


def apply_startup_jitter(
    expert_name: str,
    max_seconds: float,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> float:
    """Sleep for this expert's deterministic startup jitter; return the delay.

    ``sleep`` is injectable so tests assert the delay without waiting.
    """
    delay = startup_jitter_seconds(expert_name, max_seconds)
    if delay > 0:
        sleep(delay)
    return delay
