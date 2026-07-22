"""Linked validation and canonical rendering for simulation consult contexts."""

from __future__ import annotations

from collections.abc import Sequence

from deepr.experts.epistemic_simulation_contract import (
    CompiledContextPath,
    ConsultContextPacket,
    EpistemicContractError,
    EpistemicEdge,
    EpistemicRecord,
    EpistemicSimulation,
    EvidenceUnit,
    _canonical_json_bytes,
    principal_can_inspect,
)


def validate_context_packet(
    lens: EpistemicSimulation,
    packet: ConsultContextPacket,
    *,
    expected_principal_id: str,
) -> None:
    """Validate a context against its lens and authenticated consumer."""
    if packet.consumer_principal_id != expected_principal_id:
        raise EpistemicContractError("context consumer does not match the authenticated principal")
    _validate_context_identity(lens, packet)
    selected_records, selected_edges = _validate_context_paths(lens, packet)
    _validate_context_selection_summary(lens, packet, selected_records, selected_edges)


def _validate_context_identity(lens: EpistemicSimulation, packet: ConsultContextPacket) -> None:
    if packet.lens_id != lens.lens_id:
        raise EpistemicContractError("context lens_id does not match the frozen lens")
    if packet.branch_id not in {world.branch_id for world in lens.world_models}:
        raise EpistemicContractError("context branch_id does not match a frozen world model")
    if packet.simulation_disclosure != lens.disclosure.text:
        raise EpistemicContractError("context does not preserve the simulation disclosure")
    if packet.expert_snapshot_version != lens.snapshots.expert_snapshot_version:
        raise EpistemicContractError("context expert snapshot does not match the lens")
    if packet.compiler_version != lens.snapshots.context_compiler_version:
        raise EpistemicContractError("context compiler version does not match the lens")


def _validate_context_paths(
    lens: EpistemicSimulation,
    packet: ConsultContextPacket,
) -> tuple[set[str], set[str]]:
    record_by_id = {record.record_id: record for record in lens.records}
    edge_by_id = {edge.edge_id: edge for edge in lens.edges}
    evidence_by_id = {evidence.evidence_id: evidence for evidence in lens.evidence_units}
    selected_records: set[str] = set()
    selected_edges: set[str] = set()
    provenance_ids = set(record_by_id).union(evidence_by_id)
    for path in packet.selected_paths:
        _validate_context_path(
            path,
            packet.branch_id,
            packet.consumer_principal_id,
            record_by_id,
            edge_by_id,
            evidence_by_id,
            provenance_ids,
        )
        selected_records.update(path.record_ids)
        selected_edges.update(path.edge_ids)
    return selected_records, selected_edges


def _validate_context_selection_summary(
    lens: EpistemicSimulation,
    packet: ConsultContextPacket,
    selected_records: set[str],
    selected_edges: set[str],
) -> None:
    if selected_records != set(packet.selected_record_ids):
        raise EpistemicContractError("selected_record_ids do not match context paths")
    if selected_edges != set(packet.selected_edge_ids):
        raise EpistemicContractError("selected_edge_ids do not match context paths")
    invalidated_ids = {record.record_id for record in lens.records if record.status == "invalidated"}
    if invalidated_ids != set(packet.excluded_invalidated_record_ids):
        raise EpistemicContractError("context metadata must exactly disclose excluded invalidated memory")
    if packet.content_bytes != context_content_bytes(lens, packet):
        raise EpistemicContractError("context content_bytes does not match its canonical selected content")


def _validate_context_path(
    path: CompiledContextPath,
    packet_branch_id: str,
    consumer_principal_id: str,
    record_by_id: dict[str, EpistemicRecord],
    edge_by_id: dict[str, EpistemicEdge],
    evidence_by_id: dict[str, EvidenceUnit],
    provenance_ids: set[str],
) -> None:
    records, edges = _resolve_context_path(path, record_by_id, edge_by_id)
    _validate_context_record_access(
        records,
        record_by_id,
        evidence_by_id,
        consumer_principal_id,
        path.branch_id,
    )
    _validate_context_branch(path, records, edges, packet_branch_id)
    _validate_context_provenance(
        path,
        records,
        edges,
        record_by_id,
        evidence_by_id,
        provenance_ids,
        consumer_principal_id,
    )
    _validate_context_connectivity(path, edges)


def _resolve_context_path(
    path: CompiledContextPath,
    record_by_id: dict[str, EpistemicRecord],
    edge_by_id: dict[str, EpistemicEdge],
) -> tuple[list[EpistemicRecord], list[EpistemicEdge]]:
    try:
        records = [record_by_id[record_id] for record_id in path.record_ids]
        edges = [edge_by_id[edge_id] for edge_id in path.edge_ids]
    except KeyError as exc:
        raise EpistemicContractError(f"context path references unknown record or edge: {exc}") from exc
    return records, edges


def _validate_context_record_access(
    records: Sequence[EpistemicRecord],
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
    consumer_principal_id: str,
    path_branch_id: str | None,
) -> None:
    dependency_records = _record_dependency_closure(records, record_by_id)
    if any(record.status != "current" for record in dependency_records):
        raise EpistemicContractError("context path includes invalidated or retired memory")
    if any(record.branch_id not in {None, path_branch_id} for record in dependency_records):
        raise EpistemicContractError("context record dependencies leak across branch scope")
    if any(
        not principal_can_inspect(evidence_by_id[evidence_id], consumer_principal_id)
        for record in dependency_records
        for evidence_id in record.evidence_refs
    ):
        raise EpistemicContractError("context path includes evidence outside the consumer access policy")


def _record_dependency_closure(
    records: Sequence[EpistemicRecord],
    record_by_id: dict[str, EpistemicRecord],
) -> tuple[EpistemicRecord, ...]:
    pending = list(records)
    visited: set[str] = set()
    closure: list[EpistemicRecord] = []
    while pending:
        record = pending.pop()
        if record.record_id in visited:
            continue
        visited.add(record.record_id)
        closure.append(record)
        pending.extend(record_by_id[item] for item in record.assumption_refs)
    return tuple(closure)


def _validate_context_branch(
    path: CompiledContextPath,
    records: Sequence[EpistemicRecord],
    edges: Sequence[EpistemicEdge],
    packet_branch_id: str,
) -> None:
    if path.lane_sequence != tuple(record.lane for record in records):
        raise EpistemicContractError("context path lane sequence does not match its records")
    branch_ids = {record.branch_id for record in records if record.branch_id is not None}
    if path.branch_id not in {None, packet_branch_id}:
        raise EpistemicContractError("context path references a branch outside its packet")
    if branch_ids and (branch_ids != {packet_branch_id} or path.branch_id != packet_branch_id):
        raise EpistemicContractError("context path leaks across branch scope")
    if any(edge.branch_id not in {None, path.branch_id} for edge in edges):
        raise EpistemicContractError("context edge leaks across branch scope")
    scoped_times = {record.scenario_time for record in records if record.scenario_time is not None}
    scoped_times.update(edge.scenario_time for edge in edges if edge.scenario_time is not None)
    if scoped_times and path.scenario_time not in scoped_times:
        raise EpistemicContractError("context path scenario_time does not match selected branch state")


def _validate_context_provenance(
    path: CompiledContextPath,
    records: Sequence[EpistemicRecord],
    edges: Sequence[EpistemicEdge],
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
    provenance_ids: set[str],
    consumer_principal_id: str,
) -> None:
    if set(path.provenance_refs).difference(provenance_ids):
        raise EpistemicContractError("context path has unknown provenance refs")
    if any(
        provenance_ref in evidence_by_id
        and not principal_can_inspect(evidence_by_id[provenance_ref], consumer_principal_id)
        for provenance_ref in path.provenance_refs
    ):
        raise EpistemicContractError("context path provenance exceeds the consumer access policy")
    provenance_records = tuple(
        record_by_id[provenance_ref] for provenance_ref in path.provenance_refs if provenance_ref in record_by_id
    )
    _validate_context_record_access(
        provenance_records,
        record_by_id,
        evidence_by_id,
        consumer_principal_id,
        path.branch_id,
    )
    linked_provenance = {
        provenance_ref for record in records for provenance_ref in (*record.evidence_refs, *record.assumption_refs)
    }
    linked_provenance.update(provenance_ref for edge in edges for provenance_ref in edge.provenance_refs)
    dependency_records = _record_dependency_closure((*records, *provenance_records), record_by_id)
    linked_provenance.update(
        provenance_ref
        for record in dependency_records
        for provenance_ref in (*record.evidence_refs, *record.assumption_refs)
    )
    if set(path.provenance_refs) != linked_provenance:
        raise EpistemicContractError("context path provenance must exactly match selected records and edges")


def _validate_context_connectivity(path: CompiledContextPath, edges: Sequence[EpistemicEdge]) -> None:
    path_record_ids = set(path.record_ids)
    if any(
        edge.source_record_id not in path_record_ids or edge.target_record_id not in path_record_ids for edge in edges
    ):
        raise EpistemicContractError("context edge endpoints must remain inside their selected path")
    if not _path_is_connected(path_record_ids, edges):
        raise EpistemicContractError("multi-record context paths must be connected by selected edges")


def _path_is_connected(record_ids: set[str], edges: Sequence[EpistemicEdge]) -> bool:
    if len(record_ids) == 1:
        return True
    adjacency = {record_id: set[str]() for record_id in record_ids}
    for edge in edges:
        adjacency[edge.source_record_id].add(edge.target_record_id)
        adjacency[edge.target_record_id].add(edge.source_record_id)
    pending = [next(iter(record_ids))]
    visited: set[str] = set()
    while pending:
        record_id = pending.pop()
        if record_id in visited:
            continue
        visited.add(record_id)
        pending.extend(adjacency[record_id].difference(visited))
    return visited == record_ids


def context_content_bytes(lens: EpistemicSimulation, packet: ConsultContextPacket) -> int:
    """Return canonical UTF-8 bytes for the selected, renderable context content."""
    record_by_id = {record.record_id: record for record in lens.records}
    edge_by_id = {edge.edge_id: edge for edge in lens.edges}
    payload = {
        "simulation_disclosure": packet.simulation_disclosure,
        "consumer_principal_id": packet.consumer_principal_id,
        "paths": [
            {
                "path_id": path.path_id,
                "why_this_lens": path.why_this_lens,
                "branch_id": path.branch_id,
                "scenario_time": path.scenario_time,
                "provenance_refs": list(path.provenance_refs),
                "records": [record_by_id[item].model_dump(mode="json") for item in path.record_ids],
                "edges": [edge_by_id[item].model_dump(mode="json") for item in path.edge_ids],
            }
            for path in packet.selected_paths
        ],
    }
    return len(_canonical_json_bytes(payload))


__all__ = ["context_content_bytes", "validate_context_packet"]
