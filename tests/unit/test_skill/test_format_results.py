"""
Property-based tests for result formatting and citation preservation.

Validates: Requirements 8.1
"""

import sys
from datetime import datetime
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Add skills directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "skills" / "deepr-research" / "scripts"))

from format_results import (
    Citation,
    RawResult,
    ResearchMetadata,
    count_citations,
    extract_citations,
    format_citations,
    format_findings,
    format_recommendations,
    format_result,
    validate_citations,
)


# Custom strategies
@st.composite
def citation_strategy(draw):
    """Generate valid Citation objects."""
    index = draw(st.integers(min_value=1, max_value=100))
    source = draw(st.text(min_size=1, max_size=100).filter(lambda x: x.strip()))
    url = draw(st.one_of(st.none(), st.text(min_size=5, max_size=200).map(lambda x: f"https://example.com/{x}")))
    return Citation(index=index, source=source, url=url)


@st.composite
def metadata_strategy(draw):
    """Generate valid ResearchMetadata objects."""
    return ResearchMetadata(
        mode=draw(st.sampled_from(["quick", "standard", "deep_fast", "deep_premium"])),
        model=draw(st.sampled_from(["grok-4-fast", "o4-mini", "o3"])),
        duration_seconds=draw(st.integers(min_value=1, max_value=3600)),
        cost=draw(st.floats(min_value=0, max_value=10, allow_nan=False, allow_infinity=False)),
        job_id=draw(st.text(min_size=8, max_size=32, alphabet="abcdef0123456789")),
    )


@st.composite
def raw_result_strategy(draw):
    """Generate valid RawResult objects."""
    num_citations = draw(st.integers(min_value=0, max_value=10))
    citations = [
        Citation(index=i + 1, source=f"Source {i + 1}", url=f"https://example.com/{i}") for i in range(num_citations)
    ]

    return RawResult(
        title=draw(st.text(min_size=1, max_size=100).filter(lambda x: x.strip())),
        summary=draw(st.text(min_size=1, max_size=500).filter(lambda x: x.strip())),
        findings=draw(st.lists(st.text(min_size=1, max_size=200).filter(lambda x: x.strip()), min_size=0, max_size=10)),
        analysis=draw(st.text(min_size=1, max_size=1000).filter(lambda x: x.strip())),
        recommendations=draw(
            st.lists(st.text(min_size=1, max_size=200).filter(lambda x: x.strip()), min_size=0, max_size=5)
        ),
        citations=citations,
        metadata=draw(metadata_strategy()),
    )


class TestCitationPreservation:
    """Property 5: Citation Preservation in Results"""

    @given(raw_result_strategy())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_all_citations_preserved_in_output(self, result: RawResult):
        """
        Property: All citations from input appear in formatted output.
        Validates: Requirements 8.1
        """
        formatted = format_result(result)

        # All original citations should be in the output
        for citation in result.citations:
            assert f"[{citation.index}]" in formatted, f"Citation [{citation.index}] missing from output"

    @given(raw_result_strategy())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_citation_count_preserved_or_increased(self, result: RawResult):
        """
        Property: Citation count in output >= input citations.
        (May increase if text contains inline citations)
        """
        formatted = format_result(result)
        output_count = count_citations(formatted)

        # Output should have at least as many citations as input
        assert output_count >= len(result.citations)

    @given(raw_result_strategy())
    @settings(max_examples=50)
    def test_validate_citations_returns_true_for_valid_output(self, result: RawResult):
        """
        Property: validate_citations returns True for properly formatted output.
        """
        formatted = format_result(result)
        assert validate_citations(formatted, result.citations)


class TestCitationExtraction:
    """Test citation extraction from text."""

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_extraction_returns_tuple(self, text: str):
        """
        Property: extract_citations always returns (str, list) tuple.
        """
        result = extract_citations(text)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], list)

    def test_markdown_links_converted_to_citations(self):
        """Markdown links should be converted to numeric citations."""
        text = "According to [Wikipedia](https://wikipedia.org), this is true."
        normalized, citations = extract_citations(text)

        assert "[1]" in normalized
        assert len(citations) == 1
        assert citations[0].url == "https://wikipedia.org"

    def test_multiple_links_get_unique_indices(self):
        """Multiple different links should get unique citation indices."""
        text = "[Source A](https://a.com) and [Source B](https://b.com)"
        normalized, citations = extract_citations(text)

        assert "[1]" in normalized
        assert "[2]" in normalized
        assert len(citations) == 2

    def test_duplicate_links_reuse_index(self):
        """Same link appearing twice should reuse the same index."""
        text = "[Source](https://example.com) and again [Source](https://example.com)"
        normalized, citations = extract_citations(text)

        # Should only have one citation
        assert len(citations) == 1
        # Both should reference [1]
        assert normalized.count("[1]") == 2


class TestFormatFunctions:
    """Test individual formatting functions."""

    @given(st.lists(st.text(min_size=1, max_size=100).filter(lambda x: x.strip() and "- " not in x), max_size=10))
    @settings(max_examples=50)
    def test_format_findings_produces_bullet_list(self, findings: list[str]):
        """
        Property: format_findings produces valid bullet list.

        Filters out findings containing "- " to avoid false positives in bullet counting.
        """
        result = format_findings(findings)

        if findings:
            for finding in findings:
                assert finding in result
            assert result.count("- ") == len(findings)
        else:
            assert "No specific findings" in result

    @given(st.lists(st.text(min_size=1, max_size=100).filter(lambda x: x.strip()), max_size=10))
    @settings(max_examples=50)
    def test_format_recommendations_produces_numbered_list(self, recs: list[str]):
        """
        Property: format_recommendations produces valid numbered list.
        """
        result = format_recommendations(recs)

        if recs:
            for i, rec in enumerate(recs):
                assert f"{i + 1}." in result
                assert rec in result
        else:
            assert "No specific recommendations" in result

    @given(st.lists(citation_strategy(), max_size=10))
    @settings(max_examples=50)
    def test_format_citations_includes_all(self, citations: list[Citation]):
        """
        Property: format_citations includes all citation sources.
        """
        result = format_citations(citations)

        if citations:
            for citation in citations:
                assert f"[{citation.index}]" in result
                assert citation.source in result
        else:
            assert "No citations" in result


class TestMetadataFormatting:
    """Test metadata formatting."""

    @given(metadata_strategy())
    @settings(max_examples=50)
    def test_duration_formatted_is_human_readable(self, metadata: ResearchMetadata):
        """
        Property: duration_formatted produces human-readable string.
        """
        result = metadata.duration_formatted
        assert isinstance(result, str)
        assert "second" in result or "minute" in result or "m " in result

    @given(metadata_strategy())
    @settings(max_examples=50)
    def test_cost_formatted_is_valid(self, metadata: ResearchMetadata):
        """
        Property: cost_formatted produces valid cost string.
        """
        result = metadata.cost_formatted
        assert result == "FREE" or result.startswith("$")

    @given(metadata_strategy())
    @settings(max_examples=50)
    def test_timestamp_formatted_is_iso8601(self, metadata: ResearchMetadata):
        """
        Property: timestamp_formatted produces ISO 8601 string.
        """
        result = metadata.timestamp_formatted
        # Should be parseable as ISO format
        datetime.fromisoformat(result)


class TestFullFormatting:
    """Test complete result formatting."""

    @given(raw_result_strategy())
    @settings(max_examples=30)
    def test_format_result_produces_valid_markdown(self, result: RawResult):
        """
        Property: format_result produces valid markdown structure.
        """
        formatted = format_result(result)

        # Should have main sections
        assert "# " in formatted  # Title
        assert "## Summary" in formatted
        assert "## Key Findings" in formatted
        assert "## Analysis" in formatted
        assert "## Recommendations" in formatted
        assert "## Citations" in formatted

    @given(raw_result_strategy())
    @settings(max_examples=30)
    def test_format_result_includes_metadata(self, result: RawResult):
        """
        Property: format_result includes metadata table.
        """
        formatted = format_result(result)

        assert result.metadata.mode in formatted
        assert result.metadata.model in formatted
        assert result.metadata.job_id in formatted

    @given(raw_result_strategy())
    @settings(max_examples=30)
    def test_format_result_preserves_title(self, result: RawResult):
        """
        Property: format_result preserves the original title.
        """
        formatted = format_result(result)
        assert result.title in formatted
