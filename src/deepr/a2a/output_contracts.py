"""Published-output contract guards for A2A host-facing payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deepr.a2a.models import A2A_TASK_KIND, A2A_TASK_SCHEMA_VERSION, TaskState


@dataclass(frozen=True)
class PublishedA2AOutputContract:
    """Deterministic envelope checks for a published A2A JSON contract."""

    name: str
    schema_version: str
    kind: str
    required_fields: tuple[str, ...]


A2A_TASK_OUTPUT_CONTRACT = PublishedA2AOutputContract(
    name="a2a-task-v1",
    schema_version=A2A_TASK_SCHEMA_VERSION,
    kind=A2A_TASK_KIND,
    required_fields=(
        "schema_version",
        "kind",
        "contract",
        "id",
        "state",
        "skill",
        "input",
        "result",
        "error",
        "cost",
        "trace_id",
        "created_at",
        "updated_at",
        "metadata",
    ),
)


def validate_a2a_output(payload: dict[str, Any], contract: PublishedA2AOutputContract) -> list[str]:
    """Return deterministic schema-envelope failures for an A2A payload."""
    errors: list[str] = []
    if payload.get("schema_version") != contract.schema_version:
        errors.append(f"schema_version must be {contract.schema_version!r}, got {payload.get('schema_version')!r}")
    if payload.get("kind") != contract.kind:
        errors.append(f"kind must be {contract.kind!r}, got {payload.get('kind')!r}")
    missing = [field for field in contract.required_fields if field not in payload]
    if missing:
        errors.append(f"missing required field(s): {', '.join(missing)}")

    state = payload.get("state")
    valid_states = {item.value for item in TaskState}
    if state not in valid_states:
        errors.append(f"state must be one of {sorted(valid_states)!r}, got {state!r}")

    cost = payload.get("cost")
    if isinstance(cost, bool) or not isinstance(cost, int | float) or cost < 0:
        errors.append(f"cost must be a non-negative number, got {cost!r}")

    for field in ("id", "skill", "input", "trace_id", "created_at", "updated_at"):
        if not isinstance(payload.get(field), str):
            errors.append(f"{field} must be a string, got {type(payload.get(field)).__name__}")
    for field in ("contract", "metadata"):
        if not isinstance(payload.get(field), dict):
            errors.append(f"{field} must be an object, got {type(payload.get(field)).__name__}")
    return errors


def schema_validation_error(contract: PublishedA2AOutputContract, errors: list[str]) -> dict[str, Any]:
    """Return an error payload for a malformed published A2A output contract."""
    return {
        "error_code": "SCHEMA_VALIDATION_FAILED",
        "message": f"{contract.name} payload failed published contract validation",
        "schema_version": contract.schema_version,
        "kind": contract.kind,
        "schema_errors": errors,
    }
