"""Research orchestration and coordination.

Provides the ResearchOrchestrator class that coordinates the complete research
workflow including:
- Research job submission with cost validation
- Document upload and vector store management
- Job completion processing and report generation
- Resource cleanup
- Temporal knowledge tracking (6.4)
- Context chaining between phases (6.4)

Instrumented with distributed tracing for observability (4.2 Auto-Generated Metadata).
"""

import json
import logging
import uuid
from typing import Optional, List, Dict, Any
from pathlib import Path
from ..providers.base import DeepResearchProvider, ResearchRequest, ToolConfig
from ..storage.base import StorageBackend
from ..formatting.converters import ReportConverter
from ..utils.prompt_security import PromptSanitizer
from .documents import DocumentManager
from .reports import ReportGenerator

# Observability infrastructure
from ..observability.metadata import MetadataEmitter
from ..observability.temporal_tracker import TemporalKnowledgeTracker, FindingType
from ..services.context_chainer import ContextChainer

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
        emitter: Optional[MetadataEmitter] = None,
        enable_temporal_tracking: bool = True,
    ):
        """
        Initialize research orchestrator.

        Args:
            provider: AI provider instance
            storage: Storage backend instance
            document_manager: Document management instance
            report_generator: Report generation instance
            system_message: Custom system message (optional)
            emitter: Optional MetadataEmitter for span tracking
            enable_temporal_tracking: Enable temporal knowledge tracking (default True)
        """
        self.provider = provider
        self.storage = storage
        self.document_manager = document_manager
        self.report_generator = report_generator
        self.system_message = system_message or self._load_default_system_message()

        # Observability: MetadataEmitter for span tracking
        self._emitter = emitter or MetadataEmitter()

        # Temporal knowledge tracking (6.4)
        self._enable_temporal = enable_temporal_tracking
        self._temporal_trackers: Dict[str, TemporalKnowledgeTracker] = {}
        self._context_chainer = ContextChainer()

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
        # Start observability span for research submission
        with self._emitter.operation(
            "research_submit",
            prompt=prompt[:500],
            attributes={"model": model, "cost_sensitive": cost_sensitive}
        ) as op:
            # SECURITY: Sanitize prompt before any processing
            if not skip_sanitization:
                sanitizer = PromptSanitizer()
                sanitization_result = sanitizer.sanitize(prompt)

                # Block high-risk prompts entirely
                if sanitization_result.risk_level == "high":
                    op.add_event("prompt_blocked", {"risk_level": "high", "patterns": sanitization_result.patterns_detected})
                    raise ValueError(
                        f"Prompt blocked due to high-risk patterns detected: "
                        f"{', '.join(sanitization_result.patterns_detected)}. "
                        f"Please rephrase your research query."
                    )

                # Use sanitized prompt (neutralizes medium-risk patterns)
                if sanitization_result.patterns_detected:
                    op.add_event("prompt_sanitized", {"patterns": sanitization_result.patterns_detected})
                prompt = sanitization_result.sanitized

            # CRITICAL: Validate budget BEFORE any API calls
            estimated_cost = get_cost_estimate(model)
            op.set_attribute("estimated_cost", estimated_cost)

            # Import cost safety manager for budget validation
            from ..experts.cost_safety import get_cost_safety_manager

            cost_safety = get_cost_safety_manager()

            # Create or use session for tracking
            tracking_session_id = session_id or f"research_{uuid.uuid4().hex[:8]}"
            op.set_attribute("session_id", tracking_session_id)

            # Check against global limits (daily/monthly)
            allowed, reason, needs_confirm = cost_safety.check_operation(
                session_id=tracking_session_id,
                operation_type="research_submit",
                estimated_cost=estimated_cost,
                require_confirmation=False  # CLI/API handles confirmation
            )

            if not allowed:
                op.add_event("budget_blocked", {"reason": reason})
                raise ValueError(f"Research blocked by cost safety: {reason}")

            # Check against explicit budget limit if provided
            if budget_limit is not None and estimated_cost > budget_limit:
                op.add_event("budget_exceeded", {"limit": budget_limit, "estimated": estimated_cost})
                raise ValueError(
                    f"Estimated cost ${estimated_cost:.2f} exceeds budget limit ${budget_limit:.2f}"
                )

            op.add_event("budget_validated", {"estimated_cost": estimated_cost})

            # Generate job ID
            job_id = str(uuid.uuid4())
            op.set_attribute("job_id", job_id)

            # Initialize temporal tracking for this job (6.4)
            if self._enable_temporal:
                tracker = TemporalKnowledgeTracker(job_id=job_id)
                self._temporal_trackers[job_id] = tracker
                self._emitter.set_temporal_tracker(tracker)
                op.add_event("temporal_tracking_enabled", {"job_id": job_id})

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
            documents_count = 0
            if documents:
                documents_count = len(documents)
                op.set_attribute("documents_count", documents_count)
                op.add_event("document_upload_start", {"count": documents_count})

                file_ids = await self.document_manager.upload_documents(documents, self.provider)

                if file_ids:
                    op.add_event("document_upload_complete", {"file_ids_count": len(file_ids)})
                    vector_store = await self.document_manager.create_vector_store(
                        f"deepr-{job_id}", file_ids, self.provider
                    )
                    vector_store_id = vector_store.id
                    self.active_vector_stores[job_id] = vector_store_id
                    op.set_attribute("vector_store_id", vector_store_id)
            # If vector_store_id provided but no documents, use the existing vector store
            # Don't track it for cleanup since we didn't create it
            elif vector_store_id:
                op.set_attribute("vector_store_id", vector_store_id)
                op.set_attribute("vector_store_existing", True)

            # Build tools configuration
            tools = self._build_tools(
                vector_store_id=vector_store_id,
                enable_web_search=enable_web_search,
                enable_code_interpreter=enable_code_interpreter and not cost_sensitive,
            )

            # Track enabled tools
            enabled_tools = [t.type for t in tools]
            op.set_attribute("tools_enabled", enabled_tools)

            # Use cost-sensitive model if requested
            original_model = model
            if cost_sensitive:
                if "o3" in model:
                    model = "o4-mini-deep-research"
                    op.add_event("model_downgraded", {"from": original_model, "to": model})

            # Set final model info
            op.set_model(model, self.provider.__class__.__name__)

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
            op.add_event("provider_submit_start", {"model": model})
            response_id = await self.provider.submit_research(request)
            op.add_event("provider_submit_complete", {"response_id": response_id})

            # Record cost in safety manager for tracking
            cost_safety.record_cost(
                session_id=tracking_session_id,
                operation_type="research_submit",
                actual_cost=estimated_cost,
                details=f"Job {response_id}: {prompt[:50]}..."
            )

            # Set final cost on span
            op.set_cost(estimated_cost)

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
        # Start observability span for completion processing
        with self._emitter.operation(
            "research_completion",
            attributes={"job_id": job_id, "append_references": append_references}
        ) as op:
            # Get job results from provider
            op.add_event("fetch_status_start")
            response = await self.provider.get_status(job_id)
            op.set_attribute("job_status", response.status)

            if response.status != "completed":
                op.add_event("job_not_completed", {"status": response.status})
                raise ValueError(f"Job {job_id} is not completed (status: {response.status})")

            op.add_event("fetch_status_complete", {"status": response.status})

            # Extract text from response
            raw_text = self.report_generator.extract_text_from_response(response)

            if not raw_text:
                op.add_event("no_content_found")
                raise ValueError(f"No content found in completed job {job_id}")

            # Track content size
            op.set_attribute("raw_text_length", len(raw_text))

            # Extract findings for temporal tracking (6.4)
            if self._enable_temporal and job_id in self._temporal_trackers:
                tracker = self._temporal_trackers[job_id]
                structured = self._context_chainer.structure_phase_output(
                    raw_output=raw_text,
                    phase=1,  # Single-phase research
                    tracker=tracker
                )
                op.add_event("temporal_findings_extracted", {
                    "finding_count": len(structured.key_findings),
                    "entity_count": len(structured.entities),
                    "open_questions": len(structured.open_questions)
                })
                self._emitter.set_temporal_tracker(tracker)

            # Extract metadata for title generation
            title = response.metadata.get("report_title", "Research Report") if response.metadata else "Research Report"
            op.set_attribute("report_title", title)

            # Optionally append references
            if append_references:
                references = ReportConverter.extract_references(raw_text)
                if references:
                    raw_text += "\n\n## References\n" + "\n".join(f"- {url}" for url in references)
                    op.add_event("references_appended", {"count": len(references)})

            # Generate all report formats
            op.add_event("report_generation_start", {"formats": output_formats or ["all"]})
            reports = await self.report_generator.generate_reports(
                text=raw_text,
                title=title,
                formats=output_formats,
            )
            op.add_event("report_generation_complete", {"formats_generated": list(reports.keys())})

            # Save reports to storage
            saved_formats = []
            for format_name, content in reports.items():
                content_type = self.storage.get_content_type(f"report.{format_name}")
                await self.storage.save_report(
                    job_id=job_id,
                    filename=f"report.{format_name}",
                    content=content,
                    content_type=content_type,
                    metadata={"title": title, "status": "completed"},
                )
                saved_formats.append(format_name)

            op.add_event("reports_saved", {"formats": saved_formats})
            op.set_attribute("formats_saved", saved_formats)

            # Clean up vector store if exists
            vector_store_id = self.active_vector_stores.get(job_id)
            if vector_store_id:
                op.add_event("vector_store_cleanup_start", {"vector_store_id": vector_store_id})
            await self._cleanup_vector_store(job_id)
            if vector_store_id:
                op.add_event("vector_store_cleanup_complete")

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
        with self._emitter.operation(
            "research_cancel",
            attributes={"job_id": job_id}
        ) as op:
            success = await self.provider.cancel_job(job_id)
            op.set_attribute("cancel_success", success)

            if success:
                op.add_event("job_cancelled")
                await self._cleanup_vector_store(job_id)
            else:
                op.add_event("cancel_failed")

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

    @property
    def trace(self) -> MetadataEmitter:
        """Get the MetadataEmitter for accessing trace data.

        Returns:
            MetadataEmitter instance with all recorded spans
        """
        return self._emitter

    def get_trace_summary(self) -> Dict[str, Any]:
        """Get a summary of traced operations.

        Returns:
            Dictionary with trace summary including:
            - trace_id: Unique trace identifier
            - total_cost: Sum of costs across all operations
            - cost_breakdown: Cost by operation type
            - timeline: List of operations in order
        """
        return {
            "trace_id": self._emitter.trace_context.trace_id,
            "total_cost": self._emitter.get_total_cost(),
            "cost_breakdown": self._emitter.get_cost_breakdown(),
            "timeline": self._emitter.get_timeline(),
        }

    def save_trace(self, path: Path):
        """Save the trace to a JSON file.

        Args:
            path: Path to save the trace
        """
        self._emitter.save_trace(path)

    def get_temporal_tracker(self, job_id: str) -> Optional[TemporalKnowledgeTracker]:
        """Get the temporal tracker for a specific job.

        Args:
            job_id: Job identifier

        Returns:
            TemporalKnowledgeTracker or None if not found/disabled
        """
        return self._temporal_trackers.get(job_id)

    def record_finding(
        self,
        job_id: str,
        text: str,
        phase: int = 1,
        confidence: float = 0.5,
        source: Optional[str] = None,
        finding_type: FindingType = FindingType.FACT,
    ):
        """Record a finding for temporal tracking.

        Args:
            job_id: Job identifier
            text: Finding text
            phase: Phase number (default 1)
            confidence: Confidence score (0-1)
            source: Source URL or reference
            finding_type: Type of finding
        """
        if job_id in self._temporal_trackers:
            self._temporal_trackers[job_id].record_finding(
                text=text,
                phase=phase,
                confidence=confidence,
                source=source,
                finding_type=finding_type,
            )

    def build_phase_context(
        self,
        job_id: str,
        current_phase: int,
        max_tokens: Optional[int] = None,
        focus_query: Optional[str] = None,
    ) -> str:
        """Build structured context from prior phases for context chaining.

        Args:
            job_id: Job identifier
            current_phase: Current phase number
            max_tokens: Maximum tokens for context
            focus_query: Optional query to focus context on

        Returns:
            Formatted context string for the next phase
        """
        tracker = self._temporal_trackers.get(job_id)
        if not tracker:
            return ""

        # Get findings organized by phase
        prior_phases = []
        for phase_num in range(1, current_phase):
            phase_findings = tracker.get_timeline(phase=phase_num)
            if phase_findings:
                from ..services.context_chainer import StructuredPhaseOutput, ExtractedFinding

                # Convert temporal findings to structured output
                key_findings = [
                    ExtractedFinding(
                        text=f.text,
                        confidence=f.confidence,
                        finding_type=f.finding_type,
                        source=f.source,
                        importance=f.confidence,  # Use confidence as proxy for importance
                    )
                    for f in phase_findings
                ]

                structured = StructuredPhaseOutput(
                    phase=phase_num,
                    key_findings=key_findings,
                    summary=f"Phase {phase_num} findings",
                    entities=[],  # Could extract from metadata
                    open_questions=[],
                    contradictions=[],
                    confidence_avg=sum(f.confidence for f in phase_findings) / len(phase_findings) if phase_findings else 0.5,
                )
                prior_phases.append(structured)

        if not prior_phases:
            return ""

        return self._context_chainer.build_structured_context(
            prior_phases=prior_phases,
            current_phase=current_phase,
            max_tokens=max_tokens,
            focus_query=focus_query,
        )
