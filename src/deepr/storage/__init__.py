"""Storage abstraction for multiple backends (local, Azure Blob)."""

from typing import Literal

from .base import ReportMetadata, StorageBackend
from .blob import AzureBlobStorage
from .findings_store import FindingsStore, StoredFinding
from .local import LocalStorage

StorageType = Literal["local", "blob"]


def create_storage(storage_type: StorageType, **kwargs) -> StorageBackend:
    """
    Factory function to create the appropriate storage backend.

    Args:
        storage_type: Either "local" or "blob"
        **kwargs: Storage-specific configuration

    Returns:
        Initialized storage backend instance

    Raises:
        ValueError: If storage_type is not supported
    """
    if storage_type == "local":
        return LocalStorage(**kwargs)
    elif storage_type == "blob":
        return AzureBlobStorage(**kwargs)
    else:
        raise ValueError(f"Unsupported storage type: {storage_type}")


__all__ = [
    "AzureBlobStorage",
    "FindingsStore",
    "LocalStorage",
    "ReportMetadata",
    "StorageBackend",
    "StorageType",
    "StoredFinding",
    "create_storage",
]
