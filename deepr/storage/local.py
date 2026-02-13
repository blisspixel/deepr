"""Local filesystem storage implementation."""

import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from deepr.utils.security import InvalidInputError, PathTraversalError, sanitize_name

from .base import ReportMetadata, StorageBackend, StorageError


class LocalStorage(StorageBackend):
    """Local filesystem implementation of storage backend."""

    def __init__(self, base_path: str = "./reports"):
        """
        Initialize local storage.

        Args:
            base_path: Root directory for storing reports
        """
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Create campaigns subdirectory for multi-phase campaigns
        self.campaigns_path = self.base_path / "campaigns"
        self.campaigns_path.mkdir(parents=True, exist_ok=True)

    def _validate_job_id(self, job_id: str) -> str:
        """Validate job_id format and content.

        Args:
            job_id: User-provided job identifier

        Returns:
            Validated job_id

        Raises:
            StorageError: If job_id is invalid or contains traversal sequences
        """
        try:
            # Check for path traversal patterns
            if ".." in job_id or "/" in job_id or "\\" in job_id:
                raise PathTraversalError(f"Invalid job_id contains path traversal: {job_id}")
            # Validate format (alphanumeric, hyphens, underscores)
            sanitized = sanitize_name(job_id, allowed_chars=r"a-zA-Z0-9_-")
            return sanitized
        except (PathTraversalError, InvalidInputError) as e:
            raise StorageError(message=f"Invalid job_id: {e!s}", storage_type="local", original_error=e)

    def _validate_filename(self, filename: str) -> str:
        """Validate filename has no directory components.

        Args:
            filename: User-provided filename

        Returns:
            Validated filename

        Raises:
            StorageError: If filename contains directory separators
        """
        if "/" in filename or "\\" in filename or ".." in filename:
            raise StorageError(
                message=f"Invalid filename contains path components: {filename}",
                storage_type="local",
                original_error=None,
            )
        return filename

    def _create_readable_dirname(self, job_id: str, prompt: str, is_campaign: bool = False) -> str:
        """
        Create a human-readable directory name with timestamp and topic.

        Format: YYYY-MM-DD_HHMM_topic-slug_shortid
        Example: 2025-10-29_0825_ai-code-editor-market_ac2d48e1

        Args:
            job_id: UUID or campaign ID
            prompt: Research prompt to extract topic from
            is_campaign: Whether this is a campaign

        Returns:
            Human-readable directory name
        """
        # Get timestamp
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d_%H%M")

        # Create slug from prompt (first 50 chars, cleaned)
        slug = prompt[:50].lower() if prompt else ""
        # Remove special characters, keep alphanumeric and spaces
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        # Replace spaces with hyphens
        slug = re.sub(r"\s+", "-", slug.strip())
        # Remove multiple consecutive hyphens
        slug = re.sub(r"-+", "-", slug)
        # Trim to reasonable length
        slug = slug[:40].rstrip("-")

        # If slug is empty, use a default
        if not slug:
            slug = "research"

        # Extract short ID (last 8 chars of UUID or campaign ID)
        if job_id.startswith("campaign-"):
            # For campaign IDs like "campaign-86285e7bcd24" or "campaign-1759970251"
            short_id = job_id.replace("campaign-", "")[:12]
        else:
            # For UUIDs, take last segment
            short_id = job_id.split("-")[-1][:8]

        return f"{timestamp}_{slug}_{short_id}"

    def _get_job_dir(self, job_id: str) -> Path:
        """
        Get directory path for a specific job with validation.

        Supports both legacy job_id lookup and new human-readable names.
        Validates job_id and ensures the resolved path remains within base_path.

        Args:
            job_id: User-provided job identifier

        Returns:
            Path to the job directory

        Raises:
            StorageError: If job_id is invalid or path escapes base directory
        """
        # Validate job_id at method entry
        validated_id = self._validate_job_id(job_id)

        # First, check if this is already a full path (for new format)
        if validated_id.startswith(str(self.base_path)):
            job_dir = Path(validated_id)
        # Check campaigns folder first (for campaign-* IDs)
        elif validated_id.startswith("campaign-"):
            job_dir = None
            # Look in campaigns folder for matching directory
            if self.campaigns_path.exists():
                for dir_path in self.campaigns_path.iterdir():
                    if dir_path.is_dir() and validated_id in dir_path.name:
                        job_dir = dir_path
                        break
            # Fallback to direct path
            if job_dir is None:
                job_dir = self.campaigns_path / validated_id
        else:
            # For regular UUIDs, search ALL possible locations before falling back
            # Check for human-readable directory containing job_id OR short_id
            short_id = validated_id.split("-")[-1][:8] if "-" in validated_id else validated_id[:8]
            job_dir = None

            if self.base_path.exists():
                for dir_path in self.base_path.iterdir():
                    if dir_path.is_dir() and dir_path.name != "campaigns":
                        # Match full job_id or short_id in directory name
                        if validated_id in dir_path.name or short_id in dir_path.name:
                            job_dir = dir_path
                            break

            if job_dir is None:
                # Try direct match (legacy format) as fallback
                direct_path = self.base_path / validated_id
                if direct_path.exists():
                    job_dir = direct_path
                else:
                    # If not found anywhere, return the job_id as-is (will be created on save)
                    job_dir = self.base_path / validated_id

        # Final validation: ensure path is within base_path
        try:
            resolved = job_dir.resolve()
            resolved.relative_to(self.base_path.resolve())
        except ValueError:
            raise StorageError(
                message=f"Path escapes base directory: {job_id}",
                storage_type="local",
                original_error=PathTraversalError(f"Path escape: {job_dir}"),
            )

        return job_dir

    def _get_report_path(self, job_id: str, filename: str) -> Path:
        """Get full path for a specific report file with validation.

        Args:
            job_id: User-provided job identifier
            filename: User-provided filename

        Returns:
            Path to the report file

        Raises:
            StorageError: If filename is invalid or path escapes base directory
        """
        validated_filename = self._validate_filename(filename)
        job_dir = self._get_job_dir(job_id)  # Already validated

        full_path = job_dir / validated_filename

        # Final validation: ensure path is within base_path
        try:
            resolved = full_path.resolve()
            resolved.relative_to(self.base_path.resolve())
        except ValueError:
            raise StorageError(message="Report path escapes base directory", storage_type="local", original_error=None)

        return full_path

    async def save_report(
        self,
        job_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ReportMetadata:
        """Save report to local filesystem with human-readable naming."""
        try:
            # Determine if we should create a human-readable directory name
            # Only for new jobs (not existing legacy ones)
            job_dir = self._get_job_dir(job_id)

            # If directory doesn't exist, create with readable name
            if not job_dir.exists() and metadata and "prompt" in metadata:
                prompt = metadata["prompt"]
                is_campaign = job_id.startswith("campaign-")
                readable_name = self._create_readable_dirname(job_id, prompt, is_campaign)

                # Use campaigns subfolder for campaigns
                if is_campaign:
                    job_dir = self.campaigns_path / readable_name
                else:
                    job_dir = self.base_path / readable_name

            # Create directory
            job_dir.mkdir(parents=True, exist_ok=True)

            # Write report file (validate filename to prevent path traversal)
            validated_filename = self._validate_filename(filename)
            report_path = job_dir / validated_filename
            report_path.write_bytes(content)

            # Save metadata.json if metadata provided
            if metadata:
                metadata_path = job_dir / "metadata.json"
                metadata_content = {
                    "job_id": job_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "filename": filename,
                    "content_type": content_type,
                    "size_bytes": len(content),
                    **metadata,  # Include all additional metadata
                }
                metadata_path.write_text(json.dumps(metadata_content, indent=2))

            # Get file stats
            stat = report_path.stat()

            # Determine format from filename
            format_ext = Path(filename).suffix.lstrip(".")

            return ReportMetadata(
                job_id=job_id,
                filename=filename,
                format=format_ext,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                url=str(report_path),
                content_type=content_type,
            )

        except OSError as e:
            raise StorageError(message=f"Failed to save report: {e!s}", storage_type="local", original_error=e)

    async def get_report(self, job_id: str, filename: str) -> bytes:
        """Retrieve report from local filesystem."""
        try:
            report_path = self._get_report_path(job_id, filename)

            if not report_path.exists():
                raise FileNotFoundError(f"Report not found: {job_id}/{filename}")

            return report_path.read_bytes()

        except FileNotFoundError as e:
            raise StorageError(message=str(e), storage_type="local", original_error=e)
        except OSError as e:
            raise StorageError(
                message=f"Failed to retrieve report: {e!s}",
                storage_type="local",
                original_error=e,
            )

    async def list_reports(self, job_id: Optional[str] = None) -> list[ReportMetadata]:
        """List reports in local storage."""
        try:
            reports = []

            if job_id:
                # List reports for specific job
                job_dir = self._get_job_dir(job_id)
                if not job_dir.exists():
                    return []

                for report_path in job_dir.iterdir():
                    if report_path.is_file():
                        stat = report_path.stat()
                        format_ext = report_path.suffix.lstrip(".")

                        reports.append(
                            ReportMetadata(
                                job_id=job_id,
                                filename=report_path.name,
                                format=format_ext,
                                size_bytes=stat.st_size,
                                created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                                url=str(report_path),
                                content_type=self.get_content_type(report_path.name),
                            )
                        )
            else:
                # List all reports
                for job_dir in self.base_path.iterdir():
                    if job_dir.is_dir():
                        for report_path in job_dir.iterdir():
                            if report_path.is_file():
                                stat = report_path.stat()
                                format_ext = report_path.suffix.lstrip(".")

                                reports.append(
                                    ReportMetadata(
                                        job_id=job_dir.name,
                                        filename=report_path.name,
                                        format=format_ext,
                                        size_bytes=stat.st_size,
                                        created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                                        url=str(report_path),
                                        content_type=self.get_content_type(report_path.name),
                                    )
                                )

            return reports

        except OSError as e:
            raise StorageError(
                message=f"Failed to list reports: {e!s}",
                storage_type="local",
                original_error=e,
            )

    async def delete_report(self, job_id: str, filename: Optional[str] = None) -> bool:
        """Delete report(s) from local filesystem."""
        try:
            if filename:
                # Delete specific file
                report_path = self._get_report_path(job_id, filename)
                if report_path.exists():
                    report_path.unlink()
                    return True
                return False
            else:
                # Delete entire job directory
                job_dir = self._get_job_dir(job_id)
                if job_dir.exists():
                    shutil.rmtree(job_dir)
                    return True
                return False

        except OSError as e:
            raise StorageError(
                message=f"Failed to delete report: {e!s}",
                storage_type="local",
                original_error=e,
            )

    async def report_exists(self, job_id: str, filename: str) -> bool:
        """Check if report exists in local storage."""
        report_path = self._get_report_path(job_id, filename)
        return report_path.exists()

    async def get_report_url(self, job_id: str, filename: str, expires_in: int = 3600) -> str:
        """Get local file path as URL."""
        report_path = self._get_report_path(job_id, filename)

        if not report_path.exists():
            raise StorageError(
                message=f"Report not found: {job_id}/{filename}",
                storage_type="local",
                original_error=None,
            )

        # Return file:// URL for local paths
        return report_path.as_uri()

    async def cleanup_old_reports(self, days: int = 30) -> int:
        """Delete reports older than specified days."""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            deleted_count = 0

            for job_dir in self.base_path.iterdir():
                if not job_dir.is_dir():
                    continue

                # Check if all files in job directory are old
                all_old = True
                for report_path in job_dir.iterdir():
                    if report_path.is_file():
                        mtime = datetime.fromtimestamp(report_path.stat().st_mtime, tz=timezone.utc)
                        if mtime >= cutoff_date:
                            all_old = False
                            break

                # Delete entire job directory if all files are old
                if all_old:
                    file_count = len(list(job_dir.iterdir()))
                    shutil.rmtree(job_dir)
                    deleted_count += file_count

            return deleted_count

        except OSError as e:
            raise StorageError(
                message=f"Failed to cleanup old reports: {e!s}",
                storage_type="local",
                original_error=e,
            )
