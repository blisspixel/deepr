"""LangGraph-based reasoning graph for expert system.

Implements Tree of Thoughts (ToT) as a LangGraph pattern for complex reasoning:
- State machine with nodes for each reasoning phase
- Hypothesis generation and evaluation
- Claim verification and self-correction
- Calibrated confidence scoring

Usage:
    from deepr.experts.reasoning_graph import ReasoningGraph, ReasoningState

    graph = ReasoningGraph(expert_profile=profile, thought_stream=stream)

    # Run reasoning on a query
    result = await graph.reason("What are the implications of quantum computing?")
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from deepr.experts.thought_stream import ThoughtStream, ThoughtType


# Pydantic-style schema validation for hypothesis generation
class HypothesisSchema:
    """Schema for validating hypothesis JSON responses."""

    REQUIRED_FIELDS = ["hypotheses"]
    HYPOTHESIS_FIELDS = ["id", "text", "confidence", "reasoning"]

    @classmethod
    def validate(cls, data: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate hypothesis response against schema.

        Args:
            data: Parsed JSON data

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check required fields
        for field_name in cls.REQUIRED_FIELDS:
            if field_name not in data:
                return False, f"Missing required field: {field_name}"

        # Validate hypotheses array
        hypotheses = data.get("hypotheses", [])
        if not isinstance(hypotheses, list):
            return False, "hypotheses must be an array"

        if len(hypotheses) == 0:
            return False, "hypotheses array cannot be empty"

        # Validate each hypothesis
        for i, h in enumerate(hypotheses):
            if not isinstance(h, dict):
                return False, f"hypothesis[{i}] must be an object"

            for field_name in cls.HYPOTHESIS_FIELDS:
                if field_name not in h:
                    return False, f"hypothesis[{i}] missing field: {field_name}"

            # Validate confidence range
            conf = h.get("confidence")
            if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
                return False, f"hypothesis[{i}].confidence must be between 0 and 1"

        return True, None

    @classmethod
    def repair(cls, raw_text: str) -> dict[str, Any] | None:
        """Attempt to repair malformed JSON.

        Args:
            raw_text: Raw text that may contain JSON

        Returns:
            Parsed JSON or None if repair failed
        """
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object directly
        json_match = re.search(r"\{[\s\S]*\}", raw_text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Try to fix common issues
        fixed = raw_text

        # Fix trailing commas
        fixed = re.sub(r",\s*}", "}", fixed)
        fixed = re.sub(r",\s*]", "]", fixed)

        # Fix single quotes
        fixed = fixed.replace("'", '"')

        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return None


class ClaimSchema:
    """Schema for validating claim extraction responses."""

    REQUIRED_FIELDS = ["claims"]
    CLAIM_FIELDS = ["id", "text", "source"]

    @classmethod
    def validate(cls, data: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate claim response against schema."""
        for field_name in cls.REQUIRED_FIELDS:
            if field_name not in data:
                return False, f"Missing required field: {field_name}"

        claims = data.get("claims", [])
        if not isinstance(claims, list):
            return False, "claims must be an array"

        for i, c in enumerate(claims):
            if not isinstance(c, dict):
                return False, f"claim[{i}] must be an object"

            for field_name in cls.CLAIM_FIELDS:
                if field_name not in c:
                    return False, f"claim[{i}] missing field: {field_name}"

        return True, None

    @classmethod
    def repair(cls, raw_text: str) -> dict[str, Any] | None:
        """Attempt to repair malformed JSON."""
        return HypothesisSchema.repair(raw_text)  # Same repair logic


class ReasoningPhase(Enum):
    """Phases of the reasoning process."""

    UNDERSTAND = "understand"
    DECOMPOSE = "decompose"
    RETRIEVE = "retrieve"
    GENERATE_HYPOTHESES = "generate_hypotheses"
    VERIFY_CLAIMS = "verify_claims"
    SYNTHESIZE = "synthesize"
    SELF_CORRECT = "self_correct"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class Hypothesis:
    """A hypothesis generated during reasoning."""

    id: str
    text: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    is_active: bool = True
    pruned_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "is_active": self.is_active,
            "pruned_reason": self.pruned_reason,
        }


@dataclass
class Claim:
    """An atomic claim extracted from a hypothesis or answer."""

    id: str
    text: str
    source_hypothesis_id: str | None
    verified: bool | None = None
    verification_sources: list[str] = field(default_factory=list)
    contradicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "source_hypothesis_id": self.source_hypothesis_id,
            "verified": self.verified,
            "verification_sources": self.verification_sources,
            "contradicts": self.contradicts,
        }


@dataclass
class ClaimAnalysis:
    """Model-derived grounding + contradiction verdicts over a set of claims.

    Grounding maps a claim id to ``{"verified": bool, "sources": [id, ...]}``;
    contradictions are ``{"type", "claim_ids", "description"}`` records. An empty
    analysis means "no verdict" (nothing verified, no contradictions) - the
    honest state when no model is available, never a lexical guess.
    """

    grounding: dict[str, dict[str, Any]] = field(default_factory=dict)
    contradictions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReasoningState:
    """State for the reasoning graph.

    Attributes:
        query: Original user query
        context: Retrieved context documents
        sub_questions: Decomposed sub-questions
        hypotheses: Generated hypotheses
        claims: Extracted claims
        verified_claims: Claims that passed verification
        contradictions: Detected contradictions
        synthesis: Final synthesized answer
        confidence: Overall confidence score
        trace: Reasoning trace for observability
        phase: Current reasoning phase
        iteration: Current iteration count
        max_iterations: Maximum iterations before stopping
        is_degraded: Whether reasoning is in degraded mode
    """

    query: str
    context: list[dict[str, Any]] = field(default_factory=list)
    sub_questions: list[str] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    verified_claims: list[Claim] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    synthesis: str | None = None
    confidence: float = 0.0
    trace: list[dict[str, Any]] = field(default_factory=list)
    phase: ReasoningPhase = ReasoningPhase.UNDERSTAND
    iteration: int = 0
    max_iterations: int = 10
    is_degraded: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "context_count": len(self.context),
            "sub_questions": self.sub_questions,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "claims": [c.to_dict() for c in self.claims],
            "verified_claims": [c.to_dict() for c in self.verified_claims],
            "contradictions": self.contradictions,
            "synthesis": self.synthesis,
            "confidence": self.confidence,
            "phase": self.phase.value,
            "iteration": self.iteration,
            "is_degraded": self.is_degraded,
            "error": self.error,
        }

    def add_trace(self, phase: str, action: str, details: dict | None = None):
        """Add an entry to the reasoning trace."""
        self.trace.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "phase": phase,
                "action": action,
                "details": details or {},
            }
        )


class ReasoningGraph:
    """LangGraph-style reasoning graph for complex queries.

    Implements Tree of Thoughts pattern with:
    - Query understanding and decomposition
    - Hypothesis generation (3-5 hypotheses when ambiguous)
    - Claim extraction and verification
    - Self-correction on contradictions
    - Calibrated confidence scoring

    Attributes:
        expert_profile: The expert's profile for context
        thought_stream: Stream for emitting thoughts
        llm_client: LLM client for generation
    """

    def __init__(
        self,
        expert_profile: Any | None = None,
        thought_stream: ThoughtStream | None = None,
        llm_client: Any | None = None,
    ):
        """Initialize reasoning graph.

        Args:
            expert_profile: Expert profile for context
            thought_stream: ThoughtStream for visibility
            llm_client: LLM client for generation
        """
        self.expert_profile = expert_profile
        self.thought_stream = thought_stream
        self.llm_client = llm_client

        # Node registry
        self._nodes: dict[ReasoningPhase, Callable] = {
            ReasoningPhase.UNDERSTAND: self._understand_query,
            ReasoningPhase.DECOMPOSE: self._decompose_query,
            ReasoningPhase.RETRIEVE: self._retrieve_context,
            ReasoningPhase.GENERATE_HYPOTHESES: self._generate_hypotheses,
            ReasoningPhase.VERIFY_CLAIMS: self._verify_claims,
            ReasoningPhase.SYNTHESIZE: self._synthesize,
            ReasoningPhase.SELF_CORRECT: self._self_correct,
        }

    async def reason(self, query: str, context: list[dict] | None = None) -> ReasoningState:
        """Run reasoning on a query.

        Args:
            query: The user's query
            context: Optional pre-retrieved context

        Returns:
            Final ReasoningState with synthesis
        """
        state = ReasoningState(query=query)
        if context:
            state.context = context

        self._emit_thought(ThoughtType.PLAN_STEP, f"Starting reasoning for: {query[:100]}...")

        # Run state machine
        while state.phase not in [ReasoningPhase.COMPLETE, ReasoningPhase.ERROR]:
            if state.iteration >= state.max_iterations:
                self._emit_thought(ThoughtType.ERROR, "Max iterations reached, stopping")
                state.phase = ReasoningPhase.ERROR
                state.error = "Max iterations reached"
                break

            state.iteration += 1

            # Get node for current phase
            node = self._nodes.get(state.phase)
            if node is None:
                state.phase = ReasoningPhase.ERROR
                state.error = f"Unknown phase: {state.phase}"
                break

            # Execute node
            try:
                state = await node(state)
            except Exception as e:
                self._emit_thought(ThoughtType.ERROR, f"Error in {state.phase.value}: {e!s}")
                state.phase = ReasoningPhase.ERROR
                state.error = str(e)
                break

        return state

    async def _understand_query(self, state: ReasoningState) -> ReasoningState:
        """Understand the query and determine complexity.

        Args:
            state: Current reasoning state

        Returns:
            Updated state with next phase
        """
        state.add_trace("understand", "analyzing_query", {"query": state.query})
        self._emit_thought(ThoughtType.PLAN_STEP, "Understanding query complexity...")

        # Determine if query is simple or complex
        # Simple heuristics for now - can be enhanced with LLM
        complexity_indicators = [
            "how" in state.query.lower(),
            "why" in state.query.lower(),
            "compare" in state.query.lower(),
            "implications" in state.query.lower(),
            "relationship" in state.query.lower(),
            len(state.query.split()) > 15,
            "?" in state.query and state.query.count("?") > 1,
        ]

        is_complex = sum(complexity_indicators) >= 2

        if is_complex:
            self._emit_thought(ThoughtType.PLAN_STEP, "Complex query detected, will decompose")
            state.phase = ReasoningPhase.DECOMPOSE
        else:
            self._emit_thought(ThoughtType.PLAN_STEP, "Simple query, proceeding to retrieval")
            state.phase = ReasoningPhase.RETRIEVE

        return state

    async def _decompose_query(self, state: ReasoningState) -> ReasoningState:
        """Decompose complex query into sub-questions.

        Args:
            state: Current reasoning state

        Returns:
            Updated state with sub-questions
        """
        state.add_trace("decompose", "generating_sub_questions")
        self._emit_thought(ThoughtType.PLAN_STEP, "Decomposing query into sub-questions...")

        # Generate sub-questions (placeholder - would use LLM)
        # For now, create simple decomposition based on query structure
        sub_questions = []

        query_lower = state.query.lower()

        if "and" in query_lower:
            # Split on "and" for compound questions
            parts = state.query.split(" and ")
            sub_questions.extend([p.strip() + "?" for p in parts if len(p.strip()) > 5])

        if "compare" in query_lower or "vs" in query_lower:
            sub_questions.append(f"What are the key characteristics of the first item in: {state.query}?")
            sub_questions.append(f"What are the key characteristics of the second item in: {state.query}?")
            sub_questions.append("What are the main differences between them?")

        if not sub_questions:
            # Default decomposition
            sub_questions = [
                f"What is the main subject of: {state.query}?",
                f"What context is needed to answer: {state.query}?",
                state.query,  # Original query as final sub-question
            ]

        state.sub_questions = sub_questions[:5]  # Limit to 5
        state.add_trace("decompose", "sub_questions_generated", {"count": len(state.sub_questions)})

        self._emit_thought(ThoughtType.PLAN_STEP, f"Decomposed into {len(state.sub_questions)} sub-questions")

        state.phase = ReasoningPhase.RETRIEVE
        return state

    async def _retrieve_context(self, state: ReasoningState) -> ReasoningState:
        """Retrieve relevant context for the query.

        Args:
            state: Current reasoning state

        Returns:
            Updated state with context
        """
        state.add_trace("retrieve", "fetching_context")
        self._emit_thought(ThoughtType.SEARCH, "Retrieving relevant context...")

        # If context already provided, skip retrieval
        if state.context:
            self._emit_thought(ThoughtType.EVIDENCE_FOUND, f"Using {len(state.context)} pre-loaded context documents")
            state.phase = ReasoningPhase.GENERATE_HYPOTHESES
            return state

        # Placeholder for actual retrieval
        # Would integrate with expert's knowledge base
        state.context = []

        self._emit_thought(ThoughtType.SEARCH, "No context retrieved, proceeding with generation")
        state.phase = ReasoningPhase.GENERATE_HYPOTHESES
        return state

    async def _generate_hypotheses(self, state: ReasoningState) -> ReasoningState:
        """Generate hypotheses for the query.

        Generates 3-5 hypotheses when ambiguity is detected.
        Uses schema-validated JSON responses with retry-repair loop.

        Args:
            state: Current reasoning state

        Returns:
            Updated state with hypotheses
        """
        state.add_trace("generate_hypotheses", "creating_hypotheses")
        self._emit_thought(ThoughtType.PLAN_STEP, "Generating hypotheses...")

        # Determine if query is ambiguous
        ambiguity_indicators = [
            "best" in state.query.lower(),
            "should" in state.query.lower(),
            "opinion" in state.query.lower(),
            "think" in state.query.lower(),
            len(state.sub_questions) > 2,
        ]

        is_ambiguous = sum(ambiguity_indicators) >= 1

        if is_ambiguous:
            # Generate multiple hypotheses
            num_hypotheses = 3
            self._emit_thought(
                ThoughtType.PLAN_STEP, f"Ambiguous query detected, generating {num_hypotheses} hypotheses"
            )
        else:
            num_hypotheses = 1

        # Generate hypotheses with the LLM. There is deliberately NO synthetic
        # fallback: fabricating "Hypothesis N for: <query>" placeholders at high
        # confidence let an absent/failed model surface as a confident answer
        # (a silent-degradation bug - it produced garbage council perspectives).
        # When generation yields nothing we stay degraded and let _synthesize
        # emit an honest "Unable to generate a confident answer." instead.
        if self.llm_client:
            hypotheses_data = await self._generate_hypotheses_with_llm(state.query, state.context, num_hypotheses)
            for h_data in (hypotheses_data or {}).get("hypotheses", []):
                text = str(h_data.get("text", "")).strip()
                if not text:
                    continue  # a blank hypothesis is not content
                state.hypotheses.append(
                    Hypothesis(
                        id=h_data.get("id", f"h_{len(state.hypotheses) + 1}"),
                        text=text,
                        confidence=h_data.get("confidence", 0.5),
                        evidence=h_data.get("evidence", []),
                    )
                )

        if not state.hypotheses:
            state.is_degraded = True
            self._emit_thought(ThoughtType.ERROR, "Hypothesis generation unavailable; degrading honestly")

        state.add_trace(
            "generate_hypotheses", "hypotheses_created", {"count": len(state.hypotheses), "degraded": state.is_degraded}
        )

        self._emit_thought(ThoughtType.PLAN_STEP, f"Generated {len(state.hypotheses)} hypotheses")

        state.phase = ReasoningPhase.VERIFY_CLAIMS
        return state

    async def _generate_hypotheses_with_llm(
        self, query: str, context: list[dict], num_hypotheses: int, max_retries: int = 3
    ) -> dict[str, Any] | None:
        """Generate hypotheses using LLM with retry-repair loop.

        Args:
            query: The user's query
            context: Retrieved context
            num_hypotheses: Number of hypotheses to generate
            max_retries: Maximum retry attempts

        Returns:
            Validated hypothesis data or None if all retries failed
        """
        prompt = f"""Generate {num_hypotheses} hypotheses for the following query.

Query: {query}

Context: {json.dumps(context[:3]) if context else "No context available"}

Respond with valid JSON in this exact format:
{{
    "hypotheses": [
        {{
            "id": "h_1",
            "text": "The hypothesis text",
            "confidence": 0.8,
            "reasoning": "Why this hypothesis is plausible"
        }}
    ]
}}

Generate exactly {num_hypotheses} hypotheses with confidence scores between 0 and 1."""

        for attempt in range(max_retries):
            try:
                if self.llm_client and hasattr(self.llm_client, "generate"):
                    response = await self.llm_client.generate(prompt)
                else:
                    return None

                # Try to parse JSON
                try:
                    data = json.loads(response)
                except json.JSONDecodeError:
                    # Try repair
                    data = HypothesisSchema.repair(response)
                    if data is None:
                        self._emit_thought(
                            ThoughtType.ERROR, f"JSON parse failed (attempt {attempt + 1}/{max_retries})"
                        )
                        continue

                # Validate schema
                is_valid, error = HypothesisSchema.validate(data)
                if not is_valid:
                    self._emit_thought(
                        ThoughtType.ERROR, f"Schema validation failed: {error} (attempt {attempt + 1}/{max_retries})"
                    )
                    continue

                return data

            except Exception as e:
                self._emit_thought(ThoughtType.ERROR, f"LLM call failed: {e!s} (attempt {attempt + 1}/{max_retries})")

        return None

    async def _verify_claims(self, state: ReasoningState) -> ReasoningState:
        """Extract and verify claims from hypotheses.

        Extracts atomic claims from draft answers, checks each against
        retrieved sources, and detects contradictions.

        Args:
            state: Current reasoning state

        Returns:
            Updated state with verified claims
        """
        state.add_trace("verify_claims", "extracting_claims")
        self._emit_thought(ThoughtType.PLAN_STEP, "Extracting and verifying claims...")

        # Extract atomic claims from active hypotheses
        for hypothesis in state.hypotheses:
            if not hypothesis.is_active:
                continue

            # Extract claims from hypothesis text
            extracted_claims = self._extract_atomic_claims(hypothesis)

            for i, claim_text in enumerate(extracted_claims):
                claim = Claim(id=f"c_{hypothesis.id}_{i}", text=claim_text, source_hypothesis_id=hypothesis.id)
                state.claims.append(claim)

        self._emit_thought(ThoughtType.PLAN_STEP, f"Extracted {len(state.claims)} atomic claims")

        # Verify claims and detect contradictions with the model (the graph is
        # already model-driven). Grounding and contradiction are meaning, not word
        # overlap, so there is no lexical keyword/antonym verdict: without a model
        # we make no positive claim - unverified, no contradictions - which
        # degrades honestly instead of asserting meaning from string matching
        # (AGENTIC_BALANCE.md / checks-deterministic-vs-agentic.md).
        analysis = await self._analyze_claims(state.claims, state.context)
        for claim in state.claims:
            grounded = analysis.grounding.get(claim.id)
            claim.verified = bool(grounded and grounded.get("verified"))
            claim.verification_sources = list(grounded.get("sources", [])) if grounded else []
            if claim.verified:
                state.verified_claims.append(claim)
                # _emit_thought takes no evidence_refs; the sources live on the
                # claim and in the phase trace. (Removing the bad kwarg fixes a
                # latent TypeError that the old lexical path rarely reached and
                # the model path now does.)
                self._emit_thought(ThoughtType.EVIDENCE_FOUND, f"Verified: {claim.text[:50]}...")

        contradictions = analysis.contradictions
        state.contradictions = contradictions

        # Update claim contradiction references
        for contradiction in contradictions:
            for claim_id in contradiction.get("claim_ids", []):
                for claim in state.claims:
                    if claim.id == claim_id:
                        other_ids = [cid for cid in contradiction["claim_ids"] if cid != claim_id]
                        claim.contradicts.extend(other_ids)

        if contradictions:
            self._emit_thought(
                ThoughtType.ERROR, f"Detected {len(contradictions)} contradictions, triggering self-correction"
            )
            state.phase = ReasoningPhase.SELF_CORRECT
        else:
            self._emit_thought(
                ThoughtType.EVIDENCE_FOUND, f"Verified {len(state.verified_claims)}/{len(state.claims)} claims"
            )
            state.phase = ReasoningPhase.SYNTHESIZE

        state.add_trace(
            "verify_claims",
            "verification_complete",
            {
                "total_claims": len(state.claims),
                "verified_claims": len(state.verified_claims),
                "contradictions": len(contradictions),
            },
        )

        return state

    def _extract_atomic_claims(self, hypothesis: Hypothesis) -> list[str]:
        """Extract atomic claims from a hypothesis.

        Breaks down hypothesis text into individual verifiable claims.

        Args:
            hypothesis: The hypothesis to extract claims from

        Returns:
            List of atomic claim strings
        """
        text = hypothesis.text
        claims = []

        # Split on sentence boundaries
        sentences = re.split(r"[.!?]+", text)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:  # Skip very short fragments
                continue

            # Check if sentence contains a claim (has subject and predicate)
            # Simple heuristic: contains a verb-like word
            if any(
                word in sentence.lower()
                for word in ["is", "are", "was", "were", "has", "have", "can", "will", "should", "must"]
            ):
                claims.append(sentence)

        # If no claims extracted, use the whole hypothesis as one claim
        if not claims and text.strip():
            claims.append(text.strip())

        return claims

    def _build_claim_analysis_prompt(self, claims: list[Claim], context: list[dict[str, Any]]) -> str:
        """Prompt the model to ground claims in the sources and flag contradictions."""
        claim_lines = "\n".join(f"[{c.id}] (from {c.source_hypothesis_id}) {c.text}" for c in claims)
        if context:
            source_lines = "\n".join(
                f"[{doc.get('id', f'context_{i}')}] {str(doc.get('content', doc.get('text', '')))[:500]}"
                for i, doc in enumerate(context)
            )
        else:
            source_lines = "(no sources provided)"
        return (
            "You verify claims against source context for a reasoning system. "
            "Use ONLY the sources; do not rely on prior knowledge.\n\n"
            f"Claims:\n{claim_lines}\n\n"
            f"Sources:\n{source_lines}\n\n"
            "For each claim, decide whether the sources SUPPORT it (it is entailed by at least one "
            "source); a claim with no supporting source is unsupported. Also list any pairs of claims "
            "that CONTRADICT each other.\n\n"
            "Respond with JSON only, no prose:\n"
            '{"grounding": [{"id": "<claim id>", "supported": true, "sources": ["<source id>"]}], '
            '"contradictions": [{"claim_ids": ["<id>", "<id>"], "description": "<why>"}]}'
        )

    async def _analyze_claims(self, claims: list[Claim], context: list[dict[str, Any]]) -> ClaimAnalysis:
        """Model-based grounding + contradiction verdict over the claims.

        Grounding is retrieval-grounded judgment and contradiction is entailment;
        neither is decidable from word overlap (the HANS/ROUGE failure mode), so
        the verdict is the model's. Without a usable model this returns an empty
        analysis - nothing verified, no contradictions - an honest no-conclusion
        rather than a lexical guess. The graph is already model-driven, so this
        adds one bounded call alongside hypothesis generation. See
        docs/design/checks-deterministic-vs-agentic.md.
        """
        if not claims or not self.llm_client or not hasattr(self.llm_client, "generate"):
            return ClaimAnalysis()
        try:
            response = await self.llm_client.generate(self._build_claim_analysis_prompt(claims, context))
        except Exception as exc:
            self._emit_thought(ThoughtType.ERROR, f"Claim analysis failed: {exc!s}; treating claims as unverified")
            return ClaimAnalysis()
        try:
            data = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            data = HypothesisSchema.repair(response) if isinstance(response, str) else None
        if not isinstance(data, dict):
            self._emit_thought(ThoughtType.ERROR, "Claim analysis JSON parse failed; treating claims as unverified")
            return ClaimAnalysis()
        return self._parse_claim_analysis(data, claims)

    def _parse_claim_analysis(self, data: dict[str, Any], claims: list[Claim]) -> ClaimAnalysis:
        """Shape the model's JSON into a ClaimAnalysis (parse, don't validate).

        Unknown claim ids are dropped, types coerced, and same-hypothesis
        contradiction pairs filtered - a hypothesis's own claims are assumed
        internally coherent, which is a structural (form) rule, not a meaning
        verdict. The grounding/contradiction decisions themselves stay the
        model's.
        """
        claim_ids = {c.id for c in claims}
        source_hypothesis = {c.id: c.source_hypothesis_id for c in claims}

        grounding: dict[str, dict[str, Any]] = {}
        for entry in data.get("grounding", []) or []:
            if not isinstance(entry, dict):
                continue
            cid = str(entry.get("id", ""))
            if cid not in claim_ids:
                continue
            raw_sources = entry.get("sources", [])
            sources = [str(s) for s in raw_sources] if isinstance(raw_sources, list) else []
            grounding[cid] = {"verified": bool(entry.get("supported")), "sources": sources}

        contradictions: list[dict[str, Any]] = []
        seen: set[frozenset[str]] = set()
        for entry in data.get("contradictions", []) or []:
            if not isinstance(entry, dict):
                continue
            ids = [str(x) for x in entry.get("claim_ids", []) if str(x) in claim_ids]
            if len(set(ids)) < 2:
                continue
            a, b = ids[0], ids[1]
            if source_hypothesis.get(a) == source_hypothesis.get(b):
                continue  # same hypothesis: assumed coherent (a form rule, not a verdict)
            key = frozenset((a, b))
            if key in seen:
                continue
            seen.add(key)
            contradictions.append(
                {"type": "model", "claim_ids": [a, b], "description": str(entry.get("description", ""))}
            )

        return ClaimAnalysis(grounding=grounding, contradictions=contradictions)

    async def _self_correct(self, state: ReasoningState) -> ReasoningState:
        """Self-correct based on detected contradictions.

        Args:
            state: Current reasoning state

        Returns:
            Updated state after correction
        """
        state.add_trace("self_correct", "resolving_contradictions")
        self._emit_thought(ThoughtType.PLAN_STEP, "Self-correcting based on contradictions...")

        # Prune hypotheses involved in contradictions
        for contradiction in state.contradictions:
            claim_ids = contradiction.get("claim_ids", [])
            for hypothesis in state.hypotheses:
                if any(c.source_hypothesis_id == hypothesis.id for c in state.claims if c.id in claim_ids):
                    hypothesis.is_active = False
                    hypothesis.pruned_reason = "Involved in contradiction"

        # Check if any hypotheses remain
        active_hypotheses = [h for h in state.hypotheses if h.is_active]

        if not active_hypotheses:
            self._emit_thought(ThoughtType.ERROR, "All hypotheses pruned, entering degraded mode")
            state.is_degraded = True
            # Reactivate highest confidence hypothesis
            if state.hypotheses:
                best = max(state.hypotheses, key=lambda h: h.confidence)
                best.is_active = True
                best.pruned_reason = None

        state.contradictions = []  # Clear after handling
        state.phase = ReasoningPhase.SYNTHESIZE
        return state

    async def _synthesize(self, state: ReasoningState) -> ReasoningState:
        """Synthesize final answer from verified claims.

        Args:
            state: Current reasoning state

        Returns:
            Updated state with synthesis
        """
        state.add_trace("synthesize", "creating_synthesis")
        self._emit_thought(ThoughtType.SYNTHESIS, "Synthesizing final answer...")

        # Get active hypotheses
        active_hypotheses = [h for h in state.hypotheses if h.is_active]

        if not active_hypotheses:
            state.synthesis = "Unable to generate a confident answer."
            state.confidence = 0.0
        else:
            # Use highest confidence hypothesis
            best = max(active_hypotheses, key=lambda h: h.confidence)
            state.synthesis = best.text
            state.confidence = best.confidence

            # Adjust confidence based on verification
            if state.verified_claims:
                verification_rate = len(state.verified_claims) / max(len(state.claims), 1)
                state.confidence *= verification_rate

            # Penalize if in degraded mode
            if state.is_degraded:
                state.confidence *= 0.7

        self._emit_thought(
            ThoughtType.DECISION,
            f"Synthesis complete with confidence {state.confidence:.0%}",
            confidence=state.confidence,
        )

        state.phase = ReasoningPhase.COMPLETE
        return state

    def _emit_thought(self, thought_type: ThoughtType, text: str, confidence: float | None = None):
        """Emit a thought to the thought stream.

        Args:
            thought_type: Type of thought
            text: Thought text
            confidence: Optional confidence score
        """
        if self.thought_stream:
            self.thought_stream.emit(thought_type=thought_type, public_text=text, confidence=confidence)

    def get_active_hypotheses(self, state: ReasoningState) -> list[Hypothesis]:
        """Get active (non-pruned) hypotheses.

        Args:
            state: Current reasoning state

        Returns:
            List of active hypotheses
        """
        return [h for h in state.hypotheses if h.is_active]

    def should_use_tot(self, query: str) -> bool:
        """Determine if Tree of Thoughts should be used for a query.

        Args:
            query: The user's query

        Returns:
            True if ToT reasoning is recommended
        """
        # Complexity indicators
        indicators = [
            len(query.split()) > 10,
            "how" in query.lower(),
            "why" in query.lower(),
            "compare" in query.lower(),
            "implications" in query.lower(),
            "relationship" in query.lower(),
            "analyze" in query.lower(),
            "evaluate" in query.lower(),
        ]

        return sum(indicators) >= 2
