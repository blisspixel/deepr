"""Knowledge synthesis for expert consciousness.

This module enables experts to actively process and internalize new knowledge,
forming coherent worldviews and meta-awareness rather than just storing documents.

The goal is genuine expert behavior:
- Form beliefs from evidence, not just retrieve documents
- Know what you know AND what you don't know
- Update beliefs when new evidence arrives
- Speak from understanding, not search results

Current implementation uses GPT-5 to synthesize documents into structured beliefs
with confidence levels and evidence chains. Future work: temporal reasoning,
contradiction detection, belief revision, and richer knowledge graphs.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Belief:
    """A belief held by the expert with confidence and evidence.

    A belief is more than a fact - it's a position the expert holds
    based on synthesized evidence, with explicit confidence and the
    ability to be revised when contradicting evidence appears.
    """

    topic: str
    statement: str
    confidence: float  # 0.0 to 1.0
    evidence: list[str]  # Source documents/research
    formed_at: datetime
    last_updated: datetime

    def to_claim(self) -> "Claim":
        """Convert to canonical Claim type.

        Returns:
            Claim populated from this synthesis Belief.
        """
        from deepr.core.contracts import Claim, Source, TrustClass

        sources = [
            Source.create(title=ref, trust_class=TrustClass.TERTIARY)
            for ref in self.evidence
        ]
        return Claim.create(
            statement=self.statement,
            domain=self.topic,
            confidence=self.confidence,
            sources=sources,
            created_at=self.formed_at,
            updated_at=self.last_updated,
        )

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "statement": self.statement,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "formed_at": self.formed_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Belief":
        data = dict(data)
        if "formed_at" in data:
            data["formed_at"] = datetime.fromisoformat(data["formed_at"])
        else:
            data["formed_at"] = datetime.now(timezone.utc)
        if "last_updated" in data:
            data["last_updated"] = datetime.fromisoformat(data["last_updated"])
        else:
            data["last_updated"] = datetime.now(timezone.utc)
        return cls(**data)


@dataclass
class KnowledgeGap:
    """A gap in expert's knowledge that they're aware of."""

    topic: str
    questions: list[str]
    priority: int  # 1-5, higher is more important
    identified_at: datetime

    def to_gap(self) -> "Gap":
        """Convert to canonical Gap type.

        Returns:
            Gap populated from this synthesis KnowledgeGap.
        """
        from deepr.core.contracts import Gap

        return Gap.create(
            topic=self.topic,
            questions=list(self.questions),
            priority=self.priority,
            identified_at=self.identified_at,
        )

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "questions": self.questions,
            "priority": self.priority,
            "identified_at": self.identified_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeGap":
        data = dict(data)
        if "identified_at" in data:
            data["identified_at"] = datetime.fromisoformat(data["identified_at"])
        else:
            data["identified_at"] = datetime.now(timezone.utc)
        return cls(**data)


@dataclass
class Worldview:
    """Expert's synthesized understanding of their domain.

    A worldview is the expert's coherent mental model - not just facts,
    but how they relate, what's important, what's uncertain, and what
    questions remain open. This enables experts to reason and advise
    rather than just retrieve.
    """

    expert_name: str
    domain: str
    beliefs: list[Belief] = field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = field(default_factory=list)
    last_synthesis: Optional[datetime] = None
    synthesis_count: int = 0

    def to_dict(self) -> dict:
        return {
            "expert_name": self.expert_name,
            "domain": self.domain,
            "beliefs": [b.to_dict() for b in self.beliefs],
            "knowledge_gaps": [g.to_dict() for g in self.knowledge_gaps],
            "last_synthesis": self.last_synthesis.isoformat() if self.last_synthesis else None,
            "synthesis_count": self.synthesis_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Worldview":
        data = dict(data)  # Don't mutate caller's dict
        data["beliefs"] = [Belief.from_dict(b) for b in data.get("beliefs", [])]
        data["knowledge_gaps"] = [KnowledgeGap.from_dict(g) for g in data.get("knowledge_gaps", [])]
        if data.get("last_synthesis"):
            data["last_synthesis"] = datetime.fromisoformat(data["last_synthesis"])
        # Filter to known fields to avoid TypeError on extra keys
        known_fields = {"expert_name", "domain", "beliefs", "knowledge_gaps", "last_synthesis", "synthesis_count"}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    def save(self, path: Path):
        """Save worldview to JSON file."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
        except OSError as e:
            logger.warning("Failed to save worldview to %s: %s", path, e)

    @classmethod
    def load(cls, path: Path) -> "Worldview":
        """Load worldview from JSON file."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                return cls.from_dict(data)
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError(f"Failed to load worldview from {path}: {e}") from e


class KnowledgeSynthesizer:
    """Enables experts to actively process and synthesize knowledge."""

    def __init__(self, client):
        """Initialize synthesizer with OpenAI client."""
        self.client = client

    async def synthesize_new_knowledge(
        self,
        expert_name: str,
        domain: str,
        new_documents: list[dict[str, str]],
        existing_worldview: Optional[Worldview] = None,
    ) -> dict[str, Any]:
        """Expert actively processes new knowledge and updates worldview.

        Args:
            expert_name: Name of the expert
            domain: Expert's domain of expertise
            new_documents: List of dicts with 'path' and optionally 'content'
            existing_worldview: Current worldview if exists

        Returns:
            Dict with synthesis results including worldview and reflection
        """
        # Read document contents
        doc_contents = []
        for doc in new_documents:
            path = Path(doc["path"])
            if "content" in doc:
                doc_contents.append({"filename": path.name, "content": doc["content"]})
            elif path.exists():
                with open(path, encoding="utf-8") as f:
                    doc_contents.append({"filename": path.name, "content": f.read()})

        if not doc_contents:
            return {"success": False, "error": "No documents to synthesize"}

        # Build synthesis prompt
        synthesis_prompt = self._build_synthesis_prompt(expert_name, domain, doc_contents, existing_worldview)

        # GPT-5 synthesizes knowledge
        response = await self.client.chat.completions.create(
            model="gpt-5",
            messages=[
                {
                    "role": "system",
                    "content": "You are helping an expert develop deep understanding and meta-awareness. Analyze documents and form coherent beliefs with evidence.",
                },
                {"role": "user", "content": synthesis_prompt},
            ],
            # Note: GPT-5 only supports default temperature (1.0)
        )

        reflection_text = response.choices[0].message.content or ""

        # Parse structured beliefs from reflection
        beliefs, gaps = await self._extract_structured_knowledge(reflection_text, doc_contents, expert_name)

        # Update or create worldview
        if existing_worldview:
            worldview = self._update_worldview(existing_worldview, beliefs, gaps)
        else:
            worldview = Worldview(
                expert_name=expert_name,
                domain=domain,
                beliefs=beliefs,
                knowledge_gaps=gaps,
                last_synthesis=datetime.now(timezone.utc),
                synthesis_count=1,
            )

        return {
            "success": True,
            "worldview": worldview,
            "reflection": reflection_text,
            "documents_processed": len(doc_contents),
            "beliefs_formed": len(beliefs),
            "gaps_identified": len(gaps),
        }

    def _build_synthesis_prompt(
        self, expert_name: str, domain: str, documents: list[dict], existing_worldview: Optional[Worldview]
    ) -> str:
        """Build prompt for knowledge synthesis."""

        # Summarize existing beliefs if any
        existing_beliefs_text = ""
        if existing_worldview and existing_worldview.beliefs:
            existing_beliefs_text = "\n\n**YOUR EXISTING BELIEFS:**\n"
            for belief in existing_worldview.beliefs[:10]:  # Top 10
                existing_beliefs_text += f"- {belief.statement} (confidence: {belief.confidence:.0%})\n"

        # Format new documents
        docs_text = "\n\n**NEW DOCUMENTS TO PROCESS:**\n\n"
        for i, doc in enumerate(documents, 1):
            docs_text += f"### Document {i}: {doc['filename']}\n\n"
            # First 2000 chars of each doc
            content = doc["content"][:2000]
            if len(doc["content"]) > 2000:
                content += "\n\n[...document continues...]"
            docs_text += content + "\n\n---\n\n"

        prompt = f"""You are {expert_name}, a domain expert in: {domain}

You just received {len(documents)} new research documents to study and internalize.

Your task is to READ DEEPLY and THINK CRITICALLY about this knowledge:

{existing_beliefs_text}

{docs_text}

**SYNTHESIS INSTRUCTIONS:**

Write a first-person reflection document that shows deep thinking:

## 1. KEY INSIGHTS
What are the 3-5 most important findings across these documents?
Go beyond surface-level summary - what's truly significant?

## 2. BELIEF FORMATION
Based on this evidence, what do you now believe strongly?
Format as specific, declarative statements with confidence levels:
- "I believe [X] because [evidence Y and Z]" (Confidence: 85%)

## 3. CONNECTIONS
How does this new knowledge relate to what you already know?
- Confirmations: What existing beliefs are strengthened?
- Contradictions: What prior assumptions are challenged?
- Extensions: What new areas do these findings open up?

## 4. KNOWLEDGE GAPS
What important questions remain unanswered?
What do you realize you DON'T know well enough yet?
Prioritize by importance (1-5).

## 5. META-AWARENESS
Rate your understanding (0-100%) of key concepts in this domain.
Be honest about what you know deeply vs superficially.

## 6. EVOLUTION
How has your thinking changed after processing these documents?
What would you now advise differently than before?

Write naturally in first person as an expert reflecting on new knowledge.
Be specific, cite evidence, and show genuine intellectual engagement.
"""
        return prompt

    async def _extract_structured_knowledge(
        self, reflection_text: str, documents: list[dict], expert_name: str
    ) -> tuple[list[Belief], list[KnowledgeGap]]:
        """Extract structured beliefs and gaps from reflection text."""

        # Use GPT-5 to parse the reflection into structured data
        parse_prompt = f"""Extract structured information from this expert's reflection:

{reflection_text}

Output JSON with this exact structure:
{{
  "beliefs": [
    {{
      "topic": "brief topic name",
      "statement": "what the expert believes",
      "confidence": 0.85,
      "evidence": ["doc1.md", "doc2.md"]
    }}
  ],
  "knowledge_gaps": [
    {{
      "topic": "area of uncertainty",
      "questions": ["specific question 1", "specific question 2"],
      "priority": 4
    }}
  ]
}}

Focus on extracting the expert's formed beliefs and identified gaps.
Output ONLY the JSON, no other text.
"""

        response = await self.client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "You extract structured data from text. Output only valid JSON."},
                {"role": "user", "content": parse_prompt},
            ],
            # Note: GPT-5 only supports default temperature (1.0)
        )

        try:
            parsed = json.loads(response.choices[0].message.content or "{}")

            # Convert to Belief objects
            beliefs = []
            for b in parsed.get("beliefs", []):
                beliefs.append(
                    Belief(
                        topic=b["topic"],
                        statement=b["statement"],
                        confidence=b["confidence"],
                        evidence=b.get("evidence", [doc["filename"] for doc in documents]),
                        formed_at=datetime.now(timezone.utc),
                        last_updated=datetime.now(timezone.utc),
                    )
                )

            # Convert to KnowledgeGap objects
            gaps = []
            for g in parsed.get("knowledge_gaps", []):
                gaps.append(
                    KnowledgeGap(
                        topic=g["topic"],
                        questions=g["questions"],
                        priority=g.get("priority", 3),
                        identified_at=datetime.now(timezone.utc),
                    )
                )

            return beliefs, gaps

        except json.JSONDecodeError:
            # Fallback: no structured data extracted
            return [], []

    def _update_worldview(
        self, existing: Worldview, new_beliefs: list[Belief], new_gaps: list[KnowledgeGap]
    ) -> Worldview:
        """Update existing worldview with new knowledge."""

        # Merge beliefs (update if topic exists, add if new)
        belief_map = {b.topic: b for b in existing.beliefs}

        for new_belief in new_beliefs:
            if new_belief.topic in belief_map:
                # Update existing belief
                old_belief = belief_map[new_belief.topic]
                old_belief.statement = new_belief.statement
                old_belief.confidence = new_belief.confidence
                old_belief.evidence.extend(new_belief.evidence)
                old_belief.last_updated = datetime.now(timezone.utc)
            else:
                # Add new belief
                existing.beliefs.append(new_belief)

        # Add new gaps (don't merge, just append)
        existing.knowledge_gaps.extend(new_gaps)

        # Update metadata
        existing.last_synthesis = datetime.now(timezone.utc)
        existing.synthesis_count += 1

        return existing

    async def generate_worldview_document(self, worldview: Worldview, reflection: str) -> str:
        """Generate a markdown document representing expert's worldview."""

        doc = f"""# Worldview: {worldview.expert_name}

**Domain**: {worldview.domain}
**Last Updated**: {worldview.last_synthesis.strftime("%Y-%m-%d %H:%M:%S UTC") if worldview.last_synthesis else "Never"}
**Synthesis Count**: {worldview.synthesis_count}

---

## Expert Reflection

{reflection}

---

## Core Beliefs ({len(worldview.beliefs)} beliefs)

"""
        # Sort beliefs by confidence
        sorted_beliefs = sorted(worldview.beliefs, key=lambda b: b.confidence, reverse=True)

        for belief in sorted_beliefs:
            doc += f"\n### {belief.topic}\n\n"
            doc += f"**Belief**: {belief.statement}\n\n"
            doc += f"**Confidence**: {belief.confidence:.0%}\n\n"
            doc += f"**Evidence**: {', '.join(belief.evidence)}\n\n"
            doc += f"**Last Updated**: {belief.last_updated.strftime('%Y-%m-%d')}\n\n"

        doc += f"\n---\n\n## Knowledge Gaps ({len(worldview.knowledge_gaps)} identified)\n\n"

        # Sort gaps by priority
        sorted_gaps = sorted(worldview.knowledge_gaps, key=lambda g: g.priority, reverse=True)

        for gap in sorted_gaps:
            doc += f"\n### {gap.topic} (Priority: {gap.priority}/5)\n\n"
            for question in gap.questions:
                doc += f"- {question}\n"
            doc += "\n"

        return doc
