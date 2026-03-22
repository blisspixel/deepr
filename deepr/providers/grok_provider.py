"""xAI Grok provider implementation for research.

Grok uses chat completions API (OpenAI-compatible) with:
- Grok 4.20 flagship models (reasoning, non-reasoning, multi-agent)
- Grok 4.1 Fast budget models (reasoning, non-reasoning)
- Full agentic tool calling (web_search, x_search, code_interpreter)
- Multi-agent mode (4/16 parallel agents) via Responses API
- Document collections for file upload
"""

import os
from datetime import datetime, timezone
from typing import Any, Optional

import openai

from .base import (
    DeepResearchProvider,
    ProviderError,
    ResearchRequest,
    ResearchResponse,
    UsageStats,
)


class GrokProvider(DeepResearchProvider):
    """xAI Grok implementation using chat completions API.

    Grok models are reasoning-first with autonomous tool calling.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.x.ai/v1",
        timeout: int = 3600,
    ):
        """
        Initialize Grok provider.

        Args:
            api_key: xAI API key (defaults to XAI_API_KEY env var)
            base_url: API endpoint
            timeout: Request timeout (default 3600s for reasoning models)
        """
        api_key = api_key or os.getenv("XAI_API_KEY")
        if not api_key:
            raise ValueError("xAI API key is required (set XAI_API_KEY)")

        # Initialize OpenAI client pointing to xAI endpoint
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

        # Store timeout for xAI SDK client
        self.timeout = timeout

        # Grok model mappings
        self.model_mappings = {
            # Grok 4.20 flagship (March 2026)
            "grok-4.20-0309-reasoning": "grok-4.20-0309-reasoning",
            "grok-4.20-0309-non-reasoning": "grok-4.20-0309-non-reasoning",
            "grok-4.20-multi-agent-0309": "grok-4.20-multi-agent-0309",
            "grok-4.20-reasoning": "grok-4.20-0309-reasoning",
            "grok-4.20-non-reasoning": "grok-4.20-0309-non-reasoning",
            "grok-4.20-multi-agent": "grok-4.20-multi-agent-0309",
            "grok-4.20": "grok-4.20-0309-non-reasoning",
            # Grok 4.1 Fast budget tier
            "grok-4-1-fast-reasoning": "grok-4-1-fast-reasoning",
            "grok-4-1-fast-non-reasoning": "grok-4-1-fast-non-reasoning",
            # Legacy / other
            "grok-3": "grok-3",
            "grok-3-mini": "grok-3-mini",
            "grok-code-fast": "grok-code-fast-1",
            # Aliases
            "grok": "grok-4.20-0309-non-reasoning",  # Flagship default
            "grok-fast": "grok-4-1-fast-non-reasoning",  # Cheap tier
            "grok-flagship": "grok-4.20-0309-reasoning",  # Explicit flagship
            "grok-mini": "grok-3-mini",
        }

        # Pricing (per million tokens) -- from registry where possible
        from .registry import get_token_pricing

        _grok_4_1_fast = get_token_pricing("grok-4-1-fast-non-reasoning")
        self.pricing = {
            # Grok 4.20 flagship ($2/$6 per MTok)
            "grok-4.20-0309-reasoning": {"input": 2.00, "output": 6.00},
            "grok-4.20-0309-non-reasoning": {"input": 2.00, "output": 6.00},
            "grok-4.20-multi-agent-0309": {"input": 2.00, "output": 6.00},
            # Grok 4.1 Fast budget ($0.20/$0.50 per MTok)
            "grok-4-1-fast-reasoning": _grok_4_1_fast,
            "grok-4-1-fast-non-reasoning": _grok_4_1_fast,
            # Other
            "grok-3": {"input": 3.00, "output": 15.00},
            "grok-3-mini": {"input": 0.30, "output": 0.50},
            "grok-code-fast-1": {"input": 0.20, "output": 1.50},
        }

        # Store completed jobs in memory (simple implementation)
        self.jobs: dict[str, dict[str, Any]] = {}

    def get_model_name(self, model: str) -> str:
        """Map user-friendly model names to xAI model IDs."""
        return self.model_mappings.get(model, model)

    async def submit_research(self, request: ResearchRequest) -> str:
        """
        Submit research to Grok using chat completions.

        For multi-agent models (grok-4.20-multi-agent*), delegates to
        client-side parallel fan-out with per-agent budget isolation.
        Otherwise executes as a single synchronous completion.
        """
        import uuid

        # Generate job ID
        job_id = f"grok-{uuid.uuid4().hex[:16]}"
        resolved_model = self.get_model_name(request.model)

        # Store job
        self.jobs[job_id] = {
            "status": "processing",
            "request": request,
            "created_at": datetime.now(timezone.utc),
            "model": resolved_model,
        }

        # Route to multi-agent if appropriate
        if "multi-agent" in resolved_model:
            await self._execute_multi_agent_research(job_id)
        else:
            await self._execute_research(job_id)

        return job_id

    async def _execute_research(self, job_id: str):
        """Execute research using Grok chat completions."""
        job_data = self.jobs[job_id]
        request = job_data["request"]
        model = job_data["model"]

        try:
            # Build messages
            messages = [
                {
                    "role": "system",
                    "content": request.system_message
                    or "You are Grok, a highly intelligent research assistant. Provide comprehensive, well-reasoned analysis with citations.",
                },
                {"role": "user", "content": request.prompt},
            ]

            # Build tools list (if enabled)
            # NOTE: Grok doesn't actually support tools in chat.completions API yet
            # Web search is automatic when needed. Skip tools parameter entirely.
            tools = None

            # Create completion
            completion_params = {
                "model": model,
                "messages": messages,
                "temperature": request.temperature if request.temperature is not None else 0.7,
            }

            # Add tools if specified
            if tools:
                completion_params["tools"] = tools

            # Execute chat completion
            response = await self.client.chat.completions.create(**completion_params)

            # Extract content
            content = response.choices[0].message.content or ""

            # Calculate cost
            usage = response.usage
            cost = self._calculate_cost(
                usage.prompt_tokens,
                usage.completion_tokens,
                model,
                getattr(usage.completion_tokens_details, "reasoning_tokens", 0)
                if hasattr(usage, "completion_tokens_details")
                else 0,
            )

            # Store completion
            self.jobs[job_id].update(
                {
                    "status": "completed",
                    "content": content,
                    "usage": usage,
                    "cost": cost,
                    "completed_at": datetime.now(timezone.utc),
                }
            )

        except openai.OpenAIError as e:
            self.jobs[job_id].update(
                {
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            raise

    async def get_status(self, job_id: str) -> ResearchResponse:
        """Get research job status."""
        if job_id not in self.jobs:
            raise ProviderError(f"Job {job_id} not found", provider="grok")

        job_data = self.jobs[job_id]
        status = job_data["status"]

        if status == "processing":
            return ResearchResponse(
                id=job_id,
                status="in_progress",
                output=None,
                usage=None,
                error=None,
            )

        elif status == "completed":
            content = job_data.get("content", "")
            usage_data = job_data.get("usage")

            # Format output in standardized structure
            output = [{"type": "message", "content": [{"type": "output_text", "text": content}]}]

            # Create usage stats
            usage = None
            if usage_data:
                usage = UsageStats(
                    input_tokens=usage_data.prompt_tokens,
                    output_tokens=usage_data.completion_tokens,
                    total_tokens=usage_data.total_tokens,
                    cost=job_data.get("cost", 0.0),
                )

            return ResearchResponse(
                id=job_id,
                status="completed",
                output=output,
                usage=usage,
                error=None,
            )

        else:  # failed
            return ResearchResponse(
                id=job_id,
                status="failed",
                output=None,
                usage=None,
                error=job_data.get("error", "Unknown error"),
            )

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel research job (immediate execution, cannot cancel)."""
        if job_id in self.jobs:
            if self.jobs[job_id]["status"] == "processing":
                self.jobs[job_id]["status"] = "cancelled"
                return True
        return False

    def _determine_agent_count(self, request: ResearchRequest) -> int:
        """Determine number of parallel agents based on query complexity and budget.

        Heuristic: longer/more complex prompts get more agents, capped by budget.
        Range: 4-16 agents.
        """
        if request.agent_count is not None:
            return max(4, min(16, request.agent_count))

        # Complexity heuristic based on prompt characteristics
        prompt = request.prompt
        word_count = len(prompt.split())
        question_marks = prompt.count("?")
        has_comparison = any(w in prompt.lower() for w in ["compare", "contrast", "versus", "difference"])
        has_multi_aspect = any(w in prompt.lower() for w in ["aspects", "dimensions", "factors", "perspectives"])

        # Base: 4 agents
        agent_count = 4
        if word_count > 50:
            agent_count += 2
        if word_count > 100:
            agent_count += 2
        if question_marks > 2:
            agent_count += 2
        if has_comparison or has_multi_aspect:
            agent_count += 2

        # Cap by budget (each agent costs roughly $0.10-0.50)
        if request.per_agent_budget and request.per_agent_budget < 0.05:
            agent_count = min(agent_count, 4)

        return max(4, min(16, agent_count))

    async def _execute_multi_agent_research(self, job_id: str) -> None:
        """Execute multi-agent research via client-side parallel fan-out.

        Splits the query into N sub-queries, runs them in parallel using
        the AsyncTaskDispatcher, and synthesises results.

        When xAI releases the native Responses API for multi-agent mode,
        this method should be updated to use server-side orchestration instead.
        The entry point (submit_research) and result format stay the same.
        """
        import uuid

        from deepr.agents.contract import AgentBudget, AgentIdentity, AgentRole
        from deepr.experts.constants import MAX_PLAN_CONCURRENCY
        from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher

        job_data = self.jobs[job_id]
        request = job_data["request"]

        # Use single-agent model for individual completions
        single_model = "grok-4.20-0309-reasoning"

        agent_count = self._determine_agent_count(request)
        per_agent_budget = request.per_agent_budget or 0.50

        # Create root identity for trace correlation
        trace_id = uuid.uuid4().hex[:16]
        root_identity = AgentIdentity(
            role=AgentRole.PLANNER,
            trace_id=trace_id,
            name=f"grok-multi-agent-{job_id[:8]}",
        )

        # Generate sub-queries (fan-out perspectives)
        sub_queries = self._generate_sub_queries(request.prompt, agent_count)

        # Execute sub-queries in parallel
        dispatcher = AsyncTaskDispatcher(max_concurrent=MAX_PLAN_CONCURRENCY)

        total_cost = 0.0
        agent_results: list[dict[str, Any]] = []

        async def _run_agent(idx: int, sub_query: str) -> dict[str, Any]:
            child_identity = root_identity.child(
                role=AgentRole.WORKER,
                name=f"agent-{idx}",
            )
            agent_budget = AgentBudget(max_cost=per_agent_budget)

            messages = [
                {
                    "role": "system",
                    "content": (
                        request.system_message
                        or "You are a research agent. Provide thorough analysis with evidence and citations."
                    )
                    + f"\n\nYou are agent {idx + 1} of {agent_count} working on different aspects of the same query.",
                },
                {"role": "user", "content": sub_query},
            ]

            try:
                response = await self.client.chat.completions.create(
                    model=single_model,
                    messages=messages,
                    temperature=request.temperature if request.temperature is not None else 0.7,
                )
                content = response.choices[0].message.content or ""
                usage = response.usage
                cost = self._calculate_cost(
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    single_model,
                )
                agent_budget.record(cost)

                return {
                    "agent_id": child_identity.agent_id,
                    "trace_id": child_identity.trace_id,
                    "content": content,
                    "cost": cost,
                    "tokens_input": usage.prompt_tokens,
                    "tokens_output": usage.completion_tokens,
                    "status": "completed",
                }
            except Exception as e:
                return {
                    "agent_id": child_identity.agent_id,
                    "trace_id": child_identity.trace_id,
                    "content": f"Agent {idx} failed: {e}",
                    "cost": 0.0,
                    "tokens_input": 0,
                    "tokens_output": 0,
                    "status": "failed",
                }

        dispatch_tasks = [{"id": f"agent-{i}", "coro": _run_agent(i, sub_queries[i])} for i in range(len(sub_queries))]

        try:
            dispatch_result = await dispatcher.dispatch(dispatch_tasks)

            for task_id in sorted(dispatch_result.tasks):
                task = dispatch_result.tasks[task_id]
                if task.result is not None:
                    agent_results.append(task.result)
                    total_cost += task.result.get("cost", 0.0)

            # Synthesise agent outputs
            agent_outputs = [r["content"] for r in agent_results if r["status"] == "completed"]
            synthesis = await self._synthesise_multi_agent(request.prompt, agent_outputs, single_model)
            total_cost += synthesis.get("cost", 0.0)

            total_input = sum(r.get("tokens_input", 0) for r in agent_results)
            total_output = sum(r.get("tokens_output", 0) for r in agent_results)
            total_input += synthesis.get("tokens_input", 0)
            total_output += synthesis.get("tokens_output", 0)

            self.jobs[job_id].update(
                {
                    "status": "completed",
                    "content": synthesis.get("content", ""),
                    "cost": total_cost,
                    "completed_at": datetime.now(timezone.utc),
                    "agent_count": len(agent_results),
                    "agent_results": agent_results,
                    "trace_id": trace_id,
                    "usage": type(
                        "Usage",
                        (),
                        {
                            "prompt_tokens": total_input,
                            "completion_tokens": total_output,
                            "total_tokens": total_input + total_output,
                        },
                    )(),
                }
            )

        except Exception as e:
            self.jobs[job_id].update(
                {
                    "status": "failed",
                    "error": f"Multi-agent orchestration failed: {e}",
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            raise

    def _generate_sub_queries(self, prompt: str, agent_count: int) -> list[str]:
        """Split a research prompt into agent-specific sub-queries.

        Each agent gets the full context but a different analytical focus.
        """
        perspectives = [
            "Focus on factual claims, data points, and primary sources.",
            "Focus on historical context, trends, and how this has evolved over time.",
            "Focus on counterarguments, risks, limitations, and alternative viewpoints.",
            "Focus on practical implications, applications, and actionable insights.",
            "Focus on technical details, mechanisms, and implementation specifics.",
            "Focus on comparative analysis with related topics or competitors.",
            "Focus on expert opinions, consensus views, and areas of debate.",
            "Focus on recent developments, breaking news, and emerging trends.",
            "Focus on quantitative data, statistics, and measurable outcomes.",
            "Focus on stakeholder perspectives and impact on different groups.",
            "Focus on regulatory, legal, and compliance aspects.",
            "Focus on economic and financial implications.",
            "Focus on ethical considerations and societal impact.",
            "Focus on future outlook, predictions, and potential scenarios.",
            "Focus on methodology, evidence quality, and research design.",
            "Focus on cross-domain connections and interdisciplinary insights.",
        ]

        sub_queries = []
        for i in range(agent_count):
            perspective = perspectives[i % len(perspectives)]
            sub_queries.append(f"{prompt}\n\n[Research Directive: {perspective}]")
        return sub_queries

    async def _synthesise_multi_agent(
        self, original_query: str, agent_outputs: list[str], model: str
    ) -> dict[str, Any]:
        """Synthesise outputs from multiple agents into a unified report."""
        if not agent_outputs:
            return {"content": "No agent outputs to synthesise.", "cost": 0.0, "tokens_input": 0, "tokens_output": 0}

        parts = "\n\n---\n\n".join(
            f"**Agent {i + 1} findings:**\n{output[:2000]}" for i, output in enumerate(agent_outputs)
        )

        synth_prompt = (
            f"You are synthesising research from {len(agent_outputs)} parallel research agents.\n\n"
            f"Original query: {original_query}\n\n"
            f"Agent findings:\n{parts}\n\n"
            f"Create a comprehensive, unified research report that:\n"
            f"1. Integrates the best insights from all agents\n"
            f"2. Resolves any contradictions between agents\n"
            f"3. Identifies areas of agreement and disagreement\n"
            f"4. Provides a clear, structured final answer\n"
        )

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Synthesise multi-agent research into a unified report."},
                    {"role": "user", "content": synth_prompt[:12000]},
                ],
                temperature=0.3,
            )
            content = response.choices[0].message.content or ""
            usage = response.usage
            cost = self._calculate_cost(usage.prompt_tokens, usage.completion_tokens, model)
            return {
                "content": content,
                "cost": cost,
                "tokens_input": usage.prompt_tokens,
                "tokens_output": usage.completion_tokens,
            }
        except Exception as e:
            # Fallback: concatenate agent outputs
            return {
                "content": f"Synthesis failed ({e}). Raw agent outputs:\n\n{parts}",
                "cost": 0.0,
                "tokens_input": 0,
                "tokens_output": 0,
            }

    def _calculate_cost(
        self, prompt_tokens: int, completion_tokens: int, model: str, reasoning_tokens: int = 0
    ) -> float:
        """Calculate cost for Grok models including reasoning tokens."""
        # Get pricing for model
        prices = self.pricing.get(model, self.pricing["grok-4-1-fast-reasoning"])

        # Input cost (prompt tokens)
        input_cost = (prompt_tokens / 1_000_000) * prices["input"]

        # Output cost (completion + reasoning tokens)
        # Reasoning tokens are billed as output tokens
        total_output_tokens = completion_tokens + reasoning_tokens
        output_cost = (total_output_tokens / 1_000_000) * prices["output"]

        return round(input_cost + output_cost, 6)

    async def upload_document(self, file_path: str, collection_id: Optional[str] = None) -> dict[str, Any]:
        """
        Upload document to Grok collections.

        TODO: Implement when document collections are needed.
        """
        raise NotImplementedError("Grok document upload not yet implemented")

    async def create_vector_store(self, name: str, description: Optional[str] = None) -> str:
        """
        Create Grok collection for document storage.

        TODO: Implement when document collections are needed.
        """
        raise NotImplementedError("Grok vector store not yet implemented")

    async def delete_vector_store(self, store_id: str) -> bool:
        """Delete Grok collection."""
        raise NotImplementedError("Grok vector store not yet implemented")

    async def list_vector_stores(self) -> list[dict[str, Any]]:
        """List Grok collections."""
        raise NotImplementedError("Grok vector store not yet implemented")

    async def wait_for_vector_store(self, store_id: str, timeout: int = 300) -> bool:
        """Wait for Grok collection to be ready."""
        raise NotImplementedError("Grok vector store not yet implemented")


# Grok's Capabilities (March 2026):
#
# 1. Grok 4.20 Flagship (grok-4.20-0309-reasoning/non-reasoning)
#    - Lowest hallucination rate, strict prompt adherence
#    - Full agentic tool calling, native vision
#    - $2/$6 per MTok (input/output), 2M context, 607 RPM
#
# 2. Grok 4.20 Multi-Agent (grok-4.20-multi-agent-0309)
#    - 4 or 16 parallel agents for deep research
#    - Server-side orchestration via Responses API
#    - Same pricing as flagship ($2/$6 per MTok)
#
# 3. Grok 4.1 Fast Budget (grok-4-1-fast-reasoning/non-reasoning)
#    - $0.20/$0.50 per MTok — cheapest option
#    - 2M context, good for high-volume factual tasks
#
# 4. Server-Side Tools (autonomous execution)
#    - web_search: Internet search + page browsing
#    - x_search: X posts, users, threads
#    - code_interpreter: Python sandbox
#    - collections_search: Uploaded docs/RAG
#
# 5. Cost Structure
#    - Token-based pricing
#    - Tool invocation costs ($10/1k calls for search/code)
#    - Reasoning tokens count as output tokens
#
# Unsupported params: logprobs (ignored on 4.20),
# presence_penalty/frequency_penalty/stop (reasoning models)
