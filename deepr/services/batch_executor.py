"""
Batch Executor Service

Orchestrates multi-phase research campaigns with context chaining.

Executes research tasks in phases:
- Phase 1: Foundation tasks (parallel)
- Phase 2: Analysis tasks (sequential, with Phase 1 context)
- Phase 3+: Subsequent phases (with accumulated context)
- Final: Synthesis (integrates all findings)
"""

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
import json

from deepr.queue.base import QueueBackend, JobStatus, ResearchJob
from deepr.providers.base import DeepResearchProvider
from deepr.storage.base import StorageBackend
from deepr.services.context_builder import ContextBuilder

logger = logging.getLogger(__name__)


class BatchExecutor:
    """Executes multi-phase research campaigns with context chaining."""

    def __init__(
        self,
        queue: QueueBackend,
        provider: DeepResearchProvider,
        storage: StorageBackend,
        context_builder: ContextBuilder,
    ):
        """Initialize batch executor with required services."""
        self.queue = queue
        self.provider = provider
        self.storage = storage
        self.context_builder = context_builder

    async def execute_campaign(
        self,
        tasks: List[Dict],
        campaign_id: str,
    ) -> Dict:
        """
        Execute a complete research campaign.

        Args:
            tasks: List of task definitions with phase/dependency info
            campaign_id: Unique identifier for this campaign

        Returns:
            Campaign results with all task outputs
        """
        # Group tasks by phase
        phases = self._group_by_phase(tasks)
        max_phase = max(phases.keys())

        # Track completed tasks and results
        completed_tasks = {}
        campaign_results = {
            "campaign_id": campaign_id,
            "started_at": datetime.now().isoformat(),
            "phases": {},
            "tasks": {},
        }

        # Execute each phase sequentially
        for phase_num in sorted(phases.keys()):
            phase_tasks = phases[phase_num]
            logger.info("Executing Phase %d (%d tasks)...", phase_num, len(phase_tasks))

            # Execute all tasks in phase (in parallel)
            phase_results = await self._execute_phase(
                phase_tasks=phase_tasks,
                phase_num=phase_num,
                completed_tasks=completed_tasks,
                campaign_id=campaign_id,
            )

            # Store results
            campaign_results["phases"][phase_num] = {
                "task_count": len(phase_tasks),
                "completed": len(phase_results),
            }

            for task_id, result in phase_results.items():
                completed_tasks[task_id] = result
                campaign_results["tasks"][task_id] = {
                    "title": result["title"],
                    "phase": phase_num,
                    "job_id": result["job_id"],
                    "status": result["status"],
                    "cost": result.get("cost", 0.0),
                }

        # Save campaign results
        campaign_results["completed_at"] = datetime.now().isoformat()
        campaign_results["total_cost"] = sum(
            t.get("cost", 0.0) for t in campaign_results["tasks"].values()
        )

        await self._save_campaign_results(campaign_id, campaign_results)

        return campaign_results

    async def _execute_phase(
        self,
        phase_tasks: List[Dict],
        phase_num: int,
        completed_tasks: Dict[int, Dict],
        campaign_id: str,
    ) -> Dict[int, Dict]:
        """
        Execute all tasks in a phase.

        Args:
            phase_tasks: Tasks to execute
            phase_num: Phase number
            completed_tasks: Previously completed tasks
            campaign_id: Campaign identifier

        Returns:
            Dict mapping task_id to results
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
                metadata={
                    "phase": phase_num,
                    "title": task["title"],
                    "depends_on": task.get("depends_on", []),
                },
            )

            job_ids[task_id] = job_id

        # Wait for all tasks to complete
        results = await self._wait_for_completion(job_ids, phase_tasks)

        return results

    async def _submit_task(
        self,
        prompt: str,
        task_id: int,
        campaign_id: str,
        metadata: Dict,
    ) -> str:
        """Submit a single task to the queue."""
        from deepr.providers.base import ResearchRequest, ToolConfig
        import uuid

        # Generate unique job ID for this task
        job_id = f"{campaign_id}-task-{task_id}"

        # Create job in queue
        job = ResearchJob(
            id=job_id,
            prompt=prompt,
            model="o4-mini-deep-research",
            enable_web_search=True,
            metadata={
                **metadata,
                "campaign_id": campaign_id,
                "task_id": task_id,
            },
        )

        await self.queue.enqueue(job)

        # Submit to provider
        request = ResearchRequest(
            prompt=prompt,
            model="o4-mini-deep-research",
            system_message="You are a research assistant conducting comprehensive research. Provide detailed, citation-backed analysis.",
            tools=[ToolConfig(type="web_search_preview")],
            background=True,
        )

        provider_job_id = await self.provider.submit_research(request)

        # Update queue with provider job ID
        await self.queue.update_status(
            job_id=job.id,
            status=JobStatus.PROCESSING,
            provider_job_id=provider_job_id,
        )

        return job.id

    async def _wait_for_completion(
        self,
        job_ids: Dict[int, str],
        tasks: List[Dict],
    ) -> Dict[int, Dict]:
        """
        Wait for all jobs to complete and retrieve results.

        Args:
            job_ids: Dict mapping task_id to job_id
            tasks: Task definitions

        Returns:
            Dict mapping task_id to results
        """
        results = {}
        pending = set(job_ids.keys())

        # Create lookup for task titles
        task_titles = {t["id"]: t["title"] for t in tasks}

        while pending:
            await asyncio.sleep(5)  # Poll every 5 seconds

            # Check status of pending jobs
            for task_id in list(pending):
                job_id = job_ids[task_id]
                job = await self.queue.get_job(job_id)

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
                    # Retrieve result
                    try:
                        result_data = await self.storage.get_report(
                            job_id=job_id,
                            filename="report.md",
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
                            "cost": job.cost if hasattr(job, 'cost') else 0.0,
                        }

                        pending.remove(task_id)
                        logger.warning("Task %s: %s (Report error: %s)", task_id, task_titles[task_id], e)

        return results

    def _group_by_phase(self, tasks: List[Dict]) -> Dict[int, List[Dict]]:
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
        results: Dict,
    ):
        """Save campaign results to storage."""
        # Extract campaign prompt/goal if available (from first task)
        campaign_prompt = "Multi-phase research campaign"
        if results.get("tasks"):
            first_task = list(results["tasks"].values())[0]
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
            }
        )

        # Also create a summary report
        summary = self._generate_campaign_summary(results)
        await self.storage.save_report(
            job_id=campaign_id,
            filename="campaign_summary.md",
            content=summary.encode("utf-8"),
            content_type="text/markdown",
        )

    def _generate_campaign_summary(self, results: Dict) -> str:
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
