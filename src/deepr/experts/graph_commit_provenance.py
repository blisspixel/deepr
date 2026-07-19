"""Producer-owned provenance checks for durable graph commit writes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from deepr.utils.atomic_io import atomic_write_json

GRAPH_COMMIT_RECEIPT_SCHEMA_VERSION = "deepr-graph-commit-receipt-v1"
GRAPH_COMMIT_RECEIPT_KIND = "deepr.expert.graph_commit_receipt"
_MAX_ARTIFACT_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class GraphCommitProvenanceCheck:
    """Result of binding an envelope to producer-owned durable state."""

    valid: bool
    source: str
    failure_reasons: tuple[str, ...] = ()


class GraphCommitProvenanceError(RuntimeError):
    """Raised when a producer cannot durably bind its graph commit artifacts."""


@dataclass(frozen=True)
class _InvestigationBindings:
    persisted_envelope: dict[str, Any]
    plan: dict[str, Any]
    run_state: str
    extraction_reference: dict[str, Any]
    verification_reference: dict[str, Any]


@dataclass(frozen=True)
class _InvestigationPerspectiveBindings:
    persisted_envelope: dict[str, Any]
    persisted_position: dict[str, Any]
    plan: dict[str, Any]
    run_state: str
    position_reference: dict[str, Any]
    check_reference: dict[str, Any]


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GraphCommitProvenanceError("graph commit artifact is not canonical JSON") from exc


def graph_commit_payload_sha256(payload: dict[str, Any]) -> str:
    """Hash a JSON object with the canonical graph-commit representation."""
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _safe_relative(value: str, *, label: str) -> Path:
    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts or any(not part for part in path.parts):
        raise GraphCommitProvenanceError(f"invalid {label} artifact path")
    if ":" in path.parts[0]:
        raise GraphCommitProvenanceError(f"invalid {label} artifact path")
    return Path(*path.parts)


def _confined_path(root: Path, relative: Path, *, label: str) -> Path:
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise GraphCommitProvenanceError(f"{label} artifact escapes its trusted root") from exc
    return resolved


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        size = path.stat().st_size
        if size > _MAX_ARTIFACT_BYTES:
            raise GraphCommitProvenanceError(f"{label} artifact exceeds the byte ceiling")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except GraphCommitProvenanceError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphCommitProvenanceError(f"could not read trusted {label} artifact") from exc
    if not isinstance(payload, dict):
        raise GraphCommitProvenanceError(f"trusted {label} artifact is not an object")
    return payload


def _receipt_relative_path(envelope_artifact: str) -> Path:
    relative = _safe_relative(envelope_artifact, label="envelope")
    parts = relative.parts
    if len(parts) != 3 or parts[:2] != ("sync_artifacts", "graph_commit_envelopes"):
        raise GraphCommitProvenanceError("sync envelope is outside the producer-owned envelope directory")
    return Path("sync_artifacts") / "graph_commit_receipts" / parts[-1]


def _artifact_binding(path: str, payload: dict[str, Any]) -> dict[str, str]:
    return {"path": path, "sha256": graph_commit_payload_sha256(payload)}


def write_sync_graph_commit_receipt(
    expert_root: Path,
    *,
    envelope_artifact: str,
    envelope: dict[str, Any],
    claim_extraction: dict[str, Any],
    claim_verification: dict[str, Any],
) -> str:
    """Bind one persisted sync envelope to its exact compiler artifacts."""
    root = expert_root.resolve()
    envelope_relative = _safe_relative(envelope_artifact, label="envelope")
    receipt_relative = _receipt_relative_path(envelope_artifact)
    input_payload = envelope.get("input")
    target = envelope.get("target")
    if not isinstance(input_payload, dict) or not isinstance(target, dict):
        raise GraphCommitProvenanceError("graph commit envelope input or target is invalid")
    expert_name = str(target.get("expert_name", "") or "").strip()
    if not expert_name:
        raise GraphCommitProvenanceError("graph commit envelope target is required")
    extraction_ref = str(input_payload.get("claim_extraction_artifact", "") or "")
    verification_ref = str(input_payload.get("claim_verification_artifact", "") or "")
    extraction_relative = _safe_relative(extraction_ref, label="claim extraction")
    verification_relative = _safe_relative(verification_ref, label="claim verification")

    persisted = {
        "envelope": _read_json(_confined_path(root, envelope_relative, label="envelope"), label="envelope"),
        "claim_extraction": _read_json(
            _confined_path(root, extraction_relative, label="claim extraction"),
            label="claim extraction",
        ),
        "claim_verification": _read_json(
            _confined_path(root, verification_relative, label="claim verification"),
            label="claim verification",
        ),
    }
    expected = {
        "envelope": envelope,
        "claim_extraction": claim_extraction,
        "claim_verification": claim_verification,
    }
    if any(
        graph_commit_payload_sha256(persisted[key]) != graph_commit_payload_sha256(value)
        for key, value in expected.items()
    ):
        raise GraphCommitProvenanceError("persisted graph commit artifacts differ from producer output")

    receipt = {
        "schema_version": GRAPH_COMMIT_RECEIPT_SCHEMA_VERSION,
        "kind": GRAPH_COMMIT_RECEIPT_KIND,
        "target": {"expert_name": expert_name},
        "artifacts": {
            "envelope": _artifact_binding(envelope_relative.as_posix(), envelope),
            "claim_extraction": _artifact_binding(extraction_ref, claim_extraction),
            "claim_verification": _artifact_binding(verification_ref, claim_verification),
        },
        "producer": {
            "stage": "graph_commit_envelope",
            "authority": "sync_compiler",
            "self_declared_envelope_is_not_authority": True,
        },
        "generated_at": str(envelope.get("generated_at", "") or ""),
    }
    receipt_path = _confined_path(root, receipt_relative, label="receipt")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if receipt_path.exists():
        existing = _read_json(receipt_path, label="receipt")
        if graph_commit_payload_sha256(existing) != graph_commit_payload_sha256(receipt):
            raise GraphCommitProvenanceError("graph commit receipt idempotency conflict")
    else:
        atomic_write_json(receipt_path, receipt, sort_keys=True, fsync=True)
    return receipt_relative.as_posix()


def persist_sync_graph_commit_envelope(
    expert_root: Path,
    *,
    envelope_artifact: str,
    envelope: dict[str, Any],
    claim_extraction: dict[str, Any],
    claim_verification: dict[str, Any],
) -> str:
    """Persist a sync envelope and its producer receipt as one owned step."""
    root = expert_root.resolve()
    relative = _safe_relative(envelope_artifact, label="envelope")
    _receipt_relative_path(envelope_artifact)
    path = _confined_path(root, relative, label="envelope")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        atomic_write_json(path, envelope)
    except OSError as exc:
        raise GraphCommitProvenanceError("graph commit envelope artifact write failed") from exc
    write_sync_graph_commit_receipt(
        root,
        envelope_artifact=relative.as_posix(),
        envelope=envelope,
        claim_extraction=claim_extraction,
        claim_verification=claim_verification,
    )
    return relative.as_posix()


def _check_sync_artifact(
    root: Path,
    binding: Any,
    *,
    expected_path: str,
    label: str,
) -> list[str]:
    if not isinstance(binding, dict) or binding.get("path") != expected_path:
        return [f"{label}_receipt_binding_mismatch"]
    try:
        relative = _safe_relative(expected_path, label=label)
        payload = _read_json(_confined_path(root, relative, label=label), label=label)
    except GraphCommitProvenanceError:
        return [f"{label}_artifact_untrusted"]
    if binding.get("sha256") != graph_commit_payload_sha256(payload):
        return [f"{label}_artifact_hash_mismatch"]
    return []


def verify_sync_graph_commit_provenance(
    expert_root: Path,
    *,
    envelope_path: Path,
    envelope: dict[str, Any],
    expected_expert: str,
) -> GraphCommitProvenanceCheck:
    """Verify a sync envelope against its producer-owned receipt and files."""
    reasons: list[str] = []
    root = expert_root.resolve()
    try:
        relative = envelope_path.resolve().relative_to(root)
        relative_text = relative.as_posix()
        receipt_relative = _receipt_relative_path(relative_text)
        persisted_envelope = _read_json(envelope_path.resolve(), label="envelope")
        receipt = _read_json(_confined_path(root, receipt_relative, label="receipt"), label="receipt")
    except (ValueError, GraphCommitProvenanceError):
        return GraphCommitProvenanceCheck(False, "sync_receipt", ("graph_commit_receipt_missing_or_untrusted",))

    if graph_commit_payload_sha256(persisted_envelope) != graph_commit_payload_sha256(envelope):
        reasons.append("envelope_file_payload_mismatch")
    if (
        receipt.get("schema_version") != GRAPH_COMMIT_RECEIPT_SCHEMA_VERSION
        or receipt.get("kind") != GRAPH_COMMIT_RECEIPT_KIND
    ):
        reasons.append("unsupported_graph_commit_receipt")
    target = receipt.get("target")
    if not isinstance(target, dict) or str(target.get("expert_name", "") or "").strip() != expected_expert:
        reasons.append("receipt_target_expert_mismatch")
    envelope_target = envelope.get("target")
    if (
        not isinstance(envelope_target, dict)
        or str(envelope_target.get("expert_name", "") or "").strip() != expected_expert
    ):
        reasons.append("target_expert_mismatch")
    artifacts = receipt.get("artifacts")
    input_payload = envelope.get("input")
    if not isinstance(artifacts, dict) or not isinstance(input_payload, dict):
        reasons.append("invalid_graph_commit_receipt_bindings")
    else:
        reasons.extend(
            _check_sync_artifact(root, artifacts.get("envelope"), expected_path=relative_text, label="envelope")
        )
        extraction_ref = str(input_payload.get("claim_extraction_artifact", "") or "")
        verification_ref = str(input_payload.get("claim_verification_artifact", "") or "")
        reasons.extend(
            _check_sync_artifact(
                root,
                artifacts.get("claim_extraction"),
                expected_path=extraction_ref,
                label="claim_extraction",
            )
        )
        reasons.extend(
            _check_sync_artifact(
                root,
                artifacts.get("claim_verification"),
                expected_path=verification_ref,
                label="claim_verification",
            )
        )
    return GraphCommitProvenanceCheck(not reasons, "sync_receipt", tuple(sorted(set(reasons))))


def require_sync_graph_commit_provenance(
    expert_root: Path,
    *,
    envelope_artifact: str,
    envelope: dict[str, Any],
    expected_expert: str,
) -> None:
    """Raise with stable reasons unless a sync receipt authorizes the write."""
    check = verify_sync_graph_commit_provenance(
        expert_root,
        envelope_path=expert_root / _safe_relative(envelope_artifact, label="envelope"),
        envelope=envelope,
        expected_expert=expected_expert,
    )
    if not check.valid:
        reasons = ", ".join(check.failure_reasons) or "untrusted producer state"
        raise GraphCommitProvenanceError(f"graph commit provenance check failed ({reasons})")


def _matching_envelope_key(
    artifacts: dict[str, Any],
    artifact_path: str,
    *,
    prefix: str = "learning:envelope:",
) -> str:
    matches = [
        key
        for key, reference in artifacts.items()
        if key.startswith(prefix) and isinstance(reference, dict) and reference.get("path") == artifact_path
    ]
    if len(matches) != 1:
        raise GraphCommitProvenanceError("envelope is not bound to one learning artifact")
    return matches[0]


def _required_run_reference(artifacts: dict[str, Any], logical_key: str) -> dict[str, Any]:
    reference = artifacts.get(logical_key)
    if not isinstance(reference, dict):
        raise GraphCommitProvenanceError("learning compiler artifact is missing")
    return reference


def _load_investigation_bindings(envelope_path: Path) -> _InvestigationBindings:
    from deepr.experts.investigation.store import InvestigationStore

    store = InvestigationStore()
    relative = envelope_path.resolve().relative_to(store.root.resolve())
    run_id, *artifact_parts = relative.parts
    if not artifact_parts:
        raise GraphCommitProvenanceError("invalid investigation envelope path")
    artifact_path = Path(*artifact_parts).as_posix()
    state = store.load_state(run_id)
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        raise GraphCommitProvenanceError("investigation artifact index is invalid")
    envelope_key = _matching_envelope_key(artifacts, artifact_path)
    suffix = envelope_key.removeprefix("learning:envelope:")
    envelope_reference = _required_run_reference(artifacts, envelope_key)
    extraction_reference = _required_run_reference(artifacts, f"learning:extraction:{suffix}")
    verification_reference = _required_run_reference(artifacts, f"learning:verification:{suffix}")
    persisted = store.read_artifact(run_id, envelope_reference)
    store.read_artifact(run_id, extraction_reference)
    store.read_artifact(run_id, verification_reference)
    return _InvestigationBindings(
        persisted_envelope=persisted,
        plan=store.load_plan(run_id),
        run_state=str(state.get("state", "") or ""),
        extraction_reference=extraction_reference,
        verification_reference=verification_reference,
    )


def _load_investigation_perspective_bindings(
    envelope_path: Path,
) -> _InvestigationPerspectiveBindings:
    from deepr.experts.investigation.store import InvestigationStore

    store = InvestigationStore()
    relative = envelope_path.resolve().relative_to(store.root.resolve())
    run_id, *artifact_parts = relative.parts
    if not artifact_parts:
        raise GraphCommitProvenanceError("invalid investigation perspective envelope path")
    artifact_path = Path(*artifact_parts).as_posix()
    state = store.load_state(run_id)
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        raise GraphCommitProvenanceError("investigation artifact index is invalid")
    envelope_key = _matching_envelope_key(
        artifacts,
        artifact_path,
        prefix="learning:perspective-envelope:",
    )
    suffix = envelope_key.removeprefix("learning:perspective-envelope:")
    envelope_reference = _required_run_reference(artifacts, envelope_key)
    check_reference = _required_run_reference(artifacts, "check")
    position_candidates = [
        _required_run_reference(artifacts, key)
        for key in (f"revision:{suffix}", f"position:{suffix}")
        if isinstance(artifacts.get(key), dict)
    ]
    if len(position_candidates) not in {1, 2}:
        raise GraphCommitProvenanceError("investigation perspective position artifact is missing")
    persisted_envelope = store.read_artifact(run_id, envelope_reference)
    input_payload = persisted_envelope.get("input")
    if not isinstance(input_payload, dict):
        raise GraphCommitProvenanceError("investigation perspective envelope input is invalid")
    position_path = str(input_payload.get("position_artifact", "") or "")
    matching_positions = [reference for reference in position_candidates if reference.get("path") == position_path]
    if len(matching_positions) != 1:
        raise GraphCommitProvenanceError("investigation perspective position binding is ambiguous")
    position_reference = matching_positions[0]
    persisted_position = store.read_artifact(run_id, position_reference)
    store.read_artifact(run_id, check_reference)
    return _InvestigationPerspectiveBindings(
        persisted_envelope=persisted_envelope,
        persisted_position=persisted_position,
        plan=store.load_plan(run_id),
        run_state=str(state.get("state", "") or ""),
        position_reference=position_reference,
        check_reference=check_reference,
    )


def _plan_expert_names(plan: dict[str, Any]) -> set[str]:
    plan_experts = plan.get("experts")
    if not isinstance(plan_experts, list):
        return set()
    return {str(item.get("name", "") or "").strip() for item in plan_experts if isinstance(item, dict)}


def verify_investigation_graph_commit_provenance(
    *,
    envelope_path: Path,
    envelope: dict[str, Any],
    expected_expert: str,
) -> GraphCommitProvenanceCheck:
    """Verify an investigation envelope against its hash-bound run index."""
    from deepr.experts.investigation.store import InvestigationStorageError

    try:
        bindings = _load_investigation_bindings(envelope_path)
    except (ValueError, GraphCommitProvenanceError, InvestigationStorageError):
        return GraphCommitProvenanceCheck(False, "investigation_run", ("investigation_run_provenance_untrusted",))

    reasons: list[str] = []
    if bindings.run_state != "completed":
        reasons.append("investigation_run_not_completed")
    if graph_commit_payload_sha256(bindings.persisted_envelope) != graph_commit_payload_sha256(envelope):
        reasons.append("envelope_file_payload_mismatch")
    input_payload = envelope.get("input")
    if not isinstance(input_payload, dict):
        reasons.append("invalid_envelope_input")
    else:
        if input_payload.get("claim_extraction_artifact") != bindings.extraction_reference.get("path"):
            reasons.append("claim_extraction_run_binding_mismatch")
        if input_payload.get("claim_verification_artifact") != bindings.verification_reference.get("path"):
            reasons.append("claim_verification_run_binding_mismatch")
    target = envelope.get("target")
    if not isinstance(target, dict) or str(target.get("expert_name", "") or "").strip() != expected_expert:
        reasons.append("target_expert_mismatch")
    if expected_expert not in _plan_expert_names(bindings.plan):
        reasons.append("target_not_in_investigation_plan")
    return GraphCommitProvenanceCheck(not reasons, "investigation_run", tuple(sorted(set(reasons))))


def _perspective_provenance_reasons(
    bindings: _InvestigationPerspectiveBindings,
    envelope: dict[str, Any],
    expected_expert: str,
) -> list[str]:
    """Collect exact run, target, and operation binding failures."""
    reasons: list[str] = []
    if bindings.run_state != "completed":
        reasons.append("investigation_run_not_completed")
    if graph_commit_payload_sha256(bindings.persisted_envelope) != graph_commit_payload_sha256(envelope):
        reasons.append("envelope_file_payload_mismatch")
    input_payload = envelope.get("input")
    if not isinstance(input_payload, dict):
        reasons.append("invalid_envelope_input")
    else:
        if input_payload.get("position_artifact") != bindings.position_reference.get("path"):
            reasons.append("position_run_binding_mismatch")
        if input_payload.get("check_artifact") != bindings.check_reference.get("path"):
            reasons.append("check_run_binding_mismatch")
    target = envelope.get("target")
    if not isinstance(target, dict) or str(target.get("expert_name", "") or "").strip() != expected_expert:
        reasons.append("target_expert_mismatch")
    if str(bindings.persisted_position.get("expert_name", "") or "").strip() != expected_expert:
        reasons.append("position_expert_mismatch")
    if expected_expert not in _plan_expert_names(bindings.plan):
        reasons.append("target_not_in_investigation_plan")
    if not _perspective_operations_only(envelope.get("operations")):
        reasons.append("perspective_envelope_contains_non_perspective_operation")
    return reasons


def _perspective_operations_only(operations: Any) -> bool:
    allowed = {
        "promote_hypothesis",
        "promote_concept",
        "promote_stance",
        "promote_original_idea",
    }
    return isinstance(operations, list) and all(
        isinstance(operation, dict) and operation.get("operation") in allowed for operation in operations
    )


def verify_investigation_perspective_provenance(
    *,
    envelope_path: Path,
    envelope: dict[str, Any],
    expected_expert: str,
) -> GraphCommitProvenanceCheck:
    """Verify a perspective envelope against its completed investigation run."""
    from deepr.experts.investigation.store import InvestigationStorageError

    try:
        bindings = _load_investigation_perspective_bindings(envelope_path)
    except (ValueError, GraphCommitProvenanceError, InvestigationStorageError):
        return GraphCommitProvenanceCheck(
            False,
            "investigation_perspective_run",
            ("investigation_perspective_provenance_untrusted",),
        )

    reasons = _perspective_provenance_reasons(bindings, envelope, expected_expert)
    return GraphCommitProvenanceCheck(
        not reasons,
        "investigation_perspective_run",
        tuple(sorted(set(reasons))),
    )


def verify_graph_commit_provenance(
    expert_root: Path,
    *,
    envelope_path: Path,
    envelope: dict[str, Any],
    expected_expert: str,
) -> GraphCommitProvenanceCheck:
    """Verify a graph commit against the applicable trusted producer state."""
    try:
        envelope_path.resolve().relative_to(expert_root.resolve())
    except ValueError:
        input_payload = envelope.get("input")
        if isinstance(input_payload, dict) and "position_artifact" in input_payload:
            return verify_investigation_perspective_provenance(
                envelope_path=envelope_path,
                envelope=envelope,
                expected_expert=expected_expert,
            )
        return verify_investigation_graph_commit_provenance(
            envelope_path=envelope_path,
            envelope=envelope,
            expected_expert=expected_expert,
        )
    return verify_sync_graph_commit_provenance(
        expert_root,
        envelope_path=envelope_path,
        envelope=envelope,
        expected_expert=expected_expert,
    )


__all__ = [
    "GRAPH_COMMIT_RECEIPT_KIND",
    "GRAPH_COMMIT_RECEIPT_SCHEMA_VERSION",
    "GraphCommitProvenanceCheck",
    "GraphCommitProvenanceError",
    "graph_commit_payload_sha256",
    "persist_sync_graph_commit_envelope",
    "require_sync_graph_commit_provenance",
    "verify_graph_commit_provenance",
    "verify_investigation_graph_commit_provenance",
    "verify_investigation_perspective_provenance",
    "verify_sync_graph_commit_provenance",
    "write_sync_graph_commit_receipt",
]
