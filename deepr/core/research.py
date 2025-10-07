"""Research orchestration and coordination."""

import json
import uuid
from typing import Optional, List, Dict, Any
from pathlib import Path
from ..providers.base import DeepResearchProvider, ResearchRequest, ToolConfig
from ..storage.base import StorageBackend
from ..formatting.converters import ReportConverter
from .documents import DocumentManager
from .reports import ReportGenerator


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

        except Exception:
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
        webhook_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        cost_sensitive: bool = False,
        enable_web_search: bool = True,
        enable_code_interpreter: bool = True,
        custom_system_message: Optional[str] = None,
    ) -> str:
        """
        Submit a research job.

        Args:
            prompt: Research prompt/question
            model: Model to use (default: o3-deep-research)
            documents: List of document file paths to include
            webhook_url: Webhook URL for completion notification
            metadata: Additional metadata for the job
            cost_sensitive: Use lighter model and fewer resources
            enable_web_search: Enable web search tool
            enable_code_interpreter: Enable code interpreter tool
            custom_system_message: Override system message for this job

        Returns:
            Job ID for tracking

        Raises:
            Exception: If submission fails
        """
        # Generate job ID
        job_id = str(uuid.uuid4())

        # Prepare metadata
        job_metadata = metadata or {}
        job_metadata["job_id"] = job_id
        job_metadata["original_prompt"] = prompt

        # Handle documents if provided
        vector_store_id = None
        if documents:
            file_ids = await self.document_manager.upload_documents(documents, self.provider)

            if file_ids:
                vector_store = await self.document_manager.create_vector_store(
                    f"deepr-{job_id}", file_ids, self.provider
                )
                vector_store_id = vector_store.id
                self.active_vector_stores[job_id] = vector_store_id

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
                # Log but don't fail on cleanup errors
                print(f"Warning: Failed to cleanup vector store {vector_store_id}: {e}")

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
