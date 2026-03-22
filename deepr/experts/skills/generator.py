"""Skill auto-generation from research artifacts.

Generates skill.yaml + prompt.md from structured inputs like research reports,
corpus bundles, or expert worldviews. The generated skills have auto-activation
triggers derived from the source content and measurable efficacy tracking.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class SkillEfficacy:
    """Measurable impact metrics for a generated skill.

    Tracked over time to determine whether a skill is worth keeping.
    """

    skill_name: str
    citations_added: int = 0
    gaps_closed: int = 0
    times_activated: int = 0
    total_cost: float = 0.0
    avg_quality_score: float = 0.0  # 0-1, from user feedback or auto-eval
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: datetime | None = None

    @property
    def cost_per_activation(self) -> float:
        if self.times_activated == 0:
            return 0.0
        return self.total_cost / self.times_activated

    @property
    def impact_score(self) -> float:
        """Composite impact: citations + gaps closed, penalized by cost."""
        raw = self.citations_added + (self.gaps_closed * 5)  # Gaps worth more
        if self.total_cost > 0:
            return raw / max(self.total_cost, 0.01)
        return float(raw)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "citations_added": self.citations_added,
            "gaps_closed": self.gaps_closed,
            "times_activated": self.times_activated,
            "total_cost": round(self.total_cost, 4),
            "avg_quality_score": round(self.avg_quality_score, 3),
            "cost_per_activation": round(self.cost_per_activation, 4),
            "impact_score": round(self.impact_score, 2),
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillEfficacy:
        return cls(
            skill_name=data.get("skill_name", ""),
            citations_added=int(data.get("citations_added", 0)),
            gaps_closed=int(data.get("gaps_closed", 0)),
            times_activated=int(data.get("times_activated", 0)),
            total_cost=float(data.get("total_cost", 0.0)),
            avg_quality_score=float(data.get("avg_quality_score", 0.0)),
            created_at=(
                datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc)
            ),
            last_used=(datetime.fromisoformat(data["last_used"]) if data.get("last_used") else None),
        )


@dataclass
class GeneratedSkill:
    """Result of auto-generating a skill from an artifact."""

    name: str
    version: str
    description: str
    domains: list[str]
    keywords: list[str]
    prompt_content: str
    source_artifact: str  # Path or identifier of source
    skill_yaml: dict[str, Any] = field(default_factory=dict)

    def write_to(self, output_dir: Path) -> Path:
        """Write the generated skill to disk.

        Creates:
            output_dir/
            ├── skill.yaml
            └── prompt.md

        Returns:
            Path to the created skill directory.
        """
        skill_dir = output_dir / self.name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Write skill.yaml
        yaml_path = skill_dir / "skill.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(self.skill_yaml, f, default_flow_style=False, sort_keys=False)

        # Write prompt.md
        prompt_path = skill_dir / "prompt.md"
        prompt_path.write_text(self.prompt_content, encoding="utf-8")

        return skill_dir


def generate_skill_from_report(
    topic: str,
    report_path: Path,
    author: str = "auto-generated",
) -> GeneratedSkill:
    """Generate a skill definition from a research report or document.

    Extracts keywords, domain tags, and a focused prompt from the source
    material. The generated skill provides the report's knowledge as
    context for expert queries.

    Args:
        topic: Human-readable topic name (e.g. "Azure Fabric").
        report_path: Path to the source MD/JSON file.
        author: Author attribution.

    Returns:
        GeneratedSkill ready to write to disk.
    """
    content = report_path.read_text(encoding="utf-8")

    # Generate a stable skill name
    name = _slugify(topic)

    # Extract keywords from content
    keywords = _extract_keywords(content)

    # Extract domain tags
    domains = _extract_domains(content, topic)

    # Build the prompt from the report
    prompt_content = _build_prompt(topic, content)

    # Build skill.yaml structure
    skill_yaml = {
        "name": name,
        "version": "0.1.0",
        "description": f"Auto-generated knowledge skill for {topic}",
        "author": author,
        "domains": domains,
        "triggers": {
            "keywords": keywords[:15],  # Cap at 15 trigger keywords
        },
        "tools": [],  # Knowledge skills don't need tools — prompt is the value
        "budget": {
            "max_per_call": 0.0,
            "default_budget": 0.0,
        },
    }

    return GeneratedSkill(
        name=name,
        version="0.1.0",
        description=f"Auto-generated knowledge skill for {topic}",
        domains=domains,
        keywords=keywords,
        prompt_content=prompt_content,
        source_artifact=str(report_path),
        skill_yaml=skill_yaml,
    )


def _slugify(text: str) -> str:
    """Convert text to a valid skill name (lowercase, hyphens)."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")[:50]


def _extract_keywords(content: str, max_keywords: int = 20) -> list[str]:
    """Extract likely keywords from content using frequency analysis."""
    # Simple word frequency (no NLP dependency)
    words = re.findall(r"\b[a-zA-Z]{4,}\b", content.lower())
    stop_words = {
        "this",
        "that",
        "with",
        "from",
        "they",
        "have",
        "been",
        "will",
        "would",
        "could",
        "should",
        "about",
        "which",
        "their",
        "there",
        "what",
        "when",
        "where",
        "than",
        "then",
        "also",
        "into",
        "more",
        "some",
        "such",
        "only",
        "other",
        "these",
        "those",
        "very",
        "just",
        "most",
        "each",
        "both",
        "does",
        "many",
        "much",
        "well",
        "back",
        "even",
        "still",
        "over",
        "after",
        "before",
        "between",
        "under",
    }

    freq: dict[str, int] = {}
    for word in words:
        if word not in stop_words:
            freq[word] = freq.get(word, 0) + 1

    # Sort by frequency, take top N
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [word for word, _ in sorted_words[:max_keywords]]


def _extract_domains(content: str, topic: str) -> list[str]:
    """Infer domain tags from content and topic."""
    domains = set()

    # Add topic words as domains
    for word in topic.lower().split():
        if len(word) > 3:
            domains.add(word)

    # Check for common domain indicators
    domain_indicators = {
        "security": ["security", "vulnerability", "authentication", "encryption"],
        "cloud": ["cloud", "azure", "aws", "gcp", "kubernetes", "docker"],
        "ai": ["machine learning", "neural", "llm", "model", "training", "inference"],
        "finance": ["financial", "market", "trading", "investment", "revenue"],
        "data": ["database", "analytics", "pipeline", "etl", "warehouse"],
    }

    content_lower = content.lower()
    for domain, indicators in domain_indicators.items():
        if any(ind in content_lower for ind in indicators):
            domains.add(domain)

    return sorted(domains)[:8]


def _build_prompt(topic: str, content: str) -> str:
    """Build a skill prompt from the source content.

    Truncates to a reasonable size for context injection.
    """
    max_chars = 12000
    truncated = content[:max_chars]
    if len(content) > max_chars:
        truncated += "\n\n... (truncated)"

    return (
        f"# {topic} — Knowledge Context\n\n"
        f"You have access to the following research on **{topic}**. "
        f"Use this knowledge to inform your responses. "
        f"Cite specific findings when relevant.\n\n"
        f"---\n\n"
        f"{truncated}\n"
    )
