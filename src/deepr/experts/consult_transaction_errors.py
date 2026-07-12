"""Path-safe public errors for durable expert consult transactions."""

from __future__ import annotations


class ConsultElapsedLimitError(TimeoutError):
    """Raised when a consult reaches its elapsed-time ceiling."""

    def __init__(self, trace_id: str, max_elapsed_seconds: float, *, retryable: bool) -> None:
        self.trace_id = trace_id
        self.max_elapsed_seconds = max_elapsed_seconds
        self.retryable = retryable
        super().__init__(f"Consult {trace_id} exceeded its {max_elapsed_seconds:g}-second elapsed-time ceiling.")


class ConsultStorageError(RuntimeError):
    """Path-safe public storage failure with transaction lineage."""

    def __init__(
        self,
        trace_id: str,
        resource: str,
        *,
        retryable: bool = True,
        settlement_failure: str | None = None,
        partial_write_possible: bool = False,
        error_code: str,
    ) -> None:
        self.trace_id = trace_id
        self.retryable = retryable
        self.consult_settlement_failure = settlement_failure
        self.consult_lifecycle_terminal: str | None = None
        self.partial_write_possible = partial_write_possible
        self.error_code = error_code
        label = resource if resource in {"consult trace", "lifecycle"} else "consult"
        failure = "lock" if error_code == "CONSULT_STORAGE_LOCK_TIMEOUT" else "I/O"
        guidance = (
            "retry safely"
            if retryable
            else "do not retry the full consultation because provider work or durable state may be ambiguous"
        )
        super().__init__(f"Consult {trace_id} encountered a durable {label} {failure} failure; {guidance}")


class ConsultStorageLockTimeoutError(ConsultStorageError):
    """Path-safe bounded lock failure with transaction lineage."""

    def __init__(
        self,
        trace_id: str,
        resource: str,
        *,
        retryable: bool = True,
        settlement_failure: str | None = None,
    ) -> None:
        super().__init__(
            trace_id,
            resource,
            retryable=retryable,
            settlement_failure=settlement_failure,
            error_code="CONSULT_STORAGE_LOCK_TIMEOUT",
        )


class ConsultStorageIOError(ConsultStorageError):
    """Path-safe durable I/O failure with conservative retry metadata."""

    def __init__(
        self,
        trace_id: str,
        resource: str,
        *,
        retryable: bool,
        partial_write_possible: bool,
        settlement_failure: str | None = None,
    ) -> None:
        super().__init__(
            trace_id,
            resource,
            retryable=retryable,
            settlement_failure=settlement_failure,
            partial_write_possible=partial_write_possible,
            error_code="CONSULT_STORAGE_IO_ERROR",
        )


__all__ = [
    "ConsultElapsedLimitError",
    "ConsultStorageError",
    "ConsultStorageIOError",
    "ConsultStorageLockTimeoutError",
]
