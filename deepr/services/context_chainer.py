"""Structured context chaining for phase-to-phase handoff.

Provides structured context building that chains findings from
phase N to phase N+1, with intelligent summarization and token budget management.

Usage:
    from deepr.services.context_chainer import ContextChainer
    from deepr.observability.temporal_tracker import TemporalKnowledgeTracker

    tracker = TemporalKnowledgeTracker()
    chainer = ContextChainer()

    # Structure output from a phase
    structured = chainer.structure_phase_output(
        raw_output="Phase 1 research results...",
        phase=1,
        tracker=tracker
    )

    # Build context for next phase
    context = chainer.build_structured_context(
        prior_phases=[structured],
        current_phase=2,
        max_tokens=4000
    )
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import hashlib

from deepr.observability.temporal_tracker import (
    TemporalKnowledgeTracker,
    TemporalFinding,
    FindingType,
)
from deepr.core.constants import MAX_CONTEXT_TOKENS


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


@dataclass
class ExtractedFinding:
    """A finding extracted from raw output."""
    text: str
    confidence: float
    finding_type: FindingType
    source: Optional[str] = None
    importance: float = 0.5  # 0-1 score for prioritization

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "finding_type": self.finding_type.value,
            "source": self.source,
            "importance": self.importance,
        }


@dataclass
class StructuredPhaseOutput:
    """Structured output from a research phase."""
    phase: int
    key_findings: List[ExtractedFinding]
    summary: str
    entities: List[str]
    open_questions: List[str]
    contradictions: List[str]
    confidence_avg: float
    timestamp: datetime = field(default_factory=_utc_now)
    token_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "key_findings": [f.to_dict() for f in self.key_findings],
            "summary": self.summary,
            "entities": self.entities,
            "open_questions": self.open_questions,
            "contradictions": self.contradictions,
            "confidence_avg": self.confidence_avg,
            "timestamp": self.timestamp.isoformat(),
            "token_count": self.token_count,
        }


class ContextChainer:
    """Builds structured context chains between research phases.

    Extracts key findings, entities, and open questions from phase outputs
    to construct focused context for subsequent phases.

    Attributes:
        max_tokens: Maximum tokens for context
        importance_threshold: Minimum importance for inclusion
    """

    def __init__(
        self,
        max_tokens: Optional[int] = None,
        importance_threshold: float = 0.3,
    ):
        """Initialize the context chainer.

        Args:
            max_tokens: Maximum tokens for context (default from constants)
            importance_threshold: Minimum importance score for findings
        """
        self.max_tokens = max_tokens or MAX_CONTEXT_TOKENS
        self.importance_threshold = importance_threshold

    def structure_phase_output(
        self,
        raw_output: str,
        phase: int,
        tracker: Optional[TemporalKnowledgeTracker] = None,
    ) -> StructuredPhaseOutput:
        """Extract structured information from raw phase output.

        Args:
            raw_output: Raw text output from phase
            phase: Phase number
            tracker: Optional tracker to record findings

        Returns:
            StructuredPhaseOutput with extracted information
        """
        # Extract findings
        findings = self._extract_findings(raw_output)

        # Extract entities (capitalized phrases, likely names/terms)
        entities = self._extract_entities(raw_output)

        # Extract open questions
        open_questions = self._extract_questions(raw_output)

        # Detect contradictions
        contradictions = self._detect_contradictions(raw_output)

        # Generate summary
        summary = self._generate_summary(raw_output, findings)

        # Calculate average confidence
        conf_avg = (
            sum(f.confidence for f in findings) / len(findings)
            if findings else 0.5
        )

        # Record findings in tracker if provided
        if tracker:
            for finding in findings:
                tracker.record_finding(
                    text=finding.text,
                    phase=phase,
                    confidence=finding.confidence,
                    source=finding.source,
                    finding_type=finding.finding_type,
                )

        # Estimate token count
        token_count = len(raw_output.split()) + 100  # Rough estimate

        return StructuredPhaseOutput(
            phase=phase,
            key_findings=findings,
            summary=summary,
            entities=entities,
            open_questions=open_questions,
            contradictions=contradictions,
            confidence_avg=conf_avg,
            token_count=token_count,
        )

    def build_structured_context(
        self,
        prior_phases: List[StructuredPhaseOutput],
        current_phase: int,
        max_tokens: Optional[int] = None,
        focus_query: Optional[str] = None,
    ) -> str:
        """Build structured context from prior phases.

        Args:
            prior_phases: List of structured outputs from prior phases
            current_phase: Current phase number
            max_tokens: Override maximum tokens
            focus_query: Optional query to focus context on

        Returns:
            Formatted context string
        """
        max_tokens = max_tokens or self.max_tokens

        sections = []

        # Header
        sections.append(f"## Context from Phases 1-{current_phase - 1}")
        sections.append("")

        # Track token budget
        budget_used = 50  # Header overhead
        budget_per_phase = (max_tokens - budget_used) // max(len(prior_phases), 1)

        for phase_output in prior_phases:
            phase_section, tokens_used = self._format_phase_context(
                phase_output,
                budget=budget_per_phase,
                focus_query=focus_query,
            )
            sections.append(phase_section)
            budget_used += tokens_used

        # Open questions that need investigation
        all_questions = []
        for phase_output in prior_phases:
            all_questions.extend(phase_output.open_questions)

        if all_questions:
            sections.append("## Open Questions")
            for q in all_questions[:5]:  # Limit to top 5
                sections.append(f"- {q}")
            sections.append("")

        # Any contradictions to resolve
        all_contradictions = []
        for phase_output in prior_phases:
            all_contradictions.extend(phase_output.contradictions)

        if all_contradictions:
            sections.append("## Contradictions to Resolve")
            for c in all_contradictions[:3]:
                sections.append(f"- {c}")
            sections.append("")

        # Instructions for next phase
        sections.append("---")
        sections.append(f"You are now in Phase {current_phase}. ")
        sections.append("Build upon the above findings. Avoid repeating known information.")
        sections.append("")

        return "\n".join(sections)

    def merge_contexts(
        self,
        contexts: List[str],
        max_tokens: Optional[int] = None,
    ) -> str:
        """Merge multiple context strings with deduplication.

        Args:
            contexts: List of context strings to merge
            max_tokens: Maximum tokens in result

        Returns:
            Merged context string
        """
        max_tokens = max_tokens or self.max_tokens

        # Extract unique bullet points
        seen_hashes = set()
        unique_points = []

        for context in contexts:
            lines = context.split("\n")
            for line in lines:
                if line.startswith("- "):
                    content = line[2:].strip()
                    content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
                    if content_hash not in seen_hashes:
                        seen_hashes.add(content_hash)
                        unique_points.append(line)

        # Reconstruct
        result = "## Merged Research Context\n\n"
        result += "\n".join(unique_points[:50])  # Limit points

        # Truncate if over budget
        words = result.split()
        if len(words) > max_tokens:
            result = " ".join(words[:max_tokens])

        return result

    def _extract_findings(self, text: str) -> List[ExtractedFinding]:
        """Extract key findings from text.

        Args:
            text: Raw text to extract from

        Returns:
            List of extracted findings
        """
        findings = []

        # Split into paragraphs
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        for para in paragraphs:
            if len(para) < 30:
                continue

            # Determine finding type based on content
            finding_type = self._classify_finding(para)

            # Estimate confidence based on language
            confidence = self._estimate_confidence(para)

            # Calculate importance
            importance = self._calculate_importance(para)

            # Extract source if present
            source = self._extract_source(para)

            if importance >= self.importance_threshold:
                findings.append(ExtractedFinding(
                    text=para[:500],  # Truncate long paragraphs
                    confidence=confidence,
                    finding_type=finding_type,
                    source=source,
                    importance=importance,
                ))

        # Sort by importance and return top findings
        findings.sort(key=lambda f: f.importance, reverse=True)
        return findings[:20]  # Limit to top 20

    def _extract_entities(self, text: str) -> List[str]:
        """Extract named entities from text.

        Args:
            text: Text to extract from

        Returns:
            List of entity strings
        """
        entities = set()

        # Find capitalized phrases
        pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        matches = re.findall(pattern, text)

        for match in matches:
            if len(match) > 3 and match.lower() not in {
                'the', 'this', 'that', 'these', 'those',
                'however', 'therefore', 'furthermore',
            }:
                entities.add(match)

        return list(entities)[:30]

    def _extract_questions(self, text: str) -> List[str]:
        """Extract open questions from text.

        Args:
            text: Text to extract from

        Returns:
            List of question strings
        """
        questions = []

        # Find sentences ending with ?
        pattern = r'([^.!?]*\?)'
        matches = re.findall(pattern, text)

        for match in matches:
            q = match.strip()
            if len(q) > 20:
                questions.append(q)

        # Also look for phrases indicating uncertainty
        uncertainty_patterns = [
            r'(remains unclear[^.]*\.)',
            r'(further research[^.]*\.)',
            r'(unknown whether[^.]*\.)',
            r'(needs investigation[^.]*\.)',
        ]

        for pattern in uncertainty_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            questions.extend(m.strip() for m in matches)

        return questions[:10]

    def _detect_contradictions(self, text: str) -> List[str]:
        """Detect potential contradictions in text.

        Args:
            text: Text to analyze

        Returns:
            List of contradiction descriptions
        """
        contradictions = []

        # Look for contradiction indicators
        indicators = [
            (r'however[^.]*contradicts[^.]*\.', 'Direct contradiction'),
            (r'in contrast[^.]*\.', 'Contrasting view'),
            (r'on the other hand[^.]*\.', 'Alternative perspective'),
            (r'contrary to[^.]*\.', 'Contrary finding'),
            (r'despite[^.]*evidence[^.]*\.', 'Evidence conflict'),
        ]

        for pattern, label in indicators:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                contradictions.append(f"{label}: {match.strip()[:100]}")

        return contradictions[:5]

    def _generate_summary(
        self,
        text: str,
        findings: List[ExtractedFinding],
    ) -> str:
        """Generate a brief summary.

        Args:
            text: Original text
            findings: Extracted findings

        Returns:
            Summary string
        """
        # Use top findings as summary basis
        if findings:
            top_findings = [f.text[:100] for f in findings[:3]]
            return "Key points: " + "; ".join(top_findings)

        # Fallback to first paragraph
        paragraphs = text.split("\n\n")
        if paragraphs:
            return paragraphs[0][:200]

        return "No summary available."

    def _classify_finding(self, text: str) -> FindingType:
        """Classify a finding by type.

        Args:
            text: Finding text

        Returns:
            FindingType classification
        """
        text_lower = text.lower()

        if any(w in text_lower for w in ['data shows', 'study found', 'research indicates']):
            return FindingType.FACT
        elif any(w in text_lower for w in ['observed', 'noted', 'seen']):
            return FindingType.OBSERVATION
        elif any(w in text_lower for w in ['suggests', 'implies', 'indicates']):
            return FindingType.INFERENCE
        elif any(w in text_lower for w in ['hypothesis', 'theory', 'possibly']):
            return FindingType.HYPOTHESIS
        elif any(w in text_lower for w in ['contradicts', 'conflicts', 'however']):
            return FindingType.CONTRADICTION
        elif any(w in text_lower for w in ['confirms', 'supports', 'validates']):
            return FindingType.CONFIRMATION
        else:
            return FindingType.OBSERVATION

    def _estimate_confidence(self, text: str) -> float:
        """Estimate confidence from language.

        Args:
            text: Finding text

        Returns:
            Confidence score (0-1)
        """
        text_lower = text.lower()

        # High confidence indicators
        high_conf = ['definitely', 'certainly', 'proven', 'established', 'confirmed']
        if any(w in text_lower for w in high_conf):
            return 0.9

        # Low confidence indicators
        low_conf = ['might', 'possibly', 'uncertain', 'unclear', 'maybe']
        if any(w in text_lower for w in low_conf):
            return 0.3

        # Medium indicators
        medium_conf = ['likely', 'probably', 'suggests', 'appears']
        if any(w in text_lower for w in medium_conf):
            return 0.6

        return 0.5

    def _calculate_importance(self, text: str) -> float:
        """Calculate importance score for a finding.

        Args:
            text: Finding text

        Returns:
            Importance score (0-1)
        """
        score = 0.5

        # Boost for specific data
        if any(c.isdigit() for c in text):
            score += 0.1

        # Boost for citations/sources
        if any(w in text.lower() for w in ['according to', 'study', 'research']):
            score += 0.15

        # Boost for novel findings
        if any(w in text.lower() for w in ['first', 'novel', 'new', 'discovered']):
            score += 0.2

        # Penalty for hedging
        if any(w in text.lower() for w in ['might', 'possibly', 'perhaps']):
            score -= 0.1

        return min(1.0, max(0.0, score))

    def _extract_source(self, text: str) -> Optional[str]:
        """Extract source citation from text.

        Args:
            text: Finding text

        Returns:
            Source string or None
        """
        # Look for URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, text)
        if urls:
            return urls[0]

        # Look for citations
        cite_pattern = r'\(([^)]+(?:19|20)\d{2}[^)]*)\)'
        cites = re.findall(cite_pattern, text)
        if cites:
            return cites[0]

        return None

    def _format_phase_context(
        self,
        phase_output: StructuredPhaseOutput,
        budget: int,
        focus_query: Optional[str],
    ) -> tuple:
        """Format a phase's context within token budget.

        Args:
            phase_output: Structured phase output
            budget: Token budget for this phase
            focus_query: Optional focus query for relevance

        Returns:
            Tuple of (formatted string, tokens used)
        """
        lines = []
        lines.append(f"### Phase {phase_output.phase}")
        lines.append("")

        # Summary
        lines.append(f"**Summary:** {phase_output.summary}")
        lines.append("")

        # Key findings (prioritized by importance)
        lines.append("**Key Findings:**")
        findings = phase_output.key_findings

        # Filter by focus query if provided
        if focus_query:
            query_words = set(focus_query.lower().split())
            findings = sorted(
                findings,
                key=lambda f: len(set(f.text.lower().split()) & query_words),
                reverse=True,
            )

        tokens_used = 50  # Overhead
        for finding in findings:
            finding_text = f"- [{finding.finding_type.value}] {finding.text[:150]}"
            finding_tokens = len(finding_text.split())

            if tokens_used + finding_tokens > budget:
                break

            lines.append(finding_text)
            tokens_used += finding_tokens

        lines.append("")

        # Entities
        if phase_output.entities:
            entities_str = ", ".join(phase_output.entities[:10])
            lines.append(f"**Key Entities:** {entities_str}")
            lines.append("")

        result = "\n".join(lines)
        return result, tokens_used
