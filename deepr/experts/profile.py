"""Expert profile management - metadata and configuration for domain experts."""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
import json
import os


@dataclass
class ExpertProfile:
    """Profile for a domain expert.

    Combines vector store (for knowledge) with metadata (for behavior).
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
    max_tokens: int = 4000

    # Usage tracking
    conversations: int = 0
    research_triggered: int = 0
    total_research_cost: float = 0.0

    # Provider preferences
    provider: str = "openai"
    model: str = "chatgpt-5-latest"  # GPT-5 via Chat Completions (use Responses API for agentic)

    def is_knowledge_stale(self) -> bool:
        """Check if knowledge needs refreshing based on domain velocity."""
        if not self.knowledge_cutoff_date:
            return True  # No knowledge cutoff = needs learning

        from datetime import timedelta
        now = datetime.utcnow()
        age_days = (now - self.knowledge_cutoff_date).days

        # Velocity-based thresholds
        velocity_thresholds = {
            "slow": 180,  # Legal, compliance, fundamentals
            "medium": 90,  # General tech, business
            "fast": 30,   # AI/ML, cloud, frameworks
        }

        threshold = velocity_thresholds.get(self.domain_velocity, 90)
        return age_days > threshold

    def get_freshness_status(self) -> Dict[str, any]:
        """Get detailed freshness status."""
        if not self.knowledge_cutoff_date:
            return {
                "status": "incomplete",
                "message": "Expert needs initial learning curriculum",
                "action_required": "Run: deepr expert learn <name> --budget 5"
            }

        from datetime import timedelta
        now = datetime.utcnow()
        age_days = (now - self.knowledge_cutoff_date).days

        velocity_thresholds = {
            "slow": 180,
            "medium": 90,
            "fast": 30,
        }
        threshold = velocity_thresholds.get(self.domain_velocity, 90)

        if age_days > threshold:
            return {
                "status": "stale",
                "age_days": age_days,
                "threshold_days": threshold,
                "message": f"Knowledge is {age_days} days old (threshold: {threshold} days for {self.domain_velocity} domain)",
                "action_required": "Research refresh recommended"
            }
        elif age_days > threshold * 0.8:
            return {
                "status": "aging",
                "age_days": age_days,
                "threshold_days": threshold,
                "message": f"Knowledge approaching refresh threshold ({age_days}/{threshold} days)",
                "action_required": "Consider refresh soon"
            }
        else:
            return {
                "status": "fresh",
                "age_days": age_days,
                "threshold_days": threshold,
                "message": f"Knowledge is current ({age_days}/{threshold} days old)",
                "action_required": None
            }

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert datetime to ISO format
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        if data.get('knowledge_cutoff_date'):
            data['knowledge_cutoff_date'] = self.knowledge_cutoff_date.isoformat()
        if data.get('last_knowledge_refresh'):
            data['last_knowledge_refresh'] = self.last_knowledge_refresh.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> 'ExpertProfile':
        """Create from dictionary."""
        # Convert ISO format to datetime
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if isinstance(data.get('knowledge_cutoff_date'), str):
            data['knowledge_cutoff_date'] = datetime.fromisoformat(data['knowledge_cutoff_date'])
        if isinstance(data.get('last_knowledge_refresh'), str):
            data['last_knowledge_refresh'] = datetime.fromisoformat(data['last_knowledge_refresh'])
        return cls(**data)


class ExpertStore:
    """Storage for expert profiles."""

    def __init__(self, base_path: str = "data/experts"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_profile_path(self, name: str) -> Path:
        """Get file path for expert profile."""
        # Sanitize name for filename
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_').lower()
        return self.base_path / f"{safe_name}.json"

    def save(self, profile: ExpertProfile) -> None:
        """Save expert profile to disk."""
        profile.updated_at = datetime.utcnow()
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

        for path in self.base_path.glob("*.json"):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    profiles.append(ExpertProfile.from_dict(data))
            except Exception as e:
                # Skip corrupted profiles
                print(f"Warning: Could not load {path}: {e}")
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


# Default system message for experts
def get_expert_system_message(knowledge_cutoff_date: Optional[datetime] = None, domain_velocity: str = "medium") -> str:
    """Generate expert system message with current date programmatically inserted.

    Args:
        knowledge_cutoff_date: Latest timestamp in expert's knowledge base
        domain_velocity: slow/medium/fast - affects freshness requirements
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

    return f"""You are a specialized domain expert with access to a curated knowledge base
and the ability to conduct deep research when needed.

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
