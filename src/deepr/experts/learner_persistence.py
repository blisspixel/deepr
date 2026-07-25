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


__all__ = ["persist_completed_report", "sync_job_status_in_queue"]
