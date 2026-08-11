"""Spread work across every prepaid plan that is actually available.

Building an expert is embarrassingly parallel in one place: a card is one call
per source with no ordering between them, and a study is one call per lens per
chunk. Running those one at a time on a single plan is slow and, worse, drains
one quota while three others sit idle.

A pool hands out completions round-robin over the backends that resolved. Two
consequences beyond speed, and they matter more:

- **No single plan gets exhausted first.** Consumption spreads, so a run that
  would have hit one weekly cap finishes across four.
- **One dead backend is not a dead run.** A completion that raises is retried
  once on the next backend before the failure is returned, since the callers
  already treat a failed unit as a labeled failure rather than an abort.

Deliberately not load-balanced by latency or quality. Backends differ by more
than an order of magnitude in speed, and preferring the fast one would quietly
concentrate the work back onto one plan, which is the thing this exists to
avoid.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

Completion = Callable[[str], Awaitable[str]]


@dataclass
class PooledBackend:
    """One resolved backend and what it has been asked to do."""

    name: str
    completion: Completion
    chunk_chars: int = 0
    calls: int = 0
    failures: int = 0


@dataclass
class BackendPool:
    """Round-robin over prepaid capacity, with one retry elsewhere on failure."""

    backends: list[PooledBackend] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    """Plans that would not build, with the reason, so a thin pool is visible."""
    skipped: list[str] = field(default_factory=list)
    """Plans left out because they were already at their cap, named not hidden."""
    retired: list[str] = field(default_factory=list)
    """Plans that ran out *during* the run, with the reason.

    Distinct from ``skipped``, which was known before starting. A run that
    began with four plans and finished on one did something worth reporting,
    and without this it looks identical to a run that had one all along."""
    headroom_note: str = ""
    _index: int = 0
    _lock: Any = None

    def __post_init__(self) -> None:
        self._lock = asyncio.Lock()

    @property
    def names(self) -> list[str]:
        return [b.name for b in self.backends]

    @property
    def size(self) -> int:
        return len(self.backends)

    @property
    def chunk_chars(self) -> int:
        """The budget every member can hold, which is the smallest of them."""
        sizes = [b.chunk_chars for b in self.backends if b.chunk_chars > 0]
        return min(sizes) if sizes else 0

    def usage(self) -> dict[str, dict[str, int]]:
        """Calls and failures per backend, so a lopsided run is visible."""
        return {b.name: {"calls": b.calls, "failures": b.failures} for b in self.backends}

    async def _next(self) -> PooledBackend:
        async with self._lock:
            backend = self.backends[self._index % len(self.backends)]
            self._index += 1
            return backend

    async def _retire(self, backend: PooledBackend, reason: str) -> None:
        """Take a backend out of rotation for the rest of this run.

        The difference between a bad prompt and a dead plan. A prompt failure
        is one call; an exhausted weekly quota fails identically for every
        remaining call, so leaving it in rotation spends a wasted round-trip
        every cycle - and on a long study that is hundreds of them.

        Retirement is per-run and never persisted. Quota comes back, and a
        cached "grok is dead" would outlive the reset that fixed it.
        """
        async with self._lock:
            if backend in self.backends:
                self.backends.remove(backend)
                self.retired.append(f"{backend.name}: {reason[:120]}")

    async def complete(self, prompt: str) -> str:
        """Run one prompt, moving on from any backend that has run out.

        Two failure kinds, handled differently:

        - **Capacity.** The plan is out. Retire it and try the next one, until
          the pool is empty. This is what makes a run survive a mid-flight
          exhaustion instead of dying with three healthy plans still idle.
        - **Anything else.** Retried once on a *different* backend, then
          returned. A prompt that fails twice is usually the prompt, and
          retrying the same plan spends quota to learn nothing.
        """
        from deepr.experts.study import _is_capacity_failure

        # Started with nothing is a different condition from ran out, and the
        # caller needs to tell them apart: one is a setup problem, the other
        # means wait for a reset.
        if not self.backends:
            raise RuntimeError("no plan-quota backend is available")

        attempted: list[PooledBackend] = []
        last_error: Exception | None = None

        while self.backends:
            backend = await self._next()
            backend.calls += 1
            try:
                return await backend.completion(prompt)
            except Exception as exc:
                backend.failures += 1
                last_error = exc
                if _is_capacity_failure(exc):
                    await self._retire(backend, str(exc))
                    continue
                # Not capacity: one retry elsewhere, then give up on this prompt.
                attempted.append(backend)
                if len(attempted) >= 2 or len(self.backends) < 2:
                    raise

        raise last_error or RuntimeError("every plan-quota backend ran out of capacity: " + "; ".join(self.retired))


def build_pool(
    profile: Any,
    plans: list[str] | tuple[str, ...],
    *,
    use_headroom: bool = True,
) -> BackendPool:
    """Resolve each named plan, best headroom first, skipping the exhausted.

    A plan that is out of quota or not installed is left out rather than
    raising, because a pool of three is still a pool. What it refuses to do is
    silently fall back to a metered path: only plan backends are resolved here.

    Ordering matters more than it looks. Blind round-robin sends work to a plan
    at 95% of its five-hour window as readily as one at 4% of its week, which
    caps the tight one and then fails over. Reading headroom first costs
    nothing and finishes the run without touching it.
    """
    from deepr.cli.commands.semantic.study_backend import build_study_backend

    pool = BackendPool()
    if use_headroom:
        from deepr.backends.quota_headroom import exhausted, order_by_headroom, read_headroom

        headroom = read_headroom()
        if headroom:
            skipped = exhausted(plans, headroom)
            pool.skipped = [headroom[n.lower()].describe() for n in skipped]
            plans = [p for p in order_by_headroom(plans, headroom) if p not in skipped]
            pool.headroom_note = ", ".join(headroom[p.lower()].describe() for p in plans if p.lower() in headroom)

    for plan in plans:
        try:
            backend = build_study_backend(profile=profile, local=False, plan=plan, plan_model=None, model=None)
        except Exception as exc:
            # Named rather than dropped: a pool that is quietly one backend
            # instead of four looks identical to one that is working.
            pool.unavailable.append(f"{plan}: {str(exc)[:120]}")
            logger.debug("plan backend %s unavailable", plan, exc_info=True)
            continue
        pool.backends.append(PooledBackend(name=plan, completion=backend.completion, chunk_chars=backend.chunk_chars))
    return pool


async def map_pooled(
    pool: BackendPool,
    items: list[Any],
    run: Callable[[Any, Completion], Awaitable[Any]],
    *,
    concurrency: int = 0,
) -> list[Any]:
    """Run one unit of work per item, spread across the pool.

    Concurrency defaults to the pool size: more in flight than there are
    backends just queues requests at one vendor, which is where rate limits
    live.
    """
    if not items:
        return []
    limit = concurrency or max(1, pool.size)
    gate = asyncio.Semaphore(limit)

    async def _one(item: Any) -> Any:
        async with gate:
            return await run(item, pool.complete)

    return await asyncio.gather(*(_one(item) for item in items))
