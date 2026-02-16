"""Tests for deepr.experts.gap_discovery.GapDiscoverer."""

import json
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from deepr.experts.gap_discovery import (
    GapDiscoverer,
    _cluster_by_threshold,
    _cosine_similarity,
)


# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self):
        a = np.array([1.0, 0.0, 0.0])
        assert _cosine_similarity(a, a) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector(self):
        a = np.array([0.0, 0.0])
        b = np.array([1.0, 1.0])
        assert _cosine_similarity(a, b) == 0.0


# ---------------------------------------------------------------------------
# _cluster_by_threshold
# ---------------------------------------------------------------------------


class TestClusterByThreshold:
    def test_empty_embeddings(self):
        assert _cluster_by_threshold(np.array([]).reshape(0, 3)) == []

    def test_single_embedding(self):
        emb = np.array([[1.0, 0.0, 0.0]])
        clusters = _cluster_by_threshold(emb)
        assert len(clusters) == 1
        assert clusters[0] == [0]

    def test_identical_embeddings_one_cluster(self):
        emb = np.array([
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
        ])
        clusters = _cluster_by_threshold(emb, threshold=0.9)
        assert len(clusters) == 1
        assert sorted(clusters[0]) == [0, 1, 2]

    def test_orthogonal_embeddings_separate_clusters(self):
        emb = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ])
        clusters = _cluster_by_threshold(emb, threshold=0.5)
        assert len(clusters) == 3

    def test_two_groups(self):
        emb = np.array([
            [1.0, 0.1, 0.0],  # Group 1
            [0.9, 0.2, 0.0],  # Group 1
            [0.0, 0.1, 1.0],  # Group 2
            [0.0, 0.2, 0.9],  # Group 2
        ])
        clusters = _cluster_by_threshold(emb, threshold=0.8)
        assert len(clusters) == 2

    def test_low_threshold_merges_all(self):
        emb = np.array([
            [1.0, 0.5, 0.3],
            [0.9, 0.4, 0.2],
            [0.8, 0.6, 0.4],
        ])
        clusters = _cluster_by_threshold(emb, threshold=0.1)
        # With very low threshold, most things merge
        assert len(clusters) <= 2


# ---------------------------------------------------------------------------
# GapDiscoverer.discover_gaps
# ---------------------------------------------------------------------------


class TestDiscoverGaps:
    @pytest.mark.asyncio
    async def test_too_few_claims(self):
        discoverer = GapDiscoverer()
        result = await discoverer.discover_gaps(
            claims=[{"statement": "Only one"}],
            domain="test",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_empty(self):
        discoverer = GapDiscoverer()
        discoverer._embed_statements = AsyncMock(return_value=None)

        claims = [{"statement": f"Claim {i}"} for i in range(5)]
        result = await discoverer.discover_gaps(claims, "test")
        assert result == []

    @pytest.mark.asyncio
    async def test_discovers_thin_areas(self):
        discoverer = GapDiscoverer(min_cluster_size=3)

        # Mock embeddings: 3 similar + 1 different = 2 clusters, one thin
        discoverer._embed_statements = AsyncMock(return_value=np.array([
            [1.0, 0.0, 0.0],
            [0.95, 0.05, 0.0],
            [0.9, 0.1, 0.0],
            [0.0, 0.0, 1.0],  # Thin cluster (only 1 item)
        ]))
        discoverer._generate_gaps_for_thin_areas = AsyncMock(return_value=[
            {"topic": "Thin area", "questions": ["What about this?"], "priority": 3},
        ])

        claims = [{"statement": f"Claim {i}"} for i in range(4)]
        result = await discoverer.discover_gaps(claims, "test")

        assert len(result) == 1
        assert result[0]["discovery_method"] == "auto_clustering"

    @pytest.mark.asyncio
    async def test_deduplicates_against_existing(self):
        discoverer = GapDiscoverer(min_cluster_size=3)

        discoverer._embed_statements = AsyncMock(return_value=np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]))
        discoverer._generate_gaps_for_thin_areas = AsyncMock(return_value=[
            {"topic": "Existing Topic", "questions": ["Q1"], "priority": 3},
            {"topic": "New Topic", "questions": ["Q2"], "priority": 4},
        ])

        claims = [{"statement": f"Claim {i}"} for i in range(3)]
        existing_gaps = [{"topic": "Existing Topic"}]

        result = await discoverer.discover_gaps(claims, "test", existing_gaps)
        assert len(result) == 1
        assert result[0]["topic"] == "New Topic"

    @pytest.mark.asyncio
    async def test_falls_back_to_domain_coverage(self):
        discoverer = GapDiscoverer(min_cluster_size=1)  # All clusters meet threshold

        discoverer._embed_statements = AsyncMock(return_value=np.array([
            [1.0, 0.0],
            [0.9, 0.1],
            [0.8, 0.2],
        ]))
        discoverer._check_domain_coverage = AsyncMock(return_value=[
            {"topic": "Missing subtopic", "questions": ["Q"], "priority": 2, "discovery_method": "domain_coverage"},
        ])

        claims = [{"statement": f"Claim {i}"} for i in range(3)]
        result = await discoverer.discover_gaps(claims, "test")

        discoverer._check_domain_coverage.assert_called_once()
        assert len(result) == 1


# ---------------------------------------------------------------------------
# GapDiscoverer._embed_statements
# ---------------------------------------------------------------------------


class TestEmbedStatements:
    @pytest.mark.asyncio
    async def test_successful_embedding(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1, 0.2, 0.3]),
            MagicMock(embedding=[0.4, 0.5, 0.6]),
        ]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        discoverer = GapDiscoverer(client=mock_client)
        result = await discoverer._embed_statements(["claim 1", "claim 2"])

        assert result is not None
        assert result.shape == (2, 3)

    @pytest.mark.asyncio
    async def test_embedding_failure(self):
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=Exception("API error"))

        discoverer = GapDiscoverer(client=mock_client)
        result = await discoverer._embed_statements(["test"])
        assert result is None


# ---------------------------------------------------------------------------
# GapDiscoverer._generate_gaps_for_thin_areas
# ---------------------------------------------------------------------------


class TestGenerateGapsForThinAreas:
    @pytest.mark.asyncio
    async def test_successful_generation(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps([
            {"topic": "Thin area", "questions": ["What is X?"], "priority": 4},
        ])
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        discoverer = GapDiscoverer(client=mock_client)
        result = await discoverer._generate_gaps_for_thin_areas(
            [["Single lonely claim"]], "test_domain"
        )
        assert len(result) == 1
        assert result[0]["topic"] == "Thin area"

    @pytest.mark.asyncio
    async def test_api_failure(self):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("Fail"))

        discoverer = GapDiscoverer(client=mock_client)
        result = await discoverer._generate_gaps_for_thin_areas([["claim"]], "domain")
        assert result == []
