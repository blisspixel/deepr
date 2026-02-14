"""Azure AI Foundry provider implementation.

Supports two modes:
1. Deep Research (Agent/Thread/Run + DeepResearchTool + Bing grounding) — for
   comprehensive multi-step research using o3-deep-research. Background async.
2. Regular completions (Agent/Thread/Run, no DeepResearchTool) — for lighter
   tasks like expert chat, synthesis, quick lookups using GPT-5/5-mini,
   GPT-4.1/4.1-mini, GPT-4o/4o-mini. Synchronous via polling.

This is Microsoft's native AI Foundry Agent Service, distinct from the
OpenAI-on-Azure provider (azure_provider.py).

Requirements:
    pip install azure-ai-projects azure-ai-agents azure-identity

Region availability (Agent Service, Feb 2026):
    Deep research (o3): West US, Norway East, South Central US
    GPT-4.1/5 family: 20+ regions via Global Standard deployment
    Broadest availability: eastus2, swedencentral

Environment variables:
    AZURE_PROJECT_ENDPOINT - Project endpoint URL
    AZURE_DEEP_RESEARCH_DEPLOYMENT - Deep research model deployment (default: o3-deep-research)
    AZURE_GPT_DEPLOYMENT - Default GPT model for the agent (default: gpt-4.1)
    AZURE_BING_RESOURCE_NAME - Bing grounding connection name
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .base import (
    DeepResearchProvider,
    ProviderError,
    ResearchRequest,
    ResearchResponse,
    UsageStats,
    VectorStore,
)

logger = logging.getLogger(__name__)

# Models that trigger the deep research path (Agent + DeepResearchTool + Bing)
_DEEP_RESEARCH_MODELS = {"o3-deep-research"}


def _is_deep_research_model(model: str) -> bool:
    """Check if a model string should use the deep research path."""
    return any(dr in model for dr in _DEEP_RESEARCH_MODELS)


class AzureFoundryProvider(DeepResearchProvider):
    """Azure AI Foundry provider with dual-mode operation.

    Deep research models (o3-deep-research) use the Agent/Thread/Run pattern
    with DeepResearchTool + Bing web grounding for comprehensive async research.

    Regular models (gpt-5, gpt-5-mini, gpt-4.1, gpt-4.1-mini, gpt-4o,
    gpt-4o-mini) use a lightweight agent without DeepResearchTool for chat,
    synthesis, expert building, and quick lookups.

    Authentication is via DefaultAzureCredential (Azure AD, Managed Identity).
    No API key option — use `az login` for local development.
    """

    def __init__(
        self,
        project_endpoint: Optional[str] = None,
        deep_research_deployment: Optional[str] = None,
        gpt_deployment: Optional[str] = None,
        bing_resource_name: Optional[str] = None,
        model_mappings: Optional[dict] = None,
    ):
        """Initialize Azure Foundry provider.

        Args:
            project_endpoint: Azure AI project endpoint URL
                (defaults to AZURE_PROJECT_ENDPOINT env var)
            deep_research_deployment: Deep research model deployment name
                (defaults to AZURE_DEEP_RESEARCH_DEPLOYMENT or "o3-deep-research")
            gpt_deployment: GPT model deployment for the agent
                (defaults to AZURE_GPT_DEPLOYMENT or "gpt-4o")
            bing_resource_name: Bing grounding connection name
                (defaults to AZURE_BING_RESOURCE_NAME)
            model_mappings: Custom model name mappings (optional)
        """
        import os

        self.project_endpoint = project_endpoint or os.getenv("AZURE_PROJECT_ENDPOINT")
        if not self.project_endpoint:
            raise ValueError("Azure AI Foundry project endpoint is required (set AZURE_PROJECT_ENDPOINT)")

        self.deep_research_deployment = deep_research_deployment or os.getenv(
            "AZURE_DEEP_RESEARCH_DEPLOYMENT", "o3-deep-research"
        )
        self.gpt_deployment = gpt_deployment or os.getenv("AZURE_GPT_DEPLOYMENT", "gpt-4.1")
        self.bing_resource_name = bing_resource_name or os.getenv("AZURE_BING_RESOURCE_NAME")

        self.model_mappings = model_mappings or {
            "o3-deep-research": self.deep_research_deployment,
            "gpt-5": "gpt-5",
            "gpt-5-mini": "gpt-5-mini",
            "gpt-4.1": self.gpt_deployment,
            "gpt-4.1-mini": "gpt-4.1-mini",
            "gpt-4o": "gpt-4o",
            "gpt-4o-mini": "gpt-4o-mini",
        }

        # Lazy-initialized clients
        self._project_client = None
        self._agents_client = None
        self._deep_research_agent_id: Optional[str] = None
        self._regular_agent_ids: dict[str, str] = {}  # model -> agent_id
        self._bing_connection_id: Optional[str] = None

        # Pricing per 1M tokens for regular models (from registry)
        from .registry import get_token_pricing

        # Order matters: longer keys first so "gpt-4o-mini" matches before "gpt-4o"
        self.pricing = {
            "gpt-5-mini": {"input": 0.25, "output": 2.00},
            "gpt-5": get_token_pricing("gpt-5"),
            "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
            "gpt-4.1": get_token_pricing("gpt-4.1"),
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4o": get_token_pricing("gpt-4o"),
        }

        # Cost estimation: Bing grounding ~$0.035/search query
        self.deep_research_cost_estimate = 0.50

        # Job tracking — deep research and regular share the same dict
        self._jobs: dict[str, dict[str, Any]] = {}

        logger.info(
            "AzureFoundryProvider initialized (endpoint=%s, model=%s)",
            self.project_endpoint,
            self.deep_research_deployment,
        )

    def _get_credential(self):
        """Get Azure credential via DefaultAzureCredential."""
        from azure.identity import DefaultAzureCredential

        return DefaultAzureCredential()

    def _get_project_client(self):
        """Get or create AIProjectClient (lazy init)."""
        if self._project_client is None:
            from azure.ai.projects import AIProjectClient

            self._project_client = AIProjectClient(
                endpoint=self.project_endpoint,
                credential=self._get_credential(),
            )
        return self._project_client

    def _get_agents_client(self):
        """Get or create AgentsClient (lazy init)."""
        if self._agents_client is None:
            from azure.ai.agents import AgentsClient

            self._agents_client = AgentsClient(
                endpoint=self.project_endpoint,
                credential=self._get_credential(),
            )
        return self._agents_client

    def _get_bing_connection_id(self) -> Optional[str]:
        """Resolve Bing grounding connection ID from resource name."""
        if self._bing_connection_id is not None:
            return self._bing_connection_id

        if not self.bing_resource_name:
            return None

        try:
            project_client = self._get_project_client()
            connection = project_client.connections.get(name=self.bing_resource_name)
            self._bing_connection_id = connection.id
            logger.info("Resolved Bing connection: %s", self._bing_connection_id)
            return self._bing_connection_id
        except Exception as e:
            logger.warning("Failed to resolve Bing connection '%s': %s", self.bing_resource_name, e)
            return None

    def _ensure_deep_research_agent(self) -> str:
        """Create or return the reusable deep research agent (with DeepResearchTool + Bing)."""
        if self._deep_research_agent_id is not None:
            return self._deep_research_agent_id

        from azure.ai.agents.models import DeepResearchTool

        agents_client = self._get_agents_client()

        # Build deep research tool with Bing grounding
        tool_kwargs: dict[str, Any] = {
            "deep_research_model": self.deep_research_deployment,
        }
        bing_conn_id = self._get_bing_connection_id()
        if bing_conn_id:
            tool_kwargs["bing_grounding_connection_id"] = bing_conn_id

        deep_research_tool = DeepResearchTool(**tool_kwargs)

        agent = agents_client.create_agent(
            model=self.gpt_deployment,
            name=f"deepr-research-agent-{uuid.uuid4().hex[:8]}",
            instructions=(
                "You are a deep research assistant. Conduct thorough research "
                "and provide comprehensive answers with citations."
            ),
            tools=deep_research_tool.definitions,
        )
        self._deep_research_agent_id = agent.id
        logger.info("Created Foundry deep research agent: %s", self._deep_research_agent_id)
        return self._deep_research_agent_id

    def _ensure_regular_agent(self, model: str) -> str:
        """Create or return a reusable regular agent (no DeepResearchTool) for a model."""
        if model in self._regular_agent_ids:
            return self._regular_agent_ids[model]

        agents_client = self._get_agents_client()
        deployment = self.get_model_name(model)

        agent = agents_client.create_agent(
            model=deployment,
            name=f"deepr-{deployment}-{uuid.uuid4().hex[:8]}",
            instructions=(
                "You are a helpful research assistant. Provide clear, accurate, "
                "well-structured responses with citations where possible."
            ),
        )
        self._regular_agent_ids[model] = agent.id
        logger.info("Created Foundry regular agent: %s (model=%s)", agent.id, deployment)
        return agent.id

    def get_model_name(self, model_key: str) -> str:
        """Map generic model key to Azure Foundry deployment name."""
        return self.model_mappings.get(model_key, model_key)

    def _calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost for regular (non-deep-research) Foundry models."""
        if _is_deep_research_model(model):
            return self.deep_research_cost_estimate

        # Look up pricing by model name
        prices = None
        for key in self.pricing:
            if key in model:
                prices = self.pricing[key]
                break

        if not prices:
            prices = self.pricing.get("gpt-4o", {"input": 2.50, "output": 10.00})

        input_cost = (input_tokens / 1_000_000) * prices["input"]
        output_cost = (output_tokens / 1_000_000) * prices["output"]
        return round(input_cost + output_cost, 6)

    # =========================================================================
    # Submit research — dispatches to deep research or regular mode
    # =========================================================================

    async def submit_research(self, request: ResearchRequest) -> str:
        """Submit a research job via Azure AI Foundry.

        Routes to the deep research path (Agent + DeepResearchTool + Bing) for
        deep research models, or to a lightweight agent for regular models.
        """
        model = self.get_model_name(request.model)

        if _is_deep_research_model(model):
            return await self._submit_deep_research(request)
        else:
            return await self._submit_regular_research(request, model)

    async def _submit_deep_research(self, request: ResearchRequest) -> str:
        """Submit deep research via Agent + DeepResearchTool + Bing grounding."""
        max_retries = 3
        retry_delay = 5

        # Build prompt
        prompt_parts = []
        if request.system_message:
            prompt_parts.append(request.system_message)
        prompt_parts.append(request.prompt)
        prompt = "\n\n".join(prompt_parts)

        for attempt in range(max_retries):
            try:

                def _create_run():
                    agents_client = self._get_agents_client()
                    agent_id = self._ensure_deep_research_agent()

                    thread = agents_client.threads.create()
                    agents_client.messages.create(
                        thread_id=thread.id,
                        role="user",
                        content=prompt,
                    )
                    run = agents_client.runs.create(
                        thread_id=thread.id,
                        agent_id=agent_id,
                    )
                    return thread.id, run.id

                thread_id, run_id = await asyncio.to_thread(_create_run)
                job_id = f"{thread_id}:{run_id}"

                self._jobs[job_id] = {
                    "status": "in_progress",
                    "kind": "deep_research",
                    "thread_id": thread_id,
                    "run_id": run_id,
                    "created_at": datetime.now(timezone.utc),
                    "model": self.deep_research_deployment,
                    "request": request,
                }

                logger.info("Foundry deep research started: %s", job_id)
                return job_id

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2**attempt)
                    logger.warning(
                        "Foundry deep research submit error (attempt %d/%d): %s",
                        attempt + 1,
                        max_retries,
                        e,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise ProviderError(
                    message=f"Failed to start Foundry deep research after {max_retries} attempts: {e}",
                    provider="azure-foundry",
                    original_error=e,
                )

        raise ProviderError(
            message="Failed to start Foundry deep research after all retries",
            provider="azure-foundry",
        )

    async def _submit_regular_research(self, request: ResearchRequest, model: str) -> str:
        """Submit a regular (non-deep-research) job using a lightweight agent."""
        max_retries = 3
        retry_delay = 2

        prompt_parts = []
        if request.system_message:
            prompt_parts.append(request.system_message)
        prompt_parts.append(request.prompt)
        prompt = "\n\n".join(prompt_parts)

        for attempt in range(max_retries):
            try:

                def _create_run():
                    agents_client = self._get_agents_client()
                    agent_id = self._ensure_regular_agent(request.model)

                    thread = agents_client.threads.create()
                    agents_client.messages.create(
                        thread_id=thread.id,
                        role="user",
                        content=prompt,
                    )
                    run = agents_client.runs.create(
                        thread_id=thread.id,
                        agent_id=agent_id,
                    )
                    return thread.id, run.id

                thread_id, run_id = await asyncio.to_thread(_create_run)
                job_id = f"{thread_id}:{run_id}"

                self._jobs[job_id] = {
                    "status": "in_progress",
                    "kind": "regular",
                    "thread_id": thread_id,
                    "run_id": run_id,
                    "created_at": datetime.now(timezone.utc),
                    "model": model,
                    "request": request,
                }

                logger.info("Foundry regular job started: %s (model=%s)", job_id, model)
                return job_id

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2**attempt)
                    logger.warning(
                        "Foundry regular submit error (attempt %d/%d): %s",
                        attempt + 1,
                        max_retries,
                        e,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise ProviderError(
                    message=f"Failed to start Foundry job after {max_retries} attempts: {e}",
                    provider="azure-foundry",
                    original_error=e,
                )

        raise ProviderError(
            message="Failed to start Foundry job after all retries",
            provider="azure-foundry",
        )

    # =========================================================================
    # Get status — handles both deep research and regular jobs
    # =========================================================================

    async def get_status(self, job_id: str) -> ResearchResponse:
        """Get research job status by polling the run."""
        if job_id not in self._jobs:
            raise ProviderError(message=f"Job {job_id} not found", provider="azure-foundry")

        job_data = self._jobs[job_id]

        # If already completed/failed, return cached result
        if job_data["status"] in ("completed", "failed", "cancelled"):
            return self._build_response(job_id, job_data)

        thread_id = job_data["thread_id"]
        run_id = job_data["run_id"]
        is_deep = job_data.get("kind") == "deep_research"

        try:

            def _poll_run():
                from azure.ai.agents.models import MessageRole

                agents_client = self._get_agents_client()

                run = agents_client.runs.get(thread_id=thread_id, run_id=run_id)

                if run.status == "completed":
                    # Extract the last agent message
                    last_msg = agents_client.messages.get_last_message_by_role(
                        thread_id=thread_id,
                        role=MessageRole.AGENT,
                    )

                    text = ""
                    citations = []

                    if last_msg and hasattr(last_msg, "text_messages"):
                        text = "\n\n".join(t.text.value for t in last_msg.text_messages if hasattr(t, "text"))

                    # Citations only meaningful for deep research
                    if is_deep and last_msg and hasattr(last_msg, "url_citation_annotations"):
                        for ann in last_msg.url_citation_annotations:
                            if hasattr(ann, "url_citation"):
                                citations.append(
                                    {
                                        "title": getattr(ann.url_citation, "title", ""),
                                        "url": getattr(ann.url_citation, "url", ""),
                                    }
                                )

                    # Extract usage if available
                    usage_data = None
                    if hasattr(run, "usage") and run.usage:
                        usage_data = {
                            "prompt_tokens": getattr(run.usage, "prompt_tokens", 0),
                            "completion_tokens": getattr(run.usage, "completion_tokens", 0),
                        }

                    return "completed", text, citations, None, usage_data
                elif run.status == "failed":
                    error_msg = getattr(run, "last_error", None)
                    if error_msg and hasattr(error_msg, "message"):
                        error_msg = error_msg.message
                    else:
                        error_msg = "Run failed"
                    return "failed", "", [], str(error_msg), None
                elif run.status == "cancelled":
                    return "cancelled", "", [], None, None
                else:
                    return run.status, "", [], None, None

            status, text, citations, error, usage_data = await asyncio.to_thread(_poll_run)

            if status == "completed":
                if is_deep:
                    # Deep research: estimate cost from citation count
                    search_count = len(citations)
                    estimated_cost = max(self.deep_research_cost_estimate, search_count * 0.035)
                else:
                    # Regular: estimate cost from token usage
                    input_tokens = usage_data["prompt_tokens"] if usage_data else len(text) // 4
                    output_tokens = usage_data["completion_tokens"] if usage_data else len(text) // 4
                    estimated_cost = self._calculate_cost(input_tokens, output_tokens, job_data["model"])

                job_data.update(
                    {
                        "status": "completed",
                        "completed_at": datetime.now(timezone.utc),
                        "output": text,
                        "citations": citations,
                        "search_queries_count": len(citations),
                        "estimated_cost": estimated_cost,
                        "usage": usage_data,
                    }
                )
            elif status == "failed":
                job_data.update(
                    {
                        "status": "failed",
                        "error": error,
                        "completed_at": datetime.now(timezone.utc),
                    }
                )
            elif status == "cancelled":
                job_data.update(
                    {
                        "status": "cancelled",
                        "completed_at": datetime.now(timezone.utc),
                    }
                )
            elif status in ("queued", "in_progress"):
                job_data["status"] = "in_progress"

        except Exception as e:
            logger.warning("Error polling Foundry run %s: %s", job_id, e)

        return self._build_response(job_id, job_data)

    def _build_response(self, job_id: str, job_data: dict) -> ResearchResponse:
        """Build a ResearchResponse from job data."""
        usage = None
        if job_data["status"] == "completed":
            estimated_cost = job_data.get("estimated_cost", self.deep_research_cost_estimate)
            usage_data = job_data.get("usage")
            if usage_data:
                usage = UsageStats(
                    input_tokens=usage_data.get("prompt_tokens", 0),
                    output_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=(usage_data.get("prompt_tokens", 0) + usage_data.get("completion_tokens", 0)),
                    cost=estimated_cost,
                )
            else:
                usage = UsageStats(cost=estimated_cost)

        output = None
        if job_data.get("output"):
            output = [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": job_data["output"]}],
                }
            ]

        return ResearchResponse(
            id=job_id,
            status=job_data["status"],
            created_at=job_data.get("created_at"),
            completed_at=job_data.get("completed_at"),
            model=job_data.get("model", self.deep_research_deployment),
            output=output,
            usage=usage,
            metadata={"citations": job_data.get("citations", [])},
            error=job_data.get("error"),
        )

    # =========================================================================
    # Cancel
    # =========================================================================

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running research job."""
        if job_id not in self._jobs:
            return False

        job_data = self._jobs[job_id]
        if job_data["status"] not in ("queued", "in_progress"):
            return False

        thread_id = job_data["thread_id"]
        run_id = job_data["run_id"]

        try:

            def _cancel():
                agents_client = self._get_agents_client()
                agents_client.runs.cancel(thread_id=thread_id, run_id=run_id)

            await asyncio.to_thread(_cancel)
            job_data["status"] = "cancelled"
            job_data["completed_at"] = datetime.now(timezone.utc)
            return True
        except Exception as e:
            logger.warning("Failed to cancel Foundry run %s: %s", job_id, e)
            return False

    # =========================================================================
    # Document / vector store operations (not natively supported)
    # =========================================================================

    async def upload_document(self, file_path: str, purpose: str = "assistants") -> str:
        """Upload a document. Azure Foundry uses thread-level attachments."""
        raise ProviderError(
            message="Azure Foundry deep research does not support standalone file uploads. "
            "Use thread message attachments instead.",
            provider="azure-foundry",
        )

    async def create_vector_store(self, name: str, file_ids: list[str]) -> VectorStore:
        """Create vector store. Not supported by Foundry deep research."""
        raise ProviderError(
            message="Azure Foundry deep research does not support vector stores. "
            "Use Bing grounding for web-based research.",
            provider="azure-foundry",
        )

    async def wait_for_vector_store(self, vector_store_id: str, timeout: int = 900, poll_interval: float = 2.0) -> bool:
        """Not supported by Foundry."""
        return False

    async def list_vector_stores(self, limit: int = 100) -> list[VectorStore]:
        """Not supported by Foundry."""
        return []

    async def delete_vector_store(self, vector_store_id: str) -> bool:
        """Not supported by Foundry."""
        return False

    # =========================================================================
    # Cleanup
    # =========================================================================

    def close(self):
        """Clean up all reusable agents."""
        if self._deep_research_agent_id and self._agents_client:
            try:
                self._agents_client.delete_agent(self._deep_research_agent_id)
                logger.info("Deleted Foundry deep research agent: %s", self._deep_research_agent_id)
            except Exception as e:
                logger.warning("Failed to delete agent %s: %s", self._deep_research_agent_id, e)
            self._deep_research_agent_id = None

        if self._regular_agent_ids and self._agents_client:
            for model, agent_id in list(self._regular_agent_ids.items()):
                try:
                    self._agents_client.delete_agent(agent_id)
                    logger.info("Deleted Foundry regular agent: %s (model=%s)", agent_id, model)
                except Exception as e:
                    logger.warning("Failed to delete agent %s: %s", agent_id, e)
            self._regular_agent_ids.clear()

    def __del__(self):
        """Attempt cleanup on garbage collection."""
        try:
            self.close()
        except Exception:
            pass

    # =========================================================================
    # Adaptive polling
    # =========================================================================

    @staticmethod
    def get_poll_interval(elapsed_seconds: float) -> float:
        """Get adaptive poll interval based on elapsed time.

        Deep research typically takes 2-10 minutes. Polling strategy:
        - First 30s: every 5s (catch quick completions)
        - 30-120s: every 10s
        - 120s+: every 20s
        """
        if elapsed_seconds < 30:
            return 5.0
        elif elapsed_seconds < 120:
            return 10.0
        else:
            return 20.0
