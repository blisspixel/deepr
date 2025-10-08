"""Job management and tracking."""

import os
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict


@dataclass
class JobRecord:
    """Record of a research job."""

    response_id: str
    status: str
    timestamp: str
    original_prompt: str
    refined_prompt: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    run_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class JobManager:
    """
    Manages job tracking and persistence.

    Supports multiple backend types:
    - JSONL: Line-delimited JSON log file
    - SQLite: Local database (future)
    - CosmosDB: Azure Cosmos DB (future)
    """

    def __init__(self, backend_type: str = "jsonl", log_path: str = "data/logs/job_log.jsonl"):
        """
        Initialize job manager.

        Args:
            backend_type: Type of storage backend (jsonl, sqlite, cosmosdb)
            log_path: Path to log file (for JSONL backend)
        """
        self.backend_type = backend_type
        self.log_path = Path(log_path)

        # Ensure log directory exists
        if backend_type == "jsonl":
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    async def log_submission(
        self,
        response_id: str,
        original_prompt: str,
        refined_prompt: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Log a new job submission.

        Args:
            response_id: Job/response ID from provider
            original_prompt: Original user prompt
            refined_prompt: Refined prompt (if applicable)
            model: Model name used
            provider: Provider type (openai/azure)
            run_id: Internal run ID
            metadata: Additional metadata
        """
        record = JobRecord(
            response_id=response_id,
            status="queued",
            timestamp=datetime.now(timezone.utc).isoformat(),
            original_prompt=original_prompt,
            refined_prompt=refined_prompt,
            model=model,
            provider=provider,
            run_id=run_id,
            metadata=metadata,
        )

        if self.backend_type == "jsonl":
            await self._write_jsonl_record(record)

    async def update_status(self, response_id: str, new_status: str):
        """
        Update job status.

        Args:
            response_id: Job identifier
            new_status: New status value
        """
        if self.backend_type == "jsonl":
            await self._update_jsonl_status(response_id, new_status)

    async def get_job(self, response_id: str) -> Optional[JobRecord]:
        """
        Retrieve a specific job record.

        Args:
            response_id: Job identifier

        Returns:
            Job record if found, None otherwise
        """
        if self.backend_type == "jsonl":
            return await self._get_jsonl_job(response_id)

        return None

    async def list_jobs(
        self, status: Optional[str] = None, limit: int = 100
    ) -> List[JobRecord]:
        """
        List job records.

        Args:
            status: Filter by status (optional)
            limit: Maximum number of records to return

        Returns:
            List of job records
        """
        if self.backend_type == "jsonl":
            return await self._list_jsonl_jobs(status, limit)

        return []

    async def cleanup_old_jobs(self, days: int = 7) -> int:
        """
        Clean up completed jobs older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of jobs cleaned up
        """
        if self.backend_type == "jsonl":
            return await self._cleanup_jsonl_jobs(days)

        return 0

    # JSONL Backend Implementation

    async def _write_jsonl_record(self, record: JobRecord):
        """Write a record to JSONL file."""
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")

    async def _update_jsonl_status(self, response_id: str, new_status: str):
        """Update status in JSONL file."""
        if not self.log_path.exists():
            return

        updated_lines = []

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    if record.get("response_id") == response_id:
                        record["status"] = new_status
                        line = json.dumps(record)
                except Exception:
                    pass
                updated_lines.append(line if line.endswith("\n") else line + "\n")

        with open(self.log_path, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)

    async def _get_jsonl_job(self, response_id: str) -> Optional[JobRecord]:
        """Get job from JSONL file."""
        if not self.log_path.exists():
            return None

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    if record.get("response_id") == response_id:
                        return JobRecord(**record)
                except Exception:
                    continue

        return None

    async def _list_jsonl_jobs(
        self, status: Optional[str] = None, limit: int = 100
    ) -> List[JobRecord]:
        """List jobs from JSONL file."""
        if not self.log_path.exists():
            return []

        jobs = []

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record_dict = json.loads(line)
                    if status is None or record_dict.get("status") == status:
                        jobs.append(JobRecord(**record_dict))
                except Exception:
                    continue

        # Sort by timestamp (newest first)
        jobs.sort(
            key=lambda j: datetime.fromisoformat(j.timestamp), reverse=True
        )

        return jobs[:limit]

    async def _cleanup_jsonl_jobs(self, days: int) -> int:
        """Clean up old jobs from JSONL file."""
        if not self.log_path.exists():
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        retained = []
        cleaned = 0

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    timestamp = datetime.fromisoformat(record.get("timestamp", ""))

                    # Keep if not completed or not old enough
                    if record.get("status") != "completed" or timestamp >= cutoff:
                        retained.append(line)
                    else:
                        cleaned += 1
                except Exception:
                    retained.append(line)

        if cleaned > 0:
            with open(self.log_path, "w", encoding="utf-8") as f:
                f.writelines(retained)

        return cleaned
