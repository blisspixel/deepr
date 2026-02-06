"""Unit tests and property tests for the evidence module.

Tests the canonical evidence schema used across CLI output, MCP payloads,
and saved reports.

Property tests validate:
- Evidence ID generation is deterministic (same input = same ID)
- FactCheckResult response structure is always valid
- Serialization/deserialization round-trips preserve data
- Verdict enum values are consistent
"""

import pytest

from deepr.core.evidence import Evidence, FactCheckResult, Verdict


class TestEvidence:
    """Test Evidence dataclass."""

    def test_create_evidence_generates_id(self):
        """Test that Evidence.create generates a content-hash ID."""
        evidence = Evidence.create(source="test.md", quote="Test quote")
        assert evidence.id is not None
        assert len(evidence.id) == 12  # SHA256 truncated to 12 chars

    def test_create_evidence_same_content_same_id(self):
        """Test that same content produces same ID."""
        e1 = Evidence.create(source="test.md", quote="Test quote")
        e2 = Evidence.create(source="test.md", quote="Test quote")
        assert e1.id == e2.id

    def test_create_evidence_different_content_different_id(self):
        """Test that different content produces different ID."""
        e1 = Evidence.create(source="test.md", quote="Quote 1")
        e2 = Evidence.create(source="test.md", quote="Quote 2")
        assert e1.id != e2.id

    def test_evidence_to_dict(self):
        """Test Evidence serialization to dict."""
        evidence = Evidence.create(
            source="test.md", quote="Test quote", url="https://example.com", supports=["claim1"], contradicts=["claim2"]
        )
        data = evidence.to_dict()

        assert data["id"] == evidence.id
        assert data["source"] == "test.md"
        assert data["quote"] == "Test quote"
        assert data["url"] == "https://example.com"
        assert data["supports"] == ["claim1"]
        assert data["contradicts"] == ["claim2"]

    def test_evidence_from_dict(self):
        """Test Evidence deserialization from dict."""
        data = {
            "id": "abc123",
            "source": "test.md",
            "quote": "Test quote",
            "url": "https://example.com",
            "retrieved_at": "2025-01-01T00:00:00",
            "supports": ["claim1"],
            "contradicts": [],
        }
        evidence = Evidence.from_dict(data)

        assert evidence.id == "abc123"
        assert evidence.source == "test.md"
        assert evidence.quote == "Test quote"
        assert evidence.url == "https://example.com"

    def test_evidence_to_inline_citation(self):
        """Test inline citation format."""
        evidence = Evidence.create(source="document.md", quote="test")
        citation = evidence.to_inline_citation()
        assert citation == "[Source: document.md]"

    def test_evidence_to_footnote_with_url(self):
        """Test footnote format with URL."""
        evidence = Evidence.create(source="document.md", quote="test", url="https://example.com")
        footnote = evidence.to_footnote()
        assert evidence.id in footnote
        assert "document.md" in footnote
        assert "https://example.com" in footnote

    def test_evidence_to_footnote_without_url(self):
        """Test footnote format without URL."""
        evidence = Evidence.create(source="document.md", quote="test")
        footnote = evidence.to_footnote()
        assert evidence.id in footnote
        assert "document.md" in footnote


class TestVerdict:
    """Test Verdict enum."""

    def test_verdict_values(self):
        """Test that Verdict has expected values."""
        assert Verdict.TRUE.value == "TRUE"
        assert Verdict.FALSE.value == "FALSE"
        assert Verdict.UNCERTAIN.value == "UNCERTAIN"

    def test_verdict_from_string(self):
        """Test creating Verdict from string."""
        assert Verdict("TRUE") == Verdict.TRUE
        assert Verdict("FALSE") == Verdict.FALSE
        assert Verdict("UNCERTAIN") == Verdict.UNCERTAIN

    def test_verdict_invalid_string_raises(self):
        """Test that invalid string raises ValueError."""
        with pytest.raises(ValueError):
            Verdict("INVALID")


class TestFactCheckResult:
    """Test FactCheckResult dataclass."""

    def test_fact_check_result_creation(self):
        """Test creating a FactCheckResult."""
        result = FactCheckResult(claim="Test claim", verdict=Verdict.TRUE, confidence=0.95, scope="general")
        assert result.claim == "Test claim"
        assert result.verdict == Verdict.TRUE
        assert result.confidence == 0.95
        assert result.scope == "general"

    def test_fact_check_result_with_evidence(self):
        """Test FactCheckResult with evidence."""
        evidence = Evidence.create(source="test.md", quote="Supporting quote")
        result = FactCheckResult(
            claim="Test claim", verdict=Verdict.TRUE, confidence=0.9, scope="test", evidence=[evidence]
        )
        assert len(result.evidence) == 1
        assert result.evidence[0].source == "test.md"

    def test_fact_check_result_to_cli_output(self):
        """Test CLI output rendering."""
        result = FactCheckResult(
            claim="Test claim",
            verdict=Verdict.TRUE,
            confidence=0.95,
            scope="general",
            reasoning="Evidence supports the claim",
        )
        output = result.to_cli_output()

        assert "TRUE" in output
        assert "95%" in output
        assert "general" in output
        assert "Evidence supports the claim" in output

    def test_fact_check_result_to_mcp_payload(self):
        """Test MCP payload rendering."""
        evidence = Evidence.create(source="test.md", quote="Quote")
        result = FactCheckResult(
            claim="Test claim",
            verdict=Verdict.FALSE,
            confidence=0.8,
            scope="test",
            evidence=[evidence],
            reasoning="Contradicted by evidence",
            cost=0.01,
        )
        payload = result.to_mcp_payload()

        assert payload["claim"] == "Test claim"
        assert payload["verdict"] == "FALSE"
        assert payload["confidence"] == 0.8
        assert payload["scope"] == "test"
        assert len(payload["evidence"]) == 1
        assert payload["reasoning"] == "Contradicted by evidence"
        assert payload["cost"] == 0.01

    def test_fact_check_result_round_trip(self):
        """Test serialization/deserialization round-trip."""
        original = FactCheckResult(
            claim="Test claim",
            verdict=Verdict.UNCERTAIN,
            confidence=0.5,
            scope="limited",
            evidence=[Evidence.create(source="doc.md", quote="Quote")],
            reasoning="Insufficient evidence",
            cost=0.02,
        )

        data = original.to_dict()
        restored = FactCheckResult.from_dict(data)

        assert restored.claim == original.claim
        assert restored.verdict == original.verdict
        assert restored.confidence == original.confidence
        assert restored.scope == original.scope
        assert len(restored.evidence) == len(original.evidence)
        assert restored.reasoning == original.reasoning
        assert restored.cost == original.cost


# Property-based tests using hypothesis
from hypothesis import assume, given, settings
from hypothesis import strategies as st


class TestEvidencePropertyTests:
    """Property-based tests for Evidence class.

    Property 2: Evidence ID determinism
    - Same source + quote always produces same ID
    - Different content produces different IDs (with high probability)
    """

    @given(source=st.text(min_size=1, max_size=100), quote=st.text(min_size=1, max_size=500))
    @settings(max_examples=100)
    def test_evidence_id_deterministic(self, source, quote):
        """Property: Evidence.create is deterministic - same input = same ID."""
        assume("\x00" not in source and "\x00" not in quote)

        e1 = Evidence.create(source=source, quote=quote)
        e2 = Evidence.create(source=source, quote=quote)

        assert e1.id == e2.id, "Same content should produce same ID"

    @given(
        source=st.text(min_size=1, max_size=50),
        quote1=st.text(min_size=1, max_size=100),
        quote2=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=100)
    def test_evidence_id_different_for_different_content(self, source, quote1, quote2):
        """Property: Different content produces different IDs."""
        assume("\x00" not in source)
        assume("\x00" not in quote1 and "\x00" not in quote2)
        assume(quote1 != quote2)  # Ensure quotes are different

        e1 = Evidence.create(source=source, quote=quote1)
        e2 = Evidence.create(source=source, quote=quote2)

        assert e1.id != e2.id, "Different content should produce different IDs"

    @given(
        source=st.text(min_size=1, max_size=50),
        quote=st.text(min_size=0, max_size=200),
        url=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
        supports=st.lists(st.text(min_size=1, max_size=20), max_size=5),
        contradicts=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    )
    @settings(max_examples=50)
    def test_evidence_round_trip(self, source, quote, url, supports, contradicts):
        """Property: Evidence serialization round-trip preserves data."""
        assume("\x00" not in source and "\x00" not in quote)
        if url:
            assume("\x00" not in url)

        original = Evidence.create(source=source, quote=quote, url=url, supports=supports, contradicts=contradicts)

        data = original.to_dict()
        restored = Evidence.from_dict(data)

        assert restored.id == original.id
        assert restored.source == original.source
        assert restored.quote == original.quote
        assert restored.url == original.url
        assert restored.supports == original.supports
        assert restored.contradicts == original.contradicts

    @given(source=st.text(min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_evidence_inline_citation_format(self, source):
        """Property: Inline citation always has correct format."""
        assume("\x00" not in source)

        evidence = Evidence.create(source=source, quote="test")
        citation = evidence.to_inline_citation()

        assert citation.startswith("[Source: ")
        assert citation.endswith("]")
        assert source in citation


class TestFactCheckResultPropertyTests:
    """Property-based tests for FactCheckResult.

    Property 3: Fact verification response structure
    - Verdict is always one of TRUE, FALSE, UNCERTAIN
    - Confidence is always in [0.0, 1.0]
    - Serialization round-trip preserves all fields
    """

    @given(
        claim=st.text(min_size=1, max_size=200),
        verdict=st.sampled_from([Verdict.TRUE, Verdict.FALSE, Verdict.UNCERTAIN]),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        scope=st.text(min_size=1, max_size=50),
        reasoning=st.text(min_size=0, max_size=200),
        cost=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    )
    @settings(max_examples=100)
    def test_fact_check_result_structure_valid(self, claim, verdict, confidence, scope, reasoning, cost):
        """Property: FactCheckResult always has valid structure."""
        assume("\x00" not in claim and "\x00" not in scope and "\x00" not in reasoning)

        result = FactCheckResult(
            claim=claim, verdict=verdict, confidence=confidence, scope=scope, reasoning=reasoning, cost=cost
        )

        # Verify structure
        assert result.verdict in [Verdict.TRUE, Verdict.FALSE, Verdict.UNCERTAIN]
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.evidence, list)

    @given(
        claim=st.text(min_size=1, max_size=100),
        verdict=st.sampled_from([Verdict.TRUE, Verdict.FALSE, Verdict.UNCERTAIN]),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        scope=st.text(min_size=1, max_size=50),
        reasoning=st.text(min_size=0, max_size=100),
        cost=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
    )
    @settings(max_examples=50)
    def test_fact_check_result_round_trip(self, claim, verdict, confidence, scope, reasoning, cost):
        """Property: FactCheckResult serialization round-trip preserves data."""
        assume("\x00" not in claim and "\x00" not in scope and "\x00" not in reasoning)

        original = FactCheckResult(
            claim=claim, verdict=verdict, confidence=confidence, scope=scope, reasoning=reasoning, cost=cost
        )

        data = original.to_dict()
        restored = FactCheckResult.from_dict(data)

        assert restored.claim == original.claim
        assert restored.verdict == original.verdict
        assert abs(restored.confidence - original.confidence) < 1e-10
        assert restored.scope == original.scope
        assert restored.reasoning == original.reasoning
        assert abs(restored.cost - original.cost) < 1e-10

    @given(verdict=st.sampled_from([Verdict.TRUE, Verdict.FALSE, Verdict.UNCERTAIN]))
    @settings(max_examples=10)
    def test_fact_check_result_cli_output_contains_verdict(self, verdict):
        """Property: CLI output always contains the verdict."""
        result = FactCheckResult(claim="Test claim", verdict=verdict, confidence=0.5, scope="test")
        output = result.to_cli_output()

        assert verdict.value in output

    @given(confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    @settings(max_examples=50)
    def test_fact_check_result_cli_output_shows_confidence(self, confidence):
        """Property: CLI output shows confidence as percentage."""
        result = FactCheckResult(claim="Test claim", verdict=Verdict.TRUE, confidence=confidence, scope="test")
        output = result.to_cli_output()

        # Confidence should be shown as percentage
        expected_pct = f"{confidence:.0%}"
        assert expected_pct in output or "%" in output

    @given(
        claim=st.text(min_size=1, max_size=100),
        verdict=st.sampled_from([Verdict.TRUE, Verdict.FALSE, Verdict.UNCERTAIN]),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        scope=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50)
    def test_fact_check_result_mcp_payload_structure(self, claim, verdict, confidence, scope):
        """Property: MCP payload always has required fields."""
        assume("\x00" not in claim and "\x00" not in scope)

        result = FactCheckResult(claim=claim, verdict=verdict, confidence=confidence, scope=scope)
        payload = result.to_mcp_payload()

        # Required fields
        assert "claim" in payload
        assert "verdict" in payload
        assert "confidence" in payload
        assert "scope" in payload
        assert "evidence" in payload
        assert "reasoning" in payload
        assert "cost" in payload

        # Verdict is string value
        assert payload["verdict"] in ["TRUE", "FALSE", "UNCERTAIN"]

        # Confidence is in range
        assert 0.0 <= payload["confidence"] <= 1.0

        # Evidence is list
        assert isinstance(payload["evidence"], list)


class TestVerdictPropertyTests:
    """Property-based tests for Verdict enum."""

    @given(verdict=st.sampled_from([Verdict.TRUE, Verdict.FALSE, Verdict.UNCERTAIN]))
    @settings(max_examples=10)
    def test_verdict_value_round_trip(self, verdict):
        """Property: Verdict can be reconstructed from its value."""
        value = verdict.value
        restored = Verdict(value)
        assert restored == verdict

    @given(verdict=st.sampled_from([Verdict.TRUE, Verdict.FALSE, Verdict.UNCERTAIN]))
    @settings(max_examples=10)
    def test_verdict_value_is_uppercase(self, verdict):
        """Property: Verdict values are always uppercase."""
        assert verdict.value == verdict.value.upper()


from deepr.core.evidence import ExpertAnswer


class TestExpertAnswer:
    """Test ExpertAnswer dataclass."""

    def test_create_minimal_answer(self):
        """Should create answer with minimal fields."""
        answer = ExpertAnswer(answer_text="This is the answer")

        assert answer.answer_text == "This is the answer"
        assert answer.evidence == []
        assert answer.confidence == 0.0
        assert answer.cost == 0.0

    def test_create_full_answer(self):
        """Should create answer with all fields."""
        evidence = Evidence.create(source="test.md", quote="Quote")
        answer = ExpertAnswer(
            answer_text="This is the answer",
            evidence=[evidence],
            confidence=0.9,
            cost=0.05,
            reasoning_trace="Step 1: ...\nStep 2: ...",
        )

        assert answer.answer_text == "This is the answer"
        assert len(answer.evidence) == 1
        assert answer.confidence == 0.9
        assert answer.cost == 0.05
        assert answer.reasoning_trace is not None

    def test_to_cli_output_minimal(self):
        """Should render minimal CLI output."""
        answer = ExpertAnswer(answer_text="The answer is 42")
        output = answer.to_cli_output()

        assert "The answer is 42" in output

    def test_to_cli_output_with_evidence(self):
        """Should render CLI output with evidence."""
        evidence = Evidence.create(source="guide.md", quote="Quote", url="https://example.com")
        answer = ExpertAnswer(answer_text="The answer", evidence=[evidence])
        output = answer.to_cli_output()

        assert "The answer" in output
        assert "Sources:" in output
        assert "guide.md" in output

    def test_to_cli_output_with_cost(self):
        """Should show cost in CLI output."""
        answer = ExpertAnswer(answer_text="The answer", cost=0.0123)
        output = answer.to_cli_output()

        assert "Cost:" in output
        assert "$0.0123" in output

    def test_to_cli_output_verbose_with_reasoning(self):
        """Should show reasoning trace in verbose mode."""
        answer = ExpertAnswer(answer_text="The answer", reasoning_trace="Step 1: Analyzed docs\nStep 2: Synthesized")
        output = answer.to_cli_output(verbose=True)

        assert "Reasoning:" in output
        assert "Step 1:" in output

    def test_to_cli_output_verbose_no_reasoning(self):
        """Should not show reasoning section if no trace."""
        answer = ExpertAnswer(answer_text="The answer")
        output = answer.to_cli_output(verbose=True)

        assert "Reasoning:" not in output

    def test_to_mcp_payload(self):
        """Should render MCP payload."""
        evidence = Evidence.create(source="test.md", quote="Quote")
        answer = ExpertAnswer(answer_text="The answer", evidence=[evidence], confidence=0.85, cost=0.02)
        payload = answer.to_mcp_payload()

        assert payload["answer"] == "The answer"
        assert len(payload["evidence"]) == 1
        assert payload["confidence"] == 0.85
        assert payload["cost"] == 0.02

    def test_to_mcp_payload_empty_evidence(self):
        """Should handle empty evidence in payload."""
        answer = ExpertAnswer(answer_text="No sources")
        payload = answer.to_mcp_payload()

        assert payload["answer"] == "No sources"
        assert payload["evidence"] == []


class TestFactCheckResultCliOutput:
    """Additional tests for FactCheckResult CLI output."""

    def test_cli_output_with_evidence_markers(self):
        """Should show support/contradict markers."""
        evidence = Evidence.create(source="test.md", quote="This supports the claim", supports=["claim1"])
        result = FactCheckResult(
            claim="claim1", verdict=Verdict.TRUE, confidence=0.9, scope="test", evidence=[evidence]
        )
        output = result.to_cli_output()

        assert "Evidence:" in output
        assert "test.md" in output

    def test_cli_output_with_url(self):
        """Should show URL in evidence."""
        evidence = Evidence.create(source="test.md", quote="Quote", url="https://example.com/doc")
        result = FactCheckResult(claim="Test", verdict=Verdict.TRUE, confidence=0.9, scope="test", evidence=[evidence])
        output = result.to_cli_output()

        assert "https://example.com/doc" in output

    def test_cli_output_truncates_long_quotes(self):
        """Should truncate very long quotes."""
        long_quote = "A" * 200
        evidence = Evidence.create(source="test.md", quote=long_quote)
        result = FactCheckResult(claim="Test", verdict=Verdict.TRUE, confidence=0.9, scope="test", evidence=[evidence])
        output = result.to_cli_output()

        # Should truncate to ~100 chars + "..."
        assert "..." in output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
