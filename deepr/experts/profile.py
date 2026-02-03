"""Expert profile management - metadata and configuration for domain experts.

This module provides the core ExpertProfile dataclass and ExpertStore for
persistence. Uses composition with specialized managers for cleaner separation:

- TemporalState: Tracks temporal awareness and activity timestamps
- FreshnessChecker: Evaluates knowledge freshness based on domain velocity
- BudgetManager: Handles monthly learning budget tracking
- ActivityTracker: Records conversations and research triggers

Requirements: 5.1, 5.7 - Refactored god class using composition
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from pathlib import Path
import json

# Security imports
from deepr.utils.security import sanitize_name, validate_path

# Composition imports
from deepr.experts.temporal import TemporalState
from deepr.experts.freshness import FreshnessChecker, FreshnessLevel
from deepr.experts.budget_manager import BudgetManager
from deepr.experts.activity_tracker import ActivityTracker
from deepr.experts.serializer import (
    profile_to_dict,
    dict_to_profile_kwargs,
    datetime_to_iso,
    iso_to_datetime
)


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
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Knowledge base metadata
    source_files: List[str] = field(default_factory=list)
    research_jobs: List[str] = field(default_factory=list)
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
    refresh_history: List[Dict] = field(default_factory=list)

    # Provider preferences
    provider: str = "openai"
    model: str = "gpt-5"
    
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
                created_at=self.created_at,
                last_activity=self.updated_at,
                last_learning=self.last_knowledge_refresh
            )
        
        # Freshness checker with domain velocity
        velocity_map = {"slow": 180, "medium": 90, "fast": 30}
        velocity_days = velocity_map.get(self.domain_velocity, 90)
        
        if self._freshness_checker is None:
            self._freshness_checker = FreshnessChecker(
                domain=self.domain or "general",
                velocity_days=velocity_days
            )
        
        # Budget manager
        if self._budget_manager is None:
            self._budget_manager = BudgetManager(
                monthly_budget=self.monthly_learning_budget,
                monthly_spending=self.monthly_spending,
                total_spending=self.total_research_cost,
                reset_date=self.monthly_spending_reset_date,
                refresh_history=self.refresh_history
            )
        
        # Activity tracker
        if self._activity_tracker is None:
            self._activity_tracker = ActivityTracker(
                conversations=self.conversations,
                research_triggered=self.research_triggered,
                last_activity=self.updated_at
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
    
    def record_activity(self, activity_type: str, details: Optional[Dict] = None):
        """Record an activity event.
        
        Args:
            activity_type: Type of activity (chat, research, etc.)
            details: Optional additional details
        """
        self.activity_tracker.record_activity(activity_type, details)
        self.updated_at = datetime.utcnow()
        
        # Sync counters back to profile for serialization
        self.conversations = self.activity_tracker.conversations
        self.research_triggered = self.activity_tracker.research_triggered

    # =========================================================================
    # Freshness checking (delegates to FreshnessChecker)
    # =========================================================================

    def is_knowledge_stale(self) -> bool:
        """Check if knowledge needs refreshing based on domain velocity."""
        return self.freshness_checker.is_stale(last_learning=self.knowledge_cutoff_date)

    def get_freshness_status(self) -> Dict[str, Any]:
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
                "action_required": f"Run: deepr expert learn {self.name} --budget 5"
            }
        
        status = self.freshness_checker.check(
            last_learning=self.knowledge_cutoff_date,
            last_activity=self.updated_at
        )
        
        status_map = {
            FreshnessLevel.FRESH: "fresh",
            FreshnessLevel.AGING: "aging",
            FreshnessLevel.STALE: "stale",
            FreshnessLevel.CRITICAL: "stale"
        }
        
        return {
            "status": status_map.get(status.level, "unknown"),
            "age_days": status.days_since_update,
            "threshold_days": status.threshold_days,
            "message": status.recommendation,
            "action_required": status.recommendation if status.needs_refresh() else None,
            "freshness_score": status.score
        }
    
    def get_staleness_details(self) -> Dict[str, Any]:
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
            "fresh": ("low", 0.2)
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
            "refresh_command": f"deepr expert learn {self.name} --budget {estimated_cost:.2f}"
        }
    
    def suggest_refresh(self) -> Optional[Dict[str, Any]]:
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
            "topics": self._suggest_refresh_topics()
        }
    
    def _suggest_refresh_topics(self) -> List[str]:
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
    
    def get_monthly_budget_status(self) -> Dict[str, Any]:
        """Get monthly learning budget status."""
        status = self.budget_manager.get_status()
        self._sync_budget_from_manager()
        return status
    
    def can_spend_learning_budget(self, amount: float) -> Tuple[bool, str]:
        """Check if spending amount is within monthly budget."""
        return self.budget_manager.can_spend(amount)
    
    def record_learning_spend(
        self,
        amount: float,
        operation: str,
        details: Optional[str] = None
    ):
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
    # Serialization (uses serializer module)
    # =========================================================================

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        # Sync from managers before serialization
        self._sync_budget_from_manager()
        return profile_to_dict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'ExpertProfile':
        """Create from dictionary."""
        kwargs = dict_to_profile_kwargs(data)
        return cls(**kwargs)


class ExpertStore:
    """Storage for expert profiles."""

    def __init__(self, base_path: str = "data/experts"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_expert_dir(self, name: str) -> Path:
        """Get directory path for expert with security validation."""
        safe_name = sanitize_name(name).lower()
        return validate_path(
            safe_name,
            base_dir=self.base_path,
            must_exist=False,
            allow_create=True
        )

    def _get_profile_path(self, name: str) -> Path:
        """Get file path for expert profile."""
        return self._get_expert_dir(name) / "profile.json"

    def get_documents_dir(self, name: str) -> Path:
        """Get documents directory for expert."""
        return self._get_expert_dir(name) / "documents"

    def get_knowledge_dir(self, name: str) -> Path:
        """Get knowledge directory for expert."""
        return self._get_expert_dir(name) / "knowledge"

    def get_conversations_dir(self, name: str) -> Path:
        """Get conversations directory for expert."""
        return self._get_expert_dir(name) / "conversations"

    def save(self, profile: ExpertProfile) -> None:
        """Save expert profile to disk."""
        profile.updated_at = datetime.utcnow()

        expert_dir = self._get_expert_dir(profile.name)
        expert_dir.mkdir(parents=True, exist_ok=True)
        (expert_dir / "documents").mkdir(exist_ok=True)
        (expert_dir / "knowledge").mkdir(exist_ok=True)
        (expert_dir / "conversations").mkdir(exist_ok=True)

        path = self._get_profile_path(profile.name)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(profile.to_dict(), f, indent=2)

    def load(self, name: str) -> Optional[ExpertProfile]:
        """Load expert profile from disk."""
        path = self._get_profile_path(name)
        if not path.exists():
            return None

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return ExpertProfile.from_dict(data)

    def list_all(self) -> List[ExpertProfile]:
        """List all expert profiles."""
        profiles = []
        for expert_dir in self.base_path.iterdir():
            if expert_dir.is_dir():
                profile_path = expert_dir / "profile.json"
                if profile_path.exists():
                    try:
                        with open(profile_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            profiles.append(ExpertProfile.from_dict(data))
                    except Exception as e:
                        logger.warning("Could not load %s: %s", profile_path, e)
        return sorted(profiles, key=lambda p: p.updated_at, reverse=True)

    def delete(self, name: str) -> bool:
        """Delete expert profile."""
        path = self._get_profile_path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, name: str) -> bool:
        """Check if expert exists."""
        return self._get_profile_path(name).exists()

    async def add_documents_to_vector_store(
        self,
        profile: ExpertProfile,
        file_paths: List[str],
        provider_client=None
    ) -> Dict[str, Any]:
        """Add documents to expert's vector store."""
        if not provider_client:
            from deepr.providers import create_provider
            from deepr.config import AppConfig
            config = AppConfig.from_env()
            provider = create_provider("openai", api_key=config.provider.openai_api_key)
            provider_client = provider.client

        results = {"uploaded": [], "failed": [], "skipped": []}

        for file_path in file_paths:
            path = Path(file_path)
            if str(file_path) in profile.source_files:
                results["skipped"].append(str(file_path))
                continue

            try:
                with open(path, 'rb') as f:
                    file_obj = await provider_client.files.create(file=f, purpose="assistants")
                await provider_client.vector_stores.files.create(
                    vector_store_id=profile.vector_store_id,
                    file_id=file_obj.id
                )
                profile.source_files.append(str(file_path))
                profile.total_documents += 1
                profile.last_knowledge_refresh = datetime.utcnow()
                results["uploaded"].append({"path": str(file_path), "file_id": file_obj.id})
            except Exception as e:
                results["failed"].append({"path": str(file_path), "error": str(e)})

        if results["uploaded"]:
            self.save(profile)
        return results

    async def refresh_expert_knowledge(self, name: str, provider_client=None) -> Dict[str, Any]:
        """Scan documents folder and add any missing files to vector store."""
        profile = self.load(name)
        if not profile:
            raise ValueError(f"Expert '{name}' not found")

        docs_dir = self.get_documents_dir(name)
        if not docs_dir.exists():
            return {"uploaded": [], "failed": [], "skipped": [], "message": "No documents directory found"}

        all_files = list(docs_dir.glob("*.md"))
        new_files = [str(f) for f in all_files if str(f) not in profile.source_files]

        if not new_files:
            return {"uploaded": [], "failed": [], "skipped": [], 
                    "message": f"All {len(all_files)} documents already in vector store"}

        results = await self.add_documents_to_vector_store(profile, new_files, provider_client)
        results["message"] = f"Found {len(new_files)} new documents out of {len(all_files)} total"
        return results


def get_expert_system_message(
    knowledge_cutoff_date: Optional[datetime] = None,
    domain_velocity: str = "medium",
    worldview_summary: Optional[str] = None
) -> str:
    """Generate expert system message with current date programmatically inserted."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    today_readable = datetime.utcnow().strftime("%B %d, %Y")

    cutoff_str = "UNKNOWN"
    days_old = "UNKNOWN"
    if knowledge_cutoff_date:
        cutoff_str = knowledge_cutoff_date.strftime("%Y-%m-%d")
        days_old = (datetime.utcnow() - knowledge_cutoff_date).days

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
