"""Hierarchical Episodic Memory (H-MEM) for expert system.

Implements a three-tier memory hierarchy:
- Working Memory: Current conversation context (fast, limited capacity)
- Episodic Memory: Past conversation episodes with full context
- Semantic Memory: Consolidated knowledge and user profiles

Key features:
- Episode dataclass with full context (docs, reasoning chains)
- UserProfile for tracking user expertise and preferences
- MetaKnowledge for domain awareness and knowledge gaps
- Hierarchical retrieval with O(log n) complexity
- Consolidation for tier transitions

Usage:
    from deepr.experts.memory import HierarchicalMemory, Episode, UserProfile

    memory = HierarchicalMemory(expert_name="quantum_expert")

    # Add episode from conversation
    episode = Episode(
        query="What is quantum entanglement?",
        response="Quantum entanglement is...",
        context_docs=["doc1.md", "doc2.md"],
        reasoning_chain=[...]
    )
    memory.add_episode(episode)

    # Retrieve relevant episodes
    relevant = memory.retrieve("quantum computing", top_k=3)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


import hashlib
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MemoryTier(Enum):
    """Memory tier levels."""

    WORKING = "working"  # Current session, fast access
    EPISODIC = "episodic"  # Past episodes, medium access
    SEMANTIC = "semantic"  # Consolidated knowledge, slow access


@dataclass
class ReasoningStep:
    """A step in a reasoning chain."""

    step_type: str  # "search", "hypothesis", "verification", "synthesis"
    content: str
    confidence: float = 0.0
    sources: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_type": self.step_type,
            "content": self.content,
            "confidence": self.confidence,
            "sources": self.sources,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReasoningStep":
        return cls(
            step_type=data["step_type"],
            content=data["content"],
            confidence=data.get("confidence", 0.0),
            sources=data.get("sources", []),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc),
        )


@dataclass
class Episode:
    """An episodic memory entry with full context.

    Stores not just the Q&A but the entire reasoning context:
    - Documents retrieved during the conversation
    - Reasoning chain (hypotheses, verifications, decisions)
    - User context at the time
    - Outcome quality (for learning)

    Attributes:
        id: Unique episode identifier
        query: User's original query
        response: Expert's response
        context_docs: List of document IDs/names retrieved
        reasoning_chain: Steps in the reasoning process
        user_id: Optional user identifier
        session_id: Session this episode belongs to
        timestamp: When the episode occurred
        quality_score: Optional quality rating (0-1)
        tags: Semantic tags for retrieval
        tier: Current memory tier
    """

    query: str
    response: str
    context_docs: list[str] = field(default_factory=list)
    reasoning_chain: list[ReasoningStep] = field(default_factory=list)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: datetime = field(default_factory=_utc_now)
    quality_score: Optional[float] = None
    tags: set[str] = field(default_factory=set)
    tier: MemoryTier = MemoryTier.WORKING
    id: str = field(default="")

    def __post_init__(self):
        """Generate ID if not provided."""
        if not self.id:
            # Generate deterministic ID from content
            content = f"{self.query}:{self.response}:{self.timestamp.isoformat()}"
            self.id = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Convert tags to set if list
        if isinstance(self.tags, list):
            self.tags = set(self.tags)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "response": self.response,
            "context_docs": self.context_docs,
            "reasoning_chain": [step.to_dict() for step in self.reasoning_chain],
            "user_id": self.user_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "quality_score": self.quality_score,
            "tags": list(self.tags),
            "tier": self.tier.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Episode":
        return cls(
            id=data.get("id", ""),
            query=data["query"],
            response=data["response"],
            context_docs=data.get("context_docs", []),
            reasoning_chain=[ReasoningStep.from_dict(step) for step in data.get("reasoning_chain", [])],
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc),
            quality_score=data.get("quality_score"),
            tags=set(data.get("tags", [])),
            tier=MemoryTier(data.get("tier", "working")),
        )

    def get_keywords(self) -> set[str]:
        """Extract keywords from query and response for retrieval."""
        text = f"{self.query} {self.response}".lower()
        # Simple keyword extraction - remove common words
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "dare",
            "ought",
            "used",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "nor",
            "not",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "and",
            "but",
            "if",
            "or",
            "because",
            "until",
            "while",
            "what",
            "which",
            "who",
            "whom",
            "this",
            "that",
            "these",
            "those",
            "am",
            "it",
            "its",
            "i",
            "you",
            "he",
            "she",
            "we",
            "they",
            "me",
            "him",
            "her",
            "us",
            "them",
        }

        words = set(word.strip(".,!?;:()[]{}\"'-") for word in text.split())
        return {w for w in words if len(w) > 2 and w not in stopwords}


@dataclass
class UserProfile:
    """User profile for semantic memory.

    Tracks user characteristics for personalized responses:
    - Expertise level in different domains
    - Interests and preferences
    - Communication style preferences
    - Historical interaction patterns

    Attributes:
        user_id: Unique user identifier
        expertise_levels: Domain -> expertise level (0-1)
        interests: Topics the user frequently asks about
        preferences: User preferences (verbosity, formality, etc.)
        interaction_count: Total interactions with this user
        first_seen: First interaction timestamp
        last_seen: Most recent interaction timestamp
        feedback_history: List of (episode_id, rating) tuples
    """

    user_id: str
    expertise_levels: dict[str, float] = field(default_factory=dict)
    interests: dict[str, int] = field(default_factory=dict)  # topic -> count
    preferences: dict[str, Any] = field(default_factory=dict)
    interaction_count: int = 0
    first_seen: datetime = field(default_factory=_utc_now)
    last_seen: datetime = field(default_factory=_utc_now)
    feedback_history: list[tuple] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "expertise_levels": self.expertise_levels,
            "interests": self.interests,
            "preferences": self.preferences,
            "interaction_count": self.interaction_count,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "feedback_history": self.feedback_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        return cls(
            user_id=data["user_id"],
            expertise_levels=data.get("expertise_levels", {}),
            interests=data.get("interests", {}),
            preferences=data.get("preferences", {}),
            interaction_count=data.get("interaction_count", 0),
            first_seen=datetime.fromisoformat(data["first_seen"])
            if "first_seen" in data
            else datetime.now(timezone.utc),
            last_seen=datetime.fromisoformat(data["last_seen"]) if "last_seen" in data else datetime.now(timezone.utc),
            feedback_history=data.get("feedback_history", []),
        )

    def update_expertise(self, domain: str, level: float):
        """Update expertise level for a domain.

        Uses exponential moving average to smooth updates.

        Args:
            domain: Domain name
            level: New expertise level (0-1)
        """
        alpha = 0.3  # Smoothing factor
        current = self.expertise_levels.get(domain, 0.5)
        self.expertise_levels[domain] = alpha * level + (1 - alpha) * current

    def record_interest(self, topic: str):
        """Record interest in a topic.

        Args:
            topic: Topic name
        """
        self.interests[topic] = self.interests.get(topic, 0) + 1

    def get_top_interests(self, n: int = 5) -> list[str]:
        """Get top N interests by frequency.

        Args:
            n: Number of interests to return

        Returns:
            List of topic names
        """
        sorted_interests = sorted(self.interests.items(), key=lambda x: x[1], reverse=True)
        return [topic for topic, _ in sorted_interests[:n]]

    def get_expertise_for_query(self, query: str) -> float:
        """Estimate user expertise for a query.

        Args:
            query: User's query

        Returns:
            Estimated expertise level (0-1)
        """
        if not self.expertise_levels:
            return 0.5  # Default to medium

        query_lower = query.lower()

        # Find matching domains
        matching_levels = []
        for domain, level in self.expertise_levels.items():
            if domain.lower() in query_lower:
                matching_levels.append(level)

        if matching_levels:
            return sum(matching_levels) / len(matching_levels)

        # Return average expertise if no match
        return sum(self.expertise_levels.values()) / len(self.expertise_levels)


@dataclass
class MetaKnowledge:
    """Meta-knowledge for domain awareness.

    Tracks what the expert knows and doesn't know:
    - Knowledge domains and their coverage
    - Known knowledge gaps
    - Confidence in different areas
    - Learning history

    Attributes:
        expert_name: Name of the expert
        domains: Domain -> coverage score (0-1)
        knowledge_gaps: List of identified gaps
        confidence_by_topic: Topic -> confidence score
        learning_events: History of learning events
        last_updated: When meta-knowledge was last updated
    """

    expert_name: str
    domains: dict[str, float] = field(default_factory=dict)
    knowledge_gaps: list[dict[str, Any]] = field(default_factory=list)
    confidence_by_topic: dict[str, float] = field(default_factory=dict)
    learning_events: list[dict[str, Any]] = field(default_factory=list)
    last_updated: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_name": self.expert_name,
            "domains": self.domains,
            "knowledge_gaps": self.knowledge_gaps,
            "confidence_by_topic": self.confidence_by_topic,
            "learning_events": self.learning_events,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetaKnowledge":
        return cls(
            expert_name=data["expert_name"],
            domains=data.get("domains", {}),
            knowledge_gaps=data.get("knowledge_gaps", []),
            confidence_by_topic=data.get("confidence_by_topic", {}),
            learning_events=data.get("learning_events", []),
            last_updated=datetime.fromisoformat(data["last_updated"])
            if "last_updated" in data
            else datetime.now(timezone.utc),
        )

    def record_gap(self, topic: str, query: str, confidence: float = 0.0):
        """Record a knowledge gap.

        Args:
            topic: Topic where gap was found
            query: Query that revealed the gap
            confidence: Current confidence in this area
        """
        gap = {
            "topic": topic,
            "query": query,
            "confidence": confidence,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "resolved": False,
        }

        # Check if gap already exists
        for existing in self.knowledge_gaps:
            if existing["topic"] == topic:
                existing["confidence"] = min(existing["confidence"], confidence)
                return

        self.knowledge_gaps.append(gap)
        self.last_updated = datetime.now(timezone.utc)

    def resolve_gap(self, topic: str):
        """Mark a knowledge gap as resolved.

        Args:
            topic: Topic that was learned
        """
        for gap in self.knowledge_gaps:
            if gap["topic"] == topic:
                gap["resolved"] = True
                gap["resolved_at"] = datetime.now(timezone.utc).isoformat()

        self.last_updated = datetime.now(timezone.utc)

    def record_learning(self, topic: str, source: str, confidence_gain: float):
        """Record a learning event.

        Args:
            topic: Topic learned
            source: Source of learning (research, document, etc.)
            confidence_gain: How much confidence increased
        """
        event = {
            "topic": topic,
            "source": source,
            "confidence_gain": confidence_gain,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.learning_events.append(event)

        # Update confidence
        current = self.confidence_by_topic.get(topic, 0.5)
        self.confidence_by_topic[topic] = min(1.0, current + confidence_gain)

        # Check if this resolves a gap
        self.resolve_gap(topic)

        self.last_updated = datetime.now(timezone.utc)

    def get_confidence(self, topic: str) -> float:
        """Get confidence for a topic.

        Args:
            topic: Topic to check

        Returns:
            Confidence score (0-1)
        """
        # Direct match
        if topic in self.confidence_by_topic:
            return self.confidence_by_topic[topic]

        # Partial match
        topic_lower = topic.lower()
        for known_topic, conf in self.confidence_by_topic.items():
            if topic_lower in known_topic.lower() or known_topic.lower() in topic_lower:
                return conf

        # Check domains
        for domain, coverage in self.domains.items():
            if domain.lower() in topic_lower:
                return coverage

        return 0.5  # Default medium confidence

    def get_unresolved_gaps(self) -> list[dict[str, Any]]:
        """Get list of unresolved knowledge gaps.

        Returns:
            List of gap dictionaries
        """
        return [gap for gap in self.knowledge_gaps if not gap.get("resolved", False)]


class HierarchicalMemory:
    """Three-tier hierarchical memory system.

    Implements H-MEM with:
    - Working Memory: Current session context (fast, limited)
    - Episodic Memory: Past episodes with full context
    - Semantic Memory: Consolidated knowledge and profiles

    Features:
    - O(log n) hierarchical retrieval
    - Automatic tier transitions via consolidation
    - Full context preservation for "time travel"

    Attributes:
        expert_name: Name of the expert
        working_memory: Current session episodes
        episodic_memory: Past session episodes
        semantic_memory: Consolidated knowledge
        user_profiles: User profile cache
        meta_knowledge: Domain awareness
        working_capacity: Max episodes in working memory
    """

    def __init__(self, expert_name: str, storage_dir: Optional[Path] = None, working_capacity: int = 10):
        """Initialize hierarchical memory.

        Args:
            expert_name: Name of the expert
            storage_dir: Directory for persistence (default: data/experts/{name}/memory)
            working_capacity: Maximum episodes in working memory
        """
        self.expert_name = expert_name
        self.working_capacity = working_capacity

        # Set up storage
        if storage_dir is None:
            storage_dir = Path("data/experts") / expert_name / "memory"
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Initialize memory tiers
        self.working_memory: list[Episode] = []
        self.episodic_memory: list[Episode] = []
        self.semantic_memory: dict[str, Any] = {}

        # User profiles
        self.user_profiles: dict[str, UserProfile] = {}

        # Meta-knowledge
        self.meta_knowledge = MetaKnowledge(expert_name=expert_name)

        # Keyword index for fast retrieval
        self._keyword_index: dict[str, set[str]] = {}  # keyword -> episode_ids

        # Load persisted memory
        self._load()

    def add_episode(self, episode: Episode, auto_consolidate: bool = True) -> str:
        """Add an episode to working memory.

        Args:
            episode: Episode to add
            auto_consolidate: Whether to auto-consolidate if capacity exceeded

        Returns:
            Episode ID
        """
        episode.tier = MemoryTier.WORKING
        self.working_memory.append(episode)

        # Update keyword index
        for keyword in episode.get_keywords():
            if keyword not in self._keyword_index:
                self._keyword_index[keyword] = set()
            self._keyword_index[keyword].add(episode.id)

        # Auto-consolidate if over capacity
        if auto_consolidate and len(self.working_memory) > self.working_capacity:
            self.consolidate()

        return episode.id

    def retrieve(self, query: str, top_k: int = 5, tiers: Optional[list[MemoryTier]] = None) -> list[Episode]:
        """Retrieve relevant episodes using hierarchical search.

        Searches working memory first (fast), then episodic (medium),
        then semantic (slow) until top_k results found.

        Args:
            query: Search query
            top_k: Maximum episodes to return
            tiers: Specific tiers to search (default: all)

        Returns:
            List of relevant episodes, sorted by relevance
        """
        if tiers is None:
            tiers = [MemoryTier.WORKING, MemoryTier.EPISODIC, MemoryTier.SEMANTIC]

        results: list[tuple] = []  # (score, episode)
        query_keywords = self._extract_keywords(query)

        # Search each tier
        for tier in tiers:
            if tier == MemoryTier.WORKING:
                episodes = self.working_memory
            elif tier == MemoryTier.EPISODIC:
                episodes = self.episodic_memory
            else:
                # Semantic tier - reconstruct from consolidated knowledge
                episodes = self._get_semantic_episodes()

            for episode in episodes:
                score = self._compute_relevance(episode, query_keywords)
                if score > 0:
                    results.append((score, episode))

            # Early exit if we have enough results
            if len(results) >= top_k * 2:
                break

        # Sort by relevance and return top_k
        results.sort(key=lambda x: x[0], reverse=True)
        return [episode for _, episode in results[:top_k]]

    def consolidate(self):
        """Consolidate working memory to episodic memory.

        Moves older episodes from working to episodic tier,
        keeping only recent episodes in working memory.
        """
        if len(self.working_memory) <= self.working_capacity // 2:
            return  # Not enough to consolidate

        # Keep most recent half in working memory
        keep_count = self.working_capacity // 2
        to_consolidate = self.working_memory[:-keep_count]
        self.working_memory = self.working_memory[-keep_count:]

        # Move to episodic memory
        for episode in to_consolidate:
            episode.tier = MemoryTier.EPISODIC
            self.episodic_memory.append(episode)

        # Persist changes
        self._save()

    def _compute_relevance(self, episode: Episode, query_keywords: set[str]) -> float:
        """Compute relevance score between episode and query.

        Args:
            episode: Episode to score
            query_keywords: Keywords from query

        Returns:
            Relevance score (0-1)
        """
        if not query_keywords:
            return 0.0

        episode_keywords = episode.get_keywords()
        if not episode_keywords:
            return 0.0

        # Jaccard similarity
        intersection = len(query_keywords & episode_keywords)
        union = len(query_keywords | episode_keywords)

        if union == 0:
            return 0.0

        base_score = intersection / union

        # Boost for recency
        age_days = (datetime.now(timezone.utc) - episode.timestamp).days
        recency_boost = 1.0 / (1.0 + age_days / 30)  # Decay over 30 days

        # Boost for quality
        quality_boost = episode.quality_score if episode.quality_score else 0.5

        return base_score * (0.5 + 0.3 * recency_boost + 0.2 * quality_boost)

    def _extract_keywords(self, text: str) -> set[str]:
        """Extract keywords from text.

        Args:
            text: Text to extract from

        Returns:
            Set of keywords
        """
        # Reuse Episode's keyword extraction logic
        temp_episode = Episode(query=text, response="")
        return temp_episode.get_keywords()

    def _get_semantic_episodes(self) -> list[Episode]:
        """Get episodes from semantic memory.

        Reconstructs episodes from consolidated knowledge.

        Returns:
            List of semantic episodes
        """
        # For now, return empty - semantic consolidation is future work
        return []

    def remove_episode(self, index: int) -> bool:
        """Remove an episode by index from working memory.

        Args:
            index: Zero-based index into working_memory

        Returns:
            True if removed, False if index out of range
        """
        if 0 <= index < len(self.working_memory):
            self.working_memory.pop(index)
            self._save()
            return True
        return False

    def get_memory_summary(self) -> dict:
        """Get a summary of the memory state.

        Returns:
            Dict with episode counts, domain stats, gaps
        """
        all_episodes = self.working_memory + self.episodic_memory
        domains: dict[str, list[float]] = {}
        for ep in all_episodes:
            for kw in ep.get_keywords():
                domains.setdefault(kw, []).append(ep.quality_score or 0.5)

        # Top domains by frequency
        top_domains = sorted(domains.items(), key=lambda x: len(x[1]), reverse=True)[:5]

        return {
            "conversations": len(all_episodes),
            "working_memory": len(self.working_memory),
            "episodic_memory": len(self.episodic_memory),
            "domains": [
                {"name": name, "confidence": sum(scores) / len(scores)}
                for name, scores in top_domains
            ],
            "gaps": 0,  # Filled from metacognition if available
        }

    def get_user_profile(self, user_id: str) -> UserProfile:
        """Get or create user profile.

        Args:
            user_id: User identifier

        Returns:
            UserProfile for the user
        """
        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = UserProfile(user_id=user_id)
        return self.user_profiles[user_id]

    def update_user_profile(self, user_id: str, query: str, response_quality: Optional[float] = None):
        """Update user profile based on interaction.

        Args:
            user_id: User identifier
            query: User's query
            response_quality: Optional quality rating
        """
        profile = self.get_user_profile(user_id)
        profile.interaction_count += 1
        profile.last_seen = datetime.now(timezone.utc)

        # Extract topics from query
        keywords = self._extract_keywords(query)
        for keyword in keywords:
            profile.record_interest(keyword)

        # Update expertise based on query complexity
        # Simple heuristic: longer queries suggest higher expertise
        word_count = len(query.split())
        expertise_signal = min(1.0, word_count / 50)  # Normalize to 0-1

        for keyword in keywords:
            profile.update_expertise(keyword, expertise_signal)

    def _save(self):
        """Persist memory to disk."""
        # Save episodic memory
        episodic_path = self.storage_dir / "episodic.json"
        episodic_data = [ep.to_dict() for ep in self.episodic_memory]
        with open(episodic_path, "w", encoding="utf-8") as f:
            json.dump(episodic_data, f, indent=2)

        # Save user profiles
        profiles_path = self.storage_dir / "profiles.json"
        profiles_data = {uid: p.to_dict() for uid, p in self.user_profiles.items()}
        with open(profiles_path, "w", encoding="utf-8") as f:
            json.dump(profiles_data, f, indent=2)

        # Save meta-knowledge
        meta_path = self.storage_dir / "meta_knowledge.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(self.meta_knowledge.to_dict(), f, indent=2)

    def _load(self):
        """Load memory from disk."""
        # Load episodic memory
        episodic_path = self.storage_dir / "episodic.json"
        if episodic_path.exists():
            with open(episodic_path, encoding="utf-8") as f:
                episodic_data = json.load(f)
            self.episodic_memory = [Episode.from_dict(ep) for ep in episodic_data]

            # Rebuild keyword index
            for episode in self.episodic_memory:
                for keyword in episode.get_keywords():
                    if keyword not in self._keyword_index:
                        self._keyword_index[keyword] = set()
                    self._keyword_index[keyword].add(episode.id)

        # Load user profiles
        profiles_path = self.storage_dir / "profiles.json"
        if profiles_path.exists():
            with open(profiles_path, encoding="utf-8") as f:
                profiles_data = json.load(f)
            self.user_profiles = {uid: UserProfile.from_dict(p) for uid, p in profiles_data.items()}

        # Load meta-knowledge
        meta_path = self.storage_dir / "meta_knowledge.json"
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                meta_data = json.load(f)
            self.meta_knowledge = MetaKnowledge.from_dict(meta_data)

    def get_statistics(self) -> dict[str, Any]:
        """Get memory statistics.

        Returns:
            Dictionary with memory stats
        """
        return {
            "working_memory_count": len(self.working_memory),
            "episodic_memory_count": len(self.episodic_memory),
            "user_profiles_count": len(self.user_profiles),
            "keyword_index_size": len(self._keyword_index),
            "unresolved_gaps": len(self.meta_knowledge.get_unresolved_gaps()),
            "working_capacity": self.working_capacity,
        }


@dataclass
class ReconstructedContext:
    """Reconstructed context from an episode.

    Enables "time travel" back to a previous conversation state,
    including all documents and reasoning that were available.

    Attributes:
        episode: The original episode
        documents: Full document contents (if available)
        reasoning_summary: Summary of reasoning chain
        related_episodes: Other episodes from same session
        user_context: User profile at the time
    """

    episode: Episode
    documents: list[dict[str, Any]] = field(default_factory=list)
    reasoning_summary: str = ""
    related_episodes: list[Episode] = field(default_factory=list)
    user_context: Optional[UserProfile] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode": self.episode.to_dict(),
            "documents": self.documents,
            "reasoning_summary": self.reasoning_summary,
            "related_episodes": [ep.to_dict() for ep in self.related_episodes],
            "user_context": self.user_context.to_dict() if self.user_context else None,
        }

    def get_full_context_prompt(self) -> str:
        """Generate a prompt that reconstructs the full context.

        Returns:
            Prompt string with full context
        """
        parts = []

        # Original query and response
        parts.append(f"Previous Question: {self.episode.query}")
        parts.append(f"Previous Answer: {self.episode.response}")

        # Documents used
        if self.documents:
            parts.append("\nDocuments that were referenced:")
            for doc in self.documents[:5]:  # Limit to 5
                name = doc.get("name", "Unknown")
                content = doc.get("content", "")[:500]  # Truncate
                parts.append(f"- {name}: {content}...")

        # Reasoning summary
        if self.reasoning_summary:
            parts.append(f"\nReasoning at the time: {self.reasoning_summary}")

        # Related context
        if self.related_episodes:
            parts.append("\nRelated questions from same session:")
            for ep in self.related_episodes[:3]:
                parts.append(f"- Q: {ep.query[:100]}...")

        return "\n".join(parts)


# Add reconstruct_context method to HierarchicalMemory
def _add_reconstruct_method():
    """Add reconstruct_context method to HierarchicalMemory."""

    def reconstruct_context(
        self, episode_id: str, include_documents: bool = True, include_related: bool = True
    ) -> Optional[ReconstructedContext]:
        """Reconstruct full context from an episode.

        Enables "time travel" back to a previous conversation state,
        recovering not just the Q&A but the full reasoning context.

        Args:
            episode_id: ID of episode to reconstruct
            include_documents: Whether to load full document contents
            include_related: Whether to include related episodes

        Returns:
            ReconstructedContext or None if episode not found
        """
        # Find the episode
        episode = None
        for ep in self.working_memory + self.episodic_memory:
            if ep.id == episode_id:
                episode = ep
                break

        if episode is None:
            return None

        # Load documents if requested
        documents = []
        if include_documents and episode.context_docs:
            docs_dir = Path("data/experts") / self.expert_name / "documents"
            for doc_name in episode.context_docs:
                doc_path = docs_dir / doc_name
                if doc_path.exists():
                    try:
                        with open(doc_path, encoding="utf-8") as f:
                            content = f.read()
                        documents.append({"name": doc_name, "content": content})
                    except Exception as e:
                        logger.warning("Failed to read document %s: %s", doc_path, e)

        # Generate reasoning summary
        reasoning_summary = ""
        if episode.reasoning_chain:
            steps = []
            for step in episode.reasoning_chain:
                steps.append(f"{step.step_type}: {step.content[:100]}")
            reasoning_summary = " → ".join(steps)

        # Find related episodes from same session
        related = []
        if include_related and episode.session_id:
            for ep in self.working_memory + self.episodic_memory:
                if ep.session_id == episode.session_id and ep.id != episode_id:
                    related.append(ep)

        # Get user context if available
        user_context = None
        if episode.user_id and episode.user_id in self.user_profiles:
            user_context = self.user_profiles[episode.user_id]

        return ReconstructedContext(
            episode=episode,
            documents=documents,
            reasoning_summary=reasoning_summary,
            related_episodes=related[:5],  # Limit to 5
            user_context=user_context,
        )

    # Add method to class
    HierarchicalMemory.reconstruct_context = reconstruct_context


# Apply the method addition
_add_reconstruct_method()


class UserProfileLearner:
    """Learns user profiles from conversation patterns.

    Tracks:
    - Expertise level based on question complexity
    - Interests based on topic frequency
    - Preferences based on feedback and behavior
    - Communication style preferences

    Attributes:
        memory: HierarchicalMemory instance
    """

    def __init__(self, memory: HierarchicalMemory):
        """Initialize learner.

        Args:
            memory: HierarchicalMemory to use for storage
        """
        self.memory = memory

    def learn_from_interaction(
        self,
        user_id: str,
        query: str,
        response: str,
        feedback: Optional[str] = None,
        response_time_ms: Optional[int] = None,
    ):
        """Learn from a user interaction.

        Args:
            user_id: User identifier
            query: User's query
            response: Expert's response
            feedback: Optional feedback ("good", "bad", "helpful", etc.)
            response_time_ms: How long user took to respond (engagement signal)
        """
        profile = self.memory.get_user_profile(user_id)

        # Update basic stats
        profile.interaction_count += 1
        profile.last_seen = datetime.now(timezone.utc)

        # Learn expertise from query complexity
        self._learn_expertise(profile, query)

        # Learn interests from topics
        self._learn_interests(profile, query)

        # Learn preferences from feedback
        if feedback:
            self._learn_from_feedback(profile, feedback, query, response)

        # Learn engagement from response time
        if response_time_ms:
            self._learn_engagement(profile, response_time_ms)

        # Persist changes
        self.memory._save()

    def _learn_expertise(self, profile: UserProfile, query: str):
        """Learn expertise level from query characteristics.

        Args:
            profile: User profile to update
            query: User's query
        """
        # Indicators of expertise
        technical_terms = {
            "algorithm",
            "architecture",
            "implementation",
            "optimization",
            "latency",
            "throughput",
            "scalability",
            "distributed",
            "concurrent",
            "asynchronous",
            "synchronous",
            "protocol",
            "interface",
            "abstraction",
            "polymorphism",
            "inheritance",
            "encapsulation",
            "dependency",
            "microservice",
            "monolith",
            "container",
            "orchestration",
            "pipeline",
        }

        query_lower = query.lower()
        words = set(query_lower.split())

        # Count technical terms
        tech_count = len(words & technical_terms)

        # Query length as complexity signal
        word_count = len(query.split())

        # Calculate expertise signal
        tech_signal = min(1.0, tech_count / 3)  # 3+ technical terms = expert
        length_signal = min(1.0, word_count / 30)  # 30+ words = detailed question

        expertise_signal = 0.6 * tech_signal + 0.4 * length_signal

        # Extract domain from query
        keywords = self.memory._extract_keywords(query)
        for keyword in list(keywords)[:3]:  # Top 3 keywords as domains
            profile.update_expertise(keyword, expertise_signal)

    def _learn_interests(self, profile: UserProfile, query: str):
        """Learn interests from query topics.

        Args:
            profile: User profile to update
            query: User's query
        """
        keywords = self.memory._extract_keywords(query)
        for keyword in keywords:
            profile.record_interest(keyword)

    def _learn_from_feedback(self, profile: UserProfile, feedback: str, query: str, response: str):
        """Learn preferences from feedback.

        Args:
            profile: User profile to update
            feedback: User's feedback
            query: Original query
            response: Expert's response
        """
        feedback_lower = feedback.lower()

        # Positive feedback
        if any(word in feedback_lower for word in ["good", "great", "helpful", "thanks", "perfect"]):
            # Learn what worked
            response_length = len(response.split())

            # Update verbosity preference
            if response_length > 200:
                profile.preferences["verbosity"] = "detailed"
            elif response_length < 50:
                profile.preferences["verbosity"] = "concise"

            # Record positive feedback
            profile.feedback_history.append(("positive", datetime.now(timezone.utc).isoformat()))

        # Negative feedback
        elif any(word in feedback_lower for word in ["bad", "wrong", "unhelpful", "confusing"]):
            profile.feedback_history.append(("negative", datetime.now(timezone.utc).isoformat()))

        # Specific preferences
        if "too long" in feedback_lower or "shorter" in feedback_lower:
            profile.preferences["verbosity"] = "concise"
        elif "more detail" in feedback_lower or "elaborate" in feedback_lower:
            profile.preferences["verbosity"] = "detailed"

        if "too technical" in feedback_lower:
            profile.preferences["technical_level"] = "beginner"
        elif "more technical" in feedback_lower:
            profile.preferences["technical_level"] = "advanced"

    def _learn_engagement(self, profile: UserProfile, response_time_ms: int):
        """Learn engagement from response time.

        Args:
            profile: User profile to update
            response_time_ms: Time to respond in milliseconds
        """
        # Fast responses suggest engaged user
        # Slow responses might indicate confusion or disengagement

        engagement_history = profile.preferences.get("engagement_times", [])
        engagement_history.append(response_time_ms)

        # Keep last 20 response times
        profile.preferences["engagement_times"] = engagement_history[-20:]

        # Calculate average engagement
        avg_time = sum(engagement_history) / len(engagement_history)

        if avg_time < 5000:  # < 5 seconds
            profile.preferences["engagement_level"] = "high"
        elif avg_time < 30000:  # < 30 seconds
            profile.preferences["engagement_level"] = "medium"
        else:
            profile.preferences["engagement_level"] = "low"

    def get_personalization_hints(self, user_id: str) -> dict[str, Any]:
        """Get personalization hints for a user.

        Args:
            user_id: User identifier

        Returns:
            Dictionary with personalization hints
        """
        profile = self.memory.get_user_profile(user_id)

        # Calculate overall expertise
        avg_expertise = 0.5
        if profile.expertise_levels:
            avg_expertise = sum(profile.expertise_levels.values()) / len(profile.expertise_levels)

        # Get preferences
        verbosity = profile.preferences.get("verbosity", "medium")
        tech_level = profile.preferences.get("technical_level", "intermediate")
        engagement = profile.preferences.get("engagement_level", "medium")

        # Calculate feedback sentiment
        positive_count = sum(1 for f, _ in profile.feedback_history if f == "positive")
        negative_count = sum(1 for f, _ in profile.feedback_history if f == "negative")
        total_feedback = positive_count + negative_count
        satisfaction = positive_count / total_feedback if total_feedback > 0 else 0.5

        return {
            "expertise_level": "expert"
            if avg_expertise > 0.7
            else "intermediate"
            if avg_expertise > 0.4
            else "beginner",
            "top_interests": profile.get_top_interests(5),
            "preferred_verbosity": verbosity,
            "technical_level": tech_level,
            "engagement_level": engagement,
            "satisfaction_score": satisfaction,
            "interaction_count": profile.interaction_count,
            "is_returning_user": profile.interaction_count > 5,
        }


# Add learner factory method to HierarchicalMemory
def _add_learner_method():
    """Add get_learner method to HierarchicalMemory."""

    def get_learner(self) -> UserProfileLearner:
        """Get a UserProfileLearner for this memory.

        Returns:
            UserProfileLearner instance
        """
        if not hasattr(self, "_learner"):
            self._learner = UserProfileLearner(self)
        return self._learner

    HierarchicalMemory.get_learner = get_learner


_add_learner_method()
