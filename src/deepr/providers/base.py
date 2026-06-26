"""Abstract base classes for Deep Research providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class ToolConfig:
    """Configuration for research tools."""

    type: Literal["web_search_preview", "code_interpreter", "file_search", "google_search", "deep_research"]
    vector_store_ids: list[str] | None = None
    container: dict[str, Any] | None = None


@dataclass
class ResearchRequest:
    """Request object for research submission."""

    prompt: str
    model: str
    system_message: str
    tools: list[ToolConfig] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    webhook_url: str | None = None
    document_ids: list[str] | None = None
    temperature: float | None = None
    tool_choice: str = "auto"
    store: bool = True
    background: bool = True
    # GPT-5 specific parameters (Responses API)
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None
    text_verbosity: Literal["low", "medium", "high"] | None = None
    previous_response_id: str | None = None  # For reasoning persistence
    # Multi-agent parameters (Grok 4.20 multi-agent)
    agent_count: int | None = None  # Number of parallel agents (4-16)
    per_agent_budget: float | None = None  # Max cost per agent in USD
    # Trace correlation
    trace_id: str = ""  # Trace ID for distributed tracing across agent boundaries


@dataclass
class UsageStats:
    """Token usage statistics."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cached_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cost: float = 0.0  # Calculated cost in USD

    @classmethod
    def calculate_cost(cls, input_tokens: int, output_tokens: int, model: str) -> float:
        """
        Calculate cost based on token usage and model.

        Pricing is sourced from the model registry (providers/registry.py).
        Passing input_tokens lets tiered-pricing models (Gemini 3.x Pro
        above 200K input tokens) settle at the rate the provider actually
        bills instead of the base rate.
        """
        from .registry import get_token_pricing

        prices = get_token_pricing(model, input_tokens=input_tokens)

        input_cost = (input_tokens / 1_000_000) * prices["input"]
        output_cost = (output_tokens / 1_000_000) * prices["output"]

        return round(input_cost + output_cost, 6)

    @classmethod
    def calculate_cost_with_cached_input(
        cls,
        input_tokens: int,
        output_tokens: int,
        model: str,
        *,
        cached_input_tokens: int = 0,
    ) -> float:
        """Calculate cost when a provider reports discounted cached input."""
        from .registry import get_cached_input_pricing, get_token_pricing

        normalized_input = max(int(input_tokens), 0)
        normalized_output = max(int(output_tokens), 0)
        normalized_cached = min(max(int(cached_input_tokens), 0), normalized_input)
        non_cached_input = normalized_input - normalized_cached

        prices = get_token_pricing(model, input_tokens=normalized_input)
        cached_input_rate = get_cached_input_pricing(model, input_tokens=normalized_input)
        if cached_input_rate is None:
            cached_input_rate = prices["input"]

        input_cost = (non_cached_input / 1_000_000) * prices["input"]
        cached_input_cost = (normalized_cached / 1_000_000) * cached_input_rate
        output_cost = (normalized_output / 1_000_000) * prices["output"]

        return round(input_cost + cached_input_cost + output_cost, 6)


def coerce_usage_int(value: Any) -> int:
    """Convert provider SDK usage fields to non-negative integers."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(int(value), 0)
    return 0


def get_usage_int(usage: Any, field: str) -> int:
    """Read a top-level usage integer from a provider SDK object."""
    return coerce_usage_int(getattr(usage, field, 0))


def get_usage_detail_int(usage: Any, detail_field: str, field: str) -> int:
    """Read a nested usage detail integer from a provider SDK object."""
    detail = getattr(usage, detail_field, None)
    if detail is None:
        return 0
    return coerce_usage_int(getattr(detail, field, 0))


@dataclass
class ResearchResponse:
    """Response object from research operations."""

    id: str
    status: Literal["queued", "in_progress", "completed", "failed", "cancelled", "expired"]
    created_at: datetime | None = None
    completed_at: datetime | None = None
    model: str | None = None
    output: list[dict[str, Any]] | None = None
    usage: UsageStats | None = None
    metadata: dict[str, Any] | None = None
    error: str | None = None


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
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError


class ProviderError(Exception):
    """Base exception for provider-related errors.

    Carries the agent-classification envelope (category / retryable /
    retry_after) so a caller can decide whether to back off and retry, fall
    back to another provider, or stop and escalate - without parsing the
    message. Mirrors the shape of deepr.core.errors.DeeprError.to_dict().
    """

    def __init__(
        self,
        message: str,
        provider: str,
        original_error: Exception | None = None,
        *,
        category: str | None = None,
        retryable: bool | None = None,
        retry_after: int | None = None,
    ):
        self.message = message
        self.provider = provider
        self.original_error = original_error

        # Auto-classify from the wrapped SDK exception when the caller did
        # not set the envelope explicitly. This means every existing
        # `raise ProviderError(..., original_error=e)` across all adapters
        # gets correct category/retryable for free, with no per-site edits.
        if original_error is not None and (category is None or retryable is None or retry_after is None):
            auto_category, auto_retryable, auto_retry_after = classify_provider_exception(original_error)
            category = auto_category if category is None else category
            retryable = auto_retryable if retryable is None else retryable
            retry_after = auto_retry_after if retry_after is None else retry_after

        self.category = category if category is not None else "provider"
        self.retryable = retryable if retryable is not None else False
        self.retry_after = retry_after
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the agent-error envelope (RFC 9457 / agent pattern)."""
        payload: dict[str, Any] = {
            "error": True,
            "error_code": "PROVIDER_ERROR",
            "category": self.category,
            "retryable": self.retryable,
            "message": self.message,
            "details": {"provider": self.provider},
        }
        if self.retry_after is not None:
            payload["retry_after"] = self.retry_after
        return payload


def classify_provider_exception(exc: Exception) -> tuple[str, bool, int | None]:
    """Classify a raw provider-SDK exception into (category, retryable, retry_after).

    Uses the exception's class name so it works across provider SDKs
    (openai, anthropic, google-genai, xai, azure) without importing each.
    Transient failures (rate limit, timeout, connection, unavailable) are
    retryable; authentication is its own non-retryable category.
    """
    name = type(exc).__name__.lower()
    retry_after_attr = getattr(exc, "retry_after", None)
    retry_after = retry_after_attr if isinstance(retry_after_attr, int) else None

    if "ratelimit" in name:
        return ("provider", True, retry_after)
    if "timeout" in name or "connection" in name or "unavailable" in name or "serviceunavailable" in name:
        return ("provider", True, retry_after)
    if "authentication" in name or "permission" in name or "apikey" in name:
        return ("auth", False, None)
    return ("provider", False, retry_after)
