"""Source-world preparation checks with synthetic files and no provider access."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from deepr.evals import expert_value_artifacts as artifacts
from deepr.evals import expert_value_sources as sources


def _write_json(path: Path, payload: Any) -> str:
    data = (json.dumps(payload, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


class Bundle:
    def __init__(self, root: Path):
        self.root = root
        self.index_path = root / "index.json"
        folder = root / "source files"
        folder.mkdir(parents=True)
        self.files = [folder / "source  one.txt", folder / "source-two.txt"]
        entries = []
        for number, path in enumerate(self.files, 1):
            data = f"Synthetic source version {number}.\n".encode()
            path.write_bytes(data)
            entries.append(
                {
                    "source_version_id": f"version-{number}",
                    "artifact_ref": path.relative_to(root).as_posix(),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                    "available_at": f"2026-0{number}-01T00:00:00Z",
                    "snapshot_collected_at": "2026-09-05T00:00:00Z",
                }
            )
        self.worlds = [
            {
                "schema_version": "deepr-expert-value-source-world-v1",
                "kind": "deepr.expert.value_source_world",
                "source_world_id": f"world-{number}",
                "predecessor_source_world_id": None if number == 1 else "world-1",
                "information_cutoff": f"2026-0{number}-20T00:00:00Z",
                "clock_basis": "synthetic",
                "sources": copy.deepcopy(entries[:number]),
            }
            for number in (1, 2)
        ]
        self.index = {
            "schema_version": "deepr-expert-value-source-index-v1",
            "kind": "deepr.expert.value_source_index",
            "source_worlds": [
                {
                    "source_world_id": world["source_world_id"],
                    "predecessor_source_world_id": world["predecessor_source_world_id"],
                    "as_of": world["information_cutoff"],
                    "manifest_ref": f"worlds/{world['source_world_id']}.json",
                    "manifest_sha256": "0" * 64,
                }
                for world in self.worlds
            ],
        }
        self.save()

    def save(self):
        for binding, world in zip(self.index["source_worlds"], self.worlds, strict=True):
            binding["manifest_sha256"] = _write_json(self.root / binding["manifest_ref"], world)
        _write_json(self.index_path, self.index)

    def check(self):
        return sources.build_source_world_preflight(self.index_path, self.root)


def _tree(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_nested_source_preflight_is_read_only_and_not_execution_authority(tmp_path):
    bundle = Bundle(tmp_path)
    before = _tree(tmp_path)
    result = bundle.check()
    assert result["source_world_count"] == 2
    assert result["source_reference_count"] == 3
    assert result["verified_source_file_count"] == 2
    assert result["verified_source_bytes"] == sum(len(path.read_bytes()) for path in bundle.files)
    assert result["declared_availability_within_cutoff"] is True
    assert result["historical_availability_independently_verified"] is False
    for name in (
        "run_ready",
        "execution_authorized",
        "semantic_quality_assessed",
        "process_isolation_verified",
        "review_blinding_verified",
        "network_access",
    ):
        assert result[name] is False
    assert result["evidence_writes"] == result["provider_calls"] == result["cost_usd"] == 0
    assert _tree(tmp_path) == before


def test_changed_nested_bytes_refuse_even_when_all_outer_manifest_hashes_match(tmp_path):
    bundle = Bundle(tmp_path)
    bundle.check()
    before = bundle.files[0].read_bytes()
    bundle.files[0].write_bytes(before.replace(b"version 1", b"version 9"))
    with pytest.raises(ValueError, match="digest does not match"):
        bundle.check()


@pytest.mark.parametrize(
    "field,value",
    [
        ("available_at", "2026-02-01T00:00:00Z"),
        ("available_at", "2026-01-01T00:00:00"),
        ("snapshot_collected_at", "yesterday"),
        ("bytes", True),
        ("bytes", 0),
        ("sha256", "A" * 64),
        ("role_draft", "supporting"),
    ],
)
def test_source_metadata_rejects_ambiguous_timing_size_and_organizer_labels(tmp_path, field, value):
    bundle = Bundle(tmp_path)
    bundle.worlds[0]["sources"][0][field] = value
    bundle.save()
    before = _tree(tmp_path)
    with pytest.raises(ValueError):
        bundle.check()
    assert _tree(tmp_path) == before


def test_world_time_and_collection_time_are_distinct_and_offsets_compare_as_instants(tmp_path):
    bundle = Bundle(tmp_path)
    bundle.worlds[0]["information_cutoff"] = "2026-01-19T16:00:00-08:00"
    bundle.worlds[1]["sources"][0]["available_at"] = "2025-12-31T16:00:00-08:00"
    bundle.save()
    assert bundle.check()["clock_basis"] == "synthetic"


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "1" * 64),
        ("available_at", "2026-01-02T00:00:00Z"),
        ("snapshot_collected_at", "2026-09-06T00:00:00Z"),
        ("bytes", 1),
    ],
)
def test_source_version_identity_cannot_change_in_a_successor_world(tmp_path, field, value):
    bundle = Bundle(tmp_path)
    bundle.worlds[1]["sources"][0][field] = value
    bundle.save()
    with pytest.raises(ValueError, match="repeated source version"):
        bundle.check()


@pytest.mark.parametrize(
    "change",
    [
        "world_identity",
        "world_cutoff",
        "mixed_clocks",
        "broken_chain",
        "duplicate_id",
        "duplicate_source",
        "duplicate_path",
        "backwards_cutoff",
    ],
)
def test_source_world_chain_and_inventory_bindings_are_checked(tmp_path, change):
    bundle = Bundle(tmp_path)
    if change == "world_identity":
        bundle.worlds[0]["source_world_id"] = "different"
    elif change == "world_cutoff":
        bundle.worlds[0]["information_cutoff"] = "2026-01-21T00:00:00Z"
    elif change == "mixed_clocks":
        bundle.worlds[1]["clock_basis"] = "historical_assertion"
    elif change == "broken_chain":
        bundle.index["source_worlds"][1]["predecessor_source_world_id"] = None
    elif change == "duplicate_id":
        bundle.index["source_worlds"][1]["source_world_id"] = "world-1"
    elif change == "duplicate_source":
        bundle.worlds[1]["sources"].append(copy.deepcopy(bundle.worlds[1]["sources"][0]))
    elif change == "duplicate_path":
        bundle.worlds[1]["sources"][1]["artifact_ref"] = bundle.worlds[1]["sources"][0]["artifact_ref"]
    else:
        bundle.index["source_worlds"][1]["as_of"] = "2025-01-01T00:00:00Z"
    bundle.save()
    with pytest.raises(ValueError):
        bundle.check()


@pytest.mark.parametrize("location", ["index", "world"])
def test_duplicate_json_keys_are_refused_even_with_matching_outer_hash(tmp_path, location):
    bundle = Bundle(tmp_path)
    path = bundle.index_path if location == "index" else tmp_path / "worlds/world-1.json"
    data = path.read_bytes().replace(b"{", b'{"schema_version":"misleading",', 1)
    path.write_bytes(data)
    if location == "world":
        bundle.index["source_worlds"][0]["manifest_sha256"] = hashlib.sha256(data).hexdigest()
        _write_json(bundle.index_path, bundle.index)
    with pytest.raises(ValueError, match="duplicate object keys"):
        bundle.check()


@pytest.mark.parametrize(
    "reference",
    [
        "../outside.txt",
        "/outside.txt",
        "C:/outside.txt",
        "https://example.test/source",
        "source files/source  one.txt:stream",
        "source files\\source  one.txt",
        "source files/./source  one.txt",
        "source files//source  one.txt",
        "missing.txt",
    ],
)
def test_nested_references_refuse_escapes_aliases_and_missing_files(tmp_path, reference):
    bundle = Bundle(tmp_path)
    bundle.worlds[0]["sources"][0]["artifact_ref"] = reference
    bundle.save()
    with pytest.raises(ValueError):
        bundle.check()


@pytest.mark.parametrize(
    "ceiling,value", [("MAX_MANIFEST_BYTES", 12), ("MAX_TOTAL_SOURCE_BYTES", 1), ("MAX_SOURCE_REFERENCES", 1)]
)
def test_aggregate_and_manifest_ceilings_are_binding(tmp_path, monkeypatch, ceiling, value):
    bundle = Bundle(tmp_path)
    monkeypatch.setattr(sources, ceiling, value)
    with pytest.raises(ValueError, match="ceiling"):
        bundle.check()


def test_declared_byte_size_cannot_hide_a_shorter_file(tmp_path):
    bundle = Bundle(tmp_path)
    bundle.files[0].write_bytes(b"short")
    with pytest.raises(ValueError, match="byte size"):
        bundle.check()


@pytest.mark.parametrize("kind", ["symlink", "junction", "fifo"])
def test_reader_refuses_links_junctions_and_special_files_before_open(tmp_path, monkeypatch, kind):
    path = tmp_path / "source.txt"
    path.write_bytes(b"source")
    original = Path.lstat
    info = original(path)
    fake = SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0)
    if kind == "symlink":
        fake.st_mode = stat.S_IFLNK
    elif kind == "junction":
        monkeypatch.setattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024, raising=False)
        fake.st_file_attributes = 1024
    else:
        fake.st_mode = stat.S_IFIFO
    monkeypatch.setattr(
        Path, "lstat", lambda self, *args, **kwargs: fake if self == path else original(self, *args, **kwargs)
    )

    def forbidden_open(*args, **kwargs):
        pytest.fail("a nonregular or linked reference must be refused before opening")

    monkeypatch.setattr(os, "open", forbidden_open)
    with pytest.raises(ValueError):
        artifacts.read_bounded_artifact(path.name, tmp_path, max_bytes=info.st_size)


def test_reader_detects_a_real_mutation_during_read(tmp_path, monkeypatch):
    path = tmp_path / "source.txt"
    path.write_bytes(b"original")
    original = os.fdopen

    class ChangingFile:
        def __init__(self, *args, **kwargs):
            self.file = original(*args, **kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.file.close()

        def fileno(self):
            return self.file.fileno()

        def read(self, size):
            result = self.file.read(size)
            path.write_bytes(b"changed during read")
            return result

    monkeypatch.setattr(os, "fdopen", ChangingFile)
    with pytest.raises(ValueError, match="changed during reading"):
        artifacts.read_bounded_artifact(path.name, tmp_path, max_bytes=100)


def test_index_must_be_inside_its_selected_root(tmp_path):
    bundle = Bundle(tmp_path / "inside")
    outside = tmp_path / "outside.json"
    outside.write_bytes(bundle.index_path.read_bytes())
    with pytest.raises(ValueError, match="inside"):
        sources.build_source_world_preflight(outside, bundle.root)
