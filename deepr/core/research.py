"""Research orchestration and coordination."""

import json
import logging
import uuid
from typing import Optional, List, Dict, Any
from pathlib import Path
from ..providers.base import DeepResearchProvider, ResearchRequest, ToolConfig
from ..storage.base import StorageBackend
from ..formatting.converters import ReportConverter
from ..utils.prompt_security import PromptSanitizer, SanitizationResult
from .documents import DocumentManager
from .reports import ReportGenerator


# Cost estimates sourced from the model registry (single source of truth).
# get_cost_estimate() looks up cost_per_query from providers/registry.py.
from ..providers.registry import get_cost_estimate, MODEL_CAPABILITIES

DEFAULT_COST_ESTIMATE = 0.20  # Fallback for unknown models

# Derived from registry for backward compatibility (used by tests).
MODEL_COST_ESTIMATES = {
    cap.model: cap.cost_per_query
    for cap in MODEL_CAPABILITIES.values()
}

logger = logging.getLogger(__name__)


class ResearchOrchestrator:
    """
    Orchestrates the complete research workflow.

    Responsibilities:
    - Coordinate research submissions
    - Manage document uploads and vector stores
    - Handle job completion and report generation
    - Clean up resources
    """

    def __init__(
        self,
        provider: DeepResearchProvider,
        storage: StorageBackend,
        document_manager: DocumentManager,
        report_generator: ReportGenerator,
        system_message: Optional[str] = None,
    ):
        """
        Initialize research orchestrator.

        Args:
            provider: AI provider instance
            storage: Storage backend instance
            document_manager: Document management instance
            report_generator: Report generation instance
            system_message: Custom system message (optional)
        """
        self.provider = provider
        self.storage = storage
        self.document_manager = document_manager
        self.report_generator = report_generator
        self.system_message = system_message or self._load_default_system_message()

        # Track active vector stores for cleanup
        self.active_vector_stores: Dict[str, str] = {}  # job_id -> vector_store_id

    def _load_default_system_message(self) -> str:
        """Load system message from file or return default."""
        try:
            # Try to load from system_message.json
            paths = [
                Path("system_message.json"),
                Path(__file__).parent.parent.parent / "system_message.json",
            ]

            for path in paths:
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return data.get("message", self._get_fallback_message())

        except (OSError, json.JSONDecodeError, KeyError):
            pass

        return self._get_fallback_message()

    @staticmethod
    def _get_fallback_message() -> str:
        """Get fallback system message."""
        return (
            "You are a professional researcher producing structured, insight-driven reports. "
            "Do not include inline links, parenthetical citations, numeric bracket citations, "
            "or footnote markers in the main body. Use clear, concise Markdown formatting. "
            "Be direct, detailed, and professional."
        )

    async def submit_research(
        self,
        prompt: str,
        model: str = "o3-deep-research",
        documents: Optional[List[str]] = None,
        vector_store_id: Optional[str] = None,
        webhook_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        cost_sensitive: bool = False,
        enable_web_search: bool = True,
        enable_code_interpreter: bool = True,
        custom_system_message: Optional[str] = None,
        budget_limit: Optional[float] = None,
        session_id: Optional[str] = None,
        skip_sanitization: bool = False,
    ) -> str:
        """
        Submit a research job.

        Args:
            prompt: Research prompt/question
            model: Model to use (default: o3-deep-research)
            documents: List of document file paths to include
            vector_store_id: Existing vector store ID to use (for experts)
            webhook_url: Webhook URL for completion notification
            metadata: Additional metadata for the job
            cost_sensitive: Use lighter model and fewer resources
            enable_web_search: Enable web search tool
            enable_code_interpreter: Enable code interpreter tool
            custom_system_message: Override system message for this job
            budget_limit: Optional budget limit for this job (validated against cost safety)
            session_id: Optional session ID for cost tracking
            skip_sanitization: Skip prompt sanitization (for trusted internal prompts)

        Returns:
            Job ID for tracking

        Raises:
            Exception: If submission fails
            ValueError: If budget would be exceeded or prompt is unsafe
        """
        # SECURITY: Sanitize prompt before any processing
        if not skip_sanitization:
            sanitizer = PromptSanitizer()
            sanitization_result = sanitizer.sanitize(prompt)
            
            # Block high-risk prompts entirely
            if sanitization_result.risk_level == "high":
                raise ValueError(
                    f"Prompt blocked due to high-risk patterns detected: "
                    f"{', '.join(sanitization_result.patterns_detected)}. "
                    f"Please rephrase your research query."
                )
            
            # Use sanitized prompt (neutralizes medium-risk patterns)
            prompt = sanitization_result.sanitized
        
        # CRITICAL: Validate budget BEFORE any API calls
        estimated_cost = get_cost_estimate(model)
        
        # Import cost safety manager for budget validation
        from ..experts.cost_safety import get_cost_safety_manager
        
        cost_safety = get_cost_safety_manager()
        
        # Create or use session for tracking
        tracking_session_id = session_id or f"research_{uuid.uuid4().hex[:8]}"
        
        # Check against global limits (daily/monthly)
        allowed, reason, needs_confirm = cost_safety.check_operation(
            session_id=tracking_session_id,
            operation_type="research_submit",
            estimated_cost=estimated_cost,
            require_confirmation=False  # CLI/API handles confirmation
        )
        
        if not allowed:
            raise ValueError(f"Research blocked by cost safety: {reason}")
        
        # Check against explicit budget limit if provided
        if budget_limit is not None and estimated_cost > budget_limit:
            raise ValueError(
                f"Estimated cost ${estimated_cost:.2f} exceeds budget limit ${budget_limit:.2f}"
            )
        
        # Generate job ID
        job_id = str(uuid.uuid4())

        # Prepare metadata
        job_metadata = metadata or {}
        job_metadata["job_id"] = job_id
        # OpenAI metadata fields have 512 char limit - validate prompt length
        if len(prompt) > 300:
            raise ValueError(
                f"Research prompt too long ({len(prompt)} chars). "
                f"Must be under 300 characters for API compatibility. "
                f"Please use a more concise prompt."
            )
        job_metadata["original_prompt"] = prompt

        # Use provided vector_store_id or create one from documents
        if documents:
            file_ids = await self.document_manager.upload_documents(documents, self.provider)

            if file_ids:
                vector_store = await self.document_manager.create_vector_store(
                    f"deepr-{job_id}", file_ids, self.provider
                )
                vector_store_id = vector_store.id
                self.active_vector_stores[job_id] = vector_store_id
        # If vector_store_id provided but no documents, use the existing vector store
        # Don't track it for cleanup since we didn't create it

        # Build tools configuration
        tools = self._build_tools(
            vector_store_id=vector_store_id,
            enable_web_search=enable_web_search,
            enable_code_interpreter=enable_code_interpreter and not cost_sensitive,
        )

        # Use cost-sensitive model if requested
        if cost_sensitive:
            if "o3" in model:
                model = "o4-mini-deep-research"

        # Build research request
        request = ResearchRequest(
            prompt=self._enhance_prompt(prompt, documents is not None),
            model=model,
            system_message=custom_system_message or self.system_message,
            tools=tools,
            metadata=job_metadata,
            webhook_url=webhook_url,
            tool_choice="required" if vector_store_id else "auto",
        )

        # Submit to provider
        response_id = await self.provider.submit_research(request)

        # Record cost in safety manager for tracking
        cost_safety.record_cost(
            session_id=tracking_session_id,
            operation_type="research_submit",
            actual_cost=estimated_cost,
            details=f"Job {response_id}: {prompt[:50]}..."
        )

        return response_id

    def _enhance_prompt(self, prompt: str, has_documents: bool) -> str:
        """Enhance prompt with citation instructions."""
        prefix = (
            "Use ONLY the attached document(s) as source material. "
            if has_documents
            else ""
        )

        citation_instruction = (
            "Do NOT include inline citations, links, footnotes, bracketed numbers, "
            "or parenthetical sources in the body text. "
        )

        return f"{prefix}{citation_instruction}\n\n{prompt}"

    def _build_tools(
        self,
        vector_store_id: Optional[str] = None,
        enable_web_search: bool = True,
        enable_code_interpreter: bool = True,
    ) -> List[ToolConfig]:
        """Build tools configuration based on requirements."""
        tools = []

        # Add file search if documents provided
        if vector_store_id:
            tools.append(
                ToolConfig(type="file_search", vector_store_ids=[vector_store_id])
            )

        # Add web search
        if enable_web_search:
            tools.append(ToolConfig(type="web_search_preview"))

        # Add code interpreter
        if enable_code_interpreter:
            tools.append(
                ToolConfig(type="code_interpreter", container={"type": "auto"})
            )

        return tools

    async def process_completion(
        self,
        job_id: str,
        append_references: bool = False,
        output_formats: Optional[List[str]] = None,
    ):
        """
        Process completed research job.

        Args:
            job_id: The job identifier
            append_references: Whether to append extracted references
            output_formats: List of formats to generate (default: all)

        Raises:
            Exception: If processing fails
        """
        # Get job results from provider
        response = await self.provider.get_status(job_id)

        if response.status != "completed":
            raise ValueError(f"Job {job_id} is not completed (status: {response.status})")

        # Extract text from response
        raw_text = self.report_generator.extract_text_from_response(response)

        if not raw_text:
            raise ValueError(f"No content found in completed job {job_id}")

        # Extract metadata for title generation
        title = response.metadata.get("report_title", "Research Report") if response.metadata else "Research Report"

        # Optionally append references
        if append_references:
            references = ReportConverter.extract_references(raw_text)
            if references:
                raw_text += "\n\n## References\n" + "\n".join(f"- {url}" for url in references)

        # Generate all report formats
        reports = await self.report_generator.generate_reports(
            text=raw_text,
            title=title,
            formats=output_formats,
        )

        # Save reports to storage
        for format_name, content in reports.items():
            content_type = self.storage.get_content_type(f"report.{format_name}")
            await self.storage.save_report(
                job_id=job_id,
                filename=f"report.{format_name}",
                content=content,
                content_type=content_type,
                metadata={"title": title, "status": "completed"},
            )

        # Clean up vector store if exists
        await self._cleanup_vector_store(job_id)

    async def _cleanup_vector_store(self, job_id: str):
        """Clean up vector store for a job."""
        vector_store_id = self.active_vector_stores.pop(job_id, None)
        if vector_store_id:
            try:
                await self.provider.delete_vector_store(vector_store_id)
            except Exception as e:
                # Provider cleanup may fail for many reasons (network, auth, already
                # deleted, etc.); log and continue -- this is fire-and-forget.
                logger.warning("Failed to cleanup vector store %s: %s", vector_store_id, e)

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running job.

        Args:
            job_id: The job identifier

        Returns:
            True if cancellation was successful
        """
        success = await self.provider.cancel_job(job_id)
        if success:
            await self._cleanup_vector_store(job_id)
        return success

    async def get_job_status(self, job_id: str):
        """
        Get current job status.

        Args:
            job_id: The job identifier

        Returns:
            ResearchResponse with current status
        """
        return await self.provider.get_status(job_id)
