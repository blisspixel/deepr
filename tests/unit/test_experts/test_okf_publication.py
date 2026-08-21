"""Security tests for transactional OKF directory publication."""

from __future__ import annotations

import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

import deepr.experts.okf_publication as publication
from deepr.experts.okf_publication import OKF_PUBLICATION_MANIFEST, publish_okf_directory

_OKF_VERSION = "0.2"


def _publish(files: dict[str, str], root: Path, *, force: bool = False) -> Path:
    return publish_okf_directory(files, root, force=force, okf_version=_OKF_VERSION)


def _make_directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError as symlink_error:
        if os.name != "nt":
            pytest.skip(f"Directory symlinks are unavailable: {symlink_error}")
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        pytest.skip(f"Directory links are unavailable: {result.stderr or result.stdout}")


def test_publication_manifest_binds_exact_paths_and_content_hashes(tmp_path):
    root = tmp_path / "okf"
    files = {
        "concepts/claim.md": "claim\n",
        "index.md": "index\n",
    }

    _publish(files, root)

    manifest = json.loads((root / OKF_PUBLICATION_MANIFEST).read_text(encoding="utf-8"))
    assert manifest == {
        "schema_version": "deepr-okf-publication-v1",
        "okf_version": _OKF_VERSION,
        "files": [
            {
                "path": relative_path,
                "sha256": sha256(content.encode("utf-8")).hexdigest(),
            }
            for relative_path, content in sorted(files.items())
        ],
    }


@pytest.mark.parametrize(
    "relative_path",
    [
        "C:/claim.md",
        "concept.md:stream",
        "NUL.md",
        "concepts/claim. ",
        "concepts/claim.",
        "concepts/control\x1f.md",
    ],
)
def test_publication_rejects_nonportable_generated_paths(tmp_path, relative_path):
    root = tmp_path / "okf"

    with pytest.raises(ValueError, match="path is not portable"):
        _publish({relative_path: "generated\n"}, root)

    assert not root.exists()


def test_modified_generated_file_requires_force(tmp_path):
    root = tmp_path / "okf"
    _publish({"index.md": "generated\n"}, root)
    (root / "index.md").write_text("hand modified\n", encoding="utf-8")

    with pytest.raises(ValueError, match="modified generated files"):
        _publish({"index.md": "replacement\n"}, root)

    assert (root / "index.md").read_text(encoding="utf-8") == "hand modified\n"
    _publish({"index.md": "replacement\n"}, root, force=True)
    assert (root / "index.md").read_text(encoding="utf-8") == "replacement\n"


def test_marker_text_does_not_authenticate_unmanaged_markdown(tmp_path):
    root = tmp_path / "okf"
    root.mkdir()
    notes = root / "notes.md"
    notes.write_text("<!-- deepr:okf derived-view regenerable -->\nprivate notes\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exact Deepr publication manifest"):
        _publish({"index.md": "generated\n"}, root)

    assert notes.exists()
    _publish({"index.md": "generated\n"}, root, force=True)
    assert not notes.exists()


def test_unmanaged_markdown_in_owned_root_requires_force(tmp_path):
    root = tmp_path / "okf"
    _publish({"index.md": "generated\n"}, root)
    notes = root / "notes.md"
    notes.write_text("private notes\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unmanaged Markdown"):
        _publish({"index.md": "replacement\n"}, root)

    assert notes.read_text(encoding="utf-8") == "private notes\n"
    _publish({"index.md": "replacement\n"}, root, force=True)
    assert not notes.exists()


def test_generated_files_are_written_only_to_sibling_staging_directory(tmp_path, monkeypatch):
    root = tmp_path / "okf"
    written_paths: list[Path] = []
    lock_paths: list[Path] = []
    original_write = publication.atomic_write_text
    original_lock = publication.FileLock

    def record_write(path, content, *args, **kwargs):
        target = Path(path)
        written_paths.append(target)
        return original_write(target, content, *args, **kwargs)

    def record_lock(path, *args, **kwargs):
        lock_paths.append(Path(path))
        return original_lock(path, *args, **kwargs)

    monkeypatch.setattr(publication, "atomic_write_text", record_write)
    monkeypatch.setattr(publication, "FileLock", record_lock)

    _publish({"concepts/claim.md": "claim\n", "index.md": "index\n"}, root)

    assert written_paths
    assert all(root != target and root not in target.parents for target in written_paths)
    assert all(target.relative_to(tmp_path).parts[0].startswith(".okf.staging-") for target in written_paths)
    assert lock_paths and all(tmp_path not in lock_path.parents for lock_path in lock_paths)


def test_publish_failure_restores_exact_prior_root(tmp_path, monkeypatch):
    root = tmp_path / "okf"
    _publish({"index.md": "prior\n"}, root)
    prior_manifest = (root / OKF_PUBLICATION_MANIFEST).read_bytes()
    original_rename = publication._rename_path
    failed = False

    def fail_staging_publish(source: Path, destination: Path) -> None:
        nonlocal failed
        if not failed and ".staging-" in source.name and destination == root:
            failed = True
            raise OSError("injected publication failure")
        original_rename(source, destination)

    monkeypatch.setattr(publication, "_rename_path", fail_staging_publish)

    with pytest.raises(OSError, match="injected publication failure"):
        _publish({"index.md": "replacement\n"}, root)

    assert failed
    assert (root / "index.md").read_text(encoding="utf-8") == "prior\n"
    assert (root / OKF_PUBLICATION_MANIFEST).read_bytes() == prior_manifest
    assert not (tmp_path / ".okf.deepr-okf-recovery").exists()


def test_prior_root_identity_is_verified_before_cleanup(tmp_path, monkeypatch):
    root = tmp_path / "okf"
    _publish({"index.md": "prior\n"}, root)
    original_identity = publication._path_identity
    backup_checks = 0

    def change_cleanup_identity(path: Path):
        nonlocal backup_checks
        identity = original_identity(path)
        if path.name == ".okf.deepr-okf-recovery":
            backup_checks += 1
            if backup_checks == 2:
                return publication._PathIdentity(identity.device, identity.inode + 1, identity.mode)
        return identity

    monkeypatch.setattr(publication, "_path_identity", change_cleanup_identity)

    with pytest.raises(ValueError, match="identity changed before cleanup"):
        _publish({"index.md": "replacement\n"}, root)

    recovery = tmp_path / ".okf.deepr-okf-recovery"
    assert backup_checks == 2
    assert (recovery / "index.md").read_text(encoding="utf-8") == "prior\n"
    assert (root / "index.md").read_text(encoding="utf-8") == "replacement\n"
    _, journal = publication._coordination_paths(root)
    publication._remove_recovery_journal(journal)


def test_next_locked_run_recovers_interrupted_directory_swap(tmp_path, monkeypatch):
    root = tmp_path / "okf"
    recovery = tmp_path / ".okf.deepr-okf-recovery"
    _publish({"index.md": "prior\n"}, root)
    original_rename = publication._rename_path

    def interrupt_staging_publish(source: Path, destination: Path) -> None:
        if ".staging-" in source.name and destination == root:
            raise KeyboardInterrupt
        original_rename(source, destination)

    monkeypatch.setattr(publication, "_rename_path", interrupt_staging_publish)
    with pytest.raises(KeyboardInterrupt):
        _publish({"index.md": "interrupted\n"}, root)

    assert not root.exists()
    assert (recovery / "index.md").read_text(encoding="utf-8") == "prior\n"

    monkeypatch.setattr(publication, "_rename_path", original_rename)
    _publish({"index.md": "replacement\n"}, root)

    assert (root / "index.md").read_text(encoding="utf-8") == "replacement\n"
    assert not recovery.exists()


def test_next_locked_run_finishes_cleanup_after_install_interruption(tmp_path, monkeypatch):
    root = tmp_path / "okf"
    recovery = tmp_path / ".okf.deepr-okf-recovery"
    _publish({"index.md": "prior\n"}, root)
    original_remove = publication._remove_tree_no_follow
    interrupted = False

    def interrupt_recovery_cleanup(path: Path) -> None:
        nonlocal interrupted
        if not interrupted and path == recovery:
            interrupted = True
            raise KeyboardInterrupt
        original_remove(path)

    monkeypatch.setattr(publication, "_remove_tree_no_follow", interrupt_recovery_cleanup)
    with pytest.raises(KeyboardInterrupt):
        _publish({"index.md": "installed\n"}, root)

    assert interrupted
    assert (root / "index.md").read_text(encoding="utf-8") == "installed\n"
    assert (recovery / "index.md").read_text(encoding="utf-8") == "prior\n"

    monkeypatch.setattr(publication, "_remove_tree_no_follow", original_remove)
    _publish({"index.md": "replacement\n"}, root)

    assert (root / "index.md").read_text(encoding="utf-8") == "replacement\n"
    assert not recovery.exists()


@pytest.mark.parametrize("root_name", ["CON", "report.", "report ", "report:stream"])
def test_nonportable_export_root_names_are_rejected(tmp_path, root_name):
    with pytest.raises(ValueError, match="non-portable directory name"):
        _publish({"index.md": "generated\n"}, tmp_path / root_name)


def test_requested_parent_link_is_rejected_before_resolution(tmp_path):
    actual_parent = tmp_path / "actual"
    actual_parent.mkdir()
    linked_parent = tmp_path / "linked"
    _make_directory_link(linked_parent, actual_parent)

    with pytest.raises(ValueError, match="requested OKF output parent"):
        _publish({"index.md": "generated\n"}, linked_parent / "okf")

    assert not (actual_parent / "okf").exists()


def test_coordination_lock_substitution_is_rejected_without_touching_target(tmp_path):
    root = tmp_path / "okf"
    outside = tmp_path / "outside-lock"
    outside.mkdir()
    protected = outside / "protected.txt"
    protected.write_text("keep\n", encoding="utf-8")
    lock_path, _ = publication._coordination_paths(root)
    _make_directory_link(lock_path, outside)
    try:
        with pytest.raises(ValueError, match="coordination lock path"):
            _publish({"index.md": "generated\n"}, root)
    finally:
        publication._remove_tree_no_follow(lock_path)

    assert protected.read_text(encoding="utf-8") == "keep\n"
    assert not root.exists()


def test_recovery_journal_substitution_is_rejected_without_touching_target(tmp_path):
    root = tmp_path / "okf"
    outside = tmp_path / "outside-journal"
    outside.mkdir()
    protected = outside / "protected.txt"
    protected.write_text("keep\n", encoding="utf-8")
    _, journal_path = publication._coordination_paths(root)
    _make_directory_link(journal_path, outside)
    try:
        with pytest.raises(ValueError, match="recovery journal"):
            _publish({"index.md": "generated\n"}, root)
    finally:
        publication._remove_tree_no_follow(journal_path)

    assert protected.read_text(encoding="utf-8") == "keep\n"
    assert not root.exists()


def test_force_removes_symlink_entry_without_touching_external_target(tmp_path):
    root = tmp_path / "okf"
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "protected.txt"
    protected.write_text("keep\n", encoding="utf-8")
    _publish({"index.md": "prior\n"}, root)
    link = root / "external"
    _make_directory_link(link, outside)

    with pytest.raises(ValueError, match="link or special entries"):
        _publish({"index.md": "replacement\n"}, root)

    _publish({"index.md": "replacement\n"}, root, force=True)

    assert not os.path.lexists(link)
    assert protected.read_text(encoding="utf-8") == "keep\n"


def test_force_replaces_root_symlink_without_touching_external_target(tmp_path):
    root = tmp_path / "okf"
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "protected.txt"
    protected.write_text("keep\n", encoding="utf-8")
    _make_directory_link(root, outside)

    _publish({"index.md": "generated\n"}, root, force=True)

    assert root.is_dir()
    assert not root.is_symlink()
    assert not root.is_junction()
    assert protected.read_text(encoding="utf-8") == "keep\n"
