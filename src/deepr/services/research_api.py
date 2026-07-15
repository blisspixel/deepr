"""Simple API wrapper for submitting and managing research jobs."""

from datetime import UTC, datetime
from typing import Any

from deepr.config import AppConfig
from deepr.queue.base import JobStatus, ResearchJob
from deepr.queue.local_queue import SQLiteQueue


class ResearchAPI:
    """Simple API for submitting and managing research jobs."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.queue = SQLiteQueue()

    async def submit_research(
        self,
        prompt: str,
        mode: str = "focus",
        model: str | None = None,
        provider: str = "openai",
        vector_store_id: str | None = None,
        enable_web: bool = True,
        enable_code: bool = False,
        cost_limit: float | None = None,
    ) -> str:
        """Submit a research job to the queue.

        Args:
            prompt: Research prompt
            mode: Research mode (focus, docs, project, team)
            model: Optional model override
            provider: AI provider
            vector_store_id: Optional vector store for context
            enable_web: Enable web search
            enable_code: Enable code interpreter
            cost_limit: Optional cost limit

        Returns:
            Job ID
        """
        # Determine model based on mode if not specified
        if not model:
            if mode in {"team", "project"}:
                model = "o3-deep-research"
            elif mode == "docs":
                model = "o4-mini-deep-research"
            else:  # focus
                model = "o4-mini-deep-research"

        # Pre-flight budget check. Without this, any caller of
        # ResearchAPI.submit_research could enqueue an unbounded number
        # of paid deep-research jobs without ever touching the cost
        # safety layer that gates the MCP and Web surfaces.
        from deepr.experts.cost_safety import get_cost_safety_manager
        from deepr.providers.registry import get_cost_estimate as _get_cost_estimate

        try:
            estimated_cost = float(_get_cost_estimate(model))
        except Exception:
            estimated_cost = 2.0  # conservative default for deep-research

        # cost_limit is a CAP. Round-1 used ``min(estimated, cap)`` which
        # had the bug of presenting the lower of the two to the safety
        # check - so a $0.50 cap on a $2.00 model passed the gate even
        # though the real spend would exceed the cap. Reject upfront
        # when the model's estimate already exceeds the cap; never
        # downsize the value we hand to ``check_operation``.
        if cost_limit is not None and estimated_cost > float(cost_limit):
            raise RuntimeError(
                f"Model {model} estimated cost ${estimated_cost:.2f} exceeds caller cost_limit ${float(cost_limit):.2f}"
            )

        cost_safety = get_cost_safety_manager()
        session_id = f"research_api_{prompt[:32]}"
        allowed, deny_reason, _ = cost_safety.check_operation(
            session_id=session_id,
            operation_type="research_api_submit",
            estimated_cost=estimated_cost,
            require_confirmation=False,
        )
        if not allowed:
            raise RuntimeError(f"Research submission blocked by cost-safety: {deny_reason}")

        # Generate job ID
        import uuid

        job_id = f"research-{uuid.uuid4().hex[:6]}"

        # Create research job
        job = ResearchJob(
            id=job_id,
            prompt=prompt,
            model=model,
            provider=provider,
            status=JobStatus.QUEUED,
            submitted_at=datetime.now(UTC),
            documents=[vector_store_id] if vector_store_id else [],
            enable_web_search=enable_web,
            enable_code_interpreter=enable_code,
            cost_limit=cost_limit,
        )

        # Record estimated cost first so a ledger failure cannot leave a
        # queued paid job with no spend row (silent-money class). Enqueue
        # only after the admission ledger write succeeds.
        try:
            cost_safety.record_cost(
                session_id=session_id,
                operation_type="research_api_submit",
                actual_cost=estimated_cost,
                provider=provider,
                model=model,
                idempotency_key=f"research_api:{job_id}:submit",
                source="services.research_api.submit_research",
            )
        except Exception as exc:
            raise RuntimeError(f"Research submission blocked: cost ledger unavailable: {exc}") from exc

        await self.queue.enqueue(job)
        return job.id

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get status of a research job.

        Args:
            job_id: Job ID

        Returns:
            Dictionary with status information
        """
        job = await self.queue.get_job(job_id)

        if not job:
            raise ValueError(f"Job not found: {job_id}")

        return {
            "id": job.id,
            "status": job.status.value,
            "prompt": job.prompt,
            "model": job.model,
            "provider": job.provider,
            "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "cost": job.cost,
            "error": job.last_error,
        }

    async def get_job_result(self, job_id: str) -> dict[str, Any]:
        """Get result of a completed research job.

        Args:
            job_id: Job ID

        Returns:
            Dictionary with result information
        """
        job = await self.queue.get_job(job_id)

        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if job.status != JobStatus.COMPLETED:
            raise ValueError(f"Job not completed: {job.status.value}")

        return {
            "id": job.id,
            "status": job.status.value,
            "prompt": job.prompt,
            "report_paths": job.report_paths or {},
            "cost": job.cost,
            "tokens_used": job.tokens_used,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    async def cancel_job(self, job_id: str):
        """Cancel a research job.

        Args:
            job_id: Job ID
        """
        await self.queue.cancel(job_id)
