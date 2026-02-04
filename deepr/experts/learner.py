"""Autonomous learning executor for domain experts.

This module executes learning curricula by autonomously researching topics
and integrating findings into expert knowledge bases.
"""

import asyncio
from dataclasses import dataclass
from typing import List, Optional, Callable
from datetime import datetime, timezone
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
    """Executes learning curricula autonomously with budget protection.
    
    Safety features:
    - Hard budget caps that cannot be bypassed
    - Session-level cost tracking with alerts
    - Circuit breaker for repeated failures
    - Audit logging of all costs
    """

    def __init__(self, config):
        self.config = config
        # Use direct research execution instead of broken ResearchAPI queue
        # Create all required dependencies using factory functions
        if isinstance(config, dict):
            openai_api_key = config.get("openai_api_key")
            storage_path = config.get("storage_path", "output")
        else:
            # AppConfig object
            openai_api_key = config.provider.openai_api_key
            storage_path = config.storage.local_path

        provider = create_provider("openai", api_key=openai_api_key)
        storage = create_storage("local", base_path=storage_path)

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
        
        # Cost safety manager for defensive budget controls
        from deepr.experts.cost_safety import get_cost_safety_manager
        self.cost_safety = get_cost_safety_manager()

    async def execute_curriculum(
        self,
        expert: ExpertProfile,
        curriculum: LearningCurriculum,
        budget_limit: float,
        dry_run: bool = False,
        progress_callback: Optional[Callable] = None,
        resume: bool = False
    ) -> LearningProgress:
        """Execute a learning curriculum autonomously using parallel approach.
        
        Optimized workflow:
        1. Submit deep research jobs FIRST (async, 5-20 min each)
        2. While waiting, scrape/acquire sources (parallel)
        3. Poll for research completion and integrate

        Args:
            expert: Expert profile to update
            curriculum: Learning curriculum to execute
            budget_limit: Maximum spending allowed
            dry_run: If True, don't actually execute (for testing)
            progress_callback: Optional callback for progress updates
            resume: If True, check for and resume from saved progress

        Returns:
            LearningProgress tracking execution
        """
        import uuid
        from deepr.experts.cost_safety import estimate_curriculum_cost, format_cost_warning
        
        # Check for saved progress if resuming
        saved_progress = None
        if resume:
            saved_progress = self.load_learning_progress(expert.name)
            if saved_progress:
                self._log_progress(
                    "",
                    "="*70,
                    "  Resuming from Saved Progress",
                    "="*70,
                    f"Paused at: {saved_progress.get('paused_at', 'unknown')}",
                    f"Completed: {len(saved_progress.get('completed_topics', []))} topics",
                    f"Remaining: {len(saved_progress.get('remaining_topics', []))} topics",
                    f"Cost so far: ${saved_progress.get('total_cost_so_far', 0):.2f}",
                    "",
                    callback=progress_callback
                )
            else:
                self._log_progress(
                    "No saved progress found - starting fresh",
                    callback=progress_callback
                )
        
        # Create cost tracking session
        session_id = f"learn_{expert.name}_{uuid.uuid4().hex[:8]}"
        session = self.cost_safety.create_session(
            session_id=session_id,
            session_type="learning",
            budget_limit=budget_limit
        )
        
        # Initialize progress - restore from saved if resuming
        if saved_progress:
            progress = LearningProgress(
                curriculum=curriculum,
                completed_topics=saved_progress.get('completed_topics', []),
                failed_topics=saved_progress.get('failed_topics', []),
                total_cost=saved_progress.get('total_cost_so_far', 0.0),
                started_at=datetime.fromisoformat(saved_progress.get('started_at', datetime.now(timezone.utc).isoformat()))
            )
            # Update session with prior cost
            session.total_cost = progress.total_cost
            
            # Rebuild curriculum with only remaining topics
            remaining_topic_titles = {t['title'] for t in saved_progress.get('remaining_topics', [])}
            curriculum.topics = [t for t in curriculum.topics if t.title in remaining_topic_titles]
        else:
            progress = LearningProgress(
                curriculum=curriculum,
                completed_topics=[],
                failed_topics=[],
                total_cost=0.0,
                started_at=datetime.now(timezone.utc)
            )

        # Get execution order (respects dependencies)
        generator = CurriculumGenerator(self.config)
        phases = generator.get_execution_order(curriculum)
        
        # Pre-flight cost estimate
        deep_count = sum(1 for t in curriculum.topics if t.research_mode == "campaign")
        quick_count = sum(1 for t in curriculum.topics if t.research_mode == "focus")
        docs_count = sum(1 for t in curriculum.topics if t.research_type == "documentation")
        
        cost_estimate = estimate_curriculum_cost(
            topic_count=len(curriculum.topics),
            deep_research_count=deep_count,
            quick_research_count=quick_count,
            docs_count=docs_count
        )

        self._log_progress(
            f"Starting autonomous learning for {expert.name}",
            f"Curriculum: {len(curriculum.topics)} topics in {len(phases)} phases",
            f"Budget limit: ${budget_limit:.2f}" if budget_limit is not None else "Budget limit: unlimited",
            format_cost_warning(cost_estimate["expected_cost"], budget_limit),
            callback=progress_callback
        )
        
        # Check if estimated cost exceeds budget
        if cost_estimate["expected_cost"] > budget_limit:
            self._log_progress(
                f"Estimated cost ${cost_estimate['expected_cost']:.2f} exceeds budget ${budget_limit:.2f}",
                "Consider reducing topic count or using --dry-run to preview",
                callback=progress_callback
            )

        if dry_run:
            # Simulate execution
            for phase_num, phase_topics in enumerate(phases, 1):
                await self._simulate_phase_execution(
                    phase_topics, progress, budget_limit, progress_callback
                )
            progress.completed_at = datetime.now(timezone.utc)
            self.cost_safety.close_session(session_id)
            return progress

        try:
            # STEP 1: Submit all deep research jobs FIRST (they're async, take 5-20 min)
            self._log_progress(
                "",
                "Step 1: Submitting Deep Research Jobs",
                "",
                callback=progress_callback
            )
            
            all_job_ids = []
            for phase_num, phase_topics in enumerate(phases, 1):
                # Check budget before starting phase using cost safety manager
                can_proceed, reason = session.can_proceed()
                if not can_proceed:
                    self._log_progress(
                        f"Budget check failed: {reason}",
                        callback=progress_callback
                    )
                    break

                self._log_progress(
                    f"Phase {phase_num}/{len(phases)}: {', '.join(t.title for t in phase_topics)}",
                    callback=progress_callback
                )
                
                # Submit jobs (non-blocking)
                job_ids = await self._submit_research_jobs(
                    expert, phase_topics, progress, session, progress_callback
                )
                if job_ids:
                    all_job_ids.extend(job_ids)

            self._log_progress(
                f"Submitted {len(all_job_ids)} research jobs (running in background)",
                callback=progress_callback
            )

            # STEP 2: While research runs, acquire sources (scraping)
            self._log_progress(
                "",
                "Step 2: Acquiring Sources",
                "",
                callback=progress_callback
            )
            await self._acquire_sources(expert, curriculum, progress_callback)

            # STEP 3: Poll for research completion and integrate
            self._log_progress(
                "",
                "Step 3: Waiting for Research Completion",
                "",
                callback=progress_callback
            )
            
            if all_job_ids:
                await self._poll_and_integrate_reports(expert, all_job_ids, session, progress_callback)

            progress.completed_at = datetime.now(timezone.utc)
            
            # Get final cost from session
            progress.total_cost = session.total_cost

            self._log_progress(
                "",
                "Learning Complete",
                f"Completed: {len(progress.completed_topics)} topics",
                f"Failed: {len(progress.failed_topics)} topics",
                f"Total cost: ${progress.total_cost:.2f}",
                f"Success rate: {progress.success_rate()*100:.1f}%",
                callback=progress_callback
            )
            
            # Clear saved progress on successful completion
            if progress.is_complete():
                self.clear_learning_progress(expert.name)
            
        finally:
            # Always close the session
            summary = self.cost_safety.close_session(session_id)
            if summary and summary.get("alerts"):
                for alert in summary["alerts"]:
                    self._log_progress(
                        f"Cost alert: {alert['message']}",
                        callback=progress_callback
                    )

        return progress

    async def _submit_research_jobs(
        self,
        expert: ExpertProfile,
        topics: List[LearningTopic],
        progress: LearningProgress,
        session,  # SessionCostTracker
        callback: Optional[Callable] = None
    ) -> List[str]:
        """Submit research jobs without waiting for completion.
        
        Returns list of job IDs for later polling.
        
        If a daily/monthly limit is hit, saves progress and returns what was
        submitted so far. The user can resume later.
        """
        from deepr.experts.cost_safety import is_pausable_limit, get_resume_message
        
        job_ids = []
        
        for topic in topics:
            # Budget check using session tracker
            can_proceed, reason = session.can_proceed(topic.estimated_cost)
            if not can_proceed:
                self._log_progress(
                    f"  Skipping {topic.title} - {reason}",
                    callback=callback
                )
                progress.failed_topics.append(topic.title)
                continue
            
            # Check global cost safety limits
            allowed, block_reason, needs_confirm = self.cost_safety.check_operation(
                session_id=session.session_id,
                operation_type="research",
                estimated_cost=topic.estimated_cost,
                require_confirmation=False  # No interactive confirmation in autonomous mode
            )
            
            if not allowed:
                # Check if this is a pausable limit (daily/monthly)
                if is_pausable_limit(block_reason):
                    self._log_progress(
                        "",
                        "="*70,
                        "  PAUSED - Daily/Monthly Limit Reached",
                        "="*70,
                        "",
                        get_resume_message(block_reason),
                        "",
                        f"Progress so far: {len(progress.completed_topics)} topics completed",
                        f"Remaining: {len(topics) - len(progress.completed_topics) - len(progress.failed_topics)} topics",
                        "",
                        "Your progress has been saved. To resume:",
                        f"  deepr expert learn \"{expert.name}\" --resume",
                        "",
                        callback=callback
                    )
                    # Save progress for resume
                    self._save_learning_progress(expert, progress, topics)
                    # Return what we have so far - don't mark remaining as failed
                    return job_ids
                else:
                    self._log_progress(
                        f"  Blocked {topic.title} - {block_reason}",
                        callback=callback
                    )
                    progress.failed_topics.append(topic.title)
                    continue
            
            try:
                self._log_progress(
                    f"  Submitting: {topic.title} (~${topic.estimated_cost:.2f})",
                    callback=callback
                )
                
                # Submit job (returns immediately with job ID)
                job_id = await self._submit_single_job(expert, topic, callback)
                
                if job_id:
                    job_ids.append(job_id)
                    # Record estimated cost (actual cost reconciled later)
                    session.record_operation(
                        operation_type="research_submit",
                        cost=topic.estimated_cost,
                        details=f"{topic.title} ({topic.research_mode})"
                    )
                    progress.total_cost = session.total_cost
                    self._log_progress(
                        f"    Job submitted: {job_id}",
                        callback=callback
                    )
                else:
                    session.record_failure("research_submit", f"No job ID returned for {topic.title}")
                    progress.failed_topics.append(topic.title)
                    
            except Exception as e:
                self._log_progress(
                    f"    Failed to submit: {e}",
                    callback=callback
                )
                session.record_failure("research_submit", str(e))
                progress.failed_topics.append(topic.title)
        
        return job_ids
    
    def _save_learning_progress(
        self,
        expert: ExpertProfile,
        progress: LearningProgress,
        remaining_topics: List[LearningTopic]
    ):
        """Save learning progress for later resume.
        
        Saves to expert's data directory so it can be resumed later.
        """
        import json
        from pathlib import Path
        
        store = ExpertStore()
        progress_file = store.get_knowledge_dir(expert.name) / "learning_progress.json"
        progress_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Calculate remaining topics (not completed, not failed)
        completed_set = set(progress.completed_topics)
        failed_set = set(progress.failed_topics)
        remaining = [t for t in remaining_topics if t.title not in completed_set and t.title not in failed_set]
        
        progress_data = {
            "expert_name": expert.name,
            "paused_at": datetime.now(timezone.utc).isoformat(),
            "completed_topics": progress.completed_topics,
            "failed_topics": progress.failed_topics,
            "remaining_topics": [
                {
                    "title": t.title,
                    "research_prompt": t.research_prompt,
                    "research_mode": t.research_mode,
                    "research_type": t.research_type,
                    "estimated_cost": t.estimated_cost,
                    "estimated_minutes": t.estimated_minutes
                }
                for t in remaining
            ],
            "total_cost_so_far": progress.total_cost,
            "started_at": progress.started_at.isoformat(),
            "reason": "daily_or_monthly_limit"
        }
        
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, indent=2)
    
    def load_learning_progress(self, expert_name: str) -> Optional[dict]:
        """Load saved learning progress for resume.
        
        Args:
            expert_name: Name of the expert
            
        Returns:
            Progress data dict or None if no saved progress
        """
        import json
        
        store = ExpertStore()
        progress_file = store.get_knowledge_dir(expert_name) / "learning_progress.json"
        
        if not progress_file.exists():
            return None
        
        with open(progress_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def clear_learning_progress(self, expert_name: str):
        """Clear saved learning progress after successful completion.
        
        Args:
            expert_name: Name of the expert
        """
        store = ExpertStore()
        progress_file = store.get_knowledge_dir(expert_name) / "learning_progress.json"
        
        if progress_file.exists():
            progress_file.unlink()

    async def _acquire_sources(
        self,
        expert: ExpertProfile,
        curriculum: LearningCurriculum,
        callback: Optional[Callable] = None
    ):
        """Phase 2a: Acquire sources - Fetch and scrape discovered sources.
        
        This phase:
        1. Collects all unique sources from curriculum topics
        2. Scrapes documentation URLs using existing scraper
        3. Fetches research papers (PDFs/HTML)
        4. Uploads all to expert's vector store
        
        Cost: $0 (just scraping/fetching, no LLM calls)
        
        Args:
            expert: Expert profile to update
            curriculum: Learning curriculum with source references
            callback: Optional progress callback
        """
        from deepr.utils.scrape import scrape_website, ScrapeConfig
        from deepr.experts.profile import ExpertStore
        import tempfile
        from pathlib import Path
        
        # Collect all unique sources from topics
        all_sources = []
        seen_urls = set()
        
        for topic in curriculum.topics:
            if topic.sources:
                for source in topic.sources:
                    if source.url and source.url not in seen_urls:
                        all_sources.append(source)
                        seen_urls.add(source.url)
        
        if not all_sources:
            self._log_progress(
                "\n[SKIP] No sources to acquire (curriculum has no source references)",
                callback=callback
            )
            return
        
        # Limit sources per type to avoid excessive scraping
        MAX_SOURCES_PER_TYPE = 5
        
        # Group by type
        by_type = {}
        for source in all_sources:
            if source.source_type not in by_type:
                by_type[source.source_type] = []
            by_type[source.source_type].append(source)
        
        # Take up to MAX_SOURCES_PER_TYPE of each type
        limited_sources = []
        for source_type, sources in by_type.items():
            limited_sources.extend(sources[:MAX_SOURCES_PER_TYPE])
        
        self._log_progress(
            "\n" + "="*70,
            "  Phase 2a: Acquiring Sources",
            "="*70,
            f"Found {len(all_sources)} unique sources ({len(limited_sources)} after limiting to {MAX_SOURCES_PER_TYPE} per type)",
            "",
            callback=callback
        )
        
        # Show counts by type
        limited_by_type = {}
        for source in limited_sources:
            if source.source_type not in limited_by_type:
                limited_by_type[source.source_type] = []
            limited_by_type[source.source_type].append(source)
        
        for source_type, sources in limited_by_type.items():
            original_count = len(by_type[source_type])
            if original_count > MAX_SOURCES_PER_TYPE:
                self._log_progress(
                    f"  {source_type}: {len(sources)} sources (limited from {original_count})",
                    callback=callback
                )
            else:
                self._log_progress(
                    f"  {source_type}: {len(sources)} sources",
                    callback=callback
                )
        
        # Acquire each source
        acquired = 0
        failed = 0
        
        store = ExpertStore()
        docs_dir = store.get_documents_dir(expert.name)
        docs_dir.mkdir(parents=True, exist_ok=True)
        
        for i, source in enumerate(limited_sources, 1):
            try:
                self._log_progress(
                    f"\n{i}/{len(all_sources)}: {source.title}",
                    f"  URL: {source.url}",
                    f"  Type: {source.source_type}",
                    callback=callback
                )
                
                # Determine acquisition strategy based on source type
                if source.source_type in ["documentation", "guide", "blog"]:
                    # Scrape website
                    content = await self._scrape_source(source, callback)
                elif source.source_type == "paper":
                    # Fetch paper (PDF or HTML)
                    content = await self._fetch_paper(source, callback)
                elif source.source_type == "video":
                    # Skip videos for now (would need transcript extraction)
                    self._log_progress(
                        "  [SKIP] Video sources not yet supported",
                        callback=callback
                    )
                    continue
                else:
                    # Unknown type - try scraping
                    content = await self._scrape_source(source, callback)
                
                if not content:
                    self._log_progress(
                        "  [SKIP] No content extracted",
                        callback=callback
                    )
                    failed += 1
                    continue
                
                # Save to expert's documents folder
                safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in source.title)
                filename = f"source_{safe_title[:50]}.md"
                doc_path = docs_dir / filename
                
                with open(doc_path, 'w', encoding='utf-8') as f:
                    f.write(f"# {source.title}\n\n")
                    f.write(f"**Source:** {source.url}\n")
                    f.write(f"**Type:** {source.source_type}\n")
                    if source.description:
                        f.write(f"**Description:** {source.description}\n")
                    f.write(f"\n---\n\n")
                    f.write(content)
                
                # Upload to vector store
                with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
                    f.write(f"# {source.title}\n\n")
                    f.write(f"**Source:** {source.url}\n")
                    f.write(f"**Type:** {source.source_type}\n")
                    if source.description:
                        f.write(f"**Description:** {source.description}\n")
                    f.write(f"\n---\n\n")
                    f.write(content)
                    temp_file = f.name
                
                try:
                    # Upload file to OpenAI
                    file_id = await self.research.provider.upload_document(temp_file, purpose="assistants")
                    
                    # Attach file to vector store
                    await self.research.provider.client.vector_stores.files.create(
                        vector_store_id=expert.vector_store_id,
                        file_id=file_id
                    )
                    
                    acquired += 1
                    self._log_progress(
                        f"  [OK] Acquired and uploaded as {filename}",
                        callback=callback
                    )
                finally:
                    # Clean up temp file
                    if Path(temp_file).exists():
                        Path(temp_file).unlink()
                
            except Exception as e:
                self._log_progress(
                    f"  [ERROR] {str(e)}",
                    callback=callback
                )
                failed += 1
        
        # Update expert metadata
        expert.total_documents += acquired
        expert.last_knowledge_refresh = datetime.now(timezone.utc)
        store.save(expert)
        
        self._log_progress(
            "",
            "="*70,
            f"Source Acquisition Complete: {acquired} acquired, {failed} failed",
            "="*70,
            "",
            callback=callback
        )
    
    async def _scrape_source(
        self,
        source,
        callback: Optional[Callable] = None
    ) -> Optional[str]:
        """Scrape a documentation/guide/blog source.
        
        Args:
            source: SourceReference to scrape
            callback: Optional progress callback
            
        Returns:
            Scraped content as markdown, or None if failed
        """
        from deepr.utils.scrape import scrape_website, ScrapeConfig
        
        try:
            # Configure scraping for documentation
            config = ScrapeConfig(
                max_pages=10,  # Limit to 10 pages per source
                max_depth=2,
                try_selenium=False,  # HTTP only for speed
            )
            
            # Scrape website
            results = scrape_website(
                url=source.url,
                purpose="documentation",
                config=config,
                synthesize=False,  # Don't synthesize, just extract
            )
            
            if results['success']:
                self._log_progress(
                    f"  [OK] Scraped {results['pages_scraped']} pages",
                    callback=callback
                )
                
                # Combine all scraped pages
                content = ""
                for url, page_content in results['scraped_data'].items():
                    content += f"\n## Page: {url}\n\n"
                    content += page_content
                    content += "\n\n---\n\n"
                
                return content
            else:
                self._log_progress(
                    f"  [WARN] Scraping failed: {results.get('error', 'Unknown error')}",
                    callback=callback
                )
                return None
                
        except Exception as e:
            self._log_progress(
                f"  [ERROR] Scraping error: {str(e)}",
                callback=callback
            )
            return None
    
    async def _fetch_paper(
        self,
        source,
        callback: Optional[Callable] = None
    ) -> Optional[str]:
        """Fetch a research paper (PDF or HTML).
        
        Args:
            source: SourceReference to fetch
            callback: Optional progress callback
            
        Returns:
            Paper content as text, or None if failed
        """
        import httpx
        
        try:
            # For now, just fetch HTML content
            # TODO: Add PDF extraction support
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(source.url)
                response.raise_for_status()
                
                # Check content type
                content_type = response.headers.get('content-type', '')
                
                if 'pdf' in content_type.lower():
                    self._log_progress(
                        f"  [SKIP] PDF extraction not yet implemented",
                        callback=callback
                    )
                    return None
                else:
                    # HTML content - extract text
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style"]):
                        script.decompose()
                    
                    # Get text
                    text = soup.get_text()
                    
                    # Clean up whitespace
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    text = '\n'.join(chunk for chunk in chunks if chunk)
                    
                    self._log_progress(
                        f"  [OK] Fetched {len(text)} characters",
                        callback=callback
                    )
                    
                    return text
                    
        except Exception as e:
            self._log_progress(
                f"  [ERROR] Fetch error: {str(e)}",
                callback=callback
            )
            return None

    async def _submit_single_job(
        self,
        expert: ExpertProfile,
        topic: LearningTopic,
        callback: Optional[Callable] = None
    ) -> Optional[str]:
        """Submit a single research job without waiting for completion.
        
        Returns job ID for later polling, or None if submission failed.
        """
        try:
            # Use appropriate model based on research mode
            if topic.research_mode == "campaign":
                # Campaign mode: Deep research (10-45 min per topic)
                model = "o4-mini-deep-research"
            else:
                # Focus mode: Quick research with GPT-5 (1-5 min per topic)
                model = "gpt-5"

            response_id = await self.research.submit_research(
                prompt=topic.research_prompt,
                model=model,
                vector_store_id=expert.vector_store_id,
                enable_web_search=True,
                enable_code_interpreter=False,
            )
            
            return response_id
            
        except Exception as e:
            self._log_progress(
                f"    [ERROR] Submit failed: {e}",
                callback=callback
            )
            return None

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
                # Use appropriate model based on research mode
                if topic.research_mode == "campaign":
                    # Campaign mode: Deep research (10-45 min per topic)
                    model = "o4-mini-deep-research"
                else:
                    # Focus mode: Quick research with GPT-5 (1-5 min per topic)
                    model = "gpt-5"

                response_id = await self.research.submit_research(
                    prompt=topic.research_prompt,
                    model=model,
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
        session,  # SessionCostTracker
        callback: Optional[Callable] = None
    ):
        """Poll for job completion and integrate reports into expert's knowledge."""
        from datetime import datetime

        if not job_ids:
            return

        self._log_progress(
            "",
            "Waiting for Research Completion",
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
            # Check if circuit breaker is open
            if session.is_circuit_open:
                self._log_progress(
                    "Circuit breaker open - stopping polling due to repeated failures",
                    callback=callback
                )
                break
            
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
                            f"  {job_id[:20]}... COMPLETED",
                            callback=callback
                        )
                        pending.remove(job_id)
                        completed.add(job_id)

                        if response.usage:
                            cost = response.usage.cost
                            total_cost += cost
                            # Record actual cost (may differ from estimate)
                            self.cost_safety.record_cost(
                                session_id=session.session_id,
                                operation_type="research_complete",
                                actual_cost=cost,
                                details=f"Job {job_id[:12]}"
                            )
                            self._log_progress(
                                f"       Cost: ${cost:.4f}",
                                callback=callback
                            )

                    elif response.status in ["failed", "cancelled"]:
                        self._log_progress(
                            f"  {job_id[:20]}... {response.status.upper()}",
                            callback=callback
                        )
                        pending.remove(job_id)
                        failed.add(job_id)
                        session.record_failure("research_poll", f"Job {job_id} {response.status}")

                    elif response.status in ["in_progress", "queued"]:
                        # Still running, check next time
                        pass

                except Exception as e:
                    self._log_progress(
                        f"  {job_id[:20]}... Error: {e}",
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
            "",
            "Research Complete",
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

                # Save to expert's documents folder
                filename = f"research_{job_id[:12]}.md"
                store = ExpertStore()
                docs_dir = store.get_documents_dir(expert.name)
                docs_dir.mkdir(parents=True, exist_ok=True)

                doc_path = docs_dir / filename
                with open(doc_path, 'w', encoding='utf-8') as f:
                    f.write(raw_text)

                # Also save to temporary file for upload
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
        expert.last_knowledge_refresh = datetime.now(timezone.utc)

        store = ExpertStore()
        store.save(expert)

        self._log_progress(
            "",
            "="*70,
            f"Knowledge Integration Complete: {uploaded} documents added",
            "="*70,
            callback=callback
        )

        # CRITICAL: Synthesize knowledge into expert consciousness
        # This transforms the expert from "document store" to "conscious entity"
        try:
            from deepr.experts.synthesis import KnowledgeSynthesizer, Worldview
            from deepr.config import AppConfig

            config = AppConfig.from_env()

            # Only synthesize if auto-synthesis is enabled (default: True)
            if config.expert.auto_synthesis and uploaded > 0:
                self._log_progress(
                    "",
                    "="*70,
                    "  Knowledge Synthesis (Creating Expert Consciousness)",
                    "="*70,
                    f"Processing {uploaded} documents into synthesized understanding...",
                    "",
                    callback=callback
                )

                synthesizer = KnowledgeSynthesizer(self.research.provider.client)

                # Get documents directory
                docs_dir = store.get_documents_dir(expert.name)

                # Load newly added research documents
                new_docs = []
                for job_id in job_ids:
                    filename = f"research_{job_id[:12]}.md"
                    doc_path = docs_dir / filename
                    if doc_path.exists():
                        new_docs.append({"path": str(doc_path)})

                # Load existing worldview if it exists
                worldview_path = store.get_knowledge_dir(expert.name) / "worldview.json"
                existing_worldview = None
                if worldview_path.exists():
                    existing_worldview = Worldview.load(worldview_path)

                # Synthesize new knowledge
                result = await synthesizer.synthesize_new_knowledge(
                    expert_name=expert.name,
                    domain=expert.domain or expert.description or "General expertise",
                    new_documents=new_docs,
                    existing_worldview=existing_worldview
                )

                if result['success']:
                    worldview = result['worldview']

                    # Save worldview as JSON
                    worldview.save(worldview_path)

                    # Generate human-readable worldview document
                    worldview_doc = await synthesizer.generate_worldview_document(
                        worldview, result['reflection']
                    )

                    # Save as markdown
                    worldview_md_path = store.get_knowledge_dir(expert.name) / "worldview.md"
                    with open(worldview_md_path, 'w', encoding='utf-8') as f:
                        f.write(worldview_doc)

                    self._log_progress(
                        "",
                        f"  [OK] Expert consciousness formed",
                        f"       Beliefs: {len(worldview.beliefs)} beliefs formed",
                        f"       Knowledge gaps: {len(worldview.knowledge_gaps)} gaps identified",
                        f"       Synthesis count: {worldview.synthesis_count}",
                        f"       Worldview saved: {worldview_md_path.name}",
                        "",
                        callback=callback
                    )
                else:
                    self._log_progress(
                        "",
                        f"  [WARNING] Synthesis failed: {result.get('error', 'Unknown error')}",
                        f"  Expert will function but without synthesized worldview",
                        "",
                        callback=callback
                    )
        except Exception as e:
            self._log_progress(
                "",
                f"  [WARNING] Synthesis error: {str(e)}",
                f"  Expert will function but without synthesized worldview",
                "",
                callback=callback
            )

        # Final success message
        self._log_progress(
            "="*70,
            f"Expert Creation Complete",
            "="*70,
            "",
            f"Expert: {expert.name}",
            f"Documents: {expert.total_documents}",
            f"Consciousness: {'Formed' if (config.expert.auto_synthesis and uploaded > 0) else 'Not synthesized'}",
            "",
            f"Ready to chat: deepr expert chat \"{expert.name}\"",
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
        expert.last_knowledge_refresh = datetime.now(timezone.utc)
        if not expert.knowledge_cutoff_date:
            expert.knowledge_cutoff_date = datetime.now(timezone.utc)

        # Save updated profile
        store = ExpertStore()
        store.save(expert)

    def _log_progress(self, *messages, callback: Optional[Callable] = None):
        """Log progress messages with modern formatting.
        
        Uses Rich console for clean, colorful output without legacy markers.
        """
        from deepr.cli.colors import console
        
        for msg in messages:
            # Skip empty messages
            if not msg or not msg.strip():
                continue
            
            # Print with Rich formatting
            console.print(msg)
            
            if callback:
                callback(msg)

