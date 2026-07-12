"""Expert system - persistent domain experts with agentic research capabilities.

Provides:
- ExpertProfile: Core expert metadata and configuration (profile.py)
- ExpertStore: Persistence layer with schema migrations (profile_store.py)
- BudgetManager: Monthly learning budget tracking
- ActivityTracker: Conversation and research counting
- FreshnessChecker: Knowledge freshness evaluation
- TemporalState: Activity timestamp tracking
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
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

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "PROFILE_SCHEMA_VERSION": (".profile_store", "PROFILE_SCHEMA_VERSION"),
    "ActivityTracker": (".activity_tracker", "ActivityTracker"),
    "Belief": (".synthesis", "Belief"),
    "BudgetManager": (".budget_manager", "BudgetManager"),
    "EmbeddingCache": (".embedding_cache", "EmbeddingCache"),
    "ExpertChatSession": (".chat", "ExpertChatSession"),
    "ExpertProfile": (".profile", "ExpertProfile"),
    "ExpertStore": (".profile_store", "ExpertStore"),
    "FreshnessChecker": (".freshness", "FreshnessChecker"),
    "FreshnessLevel": (".freshness", "FreshnessLevel"),
    "FreshnessStatus": (".freshness", "FreshnessStatus"),
    "KnowledgeGap": (".synthesis", "KnowledgeGap"),
    "KnowledgeSynthesizer": (".synthesis", "KnowledgeSynthesizer"),
    "ProfileSerializer": (".serializer", "ProfileSerializer"),
    "TemporalState": (".temporal", "TemporalState"),
    "Worldview": (".synthesis", "Worldview"),
    "migrate_profile_data": (".profile_store", "migrate_profile_data"),
    "start_chat_session": (".chat", "start_chat_session"),
}


def __getattr__(name: str) -> Any:
    """Resolve public expert exports without importing chat or NumPy eagerly."""
    spec = _LAZY_EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = spec
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Include lazy public exports in introspection without importing them."""
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


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
