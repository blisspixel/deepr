"""Read-only verification of the exact source inventory delivered to one worker.

A separate regular-file copy prevents accidental sharing of mutable input files.
It does not confine a process or establish that a worker actually used the files.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any

from deepr.evals.expert_value_artifacts import ArtifactVerificationError, read_bounded_artifact
from deepr.evals.expert_value_sources import (
    MAX_MANIFEST_BYTES,
    SourceWorldManifest,
    _match_digest,
    _parse_manifest,
    load_source_world_preparation,
)


def source_copy_manifest(world: SourceWorldManifest) -> SourceWorldManifest:
    """Describe one copy without revealing organizer paths or altering sources."""
    payload = world.model_dump()
    for index, source in enumerate(payload["sources"]):
        source["artifact_ref"] = f"sources/{index:04d}-{source['sha256']}.txt"
    return SourceWorldManifest.model_validate(payload)


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink


def _inventory(path: Path, expected: dict[str, bool]) -> dict[str, tuple[int, int, int, int, int]]:
    """Bound enumeration to expected entries and never descend into extra paths."""
    root_info = path.lstat()
    if _is_link(root_info) or not stat.S_ISDIR(root_info.st_mode):
        raise ArtifactVerificationError("source copy directories must be ordinary directories without links")
    observed = {".": _identity(root_info)}
    with os.scandir(path) as entries:
        for entry in entries:
            if entry.name not in expected:
                raise ArtifactVerificationError("source copy contains an unexpected entry")
            # DirEntry.stat reports zero link counts and inode ids on Windows.
            # lstat obtains the current file identity without following links.
            info = Path(entry.path).lstat()
            directory = expected[entry.name]
            correct_kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
            if _is_link(info) or not correct_kind:
                raise ArtifactVerificationError("source copy contains a link or non-regular entry")
            if not directory and info.st_nlink != 1:
                raise ArtifactVerificationError("source copy files must not share a hard link")
            observed[entry.name] = _identity(info)
    if len(observed) != len(expected) + 1:
        raise ArtifactVerificationError("source copy is incomplete")
    return observed


def verify_source_world_copy(source: Path, artifact_root: Path, *, world_id: str, copy_root: Path) -> dict[str, Any]:
    """Revalidate the organizer inputs and selected copy without writes or calls."""
    root = artifact_root.resolve(strict=True)
    selected = copy_root.absolute()
    selected_resolved = selected.resolve(strict=True)
    if selected_resolved.is_relative_to(root) or root.is_relative_to(selected_resolved):
        raise ArtifactVerificationError("source copy and artifact roots must not overlap")
    index_bytes, index, worlds, _, _ = load_source_world_preparation(source, root)
    world = next((item for item in worlds if item.source_world_id == world_id), None)
    if world is None:
        raise ValueError("selected world is not in the preparation index")
    expected = source_copy_manifest(world)
    top_entries = {"manifest.json": False, "sources": True}
    source_entries = {Path(item.artifact_ref).name: False for item in expected.sources}
    before_top = _inventory(selected, top_entries)
    before_sources = _inventory(selected / "sources", source_entries)
    manifest_bytes = read_bounded_artifact(
        "manifest.json", selected, max_bytes=MAX_MANIFEST_BYTES, field_name="copy manifest", require_single_link=True
    )
    actual = SourceWorldManifest.model_validate(_parse_manifest(manifest_bytes))
    if actual != expected:
        raise ArtifactVerificationError("copy manifest does not match the selected source world")
    for item in actual.sources:
        payload = read_bounded_artifact(
            item.artifact_ref,
            selected,
            max_bytes=item.bytes,
            field_name="copied source",
            require_single_link=True,
        )
        if len(payload) != item.bytes:
            raise ArtifactVerificationError("copied source byte size does not match")
        _match_digest(payload, item.sha256, "copied source")
    after_sources = _inventory(selected / "sources", source_entries)
    after_top = _inventory(selected, top_entries)
    if before_top != after_top or before_sources != after_sources:
        raise ArtifactVerificationError("source copy changed during verification")
    binding = next(item for item in index.source_worlds if item.source_world_id == world_id)
    return {
        "schema_version": "deepr-expert-value-source-copy-v1",
        "kind": "deepr.expert.value_source_copy",
        "status": "source_copy_verified",
        "index_sha256": hashlib.sha256(index_bytes).hexdigest(),
        "source_world_id": world.source_world_id,
        "information_cutoff": world.information_cutoff,
        "clock_basis": world.clock_basis,
        "original_manifest_sha256": binding.manifest_sha256,
        "copy_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "verified_source_file_count": len(actual.sources),
        "verified_source_bytes": sum(item.bytes for item in actual.sources),
        "exact_inventory_verified": True,
        "independent_regular_files_verified": True,
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
