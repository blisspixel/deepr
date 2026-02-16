"""Automated gap discovery via claim clustering.

Discovers thin knowledge areas by embedding and clustering claims,
then generates gap questions for under-represented areas.

Usage:
    discoverer = GapDiscoverer()
    new_gaps = await discoverer.discover_gaps(claims, domain, existing_gaps)
"""

import json
import logging
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def _cluster_by_threshold(
    embeddings: np.ndarray,
    threshold: float = 0.7,
) -> list[list[int]]:
    """Simple agglomerative clustering by cosine similarity threshold.

    Uses numpy only (no scipy dependency). Greedily assigns each item
    to the most similar existing cluster, or creates a new one.

    Args:
        embeddings: (N, D) array of embeddings
        threshold: Minimum cosine similarity to join a cluster

    Returns:
        List of clusters, each a list of indices
    """
    n = len(embeddings)
    if n == 0:
        return []

    clusters: list[list[int]] = [[0]]
    # Cluster centroids (running mean)
    centroids = [embeddings[0].copy()]

    for i in range(1, n):
        best_sim = -1.0
        best_cluster = -1

        for j, centroid in enumerate(centroids):
            sim = _cosine_similarity(embeddings[i], centroid)
            if sim > best_sim:
                best_sim = sim
                best_cluster = j

        if best_sim >= threshold and best_cluster >= 0:
            clusters[best_cluster].append(i)
            # Update centroid
            members = clusters[best_cluster]
            centroids[best_cluster] = np.mean(embeddings[members], axis=0)
        else:
            clusters.append([i])
            centroids.append(embeddings[i].copy())

    return clusters


class GapDiscoverer:
    """Discovers knowledge gaps by analyzing claim distribution.

    Attributes:
        client: OpenAI async client (lazily initialized)
        min_cluster_size: Minimum claims per cluster (below = thin area)
        similarity_threshold: Cosine similarity threshold for clustering
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        min_cluster_size: int = 3,
        similarity_threshold: float = 0.7,
    ):
        self.client = client
        self.min_cluster_size = min_cluster_size
        self.similarity_threshold = similarity_threshold

    async def _get_client(self):
        if self.client is None:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI()
        return self.client

    async def discover_gaps(
        self,
        claims: list[dict],
        domain: str,
        existing_gaps: Optional[list[dict]] = None,
    ) -> list[dict]:
        """Discover knowledge gaps via claim clustering.

        Args:
            claims: List of claim dicts (must have 'statement' key)
            domain: Expert's domain
            existing_gaps: Existing gaps to deduplicate against

        Returns:
            List of new gap dicts with topic, questions, priority, discovery_method
        """
        if len(claims) < 3:
            return []

        existing_gaps = existing_gaps or []

        # 1. Embed all claim statements
        statements = [c.get("statement", c.get("claim", "")) for c in claims]
        embeddings = await self._embed_statements(statements)
        if embeddings is None:
            return []

        # 2. Cluster claims
        clusters = _cluster_by_threshold(embeddings, threshold=self.similarity_threshold)

        # 3. Find thin clusters (under-represented areas)
        thin_areas = []
        for cluster_indices in clusters:
            if len(cluster_indices) < self.min_cluster_size:
                cluster_statements = [statements[i] for i in cluster_indices]
                thin_areas.append(cluster_statements)

        if not thin_areas:
            # All areas well-covered; check domain coverage instead
            return await self._check_domain_coverage(statements, domain, existing_gaps)

        # 4. Generate gap questions for thin areas
        new_gaps = await self._generate_gaps_for_thin_areas(thin_areas, domain)

        # 5. Deduplicate against existing gaps
        existing_topics = {g.get("topic", "").lower() for g in existing_gaps}
        new_gaps = [g for g in new_gaps if g.get("topic", "").lower() not in existing_topics]

        # Tag as auto-discovered
        for gap in new_gaps:
            gap["discovery_method"] = "auto_clustering"

        return new_gaps

    async def _embed_statements(self, statements: list[str]) -> Optional[np.ndarray]:
        """Embed claim statements using text-embedding-3-small.

        Args:
            statements: List of text strings to embed

        Returns:
            (N, D) numpy array of embeddings, or None on failure
        """
        try:
            client = await self._get_client()
            response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=statements,
            )
            embeddings = [item.embedding for item in response.data]
            return np.array(embeddings)
        except Exception as e:
            logger.warning("Embedding failed: %s", e)
            return None

    async def _generate_gaps_for_thin_areas(
        self,
        thin_areas: list[list[str]],
        domain: str,
    ) -> list[dict]:
        """Generate gap questions for under-represented areas.

        Args:
            thin_areas: Lists of statements in thin clusters
            domain: Expert's domain

        Returns:
            List of gap dicts
        """
        areas_text = ""
        for i, area in enumerate(thin_areas[:5]):
            areas_text += f"\nThin area {i + 1} ({len(area)} claims):\n"
            for stmt in area:
                areas_text += f"  - {stmt[:100]}\n"

        prompt = (
            f"Domain: {domain}\n\n"
            "These knowledge areas have very few claims and need deeper research:\n"
            f"{areas_text}\n\n"
            "For each thin area, generate a knowledge gap with questions that would deepen understanding.\n\n"
            "Output JSON array:\n"
            '[{"topic": "area name", "questions": ["question 1", "question 2"], "priority": 3}]\n\n'
            "Priority 1-5 (5=most important). Output ONLY the JSON."
        )

        try:
            client = await self._get_client()
            response = await client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {"role": "system", "content": "You identify knowledge gaps. Output only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                reasoning_effort="low",
            )
            text = response.choices[0].message.content or "[]"
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            return json.loads(text)
        except Exception as e:
            logger.warning("Gap generation failed: %s", e)
            return []

    async def _check_domain_coverage(
        self,
        statements: list[str],
        domain: str,
        existing_gaps: list[dict],
    ) -> list[dict]:
        """Check if expected domain subtopics are covered.

        Args:
            statements: All claim statements
            domain: Expert's domain
            existing_gaps: Existing gaps to avoid duplicating

        Returns:
            List of gap dicts for uncovered subtopics
        """
        claims_sample = "\n".join(f"- {s[:80]}" for s in statements[:20])
        existing_topics = ", ".join(g.get("topic", "") for g in existing_gaps[:10])

        prompt = (
            f"Domain: {domain}\n\n"
            f"Current claims cover:\n{claims_sample}\n\n"
            f"Existing gaps already identified: {existing_topics}\n\n"
            "What important subtopics of this domain are NOT covered by these claims?\n"
            "Generate gaps for missing subtopics.\n\n"
            "Output JSON array:\n"
            '[{"topic": "missing subtopic", "questions": ["question"], "priority": 3}]\n\n'
            "Output ONLY the JSON. Return [] if coverage is good."
        )

        try:
            client = await self._get_client()
            response = await client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {"role": "system", "content": "You analyze domain coverage. Output only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                reasoning_effort="low",
            )
            text = response.choices[0].message.content or "[]"
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            gaps = json.loads(text)
            for gap in gaps:
                gap["discovery_method"] = "domain_coverage"
            return gaps
        except Exception as e:
            logger.warning("Domain coverage check failed: %s", e)
            return []
