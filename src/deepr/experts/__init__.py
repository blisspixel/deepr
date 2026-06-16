"""Expert system - persistent domain experts with agentic research capabilities.

Provides:
- ExpertProfile: Core expert metadata and configuration (profile.py)
- ExpertStore: Persistence layer with schema migrations (profile_store.py)
- BudgetManager: Monthly learning budget tracking
- ActivityTracker: Conversation and research counting
- FreshnessChecker: Knowledge freshness evaluation
- TemporalState: Activity timestamp tracking
"""

from .activity_tracker import ActivityTracker
from .budget_manager import BudgetManager
from .chat import ExpertChatSession, start_chat_session
from .embedding_cache import EmbeddingCache
from .freshness import FreshnessChecker, FreshnessLevel, FreshnessStatus
from .profile import ExpertProfile
from .profile_store import PROFILE_SCHEMA_VERSION, ExpertStore, migrate_profile_data
from .serializer import ProfileSerializer
from .synthesis import Belief, KnowledgeGap, KnowledgeSynthesizer, Worldview
from .temporal import TemporalState

__all__ = [
    "PROFILE_SCHEMA_VERSION",
    "ActivityTracker",
    "Belief",
    # Composed managers
    "BudgetManager",
    # Utilities
    "EmbeddingCache",
    # Chat
    "ExpertChatSession",
    # Core profile
    "ExpertProfile",
    "ExpertStore",
    "FreshnessChecker",
    "FreshnessLevel",
    "FreshnessStatus",
    "KnowledgeGap",
    # Synthesis
    "KnowledgeSynthesizer",
    "ProfileSerializer",
    "TemporalState",
    "Worldview",
    "migrate_profile_data",
    "start_chat_session",
]
