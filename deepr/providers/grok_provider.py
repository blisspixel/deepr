"""xAI Grok provider implementation for research.

Grok uses chat completions API (OpenAI-compatible) with:
- Reasoning models (grok-4, grok-4-fast-reasoning)
- Server-side tool calling (web_search, x_search, code_interpreter)
- Document collections for file upload
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
            "grok-4": "grok-4",
            "grok-4-fast": "grok-4-fast-non-reasoning",  # Default to non-reasoning for speed
            "grok-4-fast-reasoning": "grok-4-fast-reasoning",
            "grok-4-fast-non-reasoning": "grok-4-fast-non-reasoning",
            "grok-3": "grok-3",
            "grok-3-mini": "grok-3-mini",
            "grok-code-fast": "grok-code-fast-1",
            # Aliases (prefer non-reasoning for speed, use explicit -reasoning if needed)
            "grok": "grok-4-fast-non-reasoning",
            "grok-fast": "grok-4-fast-non-reasoning",
            "grok-mini": "grok-3-mini",
        }

        # Pricing (per million tokens) -- grok-4-fast from registry, rest local
        from .registry import get_token_pricing

        _grok_fast = get_token_pricing("grok-4-fast")
        self.pricing = {
            "grok-4": {"input": 3.00, "output": 15.00},
            "grok-4-fast-reasoning": _grok_fast,
            "grok-4-fast-non-reasoning": _grok_fast,
            "grok-3": {"input": 3.00, "output": 15.00},
            "grok-3-mini": {"input": 0.30, "output": 0.50},
            "grok-code-fast-1": {"input": 0.20, "output": 1.50},
        }

        # Store completed jobs in memory (simple implementation)
        self.jobs: Dict[str, Dict[str, Any]] = {}

    def get_model_name(self, model: str) -> str:
        """Map user-friendly model names to xAI model IDs."""
        return self.model_mappings.get(model, model)

    async def submit_research(self, request: ResearchRequest) -> str:
        """
        Submit research to Grok using chat completions.

        Executes immediately (synchronous completion).
        """
        import uuid

        # Generate job ID
        job_id = f"grok-{uuid.uuid4().hex[:16]}"

        # Store job
        self.jobs[job_id] = {
            "status": "processing",
            "request": request,
            "created_at": datetime.now(timezone.utc),
            "model": self.get_model_name(request.model),
        }

        # Execute research immediately
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
            # Don't raise - store error in job status instead
            # This matches the behavior expected for immediate-completion providers

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

    def _calculate_cost(
        self, prompt_tokens: int, completion_tokens: int, model: str, reasoning_tokens: int = 0
    ) -> float:
        """Calculate cost for Grok models including reasoning tokens."""
        # Get pricing for model
        prices = self.pricing.get(model, self.pricing["grok-4-fast-reasoning"])

        # Input cost (prompt tokens)
        input_cost = (prompt_tokens / 1_000_000) * prices["input"]

        # Output cost (completion + reasoning tokens)
        # Reasoning tokens are billed as output tokens
        total_output_tokens = completion_tokens + reasoning_tokens
        output_cost = (total_output_tokens / 1_000_000) * prices["output"]

        return round(input_cost + output_cost, 6)

    async def upload_document(self, file_path: str, collection_id: Optional[str] = None) -> Dict[str, Any]:
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

    async def list_vector_stores(self) -> List[Dict[str, Any]]:
        """List Grok collections."""
        raise NotImplementedError("Grok vector store not yet implemented")

    async def wait_for_vector_store(self, store_id: str, timeout: int = 300) -> bool:
        """Wait for Grok collection to be ready."""
        raise NotImplementedError("Grok vector store not yet implemented")


# Grok's Capabilities:
#
# 1. Reasoning Models (grok-4, grok-4-fast-reasoning)
#    - Extended thinking for complex problems
#    - reasoning_tokens tracked separately in usage
#    - No reasoning_effort parameter (always full reasoning)
#
# 2. Server-Side Tools (autonomous execution)
#    - live_search: Internet search + page browsing (formerly web_search)
#    - x_search: X posts, users, threads
#    - code_interpreter: Python execution
#    - Agent autonomously decides when/how to use tools
#
# 3. Document Collections (file upload)
#    - Upload files to collections
#    - Query across documents
#    - $2.50 per 1k requests
#
# 4. Vision Models (grok-2-vision)
#    - Image understanding
#    - Multimodal analysis
#
# 5. Cost Structure
#    - Token-based pricing
#    - Tool invocation costs ($10/1k calls for search/code)
#    - Reasoning tokens count as output tokens
#
# Note: Grok 4 is always-on reasoning (no non-reasoning mode)
# Some parameters not supported: presencePenalty, frequencyPenalty, stop
