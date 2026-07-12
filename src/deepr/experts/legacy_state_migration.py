"""Targeted repair for state written below a legacy display-name directory.

Older expert components sometimes used the display name as a directory segment
while the profile and beliefs lived in the canonical slug directory. This
module plans and applies a migration for one exact expert identity and a closed
set of known runtime artifacts. Unknown content and other experts are never
included.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from deepr.experts.paths import canonical_expert_dir
from deepr.utils.security import SecurityError, validate_path

_KNOWN_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("logs", "thoughts_*.jsonl"),
    ("memory", "episodic.json"),
    ("memory", "profiles.json"),
    ("memory", "meta_knowledge.json"),
    ("graph", "concepts.json"),
    ("graph", "edges.json"),
    ("cache", "subgraph_cache.json"),
    ("feedback", "feedback.json"),
    ("dspy", "optimized_prompts.json"),
    ("dspy", "optimization_history.json"),
    ("knowledge", "entries.json"),
    ("knowledge", "archive.json"),
)
_KNOWN_DIRS = tuple(dict.fromkeys(relative_dir for relative_dir, _ in _KNOWN_ARTIFACTS))


class LegacyStateMigrationError(RuntimeError):
    """Raised when a targeted legacy-state migration cannot proceed safely."""


@dataclass(frozen=True)
class ArtifactConflict:
    """One known artifact that cannot be moved without operator review."""

    source: Path
    destination: Path
    reason: str


@dataclass(frozen=True)
class LegacyStateMigrationPlan:
    """Read-only plan for one expert's known legacy state."""

    expert_name: str
    legacy_expert_dir: Path
    canonical_expert_dir: Path
    moves: tuple[tuple[Path, Path], ...]
    duplicates: tuple[tuple[Path, Path], ...]
    conflicts: tuple[ArtifactConflict, ...]
    prunable_dirs: tuple[Path, ...]

    @property
    def artifact_count(self) -> int:
        """Return the number of known source artifacts covered by this plan."""
        return len(self.moves) + len(self.duplicates) + len(self.conflicts)


@dataclass(frozen=True)
class LegacyStateMigrationResult:
    """Applied result for one expert's known legacy state."""

    expert_name: str
    moved: tuple[Path, ...]
    deduplicated: tuple[Path, ...]
    pruned_dirs: tuple[Path, ...]
    canonical_expert_dir: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _same_contents(left: Path, right: Path) -> bool:
    try:
        return left.stat().st_size == right.stat().st_size and _sha256(left) == _sha256(right)
    except OSError:
        return False


def _resolve_expert_dirs(expert_name: str, root: Path) -> tuple[Path, Path]:
    if not expert_name or Path(expert_name).is_absolute() or len(Path(expert_name).parts) != 1:
        raise LegacyStateMigrationError("Expert name must be one non-empty path segment.")

    try:
        resolved_root = root.resolve()
        legacy_expert = validate_path(expert_name, base_dir=resolved_root, must_exist=False, allow_create=True)
        canonical_expert = canonical_expert_dir(expert_name, resolved_root)
    except (OSError, SecurityError, ValueError) as exc:
        raise LegacyStateMigrationError(f"Expert path is unsafe or unavailable for {expert_name!r}.") from exc
    if legacy_expert.parent != resolved_root:
        raise LegacyStateMigrationError("Legacy expert directory must be a direct child of the experts root.")

    profile_path = canonical_expert / "profile.json"
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LegacyStateMigrationError(f"Canonical expert profile not found for {expert_name!r}.") from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise LegacyStateMigrationError(f"Canonical expert profile is unreadable for {expert_name!r}.") from exc
    if not isinstance(profile, dict) or profile.get("name") != expert_name:
        raise LegacyStateMigrationError("Expert name must exactly match the canonical profile identity.")
    return legacy_expert, canonical_expert


def _artifact_dirs(legacy_expert: Path, canonical_expert: Path, relative_dir: str) -> tuple[Path, Path]:
    raw_source_dir = legacy_expert / relative_dir
    raw_destination_dir = canonical_expert / relative_dir
    if raw_source_dir.is_symlink() or raw_destination_dir.is_symlink():
        raise LegacyStateMigrationError(f"Known artifact directory {relative_dir!r} must not be a symlink.")
    try:
        source_dir = validate_path(
            raw_source_dir,
            base_dir=legacy_expert.parent,
            must_exist=False,
            allow_create=True,
        )
        destination_dir = validate_path(
            raw_destination_dir,
            base_dir=canonical_expert,
            must_exist=False,
            allow_create=True,
        )
    except (OSError, SecurityError, ValueError) as exc:
        raise LegacyStateMigrationError(f"Known artifact directory {relative_dir!r} is unsafe or unavailable.") from exc
    return source_dir, destination_dir


def _projected_prunable_dirs(legacy_expert: Path, covered_sources: set[Path]) -> tuple[Path, ...]:
    prunable: list[Path] = []
    for relative_dir in _KNOWN_DIRS:
        source_dir = legacy_expert / relative_dir
        if source_dir.is_symlink() or not source_dir.is_dir():
            continue
        try:
            entries = tuple(source_dir.iterdir())
        except OSError:
            continue
        if all(entry in covered_sources for entry in entries):
            prunable.append(source_dir)

    if legacy_expert.is_dir() and not legacy_expert.is_symlink():
        try:
            root_entries = tuple(legacy_expert.iterdir())
        except OSError:
            root_entries = None
        if root_entries is not None and all(entry in prunable for entry in root_entries):
            prunable.append(legacy_expert)
    return tuple(sorted(prunable, key=lambda path: len(path.parts), reverse=True))


def plan_legacy_state_migration(expert_name: str, *, experts_root: Path | None = None) -> LegacyStateMigrationPlan:
    """Build a no-write migration plan for one exact expert identity."""
    if experts_root is None:
        from deepr.config import experts_root as configured_experts_root

        experts_root = configured_experts_root()

    legacy_expert, canonical_expert = _resolve_expert_dirs(expert_name, experts_root)
    moves: list[tuple[Path, Path]] = []
    duplicates: list[tuple[Path, Path]] = []
    conflicts: list[ArtifactConflict] = []

    if legacy_expert == canonical_expert or not legacy_expert.is_dir():
        return LegacyStateMigrationPlan(expert_name, legacy_expert, canonical_expert, (), (), (), ())

    for relative_dir, pattern in _KNOWN_ARTIFACTS:
        source_dir, destination_dir = _artifact_dirs(legacy_expert, canonical_expert, relative_dir)
        if not source_dir.is_dir():
            continue
        for source in sorted(source_dir.glob(pattern)):
            destination = destination_dir / source.name
            if source.is_symlink() or not source.is_file():
                conflicts.append(ArtifactConflict(source, destination, "source is not a regular file"))
                continue
            if destination.exists():
                if destination.is_file() and not destination.is_symlink() and _same_contents(source, destination):
                    duplicates.append((source, destination))
                else:
                    conflicts.append(ArtifactConflict(source, destination, "destination has other data"))
                continue
            moves.append((source, destination))

    covered_sources = {source for source, _ in moves + duplicates}
    prunable_dirs = _projected_prunable_dirs(legacy_expert, covered_sources)
    return LegacyStateMigrationPlan(
        expert_name,
        legacy_expert,
        canonical_expert,
        tuple(moves),
        tuple(duplicates),
        tuple(conflicts),
        prunable_dirs,
    )


def _copy_verified_then_remove(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with source.open("rb") as source_handle, destination.open("xb") as destination_handle:
            created = True
            for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                destination_handle.write(chunk)
            destination_handle.flush()
            os.fsync(destination_handle.fileno())
        if not _same_contents(source, destination):
            raise LegacyStateMigrationError(f"Copied artifact failed verification: {source.name}")
    except (OSError, LegacyStateMigrationError):
        if created:
            destination.unlink(missing_ok=True)
        raise
    source.unlink()


def migrate_legacy_state(expert_name: str, *, experts_root: Path | None = None) -> LegacyStateMigrationResult:
    """Move known legacy state after a fresh, fail-closed plan.

    A destination is created and fsynced before its source is removed. An
    interrupted run is safe to retry because completed copies are recognized as
    identical duplicates. Different destination content blocks all planned
    work. Unknown files and directories remain in place.
    """
    plan = plan_legacy_state_migration(expert_name, experts_root=experts_root)
    if plan.conflicts:
        raise LegacyStateMigrationError("Migration has artifact conflicts; no state was moved.")

    moved: list[Path] = []
    deduplicated: list[Path] = []
    for source, destination in plan.moves:
        try:
            _copy_verified_then_remove(source, destination)
        except OSError as exc:
            raise LegacyStateMigrationError(f"Could not migrate known artifact {source.name!r}.") from exc
        moved.append(destination)
    for source, destination in plan.duplicates:
        if not _same_contents(source, destination):
            raise LegacyStateMigrationError(f"Duplicate changed during migration: {source.name}")
        try:
            source.unlink()
        except OSError as exc:
            raise LegacyStateMigrationError(f"Could not remove duplicate artifact {source.name!r}.") from exc
        deduplicated.append(destination)

    pruned_dirs: list[Path] = []
    for directory in plan.prunable_dirs:
        try:
            directory.rmdir()
        except OSError:
            continue
        pruned_dirs.append(directory)

    return LegacyStateMigrationResult(
        expert_name,
        tuple(moved),
        tuple(deduplicated),
        tuple(pruned_dirs),
        plan.canonical_expert_dir,
    )


__all__ = [
    "ArtifactConflict",
    "LegacyStateMigrationError",
    "LegacyStateMigrationPlan",
    "LegacyStateMigrationResult",
    "migrate_legacy_state",
    "plan_legacy_state_migration",
]
