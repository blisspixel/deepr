"""A bounded, expiring spend authority for work a person is watching.

Paid dispatch has one authority mode and it cannot be satisfied: unfreezing
requires provider-signed account-control evidence, and no adapter produces it.
The result is not "safe by default" but "unusable", and an unusable control
gets routed around - by exporting a key and calling the provider directly,
outside this project's ledger, where none of its accounting can see the money.

This is the missing middle. It exists because two different risks were being
served by one control:

- **Unattended.** An agent loop, a schedule, an MCP call. Spends for hours with
  nobody watching, in amounts nobody named. Only the provider refusing to bill
  past a cap is real protection. That path keeps requiring evidence.
- **Attended.** A person at a terminal who typed a command and named a ceiling.
  A cap they set plus an acknowledgement they gave is proportionate, because
  the exposure is bounded and someone is present to see the outcome.

A grant is the second one, made explicit and made to expire.

What keeps "no surprise bills" true:

**A ceiling on the ceiling.** ``MAX_GRANT_USD`` refuses a grant larger than it
rather than clamping. A silently reduced authorization is its own surprise, and
a mistyped 200 must be refused.

**Expiry.** A grant is minutes. A forgotten grant that never expires is exactly
how an attended control decays into an unattended one.

**Binding to the cost state and starting total.** A grant carries the
cost-state id and canonical settled total it was issued against. The amount is
therefore a true draw-down from issuance, not a calendar-month cap that can be
exhausted by older spend or reset at midnight.

**It is authority, not accounting.** Grants raise the ceiling; the existing
durable reservation, settlement and orphaned-spend detection are untouched and
still decide what actually happened.

**Consent is still separate.** A grant does not imply ``confirm_metered_cost``
for any call. Two independent things must agree: the operator authorized this
much, and this specific call was acknowledged.
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

GRANT_SCHEMA_VERSION = "deepr-attended-spend-grant-v2"

MAX_GRANT_USD = 2.0
"""The largest attended grant that may be issued.

Attended spend is for bounded, supervised work. Two dollars is the hard total
ceiling, not a per-call allowance. Anything larger belongs behind
provider-verified authority instead."""

MAX_GRANT_MINUTES = 240
"""Four hours. Long enough for a deep-research run, short enough that a grant
forgotten at the end of a day is not still live the next morning."""

_MIN_GRANT_USD = 0.01


class AttendedGrantError(RuntimeError):
    """A grant could not be issued or is not usable."""


@dataclass(frozen=True)
class AttendedGrant:
    """One bounded authorization to spend, issued to a present operator."""

    schema_version: str
    grant_id: str
    amount_usd: float
    issued_at: str
    expires_at: str
    cost_state_id: str
    settled_cost_baseline_usd: float
    reason: str
    provider: str = ""
    """Empty means any provider. A grant may be narrowed to one."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AttendedGrant:
        return cls(
            schema_version=str(data.get("schema_version") or ""),
            grant_id=str(data.get("grant_id") or ""),
            amount_usd=float(data.get("amount_usd", 0.0) or 0.0),
            issued_at=str(data.get("issued_at") or ""),
            expires_at=str(data.get("expires_at") or ""),
            cost_state_id=str(data.get("cost_state_id") or ""),
            settled_cost_baseline_usd=float(data.get("settled_cost_baseline_usd", -1.0)),
            reason=str(data.get("reason") or ""),
            provider=str(data.get("provider") or ""),
        )

    def remaining_seconds(self, *, now: datetime | None = None) -> float:
        """Seconds of life left, negative once expired."""
        expiry = _parse(self.expires_at)
        if expiry is None:
            return -1.0
        return (expiry - (now or datetime.now(UTC))).total_seconds()

    def is_live(self, *, cost_state_id: str, now: datetime | None = None) -> bool:
        """Whether this grant still authorizes anything.

        Checked rather than trusted on every read: a grant on disk is a claim,
        and time passes between issuing it and using it.
        """
        if self.schema_version != GRANT_SCHEMA_VERSION:
            return False
        if not self.grant_id:
            return False
        if not math.isfinite(self.amount_usd) or not _MIN_GRANT_USD <= self.amount_usd <= MAX_GRANT_USD:
            return False
        # An absent binding is not a wildcard. Treating empty as "matches any"
        # meant a grant with its cost_state_id stripped would authorize spend
        # against any ledger, which is the opposite of what the binding is for.
        if not self.cost_state_id or not cost_state_id or self.cost_state_id != cost_state_id:
            return False
        if not math.isfinite(self.settled_cost_baseline_usd) or self.settled_cost_baseline_usd < 0:
            return False
        return self.remaining_seconds(now=now) > 0

    def consumed_usd(self, *, total_settled_cost_usd: float) -> float:
        """Canonical paid spend appended since this grant was issued."""
        if not math.isfinite(total_settled_cost_usd) or total_settled_cost_usd < 0:
            raise AttendedGrantError("canonical settled cost must be a finite non-negative number")
        if total_settled_cost_usd < self.settled_cost_baseline_usd:
            raise AttendedGrantError("canonical settled cost is below the grant baseline")
        return total_settled_cost_usd - self.settled_cost_baseline_usd

    def remaining_usd(self, *, total_settled_cost_usd: float, active_holds_usd: float = 0.0) -> float:
        """Uncommitted grant authority after settled spend and durable holds."""
        if not math.isfinite(active_holds_usd) or active_holds_usd < 0:
            raise AttendedGrantError("active holds must be a finite non-negative number")
        return max(
            0.0,
            self.amount_usd - self.consumed_usd(total_settled_cost_usd=total_settled_cost_usd) - active_holds_usd,
        )


def _parse(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def grant_file_path(root: Path | None = None) -> Path:
    """Where the current grant lives. One at a time, deliberately.

    Concurrent grants would make the effective ceiling the sum of things nobody
    is looking at together, which is the property this exists to prevent.
    """
    if root is not None:
        return root / "attended_grant.json"
    from deepr.config import runtime_data_path

    return runtime_data_path("costs") / "attended_grant.json"


def issue_grant(
    *,
    amount_usd: float,
    minutes: int,
    cost_state_id: str,
    settled_cost_baseline_usd: float,
    reason: str = "",
    provider: str = "",
    now: datetime | None = None,
) -> AttendedGrant:
    """Build a grant, refusing anything outside the attended envelope.

    Refuses rather than clamps. An operator who asked for more than the ceiling
    should be told, not quietly given less than they think they have.
    """
    if not cost_state_id:
        raise AttendedGrantError("a grant must be bound to a known cost state")
    if (
        isinstance(settled_cost_baseline_usd, bool)
        or not math.isfinite(settled_cost_baseline_usd)
        or settled_cost_baseline_usd < 0
    ):
        raise AttendedGrantError("a grant baseline must be a finite non-negative settled cost")
    if not math.isfinite(amount_usd):
        # NaN compares False against both < and >, so it would pass the floor
        # and the ceiling and be written as an authorized amount.
        raise AttendedGrantError("a grant amount must be a finite number of dollars")
    if amount_usd < _MIN_GRANT_USD:
        raise AttendedGrantError(f"a grant must authorize at least ${_MIN_GRANT_USD:.2f}")
    if amount_usd > MAX_GRANT_USD:
        raise AttendedGrantError(
            f"${amount_usd:.2f} exceeds the ${MAX_GRANT_USD:.2f} attended ceiling. "
            "Larger spend belongs behind provider-verified authority, not an attended grant."
        )
    if not 1 <= minutes <= MAX_GRANT_MINUTES:
        raise AttendedGrantError(f"a grant must last between 1 and {MAX_GRANT_MINUTES} minutes")

    issued = now or datetime.now(UTC)
    return AttendedGrant(
        schema_version=GRANT_SCHEMA_VERSION,
        grant_id=uuid.uuid4().hex,
        amount_usd=round(float(amount_usd), 2),
        issued_at=issued.isoformat(),
        expires_at=(issued + timedelta(minutes=minutes)).isoformat(),
        cost_state_id=cost_state_id,
        settled_cost_baseline_usd=float(settled_cost_baseline_usd),
        reason=reason.strip(),
        provider=provider.strip().lower(),
    )


def save_grant(grant: AttendedGrant, path: Path | None = None) -> Path:
    """Persist the grant atomically."""
    from deepr.utils.atomic_io import atomic_write_json

    target = path or grant_file_path()
    atomic_write_json(target, grant.to_dict(), fsync=True)
    return target


def load_grant(path: Path | None = None) -> AttendedGrant | None:
    """The grant on disk, or None when there is none or it is unreadable.

    Unreadable is None rather than an error: a corrupt grant must fail closed
    into "no authority", never into "some authority nobody can inspect".
    """
    target = path or grant_file_path()
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return AttendedGrant.from_dict(data)
    except (TypeError, ValueError):
        # A grant whose fields will not parse is no more usable than a missing
        # one, and raising here would break fail-closed for every caller.
        return None


def revoke_grant(path: Path | None = None) -> bool:
    """Remove the grant. Returns whether one was there."""
    target = path or grant_file_path()
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise AttendedGrantError(f"the grant could not be revoked: {exc}") from exc


def active_grant(*, cost_state_id: str, now: datetime | None = None, path: Path | None = None) -> AttendedGrant | None:
    """The grant currently authorizing spend, if any.

    The single question the authority layer asks. Everything about validity -
    schema, expiry, cost-state binding - is decided here rather than by each
    caller remembering to check.
    """
    grant = load_grant(path)
    if grant is None:
        return None
    return grant if grant.is_live(cost_state_id=cost_state_id, now=now) else None
