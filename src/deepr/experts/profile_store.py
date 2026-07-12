"""Expert profile storage and CRUD operations.

This module provides the ExpertStore class for persisting and managing
expert profiles. Separated from profile.py to follow Single Responsibility
Principle - profile.py contains data classes, this module contains storage
operations.

Features:
- CRUD operations for ExpertProfile
- Schema versioning with migration support
- Directory structure management
- Legacy hosted vector-store integration, execution-gated in v2.36

Requirements: 1.2 - ExpertProfile Refactoring
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from filelock import FileLock

from deepr.experts.metered_mutation_gate import require_metered_expert_mutation

if TYPE_CHECKING:
    from deepr.experts.profile import ExpertProfile

logger = logging.getLogger(__name__)

# Current schema version - increment when profile structure changes
PROFILE_SCHEMA_VERSION = 4

# Migration registry: maps (from_version, to_version) -> migration function
_MIGRATIONS: dict[tuple, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def migration(from_version: int, to_version: int):
    """Decorator to register a schema migration function.

    Usage:
        @migration(1, 2)
        def migrate_v1_to_v2(data: dict) -> dict:
            # Transform data from v1 to v2 schema
            return data
    """

    def decorator(func: Callable[[dict[str, Any]], dict[str, Any]]):
        _MIGRATIONS[(from_version, to_version)] = func
        return func

    return decorator


# =============================================================================
# Schema migrations
# =============================================================================


@migration(1, 2)
def migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate from schema v1 to v2.

    Changes in v2:
    - Added schema_version field
    - Added provider and model fields with defaults
    - Added refresh_history field
    - Renamed learning_budget to monthly_learning_budget
    """
    # Add schema version
    data["schema_version"] = 2

    # Add provider/model if missing
    if "provider" not in data:
        data["provider"] = "openai"
    if "model" not in data:
        data["model"] = "gpt-5.2"

    # Add refresh_history if missing
    if "refresh_history" not in data:
        data["refresh_history"] = []

    # Handle renamed field
    if "learning_budget" in data and "monthly_learning_budget" not in data:
        data["monthly_learning_budget"] = data.pop("learning_budget")

    return data


@migration(2, 3)
def migrate_v2_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate from schema v2 to v3.

    Changes in v3:
    - Added installed_skills field for expert skills system
    """
    data["schema_version"] = 3
    data.setdefault("installed_skills", [])
    return data


@migration(3, 4)
def migrate_v3_to_v4(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate from schema v3 to v4.

    Changes in v4:
    - Added portrait_url field for AI-generated expert portraits
    """
    data["schema_version"] = 4
    data.setdefault("portrait_url", None)
    return data


def migrate_profile_data(data: dict[str, Any]) -> dict[str, Any]:
    """Apply all necessary migrations to bring profile data to current schema.

    Args:
        data: Profile data dictionary (may be from any schema version)

    Returns:
        Migrated profile data at current schema version
    """
    # Determine current version (default to 1 if not present)
    current_version = int(float(data.get("schema_version") or 1))

    if current_version >= PROFILE_SCHEMA_VERSION:
        return data

    # Apply migrations sequentially
    while current_version < PROFILE_SCHEMA_VERSION:
        next_version = current_version + 1
        migration_key = (current_version, next_version)

        if migration_key not in _MIGRATIONS:
            logger.warning("No migration found for %d -> %d, skipping", current_version, next_version)
            current_version = next_version
            continue

        migration_func = _MIGRATIONS[migration_key]
        logger.info("Migrating profile from v%d to v%d", current_version, next_version)
        data = migration_func(data)
        current_version = next_version

    return data


# =============================================================================
# ExpertStore class
# =============================================================================


class ExpertStore:
    """Storage layer for expert profiles.

    Handles persistence, directory management, and schema migrations.
    Separated from ExpertProfile for clean separation of concerns.

    Usage:
        store = ExpertStore()
        profile = store.load("my-expert")
        store.save(profile)
        all_experts = store.list_all()
    """

    def __init__(self, base_path: str | None = None, *, create: bool = True):
        """Initialize the expert store.

        Args:
            base_path: Base directory for storing expert data (default: the
                configured experts root, deepr.config.experts_root).
            create: Create the experts root when it does not exist. Read-only
                callers set this to false to avoid hidden filesystem writes.
        """
        from deepr.config import experts_root

        self.base_path = Path(base_path) if base_path else experts_root()
        if create:
            self.base_path.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # Path helpers
    # =========================================================================

    def _get_expert_dir(self, name: str) -> Path:
        """Get directory path for expert with security validation.

        Args:
            name: Expert name (will be sanitized)

        Returns:
            Validated path to expert directory
        """
        from deepr.experts.paths import canonical_expert_dir

        return canonical_expert_dir(name, self.base_path)

    def _get_profile_path(self, name: str) -> Path:
        """Get file path for expert profile.

        Args:
            name: Expert name

        Returns:
            Path to profile.json file
        """
        return self._get_expert_dir(name) / "profile.json"

    def find_existing_dir(self, name: str) -> Path | None:
        """Resolve an existing expert directory without constructing a path from input."""
        from deepr.experts.paths import expert_slug
        from deepr.utils.security import validate_path

        if not self.base_path.is_dir():
            return None
        expected = expert_slug(name)
        for candidate in self.base_path.iterdir():
            if candidate.name == expected and candidate.is_dir():
                return validate_path(
                    candidate,
                    base_dir=self.base_path,
                    must_exist=True,
                    allow_create=False,
                )
        return None

    def get_documents_dir(self, name: str) -> Path:
        """Get documents directory for expert.

        Args:
            name: Expert name

        Returns:
            Path to documents directory
        """
        return self._get_expert_dir(name) / "documents"

    def get_knowledge_dir(self, name: str) -> Path:
        """Get knowledge directory for expert.

        Args:
            name: Expert name

        Returns:
            Path to knowledge directory
        """
        return self._get_expert_dir(name) / "knowledge"

    def get_conversations_dir(self, name: str) -> Path:
        """Get conversations directory for expert.

        Args:
            name: Expert name

        Returns:
            Path to conversations directory
        """
        return self._get_expert_dir(name) / "conversations"

    def get_beliefs_dir(self, name: str) -> Path:
        """Get beliefs directory for expert.

        Args:
            name: Expert name

        Returns:
            Path to beliefs directory
        """
        return self._get_expert_dir(name) / "beliefs"

    # =========================================================================
    # CRUD operations
    # =========================================================================

    def save(self, profile: ExpertProfile) -> None:
        """Save expert profile to disk.

        Creates directory structure if it doesn't exist.
        Updates the updated_at timestamp.

        Args:
            profile: ExpertProfile instance to save
        """
        # Import here to avoid circular import

        profile.updated_at = datetime.now(UTC)

        expert_dir = self._get_expert_dir(profile.name)
        expert_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (expert_dir / "documents").mkdir(exist_ok=True)
        (expert_dir / "knowledge").mkdir(exist_ok=True)
        (expert_dir / "conversations").mkdir(exist_ok=True)
        (expert_dir / "beliefs").mkdir(exist_ok=True)

        # Serialize with schema version
        profile.schema_version = PROFILE_SCHEMA_VERSION
        data = profile.to_dict()
        data["schema_version"] = PROFILE_SCHEMA_VERSION

        path = self._get_profile_path(profile.name)
        # Crash-safe write: tempfile + rename so a crash mid-write can't
        # leave a half-written profile.json. Expert profiles are
        # load-bearing identity data; corruption silently hides experts
        # from list_all().
        # Serialize profile writes across processes. A timeout fails closed so
        # competing CLI/MCP/web writes do not silently clobber profile.json.
        lock_path = path.with_suffix(path.suffix + ".lock")
        from deepr.utils.atomic_io import atomic_write_json

        with FileLock(str(lock_path), timeout=10):
            atomic_write_json(path, data)

    def load(
        self,
        name: str,
        migrate: bool = True,
        *,
        persist_migration: bool = True,
    ) -> ExpertProfile | None:
        """Load expert profile from disk.

        Automatically migrates old schema versions if migrate=True.

        Args:
            name: Expert name
            migrate: Apply schema migrations to the in-memory profile.
            persist_migration: Write a migrated profile back to disk. Read-only
                callers disable persistence while retaining compatibility with
                legacy schemas.

        Returns:
            ExpertProfile instance or None if not found
        """
        from deepr.experts.profile import ExpertProfile

        path = self._get_profile_path(name)
        if not path.exists():
            return None

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # Apply migrations if needed
        if migrate:
            original_version = data.get("schema_version", 1)
            data = migrate_profile_data(data)

            # Save migrated data if version changed
            if persist_migration and data.get("schema_version", 1) > original_version:
                from deepr.utils.atomic_io import atomic_write_json

                atomic_write_json(path, data)
                logger.info(
                    "Migrated profile '%s' from v%d to v%d",
                    name,
                    original_version,
                    data["schema_version"],
                )

        return ExpertProfile.from_dict(data)

    def list_all(self, include_errors: bool = False) -> list[ExpertProfile]:
        """List all expert profiles.

        Args:
            include_errors: If True, log but don't skip profiles with load errors

        Returns:
            List of ExpertProfile instances, sorted by updated_at (newest first)
        """
        from deepr.experts.profile import ExpertProfile

        # Use a list subclass so we can attach the ``.errors`` attribute
        # without changing the public return type (plain ``list`` rejects
        # attribute assignment in CPython).
        class _ProfileList(list):
            errors: list[tuple[Path, str]] = []

        profiles = _ProfileList()
        profiles.errors = []
        for expert_dir in self.base_path.iterdir():
            if expert_dir.is_dir():
                profile_path = expert_dir / "profile.json"
                if profile_path.exists():
                    try:
                        with open(profile_path, encoding="utf-8") as f:
                            data = json.load(f)
                            data = migrate_profile_data(data)
                            profiles.append(ExpertProfile.from_dict(data))
                    except Exception as e:
                        # Log at ERROR - the previous WARNING was easy to
                        # miss, so corrupted profiles silently disappeared
                        # from the UI's expert list. Operators saw their
                        # expert "deleted" with no indication of why.
                        logger.error(
                            "Failed to load expert profile %s: %s. This expert will be hidden until the file is repaired.",
                            profile_path,
                            e,
                        )
                        profiles.errors.append((profile_path, str(e)))

        sorted_profiles = _ProfileList(sorted(profiles, key=lambda p: p.updated_at, reverse=True))
        sorted_profiles.errors = profiles.errors
        return sorted_profiles

    def delete(self, name: str, remove_directory: bool = False) -> bool:
        """Delete expert profile.

        Args:
            name: Expert name
            remove_directory: If True, remove entire expert directory (including documents)

        Returns:
            True if profile was deleted, False if not found
        """
        profile_path = self._get_profile_path(name)

        if not profile_path.exists():
            return False

        if remove_directory:
            expert_dir = self._get_expert_dir(name)
            shutil.rmtree(expert_dir)
        else:
            profile_path.unlink()

        return True

    def exists(self, name: str) -> bool:
        """Check if expert exists.

        Args:
            name: Expert name

        Returns:
            True if expert profile exists
        """
        return self._get_profile_path(name).exists()

    def rename(self, old_name: str, new_name: str) -> bool:
        """Rename an expert.

        Args:
            old_name: Current expert name
            new_name: New expert name

        Returns:
            True if renamed successfully

        Raises:
            ValueError: If old expert doesn't exist or new name already exists
        """
        if not self.exists(old_name):
            raise ValueError(f"Expert '{old_name}' not found")

        if self.exists(new_name):
            raise ValueError(f"Expert '{new_name}' already exists")

        old_dir = self._get_expert_dir(old_name)
        new_dir = self._get_expert_dir(new_name)

        # Move directory
        shutil.move(str(old_dir), str(new_dir))

        # Update profile name
        profile = self.load(new_name)
        if profile:
            profile.name = new_name
            self.save(profile)

        return True

    def backup(self, name: str, backup_suffix: str = ".backup") -> Path | None:
        """Create a backup of an expert profile.

        Args:
            name: Expert name
            backup_suffix: Suffix to add to backup directory

        Returns:
            Path to backup directory or None if expert doesn't exist
        """
        if not self.exists(name):
            return None

        expert_dir = self._get_expert_dir(name)
        backup_dir = Path(str(expert_dir) + backup_suffix)

        # Remove existing backup if present
        if backup_dir.exists():
            shutil.rmtree(backup_dir)

        shutil.copytree(expert_dir, backup_dir)
        return backup_dir

    # =========================================================================
    # Vector store operations
    # =========================================================================

    async def add_documents_to_vector_store(
        self, profile: ExpertProfile, file_paths: list[str], provider_client=None
    ) -> dict[str, Any]:
        """Add documents to expert's vector store.

        Args:
            profile: ExpertProfile instance
            file_paths: List of file paths to upload
            provider_client: Optional provider client (created if not provided)

        Returns:
            Dictionary with uploaded, failed, and skipped lists
        """
        require_metered_expert_mutation(
            "hosted_expert_vector_upload",
            safe_alternative="use local source packs and expert absorb --local",
        )
        if not provider_client:
            from deepr.core.settings import get_settings
            from deepr.providers import create_provider

            settings = get_settings()
            provider = create_provider("openai", api_key=settings.get_api_key("openai"))
            provider_client = provider.client

        results: dict[str, list[Any]] = {"uploaded": [], "failed": [], "skipped": []}

        for file_path in file_paths:
            path = Path(file_path)
            if str(file_path) in profile.source_files:
                results["skipped"].append(str(file_path))
                continue

            try:
                with open(path, "rb") as f:
                    file_obj = await provider_client.files.create(file=f, purpose="assistants")
                await provider_client.vector_stores.files.create(
                    vector_store_id=profile.vector_store_id, file_id=file_obj.id
                )
                profile.source_files.append(str(file_path))
                profile.total_documents += 1
                results["uploaded"].append({"path": str(file_path), "file_id": file_obj.id})
            except Exception as e:
                results["failed"].append({"path": str(file_path), "error": str(e)})

        if results["uploaded"]:
            from deepr.experts.knowledge_freshness import advance_knowledge_freshness

            advance_knowledge_freshness(profile, datetime.now(UTC))
            self.save(profile)
        return results

    async def refresh_expert_knowledge(self, name: str, provider_client=None) -> dict[str, Any]:
        """Scan documents folder and add any missing files to vector store.

        Args:
            name: Expert name
            provider_client: Optional provider client

        Returns:
            Dictionary with upload results and message

        Raises:
            ValueError: If expert doesn't exist
        """
        profile = self.load(name)
        if not profile:
            raise ValueError(f"Expert '{name}' not found")

        docs_dir = self.get_documents_dir(name)
        if not docs_dir.exists():
            return {
                "uploaded": [],
                "failed": [],
                "skipped": [],
                "message": "No documents directory found",
            }

        all_files = list(docs_dir.glob("*.md"))
        new_files = [str(f) for f in all_files if str(f) not in profile.source_files]

        if not new_files:
            return {
                "uploaded": [],
                "failed": [],
                "skipped": [],
                "message": f"All {len(all_files)} documents already in vector store",
            }

        results = await self.add_documents_to_vector_store(profile, new_files, provider_client)
        results["message"] = f"Found {len(new_files)} new documents out of {len(all_files)} total"
        return results

    # =========================================================================
    # Bulk operations
    # =========================================================================

    def get_stale_experts(self) -> list[ExpertProfile]:
        """Get all experts with stale knowledge.

        Returns:
            List of experts that need knowledge refresh
        """
        stale = []
        for profile in self.list_all():
            if profile.is_knowledge_stale():
                stale.append(profile)
        return stale

    def get_experts_by_domain(self, domain: str) -> list[ExpertProfile]:
        """Get all experts in a specific domain.

        Args:
            domain: Domain to filter by

        Returns:
            List of experts in the specified domain
        """
        return [p for p in self.list_all() if p.domain == domain]

    def get_total_research_cost(self) -> float:
        """Get total research cost across all experts.

        Returns:
            Sum of all expert research costs
        """
        return sum(p.total_research_cost for p in self.list_all())

    def export_all(self, output_dir: Path) -> int:
        """Export all expert profiles to a directory.

        Args:
            output_dir: Directory to export profiles to

        Returns:
            Number of profiles exported
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        count = 0

        for profile in self.list_all():
            output_path = output_dir / f"{profile.name}.json"
            with open(output_path, "w", encoding="utf-8") as f:
                data = profile.to_dict()
                data["schema_version"] = PROFILE_SCHEMA_VERSION
                json.dump(data, f, indent=2)
            count += 1

        return count
