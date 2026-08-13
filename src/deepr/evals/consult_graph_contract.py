"""Pure contracts for the eval-only local structured consult graph.

This module owns graph shape, immutable expert snapshots, hashes, and resource
preflight. It performs no model calls and writes no state.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from deepr.backends.capacity import validate_owned_local_ollama_url

STRUCTURED_CONSULT_BRIEF_SCHEMA_VERSION = "deepr-structured-consult-brief-v1"
STRUCTURED_CONSULT_BRIEF_KIND = "deepr.eval.structured_consult_brief"
STRUCTURED_CONSULT_POSITION_SCHEMA_VERSION = "deepr-structured-consult-position-v1"
STRUCTURED_CONSULT_POSITION_KIND = "deepr.eval.structured_consult_position"
STRUCTURED_CONSULT_SYNTHESIS_SCHEMA_VERSION = "deepr-structured-consult-synthesis-v1"
STRUCTURED_CONSULT_SYNTHESIS_KIND = "deepr.eval.structured_consult_synthesis"
STRUCTURED_CONSULT_RUN_SCHEMA_VERSION = "deepr-structured-consult-run-v1"
STRUCTURED_CONSULT_RUN_KIND = "deepr.eval.structured_consult_run"

POSITION_MODEL_OUTPUT_FIELDS = (
    "answer",
    "abstained",
    "evidence_claims",
    "assumptions",
    "unknowns",
    "uncertainty",
    "alternative",
    "disconfirming_test",
    "decision_implications",
)
SYNTHESIS_MODEL_OUTPUT_FIELDS = (
    "answer",
    "agreements",
    "disagreements",
    "uncertainty",
    "next_tests",
)

MAX_POSITION_NODES = 10
MAX_LOCAL_CONCURRENCY = 4
MAX_QUESTION_BYTES = 16_384
MAX_SNAPSHOT_BYTES = 65_536
DEFAULT_POSITION_OUTPUT_TOKENS = 700
DEFAULT_SYNTHESIS_OUTPUT_TOKENS = 900
DEFAULT_INPUT_TOKEN_CEILING = 262_144
DEFAULT_CONTEXT_BYTE_CEILING = 262_144
DEFAULT_ARTIFACT_BYTE_CEILING = 131_072
DEFAULT_NODE_ELAPSED_SECONDS = 900.0
DEFAULT_RUN_ELAPSED_SECONDS = 3_600.0
_BRIEF_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "graph_id",
        "question",
        "question_hash",
        "prompt_version",
        "protocol_version",
        "capacity",
        "authority",
        "limits",
        "snapshots",
        "nodes",
        "expected",
        "brief_hash",
    }
)
_NODE_FIELDS = frozenset(
    {
        "node_id",
        "node_kind",
        "depends_on",
        "input_artifact_ids",
        "expert_name",
        "snapshot_hash",
        "mutable_resources",
        "max_attempts",
        "max_output_tokens",
        "max_elapsed_seconds",
    }
)


def _model_string_schema(*, allow_empty: bool = False) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string", "maxLength": 16_384}
    if not allow_empty:
        schema["minLength"] = 1
    return schema


def _model_string_list_schema(*, maximum: int = 12) -> dict[str, Any]:
    return {
        "type": "array",
        "maxItems": maximum,
        "items": _model_string_schema(),
    }


def position_model_output_schema() -> dict[str, Any]:
    """Return the exact native Ollama schema for one semantic position."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(POSITION_MODEL_OUTPUT_FIELDS),
        "properties": {
            "answer": _model_string_schema(allow_empty=True),
            "abstained": {"type": "boolean"},
            "evidence_claims": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["claim", "source_refs"],
                    "properties": {
                        "claim": _model_string_schema(),
                        "source_refs": _model_string_list_schema(maximum=8),
                    },
                },
            },
            "assumptions": _model_string_list_schema(),
            "unknowns": _model_string_list_schema(),
            "uncertainty": _model_string_schema(),
            "alternative": _model_string_schema(),
            "disconfirming_test": _model_string_schema(),
            "decision_implications": _model_string_list_schema(),
        },
    }


def synthesis_model_output_schema() -> dict[str, Any]:
    """Return the exact native Ollama schema for semantic synthesis."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(SYNTHESIS_MODEL_OUTPUT_FIELDS),
        "properties": {
            "answer": _model_string_schema(),
            "agreements": _model_string_list_schema(),
            "disagreements": _model_string_list_schema(),
            "uncertainty": _model_string_schema(),
            "next_tests": _model_string_list_schema(),
        },
    }


class StructuredConsultContractError(ValueError):
    """A deterministic graph or envelope contract failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class StructuredConsultLimits:
    """Immutable aggregate resource authority for one local graph run."""

    max_position_nodes: int
    max_total_nodes: int
    max_depth: int
    max_concurrency: int
    max_model_calls: int
    max_input_tokens: int
    max_context_bytes: int
    max_output_tokens: int
    position_output_tokens: int
    synthesis_output_tokens: int
    max_artifact_bytes: int
    per_node_elapsed_seconds: float
    max_elapsed_seconds: float
    max_attempts_per_node: int = 1
    max_retries: int = 0
    max_repairs: int = 0
    max_cost_usd: float = 0.0
    completion_policy: str = "require_all"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_structured_consult_limits(
    position_count: int,
    *,
    concurrency: int = 1,
    max_elapsed_seconds: float = DEFAULT_RUN_ELAPSED_SECONDS,
) -> StructuredConsultLimits:
    """Build the smallest default envelope that covers a fixed graph."""
    _bounded_int("position_count", position_count, minimum=1, maximum=MAX_POSITION_NODES)
    _bounded_int("concurrency", concurrency, minimum=1, maximum=MAX_LOCAL_CONCURRENCY)
    _bounded_float(
        "max_elapsed_seconds",
        max_elapsed_seconds,
        minimum=0.001,
        maximum=86_400.0,
    )
    node_count = position_count + 1
    return StructuredConsultLimits(
        max_position_nodes=position_count,
        max_total_nodes=node_count,
        max_depth=2,
        max_concurrency=min(concurrency, position_count),
        max_model_calls=node_count,
        max_input_tokens=DEFAULT_INPUT_TOKEN_CEILING,
        max_context_bytes=DEFAULT_CONTEXT_BYTE_CEILING,
        max_output_tokens=(position_count * DEFAULT_POSITION_OUTPUT_TOKENS) + DEFAULT_SYNTHESIS_OUTPUT_TOKENS,
        position_output_tokens=DEFAULT_POSITION_OUTPUT_TOKENS,
        synthesis_output_tokens=DEFAULT_SYNTHESIS_OUTPUT_TOKENS,
        max_artifact_bytes=DEFAULT_ARTIFACT_BYTE_CEILING,
        per_node_elapsed_seconds=min(DEFAULT_NODE_ELAPSED_SECONDS, max_elapsed_seconds),
        max_elapsed_seconds=max_elapsed_seconds,
    )


def stable_json_hash(value: object) -> str:
    """Return a stable SHA-256 digest for one JSON-compatible value."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_structured_consult_brief(
    *,
    question: str,
    perspectives: Sequence[object],
    model: str,
    model_provenance: Mapping[str, Any],
    owned_endpoint: str,
    limits: StructuredConsultLimits | None = None,
) -> dict[str, Any]:
    """Freeze expert packets and build the one supported dependency graph."""
    normalized_question = _nonempty_string("question", question, maximum_bytes=MAX_QUESTION_BYTES)
    normalized_model = _nonempty_string("model", model, maximum_bytes=512)
    normalized_provenance = _validate_model_provenance(model_provenance, model=normalized_model)
    raw_endpoint = _nonempty_string("owned_endpoint", owned_endpoint, maximum_bytes=2_048)
    try:
        normalized_endpoint = validate_owned_local_ollama_url(raw_endpoint)
    except ValueError as exc:
        raise StructuredConsultContractError("LOCAL_AUTHORITY", str(exc)) from exc
    if not perspectives:
        raise StructuredConsultContractError("EMPTY_ROSTER", "at least one expert perspective is required")
    if len(perspectives) > MAX_POSITION_NODES:
        raise StructuredConsultContractError(
            "POSITION_LIMIT",
            f"structured consult supports at most {MAX_POSITION_NODES} position nodes",
        )

    envelope = limits or default_structured_consult_limits(len(perspectives))
    snapshots = [_snapshot_from_perspective(item, index=index) for index, item in enumerate(perspectives)]
    identities = [str(snapshot["expert_name"]).casefold() for snapshot in snapshots]
    if len(set(identities)) != len(identities):
        raise StructuredConsultContractError("DUPLICATE_EXPERT", "expert roster must contain unique identities")

    identity_seed = {
        "question": normalized_question,
        "snapshot_hashes": [snapshot["snapshot_hash"] for snapshot in snapshots],
        "model": normalized_model,
        "model_provenance": normalized_provenance,
        "endpoint": normalized_endpoint,
        "limits": envelope.to_dict(),
    }
    graph_id = f"graph_{stable_json_hash(identity_seed)[:24]}"
    nodes: list[dict[str, Any]] = []
    for index, snapshot in enumerate(snapshots, start=1):
        nodes.append(
            {
                "node_id": f"position_{index:03d}",
                "node_kind": "position",
                "depends_on": [],
                "input_artifact_ids": [snapshot["snapshot_id"]],
                "expert_name": snapshot["expert_name"],
                "snapshot_hash": snapshot["snapshot_hash"],
                "mutable_resources": ["cost_ledger", "ollama_model_residency"],
                "max_attempts": 1,
                "max_output_tokens": envelope.position_output_tokens,
                "max_elapsed_seconds": envelope.per_node_elapsed_seconds,
            }
        )
    position_ids = [str(node["node_id"]) for node in nodes]
    nodes.append(
        {
            "node_id": "synthesis_001",
            "node_kind": "synthesis",
            "depends_on": position_ids,
            "input_artifact_ids": [],
            "expert_name": None,
            "snapshot_hash": None,
            "mutable_resources": ["cost_ledger", "ollama_model_residency"],
            "max_attempts": 1,
            "max_output_tokens": envelope.synthesis_output_tokens,
            "max_elapsed_seconds": envelope.per_node_elapsed_seconds,
        }
    )

    brief: dict[str, Any] = {
        "schema_version": STRUCTURED_CONSULT_BRIEF_SCHEMA_VERSION,
        "kind": STRUCTURED_CONSULT_BRIEF_KIND,
        "graph_id": graph_id,
        "question": normalized_question,
        "question_hash": stable_json_hash(normalized_question),
        "prompt_version": "structured-consult-local-v1",
        "protocol_version": "structured-consult-graph-v1",
        "capacity": {
            "capacity_kind": "owned_hardware",
            "provider": "local",
            "model": normalized_model,
            "model_provenance": normalized_provenance,
            "endpoint": normalized_endpoint,
            "endpoint_class": "literal_loopback",
            "transport": "ollama_native_http",
            "credential_headers": False,
            "trust_env": False,
            "follow_redirects": False,
            "model_keep_alive": "5m",
            "preflight_http_requests": 2,
            "live_metered_fallback": False,
            "plan_quota_fallback": False,
            "sdk_retries": 0,
            "cost_usd": 0.0,
        },
        "authority": {
            "read_only": True,
            "writes_state": False,
            "observability_writes": True,
            "cost_ledger_required": True,
            "tools": False,
            "browsing": False,
            "embeddings": False,
            "remote_retrieval": False,
            "remote_provider_calls": False,
            "semantic_verdict": False,
        },
        "limits": envelope.to_dict(),
        "snapshots": snapshots,
        "nodes": nodes,
        "expected": {
            "position_nodes": len(snapshots),
            "synthesis_nodes": 1,
            "total_nodes": len(nodes),
            "maximum_model_calls": len(nodes),
        },
    }
    brief["brief_hash"] = stable_json_hash(brief)
    validate_structured_consult_brief(brief)
    return brief


def validate_structured_consult_brief(brief: Mapping[str, Any]) -> None:
    """Reject graph, capacity, hash, and resource drift before inference."""
    _validate_brief_identity(brief)
    _validate_capacity_and_authority(brief)
    limits = _validate_limits(_mapping("limits", brief.get("limits")))
    snapshots = _validate_snapshots(brief, limits=limits)
    nodes = _mapping_sequence("nodes", brief.get("nodes"))
    node_by_id = _index_nodes(nodes, limits=limits)
    position_nodes, _synthesis_node = _validate_fixed_graph(
        nodes,
        node_by_id=node_by_id,
        snapshots=snapshots,
        limits=limits,
    )
    _validate_expected_counts(brief, position_count=len(position_nodes), node_count=len(nodes))
    _validate_graph_id(brief, snapshots=snapshots, limits=limits)
    _validate_brief_hash(brief)


def _validate_brief_identity(brief: Mapping[str, Any]) -> None:
    if set(brief) != _BRIEF_FIELDS:
        raise StructuredConsultContractError("BRIEF_SHAPE", "structured consult brief fields do not match v1")
    if brief.get("schema_version") != STRUCTURED_CONSULT_BRIEF_SCHEMA_VERSION:
        raise StructuredConsultContractError("SCHEMA_VERSION", "unsupported structured consult brief schema")
    if brief.get("kind") != STRUCTURED_CONSULT_BRIEF_KIND:
        raise StructuredConsultContractError("KIND", "invalid structured consult brief kind")
    if brief.get("prompt_version") != "structured-consult-local-v1":
        raise StructuredConsultContractError("PROMPT_VERSION", "unsupported structured consult prompt version")
    if brief.get("protocol_version") != "structured-consult-graph-v1":
        raise StructuredConsultContractError("PROTOCOL_VERSION", "unsupported structured consult protocol version")
    question = _nonempty_string("question", brief.get("question"), maximum_bytes=MAX_QUESTION_BYTES)
    if brief.get("question_hash") != stable_json_hash(question):
        raise StructuredConsultContractError("QUESTION_HASH", "question hash does not match the frozen question")


def _validate_capacity_and_authority(brief: Mapping[str, Any]) -> None:
    capacity = _mapping("capacity", brief.get("capacity"))
    if set(capacity) != {
        "capacity_kind",
        "provider",
        "model",
        "model_provenance",
        "endpoint",
        "endpoint_class",
        "transport",
        "credential_headers",
        "trust_env",
        "follow_redirects",
        "model_keep_alive",
        "preflight_http_requests",
        "live_metered_fallback",
        "plan_quota_fallback",
        "sdk_retries",
        "cost_usd",
    }:
        raise StructuredConsultContractError("LOCAL_AUTHORITY", "capacity fields do not match v1")
    exact_capacity = {
        "capacity_kind": "owned_hardware",
        "provider": "local",
        "endpoint_class": "literal_loopback",
        "transport": "ollama_native_http",
        "credential_headers": False,
        "trust_env": False,
        "follow_redirects": False,
        "live_metered_fallback": False,
        "plan_quota_fallback": False,
        "sdk_retries": 0,
        "cost_usd": 0.0,
        "model_keep_alive": "5m",
        "preflight_http_requests": 2,
    }
    for field, expected in exact_capacity.items():
        if capacity.get(field) != expected:
            raise StructuredConsultContractError(
                "LOCAL_AUTHORITY",
                f"capacity.{field} must be exactly {expected!r}",
            )
    _nonempty_string("capacity.model", capacity.get("model"), maximum_bytes=512)
    _validate_model_provenance(
        _mapping("capacity.model_provenance", capacity.get("model_provenance")),
        model=str(capacity["model"]),
    )
    endpoint = _nonempty_string("capacity.endpoint", capacity.get("endpoint"), maximum_bytes=2_048)
    try:
        canonical_endpoint = validate_owned_local_ollama_url(endpoint)
    except ValueError as exc:
        raise StructuredConsultContractError("LOCAL_AUTHORITY", str(exc)) from exc
    if canonical_endpoint != endpoint:
        raise StructuredConsultContractError("LOCAL_AUTHORITY", "capacity.endpoint must be canonical loopback")

    authority = _mapping("authority", brief.get("authority"))
    exact_authority = {
        "read_only": True,
        "writes_state": False,
        "observability_writes": True,
        "cost_ledger_required": True,
        "tools": False,
        "browsing": False,
        "embeddings": False,
        "remote_retrieval": False,
        "remote_provider_calls": False,
        "semantic_verdict": False,
    }
    if dict(authority) != exact_authority:
        raise StructuredConsultContractError("EXTERNAL_AUTHORITY", "authority fields do not match v1")


def _validate_snapshots(brief: Mapping[str, Any], *, limits: StructuredConsultLimits) -> list[Mapping[str, Any]]:
    snapshots = _mapping_sequence("snapshots", brief.get("snapshots"))
    if not 1 <= len(snapshots) <= limits.max_position_nodes:
        raise StructuredConsultContractError("POSITION_LIMIT", "snapshot count exceeds the position envelope")
    snapshot_ids: set[str] = set()
    expert_names: set[str] = set()
    snapshot_bytes = 0
    for snapshot in snapshots:
        if set(snapshot) != {"snapshot_id", "snapshot_hash", "expert_name", "domain", "content", "context"}:
            raise StructuredConsultContractError("SNAPSHOT_SHAPE", "snapshot fields do not match v1")
        snapshot_id = _nonempty_string("snapshot_id", snapshot.get("snapshot_id"), maximum_bytes=128)
        if snapshot_id in snapshot_ids:
            raise StructuredConsultContractError("DUPLICATE_SNAPSHOT", f"duplicate snapshot id {snapshot_id!r}")
        snapshot_ids.add(snapshot_id)
        expert_name = _nonempty_string("expert_name", snapshot.get("expert_name"), maximum_bytes=512)
        if expert_name.casefold() in expert_names:
            raise StructuredConsultContractError("DUPLICATE_EXPERT", "expert roster must contain unique identities")
        expert_names.add(expert_name.casefold())
        content = _nonempty_string("snapshot.content", snapshot.get("content"), maximum_bytes=MAX_SNAPSHOT_BYTES)
        context = _mapping("snapshot.context", snapshot.get("context"))
        hashed = {
            "expert_name": expert_name,
            "domain": str(snapshot.get("domain", "")),
            "content": content,
            "context": dict(context),
        }
        expected_hash = stable_json_hash(hashed)
        if snapshot.get("snapshot_hash") != expected_hash:
            raise StructuredConsultContractError("SNAPSHOT_HASH", f"snapshot hash mismatch for {expert_name!r}")
        if snapshot_id != f"snapshot_{expected_hash[:24]}":
            raise StructuredConsultContractError("SNAPSHOT_ID", f"snapshot id mismatch for {expert_name!r}")
        snapshot_bytes += len(json.dumps(snapshot, ensure_ascii=True).encode("utf-8"))
    if snapshot_bytes > limits.max_context_bytes:
        raise StructuredConsultContractError("CONTEXT_LIMIT", "frozen snapshots exceed max_context_bytes")
    return snapshots


def _index_nodes(nodes: list[Mapping[str, Any]], *, limits: StructuredConsultLimits) -> dict[str, Mapping[str, Any]]:
    if len(nodes) > limits.max_total_nodes:
        raise StructuredConsultContractError("NODE_LIMIT", "graph exceeds max_total_nodes")
    node_by_id: dict[str, Mapping[str, Any]] = {}
    for node in nodes:
        if set(node) != _NODE_FIELDS:
            raise StructuredConsultContractError("NODE_SHAPE", "node fields do not match v1")
        node_id = _nonempty_string("node_id", node.get("node_id"), maximum_bytes=128)
        if node_id in node_by_id:
            raise StructuredConsultContractError("DUPLICATE_NODE", f"duplicate node id {node_id!r}")
        node_by_id[node_id] = node
        if node.get("node_kind") not in {"position", "synthesis"}:
            raise StructuredConsultContractError("NODE_KIND", f"unsupported node kind for {node_id!r}")
        if node.get("max_attempts") != 1:
            raise StructuredConsultContractError("ATTEMPT_LIMIT", f"node {node_id!r} must allow exactly one attempt")
    return node_by_id


def _validate_fixed_graph(
    nodes: list[Mapping[str, Any]],
    *,
    node_by_id: Mapping[str, Mapping[str, Any]],
    snapshots: list[Mapping[str, Any]],
    limits: StructuredConsultLimits,
) -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
    snapshot_count = len(snapshots)
    if len(nodes) != snapshot_count + 1:
        raise StructuredConsultContractError("GRAPH_SHAPE", "graph must contain one node per snapshot plus synthesis")

    synthesis_nodes = [node for node in nodes if node.get("node_kind") == "synthesis"]
    position_nodes = [node for node in nodes if node.get("node_kind") == "position"]
    if len(synthesis_nodes) != 1 or len(position_nodes) != snapshot_count:
        raise StructuredConsultContractError("GRAPH_SHAPE", "graph requires all positions and exactly one synthesis")
    expected_position_ids = [f"position_{index:03d}" for index in range(1, snapshot_count + 1)]
    if set(node_by_id) != {*expected_position_ids, "synthesis_001"}:
        raise StructuredConsultContractError("NODE_ID", "graph node ids do not match the fixed v1 graph")
    if [str(node["node_id"]) for node in nodes] != [*expected_position_ids, "synthesis_001"]:
        raise StructuredConsultContractError("NODE_ORDER", "graph nodes do not match the fixed v1 order")
    graph_depth = _validate_dependencies(node_by_id)
    for node_id, snapshot in zip(expected_position_ids, snapshots, strict=True):
        _validate_position_node(node_by_id[node_id], snapshot=snapshot, limits=limits)
    synthesis_node = node_by_id["synthesis_001"]
    _validate_synthesis_node(synthesis_node, position_ids=expected_position_ids, limits=limits)

    if graph_depth > limits.max_depth:
        raise StructuredConsultContractError("DEPTH_LIMIT", "graph exceeds max_depth")

    if limits.max_position_nodes != snapshot_count or limits.max_total_nodes != len(nodes):
        raise StructuredConsultContractError("NODE_LIMIT", "node ceilings must equal the fixed graph size")
    if limits.max_model_calls != len(nodes):
        raise StructuredConsultContractError("CALL_LIMIT", "max_model_calls must equal the fixed graph size")
    required_output = (len(position_nodes) * limits.position_output_tokens) + limits.synthesis_output_tokens
    if limits.max_output_tokens != required_output:
        raise StructuredConsultContractError("OUTPUT_LIMIT", "max_output_tokens must equal the fixed graph envelope")
    return [node_by_id[node_id] for node_id in expected_position_ids], synthesis_node


def _validate_position_node(
    node: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any],
    limits: StructuredConsultLimits,
) -> None:
    if node.get("node_kind") != "position" or node.get("depends_on") != []:
        raise StructuredConsultContractError("FALSE_EDGE", "position nodes must be mutually independent")
    if node.get("mutable_resources") != ["cost_ledger", "ollama_model_residency"]:
        raise StructuredConsultContractError("MUTABLE_RESOURCE", "position must disclose ledger and model residency")
    if node.get("input_artifact_ids") != [snapshot["snapshot_id"]]:
        raise StructuredConsultContractError("SNAPSHOT_BINDING", "position input must bind its one frozen snapshot")
    if node.get("expert_name") != snapshot["expert_name"] or node.get("snapshot_hash") != snapshot["snapshot_hash"]:
        raise StructuredConsultContractError("SNAPSHOT_BINDING", "position identity must match its frozen snapshot")
    if node.get("max_output_tokens") != limits.position_output_tokens:
        raise StructuredConsultContractError("OUTPUT_LIMIT", "position output limit does not match the envelope")
    if node.get("max_elapsed_seconds") != limits.per_node_elapsed_seconds:
        raise StructuredConsultContractError("ELAPSED_LIMIT", "position elapsed limit does not match the envelope")


def _validate_synthesis_node(
    node: Mapping[str, Any],
    *,
    position_ids: list[str],
    limits: StructuredConsultLimits,
) -> None:
    if node.get("node_kind") != "synthesis" or node.get("depends_on") != position_ids:
        raise StructuredConsultContractError("COMPLETION_GATE", "synthesis must depend on every position in order")
    if node.get("mutable_resources") != ["cost_ledger", "ollama_model_residency"]:
        raise StructuredConsultContractError("MUTABLE_RESOURCE", "synthesis must disclose ledger and model residency")
    if (
        node.get("input_artifact_ids") != []
        or node.get("expert_name") is not None
        or node.get("snapshot_hash") is not None
    ):
        raise StructuredConsultContractError("SYNTHESIS_BINDING", "synthesis resource binding does not match v1")
    if node.get("max_output_tokens") != limits.synthesis_output_tokens:
        raise StructuredConsultContractError("OUTPUT_LIMIT", "synthesis output limit does not match the envelope")
    if node.get("max_elapsed_seconds") != limits.per_node_elapsed_seconds:
        raise StructuredConsultContractError("ELAPSED_LIMIT", "synthesis elapsed limit does not match the envelope")


def _validate_expected_counts(brief: Mapping[str, Any], *, position_count: int, node_count: int) -> None:
    expected = _mapping("expected", brief.get("expected"))
    expected_values = {
        "position_nodes": position_count,
        "synthesis_nodes": 1,
        "total_nodes": node_count,
        "maximum_model_calls": node_count,
    }
    if dict(expected) != expected_values:
        raise StructuredConsultContractError("EXPECTED_COUNT", "expected counts do not match the fixed graph")


def _validate_graph_id(
    brief: Mapping[str, Any],
    *,
    snapshots: list[Mapping[str, Any]],
    limits: StructuredConsultLimits,
) -> None:
    capacity = _mapping("capacity", brief["capacity"])
    identity_seed = {
        "question": brief["question"],
        "snapshot_hashes": [snapshot["snapshot_hash"] for snapshot in snapshots],
        "model": capacity["model"],
        "model_provenance": capacity["model_provenance"],
        "endpoint": capacity["endpoint"],
        "limits": limits.to_dict(),
    }
    if brief.get("graph_id") != f"graph_{stable_json_hash(identity_seed)[:24]}":
        raise StructuredConsultContractError("GRAPH_ID", "graph id does not match the immutable graph identity")


def _validate_model_provenance(value: Mapping[str, Any], *, model: str) -> dict[str, Any]:
    fields = {
        "attestation_kind",
        "cloud_disabled",
        "cloud_status_source",
        "model",
        "digest",
        "size_bytes",
        "format",
        "observed_at",
        "attestation_hash",
    }
    if set(value) != fields:
        raise StructuredConsultContractError("LOCAL_MODEL_PROVENANCE", "model provenance fields do not match v1")
    if value.get("attestation_kind") != "ollama-owned-local-v1" or value.get("cloud_disabled") is not True:
        raise StructuredConsultContractError("LOCAL_MODEL_PROVENANCE", "Ollama cloud must be explicitly disabled")
    if value.get("model") != model:
        raise StructuredConsultContractError("LOCAL_MODEL_PROVENANCE", "model provenance identity mismatch")
    if value.get("cloud_status_source") not in {"config", "both"}:
        raise StructuredConsultContractError("LOCAL_MODEL_PROVENANCE", "cloud-disable source must be stable config")
    digest = _nonempty_string("model digest", value.get("digest"), maximum_bytes=64)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise StructuredConsultContractError("LOCAL_MODEL_PROVENANCE", "model digest must be lowercase SHA-256")
    _bounded_int("size_bytes", value.get("size_bytes"), minimum=1, maximum=10**15)
    if value.get("format") != "gguf":
        raise StructuredConsultContractError("LOCAL_MODEL_PROVENANCE", "local model format must be GGUF")
    _nonempty_string("observed_at", value.get("observed_at"), maximum_bytes=128)
    unhashed = dict(value)
    provided_hash = unhashed.pop("attestation_hash", None)
    if provided_hash != stable_json_hash(unhashed):
        raise StructuredConsultContractError("LOCAL_MODEL_PROVENANCE", "model attestation hash mismatch")
    return dict(value)


def _validate_brief_hash(brief: Mapping[str, Any]) -> None:
    without_hash = dict(brief)
    provided_hash = without_hash.pop("brief_hash", None)
    if provided_hash != stable_json_hash(without_hash):
        raise StructuredConsultContractError("BRIEF_HASH", "brief hash does not match the immutable brief")


def _snapshot_from_perspective(value: object, *, index: int) -> dict[str, Any]:
    if isinstance(value, Mapping):
        expert_name = value.get("expert_name", value.get("expert", ""))
        domain = value.get("domain", "")
        content = value.get("response", value.get("content", ""))
        context = value.get("context", {})
    else:
        expert_name = getattr(value, "expert_name", "")
        domain = getattr(value, "domain", "")
        content = getattr(value, "response", "")
        context = getattr(value, "context", {})
    name = _nonempty_string(f"perspectives[{index}].expert_name", expert_name, maximum_bytes=512)
    normalized_domain = str(domain or "")
    normalized_content = _nonempty_string(
        f"perspectives[{index}].content",
        content,
        maximum_bytes=MAX_SNAPSHOT_BYTES,
    )
    normalized_context = dict(_mapping(f"perspectives[{index}].context", context))
    hashed = {
        "expert_name": name,
        "domain": normalized_domain,
        "content": normalized_content,
        "context": normalized_context,
    }
    snapshot_hash = stable_json_hash(hashed)
    return {
        "snapshot_id": f"snapshot_{snapshot_hash[:24]}",
        "snapshot_hash": snapshot_hash,
        **hashed,
    }


def _validate_limits(value: Mapping[str, Any]) -> StructuredConsultLimits:
    expected_fields = set(default_structured_consult_limits(1).to_dict())
    if set(value) != expected_fields:
        raise StructuredConsultContractError("INVALID_LIMIT", "limit fields do not match v1")
    limits = StructuredConsultLimits(
        max_position_nodes=_bounded_int(
            "max_position_nodes", value.get("max_position_nodes"), minimum=1, maximum=MAX_POSITION_NODES
        ),
        max_total_nodes=_bounded_int(
            "max_total_nodes", value.get("max_total_nodes"), minimum=2, maximum=MAX_POSITION_NODES + 1
        ),
        max_depth=_bounded_int("max_depth", value.get("max_depth"), minimum=2, maximum=2),
        max_concurrency=_bounded_int(
            "max_concurrency", value.get("max_concurrency"), minimum=1, maximum=MAX_LOCAL_CONCURRENCY
        ),
        max_model_calls=_bounded_int(
            "max_model_calls", value.get("max_model_calls"), minimum=2, maximum=MAX_POSITION_NODES + 1
        ),
        max_input_tokens=_bounded_int("max_input_tokens", value.get("max_input_tokens"), minimum=1, maximum=10_000_000),
        max_context_bytes=_bounded_int(
            "max_context_bytes", value.get("max_context_bytes"), minimum=1_024, maximum=10_000_000
        ),
        max_output_tokens=_bounded_int("max_output_tokens", value.get("max_output_tokens"), minimum=1, maximum=100_000),
        position_output_tokens=_bounded_int(
            "position_output_tokens", value.get("position_output_tokens"), minimum=64, maximum=8_192
        ),
        synthesis_output_tokens=_bounded_int(
            "synthesis_output_tokens", value.get("synthesis_output_tokens"), minimum=64, maximum=8_192
        ),
        max_artifact_bytes=_bounded_int(
            "max_artifact_bytes", value.get("max_artifact_bytes"), minimum=1_024, maximum=10_000_000
        ),
        per_node_elapsed_seconds=_bounded_float(
            "per_node_elapsed_seconds",
            value.get("per_node_elapsed_seconds"),
            minimum=0.001,
            maximum=86_400.0,
        ),
        max_elapsed_seconds=_bounded_float(
            "max_elapsed_seconds", value.get("max_elapsed_seconds"), minimum=0.001, maximum=86_400.0
        ),
        max_attempts_per_node=_bounded_int(
            "max_attempts_per_node", value.get("max_attempts_per_node"), minimum=1, maximum=1
        ),
        max_retries=_bounded_int("max_retries", value.get("max_retries"), minimum=0, maximum=0),
        max_repairs=_bounded_int("max_repairs", value.get("max_repairs"), minimum=0, maximum=0),
        max_cost_usd=_bounded_float("max_cost_usd", value.get("max_cost_usd"), minimum=0.0, maximum=0.0),
        completion_policy=str(value.get("completion_policy", "")),
    )
    if limits.completion_policy != "require_all":
        raise StructuredConsultContractError("COMPLETION_POLICY", "only require_all is supported")
    if limits.max_concurrency > limits.max_position_nodes:
        raise StructuredConsultContractError("CONCURRENCY_LIMIT", "concurrency cannot exceed position nodes")
    if limits.per_node_elapsed_seconds > limits.max_elapsed_seconds:
        raise StructuredConsultContractError("ELAPSED_LIMIT", "per-node elapsed limit exceeds run limit")
    return limits


def _validate_dependencies(nodes: Mapping[str, Mapping[str, Any]]) -> int:
    for node_id, node in nodes.items():
        dependencies = node.get("depends_on")
        if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
            raise StructuredConsultContractError("DEPENDENCY_SHAPE", f"node {node_id!r} has invalid dependencies")
        if node_id in dependencies:
            raise StructuredConsultContractError("SELF_DEPENDENCY", f"node {node_id!r} depends on itself")
        missing = [dependency for dependency in dependencies if dependency not in nodes]
        if missing:
            raise StructuredConsultContractError(
                "MISSING_DEPENDENCY",
                f"node {node_id!r} has missing dependencies: {', '.join(missing)}",
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def depth(node_id: str) -> int:
        if node_id in visiting:
            raise StructuredConsultContractError("CYCLE", f"graph contains a cycle at {node_id!r}")
        if node_id in visited:
            node = nodes[node_id]
            dependencies = node.get("depends_on", [])
            return 1 if not dependencies else 1 + max(depth(str(item)) for item in dependencies)
        visiting.add(node_id)
        dependencies = nodes[node_id].get("depends_on", [])
        current_depth = 1 if not dependencies else 1 + max(depth(str(item)) for item in dependencies)
        visiting.remove(node_id)
        visited.add(node_id)
        return current_depth

    return max(depth(node_id) for node_id in nodes)


def _mapping(name: str, value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StructuredConsultContractError("INVALID_TYPE", f"{name} must be an object")
    return value


def _mapping_sequence(name: str, value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise StructuredConsultContractError("INVALID_TYPE", f"{name} must be an array of objects")
    return list(value)


def _nonempty_string(name: str, value: object, *, maximum_bytes: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StructuredConsultContractError("INVALID_STRING", f"{name} must be a non-empty string")
    normalized = value.strip()
    if len(normalized.encode("utf-8")) > maximum_bytes:
        raise StructuredConsultContractError("BYTE_LIMIT", f"{name} exceeds {maximum_bytes} bytes")
    return normalized


def _bounded_int(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise StructuredConsultContractError("INVALID_LIMIT", f"{name} must be between {minimum} and {maximum}")
    return value


def _bounded_float(name: str, value: object, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StructuredConsultContractError("INVALID_LIMIT", f"{name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or not minimum <= normalized <= maximum:
        raise StructuredConsultContractError("INVALID_LIMIT", f"{name} must be between {minimum} and {maximum}")
    return normalized
