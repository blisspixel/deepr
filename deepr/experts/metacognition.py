"""Meta-cognitive awareness tracking for experts.

Tracks what the expert knows vs doesn't know, confidence levels, and learning patterns.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeGap:
    """Represents a recognized knowledge gap."""

    topic: str
    first_encountered: datetime
    times_asked: int
    research_triggered: bool
    research_date: Optional[datetime] = None
    confidence_before: float = 0.0
    confidence_after: Optional[float] = None


@dataclass
class DomainConfidence:
    """Confidence level in a specific domain or topic."""

    domain: str
    confidence: float  # 0.0 to 1.0
    evidence_count: int  # Number of documents/research covering this
    last_updated: datetime
    sources: list[str]  # Document names or research IDs


class MetaCognitionTracker:
    """Tracks expert's awareness of what it knows and doesn't know."""

    def __init__(self, expert_name: str, base_path: str = "data/experts"):
        self.expert_name = expert_name
        self.base_path = Path(base_path)
        self.expert_dir = self._get_expert_dir()
        self.meta_file = self.expert_dir / "meta_knowledge.json"

        self.knowledge_gaps: dict[str, KnowledgeGap] = {}
        self.domain_confidence: dict[str, DomainConfidence] = {}
        self.uncertainty_log: list[dict] = []

        self._load()

    def _get_expert_dir(self) -> Path:
        """Get expert directory path."""
        safe_name = "".join(c for c in self.expert_name if c.isalnum() or c in (" ", "-", "_")).strip()
        safe_name = safe_name.replace(" ", "_").lower()
        return self.base_path / safe_name

    def _load(self):
        """Load meta-knowledge from disk."""
        if self.meta_file.exists():
            try:
                with open(self.meta_file, encoding="utf-8") as f:
                    data = json.load(f)

                # Load knowledge gaps
                for topic, gap_data in data.get("knowledge_gaps", {}).items():
                    self.knowledge_gaps[topic] = KnowledgeGap(
                        topic=gap_data["topic"],
                        first_encountered=datetime.fromisoformat(gap_data["first_encountered"]),
                        times_asked=gap_data["times_asked"],
                        research_triggered=gap_data["research_triggered"],
                        research_date=datetime.fromisoformat(gap_data["research_date"])
                        if gap_data.get("research_date")
                        else None,
                        confidence_before=gap_data.get("confidence_before", 0.0),
                        confidence_after=gap_data.get("confidence_after"),
                    )

                # Load domain confidence
                for domain, conf_data in data.get("domain_confidence", {}).items():
                    self.domain_confidence[domain] = DomainConfidence(
                        domain=conf_data["domain"],
                        confidence=conf_data["confidence"],
                        evidence_count=conf_data["evidence_count"],
                        last_updated=datetime.fromisoformat(conf_data["last_updated"]),
                        sources=conf_data["sources"],
                    )

                self.uncertainty_log = data.get("uncertainty_log", [])

            except Exception as e:
                logger.error("Error loading meta-knowledge: %s", e)

    def _save(self):
        """Save meta-knowledge to disk."""
        try:
            self.expert_dir.mkdir(parents=True, exist_ok=True)

            data = {
                "expert_name": self.expert_name,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "knowledge_gaps": {
                    topic: {
                        "topic": gap.topic,
                        "first_encountered": gap.first_encountered.isoformat(),
                        "times_asked": gap.times_asked,
                        "research_triggered": gap.research_triggered,
                        "research_date": gap.research_date.isoformat() if gap.research_date else None,
                        "confidence_before": gap.confidence_before,
                        "confidence_after": gap.confidence_after,
                    }
                    for topic, gap in self.knowledge_gaps.items()
                },
                "domain_confidence": {
                    domain: {
                        "domain": conf.domain,
                        "confidence": conf.confidence,
                        "evidence_count": conf.evidence_count,
                        "last_updated": conf.last_updated.isoformat(),
                        "sources": conf.sources,
                    }
                    for domain, conf in self.domain_confidence.items()
                },
                "uncertainty_log": self.uncertainty_log,
            }

            with open(self.meta_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error("Error saving meta-knowledge: %s", e)

    def record_knowledge_gap(self, topic: str, confidence: float = 0.0) -> KnowledgeGap:
        """Record a knowledge gap when expert admits it doesn't know something.

        Args:
            topic: The topic or question the expert doesn't know about
            confidence: Current confidence level (0.0 = no knowledge)

        Returns:
            The KnowledgeGap object
        """
        now = datetime.now(timezone.utc)

        if topic in self.knowledge_gaps:
            gap = self.knowledge_gaps[topic]
            gap.times_asked += 1
        else:
            gap = KnowledgeGap(
                topic=topic,
                first_encountered=now,
                times_asked=1,
                research_triggered=False,
                confidence_before=confidence,
            )
            self.knowledge_gaps[topic] = gap

        # Log the uncertainty
        self.uncertainty_log.append(
            {"timestamp": now.isoformat(), "topic": topic, "times_asked": gap.times_asked, "action": "acknowledged_gap"}
        )

        self._save()
        return gap

    def record_research_triggered(self, topic: str, research_mode: str):
        """Record that research was triggered for a knowledge gap.

        Args:
            topic: The topic being researched
            research_mode: Type of research (quick_lookup, standard_research, deep_research)
        """
        if topic in self.knowledge_gaps:
            gap = self.knowledge_gaps[topic]
            gap.research_triggered = True
            gap.research_date = datetime.now(timezone.utc)

        self.uncertainty_log.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "topic": topic,
                "action": "research_triggered",
                "research_mode": research_mode,
            }
        )

        self._save()

    def record_learning(self, topic: str, confidence_after: float, sources: list[str]):
        """Record that learning occurred (research completed and integrated).

        Args:
            topic: The topic that was learned
            confidence_after: Confidence level after learning (0.0 to 1.0)
            sources: List of source documents or research IDs
        """
        now = datetime.now(timezone.utc)

        # Update knowledge gap
        if topic in self.knowledge_gaps:
            gap = self.knowledge_gaps[topic]
            gap.confidence_after = confidence_after

        # Update or create domain confidence
        if topic in self.domain_confidence:
            conf = self.domain_confidence[topic]
            conf.confidence = confidence_after
            conf.evidence_count += len(sources)
            conf.last_updated = now
            conf.sources.extend(sources)
        else:
            self.domain_confidence[topic] = DomainConfidence(
                domain=topic,
                confidence=confidence_after,
                evidence_count=len(sources),
                last_updated=now,
                sources=sources,
            )

        self.uncertainty_log.append(
            {
                "timestamp": now.isoformat(),
                "topic": topic,
                "action": "learning_completed",
                "confidence": confidence_after,
                "sources": sources,
            }
        )

        self._save()

    def get_knowledge_gaps(self, min_times_asked: int = 1) -> list[KnowledgeGap]:
        """Get knowledge gaps that have been asked about multiple times.

        Args:
            min_times_asked: Minimum number of times topic was asked about

        Returns:
            List of KnowledgeGap objects
        """
        return [gap for gap in self.knowledge_gaps.values() if gap.times_asked >= min_times_asked]

    def get_high_confidence_domains(self, min_confidence: float = 0.7) -> list[DomainConfidence]:
        """Get domains where expert has high confidence.

        Args:
            min_confidence: Minimum confidence threshold (0.0 to 1.0)

        Returns:
            List of DomainConfidence objects
        """
        return [conf for conf in self.domain_confidence.values() if conf.confidence >= min_confidence]

    def get_low_confidence_domains(self, max_confidence: float = 0.3) -> list[DomainConfidence]:
        """Get domains where expert has low confidence (might need more learning).

        Args:
            max_confidence: Maximum confidence threshold (0.0 to 1.0)

        Returns:
            List of DomainConfidence objects
        """
        return [conf for conf in self.domain_confidence.values() if conf.confidence <= max_confidence]

    def suggest_proactive_research(self, threshold_times_asked: int = 3) -> list[str]:
        """Suggest topics for proactive research based on repeated questions.

        Args:
            threshold_times_asked: Number of times a topic needs to be asked before suggesting research

        Returns:
            List of topics that should be researched proactively
        """
        return [
            gap.topic
            for gap in self.knowledge_gaps.values()
            if gap.times_asked >= threshold_times_asked and not gap.research_triggered
        ]

    def get_learning_stats(self) -> dict:
        """Get statistics about the expert's learning journey.

        Returns:
            Dictionary with learning statistics
        """
        total_gaps = len(self.knowledge_gaps)
        researched_gaps = sum(1 for gap in self.knowledge_gaps.values() if gap.research_triggered)
        learned_gaps = sum(1 for gap in self.knowledge_gaps.values() if gap.confidence_after is not None)

        avg_confidence = (
            sum(conf.confidence for conf in self.domain_confidence.values()) / len(self.domain_confidence)
            if self.domain_confidence
            else 0.0
        )

        return {
            "total_knowledge_gaps": total_gaps,
            "researched_gaps": researched_gaps,
            "learned_gaps": learned_gaps,
            "learning_rate": learned_gaps / total_gaps if total_gaps > 0 else 0.0,
            "domains_tracked": len(self.domain_confidence),
            "average_confidence": avg_confidence,
            "total_uncertainty_events": len(self.uncertainty_log),
            "high_confidence_domains": len(self.get_high_confidence_domains()),
            "low_confidence_domains": len(self.get_low_confidence_domains()),
        }
