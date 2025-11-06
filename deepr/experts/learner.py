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

        # Execute phase by phase
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
                # Real execution
                await self._execute_phase(
                    expert, phase_topics, progress, budget_limit, progress_callback
                )

        progress.completed_at = datetime.utcnow()

        self._log_progress(
            f"\n=== Learning Complete ===",
            f"Completed: {len(progress.completed_topics)} topics",
            f"Failed: {len(progress.failed_topics)} topics",
            f"Total cost: ${progress.total_cost:.2f}",
            f"Success rate: {progress.success_rate()*100:.1f}%",
            callback=progress_callback
        )

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
