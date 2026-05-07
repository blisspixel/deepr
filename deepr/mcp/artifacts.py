"""Standardised artifact ID manifests for MCP tool responses.

Every MCP tool response should include an ``artifact_ids`` dict for
end-to-end correlation across research jobs, expert sessions, and traces.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


def _new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class ArtifactManifest:
    """Collection of artifact IDs returned by an MCP tool."""

    trace_id: str = field(default_factory=_new_trace_id)
    job_id: str = ""
    report_id: str = ""
    expert_id: str = ""
    session_id: str = ""
    workflow_id: str = ""

    def to_dict(self) -> dict[str, str]:
        """Return only non-empty IDs."""
        d: dict[str, str] = {"trace_id": self.trace_id}
        if self.job_id:
            d["job_id"] = self.job_id
        if self.report_id:
            d["report_id"] = self.report_id
        if self.expert_id:
            d["expert_id"] = self.expert_id
        if self.session_id:
            d["session_id"] = self.session_id
        if self.workflow_id:
            d["workflow_id"] = self.workflow_id
        return d


def build_artifact_ids(**kwargs: str) -> dict[str, str]:
    """Build an artifact_ids dict from keyword arguments.

    Always includes trace_id. Pass any additional IDs as kwargs.
    Missing or empty values are excluded.

    Usage::

        response["artifact_ids"] = build_artifact_ids(
            trace_id=trace_id,
            job_id=job_id,
            session_id=session_id,
        )
    """
    if "trace_id" not in kwargs or not kwargs["trace_id"]:
        kwargs["trace_id"] = _new_trace_id()
    return {k: v for k, v in kwargs.items() if v}


def inject_artifact_ids(response: dict[str, Any], **kwargs: str) -> dict[str, Any]:
    """Add artifact_ids to a response dict in-place and return it.

    Convenience wrapper around ``build_artifact_ids``.
    """
    response["artifact_ids"] = build_artifact_ids(**kwargs)
    return response


def ensure_trace_id(response: dict[str, Any]) -> dict[str, Any]:
    """Guarantee trace_id is present in the response artifact_ids.

    If ``artifact_ids`` already exists and contains a ``trace_id``, the
    response is returned unchanged. Otherwise a UUID-based trace_id is
    generated and injected.

    Args:
        response: MCP tool response dict (mutated in-place).

    Returns:
        The same response dict with trace_id guaranteed present.
    """
    artifact_ids = response.get("artifact_ids")
    if artifact_ids is None:
        response["artifact_ids"] = {"trace_id": _new_trace_id()}
    elif not artifact_ids.get("trace_id"):
        artifact_ids["trace_id"] = _new_trace_id()
    return response


def inject_referenced_artifact(
    response: dict[str, Any],
    referenced_id: str,
    status: str = "found",
) -> dict[str, Any]:
    """Add a referenced artifact ID to the response metadata.

    Used when a tool response references an artifact produced by another
    tool (e.g., a report referencing a research job).

    Args:
        response: MCP tool response dict (mutated in-place).
        referenced_id: The artifact ID being referenced.
        status: Status of the referenced artifact ("found" or "not_found").

    Returns:
        The same response dict with referenced artifact metadata added.
    """
    metadata = response.setdefault("metadata", {})
    referenced = metadata.setdefault("referenced_artifacts", [])
    referenced.append({"artifact_id": referenced_id, "status": status})
    return response
