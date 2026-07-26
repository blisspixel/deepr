"""Poll-time persistence for learner research jobs.

A 30-job, $37.79 learning campaign once settled all its spend at poll time
while report persistence waited for a deferred, best-effort integration pass;
a crash and empty provider re-fetches later, zero artifacts survived. These
helpers run at poll time so the paid artifact is on disk BEFORE spend is
recorded or the queue row flips COMPLETED, and so the queue row always
carries the report path (it used to be hardcoded to an empty dict).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from deepr.experts.profile import ExpertStore

logger = logging.getLogger(__name__)


def persist_completed_report(
    *,
    report_generator: Any,
    expert_name: str,
    provider_job_id: str,
    response: Any,
    log: Callable[[str], None],
) -> str | None:
    """Write a completed job's report to the expert's documents dir.

    Returns the path, or None when no content could be persisted (the caller
    marks the job FAILED instead of COMPLETED so the loss is loud).
    """
    try:
        raw_text = report_generator.extract_text_from_response(response)
        if not raw_text:
            log("       [ERROR] Completed at provider but no extractable content")
            return None
        docs_dir = ExpertStore().get_documents_dir(expert_name)
        docs_dir.mkdir(parents=True, exist_ok=True)
        doc_path = docs_dir / f"research_{provider_job_id[:12]}.md"
        doc_path.write_text(raw_text, encoding="utf-8")
        return str(doc_path)
    except Exception as exc:
        log(f"       [ERROR] Could not persist paid report: {exc}")
        return None


async def sync_job_status_in_queue(
    *,
    queue_ids: dict[str, str],
    config: Any,
    provider_job_id: str,
    status: str,
    cost: float | None = None,
    report_path: str | None = None,
) -> None:
    """Mirror a learner job's terminal state into the local queue (best-effort).

    Results (report path and actual cost) land before the status flip, so a
    COMPLETED row always carries the artifact location.
    """
    local_id = queue_ids.get(provider_job_id)
    if not local_id:
        return
    try:
        from deepr.config import queue_db_path
        from deepr.queue import create_queue
        from deepr.queue.base import JobStatus

        db_path = queue_db_path()
        if isinstance(config, dict):
            db_path = config.get("queue_db_path", db_path) or db_path
        queue = create_queue("local", db_path=db_path)
        target = JobStatus.COMPLETED if status == "completed" else JobStatus.FAILED
        if target is JobStatus.COMPLETED and (report_path or cost is not None):
            await queue.update_results(
                local_id,
                report_paths={"markdown": report_path} if report_path else {},
                cost=cost,
            )
        await queue.update_status(local_id, target)
    except Exception as exc:
        logger.warning("Could not sync learner job %s status in local queue: %s", provider_job_id, exc)


def save_learning_progress(
    *,
    expert_name: str,
    completed_topics: list[str],
    failed_topics: list[str],
    remaining_topics: list[Any],
    total_cost: float,
    started_at: Any,
) -> None:
    """Save learning progress to the expert's data directory for resume."""
    import json
    from datetime import UTC, datetime

    progress_file = ExpertStore().get_knowledge_dir(expert_name) / "learning_progress.json"
    progress_file.parent.mkdir(parents=True, exist_ok=True)

    done = set(completed_topics) | set(failed_topics)
    remaining = [t for t in remaining_topics if t.title not in done]
    progress_data = {
        "expert_name": expert_name,
        "paused_at": datetime.now(UTC).isoformat(),
        "completed_topics": completed_topics,
        "failed_topics": failed_topics,
        "remaining_topics": [
            {
                "title": t.title,
                "research_prompt": t.research_prompt,
                "research_mode": t.research_mode,
                "research_type": t.research_type,
                "estimated_cost": t.estimated_cost,
                "estimated_minutes": t.estimated_minutes,
            }
            for t in remaining
        ],
        "total_cost_so_far": total_cost,
        "started_at": started_at.isoformat(),
        "reason": "daily_or_monthly_limit",
    }
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(progress_data, f, indent=2)


def load_learning_progress(expert_name: str) -> dict[str, Any] | None:
    """Load saved learning progress for resume, or None if absent."""
    import json

    progress_file = ExpertStore().get_knowledge_dir(expert_name) / "learning_progress.json"
    if not progress_file.exists():
        return None
    with open(progress_file, encoding="utf-8") as f:
        return json.load(f)


def clear_learning_progress(expert_name: str) -> None:
    """Clear saved learning progress after successful completion."""
    progress_file = ExpertStore().get_knowledge_dir(expert_name) / "learning_progress.json"
    if progress_file.exists():
        progress_file.unlink()


__all__ = [
    "clear_learning_progress",
    "load_learning_progress",
    "persist_completed_report",
    "save_learning_progress",
    "sync_job_status_in_queue",
]
