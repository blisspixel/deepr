"""
Job Manager for MCP Resource Subscriptions.

Tracks research job state and emits notifications when phases complete.
Uses asyncio.create_task for background execution to avoid blocking.
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime
from enum import Enum
import asyncio

from .subscriptions import SubscriptionManager


class JobPhase(Enum):
    """Research job execution phases."""
    
    QUEUED = "queued"
    PLANNING = "planning"
    EXECUTING = "executing"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobState:
    """
    Current state of a research job.
    
    Attributes:
        job_id: Unique job identifier
        phase: Current execution phase
        progress: Progress percentage (0.0 to 1.0)
        active_tasks: List of currently executing task descriptions
        cost_so_far: Accumulated cost in dollars
        estimated_remaining: Human-readable time estimate
        started_at: When job started
        updated_at: Last state update time
        error: Error message if failed
        metadata: Additional job-specific data
    """
    
    job_id: str
    phase: JobPhase = JobPhase.QUEUED
    progress: float = 0.0
    active_tasks: list[str] = field(default_factory=list)
    cost_so_far: float = 0.0
    estimated_remaining: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "job_id": self.job_id,
            "phase": self.phase.value,
            "progress": self.progress,
            "active_tasks": self.active_tasks,
            "cost_so_far": self.cost_so_far,
            "estimated_remaining": self.estimated_remaining,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error": self.error,
            "metadata": self.metadata
        }


@dataclass
class JobPlan:
    """Research plan for a job."""
    
    job_id: str
    goal: str
    steps: list[dict] = field(default_factory=list)
    estimated_cost: float = 0.0
    estimated_time: str = "unknown"
    model: str = "o4-mini"
    
    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "goal": self.goal,
            "steps": self.steps,
            "estimated_cost": self.estimated_cost,
            "estimated_time": self.estimated_time,
            "model": self.model
        }


@dataclass
class TemporalFindingRecord:
    """A timestamped finding for temporal tracking."""
    id: str
    text: str
    phase: int
    confidence: float
    finding_type: str
    timestamp: str
    source: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "phase": self.phase,
            "confidence": self.confidence,
            "finding_type": self.finding_type,
            "timestamp": self.timestamp,
            "source": self.source,
        }


@dataclass
class HypothesisRecord:
    """A hypothesis with evolution history."""
    id: str
    current_text: str
    confidence: float
    phase_created: int
    evolution_count: int = 0
    status: str = "active"  # active, invalidated

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "current_text": self.current_text,
            "confidence": self.confidence,
            "phase_created": self.phase_created,
            "evolution_count": self.evolution_count,
            "status": self.status,
        }


@dataclass
class JobBeliefs:
    """Accumulated beliefs/findings from a job."""

    job_id: str
    beliefs: list[dict] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    confidence: float = 0.0

    # Temporal knowledge tracking
    temporal_findings: list[TemporalFindingRecord] = field(default_factory=list)
    hypothesis_history: list[HypothesisRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "beliefs": self.beliefs,
            "sources": self.sources,
            "confidence": self.confidence,
            "belief_count": len(self.beliefs),
            "temporal_findings": [f.to_dict() for f in self.temporal_findings],
            "hypothesis_history": [h.to_dict() for h in self.hypothesis_history],
            "temporal_finding_count": len(self.temporal_findings),
            "active_hypotheses": len([h for h in self.hypothesis_history if h.status == "active"]),
        }

    def add_temporal_finding(
        self,
        finding_id: str,
        text: str,
        phase: int,
        confidence: float,
        finding_type: str,
        source: Optional[str] = None,
    ) -> TemporalFindingRecord:
        """Add a temporal finding record."""
        record = TemporalFindingRecord(
            id=finding_id,
            text=text,
            phase=phase,
            confidence=confidence,
            finding_type=finding_type,
            timestamp=datetime.now().isoformat(),
            source=source,
        )
        self.temporal_findings.append(record)
        return record

    def add_hypothesis(
        self,
        hypothesis_id: str,
        text: str,
        confidence: float,
        phase: int,
    ) -> HypothesisRecord:
        """Add a hypothesis record."""
        record = HypothesisRecord(
            id=hypothesis_id,
            current_text=text,
            confidence=confidence,
            phase_created=phase,
        )
        self.hypothesis_history.append(record)
        return record

    def update_hypothesis(
        self,
        hypothesis_id: str,
        new_text: Optional[str] = None,
        new_confidence: Optional[float] = None,
        status: Optional[str] = None,
    ) -> Optional[HypothesisRecord]:
        """Update an existing hypothesis."""
        for h in self.hypothesis_history:
            if h.id == hypothesis_id:
                if new_text is not None:
                    h.current_text = new_text
                if new_confidence is not None:
                    h.confidence = new_confidence
                if status is not None:
                    h.status = status
                h.evolution_count += 1
                return h
        return None


class JobManager:
    """
    Manages research jobs and emits state change notifications.
    
    Integrates with SubscriptionManager to push updates to subscribers
    when job state changes, eliminating the need for polling.
    """
    
    def __init__(self, subscription_manager: Optional[SubscriptionManager] = None):
        self._jobs: dict[str, JobState] = {}
        self._plans: dict[str, JobPlan] = {}
        self._beliefs: dict[str, JobBeliefs] = {}
        self._subscriptions = subscription_manager or SubscriptionManager()
        self._background_tasks: set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
    
    @property
    def subscriptions(self) -> SubscriptionManager:
        """Access the subscription manager."""
        return self._subscriptions
    
    async def create_job(
        self,
        job_id: str,
        goal: str,
        model: str = "o4-mini",
        estimated_cost: float = 0.0,
        estimated_time: str = "unknown"
    ) -> JobState:
        """
        Create and register a new job.
        
        Args:
            job_id: Unique job identifier
            goal: Research goal/prompt
            model: Model to use
            estimated_cost: Estimated cost in dollars
            estimated_time: Human-readable time estimate
        
        Returns:
            Initial JobState
        """
        async with self._lock:
            state = JobState(
                job_id=job_id,
                phase=JobPhase.QUEUED,
                estimated_remaining=estimated_time
            )
            self._jobs[job_id] = state
            
            plan = JobPlan(
                job_id=job_id,
                goal=goal,
                model=model,
                estimated_cost=estimated_cost,
                estimated_time=estimated_time
            )
            self._plans[job_id] = plan
            
            self._beliefs[job_id] = JobBeliefs(job_id=job_id)
        
        # Emit creation event
        await self._emit_status_update(job_id)
        
        return state
    
    async def update_phase(
        self,
        job_id: str,
        phase: JobPhase,
        progress: Optional[float] = None,
        active_tasks: Optional[list[str]] = None,
        cost_so_far: Optional[float] = None,
        estimated_remaining: Optional[str] = None,
        error: Optional[str] = None
    ) -> Optional[JobState]:
        """
        Update job phase and emit notification.
        
        Args:
            job_id: Job to update
            phase: New phase
            progress: Optional progress update (0.0-1.0)
            active_tasks: Optional list of current tasks
            cost_so_far: Optional cost update
            estimated_remaining: Optional time estimate update
            error: Optional error message (for FAILED phase)
        
        Returns:
            Updated JobState or None if job not found
        """
        async with self._lock:
            if job_id not in self._jobs:
                return None
            
            state = self._jobs[job_id]
            state.phase = phase
            state.updated_at = datetime.now()
            
            if progress is not None:
                state.progress = max(0.0, min(1.0, progress))
            if active_tasks is not None:
                state.active_tasks = active_tasks
            if cost_so_far is not None:
                state.cost_so_far = cost_so_far
            if estimated_remaining is not None:
                state.estimated_remaining = estimated_remaining
            if error is not None:
                state.error = error
        
        # Emit update in background
        self._schedule_emit(job_id)
        
        return state
    
    async def add_belief(
        self,
        job_id: str,
        belief: str,
        confidence: float,
        source: Optional[str] = None
    ) -> bool:
        """
        Add a belief/finding to a job.
        
        Args:
            job_id: Job to update
            belief: The belief/finding text
            confidence: Confidence score (0.0-1.0)
            source: Optional source citation
        
        Returns:
            True if added, False if job not found
        """
        async with self._lock:
            if job_id not in self._beliefs:
                return False
            
            beliefs = self._beliefs[job_id]
            beliefs.beliefs.append({
                "text": belief,
                "confidence": confidence,
                "added_at": datetime.now().isoformat()
            })
            
            if source:
                beliefs.sources.append(source)
            
            # Update overall confidence (weighted average)
            if beliefs.beliefs:
                total_conf = sum(b["confidence"] for b in beliefs.beliefs)
                beliefs.confidence = total_conf / len(beliefs.beliefs)
        
        # Emit beliefs update
        await self._emit_beliefs_update(job_id)
        
        return True
    
    async def update_plan(
        self,
        job_id: str,
        steps: list[dict]
    ) -> bool:
        """
        Update the research plan for a job.
        
        Args:
            job_id: Job to update
            steps: List of plan steps
        
        Returns:
            True if updated, False if job not found
        """
        async with self._lock:
            if job_id not in self._plans:
                return False
            
            self._plans[job_id].steps = steps
        
        # Emit plan update
        await self._emit_plan_update(job_id)
        
        return True
    
    def get_state(self, job_id: str) -> Optional[JobState]:
        """Get current job state."""
        return self._jobs.get(job_id)
    
    def get_plan(self, job_id: str) -> Optional[JobPlan]:
        """Get job plan."""
        return self._plans.get(job_id)
    
    def get_beliefs(self, job_id: str) -> Optional[JobBeliefs]:
        """Get job beliefs."""
        return self._beliefs.get(job_id)
    
    def list_jobs(self, phase: Optional[JobPhase] = None) -> list[JobState]:
        """
        List all jobs, optionally filtered by phase.
        
        Args:
            phase: Optional phase filter
        
        Returns:
            List of matching JobState objects
        """
        jobs = list(self._jobs.values())
        
        if phase:
            jobs = [j for j in jobs if j.phase == phase]
        
        return jobs
    
    async def remove_job(self, job_id: str) -> bool:
        """
        Remove a job and its associated data.
        
        Args:
            job_id: Job to remove
        
        Returns:
            True if removed, False if not found
        """
        async with self._lock:
            if job_id not in self._jobs:
                return False
            
            del self._jobs[job_id]
            self._plans.pop(job_id, None)
            self._beliefs.pop(job_id, None)
        
        return True
    
    def _schedule_emit(self, job_id: str) -> None:
        """Schedule a status update emission in background."""
        task = asyncio.create_task(self._emit_status_update(job_id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
    
    async def _emit_status_update(self, job_id: str) -> None:
        """Emit status update to subscribers."""
        state = self._jobs.get(job_id)
        if not state:
            return
        
        uri = f"deepr://campaigns/{job_id}/status"
        await self._subscriptions.emit(uri, state.to_dict())
    
    async def _emit_plan_update(self, job_id: str) -> None:
        """Emit plan update to subscribers."""
        plan = self._plans.get(job_id)
        if not plan:
            return
        
        uri = f"deepr://campaigns/{job_id}/plan"
        await self._subscriptions.emit(uri, plan.to_dict())
    
    async def _emit_beliefs_update(self, job_id: str) -> None:
        """Emit beliefs update to subscribers."""
        beliefs = self._beliefs.get(job_id)
        if not beliefs:
            return
        
        uri = f"deepr://campaigns/{job_id}/beliefs"
        await self._subscriptions.emit(uri, beliefs.to_dict())
    
    async def cleanup(self) -> None:
        """Cancel all background tasks."""
        for task in self._background_tasks:
            task.cancel()
        
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        self._background_tasks.clear()
