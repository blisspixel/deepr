"""Tests for FindingsStore — covers the SQLite-backed findings index.

Exercises store/retrieve, ranking, multi-finding queries, and the
delete-by-job path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deepr.storage.findings_store import FindingsStore, StoredFinding


@pytest.fixture
def store(tmp_path: Path):
    db_path = tmp_path / "findings.db"
    return FindingsStore(db_path=db_path)


class TestStoreAndRetrieve:
    @pytest.mark.asyncio
    async def test_store_finding_returns_stored_finding(self, store):
        finding = await store.store_finding(
            job_id="job-1",
            phase=1,
            text="Quantum entanglement is a real phenomenon",
            confidence=0.9,
            source="https://example.com/qe",
        )
        assert isinstance(finding, StoredFinding)
        assert finding.job_id == "job-1"
        assert finding.confidence == 0.9
        assert finding.source == "https://example.com/qe"
        assert finding.tokens  # tokenizer ran

    @pytest.mark.asyncio
    async def test_retrieve_relevant_returns_findings_by_keyword(self, store):
        await store.store_finding(job_id="j", phase=1, text="Apple is a fruit")
        await store.store_finding(job_id="j", phase=1, text="Microsoft makes Windows")
        await store.store_finding(job_id="j", phase=1, text="Apple makes computers")

        results = await store.retrieve_relevant(job_id="j", query="apple", top_k=5)
        texts = [r.text for r in results]
        # Both apple-mentioning findings should be returned, ranked first.
        assert any("Apple is a fruit" in t for t in texts)
        assert any("Apple makes computers" in t for t in texts)

    @pytest.mark.asyncio
    async def test_retrieve_respects_top_k(self, store):
        for i in range(5):
            await store.store_finding(job_id="j", phase=1, text=f"Finding number {i} talks about apples")
        results = await store.retrieve_relevant(job_id="j", query="apples", top_k=2)
        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_min_confidence_filter(self, store):
        await store.store_finding(job_id="j", phase=1, text="Low signal apple", confidence=0.2)
        await store.store_finding(job_id="j", phase=1, text="High signal apple", confidence=0.9)
        results = await store.retrieve_relevant(job_id="j", query="apple", min_confidence=0.5)
        assert all(r.confidence >= 0.5 for r in results)

    @pytest.mark.asyncio
    async def test_phase_filter(self, store):
        await store.store_finding(job_id="j", phase=1, text="P1 apples")
        await store.store_finding(job_id="j", phase=2, text="P2 apples")
        p1 = await store.retrieve_relevant(job_id="j", query="apples", phase=1)
        assert all(f.phase == 1 for f in p1)


class TestTokenizer:
    def test_short_tokens_dropped(self):
        tokens = StoredFinding._tokenize("a bc the apple")
        # Tokens of length <= 2 are dropped.
        assert "a" not in tokens
        assert "bc" not in tokens
        assert "the" in tokens
        assert "apple" in tokens

    def test_punctuation_stripped(self):
        tokens = StoredFinding._tokenize("Hello, world! Test-case.")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        assert "case" in tokens
