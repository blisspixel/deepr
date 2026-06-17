"""Local filesystem storage implementation."""

import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from deepr.utils.security import InvalidInputError, PathTraversalError, sanitize_name

from .base import ReportMetadata, StorageBackend, StorageError


class LocalStorage(StorageBackend):
    """Local filesystem implementation of storage backend."""

    def __init__(self, base_path: str | None = None):
        """
        Initialize local storage.

        Args:
            base_path: Root directory for storing reports. Defaults to the
                configured reports root (``storage.local_path`` /
                ``DEEPR_REPORTS_PATH``) so every component reads and writes
                the same root.
        """
        if base_path is None:
            from deepr.config import load_config

            base_path = load_config()["results_dir"]
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
            raise StorageError(message=f"Invalid job_id: {e!s}", storage_type="local", original_error=e) from e

    def _validate_filename(self, filename: str) -> str:
        """Validate filename has no directory components.

        Args:
            filename: User-provided filename

        Returns:
            Validated filename

        Raises:
            StorageError: If filename contains directory separators
        """
        if not filename or not filename.strip() or filename in {".", ".."} or "\x00" in filename:
            raise StorageError(
                message=f"Invalid filename: {filename!r}",
                storage_type="local",
                original_error=None,
            )
        if "/" in filename or "\\" in filename or ".." in filename:
            raise StorageError(
                message=f"Invalid filename contains path components: {filename}",
                storage_type="local",
                original_error=None,
            )
        return filename

    @staticmethod
    def _readable_lookup_suffix(job_id: str) -> str:
        """Return the stable suffix used in generated readable directories."""
        if job_id.startswith("campaign-"):
            return job_id.replace("campaign-", "", 1)[:12]
        return job_id.split("-")[-1][:8]

    @classmethod
    def _can_use_readable_dirname(cls, job_id: str) -> bool:
        """Return True when the generated suffix is specific enough to find later."""
        return len(cls._readable_lookup_suffix(job_id)) >= 8

    def _find_readable_dir(self, root: Path, job_id: str, *, skip_campaigns: bool = False) -> Path | None:
        """Find a generated readable directory by its stable suffix."""
        if not root.exists() or not self._can_use_readable_dirname(job_id):
            return None

        suffix = f"_{self._readable_lookup_suffix(job_id)}"
        for dir_path in root.iterdir():
            if not dir_path.is_dir():
                continue
            if skip_campaigns and dir_path.name == "campaigns":
                continue
            if dir_path.name.endswith(suffix):
                return dir_path
        return None

    def _ensure_within_base(self, job_id: str, job_dir: Path) -> Path:
        """Resolve and validate a job directory without allowing path escape."""
        try:
            resolved = job_dir.resolve()
            resolved.relative_to(self.base_path.resolve())
        except ValueError as err:
            raise StorageError(
                message=f"Path escapes base directory: {job_id}",
                storage_type="local",
                original_error=PathTraversalError(f"Path escape: {job_dir}"),
            ) from err
        return job_dir

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
            short_id = self._readable_lookup_suffix(job_id)
        else:
            # For UUIDs, take last segment
            short_id = self._readable_lookup_suffix(job_id)

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

        # First, check exact legacy directory names.
        direct_path = self.base_path / validated_id
        if direct_path.exists():
            return self._ensure_within_base(job_id, direct_path)

        if validated_id.startswith("campaign-"):
            readable_dir = self._find_readable_dir(self.campaigns_path, validated_id)
            job_dir = readable_dir or self.campaigns_path / validated_id
            return self._ensure_within_base(job_id, job_dir)

        # For regular UUIDs, search generated readable directories before
        # falling back to the exact job_id path that will be created on save.
        readable_dir = self._find_readable_dir(self.base_path, validated_id, skip_campaigns=True)
        job_dir = readable_dir or direct_path

        return self._ensure_within_base(job_id, job_dir)

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
            raise StorageError(
                message="Report path escapes base directory",
                storage_type="local",
                original_error=None,
            ) from None

        return full_path

    async def save_report(
        self,
        job_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> ReportMetadata:
        """Save report to local filesystem with human-readable naming."""
        try:
            # Determine if we should create a human-readable directory name
            # Only for new jobs (not existing legacy ones)
            job_dir = self._get_job_dir(job_id)

            # If directory doesn't exist, create with readable name
            if not job_dir.exists() and metadata and "prompt" in metadata and self._can_use_readable_dirname(job_id):
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
                    "created_at": datetime.now(UTC).isoformat(),
                    "filename": filename,
                    "content_type": content_type,
                    "size_bytes": len(content),
                    **metadata,  # Include all additional metadata
                }
                from deepr.utils.atomic_io import atomic_write_json

                atomic_write_json(metadata_path, metadata_content)

            # Get file stats
            stat = report_path.stat()

            # Determine format from filename
            format_ext = Path(filename).suffix.lstrip(".")

            return ReportMetadata(
                job_id=job_id,
                filename=filename,
                format=format_ext,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                url=str(report_path),
                content_type=content_type,
            )

        except OSError as e:
            raise StorageError(message=f"Failed to save report: {e!s}", storage_type="local", original_error=e) from e

    async def get_report(self, job_id: str, filename: str) -> bytes:
        """Retrieve report from local filesystem."""
        try:
            report_path = self._get_report_path(job_id, filename)

            if not report_path.exists():
                raise FileNotFoundError(f"Report not found: {job_id}/{filename}")

            return report_path.read_bytes()

        except FileNotFoundError as e:
            raise StorageError(message=str(e), storage_type="local", original_error=e) from e
        except OSError as e:
            raise StorageError(
                message=f"Failed to retrieve report: {e!s}",
                storage_type="local",
                original_error=e,
            ) from e

    async def list_reports(self, job_id: str | None = None) -> list[ReportMetadata]:
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
                                created_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
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
                                        created_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
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
            ) from e

    async def delete_report(self, job_id: str, filename: str | None = None) -> bool:
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
            ) from e

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
            cutoff_date = datetime.now(UTC) - timedelta(days=days)
            deleted_count = 0

            for job_dir in self.base_path.iterdir():
                if not job_dir.is_dir():
                    continue

                # Check if all files in job directory are old
                all_old = True
                for report_path in job_dir.iterdir():
                    if report_path.is_file():
                        mtime = datetime.fromtimestamp(report_path.stat().st_mtime, tz=UTC)
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
            ) from e
