"""Abstract base classes for queue backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

_INTERNAL_JOB_METADATA_KEYS = frozenset(
    {
        "cleanup_vector_store",
        "cost_reservation_estimated_usd",
        "cost_reservation_id",
        "cost_reservation_model",
        "cost_reservation_provider",
        "provider_file_ids",
        "uploaded_files",
        "vector_store_id",
    }
)


def client_job_metadata(value: object) -> dict[str, Any]:
    """Validate metadata supplied by an untrusted job client."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("metadata must be an object")
    if _INTERNAL_JOB_METADATA_KEYS.intersection(value):
        raise ValueError("metadata contains reserved fields")
    return dict(value)


def public_job_metadata(value: object) -> dict[str, Any]:
    """Return client-visible metadata without provider lifecycle authority."""
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if key not in _INTERNAL_JOB_METADATA_KEYS}


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class JobStatus(str, Enum):
    """Job status enum."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ResearchJob:
    """Research job definition."""

    id: str
    prompt: str
    model: str = "o3-deep-research"
    provider: str = "openai"  # openai, azure, gemini
    status: JobStatus = JobStatus.QUEUED
    priority: int = 5  # 1-10, higher = more priority

    # Timestamps
    submitted_at: datetime = field(default_factory=_utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Request options
    documents: list[str] = field(default_factory=list)
    enable_web_search: bool = True
    enable_code_interpreter: bool = True
    cost_limit: float | None = None

    # Execution tracking
    provider_job_id: str | None = None
    worker_id: str | None = None
    attempts: int = 0
    last_error: str | None = None

    # Results
    report_paths: dict[str, str] = field(default_factory=dict)
    cost: float | None = None
    tokens_used: int | None = None

    # Metadata
    tenant_id: str | None = None
    workspace_id: str | None = None
    submitted_by: str | None = None
    tags: list[str] = field(default_factory=list)
    callback_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Auto-mode routing (when --auto flag is used)
    auto_routed: bool = False
    routing_decision: dict[str, Any] | None = None  # Serialized AutoModeDecision
    batch_id: str | None = None  # For batch processing

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict for WebSocket events."""
        result = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, Enum):
                value = value.value
            elif isinstance(value, datetime):
                value = value.isoformat()
            elif isinstance(value, Path):
                value = str(value)
            result[f.name] = public_job_metadata(value) if f.name == "metadata" else value
        return result


class QueueBackend(ABC):
    """
    Abstract base class for queue backends.

    Supports:
    - SQLite for local development
    - Azure Service Bus for cloud deployment
    - Redis for mid-scale deployments
    """

    @abstractmethod
    async def enqueue(self, job: ResearchJob) -> str:
        """
        Add job to queue.

        Args:
            job: Research job to enqueue

        Returns:
            Job ID
        """
        pass

    @abstractmethod
    async def dequeue(self, worker_id: str) -> ResearchJob | None:
        """
        Get next job from queue (highest priority first).

        Args:
            worker_id: ID of worker claiming the job

        Returns:
            Next job or None if queue is empty
        """
        pass

    @abstractmethod
    async def get_job(self, job_id: str) -> ResearchJob | None:
        """
        Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job or None if not found
        """
        pass

    @abstractmethod
    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
        provider_job_id: str | None = None,
    ) -> bool:
        """
        Update job status.

        Args:
            job_id: Job identifier
            status: New status
            error: Error message if failed
            provider_job_id: Provider's job ID if submitted

        Returns:
            True if update successful
        """
        pass

    @abstractmethod
    async def update_results(
        self,
        job_id: str,
        report_paths: dict[str, str],
        cost: float | None = None,
        tokens_used: int | None = None,
    ) -> bool:
        """
        Update job results.

        Args:
            job_id: Job identifier
            report_paths: Dict mapping format to storage path
            cost: Total cost
            tokens_used: Total tokens consumed

        Returns:
            True if update successful
        """
        pass

    @abstractmethod
    async def list_jobs(
        self,
        status: JobStatus | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ResearchJob]:
        """
        List jobs with optional filtering.

        Args:
            status: Filter by status
            tenant_id: Filter by tenant (for multi-tenancy)
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of jobs
        """
        pass

    @abstractmethod
    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a queued or processing job.

        Args:
            job_id: Job identifier

        Returns:
            True if cancelled
        """
        pass

    @abstractmethod
    async def cancel_active_job(self, job_id: str) -> bool:
        """Cancel a job only while its durable state is queued or processing."""
        raise NotImplementedError

    @abstractmethod
    async def clear_cleanup_metadata(self, job_id: str) -> bool:
        """Remove provider cleanup authority after confirmed deletion."""
        raise NotImplementedError

    @abstractmethod
    async def get_queue_stats(self) -> dict[str, Any]:
        """
        Get queue statistics.

        Returns:
            Dict with stats (queued count, processing count, etc.)
        """
        pass

    @abstractmethod
    async def cleanup_old_jobs(self, days: int = 30) -> int:
        """
        Remove completed/failed jobs older than specified days.

        Args:
            days: Age threshold

        Returns:
            Number of jobs removed
        """
        pass


class QueueError(Exception):
    """Base exception for queue operations."""

    pass
