"""Small filesystem, identifier, and prompt helpers for research commands."""

from __future__ import annotations

import os
from typing import Any


def ensure_parent_dir(path: str) -> None:
    """Create the parent directory for a configured local path."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


async def resolve_job_id(queue: Any, maybe_prefix: str) -> str | None:
    """Resolve a full job ID or an unambiguous prefix from the queue."""
    if len(maybe_prefix) >= 32:
        job = await queue.get_job(maybe_prefix)
        return str(job.id) if job else None
    jobs = await queue.list_jobs(limit=500)
    matches = [str(job.id) for job in jobs if str(job.id).startswith(maybe_prefix)]
    return matches[0] if len(matches) == 1 else None


def build_research_prompt(prompt: str, context_content: str | None) -> str:
    """Build the exact provider prompt used for estimation and submission."""
    if not context_content:
        return prompt
    return (
        "## Prior Research Context\n\n"
        "The following prior research may be relevant. Use it as background "
        "but verify and update any findings:\n\n"
        f"---\n{context_content}\n---\n\n"
        f"## New Research Query\n\n{prompt}"
    )


__all__ = ["build_research_prompt", "ensure_parent_dir", "resolve_job_id"]
