"""Schema versioning infrastructure for Deepr.

Provides versioning for all persisted JSON data (memory, graph, traces)
with migration support for schema upgrades.

Usage:
    # Add version to data before saving
    data = {"beliefs": [...], "gaps": [...]}
    versioned = add_schema_version(data, "worldview", "1.0.0")
    
    # Check version when loading
    version = get_schema_version(loaded_data)
    if needs_migration(loaded_data, "worldview", "2.0.0"):
        loaded_data = migrate(loaded_data, "worldview", "2.0.0")
    
    # Register custom migrations
    @register_migration("worldview", "1.0.0", "2.0.0")
    def migrate_worldview_v1_to_v2(data):
        # Transform data from v1 to v2 format
        return transformed_data
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Callable, Optional, List, Tuple
from functools import wraps


# Current schema versions for each data type
CURRENT_VERSIONS = {
    "worldview": "1.0.0",
    "expert_profile": "1.0.0",
    "conversation": "1.0.0",
    "trace": "1.0.0",
    "memory": "1.0.0",
    "graph": "1.0.0",
    "belief": "1.0.0",
    "cost_record": "1.0.0",
}

# Migration registry: (schema_type, from_version, to_version) -> migration_function
_migrations: Dict[Tuple[str, str, str], Callable[[Dict], Dict]] = {}


@dataclass
class SchemaVersion:
    """Schema version information embedded in data."""
    schema_type: str
    version: str
    created_at: str
    migrated_from: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_type": self.schema_type,
            "version": self.version,
            "created_at": self.created_at,
            "migrated_from": self.migrated_from
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SchemaVersion":
        return cls(
            schema_type=data.get("schema_type", "unknown"),
            version=data.get("version", "0.0.0"),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            migrated_from=data.get("migrated_from")
        )


def add_schema_version(
    data: Dict[str, Any],
    schema_type: str,
    version: Optional[str] = None
) -> Dict[str, Any]:
    """Add schema version metadata to data.
    
    Args:
        data: The data dictionary to version
        schema_type: Type of schema (worldview, expert_profile, etc.)
        version: Version string (defaults to current version for type)
        
    Returns:
        Data with schema_version field added
    """
    if version is None:
        version = CURRENT_VERSIONS.get(schema_type, "1.0.0")
    
    schema_info = SchemaVersion(
        schema_type=schema_type,
        version=version,
        created_at=datetime.utcnow().isoformat()
    )
    
    # Create new dict with schema_version at the top
    versioned = {"schema_version": schema_info.to_dict()}
    versioned.update(data)
    
    return versioned


def get_schema_version(data: Dict[str, Any]) -> Optional[SchemaVersion]:
    """Get schema version from data.
    
    Args:
        data: Data dictionary that may contain schema_version
        
    Returns:
        SchemaVersion or None if not versioned
    """
    version_data = data.get("schema_version")
    if version_data is None:
        return None
    
    return SchemaVersion.from_dict(version_data)


def get_version_string(data: Dict[str, Any]) -> str:
    """Get version string from data.
    
    Args:
        data: Data dictionary
        
    Returns:
        Version string or "0.0.0" if not versioned
    """
    version = get_schema_version(data)
    return version.version if version else "0.0.0"


def needs_migration(
    data: Dict[str, Any],
    schema_type: str,
    target_version: Optional[str] = None
) -> bool:
    """Check if data needs migration to target version.
    
    Args:
        data: Data dictionary
        schema_type: Type of schema
        target_version: Target version (defaults to current version)
        
    Returns:
        True if migration is needed
    """
    if target_version is None:
        target_version = CURRENT_VERSIONS.get(schema_type, "1.0.0")
    
    current = get_version_string(data)
    return _compare_versions(current, target_version) < 0


def _compare_versions(v1: str, v2: str) -> int:
    """Compare two version strings.
    
    Args:
        v1: First version
        v2: Second version
        
    Returns:
        -1 if v1 < v2, 0 if equal, 1 if v1 > v2
    """
    def parse(v: str) -> Tuple[int, ...]:
        try:
            return tuple(int(x) for x in v.split('.'))
        except (ValueError, AttributeError):
            return (0, 0, 0)
    
    p1, p2 = parse(v1), parse(v2)
    
    # Pad to same length
    max_len = max(len(p1), len(p2))
    p1 = p1 + (0,) * (max_len - len(p1))
    p2 = p2 + (0,) * (max_len - len(p2))
    
    if p1 < p2:
        return -1
    elif p1 > p2:
        return 1
    return 0


def register_migration(
    schema_type: str,
    from_version: str,
    to_version: str
) -> Callable:
    """Decorator to register a migration function.
    
    Args:
        schema_type: Type of schema
        from_version: Source version
        to_version: Target version
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable[[Dict], Dict]) -> Callable[[Dict], Dict]:
        _migrations[(schema_type, from_version, to_version)] = func
        
        @wraps(func)
        def wrapper(data: Dict) -> Dict:
            return func(data)
        
        return wrapper
    
    return decorator


def get_migration_path(
    schema_type: str,
    from_version: str,
    to_version: str
) -> List[Tuple[str, str]]:
    """Find migration path from one version to another.
    
    Args:
        schema_type: Type of schema
        from_version: Source version
        to_version: Target version
        
    Returns:
        List of (from, to) version tuples representing migration steps
    """
    # Build graph of available migrations
    available = {
        (f, t) for (st, f, t) in _migrations.keys()
        if st == schema_type
    }
    
    if not available:
        return []
    
    # BFS to find path
    from collections import deque
    
    queue = deque([(from_version, [])])
    visited = {from_version}
    
    while queue:
        current, path = queue.popleft()
        
        if current == to_version:
            return path
        
        # Find all migrations from current version
        for (f, t) in available:
            if f == current and t not in visited:
                visited.add(t)
                queue.append((t, path + [(f, t)]))
    
    return []  # No path found


def migrate(
    data: Dict[str, Any],
    schema_type: str,
    target_version: Optional[str] = None
) -> Dict[str, Any]:
    """Migrate data to target version.
    
    Args:
        data: Data dictionary to migrate
        schema_type: Type of schema
        target_version: Target version (defaults to current version)
        
    Returns:
        Migrated data
        
    Raises:
        ValueError: If no migration path exists
    """
    if target_version is None:
        target_version = CURRENT_VERSIONS.get(schema_type, "1.0.0")
    
    current_version = get_version_string(data)
    
    if _compare_versions(current_version, target_version) >= 0:
        return data  # Already at or above target version
    
    # Find migration path
    path = get_migration_path(schema_type, current_version, target_version)
    
    if not path and current_version != target_version:
        # No explicit migrations, but we can still update version
        # This handles the case where schema is compatible but version differs
        result = dict(data)
        result["schema_version"] = SchemaVersion(
            schema_type=schema_type,
            version=target_version,
            created_at=datetime.utcnow().isoformat(),
            migrated_from=current_version
        ).to_dict()
        return result
    
    # Apply migrations in order
    result = data
    for from_v, to_v in path:
        migration_func = _migrations.get((schema_type, from_v, to_v))
        if migration_func:
            result = migration_func(result)
            
            # Update version in result
            result["schema_version"] = SchemaVersion(
                schema_type=schema_type,
                version=to_v,
                created_at=datetime.utcnow().isoformat(),
                migrated_from=from_v
            ).to_dict()
    
    return result


def ensure_versioned(
    data: Dict[str, Any],
    schema_type: str,
    default_version: str = "1.0.0"
) -> Dict[str, Any]:
    """Ensure data has schema version, adding if missing.
    
    Args:
        data: Data dictionary
        schema_type: Type of schema
        default_version: Version to use if not present
        
    Returns:
        Data with schema_version guaranteed
    """
    if "schema_version" not in data:
        return add_schema_version(data, schema_type, default_version)
    return data


# Example migrations (can be extended as needed)

@register_migration("worldview", "1.0.0", "2.0.0")
def migrate_worldview_v1_to_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """Example migration: worldview v1 to v2.
    
    This is a placeholder showing the migration pattern.
    Real migrations would transform the data structure.
    """
    result = dict(data)
    
    # Example: Add new field with default value
    if "synthesis_count" not in result:
        result["synthesis_count"] = 0
    
    # Example: Rename field
    if "knowledge_gaps" in result and "gaps" not in result:
        result["gaps"] = result.pop("knowledge_gaps")
    
    return result


# Utility functions for file operations

def save_versioned_json(
    data: Dict[str, Any],
    path: Path,
    schema_type: str,
    version: Optional[str] = None
):
    """Save data as versioned JSON.
    
    Args:
        data: Data to save
        path: File path
        schema_type: Type of schema
        version: Version (defaults to current)
    """
    versioned = add_schema_version(data, schema_type, version)
    
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(versioned, f, indent=2, ensure_ascii=False)


def load_versioned_json(
    path: Path,
    schema_type: str,
    auto_migrate: bool = True
) -> Dict[str, Any]:
    """Load versioned JSON with optional auto-migration.
    
    Args:
        path: File path
        schema_type: Expected schema type
        auto_migrate: Whether to auto-migrate to current version
        
    Returns:
        Loaded (and optionally migrated) data
    """
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Ensure versioned
    data = ensure_versioned(data, schema_type)
    
    # Auto-migrate if needed
    if auto_migrate and needs_migration(data, schema_type):
        data = migrate(data, schema_type)
    
    return data
