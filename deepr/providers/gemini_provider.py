"""Google Gemini provider implementation for Deep Research.

This provider supports two modes:
1. Deep Research Agent (Interactions API) - autonomous multi-step research with
   web search, citations, and structured reports. Equivalent to OpenAI's
   o3-deep-research. Uses background async jobs.
2. Regular generation (generate_content) - standard Gemini calls with thinking,
   Google Search grounding, and structured output. Used for expert chat,
   synthesis, and other non-research tasks.
"""

import os
import json
import asyncio
import logging
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types
from google.genai.errors import APIError as GenaiAPIError
from .base import (
    DeepResearchProvider,
    ResearchRequest,
    ResearchResponse,
    UsageStats,
    VectorStore,
    ProviderError,
)
from datetime import datetime, timezone

# Suppress experimental API warning for Interactions API
# The SDK emits a one-time warning; we acknowledge the API may change.
try:
    import google.genai.client as _genai_client
    _genai_client._interactions_experimental_warned = True
except (ImportError, AttributeError):
    pass

logger = logging.getLogger(__name__)

# Gemini Deep Research Agent identifier
DEEP_RESEARCH_AGENT = "deep-research-pro-preview-12-2025"


def _is_deep_research_model(model: str) -> bool:
    """Check if a model string refers to the Deep Research Agent."""
    return "deep-research" in model or model == DEEP_RESEARCH_AGENT


class GeminiProvider(DeepResearchProvider):
    """Google Gemini implementation of the Deep Research provider.

    Supports dual-mode operation:
    - Deep Research Agent via Interactions API (background async)
    - Regular Gemini models via generate_content (synchronous streaming)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_mappings: Optional[dict] = None,
    ):
        """
        Initialize Gemini provider.

        Args:
            api_key: Google Gemini API key (defaults to GEMINI_API_KEY env var)
            model_mappings: Custom model name mappings (optional)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key is required (set GEMINI_API_KEY)")

        # Initialize client with API key
        os.environ["GEMINI_API_KEY"] = self.api_key
        self.client = genai.Client()

        # Model mappings for convenience
        self.model_mappings = model_mappings or {
            "gemini-2.5-pro": "gemini-2.5-pro",
            "gemini-2.5-flash": "gemini-2.5-flash",
            "gemini-2.5-flash-lite": "gemini-2.5-flash-lite",
            "gemini-pro": "gemini-2.5-pro",
            "gemini-flash": "gemini-2.5-flash",
            "gemini-flash-lite": "gemini-2.5-flash-lite",
            # Deep Research Agent
            "gemini-deep-research": DEEP_RESEARCH_AGENT,
            "deep-research": DEEP_RESEARCH_AGENT,
        }

        # Pricing per 1M tokens -- sourced from registry, with local fallbacks
        from .registry import get_token_pricing
        self.pricing = {
            "gemini-2.5-pro": get_token_pricing("gemini-3-pro"),  # gemini-2.5-pro shares tier
            "gemini-2.5-flash": get_token_pricing("gemini-2.5-flash"),
            "gemini-2.5-flash-lite": {"input": 0.0375, "output": 0.15},
        }

        # Estimated cost per deep research job (varies by search query count)
        self.deep_research_cost_estimate = 1.00

        # Job tracking for regular (synchronous) research
        self.jobs: Dict[str, Dict[str, Any]] = {}

        # Deep research interaction tracking
        self._deep_research_jobs: Dict[str, Dict[str, Any]] = {}

    def get_model_name(self, model_key: str) -> str:
        """Map generic model key to Gemini model name."""
        return self.model_mappings.get(model_key, model_key)

    def _calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost for Gemini models."""
        if _is_deep_research_model(model):
            return self.deep_research_cost_estimate

        base_model = model
        for key in self.pricing:
            if key in model:
                base_model = key
                break

        prices = self.pricing.get(base_model, self.pricing["gemini-2.5-flash"])

        input_cost = (input_tokens / 1_000_000) * prices["input"]
        output_cost = (output_tokens / 1_000_000) * prices["output"]

        return round(input_cost + output_cost, 6)

    def _get_thinking_config(self, model: str, complexity: str = "medium") -> Optional[types.ThinkingConfig]:
        """
        Get thinking configuration based on model and task complexity.

        Args:
            model: Model name
            complexity: Task complexity (easy/medium/hard)

        Returns:
            ThinkingConfig or None
        """
        if "2.5-pro" in model:
            return types.ThinkingConfig(
                thinking_budget=-1,
                include_thoughts=True
            )

        if "2.5-flash" in model and "lite" not in model:
            if complexity == "easy":
                return types.ThinkingConfig(thinking_budget=0)
            elif complexity == "hard":
                return types.ThinkingConfig(
                    thinking_budget=24576,
                    include_thoughts=True
                )
            else:
                return types.ThinkingConfig(
                    thinking_budget=-1,
                    include_thoughts=True
                )

        if "flash-lite" in model:
            if complexity == "hard":
                return types.ThinkingConfig(
                    thinking_budget=8192,
                    include_thoughts=True
                )

        return None

    # =========================================================================
    # Submit research — dispatches to deep research or regular mode
    # =========================================================================

    async def submit_research(self, request: ResearchRequest) -> str:
        """
        Submit research job to Gemini.

        Routes to the Deep Research Agent (Interactions API) for deep-research
        models, or to regular generate_content for standard Gemini models.
        """
        model = self.get_model_name(request.model)

        if _is_deep_research_model(model):
            return await self._submit_deep_research(request)
        else:
            return await self._submit_regular_research(request)

    async def _submit_deep_research(self, request: ResearchRequest) -> str:
        """
        Submit deep research via the Gemini Interactions API.

        This is a background async job — returns an interaction ID immediately.
        Poll with get_status() to check for completion.
        """
        max_retries = 3
        retry_delay = 60  # Deep research retries need longer delays

        # Build prompt combining system message and user prompt
        prompt_parts = []
        if request.system_message:
            prompt_parts.append(request.system_message)
        prompt_parts.append(request.prompt)
        prompt = "\n\n".join(prompt_parts)

        # Build tools list for file grounding
        tools: List[Dict[str, Any]] = []
        file_store_name = None

        if request.document_ids:
            file_store_name = await self._create_file_search_store(
                name=f"deepr-research-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
                file_ids=request.document_ids,
            )
            if file_store_name:
                tools.append({
                    "type": "file_search",
                    "file_search_store_names": [file_store_name]
                })

        for attempt in range(max_retries):
            try:
                create_kwargs: Dict[str, Any] = {
                    "input": prompt,
                    "agent": DEEP_RESEARCH_AGENT,
                    "background": True,
                }
                if tools:
                    create_kwargs["tools"] = tools

                interaction = self.client.interactions.create(**create_kwargs)
                interaction_id = interaction.id

                # Track this deep research job
                self._deep_research_jobs[interaction_id] = {
                    "status": "in_progress",
                    "created_at": datetime.now(timezone.utc),
                    "model": DEEP_RESEARCH_AGENT,
                    "file_store_name": file_store_name,
                    "request": request,
                }

                logger.info(f"Gemini deep research started: {interaction_id}")
                return interaction_id

            except GenaiAPIError as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Gemini deep research error (attempt {attempt + 1}/{max_retries}): {e}"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Cleanup file store on final failure
                    if file_store_name:
                        await self._cleanup_file_search_store(file_store_name)
                    raise ProviderError(
                        message=f"Failed to start deep research after {max_retries} attempts: {e}",
                        provider="gemini",
                        original_error=e,
                    )

        raise ProviderError(
            message="Failed to start deep research after all retries",
            provider="gemini"
        )

    async def _submit_regular_research(self, request: ResearchRequest) -> str:
        """Submit regular (non-deep-research) job using generate_content."""
        import uuid

        job_id = f"gemini-{uuid.uuid4().hex[:16]}"

        self.jobs[job_id] = {
            "status": "queued",
            "request": request,
            "created_at": datetime.now(timezone.utc),
            "model": self.get_model_name(request.model)
        }

        await self._execute_regular_research(job_id)
        return job_id

    async def _execute_regular_research(self, job_id: str):
        """Execute regular research task with generate_content streaming."""
        job_data = self.jobs[job_id]
        request = job_data["request"]

        max_retries = 3
        retry_delay = 1

        job_data["status"] = "in_progress"

        for attempt in range(max_retries):
            try:
                model = job_data["model"]

                prompt_length = len(request.prompt)
                if prompt_length < 200:
                    complexity = "easy"
                elif prompt_length > 1000 or "analyze" in request.prompt.lower() or "research" in request.prompt.lower():
                    complexity = "hard"
                else:
                    complexity = "medium"

                config_params = {}

                thinking_config = self._get_thinking_config(model, complexity)
                if thinking_config:
                    config_params["thinking_config"] = thinking_config

                if request.system_message:
                    config_params["system_instruction"] = request.system_message

                if request.temperature is not None:
                    config_params["temperature"] = request.temperature

                enable_search = any(
                    tool.type in ("web_search_preview", "google_search")
                    for tool in request.tools
                )
                if enable_search:
                    config_params["tools"] = [{"google_search": {}}]

                if request.metadata and request.metadata.get("structured_output"):
                    schema = request.metadata.get("response_schema")
                    if schema:
                        config_params["response_mime_type"] = "application/json"
                        config_params["response_schema"] = schema

                contents = [request.prompt]

                if request.document_ids:
                    for doc_id in request.document_ids:
                        file_obj = self.client.files.get(name=doc_id)
                        contents.insert(0, file_obj)

                config = types.GenerateContentConfig(**config_params) if config_params else None

                response_parts = []
                thought_parts = []

                if config:
                    response_stream = self.client.models.generate_content_stream(
                        model=model, contents=contents, config=config
                    )
                else:
                    response_stream = self.client.models.generate_content_stream(
                        model=model, contents=contents
                    )

                for chunk in response_stream:
                    if hasattr(chunk, "candidates") and chunk.candidates:
                        candidate = chunk.candidates[0]
                        if hasattr(candidate, "content") and candidate.content:
                            for part in candidate.content.parts:
                                if hasattr(part, "text") and part.text:
                                    if hasattr(part, "thought") and part.thought:
                                        thought_parts.append(part.text)
                                    else:
                                        response_parts.append(part.text)

                full_response = "".join(response_parts)
                thoughts_summary = "".join(thought_parts) if thought_parts else None

                # Token estimation: ~4 chars per token is more accurate than word-based
                input_tokens = len(request.prompt) // 4
                output_tokens = len(full_response) // 4

                job_data.update({
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc),
                    "output": full_response,
                    "thoughts": thoughts_summary,
                    "usage": {
                        "input_tokens": int(input_tokens),
                        "output_tokens": int(output_tokens),
                        "total_tokens": int(input_tokens + output_tokens),
                    }
                })

                return

            except GenaiAPIError as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.warning(f"Gemini error (attempt {attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    job_data.update({
                        "status": "failed",
                        "error": str(e),
                        "completed_at": datetime.now(timezone.utc)
                    })
                    return

    # =========================================================================
    # Get status — handles both deep research and regular jobs
    # =========================================================================

    async def get_status(self, job_id: str) -> ResearchResponse:
        """Get research job status. Handles deep research and regular jobs."""
        # Deep research jobs are tracked by interaction ID
        if job_id in self._deep_research_jobs:
            return await self._get_deep_research_status(job_id)

        # Regular jobs tracked in self.jobs
        if job_id in self.jobs:
            return self._get_regular_job_status(job_id)

        raise ProviderError(
            message=f"Job {job_id} not found",
            provider="gemini"
        )

    async def _get_deep_research_status(self, interaction_id: str) -> ResearchResponse:
        """Poll the Interactions API for deep research job status."""
        job_data = self._deep_research_jobs[interaction_id]

        # If already completed/failed, return cached result
        if job_data["status"] in ("completed", "failed"):
            return self._build_deep_research_response(interaction_id, job_data)

        try:
            interaction = self.client.interactions.get(interaction_id)

            if interaction.status == "completed":
                # Extract content from outputs
                content = self._extract_interaction_content(interaction)
                citations = self._extract_interaction_citations(interaction)
                search_count = self._extract_search_query_count(interaction)

                job_data.update({
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc),
                    "output": content,
                    "citations": citations,
                    "search_queries_count": search_count,
                })

                # Cleanup file search store
                file_store = job_data.get("file_store_name")
                if file_store:
                    await self._cleanup_file_search_store(file_store)

            elif interaction.status == "failed":
                error_msg = getattr(interaction, "error", "Deep research failed")
                job_data.update({
                    "status": "failed",
                    "error": str(error_msg),
                    "completed_at": datetime.now(timezone.utc),
                })

                file_store = job_data.get("file_store_name")
                if file_store:
                    await self._cleanup_file_search_store(file_store)

            # else: still pending/in_progress

        except Exception as e:
            logger.warning(f"Error polling deep research {interaction_id}: {e}")
            # Don't fail — might be a transient network error. Keep status as-is.

        return self._build_deep_research_response(interaction_id, job_data)

    def _build_deep_research_response(self, interaction_id: str, job_data: Dict) -> ResearchResponse:
        """Build a ResearchResponse from deep research job data."""
        usage = None
        if job_data["status"] == "completed":
            # Deep research doesn't return token counts; estimate cost from search queries
            search_count = job_data.get("search_queries_count", 0)
            # Each search query costs ~$0.035 after Jan 5, 2026
            estimated_cost = max(self.deep_research_cost_estimate, search_count * 0.035)
            usage = UsageStats(cost=estimated_cost)

        output = None
        if "output" in job_data:
            output = [{
                "type": "message",
                "content": [{
                    "type": "output_text",
                    "text": job_data["output"]
                }]
            }]

        return ResearchResponse(
            id=interaction_id,
            status=job_data["status"],
            created_at=job_data.get("created_at"),
            completed_at=job_data.get("completed_at"),
            model=DEEP_RESEARCH_AGENT,
            output=output,
            usage=usage,
            metadata={"citations": job_data.get("citations", [])},
            error=job_data.get("error"),
        )

    def _get_regular_job_status(self, job_id: str) -> ResearchResponse:
        """Get status for a regular (non-deep-research) job."""
        job_data = self.jobs[job_id]

        usage = None
        if "usage" in job_data:
            usage_data = job_data["usage"]
            usage = UsageStats(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
                reasoning_tokens=0,
                cost=self._calculate_cost(
                    usage_data.get("input_tokens", 0),
                    usage_data.get("output_tokens", 0),
                    job_data["model"]
                )
            )

        output = None
        if "output" in job_data:
            output = [{
                "type": "message",
                "content": [{
                    "type": "output_text",
                    "text": job_data["output"]
                }]
            }]

            if "thoughts" in job_data and job_data["thoughts"]:
                output[0]["content"].insert(0, {
                    "type": "reasoning",
                    "text": job_data["thoughts"]
                })

        return ResearchResponse(
            id=job_id,
            status=job_data["status"],
            created_at=job_data.get("created_at"),
            completed_at=job_data.get("completed_at"),
            model=job_data["model"],
            output=output,
            usage=usage,
            metadata=job_data.get("request").metadata if "request" in job_data else None,
            error=job_data.get("error")
        )

    # =========================================================================
    # Deep Research — content extraction helpers
    # =========================================================================

    def _extract_interaction_content(self, interaction: Any) -> str:
        """Extract text content from a completed deep research interaction."""
        if hasattr(interaction, "outputs") and interaction.outputs:
            text_parts = []
            for output in interaction.outputs:
                if hasattr(output, "text") and output.text:
                    text_parts.append(str(output.text))
            return "\n".join(text_parts) if text_parts else ""
        return ""

    def _extract_interaction_citations(self, interaction: Any) -> List[Dict[str, str]]:
        """Extract citation URLs from grounding metadata."""
        citations = []
        if not hasattr(interaction, "outputs") or not interaction.outputs:
            return citations

        for output in interaction.outputs:
            if hasattr(output, "grounding_metadata"):
                metadata = output.grounding_metadata
                if hasattr(metadata, "grounding_chunks"):
                    for chunk in metadata.grounding_chunks:
                        if hasattr(chunk, "web") and chunk.web:
                            url = getattr(chunk.web, "uri", "")
                            title = getattr(chunk.web, "title", "")
                            if url:
                                citations.append({"url": url, "title": title})

        return citations

    def _extract_search_query_count(self, interaction: Any) -> int:
        """Extract the number of web search queries executed."""
        count = 0
        if not hasattr(interaction, "outputs") or not interaction.outputs:
            return count

        for output in interaction.outputs:
            if hasattr(output, "grounding_metadata"):
                metadata = output.grounding_metadata
                if hasattr(metadata, "web_search_queries"):
                    count += len(metadata.web_search_queries)

        return count

    # =========================================================================
    # Deep Research — File Search Store support
    # =========================================================================

    async def _create_file_search_store(
        self, name: str, file_ids: List[str]
    ) -> Optional[str]:
        """
        Create a File Search Store for deep research grounding.

        Unlike simulated vector stores, this uses Gemini's native
        file_search_stores API for RAG during deep research.

        Args:
            name: Display name for the store
            file_ids: List of file IDs (from upload_document) to include

        Returns:
            Store name for use in tools, or None on failure
        """
        try:
            # Run synchronous SDK calls in thread pool to avoid blocking event loop
            def _create_store():
                store = self.client.file_search_stores.create(
                    config={"display_name": name}
                )
                store_name = store.name

                for file_id in file_ids:
                    self.client.file_search_stores.upload_to_file_search_store(
                        file=file_id,
                        file_search_store_name=store_name,
                        config={"mime_type": "text/plain"},
                    )
                return store_name

            store_name = await asyncio.to_thread(_create_store)
            logger.info(f"Created file search store: {store_name} with {len(file_ids)} files")
            return store_name

        except GenaiAPIError as e:
            logger.warning(f"Failed to create file search store: {e}")
            return None

    async def _cleanup_file_search_store(self, store_name: str) -> None:
        """
        Delete a File Search Store and its documents.

        Important: Gemini file search stores have no TTL — they persist
        until manually deleted. Always clean up after use.
        """
        try:
            # Run synchronous SDK calls in thread pool to avoid blocking event loop
            def _cleanup_store():
                # Delete documents first
                docs = self.client.file_search_stores.documents.list(
                    file_search_store_name=store_name
                )
                for doc in docs:
                    self.client.file_search_stores.documents.delete(name=doc.name)

                # Delete the store itself
                self.client.file_search_stores.delete(name=store_name)

            await asyncio.to_thread(_cleanup_store)
            logger.info(f"Cleaned up file search store: {store_name}")

        except Exception as e:
            # Fire-and-forget cleanup; may fail for many reasons (already
            # deleted, network, auth expiry). Log and continue.
            logger.warning(f"Failed to cleanup file search store {store_name}: {e}")

    # =========================================================================
    # Citation URL resolution
    # =========================================================================

    @staticmethod
    async def resolve_redirect_url(url: str, timeout: float = 10.0) -> str:
        """
        Resolve a Google grounding redirect URL to its final destination.

        The Deep Research API returns URLs like:
        https://vertexaisearch.cloud.google.com/grounding-api-redirect/...

        This follows the redirect chain to get the actual source URL.
        """
        if "vertexaisearch.cloud.google.com/grounding-api-redirect" not in url:
            return url

        try:
            import httpx
            from deepr.utils.security import is_safe_url
            async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
                response = await client.head(url)
                final_url = str(response.url)
                # Validate the resolved URL is not an internal address
                if not is_safe_url(final_url):
                    logger.warning("SSRF: redirect resolved to blocked URL: %s", final_url)
                    return url
                return final_url
        except Exception:
            return url

    # =========================================================================
    # Adaptive polling interval
    # =========================================================================

    @staticmethod
    def get_poll_interval(elapsed_seconds: float) -> float:
        """
        Get adaptive poll interval based on elapsed time.

        Deep research typically takes 5-20 minutes. Polling strategy:
        - First 60s: every 5s (catch quick completions)
        - 60-300s: every 10s
        - 300s+: every 20s
        """
        if elapsed_seconds < 60:
            return 5.0
        elif elapsed_seconds < 300:
            return 10.0
        else:
            return 20.0

    # =========================================================================
    # Cancel, upload, vector store (existing interface)
    # =========================================================================

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a research job."""
        # Deep research jobs
        if job_id in self._deep_research_jobs:
            job_data = self._deep_research_jobs[job_id]
            if job_data["status"] in ("queued", "in_progress"):
                job_data["status"] = "cancelled"
                job_data["completed_at"] = datetime.now(timezone.utc)
                # Cleanup file store
                file_store = job_data.get("file_store_name")
                if file_store:
                    await self._cleanup_file_search_store(file_store)
                return True
            return False

        # Regular jobs
        if job_id in self.jobs:
            job_data = self.jobs[job_id]
            if job_data["status"] in ["queued", "in_progress"]:
                job_data["status"] = "cancelled"
                job_data["completed_at"] = datetime.now(timezone.utc)
                return True

        return False

    async def upload_document(self, file_path: str, purpose: str = "assistants") -> str:
        """
        Upload document to Gemini File API.

        Supports: PDF, DOCX, TXT, MD, code files, images.
        Files stored for 48 hours, up to 50MB per file.
        """
        try:
            import pathlib
            import mimetypes

            path = pathlib.Path(file_path)

            mime_type, _ = mimetypes.guess_type(str(file_path))

            if file_path.endswith('.md') or file_path.endswith('.markdown'):
                mime_type = "text/markdown"
            elif file_path.endswith('.txt'):
                mime_type = "text/plain"
            elif not mime_type:
                mime_type = "text/plain"

            file_obj = self.client.files.upload(
                file=path,
                config={"mime_type": mime_type}
            )

            return file_obj.name

        except (OSError, GenaiAPIError) as e:
            raise ProviderError(
                message=f"Failed to upload document: {str(e)}",
                provider="gemini",
                original_error=e
            )

    async def create_vector_store(self, name: str, file_ids: List[str]) -> VectorStore:
        """
        Create vector store for file grouping.

        For deep research, prefer _create_file_search_store() which uses
        Gemini's native file_search_stores API. This method maintains
        compatibility with the base class interface.
        """
        import uuid
        vs_id = f"gemini-vs-{uuid.uuid4().hex[:16]}"

        if not hasattr(self, "vector_stores"):
            self.vector_stores = {}

        self.vector_stores[vs_id] = {
            "id": vs_id,
            "name": name,
            "file_ids": file_ids,
            "created_at": datetime.now(timezone.utc)
        }

        return VectorStore(id=vs_id, name=name, file_ids=file_ids)

    async def wait_for_vector_store(
        self, vector_store_id: str, timeout: int = 900, poll_interval: float = 2.0
    ) -> bool:
        """Wait for vector store ingestion. Gemini processes files immediately."""
        if not hasattr(self, "vector_stores"):
            return False

        if vector_store_id not in self.vector_stores:
            return False

        vs_data = self.vector_stores[vector_store_id]

        try:
            for file_id in vs_data["file_ids"]:
                self.client.files.get(name=file_id)
            return True
        except GenaiAPIError:
            return False

    async def list_vector_stores(self, limit: int = 100) -> List[VectorStore]:
        """List all vector stores."""
        if not hasattr(self, "vector_stores"):
            return []

        stores = []
        for vs_data in list(self.vector_stores.values())[:limit]:
            stores.append(VectorStore(
                id=vs_data["id"],
                name=vs_data["name"],
                file_ids=vs_data["file_ids"]
            ))

        return stores

    async def delete_vector_store(self, vector_store_id: str) -> bool:
        """Delete vector store."""
        if not hasattr(self, "vector_stores"):
            return False

        if vector_store_id in self.vector_stores:
            del self.vector_stores[vector_store_id]
            return True

        return False
