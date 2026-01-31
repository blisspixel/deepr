"""Expert system - persistent domain experts with agentic research capabilities."""

from .embedding_cache import EmbeddingCache
from .profile import ExpertProfile, ExpertStore
from .chat import ExpertChatSession, start_chat_session
from .synthesis import KnowledgeSynthesizer, Worldview, Belief, KnowledgeGap

__all__ = [
    "EmbeddingCache",
    "ExpertProfile",
    "ExpertStore",
    "ExpertChatSession",
    "start_chat_session",
    "KnowledgeSynthesizer",
    "Worldview",
    "Belief",
    "KnowledgeGap",
]
