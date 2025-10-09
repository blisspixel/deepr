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

import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from anthropic import Anthropic, AnthropicError
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from deepr.providers.base import (
    DeepResearchProvider,
    ResearchRequest,
    ResearchResponse,
    UsageStats,
    VectorStore,
    ProviderError,
)


class AnthropicProvider(DeepResearchProvider):
    """
    Anthropic Claude provider for deep research.

    Uses Extended Thinking for complex reasoning + tool use for web search.
    We manage the research workflow (not turnkey like OpenAI).
    """

    SUPPORTED_MODELS = [
        "claude-opus-4-1",
        "claude-opus-4",
        "claude-sonnet-4-5",
        "claude-sonnet-4",
        "claude-sonnet-3-7",
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-5",
        thinking_budget: int = 16000,  # Recommended for complex tasks
    ):
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Claude model supporting Extended Thinking
            thinking_budget: Token budget for Extended Thinking (min 1024, rec 16k+)
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "Anthropic SDK not installed. Run: pip install anthropic"
            )

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")

        self.model = model
        self.thinking_budget = max(1024, thinking_budget)
        self.client = Anthropic(api_key=self.api_key)

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

            # Define web search tool if enabled
            tools = []
            if request.web_search_enabled:
                tools.append({
                    "name": "web_search",
                    "description": "Search the web for current information. Returns relevant search results.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            }
                        },
                        "required": ["query"]
                    }
                })

            # Execute research with Extended Thinking
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8000,  # Output budget for final report
                thinking={
                    "type": "enabled",
                    "budget_tokens": self.thinking_budget
                },
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                tools=tools if tools else None,
            )

            # Extract thinking + response
            thinking_content = []
            response_content = []

            for block in response.content:
                if block.type == "thinking":
                    thinking_content.append(block.thinking)
                elif block.type == "text":
                    response_content.append(block.text)

            # Format report with thinking trace (for transparency)
            report = self._format_research_report(
                thinking="\n\n".join(thinking_content),
                findings="\n\n".join(response_content),
                request=request
            )

            # Generate job ID (Anthropic doesn't return one)
            job_id = f"anthropic-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            # Store result internally
            # TODO: Integrate with storage system

            return job_id

        except AnthropicError as e:
            raise ProviderError(f"Anthropic API error: {e}") from e
        except Exception as e:
            raise ProviderError(f"Research submission failed: {e}") from e

    async def get_status(self, job_id: str) -> ResearchResponse:
        """
        Get status of research job.

        Note: Anthropic responses are synchronous (no polling needed).
        This method exists for interface compatibility.
        """
        # Since Anthropic is synchronous, jobs complete immediately
        # This is a compatibility shim
        return ResearchResponse(
            job_id=job_id,
            status="completed",
            result="Research completed (synchronous)",
            usage=UsageStats(
                input_tokens=0,
                output_tokens=0,
                thinking_tokens=0,
                total_cost=0.0
            ),
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
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
        raise NotImplementedError(
            "Anthropic doesn't support file uploads. Embed documents directly in prompts."
        )

    async def create_vector_store(self, name: str, file_ids: List[str]) -> VectorStore:
        """
        Create vector store.

        Anthropic doesn't have vector store feature.
        Use external vector DB if needed.
        """
        raise NotImplementedError(
            "Anthropic doesn't support vector stores. Use external solution (Pinecone, Weaviate, etc.)"
        )

    async def wait_for_vector_store(
        self, vector_store_id: str, timeout: int = 900, poll_interval: float = 2.0
    ) -> bool:
        """Not applicable for Anthropic."""
        raise NotImplementedError("Anthropic doesn't support vector stores")

    async def delete_vector_store(self, vector_store_id: str) -> bool:
        """Not applicable for Anthropic."""
        raise NotImplementedError("Anthropic doesn't support vector stores")

    def get_model_name(self, model_key: str) -> str:
        """
        Map generic model key to Anthropic model name.

        Examples:
            "claude-4-opus" -> "claude-opus-4"
            "claude-sonnet" -> "claude-sonnet-4-5"
        """
        model_mapping = {
            "claude-4-opus": "claude-opus-4",
            "claude-opus": "claude-opus-4-1",
            "claude-sonnet": "claude-sonnet-4-5",
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

        if request.additional_instructions:
            parts.append(f"\nAdditional Context:\n{request.additional_instructions}")

        if request.web_search_enabled:
            parts.append("\nYou have access to web_search tool. Use it to gather current information.")

        parts.append("\nProduce a comprehensive research report.")

        return "\n".join(parts)

    def _format_research_report(
        self,
        thinking: str,
        findings: str,
        request: ResearchRequest
    ) -> str:
        """Format research report with thinking trace."""
        parts = [
            "# Research Report",
            f"\n**Query:** {request.prompt}",
            f"\n**Model:** {self.model}",
            f"\n**Date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            "\n---\n",
        ]

        # Include thinking trace for transparency (if present)
        if thinking.strip():
            parts.append("## Research Process\n")
            parts.append("<details><summary>View reasoning trace</summary>\n")
            parts.append(f"\n{thinking}\n")
            parts.append("</details>\n\n")

        parts.append("## Findings\n")
        parts.append(findings)

        return "".join(parts)


# Pricing (as of 2025-01)
ANTHROPIC_PRICING = {
    "claude-opus-4-1": {
        "input": 15.00,  # per MTok
        "output": 75.00,
        "thinking": 15.00,  # Extended Thinking charged at input rate
    },
    "claude-opus-4": {
        "input": 15.00,
        "output": 75.00,
        "thinking": 15.00,
    },
    "claude-sonnet-4-5": {
        "input": 3.00,
        "output": 15.00,
        "thinking": 3.00,
    },
    "claude-sonnet-4": {
        "input": 3.00,
        "output": 15.00,
        "thinking": 3.00,
    },
    "claude-sonnet-3-7": {
        "input": 3.00,
        "output": 15.00,
        "thinking": 3.00,
    },
}
