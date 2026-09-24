"""Materialize one selected world into a new independent worker input root."""

from __future__ import annotations

from pathlib import Path

import pytest

from deepr.evals.expert_value_artifacts import ArtifactVerificationError
from deepr.evals.expert_value_materialize import materialize_source_world_copy, read_source_world_copy
from tests.unit.test_eval.test_expert_value_sources import Bundle, _tree


def test_materialized_copies_are_verified_independent_and_world_scoped(tmp_path: Path) -> None:
    bundle = Bundle(tmp_path / "organizer")
    (bundle.root / "private-review-key.json").write_text("organizer only")
    before = _tree(bundle.root)
    first = materialize_source_world_copy(
        bundle.index_path, bundle.root, world_id="world-1", output_root=tmp_path / "a"
    )
    second = materialize_source_world_copy(
        bundle.index_path, bundle.root, world_id="world-2", output_root=tmp_path / "b"
    )
    assert first["status"] == second["status"] == "source_copy_verified"
    assert first["materialized"] is True
    assert first["verified_source_file_count"] == 1
    assert second["verified_source_file_count"] == 2
    assert first["evidence_writes"] == 2
    assert _tree(bundle.root) == before
    # Later-world sources and organizer files never enter an earlier world's copy.
    copied = _tree(tmp_path / "a")
    assert set(copied) == {"manifest.json", f"sources/0000-{bundle.worlds[0]['sources'][0]['sha256']}.txt"}
    assert b"organizer only" not in b"".join(copied.values())
    assert [text for _, text in read_source_world_copy(tmp_path / "b")] == [
        "Synthetic source version 1.\n",
        "Synthetic source version 2.\n",
    ]


def test_existing_output_root_is_refused_without_changes(tmp_path: Path) -> None:
    bundle = Bundle(tmp_path / "organizer")
    target = tmp_path / "existing"
    target.mkdir()
    (target / "keep.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        materialize_source_world_copy(bundle.index_path, bundle.root, world_id="world-1", output_root=target)
    assert _tree(target) == {"keep.txt": b"keep"}


def test_output_inside_artifact_root_and_unknown_world_are_refused(tmp_path: Path) -> None:
    bundle = Bundle(tmp_path / "organizer")
    with pytest.raises(ValueError, match="overlap"):
        materialize_source_world_copy(
            bundle.index_path, bundle.root, world_id="world-1", output_root=bundle.root / "copy"
        )
    with pytest.raises(ValueError, match="not in the preparation index"):
        materialize_source_world_copy(bundle.index_path, bundle.root, world_id="world-9", output_root=tmp_path / "x")
    assert not (tmp_path / "x").exists()


def test_source_changed_after_preparation_is_refused_and_leaves_no_manifest(tmp_path: Path) -> None:
    bundle = Bundle(tmp_path / "organizer")
    bundle.files[0].write_bytes(b"Tampered source version 1.\n")
    with pytest.raises((ArtifactVerificationError, ValueError)):
        materialize_source_world_copy(bundle.index_path, bundle.root, world_id="world-1", output_root=tmp_path / "c")
    assert not (tmp_path / "c" / "manifest.json").exists()


def test_copy_changed_after_materialization_fails_on_read(tmp_path: Path) -> None:
    bundle = Bundle(tmp_path / "organizer")
    materialize_source_world_copy(bundle.index_path, bundle.root, world_id="world-1", output_root=tmp_path / "d")
    next((tmp_path / "d" / "sources").iterdir()).write_bytes(b"Synthetic source version X.\n")
    with pytest.raises(ArtifactVerificationError):
        read_source_world_copy(tmp_path / "d")
