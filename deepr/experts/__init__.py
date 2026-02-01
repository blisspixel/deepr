"""Expert system - persistent domain experts with agentic research capabilities.

Provides:
- ExpertProfile: Core expert metadata and configuration
- ExpertStore: Persistence layer for expert profiles
- BudgetManager: Monthly learning budget tracking
- ActivityTracker: Conversation and research counting
- FreshnessChecker: Knowledge freshness evaluation
- TemporalState: Activity timestamp tracking
"""

from .embedding_cache import EmbeddingCache
from .profile import ExpertProfile, ExpertStore
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
