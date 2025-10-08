"""OpenAI provider implementation for Deep Research."""

import os
import asyncio
from typing import Optional, List
from openai import AsyncOpenAI
from .base import (
    DeepResearchProvider,
    ResearchRequest,
    ResearchResponse,
    UsageStats,
    VectorStore,
    ProviderError,
)
from datetime import datetime, timezone


class OpenAIProvider(DeepResearchProvider):
    """OpenAI implementation of the Deep Research provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        model_mappings: Optional[dict] = None,
    ):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            base_url: Custom base URL (optional)
            organization: OpenAI organization ID (optional)
            model_mappings: Custom model name mappings (optional)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")

        self.client = AsyncOpenAI(
            api_key=self.api_key, base_url=base_url, organization=organization
        )

        # Default model mappings (can be overridden)
        self.model_mappings = model_mappings or {
            "o3-deep-research": "o3-deep-research-2025-06-26",
            "o4-mini-deep-research": "o4-mini-deep-research",
            "o3": "o3-deep-research-2025-06-26",
            "o4-mini": "o4-mini-deep-research",
        }

    def get_model_name(self, model_key: str) -> str:
        """Map generic model key to OpenAI model name."""
        return self.model_mappings.get(model_key, model_key)

    async def submit_research(self, request: ResearchRequest) -> str:
        """Submit research job to OpenAI."""
        try:
            # Map model name
            model = self.get_model_name(request.model)

            # Convert tools to OpenAI format
            tools = []
            for tool in request.tools:
                tool_dict = {"type": tool.type}
                if tool.type == "file_search" and tool.vector_store_ids:
                    tool_dict["vector_store_ids"] = tool.vector_store_ids
                elif tool.type == "code_interpreter" and tool.container:
                    tool_dict["container"] = tool.container
                tools.append(tool_dict)

            # Build request payload
            payload = {
                "model": model,
                "input": [
                    {
                        "role": "developer",
                        "content": [{"type": "input_text", "text": request.system_message}],
                    },
                    {"role": "user", "content": [{"type": "input_text", "text": request.prompt}]},
                ],
                "reasoning": {"summary": "auto"},
                "tools": tools if tools else None,
                "tool_choice": request.tool_choice,
                "metadata": request.metadata,
                "store": request.store,
                "background": request.background,
            }

            # Add webhook if provided
            if request.webhook_url:
                payload["extra_headers"] = {"OpenAI-Hook-URL": request.webhook_url}

            # Add temperature if specified
            if request.temperature is not None:
                payload["temperature"] = request.temperature

            # Submit request
            response = await self.client.responses.create(**payload)
            return response.id

        except Exception as e:
            raise ProviderError(
                message=f"Failed to submit research: {str(e)}",
                provider="openai",
                original_error=e,
            )

    async def get_status(self, job_id: str) -> ResearchResponse:
        """Get research job status from OpenAI."""
        try:
            response = await self.client.responses.retrieve(job_id)

            # Parse usage stats
            usage = None
            if hasattr(response, "usage") and response.usage:
                input_tokens = getattr(response.usage, "input_tokens", 0)
                output_tokens = getattr(response.usage, "output_tokens", 0)
                model = getattr(response, "model", "o4-mini-deep-research-2025-06-26")

                usage = UsageStats(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=getattr(response.usage, "total_tokens", 0),
                    reasoning_tokens=getattr(response.usage, "reasoning_tokens", 0),
                    cost=UsageStats.calculate_cost(input_tokens, output_tokens, model),
                )

            # Parse output
            output = None
            if hasattr(response, "output") and response.output:
                output = [
                    {
                        "type": block.type,
                        "content": [
                            {"type": item.type, "text": getattr(item, "text", "")}
                            for item in block.content
                        ]
                        if hasattr(block, "content") and block.content
                        else [],
                    }
                    for block in response.output
                ]

            # Parse timestamps
            created_at = None
            if hasattr(response, "created_at") and response.created_at:
                created_at = datetime.fromtimestamp(response.created_at, tz=timezone.utc)

            completed_at = None
            if hasattr(response, "completed_at") and response.completed_at:
                completed_at = datetime.fromtimestamp(response.completed_at, tz=timezone.utc)

            return ResearchResponse(
                id=response.id,
                status=response.status,
                created_at=created_at,
                completed_at=completed_at,
                model=getattr(response, "model", None),
                output=output,
                usage=usage,
                metadata=getattr(response, "metadata", None),
                error=getattr(response, "error", None),
            )

        except Exception as e:
            raise ProviderError(
                message=f"Failed to get status: {str(e)}", provider="openai", original_error=e
            )

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel OpenAI research job."""
        try:
            await self.client.responses.cancel(job_id)
            return True
        except Exception as e:
            raise ProviderError(
                message=f"Failed to cancel job: {str(e)}", provider="openai", original_error=e
            )

    async def upload_document(self, file_path: str, purpose: str = "assistants") -> str:
        """Upload document to OpenAI."""
        try:
            with open(file_path, "rb") as f:
                file_obj = await self.client.files.create(file=f, purpose=purpose)
            return file_obj.id
        except Exception as e:
            raise ProviderError(
                message=f"Failed to upload document: {str(e)}",
                provider="openai",
                original_error=e,
            )

    async def create_vector_store(self, name: str, file_ids: List[str]) -> VectorStore:
        """Create vector store in OpenAI."""
        try:
            # Create vector store
            vs = await self.client.vector_stores.create(name=name)

            # Attach files
            for file_id in file_ids:
                await self.client.vector_stores.files.create(
                    vector_store_id=vs.id, file_id=file_id
                )

            return VectorStore(id=vs.id, name=name, file_ids=file_ids)

        except Exception as e:
            raise ProviderError(
                message=f"Failed to create vector store: {str(e)}",
                provider="openai",
                original_error=e,
            )

    async def wait_for_vector_store(
        self, vector_store_id: str, timeout: int = 900, poll_interval: float = 2.0
    ) -> bool:
        """Wait for OpenAI vector store ingestion."""
        try:
            start_time = asyncio.get_event_loop().time()

            while True:
                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    raise TimeoutError(
                        f"Vector store ingestion timeout after {timeout} seconds"
                    )

                # Get file statuses
                listing = await self.client.vector_stores.files.list(
                    vector_store_id=vector_store_id
                )

                # Check if all files are completed
                all_completed = all(
                    getattr(item, "status", "completed") == "completed" for item in listing.data
                )

                if all_completed:
                    return True

                # Wait before next poll
                await asyncio.sleep(poll_interval)

        except TimeoutError:
            raise
        except Exception as e:
            raise ProviderError(
                message=f"Failed to wait for vector store: {str(e)}",
                provider="openai",
                original_error=e,
            )

    async def delete_vector_store(self, vector_store_id: str) -> bool:
        """Delete OpenAI vector store."""
        try:
            await self.client.vector_stores.delete(vector_store_id)
            return True
        except Exception as e:
            raise ProviderError(
                message=f"Failed to delete vector store: {str(e)}",
                provider="openai",
                original_error=e,
            )
