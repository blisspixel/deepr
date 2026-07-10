"""Azure OpenAI provider implementation for Deep Research."""

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from azure.identity.aio import DefaultAzureCredential
from openai import APIConnectionError, APITimeoutError, AsyncAzureOpenAI, RateLimitError
from openai import APIError as OpenAIAPIError

from .base import (
    DeepResearchProvider,
    ProviderError,
    ResearchRequest,
    ResearchResponse,
    UsageStats,
    VectorStore,
    get_usage_detail_int,
    get_usage_int,
)

logger = logging.getLogger(__name__)


class AzureProvider(DeepResearchProvider):
    """Azure OpenAI implementation of the Deep Research provider."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        api_version: str = "2024-10-01-preview",
        use_managed_identity: bool = False,
        deployment_mappings: dict[str, str] | None = None,
    ):
        """
        Initialize Azure OpenAI provider.

        Args:
            api_key: Azure OpenAI API key (defaults to AZURE_OPENAI_KEY env var)
            endpoint: Azure OpenAI endpoint (defaults to AZURE_OPENAI_ENDPOINT env var)
            api_version: Azure OpenAI API version
            use_managed_identity: Use Azure Managed Identity instead of API key
            deployment_mappings: Map model keys to deployment names
        """
        self.endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        if not self.endpoint:
            raise ValueError("Azure OpenAI endpoint is required")

        self.api_version = api_version
        self.use_managed_identity = use_managed_identity

        # Initialize client
        if use_managed_identity:
            # Use Azure Managed Identity for authentication
            # Store credential as instance variable to prevent garbage collection
            self._credential = DefaultAzureCredential()
            # Note: token provider setup for async client

            async def get_token() -> str:
                token = await self._credential.get_token("https://cognitiveservices.azure.com/.default")
                return str(token.token)

            self.client = AsyncAzureOpenAI(
                azure_endpoint=self.endpoint,
                api_version=self.api_version,
                azure_ad_token_provider=get_token,
            )
        else:
            # Use API key authentication
            if api_key in ("***", ""):
                api_key = None
            self.api_key = api_key or os.getenv("AZURE_OPENAI_KEY")
            if not self.api_key:
                raise ValueError("Azure OpenAI API key is required when not using managed identity")

            self.client = AsyncAzureOpenAI(
                api_key=self.api_key, azure_endpoint=self.endpoint, api_version=self.api_version
            )

        # Deployment name mappings (Azure uses deployment names instead of model names)
        self.deployment_mappings = deployment_mappings or {
            "o3-deep-research": os.getenv("AZURE_DEPLOYMENT_O3", "o3-deep-research"),
            "o4-mini-deep-research": os.getenv("AZURE_DEPLOYMENT_O4_MINI", "o4-mini-deep-research"),
            "o3": os.getenv("AZURE_DEPLOYMENT_O3", "o3-deep-research"),
            "o4-mini": os.getenv("AZURE_DEPLOYMENT_O4_MINI", "o4-mini-deep-research"),
        }

    def get_model_name(self, model_key: str) -> str:
        """Map generic model key to Azure deployment name."""
        return self.deployment_mappings.get(model_key, model_key)

    async def submit_research(self, request: ResearchRequest) -> str:
        """Submit research job to Azure OpenAI."""
        # Map model to deployment name
        deployment = self.get_model_name(request.model)

        # Convert tools to Azure format (same as OpenAI)
        tools = []
        for tool in request.tools:
            tool_dict: dict[str, Any] = {"type": tool.type}
            if tool.type == "file_search" and tool.vector_store_ids:
                tool_dict["vector_store_ids"] = tool.vector_store_ids
            elif tool.type == "code_interpreter" and tool.container:
                tool_dict["container"] = tool.container
            tools.append(tool_dict)

        # Build request payload
        payload: dict[str, Any] = {
            "model": deployment,  # Use deployment name for Azure
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
        extra_headers = {}
        if request.webhook_url:
            extra_headers["OpenAI-Hook-URL"] = request.webhook_url
        extra_headers["Idempotency-Key"] = request.idempotency_key or f"deepr-provider-{uuid4().hex}"
        payload["extra_headers"] = extra_headers

        # Add temperature if specified
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        # Retry transient failures the same way the OpenAI provider does
        # - Azure throttles aggressively and a single 429 shouldn't fail
        # a whole job. Authentication / invalid-request errors are still
        # raised immediately as ProviderError.
        max_retries = 3
        retry_delay = 1.0
        for attempt in range(max_retries):
            try:
                response = await self.client.responses.create(**payload)
                return str(response.id)
            except (RateLimitError, APIConnectionError, APITimeoutError) as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2**attempt)
                    logger.warning(
                        "Azure transient error (attempt %d/%d): %s. Retrying in %ss.",
                        attempt + 1,
                        max_retries,
                        e,
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise ProviderError(
                    message=f"Azure failed after {max_retries} retries: {e}",
                    provider="azure",
                    original_error=e,
                ) from e
            except OpenAIAPIError as e:
                raise ProviderError(
                    message=f"Failed to submit research to Azure: {e!s}",
                    provider="azure",
                    original_error=e,
                ) from e

        raise ProviderError(message="Failed to submit research after all retries", provider="azure")

    async def get_status(self, job_id: str) -> ResearchResponse:
        """Get research job status from Azure OpenAI."""
        try:
            response = await self.client.responses.retrieve(job_id)

            # Parse usage stats
            usage = None
            if hasattr(response, "usage") and response.usage:
                input_tokens = get_usage_int(response.usage, "input_tokens")
                output_tokens = get_usage_int(response.usage, "output_tokens")
                cached_input_tokens = get_usage_detail_int(
                    response.usage,
                    "input_tokens_details",
                    "cached_tokens",
                )
                reasoning_tokens = get_usage_detail_int(
                    response.usage,
                    "output_tokens_details",
                    "reasoning_tokens",
                ) or get_usage_int(response.usage, "reasoning_tokens")
                # Azure occasionally omits ``response.model``. The
                # registry's calculate_cost walks substring matches and
                # raises ``TypeError: argument of type 'NoneType' is not
                # iterable`` on None, crashing get_status. Default to a
                # safe deployment-known fallback.
                model = getattr(response, "model", None) or "o4-mini-deep-research"
                usage = UsageStats(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=get_usage_int(response.usage, "total_tokens"),
                    reasoning_tokens=reasoning_tokens,
                    cached_input_tokens=cached_input_tokens,
                )
                usage.cost = UsageStats.calculate_cost_with_cached_input(
                    input_tokens,
                    output_tokens,
                    model,
                    cached_input_tokens=cached_input_tokens,
                )

            # Parse output
            output = None
            if hasattr(response, "output") and response.output:
                output = [
                    {
                        "type": block.type,
                        "content": [
                            {"type": item.type, "text": getattr(item, "text", "")} for item in (block.content or [])
                        ]
                        if hasattr(block, "content")
                        else [],
                    }
                    for block in response.output or []
                ]

            # Parse timestamps
            created_at = None
            if hasattr(response, "created_at") and response.created_at:
                created_at = datetime.fromtimestamp(response.created_at, tz=UTC)

            completed_at = None
            if hasattr(response, "completed_at") and response.completed_at:
                completed_at = datetime.fromtimestamp(response.completed_at, tz=UTC)

            return ResearchResponse(
                id=response.id,
                # Responses API status vocabulary is a superset of the
                # ResearchResponse contract Literal.
                status=response.status,  # type: ignore[arg-type]
                created_at=created_at,
                completed_at=completed_at,
                model=getattr(response, "model", None),
                output=output,
                usage=usage,
                metadata=getattr(response, "metadata", None),
                error=getattr(response, "error", None),
            )

        except OpenAIAPIError as e:
            raise ProviderError(
                message=f"Failed to get status from Azure: {e!s}",
                provider="azure",
                original_error=e,
            ) from e

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel Azure OpenAI research job."""
        try:
            await self.client.responses.cancel(job_id)
            return True
        except OpenAIAPIError as e:
            raise ProviderError(
                message=f"Failed to cancel job on Azure: {e!s}",
                provider="azure",
                original_error=e,
            ) from e

    async def upload_document(self, file_path: str, purpose: str = "assistants") -> str:
        """Upload document to Azure OpenAI."""
        try:
            with open(file_path, "rb") as f:
                file_obj = await self.client.files.create(file=f, purpose=purpose)  # type: ignore[arg-type]
            return str(file_obj.id)
        except (OpenAIAPIError, OSError) as e:
            raise ProviderError(
                message=f"Failed to upload document to Azure: {e!s}",
                provider="azure",
                original_error=e,
            ) from e

    async def delete_document(self, file_id: str) -> bool:
        """Delete an uploaded Azure OpenAI file."""
        try:
            await self.client.files.delete(file_id)
            return True
        except OpenAIAPIError as e:
            raise ProviderError(
                message=f"Failed to delete document from Azure: {e!s}",
                provider="azure",
                original_error=e,
            ) from e

    async def create_vector_store(self, name: str, file_ids: list[str]) -> VectorStore:
        """Create vector store in Azure OpenAI."""
        try:
            # Create vector store
            vs = await self.client.vector_stores.create(
                name=name,
                expires_after={"anchor": "last_active_at", "days": 1},
            )

            # Attach files
            for file_id in file_ids:
                await self.client.vector_stores.files.create(vector_store_id=vs.id, file_id=file_id)

            return VectorStore(id=vs.id, name=name, file_ids=file_ids)

        except OpenAIAPIError as e:
            raise ProviderError(
                message=f"Failed to create vector store on Azure: {e!s}",
                provider="azure",
                original_error=e,
            ) from e

    async def wait_for_vector_store(self, vector_store_id: str, timeout: int = 900, poll_interval: float = 2.0) -> bool:
        """Wait for Azure OpenAI vector store ingestion."""
        try:
            start_time = asyncio.get_event_loop().time()

            while True:
                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    raise TimeoutError(f"Vector store ingestion timeout after {timeout} seconds")

                # Get file statuses
                listing = await self.client.vector_stores.files.list(vector_store_id=vector_store_id)

                # Check if all files are completed
                all_completed = all(getattr(item, "status", "completed") == "completed" for item in listing.data)

                if all_completed:
                    return True

                # Wait before next poll
                await asyncio.sleep(poll_interval)

        except TimeoutError:
            raise
        except OpenAIAPIError as e:
            raise ProviderError(
                message=f"Failed to wait for vector store on Azure: {e!s}",
                provider="azure",
                original_error=e,
            ) from e

    async def list_vector_stores(self, limit: int = 100) -> list[VectorStore]:
        """List Azure OpenAI vector stores.

        The base class declared this abstract; previously
        ``AzureProvider`` did not implement it, which meant the class
        could not be instantiated at all (``TypeError: Can't instantiate
        abstract class``). Every public Azure entrypoint went through
        ``create_provider("azure")`` which would have crashed at
        construction time.
        """
        try:
            stores: list[VectorStore] = []
            response = await self.client.vector_stores.list(limit=limit)
            for vs in getattr(response, "data", []):
                files_response = await self.client.vector_stores.files.list(vector_store_id=vs.id)
                file_ids = [f.id for f in getattr(files_response, "data", [])]
                stores.append(VectorStore(id=vs.id, name=getattr(vs, "name", vs.id), file_ids=file_ids))
            return stores
        except OpenAIAPIError as e:
            raise ProviderError(
                message=f"Failed to list vector stores on Azure: {e!s}",
                provider="azure",
                original_error=e,
            ) from e

    async def delete_vector_store(self, vector_store_id: str) -> bool:
        """Delete Azure OpenAI vector store."""
        try:
            await self.client.vector_stores.delete(vector_store_id)
            return True
        except OpenAIAPIError as e:
            raise ProviderError(
                message=f"Failed to delete vector store on Azure: {e!s}",
                provider="azure",
                original_error=e,
            ) from e
