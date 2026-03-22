"""Deterministic agent orchestrator: planner -> parallel workers -> synthesizer.

Implements the canonical subagent execution pattern with budget isolation,
trace propagation, and bounded fan-out via AsyncTaskDispatcher.
"""

from __future__ import annotations

import logging

from deepr.agents.contract import (
    AgentBudget,
    AgentIdentity,
    AgentResult,
    AgentRole,
    AgentStatus,
    SubagentContract,
)
from deepr.experts.constants import MAX_PLAN_CONCURRENCY
from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Orchestrate a planner -> workers -> synthesizer pipeline.

    The planner agent receives the query and returns a JSON list of subtasks.
    Worker agents execute subtasks in parallel (bounded by MAX_PLAN_CONCURRENCY).
    The synthesizer agent combines all worker outputs into a final result.

    Budget is split: 10% planner, 70% workers (divided equally), 20% synthesizer.
    """

    PLANNER_BUDGET_FRACTION = 0.10
    WORKER_BUDGET_FRACTION = 0.70
    SYNTHESIZER_BUDGET_FRACTION = 0.20

    def __init__(
        self,
        planner: SubagentContract,
        workers: list[SubagentContract],
        synthesizer: SubagentContract,
    ):
        self.planner = planner
        self.workers = workers
        self.synthesizer = synthesizer

    async def run(
        self,
        query: str,
        budget: float = 10.0,
        trace_id: str = "",
    ) -> AgentResult:
        """Execute the full orchestration pipeline.

        Args:
            query: The user's query to process.
            budget: Total budget for the entire orchestration.
            trace_id: Shared trace ID for correlation.

        Returns:
            Final AgentResult with aggregated costs and all child artifacts.
        """
        root_identity = AgentIdentity(
            role=AgentRole.PLANNER,
            trace_id=trace_id or AgentIdentity().trace_id,
            name="orchestrator-root",
        )

        total_cost = 0.0
        all_artifacts: list[str] = []

        # --- Phase 1: Planning ---
        planner_budget = AgentBudget(max_cost=budget * self.PLANNER_BUDGET_FRACTION)
        planner_identity = root_identity.child(role=AgentRole.PLANNER, name="planner")

        try:
            plan_result = await self.planner.execute(query, planner_budget, planner_identity)
        except Exception as e:
            logger.error("Planner failed: %s", e)
            return AgentResult(
                agent_id=root_identity.agent_id,
                trace_id=root_identity.trace_id,
                output=f"Planning failed: {e}",
                status=AgentStatus.FAILED,
                metadata={"phase": "planning", "error": str(e)},
            )

        total_cost += plan_result.cost
        all_artifacts.extend(plan_result.artifact_ids)

        # Parse subtasks from planner output (expects newline-separated tasks)
        subtasks = [line.strip() for line in plan_result.output.strip().split("\n") if line.strip()]
        if not subtasks:
            subtasks = [query]  # Fallback: treat original query as single task

        # --- Phase 2: Workers (parallel, bounded) ---
        num_workers = min(len(subtasks), len(self.workers)) if self.workers else 0
        if num_workers == 0:
            worker_outputs: list[str] = [plan_result.output]
        else:
            worker_budget_each = (budget * self.WORKER_BUDGET_FRACTION) / num_workers
            dispatcher = AsyncTaskDispatcher(max_concurrent=MAX_PLAN_CONCURRENCY)

            async def _run_worker(idx: int, subtask: str) -> AgentResult:
                worker = self.workers[idx % len(self.workers)]
                worker_identity = root_identity.child(
                    role=AgentRole.WORKER,
                    name=f"worker-{idx}",
                )
                wb = AgentBudget(max_cost=worker_budget_each)
                return await worker.execute(subtask, wb, worker_identity)

            dispatch_tasks = [
                {"id": f"worker-{i}", "coro": _run_worker(i, subtasks[i])}
                for i in range(min(len(subtasks), num_workers))
            ]
            dispatch_result = await dispatcher.dispatch(dispatch_tasks)

            worker_outputs = []
            for task_id in sorted(dispatch_result.tasks):
                task = dispatch_result.tasks[task_id]
                if task.result is not None:
                    result: AgentResult = task.result
                    total_cost += result.cost
                    all_artifacts.extend(result.artifact_ids)
                    worker_outputs.append(result.output)

        # --- Phase 3: Synthesis ---
        synth_input = f"Query: {query}\n\nResults:\n" + "\n---\n".join(worker_outputs)
        synth_budget = AgentBudget(max_cost=budget * self.SYNTHESIZER_BUDGET_FRACTION)
        synth_identity = root_identity.child(role=AgentRole.SYNTHESIZER, name="synthesizer")

        try:
            synth_result = await self.synthesizer.execute(synth_input, synth_budget, synth_identity)
        except Exception as e:
            logger.error("Synthesizer failed: %s", e)
            synth_result = AgentResult(
                agent_id=synth_identity.agent_id,
                trace_id=synth_identity.trace_id,
                output="\n\n".join(worker_outputs),
                status=AgentStatus.FAILED,
                metadata={"phase": "synthesis", "error": str(e)},
            )

        total_cost += synth_result.cost
        all_artifacts.extend(synth_result.artifact_ids)

        return AgentResult(
            agent_id=root_identity.agent_id,
            trace_id=root_identity.trace_id,
            output=synth_result.output,
            artifact_ids=all_artifacts,
            cost=round(total_cost, 6),
            status=synth_result.status,
            metadata={
                "subtask_count": len(subtasks),
                "worker_count": num_workers,
                "phases_completed": ["planning", "workers", "synthesis"],
            },
        )
