"""Hierarchical task decomposition for complex expert queries.

Breaks a query into parallel/sequential subtasks, executes them with
visible progress, and synthesises results.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from deepr.experts.constants import MAX_PLAN_CONCURRENCY, UTILITY_MODEL

if TYPE_CHECKING:
    from deepr.experts.chat import ExpertChatSession

logger = logging.getLogger(__name__)


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class PlanStep:
    """A single step in a task plan."""

    id: int
    title: str
    query: str
    depends_on: list[int] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: str = ""
    error: str = ""


@dataclass
class TaskPlan:
    """A plan with ordered steps."""

    query: str
    steps: list[PlanStep] = field(default_factory=list)
    synthesis: str = ""
    total_cost: float = 0.0


class TaskPlanner:
    """Decompose complex queries into executable sub-tasks."""

    MAX_STEPS = 10

    def __init__(self, session: ExpertChatSession, agent_identity: Any = None):
        self.session = session
        self.agent_identity = agent_identity
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def decompose(self, query: str) -> dict:
        """Break a query into numbered steps with dependencies.

        Returns a dict suitable for display and execution.
        """
        prompt = (
            f"Break this complex question into 3-6 research subtasks.\n"
            f"Question: {query}\n\n"
            f"Return ONLY valid JSON with this structure:\n"
            f'{{"steps": [{{"id": 1, "title": "...", "query": "...", "depends_on": []}}]}}\n'
            f"Rules:\n"
            f"- Each step should be a focused sub-question\n"
            f"- Use depends_on to mark sequential dependencies ([] for independent steps)\n"
            f"- Independent steps will run in parallel\n"
            f"- Maximum 6 steps\n"
        )

        # Cost-safety gate. A task plan that proceeds spawns N step
        # send_message calls - each itself a research dispatch - so the
        # planner is a high-amplification cost point.
        try:
            from deepr.experts.cost_safety import get_cost_safety_manager

            _cost_safety = get_cost_safety_manager()
            _est = 0.02
            _allowed, _reason, _ = _cost_safety.check_operation(
                session_id="task_planner",
                operation_type="decompose",
                estimated_cost=_est,
                require_confirmation=False,
            )
            if not _allowed:
                logger.warning("Task decomposition blocked by cost-safety: %s", _reason)
                return {"display": f"Plan blocked by cost-safety: {_reason}", "steps": [], "query": query}
        except Exception:
            _cost_safety = None  # type: ignore[assignment]
            _est = 0.0

        try:
            result = await self.client.chat.completions.create(
                model=UTILITY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You decompose complex research questions into parallel subtasks. Return only JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            if _cost_safety is not None:
                try:
                    from deepr.experts.chat import _chat_token_cost as _tc

                    _actual = _tc(result.usage, UTILITY_MODEL) if result.usage else _est
                    _cost_safety.record_cost(
                        session_id="task_planner",
                        operation_type="decompose",
                        actual_cost=float(_actual),
                        provider="openai",
                        model=UTILITY_MODEL,
                        source="experts.task_planner.decompose",
                    )
                except Exception:
                    pass  # status callback failure must never abort plan step execution or tracking
            raw = (result.choices[0].message.content or "").strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(raw)
        except Exception as e:
            return {"display": f"Failed to create plan: {e}", "steps": [], "query": query}

        steps_data = data.get("steps", [])[: self.MAX_STEPS]

        steps = [
            PlanStep(
                id=s.get("id", i + 1),
                title=s.get("title", f"Step {i + 1}"),
                query=s.get("query", ""),
                depends_on=s.get("depends_on", []),
            )
            for i, s in enumerate(steps_data)
        ]

        # Build display
        lines = [f"Plan for: {query}", ""]
        for step in steps:
            deps = f" (after step {', '.join(map(str, step.depends_on))})" if step.depends_on else " (independent)"
            lines.append(f"  {step.id}. {step.title}{deps}")
        lines.append("")
        lines.append("Approve to execute, or modify the plan.")

        return {
            "display": "\n".join(lines),
            "steps": [
                {
                    "id": s.id,
                    "title": s.title,
                    "query": s.query,
                    "depends_on": s.depends_on,
                    "status": s.status.value,
                }
                for s in steps
            ],
            "query": query,
        }

    async def execute_plan(
        self,
        plan_data: dict,
        status_callback: Any = None,
    ) -> dict:
        """Execute a plan's steps, respecting dependencies.

        Independent steps run in parallel via asyncio.gather.
        """
        steps_raw = plan_data.get("steps", [])
        steps = {
            s["id"]: PlanStep(
                id=s["id"],
                title=s["title"],
                query=s["query"],
                depends_on=s.get("depends_on", []),
            )
            for s in steps_raw
        }

        completed: set[int] = set()
        # ExpertChatSession is not safe for concurrent mutation:
        # send_message appends to self.messages and updates cost_accumulated
        # / research_count without a lock. The dispatcher below fans out
        # _run_step coroutines on the same session object, so we serialise
        # the actual send through this lock. We lose the in-step
        # parallelism, but the dispatcher still resolves dependencies
        # topologically and chat history / cost totals stay consistent.
        session_lock = asyncio.Lock()

        async def _run_step(step: PlanStep) -> None:
            # Create child agent identity for cost/trace attribution
            step_identity = None
            if self.agent_identity is not None:
                from deepr.agents.contract import AgentRole

                step_identity = self.agent_identity.child(
                    role=AgentRole.WORKER,
                    name=f"plan-step-{step.id}",
                )

            step.status = StepStatus.RUNNING
            if status_callback:
                try:
                    status_callback(step.id, step.title, "running")
                except Exception:
                    pass  # status callback failure must never abort plan step execution or tracking

            cost_before = self.session.cost_accumulated
            try:
                async with session_lock:
                    response = await self.session.send_message(
                        step.query,
                        status_callback=lambda s: None,
                    )
                step.result = response
                step.status = StepStatus.DONE
            except Exception as e:
                step.error = str(e)
                step.status = StepStatus.FAILED
            finally:
                # Track per-step cost delta
                step_cost = self.session.cost_accumulated - cost_before
                if step_identity is not None:
                    logger.debug(
                        "Plan step %d (%s) cost: $%.4f agent_id=%s trace_id=%s",
                        step.id,
                        step.title,
                        step_cost,
                        step_identity.agent_id,
                        step_identity.trace_id,
                    )
                completed.add(step.id)
                if status_callback:
                    try:
                        status_callback(step.id, step.title, step.status.value)
                    except Exception:
                        pass  # status callback failure must never abort plan step execution or tracking

        # Topological execution with bounded concurrency
        from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher

        dispatcher = AsyncTaskDispatcher(max_concurrent=MAX_PLAN_CONCURRENCY)

        # Build dispatcher tasks with dependency mapping
        dispatch_tasks = []
        dep_map: dict[str, list[str]] = {}
        for s in steps.values():
            task_id = str(s.id)
            dispatch_tasks.append(
                {
                    "id": task_id,
                    "coro": _run_step(s),
                }
            )
            dep_map[task_id] = [str(d) for d in s.depends_on]

        await dispatcher.dispatch_with_dependencies(
            tasks=dispatch_tasks,
            dependencies=dep_map,
        )

        # Synthesise
        parts = []
        for s in steps.values():
            if s.status == StepStatus.DONE:
                parts.append(f"**{s.title}**: {s.result[:500]}")
            elif s.status == StepStatus.FAILED:
                parts.append(f"**{s.title}**: Failed - {s.error}")

        synthesis = await self._synthesise(plan_data.get("query", ""), parts)

        return {
            "steps": [
                {
                    "id": s.id,
                    "title": s.title,
                    "status": s.status.value,
                    "result": s.result[:500] if s.result else s.error,
                }
                for s in steps.values()
            ],
            "synthesis": synthesis,
            "total_cost": self.session.cost_accumulated,
        }

    async def _synthesise(self, query: str, step_results: list[str]) -> str:
        """Combine step results into a final answer."""
        if not step_results:
            return "No steps completed successfully."

        # Cost-safety gate for plan synthesis.
        try:
            from deepr.experts.cost_safety import get_cost_safety_manager

            _cost_safety = get_cost_safety_manager()
            _est = 0.02
            _allowed, _reason, _ = _cost_safety.check_operation(
                session_id="task_planner",
                operation_type="synthesise",
                estimated_cost=_est,
                require_confirmation=False,
            )
            if not _allowed:
                logger.warning("Plan synthesis blocked by cost-safety: %s", _reason)
                # Return raw concatenation as fallback so the user still
                # sees per-step results even when the synth call is gated.
                return "\n\n".join(step_results)
        except Exception:
            _cost_safety = None  # type: ignore[assignment]
            _est = 0.0

        try:
            result = await self.client.chat.completions.create(
                model=UTILITY_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "Synthesise research step results into a coherent final answer. Be concise.",
                    },
                    {
                        "role": "user",
                        "content": (f"Query: {query}\n\nStep results:\n" + "\n---\n".join(step_results))[:3000],
                    },
                ],
                temperature=0.3,
                max_tokens=600,
            )
            if _cost_safety is not None:
                try:
                    from deepr.experts.chat import _chat_token_cost as _tc

                    _actual = _tc(result.usage, UTILITY_MODEL) if result.usage else _est
                    _cost_safety.record_cost(
                        session_id="task_planner",
                        operation_type="synthesise",
                        actual_cost=float(_actual),
                        provider="openai",
                        model=UTILITY_MODEL,
                        source="experts.task_planner.synthesise",
                    )
                except Exception:
                    pass  # cost recording must never break task planner synthesise step
            return result.choices[0].message.content or "Synthesis unavailable."
        except Exception as e:
            return f"Synthesis failed: {e}"
