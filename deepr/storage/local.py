"""Local filesystem storage implementation."""

import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from .base import StorageBackend, ReportMetadata, StorageError


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

    def _get_job_dir(self, job_id: str) -> Path:
        """Get directory path for a specific job."""
        return self.base_path / job_id

    def _get_report_path(self, job_id: str, filename: str) -> Path:
        """Get full path for a specific report file."""
        return self._get_job_dir(job_id) / filename

    async def save_report(
        self,
        job_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReportMetadata:
        """Save report to local filesystem."""
        try:
            # Create job directory if it doesn't exist
            job_dir = self._get_job_dir(job_id)
            job_dir.mkdir(parents=True, exist_ok=True)

            # Write report file
            report_path = self._get_report_path(job_id, filename)
            report_path.write_bytes(content)

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

        except Exception as e:
            raise StorageError(
                message=f"Failed to save report: {str(e)}", storage_type="local", original_error=e
            )

    async def get_report(self, job_id: str, filename: str) -> bytes:
        """Retrieve report from local filesystem."""
        try:
            report_path = self._get_report_path(job_id, filename)

            if not report_path.exists():
                raise FileNotFoundError(f"Report not found: {job_id}/{filename}")

            return report_path.read_bytes()

        except FileNotFoundError as e:
            raise StorageError(
                message=str(e), storage_type="local", original_error=e
            )
        except Exception as e:
            raise StorageError(
                message=f"Failed to retrieve report: {str(e)}",
                storage_type="local",
                original_error=e,
            )

    async def list_reports(self, job_id: Optional[str] = None) -> List[ReportMetadata]:
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
                                        created_at=datetime.fromtimestamp(
                                            stat.st_mtime, tz=timezone.utc
                                        ),
                                        url=str(report_path),
                                        content_type=self.get_content_type(report_path.name),
                                    )
                                )

            return reports

        except Exception as e:
            raise StorageError(
                message=f"Failed to list reports: {str(e)}",
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

        except Exception as e:
            raise StorageError(
                message=f"Failed to delete report: {str(e)}",
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
                    shutil.rmtree(job_dir)
                    deleted_count += len(list(job_dir.iterdir()))

            return deleted_count

        except Exception as e:
            raise StorageError(
                message=f"Failed to cleanup old reports: {str(e)}",
                storage_type="local",
                original_error=e,
            )
