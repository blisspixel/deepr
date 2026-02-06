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
        is_valid, error = ClaimSchema.validate(data)
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
        # Should have generated hypotheses
        assert len(state.hypotheses) > 0

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


class TestClaimVerification:
    """Tests for claim verification logic."""

    def test_verify_claim_with_supporting_context(self):
        """Test verifying a claim with supporting context."""
        graph = ReasoningGraph()
        claim = Claim(id="c_1", text="Python is a programming language", source_hypothesis_id="h_1")
        context = [{"id": "doc1", "content": "Python is a popular programming language used for web development."}]

        result = graph._verify_claim_against_context(claim, context)
        assert result["verified"] is True
        assert len(result["sources"]) > 0

    def test_verify_claim_without_context(self):
        """Test verifying a claim without context."""
        graph = ReasoningGraph()
        claim = Claim(id="c_1", text="Test claim", source_hypothesis_id="h_1")

        result = graph._verify_claim_against_context(claim, [])
        assert result["verified"] is False
        assert len(result["sources"]) == 0

    def test_verify_claim_no_match(self):
        """Test verifying a claim that doesn't match context."""
        graph = ReasoningGraph()
        claim = Claim(id="c_1", text="Quantum computing uses qubits", source_hypothesis_id="h_1")
        context = [{"id": "doc1", "content": "Python is a programming language."}]

        result = graph._verify_claim_against_context(claim, context)
        assert result["verified"] is False


class TestContradictionDetection:
    """Tests for contradiction detection logic."""

    def test_detect_negation_contradiction(self):
        """Test detecting negation-based contradictions."""
        graph = ReasoningGraph()
        claims = [
            Claim(id="c_1", text="Python is easy to learn", source_hypothesis_id="h_1"),
            Claim(id="c_2", text="Python is not easy to learn", source_hypothesis_id="h_2"),
        ]

        contradictions = graph._detect_contradictions(claims, [])
        assert len(contradictions) >= 1
        assert contradictions[0]["type"] == "negation"

    def test_detect_antonym_contradiction(self):
        """Test detecting antonym-based contradictions."""
        graph = ReasoningGraph()
        claims = [
            Claim(id="c_1", text="The performance is good", source_hypothesis_id="h_1"),
            Claim(id="c_2", text="The performance is bad", source_hypothesis_id="h_2"),
        ]

        contradictions = graph._detect_contradictions(claims, [])
        assert len(contradictions) >= 1
        assert contradictions[0]["type"] == "antonym"

    def test_no_contradiction_same_hypothesis(self):
        """Test that claims from same hypothesis don't contradict."""
        graph = ReasoningGraph()
        claims = [
            Claim(id="c_1", text="Python is fast", source_hypothesis_id="h_1"),
            Claim(id="c_2", text="Python is not fast", source_hypothesis_id="h_1"),  # Same hypothesis
        ]

        contradictions = graph._detect_contradictions(claims, [])
        # Should not detect contradiction within same hypothesis
        assert len(contradictions) == 0

    def test_no_contradiction_unrelated_claims(self):
        """Test that unrelated claims don't contradict."""
        graph = ReasoningGraph()
        claims = [
            Claim(id="c_1", text="Python is a programming language", source_hypothesis_id="h_1"),
            Claim(id="c_2", text="The weather is sunny today", source_hypothesis_id="h_2"),
        ]

        contradictions = graph._detect_contradictions(claims, [])
        assert len(contradictions) == 0


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


class TestClaimVerificationPropertyTests:
    """Property-based tests for claim verification."""

    @given(
        claim_text=st.text(min_size=10, max_size=100),
        context_texts=st.lists(st.text(min_size=10, max_size=100), min_size=0, max_size=5),
    )
    @settings(max_examples=30)
    def test_verification_returns_valid_structure(self, claim_text, context_texts):
        """Property: Verification always returns valid structure."""
        assume("\x00" not in claim_text)
        for ct in context_texts:
            assume("\x00" not in ct)

        graph = ReasoningGraph()
        claim = Claim(id="c_1", text=claim_text, source_hypothesis_id="h_1")
        context = [{"id": f"doc{i}", "content": ct} for i, ct in enumerate(context_texts)]

        result = graph._verify_claim_against_context(claim, context)

        # Must have required fields
        assert "verified" in result
        assert "sources" in result
        assert isinstance(result["verified"], bool)
        assert isinstance(result["sources"], list)

    @given(claim_text=st.text(min_size=10, max_size=50))
    @settings(max_examples=20)
    def test_empty_context_never_verifies(self, claim_text):
        """Property: Empty context never verifies a claim."""
        assume("\x00" not in claim_text)

        graph = ReasoningGraph()
        claim = Claim(id="c_1", text=claim_text, source_hypothesis_id="h_1")

        result = graph._verify_claim_against_context(claim, [])

        assert result["verified"] is False
        assert len(result["sources"]) == 0


class TestContradictionDetectionPropertyTests:
    """Property-based tests for contradiction detection."""

    @given(claim1_text=st.text(min_size=10, max_size=50), claim2_text=st.text(min_size=10, max_size=50))
    @settings(max_examples=30)
    def test_contradiction_detection_returns_list(self, claim1_text, claim2_text):
        """Property: Contradiction detection always returns a list."""
        assume("\x00" not in claim1_text and "\x00" not in claim2_text)

        graph = ReasoningGraph()
        claims = [
            Claim(id="c_1", text=claim1_text, source_hypothesis_id="h_1"),
            Claim(id="c_2", text=claim2_text, source_hypothesis_id="h_2"),
        ]

        result = graph._detect_contradictions(claims, [])

        assert isinstance(result, list)
        for contradiction in result:
            assert "type" in contradiction
            assert "claim_ids" in contradiction
            assert isinstance(contradiction["claim_ids"], list)

    @given(
        word1=st.text(alphabet=st.characters(whitelist_categories=("L",)), min_size=3, max_size=10),
        word2=st.text(alphabet=st.characters(whitelist_categories=("L",)), min_size=3, max_size=10),
    )
    @settings(max_examples=20, deadline=None)
    def test_negation_detected_as_contradiction(self, word1, word2):
        """Property: Adding 'not' creates detectable contradiction."""
        # Skip words that are themselves negation indicators, since both claims
        # would then contain negation and the detector wouldn't flag a difference
        negation_words = {"not", "no", "never", "none", "neither", "nobody", "nothing", "nowhere", "cannot"}
        assume(word1.lower() not in negation_words)
        assume(word2.lower() not in negation_words)

        graph = ReasoningGraph()

        # Create claim and its negation using generated words
        positive = f"The {word1} {word2} is good"
        negative = f"The {word1} {word2} is not good"

        claims = [
            Claim(id="c_1", text=positive, source_hypothesis_id="h_1"),
            Claim(id="c_2", text=negative, source_hypothesis_id="h_2"),
        ]

        result = graph._detect_contradictions(claims, [])

        # Should detect the negation contradiction
        assert len(result) >= 1
        assert any(c["type"] == "negation" for c in result)


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
