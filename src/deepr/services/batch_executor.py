"""
Batch Executor Service

Orchestrates multi-phase research campaigns with context chaining.

Executes research tasks in phases:
- Phase 1: Foundation tasks (parallel)
- Phase 2: Analysis tasks (sequential, with Phase 1 context)
- Phase 3+: Subsequent phases (with accumulated context)
- Final: Synthesis (integrates all findings)

Includes entropy-based stopping criteria and information gain tracking
to detect diminishing returns and optimize research efficiency.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from deepr.observability.information_gain import InformationGainTracker
from deepr.observability.stopping_criteria import (
    EntropyStoppingCriteria,
    Finding,
    PhaseContext,
    StoppingDecision,
)
from deepr.providers.base import DeepResearchProvider
from deepr.queue.base import JobStatus, QueueBackend, ResearchJob
from deepr.services.context_builder import ContextBuilder
from deepr.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class BatchExecutor:
    """Executes multi-phase research campaigns with context chaining.

    Includes entropy-based stopping criteria and information gain tracking
    to detect diminishing returns and optimize research efficiency.
    """

    def __init__(
        self,
        queue: QueueBackend,
        provider: DeepResearchProvider,
        storage: StorageBackend,
        context_builder: ContextBuilder,
        entropy_threshold: float | None = None,
    ):
        """Initialize batch executor with required services.

        Args:
            queue: Queue backend for job management
            provider: Research provider for API calls
            storage: Storage backend for reports
            context_builder: Context builder for phase chaining
            entropy_threshold: Optional override for entropy stopping threshold
        """
        self.queue = queue
        self.provider = provider
        self.storage = storage
        self.context_builder = context_builder

        # Initialize stopping criteria and information gain tracking
        self.stopping_criteria = EntropyStoppingCriteria(entropy_threshold=entropy_threshold)
        self.info_gain_tracker = InformationGainTracker()

    async def execute_campaign(
        self,
        tasks: list[dict],
        campaign_id: str,
        enable_stopping_criteria: bool = True,
    ) -> dict:
        """
        Execute a complete research campaign.

        Args:
            tasks: List of task definitions with phase/dependency info
            campaign_id: Unique identifier for this campaign
            enable_stopping_criteria: Whether to use entropy-based stopping

        Returns:
            Campaign results with all task outputs
        """
        from deepr.services.research_bounds import require_research_parent_budget_accounting

        require_research_parent_budget_accounting("BatchExecutor campaign")
        # Reset trackers for new campaign
        self.stopping_criteria.reset()
        self.info_gain_tracker.reset()

        # Group tasks by phase
        phases = self._group_by_phase(tasks)

        # Track completed tasks and results
        completed_tasks = {}
        campaign_results = {
            "campaign_id": campaign_id,
            "started_at": datetime.now(UTC).isoformat(),
            "phases": {},
            "tasks": {},
            "quality_metrics": {},
        }

        # Track prior entropy for information gain
        prior_entropy: float | None = None

        # Execute each phase sequentially
        for phase_num in sorted(phases.keys()):
            phase_tasks = phases[phase_num]
            logger.info("Executing Phase %d (%d tasks)...", phase_num, len(phase_tasks))

            # Execute all tasks in phase (in parallel)
            phase_results, stopping_decision = await self._execute_phase(
                phase_tasks=phase_tasks,
                phase_num=phase_num,
                completed_tasks=completed_tasks,
                campaign_id=campaign_id,
                prior_entropy=prior_entropy,
            )

            # Store results
            completed_results = [result for result in phase_results.values() if result.get("status") == "completed"]
            campaign_results["phases"][phase_num] = {
                "task_count": len(phase_tasks),
                "completed": len(completed_results),
                "entropy": stopping_decision.entropy if stopping_decision else None,
                "information_gain": stopping_decision.information_gain if stopping_decision else None,
            }

            for task_id, result in phase_results.items():
                if result.get("status") == "completed":
                    completed_tasks[task_id] = result
                campaign_results["tasks"][task_id] = {
                    "title": result["title"],
                    "phase": phase_num,
                    "job_id": result["job_id"],
                    "status": result["status"],
                    "result": result.get("result", ""),
                    "cost": result.get("cost", 0.0),
                }

            if any(result.get("status") == "pending" for result in phase_results.values()):
                campaign_results["status"] = "pending"
                logger.warning("Campaign %s paused with pending provider work in phase %s", campaign_id, phase_num)
                break

            # Update prior entropy for next phase
            if stopping_decision:
                prior_entropy = stopping_decision.entropy

            # Check stopping criteria
            if enable_stopping_criteria and stopping_decision and stopping_decision.should_stop:
                logger.info(
                    "Stopping campaign early: %s (entropy=%.3f, gain=%.3f)",
                    stopping_decision.reason,
                    stopping_decision.entropy,
                    stopping_decision.information_gain,
                )
                campaign_results["early_stop"] = {
                    "phase": phase_num,
                    "reason": stopping_decision.reason,
                    "entropy": stopping_decision.entropy,
                    "information_gain": stopping_decision.information_gain,
                    "pivot_suggestion": stopping_decision.pivot_suggestion,
                }
                break

        # Save campaign results
        campaign_results.setdefault("status", "completed")
        campaign_results["completed_at"] = datetime.now(UTC).isoformat()
        campaign_results["total_cost"] = sum(t.get("cost", 0.0) for t in campaign_results["tasks"].values())

        # Add quality metrics summary
        campaign_results["quality_metrics"] = {
            "info_gain_summary": self.info_gain_tracker.get_summary(),
            "final_entropy": prior_entropy,
        }

        await self._save_campaign_results(campaign_id, campaign_results)

        return campaign_results

    async def _execute_phase(
        self,
        phase_tasks: list[dict],
        phase_num: int,
        completed_tasks: dict[int, dict],
        campaign_id: str,
        prior_entropy: float | None = None,
    ) -> tuple[dict[int, dict], StoppingDecision | None]:
        """
        Execute all tasks in a phase.

        Args:
            phase_tasks: Tasks to execute
            phase_num: Phase number
            completed_tasks: Previously completed tasks
            campaign_id: Campaign identifier
            prior_entropy: Entropy from previous phase for information gain

        Returns:
            Tuple of (Dict mapping task_id to results, StoppingDecision)
        """
        # Submit all tasks in phase
        job_ids = {}
        for task in phase_tasks:
            task_id = task["id"]

            # Build context from dependencies
            context = await self.context_builder.build_phase_context(
                task=task,
                completed_tasks=completed_tasks,
            )

            # Construct full prompt with context
            if context:
                full_prompt = f"{context}\n{task['prompt']}"
            else:
                full_prompt = task["prompt"]

            # Submit to queue
            job_id = await self._submit_task(
                prompt=full_prompt,
                task_id=task_id,
                campaign_id=campaign_id,
                model=task.get("model", "o4-mini-deep-research"),
                metadata={
                    "phase": phase_num,
                    "title": task["title"],
                    "depends_on": task.get("depends_on", []),
                },
            )

            job_ids[task_id] = job_id

        # Wait for all tasks to complete
        results = await self._wait_for_completion(job_ids, phase_tasks)

        # Extract findings from results for quality metrics
        findings = self._extract_findings(results, phase_num)

        # Record information gain
        finding_texts = [f.text for f in findings]
        self.info_gain_tracker.record_phase_findings(
            phase=phase_num,
            findings=finding_texts,
            prior_context={"known_facts": [r.get("result", "") for r in completed_tasks.values()]},
        )

        # Build phase context for stopping criteria
        original_query = phase_tasks[0].get("prompt", "") if phase_tasks else ""
        phase_context = PhaseContext(
            phase_num=phase_num,
            original_query=original_query,
            current_focus=original_query,
            total_findings=len(findings),
            prior_entropy=prior_entropy,
            iteration_count=phase_num,
        )

        # Evaluate stopping criteria
        stopping_decision = self.stopping_criteria.evaluate(findings, phase_context)

        logger.info(
            "Phase %d metrics: entropy=%.3f, info_gain=%.3f, findings=%d, should_stop=%s",
            phase_num,
            stopping_decision.entropy,
            stopping_decision.information_gain,
            len(findings),
            stopping_decision.should_stop,
        )

        return results, stopping_decision

    def _extract_findings(
        self,
        results: dict[int, dict],
        phase_num: int,
    ) -> list[Finding]:
        """Extract findings from task results.

        Args:
            results: Task results dictionary
            phase_num: Current phase number

        Returns:
            List of Finding objects
        """
        findings = []

        for task_id, result in results.items():
            result_text = result.get("result", "")
            if not result_text:
                continue

            # Split long results into paragraph-level findings
            paragraphs = [p.strip() for p in result_text.split("\n\n") if p.strip()]

            for para in paragraphs[:20]:  # Limit to avoid huge finding lists
                if len(para) > 50:  # Skip very short paragraphs
                    findings.append(
                        Finding(
                            text=para,
                            phase=phase_num,
                            confidence=0.7,  # Default confidence
                            source=result.get("title", f"task_{task_id}"),
                        )
                    )

        return findings

    async def _submit_task(
        self,
        prompt: str,
        task_id: int,
        campaign_id: str,
        metadata: dict,
        model: str = "o4-mini-deep-research",
    ) -> str:
        """Submit a single task to the queue."""

        from deepr.experts.research_cost_gate import reserve_configured_research_cost
        from deepr.providers.base import ResearchRequest, ToolConfig
        from deepr.services.research_cost_reconciliation import reconcile_research_cost_reservations
        from deepr.services.research_submission import dispatch_reserved_research

        # Generate unique job ID for this task
        job_id = f"{campaign_id}-task-{task_id}"

        provider_name = getattr(self.provider, "name", "openai")
        if not isinstance(provider_name, str) or not provider_name:
            provider_name = "openai"
        await reconcile_research_cost_reservations(
            self.queue,
            default_provider=provider_name,
        )
        _, reservation = reserve_configured_research_cost(
            job_id=job_id,
            provider=provider_name,
            prompt=prompt,
            model=model,
            enable_web_search=True,
        )

        # Create job in queue
        job = ResearchJob(
            id=job_id,
            prompt=prompt,
            model=model,
            provider=provider_name,
            enable_web_search=True,
            metadata={
                **metadata,
                "campaign_id": campaign_id,
                "task_id": task_id,
                **reservation.metadata(),
            },
        )

        # Submit to provider
        request = ResearchRequest(
            prompt=prompt,
            model=model,
            system_message="You are a research assistant conducting comprehensive research. Provide detailed, citation-backed analysis.",
            tools=[ToolConfig(type="web_search_preview")],
            background=True,
        )

        await dispatch_reserved_research(
            queue=self.queue,
            provider=self.provider,
            job=job,
            request=request,
            reservation=reservation,
        )

        return job.id

    async def _wait_for_completion(
        self,
        job_ids: dict[int, str],
        tasks: list[dict],
        max_wait_seconds: float = 3600.0,
    ) -> dict[int, dict]:
        """
        Wait for all jobs to complete and retrieve results.

        Args:
            job_ids: Dict mapping task_id to job_id
            tasks: Task definitions
            max_wait_seconds: Hard ceiling on total wall-clock time
                (default: 1 hour). Without this the loop could run
                forever if a provider hung or the queue dropped the
                completion event - campaigns would hold coroutines and
                resources indefinitely.

        Returns:
            Dict mapping task_id to results
        """
        import time as _time

        results = {}
        pending = set(job_ids.keys())
        from deepr.worker.poller import JobPoller

        poller = JobPoller(queue=self.queue, provider=self.provider, storage=self.storage)

        # Create lookup for task titles
        task_titles = {t["id"]: t["title"] for t in tasks}

        wait_started = _time.monotonic()
        while pending:
            if _time.monotonic() - wait_started > max_wait_seconds:
                timeout_results = await self._handle_wait_timeout(
                    pending=pending,
                    job_ids=job_ids,
                    task_titles=task_titles,
                    max_wait_seconds=max_wait_seconds,
                )
                results.update(timeout_results)
                logger.warning(
                    "BatchExecutor._wait_for_completion timed out after %ss with %d jobs still pending",
                    max_wait_seconds,
                    len(pending),
                )
                return results
            await asyncio.sleep(5)  # Poll every 5 seconds

            # Check status of pending jobs
            for task_id in list(pending):
                job_id = job_ids[task_id]
                job = await self.queue.get_job(job_id)
                if job is None:
                    continue
                if job.status == JobStatus.PROCESSING and job.provider_job_id:
                    await poller.check_job_status(job)
                    job = await self.queue.get_job(job_id)
                    if job is None:
                        continue

                if job.status == JobStatus.FAILED:
                    results[task_id] = {
                        "title": task_titles[task_id],
                        "job_id": job_id,
                        "status": "failed",
                        "result": "",
                        "cost": 0.0,
                    }

                    pending.remove(task_id)
                    logger.warning("Task %s: %s (FAILED)", task_id, task_titles[task_id])

                elif job.status == JobStatus.COMPLETED:
                    # Retrieve result - use stored filename from job.report_paths
                    try:
                        report_filename = (
                            job.report_paths.get("markdown", "report.md") if job.report_paths else "report.md"
                        )
                        result_data = await self.storage.get_report(
                            job_id=job_id,
                            filename=report_filename,
                        )

                        results[task_id] = {
                            "title": task_titles[task_id],
                            "job_id": job_id,
                            "status": "completed",
                            "result": result_data.decode("utf-8"),
                            "cost": job.cost,
                            "tokens_used": job.tokens_used,
                        }

                        pending.remove(task_id)
                        logger.info("Task %s: %s ($%.2f)", task_id, task_titles[task_id], job.cost)
                    except Exception as e:
                        # Handle case where job is marked complete but report is missing
                        results[task_id] = {
                            "title": task_titles[task_id],
                            "job_id": job_id,
                            "status": "failed",
                            "result": f"Error retrieving report: {e}",
                            "cost": job.cost if hasattr(job, "cost") else 0.0,
                        }

                        pending.remove(task_id)
                        logger.warning("Task %s: %s (Report error: %s)", task_id, task_titles[task_id], e)

        return results

    async def _handle_wait_timeout(
        self,
        *,
        pending: set[int],
        job_ids: dict[int, str],
        task_titles: dict[int, str],
        max_wait_seconds: float,
    ) -> dict[int, dict]:
        """Attempt cancellation without inventing terminal state when it fails."""
        from deepr.services.research_cancellation import cancel_reserved_research

        results: dict[int, dict] = {}
        provider_name = getattr(self.provider, "name", "openai")
        for task_id in list(pending):
            job = await self.queue.get_job(job_ids[task_id])
            cancelled = False
            if job is not None:
                outcome = await cancel_reserved_research(
                    queue=self.queue,
                    provider=self.provider,
                    job=job,
                    default_provider=provider_name,
                    source="services.batch_executor.timeout",
                )
                cancelled = outcome.queue_cancelled and outcome.cost_closed
            if cancelled:
                error = f"Batch wait timed out and provider cancellation was confirmed after {max_wait_seconds:.0f}s"
            else:
                error = f"Batch wait timed out after {max_wait_seconds:.0f}s; durable tracking remains active"
            results[task_id] = {
                "title": task_titles.get(task_id, ""),
                "job_id": job_ids[task_id],
                "status": "cancelled" if cancelled else "pending",
                "result": "",
                "cost": 0.0,
                "error": error,
            }
        return results

    def _group_by_phase(self, tasks: list[dict]) -> dict[int, list[dict]]:
        """Group tasks by phase number."""
        phases = {}
        for task in tasks:
            phase = task.get("phase", 1)
            if phase not in phases:
                phases[phase] = []
            phases[phase].append(task)
        return phases

    async def _save_campaign_results(
        self,
        campaign_id: str,
        results: dict,
    ):
        """Save campaign results to storage."""
        # Extract campaign prompt/goal if available (from first task)
        campaign_prompt = "Multi-phase research campaign"
        if results.get("tasks"):
            first_task = next(iter(results["tasks"].values()))
            campaign_prompt = first_task.get("title", campaign_prompt)

        # Save as JSON
        results_json = json.dumps(results, indent=2)
        await self.storage.save_report(
            job_id=campaign_id,
            filename="campaign_results.json",
            content=results_json.encode("utf-8"),
            content_type="application/json",
            metadata={
                "prompt": campaign_prompt,
                "type": "campaign",
                "task_count": len(results.get("tasks", {})),
                "total_cost": results.get("total_cost", 0.0),
            },
        )

        # Also create a summary report
        summary = self._generate_campaign_summary(results)
        await self.storage.save_report(
            job_id=campaign_id,
            filename="campaign_summary.md",
            content=summary.encode("utf-8"),
            content_type="text/markdown",
        )

    def _generate_campaign_summary(self, results: dict) -> str:
        """Generate human-readable campaign summary."""
        lines = [
            f"# Campaign Results: {results['campaign_id']}",
            "",
            f"Started: {results['started_at']}",
            f"Completed: {results['completed_at']}",
            f"Total Cost: ${results['total_cost']:.2f}",
            "",
            "## Phases",
            "",
        ]

        for phase_num in sorted(results["phases"].keys()):
            phase = results["phases"][phase_num]
            lines.append(f"### Phase {phase_num}")
            lines.append(f"- Tasks: {phase['task_count']}")
            lines.append(f"- Completed: {phase['completed']}")
            lines.append("")

        lines.append("## Tasks")
        lines.append("")

        for task_id in sorted(results["tasks"].keys(), key=lambda x: int(x)):
            task = results["tasks"][task_id]
            lines.append(f"### Task {task_id}: {task['title']}")
            lines.append(f"- Phase: {task['phase']}")
            lines.append(f"- Status: {task['status']}")
            lines.append(f"- Cost: ${task['cost']:.2f}")
            lines.append(f"- Job ID: {task['job_id']}")
            lines.append("")

        return "\n".join(lines)
