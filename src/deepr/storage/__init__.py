"""Storage abstraction for multiple backends (local, Azure Blob)."""

from typing import TYPE_CHECKING, Any, Literal

from .base import ReportMetadata, StorageBackend
from .findings_store import FindingsStore, StoredFinding
from .local import LocalStorage

if TYPE_CHECKING:
    from .blob import AzureBlobStorage

StorageType = Literal["local", "blob"]


def create_storage(storage_type: StorageType, **kwargs: Any) -> StorageBackend:
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
        from .blob import AzureBlobStorage

        return AzureBlobStorage(**kwargs)
    else:
        raise ValueError(f"Unsupported storage type: {storage_type}")


def __getattr__(name: str) -> Any:
    """Load the optional Azure backend only when a caller requests it."""
    if name == "AzureBlobStorage":
        from .blob import AzureBlobStorage

        return AzureBlobStorage
    raise AttributeError(name)


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
