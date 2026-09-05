"""Root-confined SHA-256 verification for expert-value artifacts.

The review workbook carries operator-attested artifact references and hashes. This
module optionally recomputes those hashes from a caller-selected filesystem
root. It never resolves a URL, contacts a provider, or changes an artifact.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

_CHUNK_SIZE = 1024 * 1024


class ArtifactVerificationError(ValueError):
    """Raised when a declared artifact cannot be verified safely."""


def validate_artifact_reference(value: str, *, field_name: str) -> str:
    """Validate reference form without rewriting significant path characters."""
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > 4000:
        raise ValueError(f"{field_name} must be at most 4000 characters")
    return value


@dataclass(frozen=True)
class ArtifactBinding:
    """One workbook field pair that binds a reference to a digest."""

    field: str
    reference: str
    sha256: str


@dataclass(frozen=True)
class _ResolvedBinding:
    binding: ArtifactBinding
    path: Path
    path_key: str


def iter_expert_value_artifact_bindings(review: Any) -> Iterator[ArtifactBinding]:
    """Yield every artifact reference and digest declared by a review."""
    for index, world in enumerate(review.source_worlds):
        yield ArtifactBinding(
            f"source_worlds[{index}].manifest",
            world.manifest_ref,
            world.manifest_sha256,
        )
    for index, arm in enumerate(review.arm_configurations):
        yield ArtifactBinding(
            f"arm_configurations[{index}].run_policy",
            arm.run_policy_ref,
            arm.run_policy_sha256,
        )
    for index, trial in enumerate(review.trials):
        yield ArtifactBinding(
            f"trials[{index}].run_artifact",
            trial.run_artifact_ref,
            trial.run_artifact_sha256,
        )
        yield ArtifactBinding(
            f"trials[{index}].answer_artifact",
            trial.answer_artifact_ref,
            trial.answer_artifact_sha256,
        )
    yield ArtifactBinding(
        "protocol_attestation.review_assignment",
        review.protocol_attestation.review_assignment_ref,
        review.protocol_attestation.review_assignment_sha256,
    )
    for index, case in enumerate(review.cases):
        outcome = case.observed_outcome
        if outcome is not None:
            yield ArtifactBinding(
                f"cases[{index}].observed_outcome.outcome_record",
                outcome.outcome_record_ref,
                outcome.outcome_record_sha256,
            )


def operator_attested_artifact_verification(review: Any) -> dict[str, Any]:
    """Describe workbook attestation without claiming independent file reads."""
    bindings = list(iter_expert_value_artifact_bindings(review))
    return {
        "mode": "operator_attested",
        "digest_algorithm": "sha256",
        "reference_count": len(bindings),
        "declared_unique_reference_count": len({binding.reference for binding in bindings}),
        "verified_reference_count": 0,
        "verified_file_count": 0,
        "protocol_attested": bool(review.protocol_attestation.artifact_hashes_verified),
        "independently_verified": False,
        "all_matched": None,
        "root_confined": None,
        "network_access": False,
    }


def _validate_root(artifact_root: Path) -> Path:
    try:
        root = artifact_root.resolve(strict=True)
    except OSError as exc:
        raise ArtifactVerificationError("artifact root is unavailable") from exc
    if not root.is_dir():
        raise ArtifactVerificationError("artifact root must be a directory")
    return root


def _reference_path(reference: str, *, field: str) -> Path:
    if "\x00" in reference or "#" in reference or "?" in reference or ":" in reference:
        raise ArtifactVerificationError(f"{field} must be a plain relative file reference")
    windows = PureWindowsPath(reference)
    posix = PurePosixPath(reference)
    if windows.is_absolute() or windows.drive or posix.is_absolute():
        raise ArtifactVerificationError(f"{field} must be a relative file reference")
    if ".." in windows.parts or ".." in posix.parts:
        raise ArtifactVerificationError(f"{field} must not contain parent traversal")
    if "://" in reference:
        raise ArtifactVerificationError(f"{field} must not be a URI")
    return Path(reference)


def _resolve_binding(binding: ArtifactBinding, root: Path) -> _ResolvedBinding:
    relative = _reference_path(binding.reference, field=binding.field)
    try:
        path = (root / relative).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ArtifactVerificationError(f"{binding.field} does not resolve to an available file") from exc
    if not path.is_relative_to(root):
        raise ArtifactVerificationError(f"{binding.field} escapes the artifact root")
    if not path.is_file():
        raise ArtifactVerificationError(f"{binding.field} must resolve to a regular file")
    return _ResolvedBinding(binding=binding, path=path, path_key=os.path.normcase(str(path)))


def _file_identity(path: Path) -> tuple[int, int, int, int]:
    return _stat_identity(path.stat())


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _regular_reference_path(reference: str, root: Path, field: str) -> Path:
    validate_artifact_reference(reference, field_name=field)
    if any(part in {"", ".", ".."} for part in reference.split("/")):
        raise ArtifactVerificationError(f"{field} must use a canonical relative file reference")
    relative = _reference_path(reference, field=field)
    if "\\" in reference:
        raise ArtifactVerificationError(f"{field} must use portable forward-slash separators")
    current = root
    for part in relative.parts:
        current = current / part
        info = current.lstat()
        reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if stat.S_ISLNK(info.st_mode) or reparse:
            raise ArtifactVerificationError(f"{field} must not traverse links or junctions")
    if not stat.S_ISREG(current.lstat().st_mode):
        raise ArtifactVerificationError(f"{field} must be a regular file")
    return current


def read_bounded_artifact(
    reference: str, artifact_root: Path, *, max_bytes: int, field_name: str = "artifact"
) -> bytes:
    """Read one bounded regular file without accepting links or changing state.

    This stricter preparation reader does not change legacy workbook reference
    compatibility. Identity checks detect ordinary concurrent changes; this is
    not a process sandbox against a hostile writer controlling the filesystem.
    """
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    root = _validate_root(artifact_root)
    try:
        path = _regular_reference_path(reference, root, field_name)
        before = path.lstat()
        if before.st_size > max_bytes:
            raise ArtifactVerificationError(f"{field_name} exceeds its byte ceiling")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as artifact:
            opened = os.fstat(artifact.fileno())
            if not stat.S_ISREG(opened.st_mode) or _stat_identity(before) != _stat_identity(opened):
                raise ArtifactVerificationError(f"{field_name} changed before reading")
            payload = artifact.read(max_bytes + 1)
            after = os.fstat(artifact.fileno())
        final_path = _regular_reference_path(reference, root, field_name)
        if _stat_identity(before) != _stat_identity(after) or _stat_identity(before) != _file_identity(final_path):
            raise ArtifactVerificationError(f"{field_name} changed during reading")
    except OSError as exc:
        raise ArtifactVerificationError(f"{field_name} could not be read as a bounded regular file") from exc
    if len(payload) > max_bytes:
        raise ArtifactVerificationError(f"{field_name} exceeds its byte ceiling")
    return payload


def _sha256_file(resolved: _ResolvedBinding, root: Path) -> str:
    try:
        before = _file_identity(resolved.path)
    except OSError as exc:
        raise ArtifactVerificationError(f"{resolved.binding.field} could not be read") from exc
    digest = hashlib.sha256()
    try:
        with resolved.path.open("rb") as artifact:
            for chunk in iter(lambda: artifact.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ArtifactVerificationError(f"{resolved.binding.field} could not be read") from exc
    try:
        after = _file_identity(resolved.path)
        final_path = resolved.path.resolve(strict=True)
    except OSError as exc:
        raise ArtifactVerificationError(f"{resolved.binding.field} changed during verification") from exc
    if before != after or final_path != resolved.path or not final_path.is_relative_to(root):
        raise ArtifactVerificationError(f"{resolved.binding.field} changed during verification")
    return digest.hexdigest()


def verify_expert_value_artifacts(review: Any, artifact_root: Path) -> dict[str, Any]:
    """Recompute all workbook digests beneath one caller-selected root.

    Repeated bindings to the same resolved file are read once. Conflicting
    expected hashes, missing files, path escapes, and digest mismatches fail the
    complete verification before a report can be written.
    """
    root = _validate_root(artifact_root)
    bindings = list(iter_expert_value_artifact_bindings(review))
    resolved = [_resolve_binding(binding, root) for binding in bindings]
    expected_by_path: dict[str, str] = {}
    representative_by_path: dict[str, _ResolvedBinding] = {}
    for item in resolved:
        expected = expected_by_path.setdefault(item.path_key, item.binding.sha256)
        if not hmac.compare_digest(expected, item.binding.sha256):
            raise ArtifactVerificationError("one artifact file has conflicting declared SHA-256 digests")
        representative_by_path.setdefault(item.path_key, item)

    for item in representative_by_path.values():
        actual = _sha256_file(item, root)
        if not hmac.compare_digest(actual, item.binding.sha256):
            raise ArtifactVerificationError(f"{item.binding.field} SHA-256 digest does not match")

    return {
        "mode": "local_filesystem_sha256",
        "digest_algorithm": "sha256",
        "reference_count": len(bindings),
        "declared_unique_reference_count": len({binding.reference for binding in bindings}),
        "verified_reference_count": len(bindings),
        "verified_file_count": len(representative_by_path),
        "protocol_attested": bool(review.protocol_attestation.artifact_hashes_verified),
        "independently_verified": True,
        "all_matched": True,
        "root_confined": True,
        "network_access": False,
    }


__all__ = [
    "ArtifactBinding",
    "ArtifactVerificationError",
    "iter_expert_value_artifact_bindings",
    "operator_attested_artifact_verification",
    "read_bounded_artifact",
    "verify_expert_value_artifacts",
]
