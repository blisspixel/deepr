"""Read-only preflight for explicitly timed, nested source-world artifacts.

This preparation contract checks declared timing and actual local bytes. It
does not run an evaluation, establish historical publication dates, isolate an
arm process, judge source meaning, or attest that a person reviewed anything.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deepr.evals.expert_value_artifacts import ArtifactVerificationError, read_bounded_artifact
from deepr.experts.outcomes import normalize_timestamp

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_REFERENCES = 4096

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Reference = Annotated[str, Field(min_length=1, max_length=4000)]
Timestamp = Annotated[str, Field(max_length=80, json_schema_extra={"format": "date-time"})]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class SourceVersion(_StrictModel):
    """One explicit source snapshot; times remain organizer declarations."""

    source_version_id: Identifier
    artifact_ref: Reference
    sha256: Digest
    bytes: int = Field(ge=1, le=MAX_SOURCE_BYTES)
    available_at: Timestamp
    snapshot_collected_at: Timestamp

    @field_validator("available_at", "snapshot_collected_at")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        return normalize_timestamp(value)


class SourceWorldManifest(_StrictModel):
    """One world's source inventory, without organizer evaluation-role labels."""

    schema_version: Literal["deepr-expert-value-source-world-v1"]
    kind: Literal["deepr.expert.value_source_world"]
    source_world_id: Identifier
    predecessor_source_world_id: Identifier | None
    information_cutoff: Timestamp
    clock_basis: Literal["synthetic", "historical_assertion"]
    sources: list[SourceVersion] = Field(min_length=1, max_length=512)

    @field_validator("information_cutoff")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        return normalize_timestamp(value)

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        identifiers = [source.source_version_id for source in self.sources]
        paths = [os.path.normcase(source.artifact_ref) for source in self.sources]
        if len(set(identifiers)) != len(identifiers) or len(set(paths)) != len(paths):
            raise ValueError("a source world must have unique source-version ids and artifact references")
        cutoff = datetime.fromisoformat(self.information_cutoff)
        if any(datetime.fromisoformat(source.available_at) > cutoff for source in self.sources):
            raise ValueError("source availability is later than its world's information cutoff")
        return self


class SourceWorldBinding(_StrictModel):
    """Frozen preparation-index identity for one separately hashed manifest."""

    source_world_id: Identifier
    predecessor_source_world_id: Identifier | None
    as_of: Timestamp
    manifest_ref: Reference
    manifest_sha256: Digest

    @field_validator("as_of")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        return normalize_timestamp(value)


class SourceWorldIndex(_StrictModel):
    """An ordered preparation chain independent of completed answer reviews."""

    schema_version: Literal["deepr-expert-value-source-index-v1"]
    kind: Literal["deepr.expert.value_source_index"]
    source_worlds: list[SourceWorldBinding] = Field(min_length=2, max_length=64)

    @model_validator(mode="after")
    def validate_chain(self) -> Self:
        seen: set[str] = set()
        predecessor: SourceWorldBinding | None = None
        for world in self.source_worlds:
            expected = None if predecessor is None else predecessor.source_world_id
            if world.source_world_id in seen or world.predecessor_source_world_id != expected:
                raise ValueError("source worlds must form one ordered chain with unique ids")
            if predecessor is not None and datetime.fromisoformat(world.as_of) < datetime.fromisoformat(
                predecessor.as_of
            ):
                raise ValueError("source-world cutoffs must not move backwards")
            seen.add(world.source_world_id)
            predecessor = world
        return self


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("source-world JSON must not contain duplicate object keys")
        result[key] = value
    return result


def _parse_manifest(payload: bytes) -> Any:
    try:
        return json.loads(payload, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, RecursionError) as exc:
        raise ValueError("source-world JSON is not a bounded decodable object") from exc


def _match_digest(payload: bytes, expected: str, field: str) -> None:
    if not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), expected):
        raise ArtifactVerificationError(f"{field} SHA-256 digest does not match")


def _load_world(binding: SourceWorldBinding, root: Path) -> SourceWorldManifest:
    payload = read_bounded_artifact(
        binding.manifest_ref, root, max_bytes=MAX_MANIFEST_BYTES, field_name="source manifest"
    )
    _match_digest(payload, binding.manifest_sha256, "source manifest")
    world = SourceWorldManifest.model_validate(_parse_manifest(payload))
    if (
        world.source_world_id != binding.source_world_id
        or world.predecessor_source_world_id != binding.predecessor_source_world_id
    ):
        raise ValueError("source manifest identity disagrees with its preparation index")
    if datetime.fromisoformat(world.information_cutoff) != datetime.fromisoformat(binding.as_of):
        raise ValueError("source manifest cutoff disagrees with its preparation index")
    return world


def _version_identity(source: SourceVersion) -> tuple[str, int, datetime, datetime]:
    return (
        source.sha256,
        source.bytes,
        datetime.fromisoformat(source.available_at),
        datetime.fromisoformat(source.snapshot_collected_at),
    )


def _validate_version_history(worlds: list[SourceWorldManifest]) -> None:
    versions: dict[str, tuple[str, int, datetime, datetime]] = {}
    clock = worlds[0].clock_basis
    for world in worlds:
        if world.clock_basis != clock:
            raise ValueError("one experiment must use one explicit clock basis")
        for source in world.sources:
            identity = _version_identity(source)
            if versions.setdefault(source.source_version_id, identity) != identity:
                raise ValueError("a repeated source version must retain its bytes and declared timestamps")


def _verify_sources(worlds: list[SourceWorldManifest], root: Path) -> tuple[int, int]:
    reference_count = sum(len(world.sources) for world in worlds)
    if reference_count > MAX_SOURCE_REFERENCES:
        raise ValueError("source inventory exceeds the total reference ceiling")
    checked: dict[str, tuple[str, int]] = {}
    total_bytes = 0
    for world in worlds:
        for source in world.sources:
            key = os.path.normcase(source.artifact_ref)
            expected = source.sha256, source.bytes
            if key in checked:
                if checked[key] != expected:
                    raise ValueError("one source artifact has conflicting byte or digest bindings")
                continue
            if total_bytes + source.bytes > MAX_TOTAL_SOURCE_BYTES:
                raise ValueError("source inventory exceeds the total byte ceiling")
            payload = read_bounded_artifact(
                source.artifact_ref, root, max_bytes=source.bytes, field_name="source artifact"
            )
            if len(payload) != source.bytes:
                raise ArtifactVerificationError("source artifact byte size does not match")
            _match_digest(payload, source.sha256, "source artifact")
            total_bytes += len(payload)
            checked[key] = expected
    return len(checked), total_bytes


def build_source_world_preflight(source: Path, artifact_root: Path) -> dict[str, Any]:
    """Inspect current preparation bytes; never reuse an earlier report as proof."""
    root = artifact_root.resolve(strict=True)
    try:
        reference = source.absolute().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("the preparation index must be inside the selected artifact root") from exc
    index_bytes = read_bounded_artifact(reference, root, max_bytes=MAX_MANIFEST_BYTES, field_name="preparation index")
    index = SourceWorldIndex.model_validate(_parse_manifest(index_bytes))
    worlds = [_load_world(binding, root) for binding in index.source_worlds]
    _validate_version_history(worlds)
    unique_files, total_bytes = _verify_sources(worlds, root)
    return {
        "schema_version": "deepr-expert-value-source-preflight-v1",
        "kind": "deepr.expert.value_source_preflight",
        "status": "structural_preflight_passed",
        "index_sha256": hashlib.sha256(index_bytes).hexdigest(),
        "clock_basis": worlds[0].clock_basis,
        "source_world_count": len(worlds),
        "source_reference_count": sum(len(world.sources) for world in worlds),
        "verified_source_file_count": unique_files,
        "verified_source_bytes": total_bytes,
        "worlds": [
            {
                "source_world_id": binding.source_world_id,
                "information_cutoff": world.information_cutoff,
                "manifest_sha256": binding.manifest_sha256,
                "source_count": len(world.sources),
            }
            for binding, world in zip(index.source_worlds, worlds, strict=True)
        ],
        "declared_availability_within_cutoff": True,
        "historical_availability_independently_verified": False,
        "run_ready": False,
        "execution_authorized": False,
        "semantic_quality_assessed": False,
        "process_isolation_verified": False,
        "review_blinding_verified": False,
        "network_access": False,
        "provider_calls": 0,
        "evidence_writes": 0,
        "cost_usd": 0,
    }
