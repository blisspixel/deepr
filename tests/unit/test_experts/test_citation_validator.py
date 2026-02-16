"""Tests for deepr.experts.citation_validator.CitationValidator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.core.contracts import Claim, Source, SourceValidation, SupportClass, TrustClass
from deepr.experts.citation_validator import CitationValidator


def _make_claim(statement: str, source_titles: list[str], claim_id: str = "c1") -> Claim:
    sources = [
        Source.create(title=t, trust_class=TrustClass.SECONDARY)
        for t in source_titles
    ]
    return Claim(
        id=claim_id,
        statement=statement,
        domain="test",
        confidence=0.8,
        sources=sources,
    )


# ---------------------------------------------------------------------------
# CitationValidator._find_source_content
# ---------------------------------------------------------------------------


class TestFindSourceContent:
    def setup_method(self):
        self.validator = CitationValidator()

    def test_exact_match(self):
        docs = {"paper.md": "Content here"}
        src = Source.create(title="paper.md", trust_class=TrustClass.SECONDARY)
        assert self.validator._find_source_content(src, docs) == "Content here"

    def test_case_insensitive_match(self):
        docs = {"Paper.MD": "Content here"}
        src = Source.create(title="paper.md", trust_class=TrustClass.SECONDARY)
        assert self.validator._find_source_content(src, docs) == "Content here"

    def test_partial_match(self):
        docs = {"research_paper_2024.md": "Long content"}
        src = Source.create(title="research_paper", trust_class=TrustClass.SECONDARY)
        assert self.validator._find_source_content(src, docs) == "Long content"

    def test_no_match(self):
        docs = {"other.md": "Other content"}
        src = Source.create(title="missing.md", trust_class=TrustClass.SECONDARY)
        assert self.validator._find_source_content(src, docs) is None


# ---------------------------------------------------------------------------
# CitationValidator.summarize
# ---------------------------------------------------------------------------


class TestSummarize:
    def setup_method(self):
        self.validator = CitationValidator()

    def test_empty_validations(self):
        summary = self.validator.summarize([])
        assert summary["total"] == 0
        assert summary["support_rate"] == 0.0
        assert summary["flagged_claims"] == []

    def test_all_supported(self):
        validations = [
            SourceValidation(source_id="s1", claim_id="c1", support_class=SupportClass.SUPPORTED, explanation="OK"),
            SourceValidation(source_id="s2", claim_id="c2", support_class=SupportClass.SUPPORTED, explanation="OK"),
        ]
        summary = self.validator.summarize(validations)
        assert summary["total"] == 2
        assert summary["supported"] == 2
        assert summary["support_rate"] == 1.0

    def test_mixed_support(self):
        validations = [
            SourceValidation(source_id="s1", claim_id="c1", support_class=SupportClass.SUPPORTED, explanation=""),
            SourceValidation(source_id="s2", claim_id="c2", support_class=SupportClass.UNSUPPORTED, explanation=""),
            SourceValidation(source_id="s3", claim_id="c3", support_class=SupportClass.PARTIALLY_SUPPORTED, explanation=""),
            SourceValidation(source_id="s4", claim_id="c4", support_class=SupportClass.UNCERTAIN, explanation=""),
        ]
        summary = self.validator.summarize(validations)
        assert summary["total"] == 4
        assert summary["supported"] == 1
        assert summary["unsupported"] == 1
        assert summary["partially_supported"] == 1
        assert summary["uncertain"] == 1
        # support_rate = (1 + 0.5) / 4 = 0.375
        assert summary["support_rate"] == pytest.approx(0.375)
        assert "c2" in summary["flagged_claims"]

    def test_flagged_claims_deduplication(self):
        validations = [
            SourceValidation(source_id="s1", claim_id="c1", support_class=SupportClass.UNSUPPORTED, explanation=""),
            SourceValidation(source_id="s2", claim_id="c1", support_class=SupportClass.UNSUPPORTED, explanation=""),
        ]
        summary = self.validator.summarize(validations)
        assert len(summary["flagged_claims"]) == 1


# ---------------------------------------------------------------------------
# CitationValidator.validate_claims
# ---------------------------------------------------------------------------


class TestValidateClaims:
    @pytest.mark.asyncio
    async def test_no_claims(self):
        validator = CitationValidator()
        result = await validator.validate_claims([], {})
        assert result == []

    @pytest.mark.asyncio
    async def test_no_matching_documents(self):
        validator = CitationValidator()
        claim = _make_claim("Test claim", ["missing.md"])
        result = await validator.validate_claims([claim], {"other.md": "content"})
        assert result == []

    @pytest.mark.asyncio
    async def test_successful_validation(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '[{"index": 0, "support": "supported", "explanation": "Direct support"}]'
        )
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        validator = CitationValidator(client=mock_client)
        claim = _make_claim("Test claim", ["doc.md"])
        docs = {"doc.md": "Supporting content"}

        result = await validator.validate_claims([claim], docs)
        assert len(result) == 1
        assert result[0].support_class == SupportClass.SUPPORTED
        assert result[0].explanation == "Direct support"

    @pytest.mark.asyncio
    async def test_batch_processing(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        # Return all 6 pairs in batch results
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '['
            '{"index": 0, "support": "supported", "explanation": "OK"},'
            '{"index": 1, "support": "unsupported", "explanation": "No"},'
            '{"index": 2, "support": "uncertain", "explanation": "Maybe"},'
            '{"index": 3, "support": "supported", "explanation": "OK"},'
            '{"index": 4, "support": "partially_supported", "explanation": "Partial"}'
            ']'
        )
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        validator = CitationValidator(client=mock_client)
        claims = [
            _make_claim(f"Claim {i}", ["doc.md"], claim_id=f"c{i}")
            for i in range(5)
        ]
        docs = {"doc.md": "Content"}

        result = await validator.validate_claims(claims, docs)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_llm_failure_returns_uncertain(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        validator = CitationValidator(client=mock_client)
        claim = _make_claim("Test", ["doc.md"])
        docs = {"doc.md": "Content"}

        result = await validator.validate_claims([claim], docs)
        assert len(result) == 1
        assert result[0].support_class == SupportClass.UNCERTAIN

    @pytest.mark.asyncio
    async def test_invalid_json_returns_uncertain(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        validator = CitationValidator(client=mock_client)
        claim = _make_claim("Test", ["doc.md"])
        docs = {"doc.md": "Content"}

        result = await validator.validate_claims([claim], docs)
        assert len(result) == 1
        assert result[0].support_class == SupportClass.UNCERTAIN

    @pytest.mark.asyncio
    async def test_markdown_fenced_json(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '```json\n[{"index": 0, "support": "supported", "explanation": "OK"}]\n```'
        )
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        validator = CitationValidator(client=mock_client)
        claim = _make_claim("Test", ["doc.md"])
        docs = {"doc.md": "Content"}

        result = await validator.validate_claims([claim], docs)
        assert len(result) == 1
        assert result[0].support_class == SupportClass.SUPPORTED
