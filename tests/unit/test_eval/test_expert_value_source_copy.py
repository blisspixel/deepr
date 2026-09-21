"""Verify worker source copies without trusting organizer-only preflight receipts."""

from __future__ import annotations

import copy
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from deepr.evals import expert_value_source_copy as copies
from deepr.evals.expert_value_artifacts import read_bounded_artifact
from tests.unit.test_eval.test_expert_value_sources import Bundle, _tree, _write_json


def make_copy(bundle: Bundle, destination: Path, world_index: int = 0) -> Path:
    """Fixture construction is separate from the production read-only verifier."""
    world = copy.deepcopy(bundle.worlds[world_index])
    (destination / "sources").mkdir(parents=True)
    for index, source in enumerate(world["sources"]):
        data = (bundle.root / source["artifact_ref"]).read_bytes()
        source["artifact_ref"] = f"sources/{index:04d}-{source['sha256']}.txt"
        (destination / source["artifact_ref"]).write_bytes(data)
    _write_json(destination / "manifest.json", world)
    return destination


def verify(bundle: Bundle, destination: Path, world_id: str = "world-1"):
    return copies.verify_source_world_copy(bundle.index_path, bundle.root, world_id=world_id, copy_root=destination)


def test_four_copies_have_identical_bytes_and_no_shared_mutable_files(tmp_path):
    bundle = Bundle(tmp_path / "organizer")
    (bundle.root / "private-review-key.json").write_text("organizer only")
    before = _tree(bundle.root)
    destinations = [make_copy(bundle, tmp_path / f"arm-{arm}") for arm in range(4)]
    inventories = [_tree(path) for path in destinations]
    reports = [verify(bundle, path) for path in destinations]
    assert all(tree == inventories[0] for tree in inventories)
    assert all(report == reports[0] for report in reports)
    assert _tree(bundle.root) == before
    for destination in destinations:
        assert _tree(destination) == inventories[0]
    report = reports[0]
    assert report["verified_source_file_count"] == 1
    assert report["verified_source_bytes"] == bundle.files[0].stat().st_size
    assert report["exact_inventory_verified"] is True
    assert report["independent_regular_files_verified"] is True
    assert report["provider_calls"] == report["evidence_writes"] == report["cost_usd"] == 0
    for field in (
        "historical_availability_independently_verified",
        "run_ready",
        "execution_authorized",
        "semantic_quality_assessed",
        "process_isolation_verified",
        "review_blinding_verified",
        "network_access",
    ):
        assert report[field] is False
    first_source = next((destinations[0] / "sources").iterdir())
    first_source.write_bytes(b"changed worker input")
    assert _tree(destinations[1]) == inventories[0]
    assert _tree(bundle.root) == before
    with pytest.raises(ValueError):
        verify(bundle, destinations[0])


@pytest.mark.parametrize("extra", ["private-review-key.json", "future-world", "sources/extra.txt", "sources/subdir"])
def test_extra_files_and_directories_are_refused_without_removal(tmp_path, extra):
    bundle = Bundle(tmp_path / "organizer")
    destination = make_copy(bundle, tmp_path / "worker")
    target = destination / extra
    if target.suffix:
        target.write_bytes(b"unexpected")
    else:
        target.mkdir()
    before = _tree(tmp_path)
    with pytest.raises(ValueError, match="unexpected"):
        verify(bundle, destination)
    assert _tree(tmp_path) == before
    assert target.exists()


@pytest.mark.parametrize("removed", ["manifest", "source", "sources"])
def test_incomplete_copies_never_pass_as_completed_inputs(tmp_path, removed):
    bundle = Bundle(tmp_path / "organizer")
    destination = make_copy(bundle, tmp_path / "worker")
    if removed == "manifest":
        (destination / "manifest.json").unlink()
    else:
        next((destination / "sources").iterdir()).unlink()
        if removed == "sources":
            (destination / "sources").rmdir()
    with pytest.raises(ValueError, match="incomplete"):
        verify(bundle, destination)


@pytest.mark.parametrize(
    "field,value", [("information_cutoff", "2026-01-19T00:00:00Z"), ("clock_basis", "historical_assertion")]
)
def test_copy_metadata_must_match_the_selected_world(tmp_path, field, value):
    bundle = Bundle(tmp_path / "organizer")
    destination = make_copy(bundle, tmp_path / "worker")
    path = destination / "manifest.json"
    payload = json.loads(path.read_bytes())
    payload[field] = value
    _write_json(path, payload)
    with pytest.raises(ValueError, match="does not match"):
        verify(bundle, destination)


def test_wrong_world_duplicate_keys_and_non_neutral_names_are_refused(tmp_path):
    bundle = Bundle(tmp_path / "organizer")
    destination = make_copy(bundle, tmp_path / "worker", world_index=1)
    with pytest.raises(ValueError, match="unexpected entry"):
        verify(bundle, destination)
    with pytest.raises(ValueError, match="not in the preparation index"):
        verify(bundle, destination, "world-missing")
    path = destination / "manifest.json"
    original = path.read_bytes()
    path.write_bytes(original.replace(b"{", b'{"clock_basis":"synthetic",', 1))
    with pytest.raises(ValueError, match="duplicate object keys"):
        verify(bundle, destination, "world-2")
    payload = json.loads(original)
    payload["sources"][0]["artifact_ref"] = "sources/answer-key.txt"
    _write_json(path, payload)
    with pytest.raises(ValueError, match="does not match"):
        verify(bundle, destination, "world-2")


@pytest.mark.parametrize("change", ["same_size", "shorter", "larger", "original"])
def test_every_verification_rechecks_original_and_copy_bytes(tmp_path, change):
    bundle = Bundle(tmp_path / "organizer")
    destination = make_copy(bundle, tmp_path / "worker")
    verify(bundle, destination)
    source = bundle.files[0] if change == "original" else next((destination / "sources").iterdir())
    original = source.read_bytes()
    data = original.replace(b"version 1", b"version 9")
    if change == "shorter":
        data = original[:-1]
    elif change == "larger":
        data = original + b"extra"
    source.write_bytes(data)
    before = _tree(tmp_path)
    with pytest.raises(ValueError):
        verify(bundle, destination)
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("location", ["same_root", "inside", "parent"])
def test_organizer_and_copy_roots_must_be_disjoint(tmp_path, location):
    bundle = Bundle(tmp_path / "organizer")
    destination = {"same_root": bundle.root, "inside": bundle.root / "worker", "parent": tmp_path}[location]
    destination.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match="must not overlap"):
        verify(bundle, destination)


@pytest.mark.parametrize("target", ["source", "manifest"])
def test_hard_links_are_not_independent_copies(tmp_path, target):
    bundle = Bundle(tmp_path / "organizer")
    destination = make_copy(bundle, tmp_path / "worker")
    path = destination / "manifest.json" if target == "manifest" else next((destination / "sources").iterdir())
    os.link(path, tmp_path / "shared-input")
    with pytest.raises(ValueError, match="hard link"):
        verify(bundle, destination)


def test_inventory_mutation_during_reads_is_detected(tmp_path, monkeypatch):
    bundle = Bundle(tmp_path / "organizer")
    destination = make_copy(bundle, tmp_path / "worker")
    read = copies.read_bounded_artifact

    def mutate(reference, root, **kwargs):
        payload = read(reference, root, **kwargs)
        if reference.startswith("sources/"):
            (destination / reference).write_bytes(b"changed after reading")
        return payload

    monkeypatch.setattr(copies, "read_bounded_artifact", mutate)
    with pytest.raises(ValueError, match="changed during verification"):
        verify(bundle, destination)


@pytest.mark.parametrize("location", ["root", "sources", "source", "manifest"])
@pytest.mark.parametrize("kind", ["symlink", "junction", "fifo"])
def test_inventory_refuses_links_and_special_files_before_reading(tmp_path, monkeypatch, location, kind):
    bundle = Bundle(tmp_path / "organizer")
    destination = make_copy(bundle, tmp_path / "worker")
    target = {
        "root": destination,
        "sources": destination / "sources",
        "source": next((destination / "sources").iterdir()),
        "manifest": destination / "manifest.json",
    }[location]
    original = Path.lstat
    fake = SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0)
    if kind == "symlink":
        fake.st_mode = stat.S_IFLNK
    elif kind == "junction":
        monkeypatch.setattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024, raising=False)
        fake.st_file_attributes = 1024
    else:
        fake.st_mode = stat.S_IFIFO
    monkeypatch.setattr(Path, "lstat", lambda self, *a, **kw: fake if self == target else original(self, *a, **kw))

    def forbidden_read(*args, **kwargs):
        pytest.fail("an invalid input inventory must be refused before copy reads")

    monkeypatch.setattr(copies, "read_bounded_artifact", forbidden_read)
    with pytest.raises(ValueError, match=r"without links|non-regular"):
        verify(bundle, destination)


def test_sources_directory_cannot_be_a_file(tmp_path):
    bundle = Bundle(tmp_path / "organizer")
    destination = make_copy(bundle, tmp_path / "worker")
    next((destination / "sources").iterdir()).unlink()
    (destination / "sources").rmdir()
    (destination / "sources").write_text("not a directory")
    with pytest.raises(ValueError, match="non-regular"):
        verify(bundle, destination)


def test_single_link_requirement_is_opt_in_for_existing_artifact_readers(tmp_path):
    path = tmp_path / "source.txt"
    path.write_bytes(b"source")
    os.link(path, tmp_path / "another-name.txt")
    assert read_bounded_artifact(path.name, tmp_path, max_bytes=6) == b"source"
    with pytest.raises(ValueError, match="hard link"):
        read_bounded_artifact(path.name, tmp_path, max_bytes=6, require_single_link=True)


@pytest.mark.parametrize("link_at_fstat", [1, 2])
def test_link_created_after_path_inspection_is_refused(tmp_path, monkeypatch, link_at_fstat):
    path = tmp_path / "source.txt"
    path.write_bytes(b"source")
    original = os.fstat
    calls = 0

    def linking_stat(fd):
        nonlocal calls
        calls += 1
        if calls == link_at_fstat:
            os.link(path, tmp_path / "linked-during-read.txt")
        return original(fd)

    monkeypatch.setattr(os, "fstat", linking_stat)
    with pytest.raises(ValueError, match="hard link"):
        read_bounded_artifact(path.name, tmp_path, max_bytes=6, require_single_link=True)
