"""Write one selected source world into a new, independent worker input root.

This is the writing counterpart of ``expert_value_source_copy``. It copies only
the sources declared for the selected world, under neutral content-addressed
names, and publishes the manifest last. The existing read-only verifier then
checks the result. An interrupted copy has no manifest and fails verification;
it is never resumed, repaired, deleted, or overwritten here.

Copying files does not confine a process or show that a worker used them.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from deepr.evals.expert_value_artifacts import read_bounded_artifact
from deepr.evals.expert_value_source_copy import source_copy_manifest, verify_source_world_copy
from deepr.evals.expert_value_sources import _match_digest, load_source_world_preparation


def _write_exclusive(path: Path, payload: bytes) -> None:
    """Create one new regular file; an existing entry is a refusal, not a merge."""
    with open(path, "xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def materialize_source_world_copy(
    source: Path, artifact_root: Path, *, world_id: str, output_root: Path
) -> dict[str, Any]:
    """Copy one verified world into ``output_root`` and verify the copy.

    ``output_root`` must not exist and must not overlap the artifact root. The
    preparation index and every source byte are revalidated at copy time.
    """
    root = artifact_root.resolve(strict=True)
    target = output_root.absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError("materialization output root must be new")
    parent = target.parent.resolve(strict=True)
    resolved_target = parent / target.name
    if resolved_target.is_relative_to(root) or root.is_relative_to(resolved_target):
        raise ValueError("materialization output and artifact roots must not overlap")
    _, _, worlds, _, _ = load_source_world_preparation(source, root)
    world = next((item for item in worlds if item.source_world_id == world_id), None)
    if world is None:
        raise ValueError("selected world is not in the preparation index")
    manifest = source_copy_manifest(world)
    # mkdir without exist_ok reserves the root; a concurrent writer loses here.
    resolved_target.mkdir()
    (resolved_target / "sources").mkdir()
    for original, copied in zip(world.sources, manifest.sources, strict=True):
        payload = read_bounded_artifact(
            original.artifact_ref, root, max_bytes=original.bytes, field_name="source artifact"
        )
        _match_digest(payload, original.sha256, "source artifact")
        _write_exclusive(resolved_target / copied.artifact_ref, payload)
    manifest_bytes = (json.dumps(manifest.model_dump(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_exclusive(resolved_target / "manifest.json", manifest_bytes)
    report = verify_source_world_copy(source, root, world_id=world_id, copy_root=resolved_target)
    report["materialized"] = True
    report["evidence_writes"] = len(manifest.sources) + 1
    report["copy_manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    return report


def read_source_world_copy(copy_root: Path) -> list[tuple[str, str]]:
    """Return ``(sha256, text)`` pairs in manifest order from a verified copy.

    Callers must verify the copy first. Digests are rechecked on read so a
    worker never renders bytes that differ from its declared input.
    """
    manifest = json.loads((copy_root / "manifest.json").read_text(encoding="utf-8"))
    material: list[tuple[str, str]] = []
    for item in manifest["sources"]:
        payload = read_bounded_artifact(
            item["artifact_ref"], copy_root, max_bytes=int(item["bytes"]), field_name="copied source"
        )
        _match_digest(payload, item["sha256"], "copied source")
        material.append((item["sha256"], payload.decode("utf-8")))
    return material


__all__ = ["materialize_source_world_copy", "read_source_world_copy"]
