"""One clock, one interval convention, one sentinel.

There are 62 separate ``_utc_now()`` definitions in this package and at least
four hand-rolled naive-to-UTC coercions. That is survivable while nothing
depends on two of them agreeing. It stops being survivable the moment records
carry validity intervals, because the closed-open convention then has to be
implemented identically everywhere or a version boundary belongs to two
versions in one code path and to neither in the next.

**Closed-open, everywhere: ``start <= t < end``.** Not an aesthetic choice. It
is the only convention under which consecutive versions tile the timeline with
no gap and no overlap, so ``predecessor.superseded_at == successor.recorded_at``
exactly and a point-in-time read returns exactly one version. Closed-closed
forces subtracting one tick, which makes correctness depend on timestamp
resolution.

**A sentinel for open-ended, never NULL.** NULL makes every predicate
two-branch (``superseded_at IS NULL OR superseded_at > t``) and something
eventually gets it wrong - this codebase already has an instance, where a
temporal filter excludes records with missing endpoints instead of treating
them as unbounded, silently under-returning. NULL also conflates "unbounded"
with "unknown" while offering one value for two meanings.

``END_OF_TIME`` is ``datetime.max`` at UTC, which matches SQL:2011's own worked
example and what SQL Server and MarkLogic use, so an export is a no-op. It
round-trips losslessly through ``fromisoformat``/``isoformat`` and sorts
correctly as a plain string, which matters because sorting without parsing is
sometimes the right thing to do.

One deliberate hazard: arithmetic against the sentinel yields absurd durations,
and a "how long did we hold this" metric computed without checking is how an
8000-year mean reaches a chart. ``is_open`` exists so that check is one call.

**Not a general date library.** Valid time and belief time are sparse and
nullable by design, and this module is deliberately silent about them; see
``expert-v2-identity-and-time.md`` for why only the record axis is total.
"""

from __future__ import annotations

from datetime import UTC, datetime

RECORD_TIME_SCHEMA_VERSION = "deepr-record-time-v1"

END_OF_TIME = "9999-12-31T23:59:59.999999+00:00"
"""An interval that has not closed. Never NULL, never a near-future date.

datetime.max at UTC. MariaDB's system-versioning sentinel is 2038-01-19, a live
Y2038 bug where an open row sorts *before* genuinely future-dated rows."""

BEGINNING_OF_TIME = "0001-01-01T00:00:00+00:00"
"""An interval with no known start. Rare, and provided so nothing invents one."""


def utc_now() -> str:
    """The current instant, in the one format every record uses."""
    return datetime.now(UTC).isoformat()


def parse_iso(value: str) -> datetime | None:
    """Parse a stored timestamp, or None when it is absent or unusable.

    Accepts a trailing ``Z`` and assumes UTC for a naive value. Returns None
    rather than raising: a corrupt timestamp on one record must not take down
    a read across a whole store, and a caller that needs to know can check.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def is_open(end: str) -> bool:
    """Whether an interval is still open.

    Use before any duration arithmetic. Subtracting a record time from
    END_OF_TIME produces roughly eight thousand years, and that number will
    otherwise reach a mean, an axis label, or a staleness heuristic.
    """
    return not str(end or "").strip() or str(end).strip() == END_OF_TIME


def contains(start: str, end: str, at: str) -> bool:
    """Whether ``at`` falls in the closed-open interval ``[start, end)``.

    The single implementation of the convention. An unparseable or absent
    ``start`` means the interval has always applied; an absent ``end`` means it
    is still open. Both defaults are chosen so a record written before this
    module existed reads as live rather than silently vanishing.
    """
    moment = parse_iso(at)
    if moment is None:
        return False

    opened = parse_iso(start)
    if opened is not None and moment < opened:
        return False

    if is_open(end):
        return True
    closed = parse_iso(end)
    return closed is None or moment < closed


def overlaps(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    """Whether two closed-open intervals share any instant.

    Used to detect a successor that contradicts rather than continues its
    predecessor, which is a materially stronger event than a plain revision
    and worth flagging separately.
    """
    a_start = parse_iso(start_a) or parse_iso(BEGINNING_OF_TIME)
    b_start = parse_iso(start_b) or parse_iso(BEGINNING_OF_TIME)
    a_end = None if is_open(end_a) else parse_iso(end_a)
    b_end = None if is_open(end_b) else parse_iso(end_b)

    if a_end is not None and b_start is not None and b_start >= a_end:
        return False
    return not (b_end is not None and a_start is not None and a_start >= b_end)


def age_days(since: str, *, now: str = "") -> int:
    """Whole days from ``since`` until now. -1 when unknown.

    -1 rather than 0, because zero is a real answer meaning "today" and a
    missing timestamp is not that.
    """
    started = parse_iso(since)
    if started is None:
        return -1
    current = parse_iso(now) or datetime.now(UTC)
    return max(0, (current - started).days)
