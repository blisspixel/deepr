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
from deepr.services.research_api import ResearchAPI


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
        self.research_api = ResearchAPI(config)

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

                # Submit research job
                job_id = await self.research_api.submit_research(
                    prompt=topic.research_prompt,
                    mode="focus",  # Focused research for specific topics
                    vector_store_id=expert.vector_store_id  # Add to expert's knowledge
                )

                job_mapping[topic.title] = job_id

                self._log_progress(
                    f"  Job ID: {job_id}",
                    callback=callback
                )

            except Exception as e:
                self._log_progress(
                    f"[ERROR] Failed to submit {topic.title}: {e}",
                    callback=callback
                )
                progress.failed_topics.append(topic.title)

        # Wait for all jobs to complete
        if not job_mapping:
            return

        self._log_progress(
            f"\nWaiting for {len(job_mapping)} research jobs to complete...",
            callback=callback
        )

        # Poll for completion
        completed_jobs = {}
        timeout_seconds = max(t.estimated_minutes for t in topics) * 60 * 2  # 2x estimated time
        start_time = datetime.utcnow()

        while len(completed_jobs) < len(job_mapping):
            # Check timeout
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed > timeout_seconds:
                self._log_progress(
                    f"[WARNING] Timeout waiting for jobs, stopping",
                    callback=callback
                )
                break

            # Check each pending job
            for topic_title, job_id in job_mapping.items():
                if topic_title in completed_jobs:
                    continue

                try:
                    status = await self.research_api.get_job_status(job_id)

                    if status["status"] == "completed":
                        # Get result and cost
                        result = await self.research_api.get_job_result(job_id)
                        cost = result.get("cost", 0.0)

                        completed_jobs[topic_title] = {
                            "job_id": job_id,
                            "cost": cost,
                            "success": True
                        }

                        progress.completed_topics.append(topic_title)
                        progress.total_cost += cost

                        self._log_progress(
                            f"[DONE] {topic_title} - ${cost:.2f}",
                            callback=callback
                        )

                    elif status["status"] == "failed":
                        completed_jobs[topic_title] = {
                            "job_id": job_id,
                            "success": False
                        }
                        progress.failed_topics.append(topic_title)

                        self._log_progress(
                            f"[FAILED] {topic_title}",
                            callback=callback
                        )

                except Exception as e:
                    self._log_progress(
                        f"[ERROR] Checking {topic_title}: {e}",
                        callback=callback
                    )

            # Sleep between polls
            await asyncio.sleep(30)

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
