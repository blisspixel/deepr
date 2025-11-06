"""Autonomous learning executor for domain experts.

This module executes learning curricula by autonomously researching topics
and integrating findings into expert knowledge bases.
"""

import asyncio
from dataclasses import dataclass
from typing import List, Optional, Callable
from datetime import datetime
import click

from deepr.config import AppConfig
from deepr.experts.curriculum import LearningCurriculum, LearningTopic, CurriculumGenerator
from deepr.experts.profile import ExpertProfile, ExpertStore
from deepr.core.research import ResearchOrchestrator
from deepr.core.documents import DocumentManager
from deepr.core.reports import ReportGenerator
from deepr.providers import create_provider
from deepr.storage import create_storage


@dataclass
class LearningProgress:
    """Track progress of autonomous learning."""

    curriculum: LearningCurriculum
    completed_topics: List[str]
    failed_topics: List[str]
    total_cost: float
    started_at: datetime
    completed_at: Optional[datetime] = None

    def is_complete(self) -> bool:
        """Check if all topics are completed or failed."""
        total_topics = len(self.curriculum.topics)
        processed = len(self.completed_topics) + len(self.failed_topics)
        return processed >= total_topics

    def success_rate(self) -> float:
        """Calculate success rate (0.0-1.0)."""
        total = len(self.completed_topics) + len(self.failed_topics)
        if total == 0:
            return 0.0
        return len(self.completed_topics) / total


class AutonomousLearner:
    """Executes learning curricula autonomously with budget protection."""

    def __init__(self, config: AppConfig):
        self.config = config
        # Use direct research execution instead of broken ResearchAPI queue
        # Create all required dependencies using factory functions
        openai_api_key = config.get("openai_api_key")
        provider = create_provider("openai", api_key=openai_api_key)
        storage = create_storage("local", base_path=config.get("storage_path", "output"))

        # Create document manager and report generator
        document_manager = DocumentManager()
        report_generator = ReportGenerator()

        # Initialize research orchestrator with all dependencies
        self.research = ResearchOrchestrator(
            provider=provider,
            storage=storage,
            document_manager=document_manager,
            report_generator=report_generator
        )

    async def execute_curriculum(
        self,
        expert: ExpertProfile,
        curriculum: LearningCurriculum,
        budget_limit: float,
        dry_run: bool = False,
        progress_callback: Optional[Callable] = None
    ) -> LearningProgress:
        """Execute a learning curriculum autonomously.

        Args:
            expert: Expert profile to update
            curriculum: Learning curriculum to execute
            budget_limit: Maximum spending allowed
            dry_run: If True, don't actually execute (for testing)
            progress_callback: Optional callback for progress updates

        Returns:
            LearningProgress tracking execution
        """
        progress = LearningProgress(
            curriculum=curriculum,
            completed_topics=[],
            failed_topics=[],
            total_cost=0.0,
            started_at=datetime.utcnow()
        )

        # Get execution order (respects dependencies)
        generator = CurriculumGenerator(self.config)
        phases = generator.get_execution_order(curriculum)

        self._log_progress(
            f"Starting autonomous learning for {expert.name}",
            f"Curriculum: {len(curriculum.topics)} topics in {len(phases)} phases",
            f"Budget limit: ${budget_limit:.2f}",
            callback=progress_callback
        )

        # Execute phase by phase and collect job IDs
        all_job_ids = []

        for phase_num, phase_topics in enumerate(phases, 1):
            self._log_progress(
                f"\n=== Phase {phase_num}/{len(phases)} ===",
                f"Topics: {', '.join(t.title for t in phase_topics)}",
                callback=progress_callback
            )

            # Check budget before starting phase
            if progress.total_cost >= budget_limit:
                self._log_progress(
                    "[WARNING] Budget limit reached, stopping",
                    callback=progress_callback
                )
                break

            # Execute topics in parallel (they have no dependencies on each other)
            if dry_run:
                # Simulate execution
                await self._simulate_phase_execution(
                    phase_topics, progress, budget_limit, progress_callback
                )
            else:
                # Real execution - returns job IDs
                job_ids = await self._execute_phase(
                    expert, phase_topics, progress, budget_limit, progress_callback
                )
                if job_ids:
                    all_job_ids.extend(job_ids)

        progress.completed_at = datetime.utcnow()

        self._log_progress(
            f"\n=== Learning Complete ===",
            f"Completed: {len(progress.completed_topics)} topics",
            f"Failed: {len(progress.failed_topics)} topics",
            f"Total cost: ${progress.total_cost:.2f}",
            f"Success rate: {progress.success_rate()*100:.1f}%",
            callback=progress_callback
        )

        # Poll for completion and integrate reports
        if not dry_run and all_job_ids:
            await self._poll_and_integrate_reports(expert, all_job_ids, progress_callback)

        return progress

    async def _execute_phase(
        self,
        expert: ExpertProfile,
        topics: List[LearningTopic],
        progress: LearningProgress,
        budget_limit: float,
        callback: Optional[Callable]
    ):
        """Execute a single phase (topics in parallel)."""

        # Submit all research jobs in parallel
        job_mapping = {}  # topic_title -> job_id

        for topic in topics:
            # Check budget before each submission
            if progress.total_cost + topic.estimated_cost > budget_limit:
                self._log_progress(
                    f"[SKIP] {topic.title} - would exceed budget",
                    callback=callback
                )
                progress.failed_topics.append(topic.title)
                continue

            try:
                self._log_progress(
                    f"[RESEARCH] {topic.title}",
                    f"  Prompt: {topic.research_prompt[:80]}...",
                    f"  Est. cost: ${topic.estimated_cost:.2f}, time: {topic.estimated_minutes}min",
                    callback=callback
                )

                # Submit research job directly (synchronous execution)
                # Use campaign mode for deep research topics
                response_id = await self.research.submit_research(
                    prompt=topic.research_prompt,
                    model="o4-mini-deep-research",  # Deep research model
                    vector_store_id=expert.vector_store_id,  # Add to expert's knowledge
                    enable_web_search=True,
                    enable_code_interpreter=False,
                )

                job_mapping[topic.title] = {
                    "job_id": response_id,
                    "cost": 0.0,  # Will be updated when complete
                    "success": True
                }

                # Mark as completed immediately (synchronous execution)
                progress.completed_topics.append(topic.title)

                self._log_progress(
                    f"  [DONE] Research ID: {response_id}",
                    callback=callback
                )

            except Exception as e:
                self._log_progress(
                    f"[ERROR] Failed to submit {topic.title}: {e}",
                    callback=callback
                )
                progress.failed_topics.append(topic.title)

        # Jobs completed synchronously - no need to poll
        if not job_mapping:
            return

        self._log_progress(
            f"\nPhase complete: {len(job_mapping)} research topics processed",
            callback=callback
        )

        # Update expert profile with new research
        self._update_expert_profile(expert, progress, job_mapping)

        # Return job IDs for polling
        return [j["job_id"] for j in job_mapping.values() if j["success"]]

    async def _poll_and_integrate_reports(
        self,
        expert: ExpertProfile,
        job_ids: List[str],
        callback: Optional[Callable] = None
    ):
        """Poll for job completion and integrate reports into expert's knowledge."""
        from datetime import datetime

        if not job_ids:
            return

        self._log_progress(
            "\n" + "="*70,
            "  Waiting for Research Completion",
            "="*70,
            f"Jobs: {len(job_ids)}",
            "This may take 5-20 minutes per job...",
            "",
            callback=callback
        )

        pending = set(job_ids)
        completed = set()
        failed = set()
        total_cost = 0.0
        start_time = datetime.now()

        while pending:
            self._log_progress(
                f"[{datetime.now().strftime('%H:%M:%S')}] Checking status...",
                f"Pending: {len(pending)}, Completed: {len(completed)}, Failed: {len(failed)}",
                callback=callback
            )

            for job_id in list(pending):
                try:
                    response = await self.research.provider.get_status(job_id)

                    if response.status == "completed":
                        self._log_progress(
                            f"  [OK] {job_id[:20]}... COMPLETED",
                            callback=callback
                        )
                        pending.remove(job_id)
                        completed.add(job_id)

                        if response.usage:
                            cost = response.usage.cost
                            total_cost += cost
                            self._log_progress(
                                f"       Cost: ${cost:.4f}",
                                callback=callback
                            )

                    elif response.status in ["failed", "cancelled"]:
                        self._log_progress(
                            f"  [X] {job_id[:20]}... {response.status.upper()}",
                            callback=callback
                        )
                        pending.remove(job_id)
                        failed.add(job_id)

                    elif response.status in ["in_progress", "queued"]:
                        # Still running, check next time
                        pass

                except Exception as e:
                    self._log_progress(
                        f"  [!] {job_id[:20]}... Error: {e}",
                        callback=callback
                    )

            if pending:
                elapsed = (datetime.now() - start_time).total_seconds() / 60
                self._log_progress(
                    f"Elapsed: {elapsed:.1f} min, waiting 30s...",
                    "",
                    callback=callback
                )
                await asyncio.sleep(30)

        # All jobs complete
        elapsed_total = (datetime.now() - start_time).total_seconds() / 60
        self._log_progress(
            "\n" + "="*70,
            "  Research Complete",
            "="*70,
            f"Completed: {len(completed)}/{len(job_ids)}",
            f"Failed: {len(failed)}/{len(job_ids)}",
            f"Total cost: ${total_cost:.2f}",
            f"Total time: {elapsed_total:.1f} minutes",
            "",
            callback=callback
        )

        # Download and upload reports to vector store
        if completed:
            await self._integrate_reports(expert, list(completed), callback)

    async def _integrate_reports(
        self,
        expert: ExpertProfile,
        job_ids: List[str],
        callback: Optional[Callable] = None
    ):
        """Download reports and upload to expert's vector store."""
        import tempfile
        from pathlib import Path

        self._log_progress(
            "="*70,
            "  Integrating Knowledge",
            "="*70,
            callback=callback
        )

        uploaded = 0
        for i, job_id in enumerate(job_ids, 1):
            temp_file = None
            try:
                self._log_progress(
                    f"{i}/{len(job_ids)}: {job_id[:20]}...",
                    callback=callback
                )

                # Get report from OpenAI
                response = await self.research.provider.get_status(job_id)

                # Extract text
                raw_text = self.research.report_generator.extract_text_from_response(response)

                if not raw_text:
                    self._log_progress(
                        "  [SKIP] No content found",
                        callback=callback
                    )
                    continue

                # Save to temporary file
                filename = f"research_{job_id[:12]}.md"
                with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
                    f.write(raw_text)
                    temp_file = f.name

                # Upload file to OpenAI
                file_id = await self.research.provider.upload_document(temp_file, purpose="assistants")

                # Attach file to vector store
                await self.research.provider.client.vector_stores.files.create(
                    vector_store_id=expert.vector_store_id,
                    file_id=file_id
                )

                uploaded += 1
                self._log_progress(
                    f"  [OK] Uploaded as {filename} (file_id: {file_id[:20]}...)",
                    callback=callback
                )

            except Exception as e:
                self._log_progress(
                    f"  [ERROR] {str(e)}",
                    callback=callback
                )
            finally:
                # Clean up temp file
                if temp_file and Path(temp_file).exists():
                    Path(temp_file).unlink()

        # Update expert metadata
        expert.total_documents += uploaded
        expert.last_knowledge_refresh = datetime.utcnow()

        store = ExpertStore()
        store.save(expert)

        self._log_progress(
            "",
            "="*70,
            f"Knowledge Integration Complete: {uploaded} documents added",
            "="*70,
            "",
            f"Expert ready! Documents: {expert.total_documents}",
            f"Use: deepr expert chat \"{expert.name}\"",
            "",
            callback=callback
        )

    async def _simulate_phase_execution(
        self,
        topics: List[LearningTopic],
        progress: LearningProgress,
        budget_limit: float,
        callback: Optional[Callable]
    ):
        """Simulate phase execution for dry runs."""

        for topic in topics:
            # Check budget
            if progress.total_cost + topic.estimated_cost > budget_limit:
                self._log_progress(
                    f"[SKIP] {topic.title} - would exceed budget",
                    callback=callback
                )
                progress.failed_topics.append(topic.title)
                continue

            self._log_progress(
                f"[DRY RUN] {topic.title}",
                f"  Est. cost: ${topic.estimated_cost:.2f}",
                callback=callback
            )

            # Simulate success
            progress.completed_topics.append(topic.title)
            progress.total_cost += topic.estimated_cost

            # Simulate delay
            await asyncio.sleep(0.1)

    def _update_expert_profile(
        self,
        expert: ExpertProfile,
        progress: LearningProgress,
        job_mapping: dict
    ):
        """Update expert profile with learning progress."""

        # Track research jobs
        for topic_title in progress.completed_topics:
            if topic_title in job_mapping:
                job_id = job_mapping[topic_title]["job_id"]
                if job_id not in expert.research_jobs:
                    expert.research_jobs.append(job_id)

        # Update costs
        expert.total_research_cost += progress.total_cost

        # Update knowledge cutoff to now
        expert.last_knowledge_refresh = datetime.utcnow()
        if not expert.knowledge_cutoff_date:
            expert.knowledge_cutoff_date = datetime.utcnow()

        # Save updated profile
        store = ExpertStore()
        store.save(expert)

    def _log_progress(self, *messages, callback: Optional[Callable] = None):
        """Log progress messages."""
        for msg in messages:
            click.echo(msg)
            if callback:
                callback(msg)
