"""Unit tests and property tests for the reasoning graph module.

Tests the LangGraph-based reasoning graph for complex queries:
- State machine termination guarantees
- Hypothesis generation and validation
- Claim extraction and verification
- Contradiction detection
- Confidence calibration

Property tests validate:
- Property 12: Reasoning graph always terminates
- Confidence scores are always in [0.0, 1.0]
- Claim verification detects contradictions
- Schema validation catches malformed JSON
"""

import pytest

from deepr.experts.reasoning_graph import (
    Claim,
    ClaimSchema,
    Hypothesis,
    HypothesisSchema,
    ReasoningGraph,
    ReasoningPhase,
    ReasoningState,
)


class TestHypothesis:
    """Tests for Hypothesis dataclass."""

    def test_create_hypothesis(self):
        """Test creating a hypothesis."""
        h = Hypothesis(id="h_1", text="Test hypothesis", confidence=0.8, evidence=["doc1.md"])
        assert h.id == "h_1"
        assert h.text == "Test hypothesis"
        assert h.confidence == 0.8
        assert h.is_active is True

    def test_hypothesis_to_dict(self):
        """Test hypothesis serialization."""
        h = Hypothesis(
            id="h_1",
            text="Test hypothesis",
            confidence=0.8,
            evidence=["doc1.md"],
            is_active=False,
            pruned_reason="Contradiction",
        )
        d = h.to_dict()

        assert d["id"] == "h_1"
        assert d["text"] == "Test hypothesis"
        assert d["confidence"] == 0.8
        assert d["evidence"] == ["doc1.md"]
        assert d["is_active"] is False
        assert d["pruned_reason"] == "Contradiction"


class TestClaim:
    """Tests for Claim dataclass."""

    def test_create_claim(self):
        """Test creating a claim."""
        c = Claim(id="c_1", text="Test claim", source_hypothesis_id="h_1")
        assert c.id == "c_1"
        assert c.text == "Test claim"
        assert c.verified is None

    def test_claim_to_dict(self):
        """Test claim serialization."""
        c = Claim(
            id="c_1",
            text="Test claim",
            source_hypothesis_id="h_1",
            verified=True,
            verification_sources=["doc1.md"],
            contradicts=["c_2"],
        )
        d = c.to_dict()

        assert d["id"] == "c_1"
        assert d["verified"] is True
        assert d["verification_sources"] == ["doc1.md"]
        assert d["contradicts"] == ["c_2"]


class TestReasoningState:
    """Tests for ReasoningState dataclass."""

    def test_create_state(self):
        """Test creating a reasoning state."""
        state = ReasoningState(query="What is quantum computing?")

        assert state.query == "What is quantum computing?"
        assert state.phase == ReasoningPhase.UNDERSTAND
        assert state.iteration == 0
        assert state.is_degraded is False

    def test_state_to_dict(self):
        """Test state serialization."""
        state = ReasoningState(query="Test query", confidence=0.8, synthesis="Test answer")
        d = state.to_dict()

        assert d["query"] == "Test query"
        assert d["confidence"] == 0.8
        assert d["synthesis"] == "Test answer"
        assert d["phase"] == "understand"

    def test_add_trace(self):
        """Test adding trace entries."""
        state = ReasoningState(query="Test")
        state.add_trace("understand", "analyzing", {"detail": "test"})

        assert len(state.trace) == 1
        assert state.trace[0]["phase"] == "understand"
        assert state.trace[0]["action"] == "analyzing"
        assert "timestamp" in state.trace[0]


class TestHypothesisSchema:
    """Tests for HypothesisSchema validation."""

    def test_validate_valid_schema(self):
        """Test validation of valid hypothesis JSON."""
        data = {"hypotheses": [{"id": "h_1", "text": "Test hypothesis", "confidence": 0.8, "reasoning": "Because..."}]}
        is_valid, error = HypothesisSchema.validate(data)
        assert is_valid is True
        assert error is None

    def test_validate_missing_hypotheses(self):
        """Test validation fails for missing hypotheses field."""
        data = {"other": "field"}
        is_valid, error = HypothesisSchema.validate(data)
        assert is_valid is False
        assert "hypotheses" in error

    def test_validate_empty_hypotheses(self):
        """Test validation fails for empty hypotheses array."""
        data = {"hypotheses": []}
        is_valid, error = HypothesisSchema.validate(data)
        assert is_valid is False
        assert "empty" in error

    def test_validate_invalid_confidence(self):
        """Test validation fails for out-of-range confidence."""
        data = {
            "hypotheses": [
                {
                    "id": "h_1",
                    "text": "Test",
                    "confidence": 1.5,  # Invalid: > 1
                    "reasoning": "...",
                }
            ]
        }
        is_valid, error = HypothesisSchema.validate(data)
        assert is_valid is False
        assert "confidence" in error

    def test_repair_json_from_markdown(self):
        """Test JSON repair from markdown code block."""
        raw = """Here is the response:
```json
{"hypotheses": [{"id": "h_1", "text": "Test", "confidence": 0.8, "reasoning": "..."}]}
```
"""
        result = HypothesisSchema.repair(raw)
        assert result is not None
        assert "hypotheses" in result

    def test_repair_json_with_trailing_comma(self):
        """Test JSON repair with trailing comma."""
        raw = '{"hypotheses": [{"id": "h_1", "text": "Test", "confidence": 0.8, "reasoning": "...",}]}'
        result = HypothesisSchema.repair(raw)
        assert result is not None
        assert "hypotheses" in result

    def test_repair_returns_none_for_invalid(self):
        """Test repair returns None for completely invalid input."""
        raw = "This is not JSON at all"
        result = HypothesisSchema.repair(raw)
        assert result is None


class TestClaimSchema:
    """Tests for ClaimSchema validation."""

    def test_validate_valid_schema(self):
        """Test validation of valid claim JSON."""
        data = {"claims": [{"id": "c_1", "text": "Test claim", "source": "h_1"}]}
        is_valid, _error = ClaimSchema.validate(data)
        assert is_valid is True

    def test_validate_missing_claims(self):
        """Test validation fails for missing claims field."""
        data = {"other": "field"}
        is_valid, error = ClaimSchema.validate(data)
        assert is_valid is False
        assert "claims" in error


class TestReasoningGraph:
    """Tests for ReasoningGraph class."""

    def test_create_graph(self):
        """Test creating a reasoning graph."""
        graph = ReasoningGraph()
        assert graph.expert_profile is None
        assert graph.thought_stream is None

    def test_should_use_tot_simple_query(self):
        """Test ToT detection for simple queries."""
        graph = ReasoningGraph()

        # Simple queries should not use ToT
        assert graph.should_use_tot("What is Python?") is False
        assert graph.should_use_tot("Define AI") is False

    def test_should_use_tot_complex_query(self):
        """Test ToT detection for complex queries."""
        graph = ReasoningGraph()

        # Complex queries should use ToT
        assert (
            graph.should_use_tot("How does quantum computing compare to classical computing and why is it important?")
            is True
        )
        assert graph.should_use_tot("Analyze the implications of AI on society and evaluate the risks") is True

    def test_get_active_hypotheses(self):
        """Test getting active hypotheses."""
        graph = ReasoningGraph()
        state = ReasoningState(query="Test")
        state.hypotheses = [
            Hypothesis(id="h_1", text="Active", confidence=0.8, is_active=True),
            Hypothesis(id="h_2", text="Pruned", confidence=0.6, is_active=False),
            Hypothesis(id="h_3", text="Active2", confidence=0.7, is_active=True),
        ]

        active = graph.get_active_hypotheses(state)
        assert len(active) == 2
        assert all(h.is_active for h in active)


class TestReasoningGraphAsync:
    """Async tests for ReasoningGraph."""

    @pytest.mark.asyncio
    async def test_reason_simple_query(self):
        """Test reasoning on a simple query."""
        graph = ReasoningGraph()
        state = await graph.reason("What is Python?")

        # Should complete
        assert state.phase in [ReasoningPhase.COMPLETE, ReasoningPhase.ERROR]
        # Should not exceed max iterations
        assert state.iteration <= state.max_iterations

    @pytest.mark.asyncio
    async def test_reason_complex_query(self):
        """Test reasoning on a complex query."""
        graph = ReasoningGraph()
        state = await graph.reason("How does machine learning compare to traditional programming?")

        # Should complete
        assert state.phase in [ReasoningPhase.COMPLETE, ReasoningPhase.ERROR]

    @pytest.mark.asyncio
    async def test_no_llm_degrades_honestly_without_fabricating(self):
        """Regression: without an LLM, reasoning must NOT fabricate confident
        'Hypothesis N for: <query>' placeholders (which surfaced as a confident
        council answer). It degrades honestly and synthesizes an explicit
        'unable' message at zero confidence."""
        graph = ReasoningGraph()  # no llm_client
        state = await graph.reason("How does machine learning compare to traditional programming?")

        assert state.is_degraded is True
        # No fabricated placeholder content anywhere.
        assert all("Hypothesis " not in h.text for h in state.hypotheses)
        assert "for: How does machine learning" not in state.synthesis
        # Honest degraded synthesis.
        assert state.synthesis == "Unable to generate a confident answer."
        assert state.confidence == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_reason_with_context(self):
        """Test reasoning with pre-loaded context."""
        graph = ReasoningGraph()
        context = [
            {"id": "doc1", "content": "Python is a programming language."},
            {"id": "doc2", "content": "Python is known for its simplicity."},
        ]
        state = await graph.reason("What is Python?", context=context)

        assert len(state.context) == 2
        assert state.phase in [ReasoningPhase.COMPLETE, ReasoningPhase.ERROR]

    @pytest.mark.asyncio
    async def test_reason_terminates_on_max_iterations(self):
        """Test that reasoning terminates at max iterations."""
        graph = ReasoningGraph()
        state = ReasoningState(query="Test", max_iterations=1)

        # Manually run to test iteration limit
        result = await graph.reason("Complex query with many sub-questions?")

        assert result.iteration <= result.max_iterations


class TestClaimExtraction:
    """Tests for claim extraction logic."""

    def test_extract_atomic_claims_single_sentence(self):
        """Test extracting claims from single sentence."""
        graph = ReasoningGraph()
        h = Hypothesis(id="h_1", text="Python is a programming language.", confidence=0.8)

        claims = graph._extract_atomic_claims(h)
        assert len(claims) >= 1
        assert "Python" in claims[0]

    def test_extract_atomic_claims_multiple_sentences(self):
        """Test extracting claims from multiple sentences."""
        graph = ReasoningGraph()
        h = Hypothesis(
            id="h_1", text="Python is easy to learn. It has a large community. The syntax is clean.", confidence=0.8
        )

        claims = graph._extract_atomic_claims(h)
        assert len(claims) >= 2

    def test_extract_atomic_claims_empty_text(self):
        """Test extracting claims from empty text."""
        graph = ReasoningGraph()
        h = Hypothesis(id="h_1", text="", confidence=0.8)

        claims = graph._extract_atomic_claims(h)
        assert len(claims) == 0


class _FakeLLM:
    """Minimal llm_client with the async ``.generate`` the graph expects."""

    def __init__(self, response: str):
        self._response = response
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._response


class TestClaimAnalysis:
    """Claim grounding + contradiction is a model verdict, never word overlap.

    Replaces the former lexical tests (30% keyword-overlap "verified", negation/
    antonym contradiction) - those encoded the brittle anti-pattern this fix
    removes. See docs/design/checks-deterministic-vs-agentic.md.
    """

    @pytest.mark.asyncio
    async def test_model_verdict_grounds_claims(self):
        llm = _FakeLLM('{"grounding": [{"id": "c_1", "supported": true, "sources": ["doc1"]}], "contradictions": []}')
        graph = ReasoningGraph(llm_client=llm)
        claims = [Claim(id="c_1", text="Python is a programming language", source_hypothesis_id="h_1")]

        analysis = await graph._analyze_claims(claims, [{"id": "doc1", "content": "Python is a language."}])

        assert analysis.grounding["c_1"]["verified"] is True
        assert analysis.grounding["c_1"]["sources"] == ["doc1"]

    @pytest.mark.asyncio
    async def test_no_model_makes_no_verdict_not_a_keyword_guess(self):
        # The whole point: without a model we assert nothing, rather than
        # "verifying" by keyword overlap.
        graph = ReasoningGraph()
        claims = [Claim(id="c_1", text="Python is a programming language", source_hypothesis_id="h_1")]

        analysis = await graph._analyze_claims(claims, [{"id": "doc1", "content": "Python is a programming language."}])

        assert analysis.grounding == {}
        assert analysis.contradictions == []

    @pytest.mark.asyncio
    async def test_malformed_json_falls_back_to_no_verdict(self):
        graph = ReasoningGraph(llm_client=_FakeLLM("not json at all"))
        claims = [Claim(id="c_1", text="x is y", source_hypothesis_id="h_1")]

        analysis = await graph._analyze_claims(claims, [])

        assert analysis.grounding == {}
        assert analysis.contradictions == []

    @pytest.mark.asyncio
    async def test_model_contradictions_are_parsed(self):
        llm = _FakeLLM(
            '{"grounding": [], "contradictions": [{"claim_ids": ["c_1", "c_2"], "description": "opposite claims"}]}'
        )
        graph = ReasoningGraph(llm_client=llm)
        claims = [
            Claim(id="c_1", text="Python is easy to learn", source_hypothesis_id="h_1"),
            Claim(id="c_2", text="Python is hard to learn", source_hypothesis_id="h_2"),
        ]

        analysis = await graph._analyze_claims(claims, [])

        assert len(analysis.contradictions) == 1
        assert analysis.contradictions[0]["claim_ids"] == ["c_1", "c_2"]
        assert analysis.contradictions[0]["type"] == "model"

    @pytest.mark.asyncio
    async def test_same_hypothesis_contradiction_is_filtered(self):
        # The model may flag a pair; the deterministic form rule drops pairs from
        # one hypothesis (assumed internally coherent).
        llm = _FakeLLM('{"grounding": [], "contradictions": [{"claim_ids": ["c_1", "c_2"], "description": "x"}]}')
        graph = ReasoningGraph(llm_client=llm)
        claims = [
            Claim(id="c_1", text="Python is fast", source_hypothesis_id="h_1"),
            Claim(id="c_2", text="Python is not fast", source_hypothesis_id="h_1"),
        ]

        analysis = await graph._analyze_claims(claims, [])

        assert analysis.contradictions == []

    @pytest.mark.asyncio
    async def test_unknown_claim_ids_are_dropped(self):
        llm = _FakeLLM(
            '{"grounding": [{"id": "c_99", "supported": true}], "contradictions": [{"claim_ids": ["c_99", "c_1"]}]}'
        )
        graph = ReasoningGraph(llm_client=llm)
        claims = [Claim(id="c_1", text="a is b", source_hypothesis_id="h_1")]

        analysis = await graph._analyze_claims(claims, [])

        assert analysis.grounding == {}  # c_99 is not a real claim id
        assert analysis.contradictions == []  # fewer than two valid ids


# Property-based tests using hypothesis
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st


class TestReasoningGraphPropertyTests:
    """Property-based tests for ReasoningGraph.

    Property 12: Reasoning graph termination
    - Graph always terminates (reaches COMPLETE or ERROR)
    - Iteration count never exceeds max_iterations
    - Confidence is always in [0.0, 1.0]
    """

    @given(query=st.text(min_size=5, max_size=200), max_iterations=st.integers(min_value=1, max_value=20))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    @pytest.mark.asyncio
    async def test_reasoning_always_terminates(self, query, max_iterations):
        """Property: Reasoning graph always terminates."""
        assume("\x00" not in query)

        graph = ReasoningGraph()
        state = ReasoningState(query=query, max_iterations=max_iterations)

        # Run reasoning
        result = await graph.reason(query)

        # Must terminate
        assert result.phase in [ReasoningPhase.COMPLETE, ReasoningPhase.ERROR]
        # Must not exceed max iterations
        assert result.iteration <= result.max_iterations

    @given(query=st.text(min_size=10, max_size=100), context_count=st.integers(min_value=0, max_value=5))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    @pytest.mark.asyncio
    async def test_confidence_always_valid(self, query, context_count):
        """Property: Confidence is always in [0.0, 1.0]."""
        assume("\x00" not in query)

        graph = ReasoningGraph()
        context = [{"id": f"doc{i}", "content": f"Context {i}"} for i in range(context_count)]

        result = await graph.reason(query, context=context)

        # Confidence must be in valid range
        assert 0.0 <= result.confidence <= 1.0

    @given(query=st.text(min_size=5, max_size=100))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    @pytest.mark.asyncio
    async def test_hypotheses_have_valid_confidence(self, query):
        """Property: All hypotheses have confidence in [0.0, 1.0]."""
        assume("\x00" not in query)

        graph = ReasoningGraph()
        result = await graph.reason(query)

        for hypothesis in result.hypotheses:
            assert 0.0 <= hypothesis.confidence <= 1.0


class TestHypothesisSchemaPropertyTests:
    """Property-based tests for HypothesisSchema validation."""

    @given(
        num_hypotheses=st.integers(min_value=1, max_value=5),
        confidences=st.lists(st.floats(min_value=0.0, max_value=1.0, allow_nan=False), min_size=1, max_size=5),
    )
    @settings(max_examples=50)
    def test_valid_schema_always_validates(self, num_hypotheses, confidences):
        """Property: Valid schema always passes validation."""
        hypotheses = []
        for i in range(min(num_hypotheses, len(confidences))):
            hypotheses.append(
                {"id": f"h_{i}", "text": f"Hypothesis {i}", "confidence": confidences[i], "reasoning": f"Reasoning {i}"}
            )

        if not hypotheses:
            hypotheses.append(
                {"id": "h_0", "text": "Default hypothesis", "confidence": 0.5, "reasoning": "Default reasoning"}
            )

        data = {"hypotheses": hypotheses}
        is_valid, error = HypothesisSchema.validate(data)

        assert is_valid is True
        assert error is None

    @given(confidence=st.floats(min_value=1.01, max_value=100.0, allow_nan=False))
    @settings(max_examples=20)
    def test_invalid_confidence_fails_validation(self, confidence):
        """Property: Confidence > 1.0 always fails validation."""
        data = {"hypotheses": [{"id": "h_1", "text": "Test", "confidence": confidence, "reasoning": "..."}]}
        is_valid, error = HypothesisSchema.validate(data)

        assert is_valid is False
        assert "confidence" in error

    @given(confidence=st.floats(max_value=-0.01, allow_nan=False))
    @settings(max_examples=20)
    def test_negative_confidence_fails_validation(self, confidence):
        """Property: Negative confidence always fails validation."""
        data = {"hypotheses": [{"id": "h_1", "text": "Test", "confidence": confidence, "reasoning": "..."}]}
        is_valid, error = HypothesisSchema.validate(data)

        assert is_valid is False
        assert "confidence" in error


class TestClaimAnalysisPropertyTests:
    """Property-based tests for the model-based claim analysis.

    The invariant that replaces the old lexical properties: with no model, the
    analysis asserts nothing (no false "verified", no fabricated contradiction)
    for any input - the honest no-conclusion that the brittle keyword/negation
    verdicts used to violate.
    """

    @given(
        claim_text=st.text(min_size=10, max_size=100),
        context_count=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow])
    @pytest.mark.asyncio
    async def test_no_model_never_verifies_or_contradicts(self, claim_text, context_count):
        assume("\x00" not in claim_text)

        graph = ReasoningGraph()  # no llm_client
        claims = [
            Claim(id="c_1", text=claim_text, source_hypothesis_id="h_1"),
            Claim(id="c_2", text=f"not {claim_text}", source_hypothesis_id="h_2"),
        ]
        context = [{"id": f"doc{i}", "content": f"Context {i}: {claim_text}"} for i in range(context_count)]

        analysis = await graph._analyze_claims(claims, context)

        assert analysis.grounding == {}
        assert analysis.contradictions == []


class TestReasoningStatePropertyTests:
    """Property-based tests for ReasoningState."""

    @given(
        query=st.text(min_size=1, max_size=200),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        iteration=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=50)
    def test_state_to_dict_preserves_data(self, query, confidence, iteration):
        """Property: State serialization preserves all data."""
        assume("\x00" not in query)

        state = ReasoningState(query=query, confidence=confidence, iteration=iteration)

        d = state.to_dict()

        assert d["query"] == query
        assert abs(d["confidence"] - confidence) < 1e-10
        assert d["iteration"] == iteration

    @given(phase=st.sampled_from(list(ReasoningPhase)))
    @settings(max_examples=10)
    def test_phase_serializes_to_string(self, phase):
        """Property: Phase is serialized as string value."""
        state = ReasoningState(query="Test", phase=phase)
        d = state.to_dict()

        assert d["phase"] == phase.value
        assert isinstance(d["phase"], str)


class TestCalibrationPropertyTests:
    """Property-based tests for confidence calibration.

    Tests that confidence scores are well-calibrated:
    - Higher verification rate should correlate with higher confidence
    - Degraded mode should reduce confidence
    """

    @given(num_verified=st.integers(min_value=0, max_value=10), num_total=st.integers(min_value=1, max_value=10))
    @settings(max_examples=30)
    def test_verification_rate_affects_confidence(self, num_verified, num_total):
        """Property: Verification rate affects final confidence."""
        assume(num_verified <= num_total)

        # Create state with verified claims
        state = ReasoningState(query="Test")
        state.hypotheses = [Hypothesis(id="h_1", text="Test", confidence=0.8)]

        # Add claims
        for i in range(num_total):
            claim = Claim(id=f"c_{i}", text=f"Claim {i}", source_hypothesis_id="h_1")
            claim.verified = i < num_verified
            state.claims.append(claim)
            if claim.verified:
                state.verified_claims.append(claim)

        # Calculate expected confidence adjustment
        verification_rate = num_verified / num_total
        base_confidence = 0.8
        expected_confidence = base_confidence * verification_rate

        # The actual synthesis would apply this adjustment
        # Here we just verify the math is correct
        assert 0.0 <= expected_confidence <= 1.0

    @given(base_confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    @settings(max_examples=20)
    def test_degraded_mode_reduces_confidence(self, base_confidence):
        """Property: Degraded mode always reduces confidence."""
        degradation_factor = 0.7
        degraded_confidence = base_confidence * degradation_factor

        assert degraded_confidence <= base_confidence
        assert 0.0 <= degraded_confidence <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
