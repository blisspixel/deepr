"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path


@dataclass
class ReportMetadata:
    """Metadata for a stored report."""

    job_id: str
    filename: str
    format: str  # txt, md, json, docx, pdf
    size_bytes: int
    created_at: datetime
    url: str  # Local path or blob URL
    content_type: str


class StorageBackend(ABC):
    """
    Abstract base class for storage backends.

    Implementations must handle:
    - Report storage and retrieval
    - Format-specific handling (txt, md, json, docx, pdf)
    - Listing and metadata operations
    - Cleanup and deletion
    """

    @abstractmethod
    async def save_report(
        self, job_id: str, filename: str, content: bytes, content_type: str, metadata: Optional[Dict[str, Any]] = None
    ) -> ReportMetadata:
        """
        Save a report to storage.

        Args:
            job_id: Unique job identifier
            filename: Report filename (e.g., "report.md")
            content: Report content as bytes
            content_type: MIME type (e.g., "text/markdown")
            metadata: Additional metadata to store

        Returns:
            Metadata for the saved report

        Raises:
            StorageError: If save operation fails
        """
        pass

    @abstractmethod
    async def get_report(self, job_id: str, filename: str) -> bytes:
        """
        Retrieve report content from storage.

        Args:
            job_id: Unique job identifier
            filename: Report filename

        Returns:
            Report content as bytes

        Raises:
            StorageError: If retrieval fails or report doesn't exist
        """
        pass

    @abstractmethod
    async def list_reports(self, job_id: Optional[str] = None) -> List[ReportMetadata]:
        """
        List available reports.

        Args:
            job_id: Filter by specific job (optional)

        Returns:
            List of report metadata

        Raises:
            StorageError: If listing operation fails
        """
        pass

    @abstractmethod
    async def delete_report(self, job_id: str, filename: Optional[str] = None) -> bool:
        """
        Delete a report or all reports for a job.

        Args:
            job_id: Unique job identifier
            filename: Specific filename to delete (deletes all if None)

        Returns:
            True if deletion was successful

        Raises:
            StorageError: If deletion fails
        """
        pass

    @abstractmethod
    async def report_exists(self, job_id: str, filename: str) -> bool:
        """
        Check if a report exists in storage.

        Args:
            job_id: Unique job identifier
            filename: Report filename

        Returns:
            True if report exists
        """
        pass

    @abstractmethod
    async def get_report_url(self, job_id: str, filename: str, expires_in: int = 3600) -> str:
        """
        Get a URL to access the report.

        Args:
            job_id: Unique job identifier
            filename: Report filename
            expires_in: URL expiration time in seconds (for signed URLs)

        Returns:
            Accessible URL (local path or public/signed URL)

        Raises:
            StorageError: If URL generation fails
        """
        pass

    @abstractmethod
    async def cleanup_old_reports(self, days: int = 30) -> int:
        """
        Delete reports older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of reports deleted

        Raises:
            StorageError: If cleanup fails
        """
        pass

    def get_content_type(self, filename: str) -> str:
        """
        Determine content type from filename extension.

        Args:
            filename: The filename

        Returns:
            MIME type string
        """
        ext = Path(filename).suffix.lower()
        content_types = {
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".json": "application/json",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pdf": "application/pdf",
        }
        return content_types.get(ext, "application/octet-stream")


class StorageError(Exception):
    """Base exception for storage-related errors."""

    def __init__(
        self, message: str, storage_type: str, original_error: Optional[Exception] = None
    ):
        self.message = message
        self.storage_type = storage_type
        self.original_error = original_error
        super().__init__(self.message)
