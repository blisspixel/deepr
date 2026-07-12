"""Validated derived attribution for append-only cost-ledger events."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

from deepr.observability.cost_ledger import CostLedgerEvent

ATTRIBUTION_RECONCILIATION_SCHEMA = "deepr-cost-attribution-reconciliation-v1"
_RECONCILIATION_OPERATION = "cost_accounting_reconciliation"
_CORRECTION_TYPE = "attribution_metadata"


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _text(value: Any, *, allow_empty: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    if not allow_empty and not value:
        return None
    return value


@dataclass(frozen=True)
class _AttributionCorrection:
    target_key: str
    original_model: str
    routed_model: str
    original_provider: str | None
    routed_provider: str
    conservative_ceiling: float

    @classmethod
    def parse(cls, event: CostLedgerEvent) -> _AttributionCorrection | None:
        """Parse one reconciliation event, rejecting malformed metadata."""
        if event.operation != _RECONCILIATION_OPERATION:
            return None
        event_cost = _finite_number(event.cost_usd)
        if event_cost != 0.0 or event.tokens_input != 0 or event.tokens_output != 0:
            return None
        if _text(event.idempotency_key) is None or _text(event.provider) is None:
            return None
        routed_model = _text(event.model)
        metadata = event.metadata
        if routed_model is None or not isinstance(metadata, dict):
            return None

        schema = metadata.get("schema_version")
        # The first live correction predates the explicit version field. Its
        # complete metadata shape is parsed under this same v1 contract.
        if schema is not None and schema != ATTRIBUTION_RECONCILIATION_SCHEMA:
            return None
        if metadata.get("correction_type") != _CORRECTION_TYPE:
            return None
        target_key = _text(metadata.get("supersedes_idempotency_key"))
        original_model = _text(metadata.get("original_model_attribution"), allow_empty=True)
        declared_routed_model = _text(metadata.get("routed_model_attribution"))
        ceiling = _finite_number(metadata.get("conservative_ceiling_charge_usd"))
        adjustment = _finite_number(metadata.get("total_adjustment_usd"))
        if (
            target_key is None
            or target_key == event.idempotency_key
            or original_model is None
            or declared_routed_model != routed_model
            or ceiling is None
            or ceiling < 0.0
            or adjustment != 0.0
            or metadata.get("actual_cost_reported") is not False
            or _text(metadata.get("settlement_basis")) is None
            or _text(metadata.get("observed_outcome")) is None
        ):
            return None

        original_provider = metadata.get("original_provider_attribution")
        declared_routed_provider = metadata.get("routed_provider_attribution")
        if original_provider is None and declared_routed_provider is None:
            parsed_original_provider = None
        else:
            parsed_original_provider = _text(original_provider)
            if parsed_original_provider is None or _text(declared_routed_provider) != event.provider:
                return None

        return cls(
            target_key=target_key,
            original_model=original_model,
            routed_model=routed_model,
            original_provider=parsed_original_provider,
            routed_provider=event.provider,
            conservative_ceiling=ceiling,
        )

    def applies_to(self, target: CostLedgerEvent, correction: CostLedgerEvent) -> bool:
        """Return whether the parsed correction exactly describes its target."""
        target_cost = _finite_number(target.cost_usd)
        if (
            target.operation == _RECONCILIATION_OPERATION
            or target_cost is None
            or not math.isclose(target_cost, self.conservative_ceiling, rel_tol=0.0, abs_tol=1e-12)
            or target.model != self.original_model
            or target.task_id != correction.task_id
            or target.session_id != correction.session_id
        ):
            return False
        if self.original_provider is None:
            return target.provider == self.routed_provider
        return target.provider == self.original_provider


def _index_cost_events(events: list[CostLedgerEvent]) -> tuple[dict[str, list[int]], set[int]]:
    key_indices: dict[str, list[int]] = {}
    bookkeeping_indices: set[int] = set()
    for index, event in enumerate(events):
        if event.idempotency_key:
            key_indices.setdefault(event.idempotency_key, []).append(index)
        if event.operation == _RECONCILIATION_OPERATION and _finite_number(event.cost_usd) == 0.0:
            bookkeeping_indices.add(index)
    return key_indices, bookkeeping_indices


def _collect_attribution_corrections(
    events: list[CostLedgerEvent],
    key_indices: dict[str, list[int]],
) -> dict[int, list[tuple[_AttributionCorrection, CostLedgerEvent]]]:
    corrections: dict[int, list[tuple[_AttributionCorrection, CostLedgerEvent]]] = {}
    for correction_index, event in enumerate(events):
        correction = _AttributionCorrection.parse(event)
        if correction is None:
            continue
        target_indices = key_indices.get(correction.target_key, [])
        if len(target_indices) != 1 or target_indices[0] >= correction_index:
            continue
        target_index = target_indices[0]
        if correction.applies_to(events[target_index], event):
            corrections.setdefault(target_index, []).append((correction, event))
    return corrections


def project_cost_attribution(events: list[CostLedgerEvent]) -> list[CostLedgerEvent]:
    """Return charge events with validated provider/model corrections applied.

    The input remains untouched. Zero-dollar reconciliation records remain in
    the canonical ledger but are omitted from this provider/model attribution
    view so they do not inflate request counts. A target is changed only when
    exactly one valid correction names one unique earlier idempotency key.
    """
    key_indices, bookkeeping_indices = _index_cost_events(events)
    corrections = _collect_attribution_corrections(events, key_indices)

    projected: list[CostLedgerEvent] = []
    for index, event in enumerate(events):
        if index in bookkeeping_indices:
            continue
        candidates = corrections.get(index, [])
        if len(candidates) == 1:
            correction, _correction_event = candidates[0]
            event = replace(event, provider=correction.routed_provider, model=correction.routed_model)
        projected.append(event)
    return projected


__all__ = ["ATTRIBUTION_RECONCILIATION_SCHEMA", "project_cost_attribution"]
