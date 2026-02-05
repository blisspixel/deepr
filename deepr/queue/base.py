"""Abstract base classes for queue backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


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
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Request options
    documents: List[str] = field(default_factory=list)
    enable_web_search: bool = True
    enable_code_interpreter: bool = True
    cost_limit: Optional[float] = None

    # Execution tracking
    provider_job_id: Optional[str] = None
    worker_id: Optional[str] = None
    attempts: int = 0
    last_error: Optional[str] = None

    # Results
    report_paths: Dict[str, str] = field(default_factory=dict)
    cost: Optional[float] = None
    tokens_used: Optional[int] = None

    # Metadata
    tenant_id: Optional[str] = None
    workspace_id: Optional[str] = None
    submitted_by: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    callback_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Auto-mode routing (when --auto flag is used)
    auto_routed: bool = False
    routing_decision: Optional[Dict[str, Any]] = None  # Serialized AutoModeDecision
    batch_id: Optional[str] = None  # For batch processing


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
    async def dequeue(self, worker_id: str) -> Optional[ResearchJob]:
        """
        Get next job from queue (highest priority first).

        Args:
            worker_id: ID of worker claiming the job

        Returns:
            Next job or None if queue is empty
        """
        pass

    @abstractmethod
    async def get_job(self, job_id: str) -> Optional[ResearchJob]:
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
        error: Optional[str] = None,
        provider_job_id: Optional[str] = None,
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
        report_paths: Dict[str, str],
        cost: Optional[float] = None,
        tokens_used: Optional[int] = None,
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
        status: Optional[JobStatus] = None,
        tenant_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ResearchJob]:
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
    async def get_queue_stats(self) -> Dict[str, Any]:
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
