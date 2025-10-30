"""Google Gemini provider implementation for Deep Research.

This provider implements agentic research capabilities using Gemini 2.5 models with:
- Native thinking/reasoning for complex tasks
- Google Search grounding for web research
- Structured output for knowledge extraction
- Long context windows (1M+ tokens)
- Multimodal document understanding
"""

import os
import asyncio
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types
from .base import (
    DeepResearchProvider,
    ResearchRequest,
    ResearchResponse,
    UsageStats,
    VectorStore,
    ProviderError,
)
from datetime import datetime, timezone


class GeminiProvider(DeepResearchProvider):
    """Google Gemini implementation of the Deep Research provider."""

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
        }

        # Pricing per 1M tokens (as of October 2025)
        self.pricing = {
            "gemini-2.5-pro": {"input": 1.25, "output": 5.00},  # Premium reasoning
            "gemini-2.5-flash": {"input": 0.075, "output": 0.30},  # Balanced
            "gemini-2.5-flash-lite": {"input": 0.0375, "output": 0.15},  # Cost-optimized
        }

        # Job tracking (Gemini doesn't have native job queue, so we simulate)
        self.jobs: Dict[str, Dict[str, Any]] = {}

    def get_model_name(self, model_key: str) -> str:
        """Map generic model key to Gemini model name."""
        return self.model_mappings.get(model_key, model_key)

    def _calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost for Gemini models."""
        # Extract base model name (remove version suffixes)
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

        Gemini 2.5 models use thinking/reasoning for complex tasks:
        - Pro: Always thinks (dynamic by default)
        - Flash: Dynamic thinking (can be controlled)
        - Flash-Lite: Optional thinking (disabled by default)

        Args:
            model: Model name
            complexity: Task complexity (easy/medium/hard)

        Returns:
            ThinkingConfig or None
        """
        # Gemini 2.5 Pro always thinks
        if "2.5-pro" in model:
            return types.ThinkingConfig(
                thinking_budget=-1,  # Dynamic thinking
                include_thoughts=True  # Include thought summaries
            )

        # Gemini 2.5 Flash - dynamic by default, can adjust
        if "2.5-flash" in model and "lite" not in model:
            if complexity == "easy":
                return types.ThinkingConfig(thinking_budget=0)  # No thinking
            elif complexity == "hard":
                return types.ThinkingConfig(
                    thinking_budget=24576,  # Maximum thinking
                    include_thoughts=True
                )
            else:
                return types.ThinkingConfig(
                    thinking_budget=-1,  # Dynamic
                    include_thoughts=True
                )

        # Gemini 2.5 Flash-Lite - thinking on demand
        if "flash-lite" in model:
            if complexity == "hard":
                return types.ThinkingConfig(
                    thinking_budget=8192,  # Some thinking
                    include_thoughts=True
                )
            # Otherwise no thinking for cost optimization

        return None

    async def submit_research(self, request: ResearchRequest) -> str:
        """
        Submit research job to Gemini.

        Note: Gemini doesn't have native background job queue like OpenAI,
        so we execute immediately and return completed results.
        """
        import uuid

        # Generate job ID
        job_id = f"gemini-{uuid.uuid4().hex[:16]}"

        # Store job as queued
        self.jobs[job_id] = {
            "status": "queued",
            "request": request,
            "created_at": datetime.now(timezone.utc),
            "model": self.get_model_name(request.model)
        }

        # Execute research immediately (Gemini is synchronous)
        await self._execute_research(job_id)

        return job_id

    async def _execute_research(self, job_id: str):
        """Execute research task with Gemini."""
        job_data = self.jobs[job_id]
        request = job_data["request"]

        max_retries = 3
        retry_delay = 1

        job_data["status"] = "in_progress"

        for attempt in range(max_retries):
            try:
                model = job_data["model"]

                # Determine task complexity (simple heuristic)
                prompt_length = len(request.prompt)
                if prompt_length < 200:
                    complexity = "easy"
                elif prompt_length > 1000 or "analyze" in request.prompt.lower() or "research" in request.prompt.lower():
                    complexity = "hard"
                else:
                    complexity = "medium"

                # Build configuration
                config_params = {}

                # Add thinking config for reasoning
                thinking_config = self._get_thinking_config(model, complexity)
                if thinking_config:
                    config_params["thinking_config"] = thinking_config

                # Add system instructions
                if request.system_message:
                    config_params["system_instruction"] = request.system_message

                # Add temperature if specified
                if request.temperature is not None:
                    config_params["temperature"] = request.temperature

                # Enable Google Search for web research (agentic capability)
                # This is Gemini's built-in grounding feature
                enable_search = any(tool.type == "web_search_preview" for tool in request.tools)
                if enable_search:
                    config_params["tools"] = [{"google_search": {}}]

                # Enable structured output for knowledge extraction (agentic capability)
                # Gemini can output JSON for downstream processing
                if request.metadata and request.metadata.get("structured_output"):
                    schema = request.metadata.get("response_schema")
                    if schema:
                        config_params["response_mime_type"] = "application/json"
                        config_params["response_schema"] = schema

                # Build content list
                contents = [request.prompt]

                # Handle file uploads (if document_ids provided)
                if request.document_ids:
                    # Note: document_ids should be File objects from upload_document
                    for doc_id in request.document_ids:
                        # Gemini expects file objects in contents
                        file_obj = self.client.files.get(name=doc_id)
                        contents.insert(0, file_obj)

                # Create config object
                config = types.GenerateContentConfig(**config_params) if config_params else None

                # Execute research with streaming for responsiveness
                response_parts = []
                thought_parts = []

                if config:
                    response_stream = self.client.models.generate_content_stream(
                        model=model,
                        contents=contents,
                        config=config
                    )
                else:
                    response_stream = self.client.models.generate_content_stream(
                        model=model,
                        contents=contents
                    )

                # Collect response
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

                # Combine response
                full_response = "".join(response_parts)
                thoughts_summary = "".join(thought_parts) if thought_parts else None

                # Get usage metadata (approximate since streaming doesn't return full usage)
                # For now, estimate tokens
                input_tokens = len(request.prompt.split()) * 1.3  # Rough estimate
                output_tokens = len(full_response.split()) * 1.3

                # Store completed job
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

            except Exception as e:
                # Retry on transient errors
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    print(f"Gemini error (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Final failure
                    job_data.update({
                        "status": "failed",
                        "error": str(e),
                        "completed_at": datetime.now(timezone.utc)
                    })
                    return

    async def get_status(self, job_id: str) -> ResearchResponse:
        """Get research job status."""
        if job_id not in self.jobs:
            raise ProviderError(
                message=f"Job {job_id} not found",
                provider="gemini"
            )

        job_data = self.jobs[job_id]

        # Build usage stats if available
        usage = None
        if "usage" in job_data:
            usage_data = job_data["usage"]
            usage = UsageStats(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
                reasoning_tokens=0,  # Gemini tracks this separately in thoughts
                cost=self._calculate_cost(
                    usage_data.get("input_tokens", 0),
                    usage_data.get("output_tokens", 0),
                    job_data["model"]
                )
            )

        # Build output in OpenAI-compatible format
        output = None
        if "output" in job_data:
            output = [{
                "type": "message",
                "content": [{
                    "type": "output_text",
                    "text": job_data["output"]
                }]
            }]

            # Add thoughts if available
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

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a research job."""
        if job_id not in self.jobs:
            return False

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

            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                # Default to application/octet-stream
                mime_type = "application/octet-stream"

            # Upload file
            file_obj = self.client.files.upload(
                file=path,
                config={"mime_type": mime_type} if mime_type else None
            )

            return file_obj.name

        except Exception as e:
            raise ProviderError(
                message=f"Failed to upload document: {str(e)}",
                provider="gemini",
                original_error=e
            )

    async def create_vector_store(self, name: str, file_ids: List[str]) -> VectorStore:
        """
        Create vector store (not natively supported by Gemini).

        Gemini uses the File API differently - files are passed directly in contents.
        We simulate vector stores by tracking file groups.
        """
        # Generate vector store ID
        import uuid
        vs_id = f"gemini-vs-{uuid.uuid4().hex[:16]}"

        # Store metadata
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
        """
        Wait for vector store ingestion.

        For Gemini, files are processed immediately, so this returns True.
        """
        # Verify all files exist
        if not hasattr(self, "vector_stores"):
            return False

        if vector_store_id not in self.vector_stores:
            return False

        vs_data = self.vector_stores[vector_store_id]

        # Check all files are accessible
        try:
            for file_id in vs_data["file_ids"]:
                file_obj = self.client.files.get(name=file_id)
                # If we get here, file exists and is ready
            return True
        except Exception:
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
