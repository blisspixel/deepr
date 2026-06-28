"""Subagent runtime for bounded parallel fan-out orchestration.

Implements the planner -> workers -> synthesizer pattern with:
- Per-subagent budget caps
- Trace ID propagation
- Circuit breaker integration
- Cost ledger recording
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from deepr.agents.circuit_breaker import CircuitBreaker
from deepr.agents.contract import (
    AgentBudget,
    AgentIdentity,
    AgentResult,
    AgentRole,
    AgentStatus,
    SubagentContract,
)

_logger = logging.getLogger(__name__)


@dataclass
class FanOutConfig:
    """Configuration for bounded parallel fan-out."""

    max_concurrent: int = 16
    operation_budget: float = 10.0
    failure_rate_threshold: float = 0.5
    synthesis_reserve_fraction: float = 0.2


@dataclass
class FanOutResult:
    """Result of a fan-out operation."""

    results: list[AgentResult] = field(default_factory=list)
    total_cost: float = 0.0
    trace_id: str = ""
    circuit_breaker_tripped: bool = False
    trip_reason: str = ""


class SubagentRuntime:
    """Orchestrates planner -> workers -> synthesizer pattern.

    Dispatches queries to parallel workers using asyncio.Semaphore for
    max_concurrent enforcement, enforces per-subagent budget caps,
    propagates trace_id from planner_identity to all children, and
    records costs in the cost ledger.
    """

    def __init__(
        self,
        config: FanOutConfig,
        cost_ledger: Any | None = None,
    ) -> None:
        self.config = config
        self.cost_ledger = cost_ledger
        self.circuit_breaker = CircuitBreaker(config)

    async def fan_out(
        self,
        queries: list[str],
        agent_factory: Callable[[str, AgentBudget, AgentIdentity], Coroutine[Any, Any, AgentResult]],
        planner_identity: AgentIdentity,
        operation_budget: float | None = None,
    ) -> FanOutResult:
        """Dispatch queries to parallel workers with budget and failure guards.

        Args:
            queries: List of sub-queries to dispatch to workers.
            agent_factory: Async callable that creates and runs a worker agent.
                Signature: (query, budget, identity) -> AgentResult
            planner_identity: Identity of the planner agent (trace_id propagated).
            operation_budget: Override for operation budget (defaults to config).

        Returns:
            FanOutResult with all collected results and cost information.
        """
        budget = operation_budget if operation_budget is not None else self.config.operation_budget
        agent_count = len(queries)

        if agent_count == 0:
            return FanOutResult(
                results=[],
                total_cost=0.0,
                trace_id=planner_identity.trace_id,
            )

        # Calculate per-agent budget cap: (budget * (1 - synthesis_reserve)) / agent_count
        worker_budget_pool = budget * (1.0 - self.config.synthesis_reserve_fraction)
        per_agent_cap = worker_budget_pool / agent_count

        # Reset circuit breaker for this operation
        self.circuit_breaker.reset()
        self.circuit_breaker.state.total_dispatched = agent_count

        # Semaphore for max_concurrent enforcement
        semaphore = asyncio.Semaphore(self.config.max_concurrent)
        results: list[AgentResult] = []
        results_lock = asyncio.Lock()
        halt_event = asyncio.Event()

        async def _run_worker(query: str, index: int) -> None:
            """Run a single worker with semaphore and circuit breaker checks."""
            if halt_event.is_set():
                return

            async with semaphore:
                if halt_event.is_set():
                    return

                # Create child identity inheriting trace_id
                child_identity = planner_identity.child(
                    role=AgentRole.WORKER,
                    name=f"worker-{index}",
                )

                # Create per-agent budget
                agent_budget = AgentBudget(max_cost=per_agent_cap)

                try:
                    result = await agent_factory(query, agent_budget, child_identity)
                except Exception as exc:
                    result = AgentResult(
                        agent_id=child_identity.agent_id,
                        trace_id=child_identity.trace_id,
                        output=str(exc),
                        cost=agent_budget.cost_accumulated,
                        status=AgentStatus.FAILED,
                        metadata={"error": str(exc)},
                    )

                async with results_lock:
                    results.append(result)

                    # Record in cost ledger
                    self._record_cost(result)

                    # Update circuit breaker
                    if result.status in (AgentStatus.SUCCESS,):
                        self.circuit_breaker.record_completion(result)
                    else:
                        self.circuit_breaker.record_failure(result)

                    # Check if we should halt
                    should_halt, reason = self.circuit_breaker.should_halt()
                    if should_halt:
                        trace_ids = [r.trace_id for r in results]
                        self.circuit_breaker.trip(reason, trace_ids)
                        halt_event.set()

        # Dispatch all workers concurrently
        tasks = [asyncio.ensure_future(_run_worker(query, i)) for i, query in enumerate(queries)]
        await asyncio.gather(*tasks, return_exceptions=True)

        total_cost = sum(r.cost for r in results)

        return FanOutResult(
            results=results,
            total_cost=total_cost,
            trace_id=planner_identity.trace_id,
            circuit_breaker_tripped=self.circuit_breaker.state.tripped,
            trip_reason=self.circuit_breaker.state.trip_reason,
        )

    async def synthesize(
        self,
        results: list[AgentResult],
        synthesizer: SubagentContract,
        planner_identity: AgentIdentity,
        synthesis_budget: float,
    ) -> AgentResult:
        """Run synthesizer with worker results and their metadata.

        Args:
            results: List of worker results to synthesize.
            synthesizer: The synthesizer agent contract.
            planner_identity: Identity of the planner (trace_id propagated).
            synthesis_budget: Budget allocated for synthesis.

        Returns:
            AgentResult from the synthesizer.
        """
        # Create synthesizer identity inheriting trace_id
        synth_identity = planner_identity.child(
            role=AgentRole.SYNTHESIZER,
            name="synthesizer",
        )

        # Build synthesis query from worker results
        worker_summaries = []
        for r in results:
            worker_summaries.append(
                f"[Agent {r.agent_id} | status={r.status.value} | trace={r.trace_id} | cost=${r.cost:.4f}]\n{r.output}"
            )

        synthesis_query = "\n---\n".join(worker_summaries)

        # Create synthesis budget
        synth_budget = AgentBudget(max_cost=synthesis_budget)

        try:
            result = await synthesizer.execute(synthesis_query, synth_budget, synth_identity)
        except Exception as exc:
            result = AgentResult(
                agent_id=synth_identity.agent_id,
                trace_id=synth_identity.trace_id,
                output=str(exc),
                cost=synth_budget.cost_accumulated,
                status=AgentStatus.FAILED,
                metadata={"error": str(exc)},
            )

        # Record synthesis cost
        self._record_cost(result)

        return result

    def _record_cost(self, result: AgentResult) -> None:
        """Record agent cost in the cost ledger if available."""
        if self.cost_ledger is None or result.cost <= 0:
            return

        try:
            self.cost_ledger.record_event(
                operation="subagent_execution",
                provider="subagent_runtime",
                cost_usd=result.cost,
                agent_id=result.agent_id,
                metadata={"trace_id": result.trace_id},
            )
        except Exception as exc:
            # Non-blocking: log failure but don't halt execution
            _logger.warning(
                "Failed to record cost for agent %s (trace=%s, cost=$%.4f): %s",
                result.agent_id,
                result.trace_id,
                result.cost,
                exc,
            )
