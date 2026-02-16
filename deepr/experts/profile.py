"""Expert profile data classes.

This module provides the core ExpertProfile dataclass for domain experts.
Uses composition with specialized managers for cleaner separation:

- TemporalState: Tracks temporal awareness and activity timestamps
- FreshnessChecker: Evaluates knowledge freshness based on domain velocity
- BudgetManager: Handles monthly learning budget tracking
- ActivityTracker: Records conversations and research triggers

For storage operations (save, load, delete), see profile_store.py.
ExpertStore is re-exported here for backwards compatibility.

Requirements: 1.2 - ExpertProfile Refactoring
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from deepr.core.contracts import ExpertManifest

from deepr.experts.activity_tracker import ActivityTracker
from deepr.experts.budget_manager import BudgetManager
from deepr.experts.freshness import FreshnessChecker, FreshnessLevel
from deepr.experts.serializer import (
    datetime_to_iso,
    dict_to_profile_kwargs,
    profile_to_dict,
)
from deepr.experts.temporal import TemporalState


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


@dataclass
class ExpertProfile:
    """Profile for a domain expert.

    Combines vector store (for knowledge) with metadata (for behavior).
    Uses composition with specialized managers for cleaner separation.

    Core Metadata:
        name, vector_store_id, description, domain, created_at, updated_at

    Knowledge Tracking:
        source_files, research_jobs, total_documents, knowledge_cutoff_date,
        last_knowledge_refresh, refresh_frequency_days, domain_velocity

    Behavior Configuration:
        system_message, temperature, max_tokens, provider, model

    Composed Managers (delegated functionality):
        - BudgetManager: Monthly learning budget tracking
        - ActivityTracker: Conversation and research counting
        - TemporalState: Activity timestamps
        - FreshnessChecker: Knowledge freshness evaluation
    """

    # Core metadata
    name: str
    vector_store_id: str
    description: Optional[str] = None
    domain: Optional[str] = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    # Knowledge base metadata
    source_files: list[str] = field(default_factory=list)
    research_jobs: list[str] = field(default_factory=list)
    total_documents: int = 0

    # Temporal awareness
    knowledge_cutoff_date: Optional[datetime] = None
    last_knowledge_refresh: Optional[datetime] = None
    refresh_frequency_days: int = 90
    domain_velocity: str = "medium"  # slow/medium/fast

    # Behavior configuration
    system_message: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None

    # Usage tracking (delegated to managers but kept for serialization)
    conversations: int = 0
    research_triggered: int = 0
    total_research_cost: float = 0.0

    # Budget tracking (delegated to BudgetManager)
    monthly_learning_budget: float = 5.0
    monthly_spending: float = 0.0
    monthly_spending_reset_date: Optional[datetime] = None
    refresh_history: list[dict] = field(default_factory=list)

    # Provider preferences
    provider: str = "openai"
    model: str = "gpt-5.2"

    # Installed skills (skill names referencing skill directories)
    installed_skills: list[str] = field(default_factory=list)

    # Composed components (not serialized directly)
    _temporal_state: Optional[TemporalState] = field(default=None, repr=False)
    _freshness_checker: Optional[FreshnessChecker] = field(default=None, repr=False)
    _budget_manager: Optional[BudgetManager] = field(default=None, repr=False)
    _activity_tracker: Optional[ActivityTracker] = field(default=None, repr=False)

    def __post_init__(self):
        """Initialize composed components."""
        self._init_components()

    def _init_components(self):
        """Initialize all composed managers."""
        # Temporal state
        if self._temporal_state is None:
            self._temporal_state = TemporalState(
                created_at=self.created_at, last_activity=self.updated_at, last_learning=self.last_knowledge_refresh
            )

        # Freshness checker with domain velocity
        velocity_map = {"slow": 180, "medium": 90, "fast": 30}
        velocity_days = velocity_map.get(self.domain_velocity, 90)

        if self._freshness_checker is None:
            self._freshness_checker = FreshnessChecker(domain=self.domain or "general", velocity_days=velocity_days)

        # Budget manager
        if self._budget_manager is None:
            self._budget_manager = BudgetManager(
                monthly_budget=self.monthly_learning_budget,
                monthly_spending=self.monthly_spending,
                total_spending=self.total_research_cost,
                reset_date=self.monthly_spending_reset_date,
                refresh_history=self.refresh_history,
            )

        # Activity tracker
        if self._activity_tracker is None:
            self._activity_tracker = ActivityTracker(
                conversations=self.conversations,
                research_triggered=self.research_triggered,
                last_activity=self.updated_at,
            )

    # =========================================================================
    # Property accessors for composed components
    # =========================================================================

    @property
    def temporal_state(self) -> TemporalState:
        """Get temporal state component."""
        if self._temporal_state is None:
            self._init_components()
        return self._temporal_state

    @property
    def freshness_checker(self) -> FreshnessChecker:
        """Get freshness checker component."""
        if self._freshness_checker is None:
            self._init_components()
        return self._freshness_checker

    @property
    def budget_manager(self) -> BudgetManager:
        """Get budget manager component."""
        if self._budget_manager is None:
            self._init_components()
        return self._budget_manager

    @property
    def activity_tracker(self) -> ActivityTracker:
        """Get activity tracker component."""
        if self._activity_tracker is None:
            self._init_components()
        return self._activity_tracker

    # =========================================================================
    # Activity tracking (delegates to ActivityTracker)
    # =========================================================================

    def record_activity(self, activity_type: str, details: Optional[dict] = None):
        """Record an activity event.

        Args:
            activity_type: Type of activity (chat, research, etc.)
            details: Optional additional details
        """
        self.activity_tracker.record_activity(activity_type, details)
        self.updated_at = datetime.now(timezone.utc)

        # Sync counters back to profile for serialization
        self.conversations = self.activity_tracker.conversations
        self.research_triggered = self.activity_tracker.research_triggered

    # =========================================================================
    # Freshness checking (delegates to FreshnessChecker)
    # =========================================================================

    def is_knowledge_stale(self) -> bool:
        """Check if knowledge needs refreshing based on domain velocity."""
        if self.knowledge_cutoff_date is None:
            return True
        return self.freshness_checker.is_stale(last_learning=self.knowledge_cutoff_date)

    def get_freshness_status(self) -> dict[str, Any]:
        """Get detailed freshness status.

        Returns:
            Dictionary with status, message, action_required, age_days,
            threshold_days, and freshness_score
        """
        # Check for incomplete expert first
        if self.knowledge_cutoff_date is None:
            return {
                "status": "incomplete",
                "message": "Expert needs initial learning curriculum",
                "action_required": f"Run: deepr expert learn {self.name} --budget 5",
            }

        status = self.freshness_checker.check(last_learning=self.knowledge_cutoff_date, last_activity=self.updated_at)

        status_map = {
            FreshnessLevel.FRESH: "fresh",
            FreshnessLevel.AGING: "aging",
            FreshnessLevel.STALE: "stale",
            FreshnessLevel.CRITICAL: "stale",
        }

        return {
            "status": status_map.get(status.level, "unknown"),
            "age_days": status.days_since_update,
            "threshold_days": status.threshold_days,
            "message": status.recommendation,
            "action_required": status.recommendation if status.needs_refresh() else None,
            "freshness_score": status.score,
        }

    def get_staleness_details(self) -> dict[str, Any]:
        """Get detailed staleness information for continuous self-improvement."""
        freshness = self.get_freshness_status()

        # Calculate refresh cost estimate
        velocity_multipliers = {"slow": 0.5, "medium": 1.0, "fast": 2.0}
        estimated_cost = 0.50 * velocity_multipliers.get(self.domain_velocity, 1.0)

        # Determine urgency
        urgency_map = {
            "stale": ("high", 1.0),
            "aging": ("medium", 0.6),
            "incomplete": ("critical", 1.0),
            "fresh": ("low", 0.2),
        }
        urgency, urgency_score = urgency_map.get(freshness["status"], ("low", 0.2))

        # Days until stale
        days_until_stale = None
        if self.knowledge_cutoff_date and freshness.get("threshold_days"):
            age_days = freshness.get("age_days", 0)
            days_until_stale = max(0, freshness["threshold_days"] - age_days)

        return {
            "is_stale": self.is_knowledge_stale(),
            "freshness_status": freshness["status"],
            "age_days": freshness.get("age_days"),
            "threshold_days": freshness.get("threshold_days"),
            "days_until_stale": days_until_stale,
            "domain_velocity": self.domain_velocity,
            "urgency": urgency,
            "urgency_score": urgency_score,
            "estimated_refresh_cost": estimated_cost,
            "last_refresh": datetime_to_iso(self.last_knowledge_refresh),
            "knowledge_cutoff": datetime_to_iso(self.knowledge_cutoff_date),
            "message": freshness.get("message"),
            "action_required": freshness.get("action_required"),
            "refresh_command": f"deepr expert learn {self.name} --budget {estimated_cost:.2f}",
        }

    def suggest_refresh(self) -> Optional[dict[str, Any]]:
        """Suggest a knowledge refresh if needed."""
        staleness = self.get_staleness_details()

        if not staleness["is_stale"] and staleness["urgency"] == "low":
            return None

        return {
            "expert_name": self.name,
            "domain": self.domain,
            "reason": staleness["message"],
            "urgency": staleness["urgency"],
            "estimated_cost": staleness["estimated_refresh_cost"],
            "command": staleness["refresh_command"],
            "topics": self._suggest_refresh_topics(),
        }

    def _suggest_refresh_topics(self) -> list[str]:
        """Suggest topics for refresh based on domain."""
        topics = []
        if self.domain:
            topics.append(f"Latest developments in {self.domain}")
            topics.append(f"Recent changes to {self.domain} best practices")

        if self.domain_velocity == "fast":
            topics.extend(["Breaking news and announcements", "New tools and frameworks"])
        elif self.domain_velocity == "medium":
            topics.append("Industry trends and updates")

        return topics[:5]

    # =========================================================================
    # Budget management (delegates to BudgetManager)
    # =========================================================================

    def get_monthly_budget_status(self) -> dict[str, Any]:
        """Get monthly learning budget status."""
        status = self.budget_manager.get_status()
        self._sync_budget_from_manager()
        return status

    def can_spend_learning_budget(self, amount: float) -> tuple[bool, str]:
        """Check if spending amount is within monthly budget."""
        return self.budget_manager.can_spend(amount)

    def record_learning_spend(self, amount: float, operation: str, details: Optional[str] = None):
        """Record spending against monthly learning budget."""
        self.budget_manager.record_spending(amount, operation, details)
        self._sync_budget_from_manager()

    def _sync_budget_from_manager(self):
        """Sync budget fields from manager for serialization."""
        self.monthly_spending = self.budget_manager.monthly_spending
        self.total_research_cost = self.budget_manager.total_spending
        self.monthly_spending_reset_date = self.budget_manager.reset_date
        self.refresh_history = self.budget_manager.refresh_history

    # =========================================================================
    # Manifest generation
    # =========================================================================

    def get_manifest(self) -> "ExpertManifest":
        """Build a complete ExpertManifest snapshot.

        Loads beliefs from BeliefStore, worldview from synthesis, gaps from
        metacognition + synthesis, and decision records from ThoughtStream logs.

        Returns:
            ExpertManifest composing all expert state.
        """
        from deepr.core.contracts import ExpertManifest, Gap
        from deepr.experts.gap_scorer import score_gap

        claims = []
        seen_statements: set[str] = set()

        # Load beliefs from BeliefStore
        try:
            from deepr.experts.beliefs import BeliefStore

            store = BeliefStore(self.name)
            for belief in store.beliefs.values():
                claim = belief.to_claim()
                if claim.statement not in seen_statements:
                    claims.append(claim)
                    seen_statements.add(claim.statement)
        except Exception:
            pass

        # Load worldview beliefs from synthesis
        try:
            from deepr.experts.synthesis import Worldview

            wv_path = Path(f"data/experts/{self.name}/worldview.json")
            if wv_path.exists():
                wv = Worldview.load(wv_path)
                for belief in wv.beliefs:
                    claim = belief.to_claim()
                    if claim.statement not in seen_statements:
                        claims.append(claim)
                        seen_statements.add(claim.statement)
        except Exception:
            pass

        gaps: list[Gap] = []
        seen_topics: set[str] = set()
        velocity = self.domain_velocity or "medium"

        # Load gaps from metacognition
        try:
            from deepr.experts.metacognition import MetaCognitionTracker

            tracker = MetaCognitionTracker(self.name)
            for kg in tracker.knowledge_gaps.values():
                gap = kg.to_gap()
                if gap.topic not in seen_topics:
                    score_gap(gap, domain_velocity=velocity)
                    gaps.append(gap)
                    seen_topics.add(gap.topic)
        except Exception:
            pass

        # Load gaps from synthesis worldview
        try:
            from deepr.experts.synthesis import Worldview

            wv_path = Path(f"data/experts/{self.name}/worldview.json")
            if wv_path.exists():
                wv = Worldview.load(wv_path)
                for kg in wv.knowledge_gaps:
                    gap = kg.to_gap()
                    if gap.topic not in seen_topics:
                        score_gap(gap, domain_velocity=velocity)
                        gaps.append(gap)
                        seen_topics.add(gap.topic)
        except Exception:
            pass

        # Load decision records from ThoughtStream logs
        decisions = []
        try:
            import json as _json

            from deepr.core.contracts import DecisionRecord

            log_dir = Path(f"data/experts/{self.name}/logs")
            if log_dir.exists():
                for json_file in sorted(log_dir.glob("decisions*.json"), reverse=True):
                    with open(json_file, encoding="utf-8") as f:
                        records = _json.load(f)
                    for rec_data in records:
                        decisions.append(DecisionRecord.from_dict(rec_data))
                    break  # Only load most recent
        except Exception:
            pass

        return ExpertManifest(
            expert_name=self.name,
            domain=self.domain or "",
            claims=claims,
            gaps=gaps,
            decisions=decisions,
            policies={
                "refresh_days": self.refresh_frequency_days,
                "budget_cap": self.monthly_learning_budget,
                "velocity": self.domain_velocity,
            },
        )

    # =========================================================================
    # Serialization (uses serializer module)
    # =========================================================================

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        # Sync from managers before serialization
        self._sync_budget_from_manager()
        return profile_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExpertProfile":
        """Create from dictionary."""
        kwargs = dict_to_profile_kwargs(data)
        return cls(**kwargs)


# Import ExpertStore for backwards compatibility
# New code should import from profile_store directly


def get_expert_system_message(
    knowledge_cutoff_date: Optional[datetime] = None,
    domain_velocity: str = "medium",
    worldview_summary: Optional[str] = None,
) -> str:
    """Generate expert system message with current date programmatically inserted."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_readable = datetime.now(timezone.utc).strftime("%B %d, %Y")

    cutoff_str = "UNKNOWN"
    days_old = "UNKNOWN"
    if knowledge_cutoff_date:
        cutoff_str = knowledge_cutoff_date.strftime("%Y-%m-%d")
        days_old = (datetime.now(timezone.utc) - knowledge_cutoff_date).days

    velocity_thresholds = {"slow": 180, "medium": 90, "fast": 30}
    threshold = velocity_thresholds.get(domain_velocity, 90)

    worldview_section = ""
    if worldview_summary:
        worldview_section = f"""

**YOUR WORLDVIEW AND BELIEFS:**
{worldview_summary}

You have actively synthesized your knowledge and formed beliefs based on evidence.
Reference your worldview when answering - speak from your beliefs, not just documents.
Express confidence levels and acknowledge knowledge gaps when relevant.
"""

    return f"""You are a specialized domain expert with access to a curated knowledge base
and the ability to conduct deep research when needed.
{worldview_section}

**IMPORTANT TEMPORAL CONTEXT:**
- Today's date: {today_readable} ({today})
- Your knowledge cutoff: {cutoff_str}
- Knowledge age: {days_old} days old
- Domain velocity: {domain_velocity} (refresh threshold: {threshold} days)
- Status: {"STALE - RESEARCH REQUIRED" if isinstance(days_old, int) and days_old > threshold else "FRESH"}

CORE PRINCIPLES - Beginner's Mind + Temporal Awareness:

1. **Intellectual Humility**
   - Say "I don't know" when your knowledge is uncertain or outdated
   - Never guess or extrapolate beyond your knowledge
   - Acknowledge the limits of your expertise

2. **TEMPORAL AWARENESS (CRITICAL)**
   - ALWAYS state your knowledge cutoff date at conversation start
   - Check document timestamps BEFORE citing them
   - For fast-moving domains: Documents >1 month old: Flag as potentially outdated
   - For medium-velocity domains: Documents >3 months old: Flag as potentially outdated
   - User asks for "current", "latest", or mentions a specific year: ALWAYS research
   - NEVER recommend deprecated services, APIs, or patterns

3. **Source Transparency**
   - Distinguish clearly between initial documents, research findings, and your synthesis
   - ALWAYS include timestamps when citing sources

4. **Research-First Approach for Freshness**
   - ALWAYS trigger research if your knowledge is outdated for the topic
   - Better to research and be accurate than fast and wrong

5. **Question Assumptions About Versions and Currency**
   - Challenge outdated patterns
   - Ask about version context
   - Admit limitations

6. **Depth Over Breadth + Freshness Over Speed**
   - Outdated advice is WORSE than no advice
   - Take time to get current information

Remember: Your value comes from CURRENT, accurate guidance. Giving advice based on
outdated patterns is harmful. Always bias toward researching when freshness is questionable.
"""


# For backwards compatibility
DEFAULT_EXPERT_SYSTEM_MESSAGE = get_expert_system_message()

# Re-export ExpertStore for backwards compatibility
# New code should import from profile_store directly
from deepr.experts.profile_store import PROFILE_SCHEMA_VERSION, ExpertStore

__all__ = [
    "DEFAULT_EXPERT_SYSTEM_MESSAGE",
    "PROFILE_SCHEMA_VERSION",
    "ExpertProfile",
    "ExpertStore",
    "get_expert_system_message",
]
