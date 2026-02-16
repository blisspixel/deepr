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

    def __init__(self, session: ExpertChatSession):
        self.session = session
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

        try:
            result = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You decompose complex research questions into parallel subtasks. Return only JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            raw = (result.choices[0].message.content or "").strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(raw)
        except Exception as e:
            return {"display": f"Failed to create plan: {e}", "steps": [], "query": query}

        steps_data = data.get("steps", [])[:self.MAX_STEPS]

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

        async def _run_step(step: PlanStep) -> None:
            step.status = StepStatus.RUNNING
            if status_callback:
                try:
                    status_callback(step.id, step.title, "running")
                except Exception:
                    pass
            try:
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
                completed.add(step.id)
                if status_callback:
                    try:
                        status_callback(step.id, step.title, step.status.value)
                    except Exception:
                        pass

        # Topological execution
        max_iterations = len(steps) + 1
        iteration = 0
        while len(completed) < len(steps) and iteration < max_iterations:
            iteration += 1
            ready = [
                s for s in steps.values()
                if s.id not in completed
                and s.status == StepStatus.PENDING
                and all(d in completed for d in s.depends_on)
            ]
            if not ready:
                break
            await asyncio.gather(*[_run_step(s) for s in ready])

        # Synthesise
        parts = []
        for s in steps.values():
            if s.status == StepStatus.DONE:
                parts.append(f"**{s.title}**: {s.result[:500]}")
            elif s.status == StepStatus.FAILED:
                parts.append(f"**{s.title}**: Failed — {s.error}")

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

        try:
            result = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Synthesise research step results into a coherent final answer. Be concise.",
                    },
                    {
                        "role": "user",
                        "content": f"Query: {query}\n\nStep results:\n" + "\n---\n".join(step_results[:3000]),
                    },
                ],
                temperature=0.3,
                max_tokens=600,
            )
            return result.choices[0].message.content or "Synthesis unavailable."
        except Exception as e:
            return f"Synthesis failed: {e}"
