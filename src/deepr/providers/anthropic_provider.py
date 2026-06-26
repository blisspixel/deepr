"""
Anthropic Claude provider for Deep Research.

Uses Claude's Extended Thinking + Agentic workflow for research tasks.

Architecture:
- Claude doesn't have a turnkey "deep research" API like OpenAI
- Instead: Extended Thinking + tool use + our orchestration = research capability
- We control the agentic loop (planning, web search, synthesis)
- Extended Thinking provides reasoning transparency (like o1/o3)

Key Insight from Research:
- Anthropic has "Research" feature in claude.ai (5+ tool calls, synthesize sources)
- This is UI-only, not an API endpoint
- We replicate this by: Extended Thinking + web search tools + our workflow

Comparison to OpenAI:
- OpenAI: Submit prompt → get comprehensive report (turnkey)
- Anthropic: Submit prompt with tools → manage multi-turn workflow ourselves
"""

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

try:
    from anthropic import Anthropic, AnthropicError

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from deepr.providers.base import (
    DeepResearchProvider,
    ProviderError,
    ResearchRequest,
    ResearchResponse,
    UsageStats,
    VectorStore,
    coerce_usage_int,
)
from deepr.tools import ToolRegistry


class AnthropicProvider(DeepResearchProvider):
    """
    Anthropic Claude provider for deep research.

    Uses Extended Thinking for complex reasoning + tool use for web search.
    We manage the research workflow (not turnkey like OpenAI).
    """

    SUPPORTED_MODELS = [
        "claude-fable-5",  # Frontier tier - $10/$50 per MTok (new tokenizer ~30% more tokens)
        "claude-opus-4-8",  # Flagship - $5/$25 per MTok (adaptive thinking only)
        "claude-opus-4-7",  # Previous flagship - $5/$25 per MTok (adaptive thinking only)
        "claude-opus-4-6",  # $5/$25 per MTok (adaptive thinking recommended)
        "claude-opus-4-5",  # $5/$25 per MTok
        "claude-opus-4-1",  # Deprecated (retires 2026-08-05) - $15/$75 per MTok
        "claude-opus-4",  # Deprecated (retires 2026-06-15) - $15/$75 per MTok
        "claude-sonnet-4-6",  # Best value - $3/$15 per MTok (adaptive thinking recommended)
        "claude-sonnet-4-5",  # Previous gen - $3/$15 per MTok
        "claude-sonnet-4",  # Deprecated (retires 2026-06-15) - $3/$15 per MTok
        "claude-haiku-4-5",  # Fast/cheap - $1/$5 per MTok (no Extended Thinking)
    ]

    # Recommended models by use case
    RECOMMENDED_MODELS = {
        "research": "claude-opus-4-8",  # Best reasoning for deep research (~$0.85/query)
        "frontier": "claude-fable-5",  # Most capable, premium price (~$2.20/query)
        "balanced": "claude-sonnet-4-6",  # Good quality, lower cost (~$0.48/query)
        "fast": "claude-haiku-4-5",  # Quick answers, cheapest (no Extended Thinking)
    }

    # Models where thinking is adaptive-only: sending budget_tokens returns 400.
    # claude-fable-5 additionally rejects an explicit {"type": "disabled"}.
    ADAPTIVE_THINKING_MODELS = (
        "claude-fable-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
    )

    # Models with no Extended Thinking support at all - omit the param.
    NO_THINKING_MODELS = ("claude-haiku-4-5",)

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-opus-4-8",  # Default to Opus for research quality
        thinking_budget: int = 32000,  # Higher budget for Opus research tasks
        web_search_backend: str = "auto",  # brave, tavily, duckduckgo, auto
    ):
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Claude model (default: claude-opus-4-8 for best research quality)
            thinking_budget: Token budget for Extended Thinking on legacy models.
                Adaptive-thinking models (4.6+/Fable) ignore the budget but still
                use it to size max_tokens headroom.
            web_search_backend: Web search backend (brave, tavily, duckduckgo, auto)

        Model recommendations:
            - Research tasks: claude-opus-4-8 (~$0.85/query) - best reasoning
            - Frontier: claude-fable-5 (~$2.20/query) - most capable, 2x token rate
            - Balanced: claude-sonnet-4-6 (~$0.48/query) - good quality, lower cost
            - Fast/cheap: claude-haiku-4-5 - no Extended Thinking support
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("Anthropic SDK not installed. Run: pip install anthropic")

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")

        self.model = model
        self.thinking_budget = max(1024, thinking_budget)
        # In-memory store for completed jobs. Anthropic responses are
        # synchronous, but the poller/queue contract expects a job_id we
        # can re-query for usage + output. Previously submit_research
        # discarded both, leaving every Anthropic call to be billed by
        # the provider while the cost ledger recorded $0.
        self._jobs: dict[str, ResearchResponse] = {}
        self.client = Anthropic(api_key=self.api_key, timeout=1200.0)  # 20 min timeout

        # Initialize tool executor
        self.tool_executor = ToolRegistry.create_executor(web_search=True, backend=web_search_backend)

    def _calculate_usage_cost(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        """Calculate Anthropic cost across regular and prompt-cache buckets."""
        from deepr.providers.registry import get_token_pricing

        token_rates = get_token_pricing(self.model, input_tokens=input_tokens)
        cache_rates = self._cache_rates_for_model(token_rates["input"])

        input_cost = (max(input_tokens, 0) / 1_000_000) * token_rates["input"]
        output_cost = (max(output_tokens, 0) / 1_000_000) * token_rates["output"]
        cache_creation_cost = (max(cache_creation_tokens, 0) / 1_000_000) * cache_rates["cache_write"]
        cache_read_cost = (max(cache_read_tokens, 0) / 1_000_000) * cache_rates["cache_read"]

        return round(input_cost + output_cost + cache_creation_cost + cache_read_cost, 6)

    def _cache_rates_for_model(self, input_rate: float) -> dict[str, float]:
        """Return Anthropic prompt-cache rates for the configured model."""
        for model, rates in ANTHROPIC_CACHE_PRICING.items():
            if self.model.startswith(model):
                return rates
        return {
            "cache_write": round(input_rate * 1.25, 6),
            "cache_read": round(input_rate * 0.10, 6),
        }

    def _build_thinking_param(self) -> dict[str, Any] | None:
        """Return the thinking config appropriate for the configured model.

        - Adaptive-only models (Opus 4.6+, Sonnet 4.6, Fable 5): sending
          ``budget_tokens`` returns a 400, so use ``{"type": "adaptive"}``.
        - Haiku has no Extended Thinking: omit the param entirely.
        - Older models keep the legacy enabled+budget form.
        """
        if any(self.model.startswith(m) for m in self.NO_THINKING_MODELS):
            return None
        if any(self.model.startswith(m) for m in self.ADAPTIVE_THINKING_MODELS):
            return {"type": "adaptive"}
        return {"type": "enabled", "budget_tokens": self.thinking_budget}

    async def submit_research(self, request: ResearchRequest) -> str:
        """
        Submit research using Claude Extended Thinking + agentic workflow.

        Since Anthropic doesn't have turnkey deep research:
        1. Use Extended Thinking to plan research approach
        2. Use tools for web search (if web_search_enabled)
        3. Synthesize findings
        4. Return comprehensive report

        Note: This is more manual than OpenAI's approach but gives more control.
        """
        try:
            # Build system prompt for research mode
            system_prompt = self._build_research_system_prompt(request)

            # Build user message with context
            user_message = self._build_research_prompt(request)

            # Get tool definitions if web search enabled
            tools = None
            if hasattr(request, "web_search_enabled") and request.web_search_enabled:
                tools = self.tool_executor.get_tool_definitions(format="anthropic")

            # Execute research with Extended Thinking (multi-turn for tool calls)
            messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
            thinking_content = []
            response_content = []
            tool_calls_made = []

            # Per-turn token accumulation. The previous implementation
            # dropped response.usage entirely so every Anthropic research
            # call was billed by the provider but recorded as $0 in the
            # cost ledger / get_status response.
            total_input_tokens = 0
            total_output_tokens = 0
            total_cache_read_tokens = 0
            total_cache_creation_tokens = 0

            # Multi-turn loop for tool use
            max_turns = 5  # Prevent infinite loops
            for _turn in range(max_turns):
                request_kwargs: dict[str, Any] = {
                    "model": self.model,
                    "max_tokens": self.thinking_budget + 16000,  # Headroom above thinking
                    "system": system_prompt,
                    "messages": messages,
                    "tools": tools,
                }
                thinking_param = self._build_thinking_param()
                if thinking_param is not None:
                    request_kwargs["thinking"] = thinking_param
                response = self.client.messages.create(  # type: ignore[call-overload]  # plain dicts for thinking/messages/tools; SDK wants typed params
                    **request_kwargs
                )

                # Safety classifiers (claude-fable-5) can decline with a
                # successful HTTP 200 + stop_reason "refusal". Pre-output
                # refusals carry an empty content array, so reading blocks
                # below would silently yield an empty report billed as
                # success. Surface it as a provider error instead.
                if getattr(response, "stop_reason", None) == "refusal":
                    details = getattr(response, "stop_details", None)
                    category = getattr(details, "category", None) if details else None
                    raise ProviderError(
                        f"Anthropic safety classifiers declined the request"
                        f"{f' (category: {category})' if category else ''}. "
                        "Retry on a different model (e.g. claude-opus-4-8).",
                        provider="anthropic",
                    )

                # Accumulate usage from this turn
                turn_usage = getattr(response, "usage", None)
                if turn_usage is not None:
                    total_input_tokens += coerce_usage_int(getattr(turn_usage, "input_tokens", 0))
                    total_output_tokens += coerce_usage_int(getattr(turn_usage, "output_tokens", 0))
                    total_cache_read_tokens += coerce_usage_int(getattr(turn_usage, "cache_read_input_tokens", 0))
                    total_cache_creation_tokens += coerce_usage_int(
                        getattr(turn_usage, "cache_creation_input_tokens", 0)
                    )

                # Extract thinking + content + collect tool uses
                has_tool_use = False
                tool_results_to_send = []

                for block in response.content:
                    if block.type == "thinking":
                        thinking_content.append(block.thinking)
                    elif block.type == "text":
                        response_content.append(block.text)
                    elif block.type == "tool_use":
                        has_tool_use = True
                        # Execute tool
                        tool_result = await self.tool_executor.execute(block.name, **block.input)
                        tool_calls_made.append(
                            {"tool": block.name, "input": block.input, "success": tool_result.success}
                        )

                        # Collect tool result for next message. The
                        # Anthropic spec accepts a string OR a list of
                        # blocks; ensure we always send a non-empty
                        # string so a None error doesn't produce a
                        # malformed message body.
                        if tool_result.success:
                            result_payload = json.dumps(tool_result.data)
                        else:
                            err_text = tool_result.error or "tool execution failed"
                            result_payload = str(err_text) or "tool execution failed"
                        tool_results_to_send.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_payload,
                                **({"is_error": True} if not tool_result.success else {}),
                            }
                        )

                # If we made tool calls, add assistant message + tool results
                if has_tool_use:
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content": tool_results_to_send})
                else:
                    # No tool use, we're done
                    break
            else:
                # for-else: ran ``max_turns`` iterations without an early
                # break. The final turn may have requested tool use that
                # was executed but never sent back for the model to
                # synthesise. Add an explicit note so the consumer can
                # detect a truncated response instead of silently
                # accepting a partial report.
                logger.warning(
                    "Anthropic research hit max_turns=%d without convergence; report may be incomplete",
                    max_turns,
                )
                response_content.append(
                    f"\n\n_[Report truncated: research loop reached the {max_turns}-turn ceiling. "
                    "Consider re-running with a higher max_turns or a narrower query.]_"
                )

            # Format report with thinking trace (for transparency)
            report_markdown = self._format_research_report(
                thinking="\n\n".join(thinking_content),
                findings="\n\n".join(response_content),
                tool_calls=tool_calls_made,
                request=request,
            )

            # Generate job ID (Anthropic doesn't return one)
            job_id = f"anthropic-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"

            # Compute cost from accumulated usage. Anthropic reports regular
            # input, cache writes, and cache reads as separate token buckets.
            total_prompt_tokens = total_input_tokens + total_cache_creation_tokens + total_cache_read_tokens
            usage_stats = UsageStats(
                input_tokens=total_prompt_tokens,
                output_tokens=total_output_tokens,
                cache_creation_input_tokens=total_cache_creation_tokens,
                cache_read_input_tokens=total_cache_read_tokens,
                reasoning_tokens=0,
                total_tokens=total_prompt_tokens + total_output_tokens,
            )
            try:
                usage_stats.cost = self._calculate_usage_cost(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    cache_creation_tokens=total_cache_creation_tokens,
                    cache_read_tokens=total_cache_read_tokens,
                )
            except Exception:
                usage_stats.cost = 0.0

            self._jobs[job_id] = ResearchResponse(
                id=job_id,
                status="completed",
                output=[
                    {
                        "type": "message",
                        "content": [{"type": "text", "text": report_markdown}],
                    }
                ],
                usage=usage_stats,
                created_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )

            return job_id

        except ProviderError:
            raise
        except AnthropicError as e:
            raise ProviderError(message=f"Anthropic API error: {e}", provider="anthropic", original_error=e) from e
        except Exception as e:
            raise ProviderError(
                message=f"Research submission failed: {e}", provider="anthropic", original_error=e
            ) from e

    async def get_status(self, job_id: str) -> ResearchResponse:
        """
        Get status of research job.

        Returns the stored response built during ``submit_research``.
        Anthropic responses are synchronous, so a job is always either
        present-and-completed or unknown. Previously this method returned
        ``output=None`` and ``cost=0.0`` for every call, which meant the
        poller recorded $0 for every Anthropic spend.
        """
        stored = self._jobs.get(job_id)
        if stored is not None:
            return stored
        return ResearchResponse(
            id=job_id,
            status="failed",
            output=None,
            usage=UsageStats(input_tokens=0, output_tokens=0, reasoning_tokens=0, cost=0.0),
            created_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            error=f"Unknown Anthropic job id {job_id}",
        )

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel research job.

        Not applicable for Anthropic (synchronous responses).
        """
        return False

    async def upload_document(self, file_path: str, purpose: str = "assistants") -> str:
        """
        Upload document for context.

        Anthropic doesn't have persistent file storage like OpenAI.
        Documents must be embedded in message content directly.
        """
        raise NotImplementedError("Anthropic doesn't support file uploads. Embed documents directly in prompts.")

    async def create_vector_store(self, name: str, file_ids: list[str]) -> VectorStore:
        """
        Create vector store.

        Anthropic doesn't have vector store feature.
        Use external vector DB if needed.
        """
        raise NotImplementedError(
            "Anthropic doesn't support vector stores. Use external solution (Pinecone, Weaviate, etc.)"
        )

    async def wait_for_vector_store(self, vector_store_id: str, timeout: int = 900, poll_interval: float = 2.0) -> bool:
        """Not applicable for Anthropic."""
        raise NotImplementedError("Anthropic doesn't support vector stores")

    async def delete_vector_store(self, vector_store_id: str) -> bool:
        """Not applicable for Anthropic."""
        raise NotImplementedError("Anthropic doesn't support vector stores")

    async def list_vector_stores(self, limit: int = 100) -> list[VectorStore]:
        """Not applicable for Anthropic."""
        raise NotImplementedError("Anthropic doesn't support vector stores")

    def get_model_name(self, model_key: str) -> str:
        """
        Map generic model key to Anthropic model name.

        Examples:
            "claude-4-opus" -> "claude-opus-4-8"
            "claude-sonnet" -> "claude-sonnet-4-6"
            "claude-haiku" -> "claude-haiku-4-5"
        """
        model_mapping = {
            # Current generation
            "claude-fable": "claude-fable-5",
            "claude-opus": "claude-opus-4-8",
            "claude-4-opus": "claude-opus-4-8",
            "claude-sonnet": "claude-sonnet-4-6",
            "claude-haiku": "claude-haiku-4-5",
            # Legacy mappings
            "claude-4-opus-legacy": "claude-opus-4-1",
        }

        return model_mapping.get(model_key, self.model)

    def _build_research_system_prompt(self, request: ResearchRequest) -> str:
        """Build system prompt for research mode."""
        return """You are a deep research assistant. Your goal is to produce comprehensive, well-sourced research reports.

Your research process:
1. Use Extended Thinking to plan your research approach
2. Break down the question into key areas to investigate
3. Use web_search tool to gather current information (if enabled)
4. Synthesize findings into a coherent, structured report
5. Cite sources and show your reasoning

Report format:
- Executive Summary (2-3 paragraphs)
- Key Findings (organized by theme)
- Detailed Analysis (with reasoning traces)
- Sources and Citations
- Recommendations or Conclusions

Always show your work. Transparency builds trust."""

    def _build_research_prompt(self, request: ResearchRequest) -> str:
        """Build user message for research request."""
        parts = [f"Research Question: {request.prompt}"]

        if hasattr(request, "additional_instructions") and request.additional_instructions:
            parts.append(f"\nAdditional Context:\n{request.additional_instructions}")

        if hasattr(request, "web_search_enabled") and request.web_search_enabled:
            parts.append("\nYou have access to web_search tool. Use it to gather current information.")

        parts.append("\nProduce a comprehensive research report.")

        return "\n".join(parts)

    def _format_research_report(
        self, thinking: str, findings: str, tool_calls: list[dict[str, Any]], request: ResearchRequest
    ) -> str:
        """Format research report with thinking trace."""
        parts = [
            "# Research Report",
            f"\n**Query:** {request.prompt}",
            f"\n**Model:** {self.model}",
            f"\n**Date:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            "\n---\n",
        ]

        # Include thinking trace for transparency (if present)
        if thinking.strip():
            parts.append("## Research Process\n")
            parts.append("<details><summary>View reasoning trace</summary>\n")
            parts.append(f"\n{thinking}\n")
            parts.append("</details>\n\n")

        # Include tool calls for observability
        if tool_calls:
            parts.append("## Tool Usage\n")
            parts.append("<details><summary>View tool calls</summary>\n\n")
            for i, call in enumerate(tool_calls, 1):
                parts.append(f"{i}. **{call['tool']}**\n")
                parts.append(f"   - Input: `{call['input']}`\n")
                parts.append(f"   - Success: {call['success']}\n\n")
            parts.append("</details>\n\n")

        parts.append("## Findings\n")
        parts.append(findings)

        return "".join(parts)


# Pricing (as of 2026-06)
# Source: https://www.anthropic.com/pricing
# INFORMATIONAL ONLY: actual billing/estimates use deepr/providers/registry.py
# (get_token_pricing). When adding a model, update the registry first - an
# unregistered model silently bills at the o4-mini default rate.
ANTHROPIC_PRICING = {
    # Claude 5 family
    "claude-fable-5": {
        "input": 10.00,  # per MTok - new tokenizer uses ~30% more tokens for the same text
        "output": 50.00,
        "thinking": 10.00,  # Thinking always on, charged at input rate
    },
    # Claude 4.6-4.8 series
    "claude-opus-4-8": {
        "input": 5.00,  # per MTok
        "output": 25.00,
        "thinking": 5.00,  # Adaptive Thinking charged at input rate
    },
    "claude-opus-4-7": {
        "input": 5.00,
        "output": 25.00,
        "thinking": 5.00,
    },
    "claude-opus-4-6": {
        "input": 5.00,
        "output": 25.00,
        "thinking": 5.00,
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "thinking": 3.00,
    },
    # Claude 4.5 series
    "claude-opus-4-5": {
        "input": 5.00,  # per MTok - 66% cheaper than Opus 4!
        "output": 25.00,
        "thinking": 5.00,  # Extended Thinking charged at input rate
    },
    "claude-sonnet-4-5": {
        "input": 3.00,  # per MTok (prompts ≤200K tokens)
        "output": 15.00,
        "thinking": 3.00,
        # Note: $6/$15 for prompts >200K tokens
    },
    "claude-haiku-4-5": {
        "input": 1.00,  # per MTok
        "output": 5.00,
        "thinking": None,  # Haiku doesn't support Extended Thinking
    },
    # Claude 4 series (legacy but still available)
    "claude-opus-4-1": {
        "input": 15.00,
        "output": 75.00,
        "thinking": 15.00,
    },
    "claude-opus-4": {
        "input": 15.00,
        "output": 75.00,
        "thinking": 15.00,
    },
    "claude-sonnet-4": {
        "input": 3.00,
        "output": 15.00,
        "thinking": 3.00,
    },
    # Claude 3.7 (legacy)
    "claude-sonnet-3-7": {
        "input": 3.00,
        "output": 15.00,
        "thinking": 3.00,
    },
}

# Additional Anthropic API costs (not per-token)
ANTHROPIC_TOOL_PRICING = {
    "web_search": 10.00,  # $10 per 1,000 searches (released Sept 2025)
    # Note: Web search also incurs token costs for results
}

# Prompt caching pricing (cache_write = 1.25x input, cache_read = 0.1x input)
ANTHROPIC_CACHE_PRICING = {
    "claude-fable-5": {
        "cache_write": 12.50,
        "cache_read": 1.00,
    },
    "claude-opus-4-8": {
        "cache_write": 6.25,
        "cache_read": 0.50,
    },
    "claude-sonnet-4-6": {
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-opus-4-5": {
        "cache_write": 6.25,  # per MTok to write to cache
        "cache_read": 0.50,  # per MTok to read from cache (90% savings!)
    },
    "claude-sonnet-4-5": {
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
}
