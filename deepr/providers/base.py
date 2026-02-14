"""Abstract base classes for Deep Research providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional


@dataclass
class ToolConfig:
    """Configuration for research tools."""

    type: Literal["web_search_preview", "code_interpreter", "file_search", "google_search", "deep_research"]
    vector_store_ids: Optional[list[str]] = None
    container: Optional[dict[str, Any]] = None


@dataclass
class ResearchRequest:
    """Request object for research submission."""

    prompt: str
    model: str
    system_message: str
    tools: list[ToolConfig] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    webhook_url: Optional[str] = None
    document_ids: Optional[list[str]] = None
    temperature: Optional[float] = None
    tool_choice: str = "auto"
    store: bool = True
    background: bool = True
    # GPT-5 specific parameters (Responses API)
    reasoning_effort: Optional[Literal["minimal", "low", "medium", "high"]] = None
    text_verbosity: Optional[Literal["low", "medium", "high"]] = None
    previous_response_id: Optional[str] = None  # For reasoning persistence


@dataclass
class UsageStats:
    """Token usage statistics."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0  # Calculated cost in USD

    @classmethod
    def calculate_cost(cls, input_tokens: int, output_tokens: int, model: str) -> float:
        """
        Calculate cost based on token usage and model.

        Pricing is sourced from the model registry (providers/registry.py).
        """
        from .registry import get_token_pricing

        prices = get_token_pricing(model)

        input_cost = (input_tokens / 1_000_000) * prices["input"]
        output_cost = (output_tokens / 1_000_000) * prices["output"]

        return round(input_cost + output_cost, 6)


@dataclass
class ResearchResponse:
    """Response object from research operations."""

    id: str
    status: Literal["queued", "in_progress", "completed", "failed", "cancelled", "expired"]
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    model: Optional[str] = None
    output: Optional[list[dict[str, Any]]] = None
    usage: Optional[UsageStats] = None
    metadata: Optional[dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class VectorStore:
    """Vector store information."""

    id: str
    name: str
    file_ids: list[str] = field(default_factory=list)


class DeepResearchProvider(ABC):
    """
    Abstract base class for Deep Research providers.

    Implements the interface that all providers (OpenAI, Azure) must support.
    """

    @abstractmethod
    async def submit_research(self, request: ResearchRequest) -> str:
        """
        Submit a research job for background processing.

        Args:
            request: Research request configuration

        Returns:
            Job ID for tracking

        Raises:
            ProviderError: If submission fails
        """
        pass

    @abstractmethod
    async def get_status(self, job_id: str) -> ResearchResponse:
        """
        Get the current status and results of a research job.

        Args:
            job_id: The job identifier

        Returns:
            Current job status and results (if completed)

        Raises:
            ProviderError: If retrieval fails
        """
        pass

    @abstractmethod
    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running or queued research job.

        Args:
            job_id: The job identifier

        Returns:
            True if cancellation was successful

        Raises:
            ProviderError: If cancellation fails
        """
        pass

    @abstractmethod
    async def upload_document(self, file_path: str, purpose: str = "assistants") -> str:
        """
        Upload a document for use in research.

        Args:
            file_path: Path to the document file
            purpose: Purpose of the upload (default: "assistants")

        Returns:
            File ID for reference

        Raises:
            ProviderError: If upload fails
        """
        pass

    @abstractmethod
    async def create_vector_store(self, name: str, file_ids: list[str]) -> VectorStore:
        """
        Create a vector store with the given files.

        Args:
            name: Name for the vector store
            file_ids: List of file IDs to include

        Returns:
            Vector store information

        Raises:
            ProviderError: If creation fails
        """
        pass

    @abstractmethod
    async def wait_for_vector_store(self, vector_store_id: str, timeout: int = 900, poll_interval: float = 2.0) -> bool:
        """
        Wait for vector store ingestion to complete.

        Args:
            vector_store_id: The vector store identifier
            timeout: Maximum seconds to wait
            poll_interval: Seconds between status checks

        Returns:
            True if ingestion completed successfully

        Raises:
            TimeoutError: If ingestion doesn't complete within timeout
            ProviderError: If ingestion fails
        """
        pass

    @abstractmethod
    async def list_vector_stores(self, limit: int = 100) -> list[VectorStore]:
        """
        List all vector stores.

        Args:
            limit: Maximum number of vector stores to return

        Returns:
            List of vector store information

        Raises:
            ProviderError: If listing fails
        """
        pass

    @abstractmethod
    async def delete_vector_store(self, vector_store_id: str) -> bool:
        """
        Delete a vector store.

        Args:
            vector_store_id: The vector store identifier

        Returns:
            True if deletion was successful

        Raises:
            ProviderError: If deletion fails
        """
        pass

    @abstractmethod
    def get_model_name(self, model_key: str) -> str:
        """
        Map a generic model key to the provider-specific model/deployment name.

        Args:
            model_key: Generic model identifier (e.g., "o3-deep-research")

        Returns:
            Provider-specific model or deployment name

        Examples:
            OpenAI: "o3-deep-research" -> "o3-deep-research"
            Azure: "o3-deep-research" -> "my-o3-deployment"
        """
        pass


class ProviderError(Exception):
    """Base exception for provider-related errors."""

    def __init__(self, message: str, provider: str, original_error: Optional[Exception] = None):
        self.message = message
        self.provider = provider
        self.original_error = original_error
        super().__init__(self.message)
