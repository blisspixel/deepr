"""Published-output contract guards for MCP host-facing payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deepr.experts.handoff import HANDOFF_KIND, HANDOFF_SCHEMA_VERSION
from deepr.experts.loop_status_rollup import LOOP_STATUS_SCHEMA_VERSION

LOOP_STATUS_KIND = "deepr.expert.loop_status"


@dataclass(frozen=True)
class PublishedOutputContract:
    """Deterministic envelope checks for a published JSON contract."""

    name: str
    schema_version: str
    kind: str
    required_fields: tuple[str, ...]


EXPERT_HANDOFF_OUTPUT_CONTRACT = PublishedOutputContract(
    name="expert-handoff-v1",
    schema_version=HANDOFF_SCHEMA_VERSION,
    kind=HANDOFF_KIND,
    required_fields=(
        "schema_version",
        "kind",
        "generated_at",
        "contract",
        "expert",
        "summary",
        "manifest",
        "expert_state",
        "loop_status",
        "okf",
        "recommended_mcp_tools",
    ),
)

LOOP_STATUS_OUTPUT_CONTRACT = PublishedOutputContract(
    name="loop-status-v1",
    schema_version=LOOP_STATUS_SCHEMA_VERSION,
    kind=LOOP_STATUS_KIND,
    required_fields=(
        "schema_version",
        "kind",
        "contract",
        "expert_name",
        "count",
        "window",
        "latest_run",
        "last_sync_result",
        "last_failure",
        "next_scheduled_action",
        "latest_capacity_source",
        "status_counts",
        "loop_type_counts",
        "stop_reason_counts",
        "capacity_source_counts",
        "budget_spent_total",
        "accepted_changes_total",
        "rejected_changes_total",
        "acceptance_rate",
        "cost_per_accepted_change",
        "verifier_failure_count",
        "admission_contracts",
        "runs",
    ),
)


def validate_published_output(payload: dict[str, Any], contract: PublishedOutputContract) -> list[str]:
    """Return deterministic schema-envelope failures for a host-facing payload."""
    errors: list[str] = []
    if payload.get("schema_version") != contract.schema_version:
        errors.append(f"schema_version must be {contract.schema_version!r}, got {payload.get('schema_version')!r}")
    if payload.get("kind") != contract.kind:
        errors.append(f"kind must be {contract.kind!r}, got {payload.get('kind')!r}")
    missing = [field for field in contract.required_fields if field not in payload]
    if missing:
        errors.append(f"missing required field(s): {', '.join(missing)}")
    return errors


def schema_validation_error(contract: PublishedOutputContract, errors: list[str]) -> dict[str, Any]:
    """Return a tool-error payload for a malformed published output contract."""
    return {
        "error_code": "SCHEMA_VALIDATION_FAILED",
        "message": f"{contract.name} payload failed published contract validation",
        "schema_version": contract.schema_version,
        "kind": contract.kind,
        "schema_errors": errors,
    }
