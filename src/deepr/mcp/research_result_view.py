"""Build bounded MCP views for completed provider research results.

This module owns only the derived response shape. Provider polling, canonical
cost settlement, durable job state, and lifecycle cleanup remain with the MCP
server and the research orchestrator.
"""

from __future__ import annotations

import os
from typing import Any

from deepr.mcp.artifacts import inject_artifact_ids

_DEFAULT_MAX_INLINE_CHARS = 8_000
_MAX_CONFIGURED_INLINE_CHARS = 1_000_000


def _max_inline_chars() -> int:
    try:
        configured = int(os.environ.get("DEEPR_MAX_INLINE_CHARS", str(_DEFAULT_MAX_INLINE_CHARS)))
    except (ValueError, TypeError):
        return _DEFAULT_MAX_INLINE_CHARS
    if configured <= 0:
        return _DEFAULT_MAX_INLINE_CHARS
    return min(configured, _MAX_CONFIGURED_INLINE_CHARS)


def _truncated_summary(report: str) -> str:
    summary = report[:2000]
    next_section = report.find("\n## ", 2000)
    if 0 < next_section < 3000:
        summary = report[:next_section]
    return summary + "\n\n... (truncated)"


def build_research_result_view(
    *,
    job_id: str,
    report: str,
    cost_final: float,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Return either an inline report or a bounded lazy-loading response."""
    report_uri = f"deepr://reports/{job_id}/final.md"
    raw_sources = metadata.get("sources", [])
    sources = raw_sources if isinstance(raw_sources, list) else []
    if len(report) > _max_inline_chars():
        return inject_artifact_ids(
            {
                "job_id": job_id,
                "status": "completed",
                "summary": _truncated_summary(report),
                "full_report_uri": report_uri,
                "report_length": len(report),
                "cost_final": cost_final,
                "metadata": metadata,
                "sources_count": len(sources),
                "hint": (
                    "Report truncated for context efficiency. "
                    "Use resources/read with the full_report_uri to get the complete report."
                ),
            },
            job_id=job_id,
            report_id=report_uri,
        )
    return inject_artifact_ids(
        {
            "job_id": job_id,
            "status": "completed",
            "markdown_report": report,
            "cost_final": cost_final,
            "metadata": metadata,
            "sources": sources,
            "resource_uri": report_uri,
        },
        job_id=job_id,
        report_id=report_uri,
    )
