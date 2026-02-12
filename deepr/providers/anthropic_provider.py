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
import os
from datetime import datetime, timezone
from typing import Any, Optional

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
)
from deepr.tools import ToolRegistry


class AnthropicProvider(DeepResearchProvider):
    """
    Anthropic Claude provider for deep research.

    Uses Extended Thinking for complex reasoning + tool use for web search.
    We manage the research workflow (not turnkey like OpenAI).
    """

    SUPPORTED_MODELS = [
        "claude-opus-4-5",  # Latest flagship - $5/$25 per MTok
        "claude-opus-4-1",  # Legacy - $15/$75 per MTok
        "claude-opus-4",  # Legacy - $15/$75 per MTok
        "claude-sonnet-4-5",  # Best value for research - $3/$15 per MTok
        "claude-sonnet-4",  # Previous gen - $3/$15 per MTok
        "claude-sonnet-3-7",  # Legacy - $3/$15 per MTok
        "claude-haiku-4-5",  # Fast/cheap - $1/$5 per MTok (no Extended Thinking)
    ]

    # Recommended models by use case
    RECOMMENDED_MODELS = {
        "research": "claude-opus-4-5",  # Best reasoning for deep research (~$0.80/query)
        "balanced": "claude-sonnet-4-5",  # Good quality, lower cost (~$0.48/query)
        "fast": "claude-haiku-4-5",  # Quick answers, cheapest (no Extended Thinking)
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-opus-4-5",  # Default to Opus for research quality
        thinking_budget: int = 32000,  # Higher budget for Opus research tasks
        web_search_backend: str = "auto",  # brave, tavily, duckduckgo, auto
    ):
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Claude model (default: claude-opus-4-5 for best research quality)
            thinking_budget: Token budget for Extended Thinking (default 32K for research)
            web_search_backend: Web search backend (brave, tavily, duckduckgo, auto)

        Model recommendations:
            - Research tasks: claude-opus-4-5 (~$0.80/query) - best reasoning
            - Balanced: claude-sonnet-4-5 (~$0.48/query) - good quality, lower cost
            - Fast/cheap: claude-haiku-4-5 - no Extended Thinking support
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("Anthropic SDK not installed. Run: pip install anthropic")

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")

        self.model = model
        self.thinking_budget = max(1024, thinking_budget)
        self.client = Anthropic(api_key=self.api_key, timeout=1200.0)  # 20 min timeout

        # Initialize tool executor
        self.tool_executor = ToolRegistry.create_executor(web_search=True, backend=web_search_backend)

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
            messages = [{"role": "user", "content": user_message}]
            thinking_content = []
            response_content = []
            tool_calls_made = []

            # Multi-turn loop for tool use
            max_turns = 5  # Prevent infinite loops
            for _turn in range(max_turns):
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.thinking_budget + 16000,  # Must be > thinking budget
                    thinking={"type": "enabled", "budget_tokens": self.thinking_budget},
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
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

                        # Collect tool result for next message
                        tool_results_to_send.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(tool_result.data) if tool_result.success else tool_result.error,
                            }
                        )

                # If we made tool calls, add assistant message + tool results
                if has_tool_use:
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content": tool_results_to_send})
                else:
                    # No tool use, we're done
                    break

            # Format report with thinking trace (for transparency)
            self._format_research_report(
                thinking="\n\n".join(thinking_content),
                findings="\n\n".join(response_content),
                tool_calls=tool_calls_made,
                request=request,
            )

            # Generate job ID (Anthropic doesn't return one)
            job_id = f"anthropic-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

            # Store result internally
            # TODO: Integrate with storage system

            return job_id

        except AnthropicError as e:
            raise ProviderError(message=f"Anthropic API error: {e}", provider="anthropic", original_error=e) from e
        except Exception as e:
            raise ProviderError(
                message=f"Research submission failed: {e}", provider="anthropic", original_error=e
            ) from e

    async def get_status(self, job_id: str) -> ResearchResponse:
        """
        Get status of research job.

        Note: Anthropic responses are synchronous (no polling needed).
        This method exists for interface compatibility.
        """
        # Since Anthropic is synchronous, jobs complete immediately
        # This is a compatibility shim
        return ResearchResponse(
            id=job_id,
            status="completed",
            output=None,  # Synchronous - no stored output
            usage=UsageStats(input_tokens=0, output_tokens=0, reasoning_tokens=0, cost=0.0),
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
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
            "claude-4-opus" -> "claude-opus-4-5"
            "claude-sonnet" -> "claude-sonnet-4-5"
            "claude-haiku" -> "claude-haiku-4-5"
        """
        model_mapping = {
            # Current generation (4.5)
            "claude-opus": "claude-opus-4-5",
            "claude-4-opus": "claude-opus-4-5",
            "claude-sonnet": "claude-sonnet-4-5",
            "claude-haiku": "claude-haiku-4-5",
            # Legacy mappings
            "claude-4-opus-legacy": "claude-opus-4-1",
            "claude-3.7-sonnet": "claude-sonnet-3-7",
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
            f"\n**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
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


# Pricing (as of 2026-02)
# Source: https://www.anthropic.com/pricing
ANTHROPIC_PRICING = {
    # Claude 4.5 series (latest)
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

# Prompt caching pricing (for Opus 4.5)
ANTHROPIC_CACHE_PRICING = {
    "claude-opus-4-5": {
        "cache_write": 6.25,  # per MTok to write to cache
        "cache_read": 0.50,  # per MTok to read from cache (90% savings!)
    },
    "claude-sonnet-4-5": {
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
}
