"""Azure OpenAI provider implementation for Deep Research."""

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

from azure.identity.aio import DefaultAzureCredential
from openai import APIError as OpenAIAPIError
from openai import AsyncAzureOpenAI

from .base import (
    DeepResearchProvider,
    ProviderError,
    ResearchRequest,
    ResearchResponse,
    UsageStats,
    VectorStore,
)


class AzureProvider(DeepResearchProvider):
    """Azure OpenAI implementation of the Deep Research provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_version: str = "2024-10-01-preview",
        use_managed_identity: bool = False,
        deployment_mappings: Optional[dict[str, str]] = None,
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

            async def get_token():
                token = await self._credential.get_token("https://cognitiveservices.azure.com/.default")
                return token.token

            self.client = AsyncAzureOpenAI(
                azure_endpoint=self.endpoint,
                api_version=self.api_version,
                azure_ad_token_provider=get_token,
            )
        else:
            # Use API key authentication
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
        try:
            # Map model to deployment name
            deployment = self.get_model_name(request.model)

            # Convert tools to Azure format (same as OpenAI)
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
            if request.webhook_url:
                payload["extra_headers"] = {"OpenAI-Hook-URL": request.webhook_url}

            # Add temperature if specified
            if request.temperature is not None:
                payload["temperature"] = request.temperature

            # Submit request
            response = await self.client.responses.create(**payload)
            return response.id

        except OpenAIAPIError as e:
            raise ProviderError(
                message=f"Failed to submit research to Azure: {e!s}",
                provider="azure",
                original_error=e,
            )

    async def get_status(self, job_id: str) -> ResearchResponse:
        """Get research job status from Azure OpenAI."""
        try:
            response = await self.client.responses.retrieve(job_id)

            # Parse usage stats
            usage = None
            if hasattr(response, "usage") and response.usage:
                input_tokens = getattr(response.usage, "input_tokens", 0)
                output_tokens = getattr(response.usage, "output_tokens", 0)
                model = getattr(response, "model", None)
                usage = UsageStats(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=getattr(response.usage, "total_tokens", 0),
                    reasoning_tokens=getattr(response.usage, "reasoning_tokens", 0),
                )
                usage.cost = UsageStats.calculate_cost(input_tokens, output_tokens, model)

            # Parse output
            output = None
            if hasattr(response, "output") and response.output:
                output = [
                    {
                        "type": block.type,
                        "content": [{"type": item.type, "text": getattr(item, "text", "")} for item in block.content]
                        if hasattr(block, "content")
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

        except OpenAIAPIError as e:
            raise ProviderError(
                message=f"Failed to get status from Azure: {e!s}",
                provider="azure",
                original_error=e,
            )

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
            )

    async def upload_document(self, file_path: str, purpose: str = "assistants") -> str:
        """Upload document to Azure OpenAI."""
        try:
            with open(file_path, "rb") as f:
                file_obj = await self.client.files.create(file=f, purpose=purpose)
            return file_obj.id
        except (OpenAIAPIError, OSError) as e:
            raise ProviderError(
                message=f"Failed to upload document to Azure: {e!s}",
                provider="azure",
                original_error=e,
            )

    async def create_vector_store(self, name: str, file_ids: list[str]) -> VectorStore:
        """Create vector store in Azure OpenAI."""
        try:
            # Create vector store
            vs = await self.client.vector_stores.create(name=name)

            # Attach files
            for file_id in file_ids:
                await self.client.vector_stores.files.create(vector_store_id=vs.id, file_id=file_id)

            return VectorStore(id=vs.id, name=name, file_ids=file_ids)

        except OpenAIAPIError as e:
            raise ProviderError(
                message=f"Failed to create vector store on Azure: {e!s}",
                provider="azure",
                original_error=e,
            )

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
            )

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
            )
