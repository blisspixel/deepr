"""Transactional publication for dedicated Deepr OKF export roots.

An OKF export root is a generated artifact, not a mixed-purpose directory. Each
publication carries an exact manifest of generated relative paths and content
hashes. Replacement is performed by sibling directory renames so no generated
file is written or deleted through a previously checked mutable parent path.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from filelock import FileLock
from filelock import Timeout as FileLockTimeout

from deepr.experts.okf_contract import portable_relative_path_failure
from deepr.utils.atomic_io import atomic_write_text

OKF_PUBLICATION_SCHEMA_VERSION = "deepr-okf-publication-v1"
OKF_PUBLICATION_MANIFEST = ".deepr-okf-manifest.json"
_RECOVERY_SCHEMA_VERSION = "deepr-okf-recovery-v1"
_MAX_MANIFEST_BYTES = 1024 * 1024
_WINDOWS_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class OKFPublicationError(ValueError):
    """An OKF directory could not be published without risking user data."""


@dataclass(frozen=True)
class _PathIdentity:
    device: int
    inode: int
    mode: int


@dataclass(frozen=True)
class _TreeInventory:
    files: dict[str, Path]
    directories: frozenset[str]
    links: frozenset[str]


@dataclass(frozen=True)
class _RecoveryRecord:
    target: str
    prior: _PathIdentity
    staged: _PathIdentity


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _is_link_like(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _path_identity(path: Path) -> _PathIdentity:
    result = os.lstat(path)
    return _PathIdentity(result.st_dev, result.st_ino, result.st_mode)


def _rename_path(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _sha256_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise OKFPublicationError("OKF publication manifest contains an invalid relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise OKFPublicationError(f"OKF publication manifest path escapes its root: {value!r}")
    if path_failure := portable_relative_path_failure(value):
        raise OKFPublicationError(f"OKF publication manifest path is not portable: {value!r}: {path_failure}")
    if value == OKF_PUBLICATION_MANIFEST:
        raise OKFPublicationError("OKF publication manifest cannot list itself as generated content")
    return path.as_posix()


def _manifest_payload(files: Mapping[str, str], *, okf_version: str) -> tuple[dict[str, Any], str]:
    entries = []
    collision_keys: set[str] = set()
    for raw_path, content in sorted(files.items()):
        relative_path = _validated_relative_path(raw_path)
        collision_key = relative_path.casefold()
        if collision_key in collision_keys:
            raise OKFPublicationError(f"OKF publication paths collide portably: {relative_path!r}")
        collision_keys.add(collision_key)
        entries.append(
            {
                "path": relative_path,
                "sha256": _sha256_bytes(content.encode("utf-8")),
            }
        )
    payload = {
        "schema_version": OKF_PUBLICATION_SCHEMA_VERSION,
        "okf_version": okf_version,
        "files": entries,
    }
    return payload, json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _read_manifest_payload(root: Path) -> dict[str, Any]:
    manifest_path = root / OKF_PUBLICATION_MANIFEST
    if not _lexists(manifest_path) or _is_link_like(manifest_path) or not manifest_path.is_file():
        raise OKFPublicationError(
            "OKF export root is not owned by an exact Deepr publication manifest. "
            "Use --force only to replace the entire dedicated export root."
        )
    if manifest_path.stat().st_size > _MAX_MANIFEST_BYTES:
        raise OKFPublicationError("OKF publication manifest exceeds the supported size limit")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OKFPublicationError(f"OKF publication manifest is unreadable: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "okf_version", "files"}:
        raise OKFPublicationError("OKF publication manifest has an unsupported structure")
    return payload


def _manifest_entries(entries: Any) -> dict[str, str]:
    if not isinstance(entries, list):
        raise OKFPublicationError("OKF publication manifest files must be a list")
    expected: dict[str, str] = {}
    collision_keys: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise OKFPublicationError("OKF publication manifest contains an invalid file entry")
        relative_path = _validated_relative_path(entry.get("path"))
        digest = entry.get("sha256")
        collision_key = relative_path.casefold()
        if collision_key in collision_keys or not isinstance(digest, str) or len(digest) != 64:
            raise OKFPublicationError("OKF publication manifest contains a duplicate path or invalid hash")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise OKFPublicationError("OKF publication manifest contains a non-hexadecimal hash") from exc
        collision_keys.add(collision_key)
        expected[relative_path] = digest.lower()
    return expected


def _parse_manifest(root: Path, *, okf_version: str) -> dict[str, str]:
    payload = _read_manifest_payload(root)
    if payload.get("schema_version") != OKF_PUBLICATION_SCHEMA_VERSION:
        raise OKFPublicationError("OKF publication manifest uses an unsupported schema version")
    if payload.get("okf_version") != okf_version:
        raise OKFPublicationError("OKF publication manifest targets a different OKF version")
    return _manifest_entries(payload.get("files"))


def _inventory_tree(root: Path) -> _TreeInventory:
    files: dict[str, Path] = {}
    directories: set[str] = set()
    links: set[str] = set()

    def visit(directory: Path, prefix: PurePosixPath) -> None:
        with os.scandir(directory) as entries:
            ordered = sorted(entries, key=lambda entry: entry.name.casefold())
        for entry in ordered:
            relative = (prefix / entry.name).as_posix()
            path = Path(entry.path)
            if entry.is_symlink() or path.is_junction():
                links.add(relative)
                continue
            if entry.is_dir(follow_symlinks=False):
                directories.add(relative)
                visit(path, prefix / entry.name)
                continue
            if entry.is_file(follow_symlinks=False):
                files[relative] = path
                continue
            links.add(relative)

    visit(root, PurePosixPath())
    return _TreeInventory(files=files, directories=frozenset(directories), links=frozenset(links))


def _validate_owned_root(root: Path, *, okf_version: str) -> None:
    if _is_link_like(root) or not root.is_dir():
        raise OKFPublicationError(
            "Existing OKF output is not a manifest-owned directory. "
            "Use --force only to replace the entire dedicated export root."
        )
    expected = _parse_manifest(root, okf_version=okf_version)
    inventory = _inventory_tree(root)
    if inventory.links:
        detail = ", ".join(sorted(inventory.links)[:5])
        raise OKFPublicationError(f"OKF export root contains unmanaged link or special entries: {detail}")

    expected_files = set(expected)
    actual_files = set(inventory.files) - {OKF_PUBLICATION_MANIFEST}
    unmanaged_files = sorted(actual_files - expected_files)
    missing_files = sorted(expected_files - actual_files)
    expected_directories = {
        parent.as_posix()
        for relative_path in expected_files
        for parent in PurePosixPath(relative_path).parents
        if parent.as_posix() != "."
    }
    unmanaged_directories = sorted(set(inventory.directories) - expected_directories)
    if unmanaged_files or unmanaged_directories:
        detail = ", ".join([*unmanaged_files, *unmanaged_directories][:5])
        raise OKFPublicationError(
            "OKF export root contains unmanaged Markdown or other content. "
            "It is a dedicated derived export root: " + detail
        )
    if missing_files:
        raise OKFPublicationError(f"OKF export root is missing generated files: {', '.join(missing_files[:5])}")

    modified = [
        relative_path
        for relative_path, expected_digest in expected.items()
        if _sha256_file(inventory.files[relative_path]) != expected_digest
    ]
    if modified:
        raise OKFPublicationError(
            "OKF export root contains modified generated files. Use --force only to replace the entire root: "
            + ", ".join(modified[:5])
        )


def _remove_tree_no_follow(path: Path) -> None:
    if not _lexists(path):
        return
    if path.is_symlink():
        path.unlink()
        return
    if path.is_junction():
        path.rmdir()
        return
    mode = os.lstat(path).st_mode
    if not stat.S_ISDIR(mode):
        path.unlink()
        return
    with os.scandir(path) as entries:
        children = [Path(entry.path) for entry in entries]
    for child in children:
        _remove_tree_no_follow(child)
    path.rmdir()


def _build_staging_directory(parent: Path, root_name: str, files: Mapping[str, str], manifest_text: str) -> Path:
    staging = Path(tempfile.mkdtemp(prefix=f".{root_name}.staging-", dir=parent))
    try:
        for relative_path, content in sorted(files.items()):
            target = staging.joinpath(*PurePosixPath(relative_path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(target, content)
        atomic_write_text(staging / OKF_PUBLICATION_MANIFEST, manifest_text)
    except Exception:
        _remove_tree_no_follow(staging)
        raise
    return staging


def _restore_prior_root(root: Path, recovery: Path, prior_identity: _PathIdentity) -> None:
    if _path_identity(recovery) != prior_identity:
        raise OKFPublicationError("Prior OKF export identity changed before rollback; automatic cleanup was refused")
    displaced: Path | None = None
    if _lexists(root):
        displaced = root.parent / f".{root.name}.failed-{uuid4().hex}"
        _rename_path(root, displaced)
    try:
        _rename_path(recovery, root)
        if _path_identity(root) != prior_identity:
            raise OKFPublicationError("Prior OKF export identity changed during rollback")
    except Exception:
        if displaced is not None and not _lexists(root) and _lexists(displaced):
            _rename_path(displaced, root)
        raise
    if displaced is not None:
        _remove_tree_no_follow(displaced)


def _identity_payload(identity: _PathIdentity) -> dict[str, int]:
    return {"device": identity.device, "inode": identity.inode, "mode": identity.mode}


def _identity_from_payload(value: Any) -> _PathIdentity:
    if not isinstance(value, dict) or set(value) != {"device", "inode", "mode"}:
        raise OKFPublicationError("OKF recovery journal contains an invalid path identity")
    if any(not isinstance(value[key], int) for key in ("device", "inode", "mode")):
        raise OKFPublicationError("OKF recovery journal contains a non-integer path identity")
    return _PathIdentity(value["device"], value["inode"], value["mode"])


def _write_recovery_record(path: Path, record: _RecoveryRecord) -> None:
    payload = {
        "schema_version": _RECOVERY_SCHEMA_VERSION,
        "target": record.target,
        "prior": _identity_payload(record.prior),
        "staged": _identity_payload(record.staged),
    }
    atomic_write_text(path, json.dumps(payload, sort_keys=True) + "\n", fsync=True, overwrite=False)


def _read_recovery_record(path: Path) -> _RecoveryRecord:
    if _is_link_like(path) or not path.is_file() or path.stat().st_size > _MAX_MANIFEST_BYTES:
        raise OKFPublicationError("OKF recovery journal is not a bounded regular file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OKFPublicationError(f"OKF recovery journal is unreadable: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "target", "prior", "staged"}:
        raise OKFPublicationError("OKF recovery journal has an unsupported structure")
    if payload["schema_version"] != _RECOVERY_SCHEMA_VERSION or not isinstance(payload["target"], str):
        raise OKFPublicationError("OKF recovery journal has an unsupported version or target")
    return _RecoveryRecord(
        target=payload["target"],
        prior=_identity_from_payload(payload["prior"]),
        staged=_identity_from_payload(payload["staged"]),
    )


def _remove_recovery_journal(path: Path) -> None:
    if not _lexists(path):
        return
    if _is_link_like(path) or not path.is_file():
        raise OKFPublicationError("OKF recovery journal changed before cleanup")
    path.unlink()


def _reconcile_recovery(root: Path, recovery: Path, journal: Path) -> None:
    if not _lexists(journal):
        if _lexists(recovery):
            raise OKFPublicationError(
                f"Reserved OKF recovery path already exists without a recovery journal: {recovery}"
            )
        return
    record = _read_recovery_record(journal)
    if os.path.normcase(record.target) != os.path.normcase(str(root)):
        raise OKFPublicationError("OKF recovery journal targets a different export root")

    root_identity = _path_identity(root) if _lexists(root) else None
    recovery_identity = _path_identity(recovery) if _lexists(recovery) else None
    if recovery_identity is not None and recovery_identity != record.prior:
        raise OKFPublicationError("Recoverable OKF root identity no longer matches its journal")
    if recovery_identity is not None and root_identity is None:
        _rename_path(recovery, root)
        if _path_identity(root) != record.prior:
            raise OKFPublicationError("Recoverable OKF root identity changed during restoration")
        _remove_recovery_journal(journal)
        return
    if recovery_identity is not None and root_identity == record.staged:
        _remove_tree_no_follow(recovery)
        _remove_recovery_journal(journal)
        return
    if recovery_identity is None and root_identity in {record.prior, record.staged}:
        _remove_recovery_journal(journal)
        return
    raise OKFPublicationError("OKF recovery state is ambiguous; automatic mutation was refused")


def _install_staging(root: Path, staging: Path, staging_identity: _PathIdentity) -> None:
    _rename_path(staging, root)
    if _path_identity(root) != staging_identity:
        raise OKFPublicationError("Staged OKF export identity changed during publication")


def _rollback_publication(
    root: Path,
    recovery: Path,
    journal: Path,
    prior_identity: _PathIdentity,
) -> None:
    if _lexists(recovery):
        _restore_prior_root(root, recovery, prior_identity)
    elif not _lexists(root) or _path_identity(root) != prior_identity:
        raise OKFPublicationError("Prior OKF export could not be located for rollback")
    _remove_recovery_journal(journal)


def _publish_staging(
    root: Path,
    staging: Path,
    recovery: Path,
    journal: Path,
    *,
    force: bool,
    okf_version: str,
) -> None:
    prior_exists = _lexists(root)
    staging_identity = _path_identity(staging)
    if not prior_exists:
        _install_staging(root, staging, staging_identity)
        return

    prior_identity = _path_identity(root)
    if not force:
        _validate_owned_root(root, okf_version=okf_version)
        if _path_identity(root) != prior_identity:
            raise OKFPublicationError("OKF export root changed while its publication manifest was verified")

    record = _RecoveryRecord(str(root), prior_identity, staging_identity)
    _write_recovery_record(journal, record)
    try:
        _rename_path(root, recovery)
        if _path_identity(recovery) != prior_identity:
            _restore_prior_root(root, recovery, prior_identity)
            raise OKFPublicationError("OKF export root identity changed during publication")
        if not force:
            _validate_owned_root(recovery, okf_version=okf_version)
        _install_staging(root, staging, staging_identity)
    except Exception as exc:
        try:
            _rollback_publication(root, recovery, journal, prior_identity)
        except Exception as restore_exc:
            raise OKFPublicationError(
                f"OKF publication failed and the prior root could not be restored: {restore_exc}"
            ) from exc
        raise

    if _path_identity(recovery) != prior_identity:
        raise OKFPublicationError("Prior OKF export identity changed before cleanup; cleanup was refused")
    _remove_tree_no_follow(recovery)
    _remove_recovery_journal(journal)


def _validate_portable_root_name(name: str) -> None:
    reserved_stem = name.split(".", 1)[0].rstrip(" .").upper()
    invalid_character = any(ord(character) < 32 or character in '<>:"/\\|?*' for character in name)
    if (
        name in {"", ".", ".."}
        or name.rstrip(" .") != name
        or reserved_stem in _WINDOWS_DEVICE_NAMES
        or invalid_character
    ):
        raise OKFPublicationError(f"OKF output uses a non-portable directory name: {name!r}")


def _real_directory(path: Path) -> None:
    if _is_link_like(path):
        raise OKFPublicationError(f"Links are not accepted in the requested OKF output parent: {path}")
    if not stat.S_ISDIR(os.lstat(path).st_mode):
        raise OKFPublicationError(f"OKF output parent component is not a directory: {path}")


def _parent_components(path: Path) -> list[Path]:
    current = Path(path.anchor)
    components = [current]
    for part in path.parts[1:]:
        current = current / part
        components.append(current)
    return components


def _checked_output_parent(requested: Path) -> Path:
    if ".." in requested.parts:
        raise OKFPublicationError("OKF output path cannot contain parent traversal components")
    absolute = requested if requested.is_absolute() else Path.cwd() / requested
    parent = absolute.parent
    identities: list[tuple[Path, _PathIdentity]] = []
    for component in _parent_components(parent):
        if not _lexists(component):
            component.mkdir()
        _real_directory(component)
        identities.append((component, _path_identity(component)))
    resolved = parent.resolve(strict=True)
    if any(_path_identity(component) != identity for component, identity in identities):
        raise OKFPublicationError("OKF output parent changed while its components were verified")
    return resolved


def _secure_coordination_directory() -> Path:
    base = Path(tempfile.gettempdir()).resolve(strict=True)
    directory = base / "deepr-okf-publication-locks"
    directory.mkdir(mode=0o700, exist_ok=True)
    _real_directory(directory)
    if os.name != "nt":
        result = os.lstat(directory)
        getuid = getattr(os, "getuid", None)
        if getuid is not None and result.st_uid != getuid():
            raise OKFPublicationError("OKF coordination directory is not owned by the current user")
        if stat.S_IMODE(result.st_mode) & 0o077:
            directory.chmod(0o700)
    return directory.resolve(strict=True)


def _coordination_paths(root: Path) -> tuple[Path, Path]:
    directory = _secure_coordination_directory()
    key = sha256(os.fsencode(os.path.normcase(str(root)))).hexdigest()
    lock_path = directory / f"{key}.lock"
    journal_path = directory / f"{key}.recovery.json"
    if _lexists(lock_path) and (_is_link_like(lock_path) or not lock_path.is_file()):
        raise OKFPublicationError("OKF coordination lock path is not a regular file")
    return lock_path, journal_path


def publish_okf_directory(
    files: Mapping[str, str],
    output_dir: Path,
    *,
    force: bool,
    okf_version: str,
) -> Path:
    """Publish a complete OKF directory transaction under a sibling lock.

    Existing output must match its exact publication manifest unless ``force``
    is set. Force replaces the complete dedicated export root, not individual
    files. Link entries are renamed with the prior root and removed without
    traversing their targets.
    """
    requested = Path(output_dir)
    _validate_portable_root_name(requested.name)
    _, manifest_text = _manifest_payload(files, okf_version=okf_version)
    parent = _checked_output_parent(requested)
    root = parent / requested.name
    lock_path, journal_path = _coordination_paths(root)
    recovery = parent / f".{root.name}.deepr-okf-recovery"
    staging: Path | None = None
    try:
        with FileLock(str(lock_path), timeout=10, thread_local=False):
            parent_identity = _path_identity(parent)
            _reconcile_recovery(root, recovery, journal_path)
            staging = _build_staging_directory(parent, root.name, files, manifest_text)
            if _path_identity(parent) != parent_identity:
                raise OKFPublicationError("OKF output parent changed while staging the publication")
            _publish_staging(
                root,
                staging,
                recovery,
                journal_path,
                force=force,
                okf_version=okf_version,
            )
            staging = None
    except FileLockTimeout as exc:
        raise OKFPublicationError(f"Timed out waiting for the OKF export lock for {root}") from exc
    finally:
        if staging is not None and _lexists(staging):
            _remove_tree_no_follow(staging)
    return root


__all__ = [
    "OKF_PUBLICATION_MANIFEST",
    "OKF_PUBLICATION_SCHEMA_VERSION",
    "OKFPublicationError",
    "publish_okf_directory",
]
