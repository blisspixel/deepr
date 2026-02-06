"""Queue management for research job orchestration."""

from .azure_queue import ServiceBusQueue
from .base import JobStatus, QueueBackend, ResearchJob
from .local_queue import SQLiteQueue

__all__ = ["QueueBackend", "ResearchJob", "JobStatus", "SQLiteQueue", "ServiceBusQueue"]

from typing import Literal

QueueType = Literal["local", "azure"]


def create_queue(queue_type: QueueType, **kwargs) -> QueueBackend:
    """
    Factory function to create the appropriate queue backend.

    Args:
        queue_type: Either "local" or "azure"
        **kwargs: Queue-specific configuration

    Returns:
        Initialized queue backend instance

    Raises:
        ValueError: If queue_type is not supported
    """
    if queue_type == "local":
        return SQLiteQueue(**kwargs)
    elif queue_type == "azure":
        return ServiceBusQueue(**kwargs)
    else:
        raise ValueError(f"Unsupported queue type: {queue_type}")


__all__ = [
    "QueueBackend",
    "ResearchJob",
    "JobStatus",
    "SQLiteQueue",
    "ServiceBusQueue",
    "create_queue",
    "QueueType",
]
