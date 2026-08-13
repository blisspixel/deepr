"""Persistent cumulative authority for attended metered API spend.

The wallet is a local safety control. It does not buy provider credits and it
must never be described as proof that a provider account is prepaid. Its one
job is to make the operator's chosen cumulative exposure executable: every
settled metered dollar and every active durable hold draws down one balance.

Actual provider-side prepaid credits or a hard provider cap with paid overage
disabled remain the stronger control. Unattended work still requires proof of
that external boundary and ignores this wallet entirely.
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

WALLET_SCHEMA_VERSION = "deepr-metered-spend-wallet-v1"

# IEEE-754 integers are exact through 2**53. Storing dollars rounded to cents is
# therefore exact through this value. This is a representation boundary, not a
# recommended or product-level spending cap.
MAX_EXACT_CENTS = 2**53 - 1
MAX_EXACT_CENTS_USD = MAX_EXACT_CENTS / 100
MIN_CREDIT_USD = 0.01
MAX_REASON_LENGTH = 500
_WALLET_FIELDS = frozenset(
    {
        "schema_version",
        "wallet_id",
        "authorized_cents",
        "created_at",
        "updated_at",
        "cost_state_id",
        "settled_cost_baseline_usd",
        "reason",
    }
)


class SpendWalletError(RuntimeError):
    """The local metered-spend wallet is invalid or cannot be changed safely."""


def _money(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpendWalletError(f"{field} must be a finite number of dollars")
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > MAX_EXACT_CENTS_USD:
        raise SpendWalletError(f"{field} must be a finite non-negative amount")
    return number


def _credit_cents(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpendWalletError(f"{field} must be a finite positive amount with exact cents")
    try:
        decimal = Decimal(str(value))
    except InvalidOperation as exc:
        raise SpendWalletError(f"{field} must be a finite positive amount with exact cents") from exc
    cents = decimal * 100
    if not decimal.is_finite() or decimal < Decimal("0.01") or cents != cents.to_integral_value():
        raise SpendWalletError(f"{field} must be a finite positive amount with exact cents")
    integer = int(cents)
    if integer > MAX_EXACT_CENTS:
        raise SpendWalletError(f"{field} exceeds the exact-cent storage boundary")
    return integer


def _bounded_reason(value: object) -> str:
    if not isinstance(value, str):
        raise SpendWalletError("wallet reason must be text")
    reason = value.strip()
    if len(reason) > MAX_REASON_LENGTH:
        raise SpendWalletError(f"wallet reason must contain at most {MAX_REASON_LENGTH} characters")
    return reason


def _cost_state_identifier(value: object) -> str:
    if not isinstance(value, str) or len(value) != 32:
        raise SpendWalletError("wallet cost state must be a 32-character hexadecimal identifier")
    try:
        int(value, 16)
    except ValueError as exc:
        raise SpendWalletError("wallet cost state must be a 32-character hexadecimal identifier") from exc
    return value


@dataclass(frozen=True)
class SpendWallet:
    """One additive cumulative authorization bound to canonical money state."""

    schema_version: str
    wallet_id: str
    authorized_cents: int
    created_at: str
    updated_at: str
    cost_state_id: str
    settled_cost_baseline_usd: float
    reason: str = ""

    @property
    def authorized_usd(self) -> float:
        return self.authorized_cents / 100

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpendWallet:
        if set(data) != _WALLET_FIELDS:
            raise SpendWalletError("wallet fields do not match the supported schema")
        for field_name in ("schema_version", "wallet_id", "created_at", "updated_at", "cost_state_id"):
            if not isinstance(data[field_name], str):
                raise SpendWalletError(f"wallet {field_name} must be text")
        authorized_cents = data["authorized_cents"]
        if isinstance(authorized_cents, bool) or not isinstance(authorized_cents, int):
            raise SpendWalletError("wallet authorized_cents must be an integer")
        baseline = _money(data["settled_cost_baseline_usd"], field="wallet settled baseline")
        return cls(
            schema_version=data["schema_version"],
            wallet_id=data["wallet_id"],
            authorized_cents=authorized_cents,
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            cost_state_id=data["cost_state_id"],
            settled_cost_baseline_usd=baseline,
            reason=_bounded_reason(data["reason"]),
        )

    def is_valid(self, *, cost_state_id: str) -> bool:
        """Whether this document can authorize attended spend."""
        if self.schema_version != WALLET_SCHEMA_VERSION:
            return False
        if not isinstance(self.wallet_id, str) or not isinstance(self.cost_state_id, str):
            return False
        if len(self.wallet_id) != 32 or len(self.cost_state_id) != 32:
            return False
        try:
            int(self.wallet_id, 16)
            int(self.cost_state_id, 16)
        except ValueError:
            return False
        if not cost_state_id or self.cost_state_id != cost_state_id:
            return False
        try:
            if not 1 <= self.authorized_cents <= MAX_EXACT_CENTS:
                return False
            _money(self.settled_cost_baseline_usd, field="wallet settled baseline")
            _bounded_reason(self.reason)
        except SpendWalletError:
            return False
        created = _parse_timestamp(self.created_at)
        updated = _parse_timestamp(self.updated_at)
        return created is not None and updated is not None and created <= updated

    def consumed_usd(self, *, total_settled_cost_usd: float) -> float:
        """Canonical metered spend appended since the wallet was created."""
        total = _money(total_settled_cost_usd, field="canonical settled cost")
        if total < self.settled_cost_baseline_usd:
            raise SpendWalletError("canonical settled cost is below the wallet baseline")
        return total - self.settled_cost_baseline_usd

    def available_usd(self, *, total_settled_cost_usd: float, active_holds_usd: float = 0.0) -> float:
        """Uncommitted wallet authority after spend and durable reservations."""
        holds = _money(active_holds_usd, field="active holds")
        return max(0.0, self.authorized_usd - self.consumed_usd(total_settled_cost_usd=total_settled_cost_usd) - holds)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def wallet_file_path(root: Path | None = None) -> Path:
    """Return the wallet path colocated with the ledger and reservations."""
    if root is not None:
        return root / "spend_wallet.json"
    from deepr.observability.cost_authority import default_cost_data_dir

    return default_cost_data_dir() / "spend_wallet.json"


def create_wallet(
    *,
    amount_usd: float,
    cost_state_id: str,
    settled_cost_baseline_usd: float,
    reason: str = "",
    now: datetime | None = None,
) -> SpendWallet:
    """Create a new wallet document without writing it."""
    cost_state_id = _cost_state_identifier(cost_state_id)
    authorized_cents = _credit_cents(amount_usd, field="credit amount")
    baseline = _money(settled_cost_baseline_usd, field="wallet settled baseline")
    stamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    return SpendWallet(
        schema_version=WALLET_SCHEMA_VERSION,
        wallet_id=uuid.uuid4().hex,
        authorized_cents=authorized_cents,
        created_at=stamp,
        updated_at=stamp,
        cost_state_id=cost_state_id,
        settled_cost_baseline_usd=baseline,
        reason=_bounded_reason(reason),
    )


def add_credits(
    wallet: SpendWallet,
    *,
    amount_usd: float,
    cost_state_id: str,
    reason: str = "",
    now: datetime | None = None,
) -> SpendWallet:
    """Add explicit authorization while preserving one drawdown baseline."""
    cost_state_id = _cost_state_identifier(cost_state_id)
    if wallet.cost_state_id != cost_state_id:
        raise SpendWalletError("the existing wallet belongs to another current cost state")
    if not wallet.is_valid(cost_state_id=cost_state_id):
        raise SpendWalletError("the existing wallet is not valid for the current cost state")
    amount_cents = _credit_cents(amount_usd, field="credit amount")
    authorized_cents = wallet.authorized_cents + amount_cents
    if authorized_cents > MAX_EXACT_CENTS:
        raise SpendWalletError("resulting wallet authorization exceeds the exact-cent storage boundary")
    stamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    stamp_time = _parse_timestamp(stamp)
    previous_time = _parse_timestamp(wallet.updated_at)
    if stamp_time is None or previous_time is None or stamp_time < previous_time:
        raise SpendWalletError("wallet update time cannot precede its last update")
    return replace(
        wallet,
        authorized_cents=authorized_cents,
        updated_at=stamp,
        reason=_bounded_reason(reason) or wallet.reason,
    )


def save_wallet(wallet: SpendWallet, path: Path | None = None) -> Path:
    """Persist the current wallet atomically."""
    from deepr.utils.atomic_io import atomic_write_json

    if not wallet.is_valid(cost_state_id=wallet.cost_state_id):
        raise SpendWalletError("an invalid wallet cannot be saved")
    target = path or wallet_file_path()
    atomic_write_json(target, wallet.to_dict(), fsync=True)
    return target


def load_wallet(path: Path | None = None) -> SpendWallet | None:
    """Read the wallet, returning no authority for malformed input."""
    target = path or wallet_file_path()
    if not target.exists():
        return None

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant {value!r} is not allowed")

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        document: dict[str, object] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"duplicate JSON key {key!r} is not allowed")
            document[key] = value
        return document

    try:
        data = json.loads(
            target.read_text(encoding="utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return SpendWallet.from_dict(data)
    except (SpendWalletError, TypeError, ValueError):
        return None


def active_wallet(*, cost_state_id: str, path: Path | None = None) -> SpendWallet | None:
    """Return the wallet bound to this canonical cost state, if valid."""
    wallet = load_wallet(path)
    if wallet is None:
        return None
    return wallet if wallet.is_valid(cost_state_id=cost_state_id) else None


def clear_wallet(path: Path | None = None) -> bool:
    """Remove cumulative authority and block new attended reservations."""
    target = path or wallet_file_path()
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise SpendWalletError(f"the wallet could not be cleared: {exc}") from exc


__all__ = [
    "MAX_EXACT_CENTS",
    "MAX_EXACT_CENTS_USD",
    "MIN_CREDIT_USD",
    "SpendWallet",
    "SpendWalletError",
    "active_wallet",
    "add_credits",
    "clear_wallet",
    "create_wallet",
    "load_wallet",
    "save_wallet",
    "wallet_file_path",
]
