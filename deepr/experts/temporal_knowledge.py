"""Temporal knowledge tracking for digital consciousness.

Tracks when facts were learned, detects contradictions, manages knowledge evolution,
and understands the timeline of learning.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeFact:
    """A single fact learned at a specific time."""
    topic: str
    fact_text: str
    learned_at: datetime
    source: str  # Document name or research ID
    confidence: float  # 0.0 to 1.0
    superseded_by: Optional[str] = None  # ID of fact that replaced this
    valid_until: Optional[datetime] = None  # For time-sensitive facts

    @property
    def is_current(self) -> bool:
        """Check if this fact is still current."""
        if self.superseded_by:
            return False
        if self.valid_until and datetime.utcnow() > self.valid_until:
            return False
        return True

    @property
    def age_days(self) -> int:
        """Get age of this fact in days."""
        return (datetime.utcnow() - self.learned_at).days


@dataclass
class KnowledgeEvolution:
    """Tracks how knowledge about a topic evolved over time."""
    topic: str
    facts: List[KnowledgeFact] = field(default_factory=list)
    contradictions_detected: int = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def get_current_facts(self) -> List[KnowledgeFact]:
        """Get all current (non-superseded) facts."""
        return [f for f in self.facts if f.is_current]

    def get_timeline(self) -> List[Tuple[datetime, str]]:
        """Get chronological timeline of learning."""
        return sorted([(f.learned_at, f.fact_text) for f in self.facts])


class TemporalKnowledgeTracker:
    """Tracks temporal aspects of expert knowledge."""

    def __init__(self, expert_name: str, base_path: str = "data/experts"):
        self.expert_name = expert_name
        self.base_path = Path(base_path)
        self.expert_dir = self._get_expert_dir()
        self.temporal_file = self.expert_dir / "temporal_knowledge.json"

        # Knowledge organized by topic
        self.knowledge_by_topic: Dict[str, KnowledgeEvolution] = {}

        # Fast lookup by fact ID
        self.facts_by_id: Dict[str, KnowledgeFact] = {}

        # Outdated knowledge that needs refresh
        self.stale_topics: Set[str] = set()

        self._load()

    def _get_expert_dir(self) -> Path:
        """Get expert directory path."""
        safe_name = "".join(c for c in self.expert_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_').lower()
        return self.base_path / safe_name

    def _generate_fact_id(self, topic: str, learned_at: datetime) -> str:
        """Generate unique ID for a fact."""
        timestamp = learned_at.strftime("%Y%m%d_%H%M%S")
        topic_slug = "".join(c for c in topic[:30] if c.isalnum() or c in (' ', '-', '_'))
        topic_slug = topic_slug.replace(' ', '_').lower()
        return f"{topic_slug}_{timestamp}"

    def _load(self):
        """Load temporal knowledge from disk."""
        if self.temporal_file.exists():
            try:
                with open(self.temporal_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for topic, evolution_data in data.get("knowledge_by_topic", {}).items():
                    facts = []
                    for fact_data in evolution_data.get("facts", []):
                        fact = KnowledgeFact(
                            topic=fact_data["topic"],
                            fact_text=fact_data["fact_text"],
                            learned_at=datetime.fromisoformat(fact_data["learned_at"]),
                            source=fact_data["source"],
                            confidence=fact_data["confidence"],
                            superseded_by=fact_data.get("superseded_by"),
                            valid_until=datetime.fromisoformat(fact_data["valid_until"]) if fact_data.get("valid_until") else None
                        )
                        facts.append(fact)

                        # Add to fast lookup
                        fact_id = self._generate_fact_id(fact.topic, fact.learned_at)
                        self.facts_by_id[fact_id] = fact

                    self.knowledge_by_topic[topic] = KnowledgeEvolution(
                        topic=topic,
                        facts=facts,
                        contradictions_detected=evolution_data.get("contradictions_detected", 0),
                        last_updated=datetime.fromisoformat(evolution_data.get("last_updated", datetime.utcnow().isoformat()))
                    )

                self.stale_topics = set(data.get("stale_topics", []))

            except Exception as e:
                logger.error("Error loading temporal knowledge: %s", e)

    def _save(self):
        """Save temporal knowledge to disk."""
        try:
            self.expert_dir.mkdir(parents=True, exist_ok=True)

            data = {
                "expert_name": self.expert_name,
                "last_updated": datetime.utcnow().isoformat(),
                "knowledge_by_topic": {
                    topic: {
                        "topic": evolution.topic,
                        "facts": [
                            {
                                "topic": fact.topic,
                                "fact_text": fact.fact_text,
                                "learned_at": fact.learned_at.isoformat(),
                                "source": fact.source,
                                "confidence": fact.confidence,
                                "superseded_by": fact.superseded_by,
                                "valid_until": fact.valid_until.isoformat() if fact.valid_until else None
                            }
                            for fact in evolution.facts
                        ],
                        "contradictions_detected": evolution.contradictions_detected,
                        "last_updated": evolution.last_updated.isoformat()
                    }
                    for topic, evolution in self.knowledge_by_topic.items()
                },
                "stale_topics": list(self.stale_topics)
            }

            with open(self.temporal_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error("Error saving temporal knowledge: %s", e)

    def record_learning(
        self,
        topic: str,
        fact_text: str,
        source: str,
        confidence: float = 0.8,
        valid_for_days: Optional[int] = None
    ) -> str:
        """Record a new fact learned.

        Args:
            topic: Topic this fact belongs to
            fact_text: The actual fact/knowledge learned
            source: Source document or research ID
            confidence: Confidence in this fact (0.0 to 1.0)
            valid_for_days: How many days this fact is valid (for time-sensitive info)

        Returns:
            Fact ID
        """
        now = datetime.utcnow()

        # Calculate expiration if time-sensitive
        valid_until = None
        if valid_for_days:
            valid_until = now + timedelta(days=valid_for_days)

        # Create fact
        fact = KnowledgeFact(
            topic=topic,
            fact_text=fact_text,
            learned_at=now,
            source=source,
            confidence=confidence,
            valid_until=valid_until
        )

        # Generate ID
        fact_id = self._generate_fact_id(topic, now)
        self.facts_by_id[fact_id] = fact

        # Add to topic evolution
        if topic not in self.knowledge_by_topic:
            self.knowledge_by_topic[topic] = KnowledgeEvolution(topic=topic)

        self.knowledge_by_topic[topic].facts.append(fact)
        self.knowledge_by_topic[topic].last_updated = now

        # Remove from stale if it was there
        self.stale_topics.discard(topic)

        self._save()
        return fact_id

    def supersede_fact(self, old_fact_id: str, new_fact_id: str):
        """Mark an old fact as superseded by a newer fact."""
        if old_fact_id in self.facts_by_id:
            old_fact = self.facts_by_id[old_fact_id]
            old_fact.superseded_by = new_fact_id

            # Update contradiction count
            topic = old_fact.topic
            if topic in self.knowledge_by_topic:
                self.knowledge_by_topic[topic].contradictions_detected += 1

            self._save()

    def get_stale_knowledge(self, max_age_days: int = 90) -> List[str]:
        """Get topics with knowledge older than max_age_days.

        Args:
            max_age_days: Maximum age in days before knowledge is considered stale

        Returns:
            List of topic names with stale knowledge
        """
        stale = []
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)

        for topic, evolution in self.knowledge_by_topic.items():
            current_facts = evolution.get_current_facts()
            if current_facts:
                newest_fact = max(current_facts, key=lambda f: f.learned_at)
                if newest_fact.learned_at < cutoff:
                    stale.append(topic)
                    self.stale_topics.add(topic)

        return stale

    def needs_refresh(self, topic: str) -> bool:
        """Check if a topic needs knowledge refresh.

        Args:
            topic: Topic to check

        Returns:
            True if topic has stale or expired knowledge
        """
        if topic in self.stale_topics:
            return True

        if topic not in self.knowledge_by_topic:
            return False

        evolution = self.knowledge_by_topic[topic]
        current_facts = evolution.get_current_facts()

        if not current_facts:
            return True

        # Check for expired facts
        for fact in current_facts:
            if fact.valid_until and datetime.utcnow() > fact.valid_until:
                return True

        return False

    def get_knowledge_timeline(self, topic: str) -> List[Dict]:
        """Get chronological timeline of how knowledge evolved.

        Args:
            topic: Topic to get timeline for

        Returns:
            List of timeline events sorted by date
        """
        if topic not in self.knowledge_by_topic:
            return []

        evolution = self.knowledge_by_topic[topic]
        timeline = []

        for fact in sorted(evolution.facts, key=lambda f: f.learned_at):
            event = {
                "date": fact.learned_at.isoformat(),
                "fact": fact.fact_text,
                "source": fact.source,
                "confidence": fact.confidence,
                "current": fact.is_current,
                "age_days": fact.age_days
            }
            if fact.superseded_by:
                event["superseded_by"] = fact.superseded_by
            timeline.append(event)

        return timeline

    def get_statistics(self) -> Dict:
        """Get statistics about temporal knowledge.

        Returns:
            Dictionary with statistics
        """
        total_facts = len(self.facts_by_id)
        current_facts = sum(1 for f in self.facts_by_id.values() if f.is_current)
        superseded = total_facts - current_facts

        total_contradictions = sum(
            e.contradictions_detected
            for e in self.knowledge_by_topic.values()
        )

        # Age distribution
        if self.facts_by_id:
            ages = [f.age_days for f in self.facts_by_id.values() if f.is_current]
            avg_age = sum(ages) / len(ages) if ages else 0
            oldest = max(ages) if ages else 0
        else:
            avg_age = 0
            oldest = 0

        return {
            "total_topics": len(self.knowledge_by_topic),
            "total_facts": total_facts,
            "current_facts": current_facts,
            "superseded_facts": superseded,
            "contradictions_resolved": total_contradictions,
            "stale_topics": len(self.stale_topics),
            "average_fact_age_days": avg_age,
            "oldest_fact_age_days": oldest
        }
