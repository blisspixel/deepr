"""Expert system - persistent domain experts with agentic research capabilities.

Provides:
- ExpertProfile: Core expert metadata and configuration (profile.py)
- ExpertStore: Persistence layer with schema migrations (profile_store.py)
- BudgetManager: Monthly learning budget tracking
- ActivityTracker: Conversation and research counting
- FreshnessChecker: Knowledge freshness evaluation
- TemporalState: Activity timestamp tracking
"""

from .embedding_cache import EmbeddingCache
from .profile import ExpertProfile
from .profile_store import ExpertStore, PROFILE_SCHEMA_VERSION, migrate_profile_data
from .chat import ExpertChatSession, start_chat_session
from .synthesis import KnowledgeSynthesizer, Worldview, Belief, KnowledgeGap
from .budget_manager import BudgetManager
from .activity_tracker import ActivityTracker
from .freshness import FreshnessChecker, FreshnessLevel, FreshnessStatus
from .temporal import TemporalState
from .serializer import ProfileSerializer

__all__ = [
    # Core profile
    "ExpertProfile",
    "ExpertStore",
    "PROFILE_SCHEMA_VERSION",
    "migrate_profile_data",
    # Composed managers
    "BudgetManager",
    "ActivityTracker",
    "FreshnessChecker",
    "FreshnessLevel",
    "FreshnessStatus",
    "TemporalState",
    "ProfileSerializer",
    # Chat
    "ExpertChatSession",
    "start_chat_session",
    # Synthesis
    "KnowledgeSynthesizer",
    "Worldview",
    "Belief",
    "KnowledgeGap",
    # Utilities
    "EmbeddingCache",
]
