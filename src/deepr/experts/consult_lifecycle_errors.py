"""Typed, path-safe errors for durable consult lifecycle operations."""

from __future__ import annotations

from collections.abc import Mapping


class ConsultLifecycleError(RuntimeError):
    """Base error for lifecycle journal operations."""


class ConsultLifecycleJournalError(ConsultLifecycleError):
    """Raised when persisted lifecycle history cannot be trusted."""


class ConsultLifecycleTransitionError(ConsultLifecycleError):
    """Raised when a requested state transition violates the contract."""


class ConsultLifecycleStorageError(ConsultLifecycleError):
    """Raised for path-safe durable storage I/O failures."""

    def __init__(self, operation: str, *, partial_write_possible: bool) -> None:
        self.operation = operation
        self.partial_write_possible = partial_write_possible
        ambiguity = " after a write may have started" if partial_write_possible else " before a journal write"
        super().__init__(f"Lifecycle storage failed during {operation}{ambiguity}")


class ConsultLifecycleLockTimeoutError(ConsultLifecycleStorageError):
    """Raised when lifecycle serialization cannot acquire its bounded locks."""

    def __init__(self, resource: str = "lifecycle") -> None:
        self.resource = resource
        super().__init__("lock acquisition", partial_write_possible=False)


class ConsultLifecycleElapsedLimitError(ConsultLifecycleTransitionError):
    """Raised after the lifecycle durably stops at its elapsed ceiling."""

    def __init__(self, trace_id: str, event: Mapping[str, object]) -> None:
        self.trace_id = trace_id
        self.event = dict(event)
        super().__init__(f"Lifecycle {trace_id} reached its elapsed-time ceiling")


__all__ = [
    "ConsultLifecycleElapsedLimitError",
    "ConsultLifecycleError",
    "ConsultLifecycleJournalError",
    "ConsultLifecycleLockTimeoutError",
    "ConsultLifecycleStorageError",
    "ConsultLifecycleTransitionError",
]
