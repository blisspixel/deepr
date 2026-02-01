"""Expert profile management - metadata and configuration for domain experts."""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
import json
import os

# Security imports
from deepr.utils.security import sanitize_name, validate_path, PathTraversalError

# Composition imports
from deepr.experts.temporal import TemporalState
from deepr.experts.freshness import FreshnessChecker, FreshnessLevel


@dataclass
class ExpertProfile:
    """Profile for a domain expert.

    Combines vector store (for knowledge) with metadata (for behavior).
    Uses composition with TemporalState and FreshnessChecker for cleaner separation.
    """
    name: str
    vector_store_id: str
    description: Optional[str] = None
    domain: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Knowledge base metadata
    source_files: List[str] = field(default_factory=list)
    research_jobs: List[str] = field(default_factory=list)  # IDs of research added to knowledge
    total_documents: int = 0

    # Temporal awareness - CRITICAL for freshness
    knowledge_cutoff_date: Optional[datetime] = None  # Latest doc/research timestamp
    last_knowledge_refresh: Optional[datetime] = None  # Last time knowledge was updated
    refresh_frequency_days: int = 90  # Default: refresh every 90 days
    domain_velocity: str = "medium"  # slow/medium/fast - affects refresh urgency

    # Domain velocity guidelines:
    # - "slow": Legal, compliance, math, physics (180 day refresh)
    # - "medium": General tech, business, architecture (90 day refresh)
    # - "fast": AI/ML, cloud services, web frameworks (30 day refresh)

    # Behavior configuration
    system_message: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None  # No limit for GPT-5

    # Usage tracking
    conversations: int = 0
    research_triggered: int = 0
    total_research_cost: float = 0.0
    
    # Monthly learning budget for autonomous updates
    monthly_learning_budget: float = 5.0  # Default $5/month for autonomous learning
    monthly_spending: float = 0.0  # Current month's spending
    monthly_spending_reset_date: Optional[datetime] = None  # When to reset monthly spending
    refresh_history: List[Dict] = field(default_factory=list)  # History of refresh operations

    # Provider preferences
    provider: str = "openai"
    model: str = "gpt-5"  # GPT-5 with tool calling for RAG (NOT deprecated Assistants API)
    
    # Composed components (not serialized directly)
    _temporal_state: Optional[TemporalState] = field(default=None, repr=False)
    _freshness_checker: Optional[FreshnessChecker] = field(default=None, repr=False)
    
    def __post_init__(self):
        """Initialize composed components."""
        self._init_components()
    
    def _init_components(self):
        """Initialize TemporalState and FreshnessChecker."""
        # Initialize temporal state
        if self._temporal_state is None:
            self._temporal_state = TemporalState(
                created_at=self.created_at,
                last_activity=self.updated_at,
                last_learning=self.last_knowledge_refresh
            )
        
        # Initialize freshness checker with domain velocity
        velocity_map = {"slow": 180, "medium": 90, "fast": 30}
        velocity_days = velocity_map.get(self.domain_velocity, 90)
        
        if self._freshness_checker is None:
            self._freshness_checker = FreshnessChecker(
                domain=self.domain or "general",
                velocity_days=velocity_days
            )
    
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
    
    def record_activity(self, activity_type: str, details: Optional[Dict] = None):
        """Record an activity using TemporalState.
        
        Args:
            activity_type: Type of activity
            details: Optional details
        """
        self.temporal_state.record_activity(activity_type, details)
        self.updated_at = datetime.utcnow()
        
        if activity_type == "chat":
            self.conversations += 1
        elif activity_type == "research":
            self.research_triggered += 1

    def is_knowledge_stale(self) -> bool:
        """Check if knowledge needs refreshing based on domain velocity.
        
        Uses FreshnessChecker for consistent logic.
        """
        return self.freshness_checker.is_stale(last_learning=self.knowledge_cutoff_date)

    def get_freshness_status(self) -> Dict[str, any]:
        """Get detailed freshness status using FreshnessChecker."""
        status = self.freshness_checker.check(
            last_learning=self.knowledge_cutoff_date,
            last_activity=self.updated_at
        )
        
        # Convert to legacy format for backward compatibility
        if status.level == FreshnessLevel.CRITICAL and self.knowledge_cutoff_date is None:
            return {
                "status": "incomplete",
                "message": "Expert needs initial learning curriculum",
                "action_required": f"Run: deepr expert learn {self.name} --budget 5"
            }
        
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
    
    def get_staleness_details(self) -> Dict[str, any]:
        """Get detailed staleness information for continuous self-improvement.
        
        Returns comprehensive staleness analysis including:
        - Knowledge age and threshold
        - Domain velocity impact
        - Refresh cost estimate
        - Recommended refresh topics
        
        Returns:
            Dictionary with detailed staleness information
        """
        freshness = self.get_freshness_status()
        
        # Calculate refresh cost estimate based on domain
        base_cost = 0.50  # Base cost for refresh research
        velocity_multipliers = {
            "slow": 0.5,   # Less frequent, simpler refresh
            "medium": 1.0,  # Standard refresh
            "fast": 2.0,   # More comprehensive refresh needed
        }
        multiplier = velocity_multipliers.get(self.domain_velocity, 1.0)
        estimated_cost = base_cost * multiplier
        
        # Determine urgency level
        if freshness["status"] == "stale":
            urgency = "high"
            urgency_score = 1.0
        elif freshness["status"] == "aging":
            urgency = "medium"
            urgency_score = 0.6
        elif freshness["status"] == "incomplete":
            urgency = "critical"
            urgency_score = 1.0
        else:
            urgency = "low"
            urgency_score = 0.2
        
        # Calculate days until stale
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
            "last_refresh": self.last_knowledge_refresh.isoformat() if self.last_knowledge_refresh else None,
            "knowledge_cutoff": self.knowledge_cutoff_date.isoformat() if self.knowledge_cutoff_date else None,
            "message": freshness.get("message"),
            "action_required": freshness.get("action_required"),
            "refresh_command": f"deepr expert learn {self.name} --budget {estimated_cost:.2f}"
        }
    
    def suggest_refresh(self) -> Optional[Dict[str, any]]:
        """Suggest a knowledge refresh if needed.
        
        Returns refresh suggestion with cost estimate, or None if not needed.
        
        Returns:
            Dictionary with refresh suggestion or None
        """
        staleness = self.get_staleness_details()
        
        if not staleness["is_stale"] and staleness["urgency"] == "low":
            return None
        
        # Build refresh suggestion
        suggestion = {
            "expert_name": self.name,
            "domain": self.domain,
            "reason": staleness["message"],
            "urgency": staleness["urgency"],
            "estimated_cost": staleness["estimated_refresh_cost"],
            "command": staleness["refresh_command"],
            "topics": self._suggest_refresh_topics()
        }
        
        return suggestion
    
    def _suggest_refresh_topics(self) -> List[str]:
        """Suggest topics for refresh based on domain.
        
        Returns:
            List of suggested refresh topics
        """
        # Base topics from domain
        topics = []
        
        if self.domain:
            topics.append(f"Latest developments in {self.domain}")
            topics.append(f"Recent changes to {self.domain} best practices")
        
        # Add velocity-specific topics
        if self.domain_velocity == "fast":
            topics.append("Breaking news and announcements")
            topics.append("New tools and frameworks")
        elif self.domain_velocity == "medium":
            topics.append("Industry trends and updates")
        
        return topics[:5]  # Limit to 5 topics
    
    def get_monthly_budget_status(self) -> Dict[str, any]:
        """Get monthly learning budget status.
        
        Returns:
            Dictionary with budget status
        """
        self._check_monthly_reset()
        
        remaining = self.monthly_learning_budget - self.monthly_spending
        usage_percent = (self.monthly_spending / self.monthly_learning_budget * 100) if self.monthly_learning_budget > 0 else 0
        
        return {
            "monthly_budget": self.monthly_learning_budget,
            "monthly_spent": self.monthly_spending,
            "monthly_remaining": max(0, remaining),
            "usage_percent": usage_percent,
            "reset_date": self.monthly_spending_reset_date.isoformat() if self.monthly_spending_reset_date else None,
            "can_spend": remaining > 0,
            "refresh_count_this_month": len([r for r in self.refresh_history if self._is_this_month(r.get("timestamp"))])
        }
    
    def can_spend_learning_budget(self, amount: float) -> tuple:
        """Check if spending amount is within monthly budget.
        
        Args:
            amount: Amount to spend
            
        Returns:
            Tuple of (can_spend: bool, reason: str)
        """
        self._check_monthly_reset()
        
        remaining = self.monthly_learning_budget - self.monthly_spending
        
        if amount <= 0:
            return True, "No cost"
        
        if remaining <= 0:
            return False, f"Monthly learning budget exhausted (${self.monthly_learning_budget:.2f} limit)"
        
        if amount > remaining:
            return False, f"Amount ${amount:.2f} exceeds remaining budget ${remaining:.2f}"
        
        return True, f"Within budget (${remaining:.2f} remaining after)"
    
    def record_learning_spend(self, amount: float, operation: str, details: Optional[str] = None):
        """Record spending against monthly learning budget.
        
        Args:
            amount: Amount spent
            operation: Type of operation (refresh, research, etc.)
            details: Optional details about the operation
        """
        self._check_monthly_reset()
        
        self.monthly_spending += amount
        self.total_research_cost += amount
        
        # Record in refresh history
        self.refresh_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "operation": operation,
            "amount": amount,
            "details": details,
            "budget_remaining": self.monthly_learning_budget - self.monthly_spending
        })
        
        # Keep only last 100 entries
        if len(self.refresh_history) > 100:
            self.refresh_history = self.refresh_history[-100:]
    
    def _check_monthly_reset(self):
        """Check and reset monthly spending if new month."""
        now = datetime.utcnow()
        
        if self.monthly_spending_reset_date is None:
            # Initialize reset date to first of next month
            if now.month == 12:
                self.monthly_spending_reset_date = datetime(now.year + 1, 1, 1)
            else:
                self.monthly_spending_reset_date = datetime(now.year, now.month + 1, 1)
            return
        
        if now >= self.monthly_spending_reset_date:
            # Reset spending
            self.monthly_spending = 0.0
            
            # Set next reset date
            if now.month == 12:
                self.monthly_spending_reset_date = datetime(now.year + 1, 1, 1)
            else:
                self.monthly_spending_reset_date = datetime(now.year, now.month + 1, 1)
    
    def _is_this_month(self, timestamp_str: Optional[str]) -> bool:
        """Check if timestamp is in current month.
        
        Args:
            timestamp_str: ISO format timestamp string
            
        Returns:
            True if timestamp is in current month
        """
        if not timestamp_str:
            return False
        
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            now = datetime.utcnow()
            return timestamp.year == now.year and timestamp.month == now.month
        except Exception:
            return False

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization.
        
        Excludes composed components (_temporal_state, _freshness_checker)
        which are runtime-only and reconstructed on load.
        """
        data = asdict(self)
        
        # Remove composed components (not serialized)
        data.pop('_temporal_state', None)
        data.pop('_freshness_checker', None)
        
        # Convert datetime to ISO format
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        if data.get('knowledge_cutoff_date'):
            data['knowledge_cutoff_date'] = self.knowledge_cutoff_date.isoformat()
        if data.get('last_knowledge_refresh'):
            data['last_knowledge_refresh'] = self.last_knowledge_refresh.isoformat()
        if data.get('monthly_spending_reset_date'):
            data['monthly_spending_reset_date'] = self.monthly_spending_reset_date.isoformat()
        
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'ExpertProfile':
        """Create from dictionary.
        
        Handles datetime conversion and removes any composed component
        fields that may have been accidentally serialized.
        """
        # Make a copy to avoid modifying the original
        data = data.copy()
        
        # Remove composed components if present (they're reconstructed in __post_init__)
        data.pop('_temporal_state', None)
        data.pop('_freshness_checker', None)
        
        # Convert ISO format to datetime
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if isinstance(data.get('knowledge_cutoff_date'), str):
            data['knowledge_cutoff_date'] = datetime.fromisoformat(data['knowledge_cutoff_date'])
        if isinstance(data.get('last_knowledge_refresh'), str):
            data['last_knowledge_refresh'] = datetime.fromisoformat(data['last_knowledge_refresh'])
        if isinstance(data.get('monthly_spending_reset_date'), str):
            data['monthly_spending_reset_date'] = datetime.fromisoformat(data['monthly_spending_reset_date'])
        
        return cls(**data)


class ExpertStore:
    """Storage for expert profiles."""

    def __init__(self, base_path: str = "data/experts"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_expert_dir(self, name: str) -> Path:
        """Get directory path for expert with security validation."""
        # Sanitize name using security utilities
        safe_name = sanitize_name(name).lower()

        # Validate path doesn't escape base directory
        expert_path = validate_path(
            safe_name,
            base_dir=self.base_path,
            must_exist=False,
            allow_create=True
        )

        return expert_path

    def _get_profile_path(self, name: str) -> Path:
        """Get file path for expert profile.

        New structure: data/experts/[expert_name]/profile.json
        """
        return self._get_expert_dir(name) / "profile.json"

    def get_documents_dir(self, name: str) -> Path:
        """Get documents directory for expert."""
        return self._get_expert_dir(name) / "documents"

    def get_knowledge_dir(self, name: str) -> Path:
        """Get knowledge directory for expert (temporal knowledge graph)."""
        return self._get_expert_dir(name) / "knowledge"

    def get_conversations_dir(self, name: str) -> Path:
        """Get conversations directory for expert."""
        return self._get_expert_dir(name) / "conversations"

    def save(self, profile: ExpertProfile) -> None:
        """Save expert profile to disk with new folder structure."""
        profile.updated_at = datetime.utcnow()

        # Create expert directory structure if it doesn't exist
        expert_dir = self._get_expert_dir(profile.name)
        expert_dir.mkdir(parents=True, exist_ok=True)
        (expert_dir / "documents").mkdir(exist_ok=True)
        (expert_dir / "knowledge").mkdir(exist_ok=True)
        (expert_dir / "conversations").mkdir(exist_ok=True)

        # Save profile
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
        """List all expert profiles from new folder structure."""
        profiles = []

        # Look for profile.json files in subdirectories
        for expert_dir in self.base_path.iterdir():
            if expert_dir.is_dir():
                profile_path = expert_dir / "profile.json"
                if profile_path.exists():
                    try:
                        with open(profile_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            profiles.append(ExpertProfile.from_dict(data))
                    except Exception as e:
                        # Skip corrupted profiles
                        print(f"Warning: Could not load {profile_path}: {e}")
                        continue

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
        provider_client = None
    ) -> Dict[str, any]:
        """Add documents to expert's vector store.

        Args:
            profile: Expert profile
            file_paths: List of file paths to upload
            provider_client: OpenAI client (optional, will create if not provided)

        Returns:
            Dict with upload results
        """
        from pathlib import Path

        if not provider_client:
            from deepr.providers import create_provider
            from deepr.config import AppConfig
            config = AppConfig.from_env()
            openai_api_key = config.provider.openai_api_key
            provider = create_provider("openai", api_key=openai_api_key)
            provider_client = provider.client

        results = {
            "uploaded": [],
            "failed": [],
            "skipped": []
        }

        for file_path in file_paths:
            path = Path(file_path)

            # Check if already added
            if str(file_path) in profile.source_files:
                results["skipped"].append(str(file_path))
                continue

            try:
                # Upload file to OpenAI
                with open(path, 'rb') as f:
                    file_obj = await provider_client.files.create(
                        file=f,
                        purpose="assistants"
                    )

                # Attach to vector store
                await provider_client.vector_stores.files.create(
                    vector_store_id=profile.vector_store_id,
                    file_id=file_obj.id
                )

                # Update profile
                profile.source_files.append(str(file_path))
                profile.total_documents += 1
                profile.last_knowledge_refresh = datetime.utcnow()

                results["uploaded"].append({
                    "path": str(file_path),
                    "file_id": file_obj.id
                })

            except Exception as e:
                results["failed"].append({
                    "path": str(file_path),
                    "error": str(e)
                })

        # Save updated profile
        if results["uploaded"]:
            self.save(profile)

        return results

    async def refresh_expert_knowledge(
        self,
        name: str,
        provider_client = None
    ) -> Dict[str, any]:
        """Scan documents folder and add any missing files to vector store.

        Args:
            name: Expert name
            provider_client: OpenAI client (optional)

        Returns:
            Dict with refresh results
        """
        from pathlib import Path

        profile = self.load(name)
        if not profile:
            raise ValueError(f"Expert '{name}' not found")

        # Get documents directory
        docs_dir = self.get_documents_dir(name)
        if not docs_dir.exists():
            return {
                "uploaded": [],
                "failed": [],
                "skipped": [],
                "message": "No documents directory found"
            }

        # Find all markdown files in documents directory
        all_files = list(docs_dir.glob("*.md"))

        # Filter to files not in source_files
        new_files = [
            str(f) for f in all_files
            if str(f) not in profile.source_files
        ]

        if not new_files:
            return {
                "uploaded": [],
                "failed": [],
                "skipped": [],
                "message": f"All {len(all_files)} documents already in vector store"
            }

        # Upload new files
        results = await self.add_documents_to_vector_store(
            profile, new_files, provider_client
        )

        results["message"] = f"Found {len(new_files)} new documents out of {len(all_files)} total"

        return results


# Default system message for experts
def get_expert_system_message(
    knowledge_cutoff_date: Optional[datetime] = None,
    domain_velocity: str = "medium",
    worldview_summary: Optional[str] = None
) -> str:
    """Generate expert system message with current date programmatically inserted.

    Args:
        knowledge_cutoff_date: Latest timestamp in expert's knowledge base
        domain_velocity: slow/medium/fast - affects freshness requirements
        worldview_summary: Optional synthesized worldview with beliefs and meta-awareness
    """
    from datetime import datetime

    today = datetime.utcnow().strftime("%Y-%m-%d")
    today_readable = datetime.utcnow().strftime("%B %d, %Y")

    cutoff_str = "UNKNOWN"
    days_old = "UNKNOWN"
    if knowledge_cutoff_date:
        cutoff_str = knowledge_cutoff_date.strftime("%Y-%m-%d")
        days_old = (datetime.utcnow() - knowledge_cutoff_date).days

    velocity_thresholds = {
        "slow": 180,
        "medium": 90,
        "fast": 30,
    }
    threshold = velocity_thresholds.get(domain_velocity, 90)

    # Add worldview section if exists
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
   - For fast-moving domains (AI, cloud services, frameworks):
     * Documents >1 month old: Flag as potentially outdated
     * Documents >3 months old: MUST research before citing
   - For medium-velocity domains (general tech, business):
     * Documents >3 months old: Flag as potentially outdated
     * Documents >6 months old: MUST research before citing
   - User asks for "current", "latest", or mentions a specific year: ALWAYS research
   - NEVER recommend deprecated services, APIs, or patterns
   - When in doubt: "My knowledge is from [date]. Let me research current state..."

3. **Source Transparency**
   - Distinguish clearly between:
     * Initial documents: "According to [document name, dated YYYY-MM]..."
     * Research findings: "I researched this on [date] and found..."
     * Your synthesis: "Based on combining [sources with dates]..."
   - ALWAYS include timestamps when citing sources
   - Example: "According to azure-landing-zones.pdf (March 2025), the pattern was..."

4. **Research-First Approach for Freshness**
   - ALWAYS trigger research if:
     * Your documents are >90 days old for the specific topic
     * User asks for "latest", "current", "best practices", or specific recent date
     * Topic is a cloud service, API, or framework (these change monthly)
     * You detect potential deprecation or version conflicts
   - Say: "My knowledge is from [date]. This domain changes rapidly. Let me research current state..."
   - Wait for research to complete before answering

5. **Question Assumptions About Versions and Currency**
   - Challenge outdated patterns: "That pattern was common previously, but let me verify current best practices..."
   - Ask about version context: "Are you using version X or the latest version Y?"
   - Admit limitations: "My docs don't cover changes after [date]. I should research..."

6. **Depth Over Breadth + Freshness Over Speed**
   - Better to research and be accurate than fast and wrong
   - Outdated advice is WORSE than no advice
   - Take time to get current information
   - Users care about correctness more than speed

MANDATORY RESEARCH TRIGGERS:

- Your knowledge base doesn't cover the topic
- Your knowledge is >90 days old for medium-velocity domains
- Your knowledge is >30 days old for fast-velocity domains (AI, cloud, frameworks)
- User asks for "current", "latest", "2025", or any future date
- User mentions a service/API version you don't recognize
- You detect deprecated patterns in your knowledge
- Complex questions requiring multiple perspectives
- User explicitly requests research

FRESHNESS CHECK PROCESS (Use this EVERY TIME):

1. User asks question
2. Check your knowledge base
3. **Check timestamps on relevant documents**
4. Calculate age: days_old = today - document_date
5. Compare to domain velocity threshold:
   - Fast domains (AI/ML, cloud): >30 days = research required
   - Medium domains (tech, business): >90 days = research required
   - Slow domains (legal, compliance): >180 days = acceptable
6. If age > threshold: "My knowledge is [X] days old. This domain changes rapidly. Let me research..."
7. Trigger research and wait
8. Respond with fresh, current information
9. Update your knowledge base

Remember: Your value comes from CURRENT, accurate guidance. Giving advice based on
outdated patterns is harmful. Always bias toward researching when freshness is questionable.

If user complains about research delays: Explain that accuracy requires current information,
and researching for 10 minutes is better than implementing a deprecated pattern that wastes hours.
"""


# For backwards compatibility - calls function with defaults
DEFAULT_EXPERT_SYSTEM_MESSAGE = get_expert_system_message()
