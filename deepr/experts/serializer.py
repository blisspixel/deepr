"""Serialization utilities for expert profiles.

This module extracts serialization logic from ExpertProfile to reduce
god class complexity. Handles datetime conversions and composed component
serialization.

Requirements: 5.5 - Extract to_dict/from_dict logic
"""

from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from deepr.experts.profile import ExpertProfile


# Fields that contain datetime objects and need ISO conversion
DATETIME_FIELDS = [
    "created_at",
    "updated_at",
    "knowledge_cutoff_date",
    "last_knowledge_refresh",
    "monthly_spending_reset_date",
]

# Fields that are composed components (not serialized directly)
COMPOSED_FIELDS = ["_temporal_state", "_freshness_checker", "_budget_manager", "_activity_tracker"]

# Metadata fields to exclude from ExpertProfile constructor
METADATA_FIELDS = ["schema_version"]


def datetime_to_iso(dt: Optional[datetime]) -> Optional[str]:
    """Convert datetime to ISO format string.

    Args:
        dt: Datetime object or None

    Returns:
        ISO format string or None
    """
    if dt is None:
        return None
    return dt.isoformat()


def iso_to_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    """Convert ISO format string to datetime.

    Args:
        iso_str: ISO format string or None

    Returns:
        Datetime object or None
    """
    if iso_str is None:
        return None
    if isinstance(iso_str, datetime):
        return iso_str
    return datetime.fromisoformat(iso_str)


def profile_to_dict(profile: "ExpertProfile") -> Dict[str, Any]:
    """Convert ExpertProfile to dictionary for JSON serialization.

    Excludes composed components (_temporal_state, _freshness_checker, etc.)
    which are runtime-only and reconstructed on load.

    Args:
        profile: ExpertProfile instance

    Returns:
        Dictionary suitable for JSON serialization
    """
    data = asdict(profile)

    # Remove composed components (not serialized)
    for field in COMPOSED_FIELDS:
        data.pop(field, None)

    # Convert datetime fields to ISO format
    for field in DATETIME_FIELDS:
        value = getattr(profile, field, None)
        if value is not None:
            data[field] = datetime_to_iso(value)

    return data


def dict_to_profile_kwargs(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert dictionary to kwargs for ExpertProfile constructor.

    Handles datetime conversion and removes any composed component
    fields that may have been accidentally serialized.

    Args:
        data: Dictionary with profile data

    Returns:
        Dictionary suitable for ExpertProfile(**kwargs)
    """
    # Make a copy to avoid modifying the original
    kwargs = data.copy()

    # Remove composed components if present (they're reconstructed in __post_init__)
    for field in COMPOSED_FIELDS:
        kwargs.pop(field, None)

    # Remove metadata fields that aren't part of ExpertProfile
    for field in METADATA_FIELDS:
        kwargs.pop(field, None)

    # Convert ISO format strings to datetime
    for field in DATETIME_FIELDS:
        if field in kwargs and isinstance(kwargs[field], str):
            kwargs[field] = iso_to_datetime(kwargs[field])

    return kwargs


class ProfileSerializer:
    """Handles serialization and deserialization of ExpertProfile.

    Provides a clean interface for converting profiles to/from dictionaries
    with proper datetime handling and composed component management.
    """

    @staticmethod
    def to_dict(profile: "ExpertProfile") -> Dict[str, Any]:
        """Convert profile to dictionary.

        Args:
            profile: ExpertProfile instance

        Returns:
            Dictionary for JSON serialization
        """
        return profile_to_dict(profile)

    @staticmethod
    def from_dict(data: Dict[str, Any], profile_class: type) -> "ExpertProfile":
        """Create profile from dictionary.

        Args:
            data: Dictionary with profile data
            profile_class: ExpertProfile class (to avoid circular import)

        Returns:
            ExpertProfile instance
        """
        kwargs = dict_to_profile_kwargs(data)
        return profile_class(**kwargs)

    @staticmethod
    def serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
        """Serialize datetime to ISO string.

        Args:
            dt: Datetime or None

        Returns:
            ISO string or None
        """
        return datetime_to_iso(dt)

    @staticmethod
    def deserialize_datetime(iso_str: Optional[str]) -> Optional[datetime]:
        """Deserialize ISO string to datetime.

        Args:
            iso_str: ISO string or None

        Returns:
            Datetime or None
        """
        return iso_to_datetime(iso_str)
