"""Root-confined SHA-256 verification for expert-value artifacts.

The review workbook carries operator-attested artifact references and hashes. This
module optionally recomputes those hashes from a caller-selected filesystem
root. It never resolves a URL, contacts a provider, or changes an artifact.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

_CHUNK_SIZE = 1024 * 1024


class ArtifactVerificationError(ValueError):
    """Raised when a declared artifact cannot be verified safely."""


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
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


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
    "verify_expert_value_artifacts",
]
