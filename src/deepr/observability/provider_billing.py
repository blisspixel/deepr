"""Offline provider billing reconciliation with fail-closed apply semantics."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from filelock import FileLock
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from deepr.observability.cost_ledger import (
    CostLedger,
    CostLedgerEvent,
    default_cost_data_dir,
    well_known_ledger_paths,
)
from deepr.utils.atomic_io import atomic_write_bytes

BILLING_IMPORT_SCHEMA_VERSION: Literal["deepr-provider-billing-import-v1"] = "deepr-provider-billing-import-v1"
BILLING_IMPORT_KIND: Literal["deepr.costs.provider_billing_import"] = "deepr.costs.provider_billing_import"
BILLING_RECONCILIATION_SCHEMA_VERSION: Literal["deepr-provider-billing-reconciliation-v1"] = (
    "deepr-provider-billing-reconciliation-v1"
)
BILLING_RECONCILIATION_KIND: Literal["deepr.costs.provider_billing_reconciliation"] = (
    "deepr.costs.provider_billing_reconciliation"
)
_MAX_SOURCE_BYTES = 5 * 1024 * 1024
_MAX_LEDGER_BYTES = 100 * 1024 * 1024
_MAX_DEPTH = 12
_MAX_LINES = 10_000
_MONEY_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?$")
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,199}$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_SECRET_PREFIXES = ("sk-", "xai-", "bearer ", "aiza", "anthropic-")


class ProviderBillingError(RuntimeError):
    """Base class for safe provider-billing failures."""


class ProviderBillingValidationError(ProviderBillingError):
    """A normalized provider statement failed its closed contract."""


class ProviderBillingStorageError(ProviderBillingError):
    """Immutable billing evidence could not be stored safely."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _validate_identifier(value: str, *, field_name: str, optional: bool = False) -> str:
    if optional and not value:
        return value
    if _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a bounded opaque identifier")
    return value


def _parse_utc(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a timezone-aware UTC timestamp") from exc
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{field_name} must be a timezone-aware UTC timestamp")
    return parsed.astimezone(UTC)


def _money(value: str, *, field_name: str) -> Decimal:
    if _MONEY_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a decimal string with at most six fractional digits")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a finite decimal string") from exc


def _decimal_to_microusd(value: Decimal) -> int:
    scaled = value * Decimal(1_000_000)
    if scaled != scaled.to_integral_value():
        raise ProviderBillingValidationError("money contains more than six fractional digits")
    return int(scaled)


def _float_to_microusd(value: float) -> int:
    if value < 0:
        raise ProviderBillingValidationError("canonical ledger contains negative cost")
    return int((Decimal(str(value)) * Decimal(1_000_000)).to_integral_value(rounding=ROUND_CEILING))


class BillingScope(_StrictModel):
    scope_ref: StrictStr
    account_id: StrictStr = ""
    organization_id: StrictStr = ""
    project_id: StrictStr = ""
    workspace_id: StrictStr = ""
    subscription_id: StrictStr = ""
    credential_fingerprint: StrictStr = ""

    @field_validator(
        "scope_ref",
        "account_id",
        "organization_id",
        "project_id",
        "workspace_id",
        "subscription_id",
    )
    @classmethod
    def validate_identifiers(cls, value: str, info: Any) -> str:
        return _validate_identifier(value, field_name=str(info.field_name), optional=info.field_name != "scope_ref")

    @field_validator("credential_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: str) -> str:
        if value and re.fullmatch(r"sha256:[a-f0-9]{64}", value) is None:
            raise ValueError("credential_fingerprint must be an external SHA-256 fingerprint")
        return value


class BillingStatement(_StrictModel):
    statement_id: StrictStr
    status: Literal["final", "provisional"]
    complete: StrictBool
    period_start: StrictStr
    period_end: StrictStr
    currency: StrictStr
    source_posture: Literal["operator_normalized", "provider_export", "provider_api"]
    net_total_usd: StrictStr

    @field_validator("statement_id")
    @classmethod
    def validate_statement_id(cls, value: str) -> str:
        return _validate_identifier(value, field_name="statement_id")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        if re.fullmatch(r"[A-Z]{3}", value) is None:
            raise ValueError("currency must be a three-letter uppercase code")
        return value

    @field_validator("net_total_usd")
    @classmethod
    def validate_total(cls, value: str) -> str:
        _money(value, field_name="net_total_usd")
        return value

    @model_validator(mode="after")
    def validate_period(self) -> BillingStatement:
        if _parse_utc(self.period_end, field_name="period_end") <= _parse_utc(
            self.period_start, field_name="period_start"
        ):
            raise ValueError("statement period_end must be after period_start")
        return self


class BillingLine(_StrictModel):
    line_id: StrictStr
    category: Literal["metered_api", "tool", "storage", "cache", "tax", "credit", "adjustment", "other"]
    capacity_class: Literal["api_metered", "prepaid_plan", "owned_local", "unknown"]
    usage_start: StrictStr
    usage_end: StrictStr
    charge_usd: StrictStr
    credit_usd: StrictStr
    adjustment_usd: StrictStr
    tax_usd: StrictStr
    net_usd: StrictStr
    model: StrictStr = ""
    sku: StrictStr = ""
    pricing_tier: StrictStr = ""
    provider_http_request_id: StrictStr = ""
    provider_object_id: StrictStr = ""
    provider_job_id: StrictStr = ""
    provider_request_id: StrictStr = ""
    client_correlation_id: StrictStr = ""

    @field_validator("line_id")
    @classmethod
    def validate_line_id(cls, value: str) -> str:
        return _validate_identifier(value, field_name="line_id")

    @field_validator(
        "model",
        "sku",
        "pricing_tier",
        "provider_http_request_id",
        "provider_object_id",
        "provider_job_id",
        "provider_request_id",
        "client_correlation_id",
    )
    @classmethod
    def validate_optional_identifiers(cls, value: str, info: Any) -> str:
        return _validate_identifier(value, field_name=str(info.field_name), optional=True)

    @field_validator("charge_usd", "credit_usd", "adjustment_usd", "tax_usd", "net_usd")
    @classmethod
    def validate_money(cls, value: str, info: Any) -> str:
        _money(value, field_name=str(info.field_name))
        return value

    @model_validator(mode="after")
    def validate_line(self) -> BillingLine:
        start = _parse_utc(self.usage_start, field_name="usage_start")
        end = _parse_utc(self.usage_end, field_name="usage_end")
        if end < start:
            raise ValueError("usage_end must not precede usage_start")
        charge = _money(self.charge_usd, field_name="charge_usd")
        credit = _money(self.credit_usd, field_name="credit_usd")
        adjustment = _money(self.adjustment_usd, field_name="adjustment_usd")
        tax = _money(self.tax_usd, field_name="tax_usd")
        net = _money(self.net_usd, field_name="net_usd")
        if charge < 0 or tax < 0 or credit > 0:
            raise ValueError("charge and tax must be non-negative and credit must be non-positive")
        if charge + credit + adjustment + tax != net:
            raise ValueError("billing line components must sum exactly to net_usd")
        return self

    def receipt_values(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (basis, value)
            for basis, value in (
                ("provider_http_request_id", self.provider_http_request_id),
                ("provider_object_id", self.provider_object_id),
                ("provider_job_id", self.provider_job_id),
                ("provider_request_id", self.provider_request_id),
                ("client_correlation_id", self.client_correlation_id),
            )
            if value
        )


class ProviderBillingImport(_StrictModel):
    schema_version: Literal["deepr-provider-billing-import-v1"]
    kind: Literal["deepr.costs.provider_billing_import"]
    provider: StrictStr
    billing_scope: BillingScope
    statement: BillingStatement
    lines: list[BillingLine] = Field(min_length=1, max_length=_MAX_LINES)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.strip().casefold()
        return _validate_identifier(normalized, field_name="provider")

    @model_validator(mode="after")
    def validate_totals_and_periods(self) -> ProviderBillingImport:
        line_ids = [line.line_id for line in self.lines]
        if len(set(line_ids)) != len(line_ids):
            raise ValueError("billing line IDs must be unique")
        statement_start = _parse_utc(self.statement.period_start, field_name="period_start")
        statement_end = _parse_utc(self.statement.period_end, field_name="period_end")
        total = Decimal(0)
        for line in self.lines:
            if _parse_utc(line.usage_start, field_name="usage_start") < statement_start:
                raise ValueError("billing line starts before the statement period")
            if _parse_utc(line.usage_end, field_name="usage_end") > statement_end:
                raise ValueError("billing line ends after the statement period")
            total += _money(line.net_usd, field_name="net_usd")
        if total != _money(self.statement.net_total_usd, field_name="net_total_usd"):
            raise ValueError("billing line totals must sum exactly to statement net_total_usd")
        return self


class BillingMatch(_StrictModel):
    line_id: StrictStr
    ledger_event_ref: StrictStr
    basis: StrictStr
    provider_microusd: int
    ledger_microusd: int


class UnmatchedProviderLine(_StrictModel):
    line_id: StrictStr
    positive_microusd: int
    reason: StrictStr


class UnmatchedLedgerEvent(_StrictModel):
    ledger_event_ref: StrictStr
    cost_microusd: int
    reason: StrictStr


class BillingMatchCounts(_StrictModel):
    statement_lines: int
    positive_lines: int
    matched_positive_lines: int
    ambiguous_positive_lines: int
    unmatched_positive_lines: int
    local_positive_events: int
    unmatched_local_events: int


class BillingReconciliation(_StrictModel):
    schema_version: Literal["deepr-provider-billing-reconciliation-v1"]
    kind: Literal["deepr.costs.provider_billing_reconciliation"]
    source_sha256: StrictStr
    normalized_sha256: StrictStr
    ledger_snapshot_sha256: StrictStr
    provider: StrictStr
    scope_ref: StrictStr
    account_id: StrictStr
    statement_id: StrictStr
    period_start: StrictStr
    period_end: StrictStr
    currency: StrictStr
    statement_status: Literal["final", "provisional"]
    statement_complete: StrictBool
    statement_source_posture: Literal["operator_normalized", "provider_export", "provider_api"]
    status: Literal["clean", "drift", "ambiguous", "incomplete", "provisional", "unsupported_currency"]
    provider_net_microusd: int
    api_metered_net_microusd: int
    prepaid_plan_net_microusd: int
    owned_local_net_microusd: int
    unknown_net_microusd: int
    local_ledger_microusd: int
    net_drift_microusd: int
    gross_unexplained_positive_microusd: int
    credits_and_negative_adjustments_microusd: int
    local_overstatement_microusd: int
    match_counts: BillingMatchCounts
    matches: list[BillingMatch]
    unmatched_provider_lines: list[UnmatchedProviderLine]
    unmatched_ledger_events: list[UnmatchedLedgerEvent]
    authority_limitations: list[StrictStr]
    freeze_required: StrictBool
    freeze_applied: StrictBool
    zero_network_calls: Literal[True]
    zero_provider_calls: Literal[True]

    @field_validator("source_sha256", "normalized_sha256", "ledger_snapshot_sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("digest must be a lowercase SHA-256 value")
        return value


@dataclass(frozen=True)
class LoadedBillingImport:
    document: ProviderBillingImport
    source_sha256: str
    normalized_sha256: str
    normalized_bytes: bytes


@dataclass(frozen=True)
class BillingLedgerSnapshot:
    events: tuple[CostLedgerEvent, ...]
    sha256: str


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProviderBillingValidationError("billing JSON contains a duplicate object key")
        result[key] = value
    return result


def _depth(value: Any, level: int = 0) -> int:
    if level > _MAX_DEPTH:
        return level
    if isinstance(value, dict):
        return max((_depth(item, level + 1) for item in value.values()), default=level)
    if isinstance(value, list):
        return max((_depth(item, level + 1) for item in value), default=level)
    return level


def _reject_secret_values(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if any(marker in key.casefold() for marker in ("api_key", "authorization", "secret", "token")):
                raise ProviderBillingValidationError("billing JSON contains a forbidden secret-bearing field")
            _reject_secret_values(item)
    elif isinstance(value, list):
        for item in value:
            _reject_secret_values(item)
    elif isinstance(value, str) and value.casefold().startswith(_SECRET_PREFIXES):
        raise ProviderBillingValidationError("billing JSON contains a value that resembles a credential")


def _safe_validation_message(exc: ValidationError) -> str:
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    rendered = []
    for error in errors[:8]:
        location = ".".join(str(part) for part in error.get("loc", ())) or "document"
        rendered.append(f"{location}: {error.get('type', 'invalid')}")
    return "billing JSON failed validation at " + "; ".join(rendered)


def _canonical_bytes(value: BaseModel | dict[str, Any] | list[Any]) -> bytes:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode(
        "utf-8"
    )


def load_billing_import(
    path: Path,
    *,
    expect_provider: str | None = None,
    expect_scope_ref: str | None = None,
) -> LoadedBillingImport:
    """Read one bounded normalized statement without performing any write."""
    try:
        size = path.stat().st_size
        if size > _MAX_SOURCE_BYTES:
            raise ProviderBillingValidationError("billing JSON exceeds the 5 MiB input limit")
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        parsed = json.loads(text, object_pairs_hook=_duplicate_guard)
    except ProviderBillingValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProviderBillingValidationError("billing JSON is unreadable or malformed") from exc
    if _depth(parsed) > _MAX_DEPTH:
        raise ProviderBillingValidationError("billing JSON exceeds the maximum nesting depth")
    _reject_secret_values(parsed)
    try:
        document = ProviderBillingImport.model_validate(parsed)
    except ValidationError as exc:
        raise ProviderBillingValidationError(_safe_validation_message(exc)) from exc
    if expect_provider is not None and document.provider != expect_provider.strip().casefold():
        raise ProviderBillingValidationError("billing provider does not match the expected provider")
    if expect_scope_ref is not None and document.billing_scope.scope_ref != expect_scope_ref:
        raise ProviderBillingValidationError("billing scope does not match the expected scope")
    normalized = _canonical_bytes(document)
    return LoadedBillingImport(
        document=document,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        normalized_bytes=normalized,
    )


def _ledger_paths(ledger_path: Path | None) -> tuple[Path, ...]:
    if ledger_path is not None:
        return (ledger_path,)
    return tuple(path for path in well_known_ledger_paths() if path.exists())


def _bounded_ledger_read(path: Path) -> bytes:
    try:
        if path.stat().st_size > _MAX_LEDGER_BYTES:
            raise ProviderBillingValidationError("canonical cost ledger exceeds the read-only audit limit")
        raw = path.read_bytes()
    except FileNotFoundError:
        return b""
    except OSError as exc:
        raise ProviderBillingValidationError("canonical cost ledger is unreadable") from exc
    if len(raw) > _MAX_LEDGER_BYTES:
        raise ProviderBillingValidationError("canonical cost ledger exceeds the read-only audit limit")
    return raw


def _read_ledger_bytes_stably(ledger_path: Path | None) -> tuple[tuple[Path, bytes], ...]:
    for _attempt in range(3):
        paths = _ledger_paths(ledger_path)
        first = tuple((path, _bounded_ledger_read(path)) for path in paths)
        if _ledger_paths(ledger_path) != paths:
            continue
        second = tuple((path, _bounded_ledger_read(path)) for path in paths)
        if _ledger_paths(ledger_path) == paths and first == second:
            return tuple(first)
    raise ProviderBillingValidationError("canonical cost ledger changed during write-free preview")


def _same_idempotent_event(existing: CostLedgerEvent, proposed: CostLedgerEvent) -> bool:
    """Mirror strict ledger identity while ignoring only append timestamp."""
    return (
        existing.operation == proposed.operation
        and existing.provider == proposed.provider
        and existing.cost_usd == proposed.cost_usd
        and existing.model == proposed.model
        and existing.tokens_input == proposed.tokens_input
        and existing.tokens_output == proposed.tokens_output
        and existing.task_id == proposed.task_id
        and existing.session_id == proposed.session_id
        and existing.request_id == proposed.request_id
        and existing.source == proposed.source
        and existing.metadata == proposed.metadata
        and existing.agent_id == proposed.agent_id
    )


def _normalize_accounting_events(events: list[CostLedgerEvent]) -> list[CostLedgerEvent]:
    normalized: list[CostLedgerEvent] = []
    idempotent: dict[str, CostLedgerEvent] = {}
    for event in events:
        existing = idempotent.get(event.idempotency_key) if event.idempotency_key else None
        if existing is not None:
            if not _same_idempotent_event(existing, event):
                raise ProviderBillingValidationError(
                    "canonical cost ledger contains conflicting cross-root idempotency events"
                )
            continue
        if event.idempotency_key:
            idempotent[event.idempotency_key] = event
        normalized.append(event)
    normalized.sort(key=lambda event: event.timestamp)
    return normalized


def read_only_ledger_snapshot(ledger_path: Path | None = None) -> BillingLedgerSnapshot:
    """Build a strict stable ledger snapshot without creating lock files."""
    files = _read_ledger_bytes_stably(ledger_path)
    events: list[CostLedgerEvent] = []
    digest = hashlib.sha256()
    for path, raw in files:
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(raw)
        try:
            text = raw.decode("utf-8")
        except UnicodeError as exc:
            raise ProviderBillingValidationError("canonical cost ledger is not valid UTF-8") from exc
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line, object_pairs_hook=_duplicate_guard)
                events.append(CostLedgerEvent.from_dict(data))
            except (ProviderBillingValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ProviderBillingValidationError("canonical cost ledger contains a malformed event") from exc
    normalized = _normalize_accounting_events(events)
    return BillingLedgerSnapshot(events=tuple(normalized), sha256=digest.hexdigest())


def locked_ledger_snapshot(ledger: CostLedger) -> BillingLedgerSnapshot:
    """Build a strict snapshot while holding the canonical ledger lock."""

    def snapshot(events: list[CostLedgerEvent]) -> BillingLedgerSnapshot:
        payload = [event.to_dict() for event in events]
        digest = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
        return BillingLedgerSnapshot(events=tuple(events), sha256=digest)

    return ledger.with_locked_accounting_events(snapshot)


def _event_ref(event: CostLedgerEvent, index: int) -> str:
    return event.idempotency_key or event.request_id or f"ledger-event-{index + 1}"


def _receipt_index(events: list[tuple[int, CostLedgerEvent]]) -> dict[tuple[str, str], set[int]]:
    index: dict[tuple[str, str], set[int]] = defaultdict(set)
    for event_index, event in events:
        metadata = event.metadata
        values = (
            ("provider_http_request_id", metadata.get("provider_http_request_id")),
            ("provider_object_id", metadata.get("provider_object_id")),
            ("provider_job_id", metadata.get("provider_job_id") or event.request_id),
            ("provider_request_id", metadata.get("provider_request_id") or event.request_id),
            ("client_correlation_id", metadata.get("client_correlation_id")),
        )
        for basis, raw in values:
            if isinstance(raw, str) and raw:
                index[(basis, raw)].add(event_index)
    return index


@dataclass(frozen=True)
class _ProviderLineGroups:
    grouped: dict[int, list[tuple[BillingLine, str, int]]]
    ambiguous: list[UnmatchedProviderLine]
    unmatched: list[UnmatchedProviderLine]
    positive_count: int
    credits_microusd: int
    capacity_net_microusd: dict[str, int]
    nonmetered_positive_count: int


def _group_provider_lines(
    lines: list[BillingLine],
    receipt_index: dict[tuple[str, str], set[int]],
) -> _ProviderLineGroups:
    grouped: dict[int, list[tuple[BillingLine, str, int]]] = defaultdict(list)
    ambiguous: list[UnmatchedProviderLine] = []
    unmatched: list[UnmatchedProviderLine] = []
    positive_count = 0
    credits = 0
    capacity_totals = {"api_metered": 0, "prepaid_plan": 0, "owned_local": 0, "unknown": 0}
    nonmetered_positive_count = 0
    for line in lines:
        net = _decimal_to_microusd(_money(line.net_usd, field_name="net_usd"))
        capacity_totals[line.capacity_class] += net
        if net <= 0:
            credits += abs(net)
            continue
        positive_count += 1
        if line.capacity_class in {"prepaid_plan", "owned_local"}:
            nonmetered_positive_count += 1
            continue
        if line.capacity_class == "unknown":
            unmatched.append(
                UnmatchedProviderLine(
                    line_id=line.line_id,
                    positive_microusd=net,
                    reason="unknown capacity class cannot be reconciled to metered API spend",
                )
            )
            continue
        matched_by_basis = [(basis, receipt_index.get((basis, value), set())) for basis, value in line.receipt_values()]
        candidates = set().union(*(matches for _basis, matches in matched_by_basis)) if matched_by_basis else set()
        identity_ambiguous = any(len(matches) > 1 for _basis, matches in matched_by_basis)
        bases = [basis for basis, matches in matched_by_basis if matches]
        if identity_ambiguous or len(candidates) > 1:
            ambiguous.append(
                UnmatchedProviderLine(
                    line_id=line.line_id, positive_microusd=net, reason="receipt identity is ambiguous"
                )
            )
        elif len(candidates) == 1:
            grouped[next(iter(candidates))].append((line, bases[0], net))
        else:
            unmatched.append(
                UnmatchedProviderLine(
                    line_id=line.line_id, positive_microusd=net, reason="no exact local receipt identity"
                )
            )
    return _ProviderLineGroups(
        grouped,
        ambiguous,
        unmatched,
        positive_count,
        credits,
        capacity_totals,
        nonmetered_positive_count,
    )


def _build_matches(
    groups: _ProviderLineGroups,
    relevant_by_index: dict[int, CostLedgerEvent],
) -> tuple[list[BillingMatch], set[int], int, int]:
    matches: list[BillingMatch] = []
    matched_event_indexes: set[int] = set()
    unexplained = sum(item.positive_microusd for item in groups.ambiguous) + sum(
        item.positive_microusd for item in groups.unmatched
    )
    local_overstatement = 0
    for event_index, line_group in sorted(groups.grouped.items()):
        event = relevant_by_index[event_index]
        provider_total = sum(item[2] for item in line_group)
        ledger_total = _float_to_microusd(event.cost_usd)
        matched_event_indexes.add(event_index)
        unexplained += max(0, provider_total - ledger_total)
        local_overstatement += max(0, ledger_total - provider_total)
        event_ref = _event_ref(event, event_index)
        matches.extend(
            BillingMatch(
                line_id=line.line_id,
                ledger_event_ref=event_ref,
                basis=basis,
                provider_microusd=amount,
                ledger_microusd=ledger_total,
            )
            for line, basis, amount in line_group
        )
    return matches, matched_event_indexes, unexplained, local_overstatement


def _reconciliation_status(
    document: ProviderBillingImport,
    *,
    ambiguous: bool,
    unexplained_microusd: int,
    unmatched_ledger: bool,
    untrusted_capacity_class: bool,
) -> Literal["clean", "drift", "ambiguous", "incomplete", "provisional", "unsupported_currency"]:
    if document.statement.currency != "USD":
        return "unsupported_currency"
    if document.statement.status != "final":
        return "provisional"
    if not document.statement.complete or not document.billing_scope.account_id:
        return "incomplete"
    if ambiguous:
        return "ambiguous"
    if unexplained_microusd:
        return "drift"
    if unmatched_ledger:
        return "incomplete"
    if untrusted_capacity_class:
        return "incomplete"
    return "clean"


def reconcile_billing(
    loaded: LoadedBillingImport,
    snapshot: BillingLedgerSnapshot,
    *,
    freeze_applied: bool = False,
) -> BillingReconciliation:
    """Compare one provider statement to exact local receipt identities."""
    document = loaded.document
    start = _parse_utc(document.statement.period_start, field_name="period_start")
    end = _parse_utc(document.statement.period_end, field_name="period_end")
    relevant = [
        (index, event)
        for index, event in enumerate(snapshot.events)
        if event.provider.strip().casefold() == document.provider
        and start <= event.timestamp <= end
        and event.cost_usd > 0
    ]
    receipt_index = _receipt_index(relevant)
    relevant_by_index = {index: event for index, event in relevant}
    groups = _group_provider_lines(document.lines, receipt_index)
    matches, matched_event_indexes, unexplained, local_overstatement = _build_matches(groups, relevant_by_index)

    unmatched_ledger = [
        UnmatchedLedgerEvent(
            ledger_event_ref=_event_ref(event, event_index),
            cost_microusd=_float_to_microusd(event.cost_usd),
            reason="local paid event has no provider statement line",
        )
        for event_index, event in relevant
        if event_index not in matched_event_indexes
    ]
    local_total = sum(_float_to_microusd(event.cost_usd) for _index, event in relevant)
    provider_total = _decimal_to_microusd(_money(document.statement.net_total_usd, field_name="net_total_usd"))
    status = _reconciliation_status(
        document,
        ambiguous=bool(groups.ambiguous),
        unexplained_microusd=unexplained,
        unmatched_ledger=bool(unmatched_ledger),
        untrusted_capacity_class=(
            document.statement.source_posture == "operator_normalized" and groups.nonmetered_positive_count > 0
        ),
    )

    return BillingReconciliation(
        schema_version=BILLING_RECONCILIATION_SCHEMA_VERSION,
        kind=BILLING_RECONCILIATION_KIND,
        source_sha256=loaded.source_sha256,
        normalized_sha256=loaded.normalized_sha256,
        ledger_snapshot_sha256=snapshot.sha256,
        provider=document.provider,
        scope_ref=document.billing_scope.scope_ref,
        account_id=document.billing_scope.account_id,
        statement_id=document.statement.statement_id,
        period_start=document.statement.period_start,
        period_end=document.statement.period_end,
        currency=document.statement.currency,
        statement_status=document.statement.status,
        statement_complete=document.statement.complete,
        statement_source_posture=document.statement.source_posture,
        status=status,
        provider_net_microusd=provider_total,
        api_metered_net_microusd=groups.capacity_net_microusd["api_metered"],
        prepaid_plan_net_microusd=groups.capacity_net_microusd["prepaid_plan"],
        owned_local_net_microusd=groups.capacity_net_microusd["owned_local"],
        unknown_net_microusd=groups.capacity_net_microusd["unknown"],
        local_ledger_microusd=local_total,
        net_drift_microusd=groups.capacity_net_microusd["api_metered"] - local_total,
        gross_unexplained_positive_microusd=unexplained,
        credits_and_negative_adjustments_microusd=groups.credits_microusd,
        local_overstatement_microusd=local_overstatement,
        match_counts=BillingMatchCounts(
            statement_lines=len(document.lines),
            positive_lines=groups.positive_count,
            matched_positive_lines=len(matches),
            ambiguous_positive_lines=len(groups.ambiguous),
            unmatched_positive_lines=len(groups.unmatched),
            local_positive_events=len(relevant),
            unmatched_local_events=len(unmatched_ledger),
        ),
        matches=matches,
        unmatched_provider_lines=[*groups.ambiguous, *groups.unmatched],
        unmatched_ledger_events=unmatched_ledger,
        authority_limitations=[
            "normalized input is not provider-authenticated evidence",
            "operator-normalized capacity classes do not prove that paid overage is disabled",
            "negative drift never restores spend authority",
            "reconciliation does not control calls made outside Deepr",
        ],
        freeze_required=status != "clean",
        freeze_applied=freeze_applied,
        zero_network_calls=True,
        zero_provider_calls=True,
    )


class BillingEvidenceStore:
    """Immutable storage for sanitized billing evidence and derived reports."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_cost_data_dir() / "provider_billing"

    @staticmethod
    def _store_once(path: Path, payload: bytes) -> None:
        if path.exists():
            try:
                if path.read_bytes() == payload:
                    return
            except OSError as exc:
                raise ProviderBillingStorageError("existing billing evidence is unreadable") from exc
            raise ProviderBillingStorageError("immutable billing evidence path contains different content")
        try:
            atomic_write_bytes(path, payload, fsync=True, overwrite=False)
        except FileExistsError:
            try:
                if path.read_bytes() == payload:
                    return
            except OSError as exc:
                raise ProviderBillingStorageError("billing evidence replay could not be verified") from exc
            raise ProviderBillingStorageError("immutable billing evidence path changed during creation") from None
        except OSError as exc:
            raise ProviderBillingStorageError("billing evidence could not be persisted durably") from exc

    def store(self, loaded: LoadedBillingImport, report: BillingReconciliation) -> tuple[Path, Path]:
        import_path = self.root / "imports" / f"{loaded.source_sha256}.json"
        report_path = self.root / "reconciliations" / f"{loaded.source_sha256}-{report.ledger_snapshot_sha256}.json"
        report_payload = _canonical_bytes(report)
        report_digest = hashlib.sha256(report_payload).hexdigest()
        digest_path = self.root / "reconciliations_by_hash" / f"{report_digest}.json"
        lock_path = self.root / ".lock"
        self.root.mkdir(parents=True, exist_ok=True)
        with FileLock(str(lock_path), timeout=10.0, thread_local=False):
            self._store_once(import_path, loaded.normalized_bytes + b"\n")
            self._store_once(report_path, report_payload + b"\n")
            self._store_once(digest_path, report_payload + b"\n")
        return import_path, report_path


def reconcile_billing_file(
    path: Path,
    *,
    apply: bool = False,
    expect_provider: str | None = None,
    expect_scope_ref: str | None = None,
    ledger_path: Path | None = None,
    store_root: Path | None = None,
    budget_path: Path | None = None,
) -> BillingReconciliation:
    """Preview or durably apply an offline billing reconciliation."""
    if not apply:
        loaded = load_billing_import(
            path,
            expect_provider=expect_provider,
            expect_scope_ref=expect_scope_ref,
        )
        return reconcile_billing(loaded, read_only_ledger_snapshot(ledger_path))

    from deepr.core.cost_caps import (
        _freeze_paid_api_unlocked,
        budget_file_path,
        spend_policy_lock,
    )

    target = budget_path or budget_file_path()
    frozen = False
    with spend_policy_lock(target):
        try:
            loaded = load_billing_import(
                path,
                expect_provider=expect_provider,
                expect_scope_ref=expect_scope_ref,
            )
            snapshot = locked_ledger_snapshot(CostLedger(ledger_path=ledger_path) if ledger_path else CostLedger())
            report = reconcile_billing(loaded, snapshot)
            if report.freeze_required:
                _freeze_paid_api_unlocked(
                    "provider billing reconciliation is not clean",
                    target=target,
                    kind="billing_divergence",
                    freeze_id=f"billing_{loaded.source_sha256[:32]}",
                )
                frozen = True
                report = report.model_copy(update={"freeze_applied": True})
            BillingEvidenceStore(store_root).store(loaded, report)
            return report
        except Exception as exc:
            if not frozen:
                kind = (
                    "account_identity_mismatch"
                    if isinstance(exc, ProviderBillingValidationError)
                    and ("expected provider" in str(exc) or "expected scope" in str(exc))
                    else "billing_evidence_storage_failure"
                )
                _freeze_paid_api_unlocked(
                    "provider billing reconciliation could not be proven complete",
                    target=target,
                    kind=kind,
                )
            raise


__all__ = [
    "BILLING_IMPORT_KIND",
    "BILLING_IMPORT_SCHEMA_VERSION",
    "BILLING_RECONCILIATION_KIND",
    "BILLING_RECONCILIATION_SCHEMA_VERSION",
    "BillingEvidenceStore",
    "BillingLedgerSnapshot",
    "BillingReconciliation",
    "LoadedBillingImport",
    "ProviderBillingError",
    "ProviderBillingImport",
    "ProviderBillingStorageError",
    "ProviderBillingValidationError",
    "load_billing_import",
    "locked_ledger_snapshot",
    "read_only_ledger_snapshot",
    "reconcile_billing",
    "reconcile_billing_file",
]
