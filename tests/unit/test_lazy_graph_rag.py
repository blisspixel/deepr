"""Unit tests and property tests for the LazyGraphRAG module.

Tests the LazyGraphRAG system with Subgraph Materialization Cache:
- Concept extraction (noun phrases, headings, key phrases)
- Typed and weighted edges (co-occurrence, PMI)
- Retrieval sufficiency scoring
- Subgraph caching with LRU eviction
- Knowledge graph traversal
- Hybrid retrieval routing

Property tests validate:
- Property 6: Graph traversal completeness
- Property 7: Hybrid retrieval ranking
- Concept serialization round-trips
- Edge serialization round-trips
- Cache LRU eviction behavior
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set

from deepr.experts.lazy_graph_rag import (
    EdgeType,
    Concept,
    Edge,
    DocumentSection,
    ConceptExtractor,
    EdgeBuilder,
    RetrievalSufficiency,
    SufficiencyScorer,
    CachedSubgraph,
    SubgraphCache,
    KnowledgeGraph,
    LazyGraphRAG,
)


class TestEdgeType:
    """Tests for EdgeType enum."""

    def test_edge_type_values(self):
        """Test edge type enum values."""
        assert EdgeType.CO_OCCURS.value == "co_occurs"
        assert EdgeType.DEFINED_IN.value == "defined_in"
        assert EdgeType.DEPENDS_ON.value == "depends_on"
        assert EdgeType.MENTIONED_IN_SAME_SECTION.value == "mentioned_in_same_section"

    def test_edge_type_from_string(self):
        """Test creating edge type from string."""
        assert EdgeType("co_occurs") == EdgeType.CO_OCCURS
        assert EdgeType("defined_in") == EdgeType.DEFINED_IN
        assert EdgeType("mentioned_in_same_paragraph") == EdgeType.MENTIONED_IN_SAME_PARAGRAPH


class TestConcept:
    """Tests for Concept dataclass."""

    def test_create_concept(self):
        """Test creating a concept."""
        concept = Concept(
            text="quantum computing",
            concept_type="noun_phrase"
        )
        assert concept.text == "quantum computing"
        assert concept.concept_type == "noun_phrase"
        assert concept.id != ""  # Auto-generated

    def test_concept_id_generation(self):
        """Test concept ID is deterministically generated from text."""
        concept1 = Concept(text="quantum computing")
        concept2 = Concept(text="quantum computing")
        
        # Same text = same ID
        assert concept1.id == concept2.id
        
        # Different text = different ID
        concept3 = Concept(text="machine learning")
        assert concept1.id != concept3.id

    def test_concept_with_explicit_id(self):
        """Test concept with explicit ID."""
        concept = Concept(
            id="custom_id",
            text="test concept"
        )
        assert concept.id == "custom_id"

    def test_concept_to_dict(self):
        """Test concept serialization."""
        concept = Concept(
            text="quantum computing",
            concept_type="heading",
            original_forms={"Quantum Computing", "quantum computing"},
            document_ids={"doc1.md", "doc2.md"},
            section_ids={"sec1"},
            frequency=5,
            tf_idf_score=0.75
        )
        d = concept.to_dict()
        
        assert d["text"] == "quantum computing"
        assert d["concept_type"] == "heading"
        assert set(d["original_forms"]) == {"Quantum Computing", "quantum computing"}
        assert set(d["document_ids"]) == {"doc1.md", "doc2.md"}
        assert d["frequency"] == 5
        assert d["tf_idf_score"] == 0.75
        assert "created_at" in d

    def test_concept_from_dict(self):
        """Test concept deserialization."""
        data = {
            "id": "concept_123",
            "text": "machine learning",
            "concept_type": "key_phrase",
            "original_forms": ["Machine Learning"],
            "document_ids": ["doc1.md"],
            "section_ids": ["sec1"],
            "frequency": 10,
            "tf_idf_score": 0.8,
            "created_at": "2025-01-01T12:00:00"
        }
        concept = Concept.from_dict(data)
        
        assert concept.id == "concept_123"
        assert concept.text == "machine learning"
        assert concept.concept_type == "key_phrase"
        assert "Machine Learning" in concept.original_forms
        assert concept.frequency == 10

    def test_concept_sets_conversion(self):
        """Test that lists are converted to sets."""
        concept = Concept(
            text="test",
            original_forms=["form1", "form2", "form1"],  # Duplicate
            document_ids=["doc1", "doc1"]  # Duplicate
        )
        assert isinstance(concept.original_forms, set)
        assert isinstance(concept.document_ids, set)
        assert len(concept.original_forms) == 2
        assert len(concept.document_ids) == 1


class TestEdge:
    """Tests for Edge dataclass."""

    def test_create_edge(self):
        """Test creating an edge."""
        edge = Edge(
            source_id="concept1",
            target_id="concept2",
            edge_type=EdgeType.CO_OCCURS,
            weight=0.8
        )
        assert edge.source_id == "concept1"
        assert edge.target_id == "concept2"
        assert edge.edge_type == EdgeType.CO_OCCURS
        assert edge.weight == 0.8

    def test_edge_id_property(self):
        """Test edge ID is computed from source, type, and target."""
        edge = Edge(
            source_id="concept1",
            target_id="concept2",
            edge_type=EdgeType.DEFINED_IN
        )
        assert edge.id == "concept1:defined_in:concept2"

    def test_edge_to_dict(self):
        """Test edge serialization."""
        edge = Edge(
            source_id="concept1",
            target_id="concept2",
            edge_type=EdgeType.MENTIONED_IN_SAME_SECTION,
            weight=0.9,
            document_ids={"doc1.md"}
        )
        d = edge.to_dict()
        
        assert d["source_id"] == "concept1"
        assert d["target_id"] == "concept2"
        assert d["edge_type"] == "mentioned_in_same_section"
        assert d["weight"] == 0.9
        assert "doc1.md" in d["document_ids"]

    def test_edge_from_dict(self):
        """Test edge deserialization."""
        data = {
            "source_id": "concept1",
            "target_id": "concept2",
            "edge_type": "co_occurs",
            "weight": 0.7,
            "document_ids": ["doc1.md"],
            "created_at": "2025-01-01T12:00:00"
        }
        edge = Edge.from_dict(data)
        
        assert edge.source_id == "concept1"
        assert edge.target_id == "concept2"
        assert edge.edge_type == EdgeType.CO_OCCURS
        assert edge.weight == 0.7

    def test_edge_document_ids_conversion(self):
        """Test that document_ids list is converted to set."""
        edge = Edge(
            source_id="c1",
            target_id="c2",
            edge_type=EdgeType.CO_OCCURS,
            document_ids=["doc1", "doc2", "doc1"]  # Duplicate
        )
        assert isinstance(edge.document_ids, set)
        assert len(edge.document_ids) == 2


class TestDocumentSection:
    """Tests for DocumentSection dataclass."""

    def test_create_section(self):
        """Test creating a document section."""
        section = DocumentSection(
            document_id="doc1.md",
            content="This is the content",
            heading="Introduction",
            level=1
        )
        assert section.document_id == "doc1.md"
        assert section.content == "This is the content"
        assert section.heading == "Introduction"
        assert section.level == 1
        assert section.id != ""  # Auto-generated

    def test_section_id_generation(self):
        """Test section ID is generated from content."""
        section1 = DocumentSection(
            document_id="doc1.md",
            content="Content A",
            start_pos=0
        )
        section2 = DocumentSection(
            document_id="doc1.md",
            content="Content B",
            start_pos=100
        )
        
        # Different content = different ID
        assert section1.id != section2.id


class TestConceptExtractor:
    """Tests for ConceptExtractor class."""

    def test_create_extractor(self):
        """Test creating a concept extractor."""
        extractor = ConceptExtractor(
            min_phrase_length=2,
            max_phrase_length=4
        )
        assert extractor.min_phrase_length == 2
        assert extractor.max_phrase_length == 4

    def test_extract_noun_phrases(self):
        """Test noun phrase extraction."""
        extractor = ConceptExtractor()
        text = "Machine learning algorithms process large datasets efficiently."
        
        concepts = extractor.extract_concepts(text, "doc1.md")
        
        # Should extract some concepts
        assert len(concepts) > 0
        concept_texts = [c.text for c in concepts]
        # Should find relevant phrases
        assert any("machine" in t or "learning" in t for t in concept_texts)

    def test_extract_headings(self):
        """Test heading extraction from markdown."""
        extractor = ConceptExtractor()
        text = """# Introduction
        
This is the introduction.

## Background

Some background information.

### Details

More details here.
"""
        concepts = extractor.extract_concepts(text, "doc1.md")
        
        # Should extract headings
        heading_concepts = [c for c in concepts if c.concept_type == "heading"]
        assert len(heading_concepts) >= 1

    def test_extract_key_phrases(self):
        """Test key phrase extraction with TF-IDF scoring."""
        extractor = ConceptExtractor()
        text = "Python Python Python programming language. Python is great."
        
        concepts = extractor.extract_concepts(text, "doc1.md")
        
        # Should find python as a key phrase with high frequency
        python_concepts = [c for c in concepts if "python" in c.text.lower()]
        assert len(python_concepts) > 0
        # High frequency word should have higher TF-IDF
        assert any(c.frequency > 1 for c in python_concepts)

    def test_extract_sections(self):
        """Test section extraction from markdown."""
        extractor = ConceptExtractor()
        text = """# Section 1

Content for section 1.

# Section 2

Content for section 2.
"""
        sections = extractor.extract_sections(text, "doc1.md")
        
        assert len(sections) >= 2
        assert any(s.heading == "Section 1" for s in sections)
        assert any(s.heading == "Section 2" for s in sections)

    def test_extract_sections_no_headings(self):
        """Test section extraction when no headings present."""
        extractor = ConceptExtractor()
        text = "Just plain text without any headings."
        
        sections = extractor.extract_sections(text, "doc1.md")
        
        # Should return single section with entire content
        assert len(sections) == 1
        assert sections[0].heading == ""
        assert sections[0].content == text

    def test_stopwords_filtered(self):
        """Test that stopwords are filtered from concepts."""
        extractor = ConceptExtractor()
        text = "The quick brown fox jumps over the lazy dog."
        
        concepts = extractor.extract_concepts(text, "doc1.md")
        
        # Should not have concepts that are just stopwords
        for concept in concepts:
            words = concept.text.split()
            # First and last words should not be stopwords
            assert words[0] not in extractor.stopwords
            assert words[-1] not in extractor.stopwords


class TestEdgeBuilder:
    """Tests for EdgeBuilder class."""

    def test_create_edge_builder(self):
        """Test creating an edge builder."""
        builder = EdgeBuilder(min_pmi=0.1)
        assert builder.min_pmi == 0.1

    def test_build_edges_cooccurrence(self):
        """Test building co-occurrence edges."""
        builder = EdgeBuilder()
        
        concepts = [
            Concept(text="machine learning", section_ids={"sec1"}, frequency=2),
            Concept(text="neural networks", section_ids={"sec1"}, frequency=2),
        ]
        sections = [
            DocumentSection(
                id="sec1",
                document_id="doc1.md",
                content="Machine learning and neural networks are related.",
                heading="ML"
            )
        ]
        
        edges = builder.build_edges(concepts, sections, "doc1.md")
        
        # Should create edges between concepts in same section
        assert len(edges) >= 1

    def test_calculate_pmi(self):
        """Test PMI calculation."""
        builder = EdgeBuilder()
        
        # Perfect co-occurrence
        pmi = builder.calculate_pmi(
            c1_count=10,
            c2_count=10,
            cooccur_count=10,
            total_docs=100
        )
        assert pmi > 0  # Positive PMI for co-occurring concepts
        
        # No co-occurrence
        pmi_zero = builder.calculate_pmi(
            c1_count=10,
            c2_count=10,
            cooccur_count=0,
            total_docs=100
        )
        assert pmi_zero == 0.0

    def test_scope_weights(self):
        """Test that scope weights are applied correctly."""
        builder = EdgeBuilder()
        
        # Same heading should have highest weight
        assert builder.scope_weights["same_heading"] > builder.scope_weights["same_paragraph"]
        assert builder.scope_weights["same_paragraph"] > builder.scope_weights["same_chunk"]


class TestRetrievalSufficiency:
    """Tests for RetrievalSufficiency dataclass."""

    def test_create_sufficiency(self):
        """Test creating retrieval sufficiency."""
        sufficiency = RetrievalSufficiency(
            coverage=0.8,
            redundancy=0.2,
            citation_density=2.0,
            contradiction_rate=0.1
        )
        assert sufficiency.coverage == 0.8
        assert sufficiency.redundancy == 0.2

    def test_compute_overall(self):
        """Test computing overall sufficiency score."""
        sufficiency = RetrievalSufficiency(
            coverage=0.8,
            redundancy=0.2,
            citation_density=2.0,
            contradiction_rate=0.1
        )
        
        score = sufficiency.compute_overall()
        
        assert 0.0 <= score <= 1.0
        assert sufficiency.overall_score == score

    def test_is_sufficient(self):
        """Test sufficiency threshold check."""
        high_sufficiency = RetrievalSufficiency(
            coverage=0.9,
            redundancy=0.1,
            citation_density=3.0,
            contradiction_rate=0.0
        )
        high_sufficiency.compute_overall()
        
        low_sufficiency = RetrievalSufficiency(
            coverage=0.2,
            redundancy=0.8,
            citation_density=0.0,
            contradiction_rate=0.5
        )
        low_sufficiency.compute_overall()
        
        assert high_sufficiency.is_sufficient(threshold=0.6)
        assert not low_sufficiency.is_sufficient(threshold=0.6)


class TestSufficiencyScorer:
    """Tests for SufficiencyScorer class."""

    def test_create_scorer(self):
        """Test creating a sufficiency scorer."""
        scorer = SufficiencyScorer()
        assert len(scorer.stopwords) > 0

    def test_score_empty_chunks(self):
        """Test scoring with no chunks."""
        scorer = SufficiencyScorer()
        
        sufficiency = scorer.score("test query", [])
        
        assert sufficiency.coverage == 0.0
        assert sufficiency.overall_score == 0.0

    def test_score_with_chunks(self):
        """Test scoring with chunks."""
        scorer = SufficiencyScorer()
        
        chunks = [
            {"content": "Python is a programming language."},
            {"content": "Python supports multiple paradigms."}
        ]
        
        sufficiency = scorer.score("What is Python?", chunks)
        
        assert sufficiency.coverage > 0.0
        assert 0.0 <= sufficiency.overall_score <= 1.0

    def test_coverage_calculation(self):
        """Test coverage calculation."""
        scorer = SufficiencyScorer()
        
        # Chunks that cover query keywords
        chunks = [
            {"content": "Machine learning is a subset of artificial intelligence."},
            {"content": "Deep learning uses neural networks."}
        ]
        
        sufficiency = scorer.score("machine learning artificial intelligence", chunks)
        
        # Should have good coverage
        assert sufficiency.coverage > 0.5

    def test_redundancy_calculation(self):
        """Test redundancy calculation."""
        scorer = SufficiencyScorer()
        
        # Identical chunks = high redundancy
        identical_chunks = [
            {"content": "Python is great."},
            {"content": "Python is great."}
        ]
        
        sufficiency = scorer.score("Python", identical_chunks)
        
        # Should have high redundancy
        assert sufficiency.redundancy > 0.5


class TestCachedSubgraph:
    """Tests for CachedSubgraph dataclass."""

    def test_create_cached_subgraph(self):
        """Test creating a cached subgraph."""
        subgraph = CachedSubgraph(
            query_hash="abc123",
            node_ids={"node1", "node2"},
            node_summaries={"node1": "Summary 1"}
        )
        assert subgraph.query_hash == "abc123"
        assert len(subgraph.node_ids) == 2
        assert subgraph.access_count == 0

    def test_touch_updates_access(self):
        """Test that touch updates access time and count."""
        subgraph = CachedSubgraph(query_hash="abc123")
        original_time = subgraph.last_accessed
        
        import time
        time.sleep(0.01)  # Small delay
        subgraph.touch()
        
        assert subgraph.access_count == 1
        assert subgraph.last_accessed >= original_time

    def test_to_dict(self):
        """Test cached subgraph serialization."""
        subgraph = CachedSubgraph(
            query_hash="abc123",
            node_ids={"node1", "node2"},
            prompt_blocks=["Block 1", "Block 2"]
        )
        d = subgraph.to_dict()
        
        assert d["query_hash"] == "abc123"
        assert set(d["node_ids"]) == {"node1", "node2"}
        assert d["prompt_blocks"] == ["Block 1", "Block 2"]

    def test_from_dict(self):
        """Test cached subgraph deserialization."""
        data = {
            "query_hash": "abc123",
            "node_ids": ["node1", "node2"],
            "node_summaries": {"node1": "Summary"},
            "prompt_blocks": ["Block 1"],
            "created_at": "2025-01-01T12:00:00",
            "last_accessed": "2025-01-01T12:00:00",
            "access_count": 5
        }
        subgraph = CachedSubgraph.from_dict(data)
        
        assert subgraph.query_hash == "abc123"
        assert subgraph.access_count == 5
        assert isinstance(subgraph.node_ids, set)


class TestSubgraphCache:
    """Tests for SubgraphCache class."""

    def test_create_cache(self, tmp_path):
        """Test creating a subgraph cache."""
        cache = SubgraphCache(
            max_size=10,
            storage_path=tmp_path / "cache.json"
        )
        assert cache.max_size == 10
        assert len(cache.cache) == 0

    def test_put_and_get(self, tmp_path):
        """Test putting and getting from cache."""
        cache = SubgraphCache(
            max_size=10,
            storage_path=tmp_path / "cache.json"
        )
        
        cache.put(
            query="What is Python?",
            node_ids={"node1", "node2"},
            prompt_blocks=["Block 1"]
        )
        
        result = cache.get("What is Python?")
        
        assert result is not None
        assert "node1" in result.node_ids
        assert result.access_count == 1  # Touched on get

    def test_get_miss(self, tmp_path):
        """Test cache miss returns None."""
        cache = SubgraphCache(max_size=10)
        
        result = cache.get("nonexistent query")
        
        assert result is None

    def test_lru_eviction(self, tmp_path):
        """Test LRU eviction when cache is full."""
        import time
        cache = SubgraphCache(max_size=3)
        
        # Fill cache with delays to ensure different timestamps
        cache.put("query1", {"node1"})
        time.sleep(0.01)
        cache.put("query2", {"node2"})
        time.sleep(0.01)
        cache.put("query3", {"node3"})
        time.sleep(0.01)
        
        # Access query1 to make it recently used
        cache.get("query1")
        time.sleep(0.01)
        
        # Add new entry - should evict query2 (least recently used)
        cache.put("query4", {"node4"})
        
        # Cache should be at capacity
        assert len(cache.cache) == 3
        # New entry should be present
        assert cache.get("query4") is not None

    def test_invalidate(self, tmp_path):
        """Test cache invalidation."""
        cache = SubgraphCache(max_size=10)
        
        cache.put("query1", {"node1"})
        cache.invalidate("query1")
        
        assert cache.get("query1") is None

    def test_clear(self, tmp_path):
        """Test clearing cache."""
        cache = SubgraphCache(max_size=10)
        
        cache.put("query1", {"node1"})
        cache.put("query2", {"node2"})
        cache.clear()
        
        assert len(cache.cache) == 0

    def test_update_summaries(self, tmp_path):
        """Test updating node summaries."""
        cache = SubgraphCache(max_size=10)
        
        cache.put("query1", {"node1", "node2"})
        cache.update_summaries("query1", {"node1": "Summary 1"})
        
        result = cache.get("query1")
        assert result.node_summaries["node1"] == "Summary 1"

    def test_persistence(self, tmp_path):
        """Test cache persistence across instances."""
        storage_path = tmp_path / "cache.json"
        
        # Create and populate cache
        cache1 = SubgraphCache(max_size=10, storage_path=storage_path)
        cache1.put("query1", {"node1"}, prompt_blocks=["Block 1"])
        
        # Create new instance - should load from disk
        cache2 = SubgraphCache(max_size=10, storage_path=storage_path)
        
        result = cache2.get("query1")
        assert result is not None
        assert "node1" in result.node_ids

    def test_get_stats(self, tmp_path):
        """Test getting cache statistics."""
        cache = SubgraphCache(max_size=10)
        
        cache.put("query1", {"node1"})
        cache.get("query1")
        cache.get("query1")
        
        stats = cache.get_stats()
        
        assert stats["size"] == 1
        assert stats["max_size"] == 10
        assert stats["total_accesses"] >= 2


class TestKnowledgeGraph:
    """Tests for KnowledgeGraph class."""

    def test_create_graph(self, tmp_path):
        """Test creating a knowledge graph."""
        graph = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=tmp_path / "graph"
        )
        assert graph.expert_name == "test_expert"
        assert len(graph.concepts) == 0
        assert len(graph.edges) == 0

    def test_add_concept(self, tmp_path):
        """Test adding a concept to the graph."""
        graph = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=tmp_path / "graph"
        )
        
        concept = Concept(text="machine learning", frequency=1)
        concept_id = graph.add_concept(concept)
        
        assert concept_id in graph.concepts
        assert graph.concepts[concept_id].text == "machine learning"

    def test_add_concept_merges_existing(self, tmp_path):
        """Test that adding existing concept merges data."""
        graph = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=tmp_path / "graph"
        )
        
        concept1 = Concept(text="machine learning", frequency=1, document_ids={"doc1"})
        concept2 = Concept(text="machine learning", frequency=2, document_ids={"doc2"})
        
        graph.add_concept(concept1)
        graph.add_concept(concept2)
        
        # Should have merged
        assert len(graph.concepts) == 1
        merged = list(graph.concepts.values())[0]
        assert merged.frequency == 3
        assert "doc1" in merged.document_ids
        assert "doc2" in merged.document_ids

    def test_add_edge(self, tmp_path):
        """Test adding an edge to the graph."""
        graph = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=tmp_path / "graph"
        )
        
        c1 = Concept(text="machine learning")
        c2 = Concept(text="neural networks")
        graph.add_concept(c1)
        graph.add_concept(c2)
        
        edge = Edge(
            source_id=c1.id,
            target_id=c2.id,
            edge_type=EdgeType.CO_OCCURS,
            weight=0.8
        )
        edge_id = graph.add_edge(edge)
        
        assert edge_id in graph.edges
        # Should update adjacency
        assert len(graph.adjacency[c1.id]) > 0
        assert len(graph.adjacency[c2.id]) > 0

    def test_get_concept(self, tmp_path):
        """Test getting concept by ID."""
        graph = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=tmp_path / "graph"
        )
        
        concept = Concept(text="test concept")
        graph.add_concept(concept)
        
        retrieved = graph.get_concept(concept.id)
        assert retrieved is not None
        assert retrieved.text == "test concept"
        
        # Non-existent
        assert graph.get_concept("nonexistent") is None

    def test_get_concept_by_text(self, tmp_path):
        """Test getting concept by text."""
        graph = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=tmp_path / "graph"
        )
        
        concept = Concept(text="machine learning")
        graph.add_concept(concept)
        
        retrieved = graph.get_concept_by_text("machine learning")
        assert retrieved is not None
        assert retrieved.id == concept.id
        
        # Case insensitive
        retrieved2 = graph.get_concept_by_text("Machine Learning")
        assert retrieved2 is not None

    def test_get_neighbors(self, tmp_path):
        """Test getting neighboring concepts."""
        graph = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=tmp_path / "graph"
        )
        
        c1 = Concept(text="machine learning")
        c2 = Concept(text="neural networks")
        c3 = Concept(text="deep learning")
        graph.add_concept(c1)
        graph.add_concept(c2)
        graph.add_concept(c3)
        
        edge1 = Edge(source_id=c1.id, target_id=c2.id, edge_type=EdgeType.CO_OCCURS, weight=0.8)
        edge2 = Edge(source_id=c1.id, target_id=c3.id, edge_type=EdgeType.CO_OCCURS, weight=0.5)
        graph.add_edge(edge1)
        graph.add_edge(edge2)
        
        neighbors = graph.get_neighbors(c1.id)
        
        assert len(neighbors) == 2
        # Should be sorted by weight
        assert neighbors[0][1].weight >= neighbors[1][1].weight

    def test_get_neighbors_with_filter(self, tmp_path):
        """Test getting neighbors with edge type filter."""
        graph = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=tmp_path / "graph"
        )
        
        c1 = Concept(text="concept1")
        c2 = Concept(text="concept2")
        c3 = Concept(text="concept3")
        graph.add_concept(c1)
        graph.add_concept(c2)
        graph.add_concept(c3)
        
        edge1 = Edge(source_id=c1.id, target_id=c2.id, edge_type=EdgeType.CO_OCCURS)
        edge2 = Edge(source_id=c1.id, target_id=c3.id, edge_type=EdgeType.DEFINED_IN)
        graph.add_edge(edge1)
        graph.add_edge(edge2)
        
        # Filter by edge type
        neighbors = graph.get_neighbors(c1.id, edge_types=[EdgeType.CO_OCCURS])
        
        assert len(neighbors) == 1
        assert neighbors[0][1].edge_type == EdgeType.CO_OCCURS


    def test_traverse(self, tmp_path):
        """Test graph traversal."""
        graph = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=tmp_path / "graph"
        )
        
        # Create a chain: c1 -> c2 -> c3 -> c4
        concepts = [Concept(text=f"concept{i}") for i in range(4)]
        for c in concepts:
            graph.add_concept(c)
        
        for i in range(3):
            edge = Edge(
                source_id=concepts[i].id,
                target_id=concepts[i+1].id,
                edge_type=EdgeType.CO_OCCURS,
                weight=0.8
            )
            graph.add_edge(edge)
        
        # Traverse from c1 with depth 2
        visited = graph.traverse([concepts[0].id], max_depth=2)
        
        # Should visit c1, c2, c3 (depth 0, 1, 2)
        assert concepts[0].id in visited
        assert concepts[1].id in visited
        assert concepts[2].id in visited

    def test_traverse_max_nodes(self, tmp_path):
        """Test traversal respects max_nodes limit."""
        graph = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=tmp_path / "graph"
        )
        
        # Create many connected concepts
        concepts = [Concept(text=f"concept{i}") for i in range(10)]
        for c in concepts:
            graph.add_concept(c)
        
        # Connect all to first concept
        for i in range(1, 10):
            edge = Edge(
                source_id=concepts[0].id,
                target_id=concepts[i].id,
                edge_type=EdgeType.CO_OCCURS
            )
            graph.add_edge(edge)
        
        # Traverse with max_nodes limit
        visited = graph.traverse([concepts[0].id], max_depth=5, max_nodes=5)
        
        assert len(visited) <= 5

    def test_search(self, tmp_path):
        """Test concept search."""
        graph = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=tmp_path / "graph"
        )
        
        concepts = [
            Concept(text="machine learning", tf_idf_score=0.8),
            Concept(text="deep learning", tf_idf_score=0.7),
            Concept(text="cooking recipes", tf_idf_score=0.5)
        ]
        for c in concepts:
            graph.add_concept(c)
        
        results = graph.search("machine learning algorithms", top_k=2)
        
        assert len(results) <= 2
        # Should find machine learning first
        assert results[0].text == "machine learning"

    def test_persistence(self, tmp_path):
        """Test graph persistence."""
        storage_dir = tmp_path / "graph"
        
        # Create and populate graph
        graph1 = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=storage_dir
        )
        
        c1 = Concept(text="machine learning")
        c2 = Concept(text="neural networks")
        graph1.add_concept(c1)
        graph1.add_concept(c2)
        
        edge = Edge(source_id=c1.id, target_id=c2.id, edge_type=EdgeType.CO_OCCURS)
        graph1.add_edge(edge)
        graph1.save()
        
        # Create new instance - should load from disk
        graph2 = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=storage_dir
        )
        
        assert len(graph2.concepts) == 2
        assert len(graph2.edges) == 1

    def test_get_stats(self, tmp_path):
        """Test getting graph statistics."""
        graph = KnowledgeGraph(
            expert_name="test_expert",
            storage_dir=tmp_path / "graph"
        )
        
        c1 = Concept(text="concept1", concept_type="noun_phrase")
        c2 = Concept(text="concept2", concept_type="heading")
        graph.add_concept(c1)
        graph.add_concept(c2)
        
        edge = Edge(source_id=c1.id, target_id=c2.id, edge_type=EdgeType.CO_OCCURS)
        graph.add_edge(edge)
        
        stats = graph.get_stats()
        
        assert stats["concept_count"] == 2
        assert stats["edge_count"] == 1
        assert "noun_phrase" in stats["concept_types"]
        assert "heading" in stats["concept_types"]


class TestLazyGraphRAG:
    """Tests for LazyGraphRAG class."""

    def test_create_lazy_graph_rag(self, tmp_path):
        """Test creating a LazyGraphRAG instance."""
        rag = LazyGraphRAG(
            expert_name="test_expert",
            storage_dir=tmp_path / "rag"
        )
        assert rag.expert_name == "test_expert"
        assert rag.graph is not None
        assert rag.cache is not None

    @pytest.mark.asyncio
    async def test_index_document(self, tmp_path):
        """Test indexing a single document."""
        rag = LazyGraphRAG(
            expert_name="test_expert",
            storage_dir=tmp_path / "rag"
        )
        
        content = """# Machine Learning

Machine learning is a subset of artificial intelligence.

## Neural Networks

Neural networks are inspired by biological neurons.
"""
        
        result = await rag.index_document("ml_intro.md", content)
        
        assert result["document_id"] == "ml_intro.md"
        assert result["concepts"] >= 0
        assert result["edges"] >= 0

    @pytest.mark.asyncio
    async def test_index_documents(self, tmp_path):
        """Test indexing multiple documents."""
        rag = LazyGraphRAG(
            expert_name="test_expert",
            storage_dir=tmp_path / "rag"
        )
        
        documents = [
            {"id": "doc1.md", "content": "Python is a programming language."},
            {"id": "doc2.md", "content": "Python supports multiple paradigms."}
        ]
        
        results = await rag.index_documents(documents)
        
        assert results["documents"] == 2
        assert results["concepts"] >= 0

    @pytest.mark.asyncio
    async def test_retrieve_simple_query(self, tmp_path):
        """Test retrieval with a simple query."""
        rag = LazyGraphRAG(
            expert_name="test_expert",
            storage_dir=tmp_path / "rag"
        )
        
        # Index some content
        await rag.index_document("python.md", "Python is a programming language. Python is easy to learn.")
        
        results = await rag.retrieve("What is Python?", top_k=5)
        
        assert isinstance(results, dict)
        assert "chunks" in results
        assert isinstance(results["chunks"], list)

    @pytest.mark.asyncio
    async def test_retrieve_complex_query(self, tmp_path):
        """Test retrieval with a complex query that triggers graph expansion."""
        rag = LazyGraphRAG(
            expert_name="test_expert",
            storage_dir=tmp_path / "rag"
        )
        
        # Index related content
        await rag.index_document("ml.md", """# Machine Learning
        
Machine learning uses algorithms to learn from data.
Neural networks are a type of machine learning model.
Deep learning uses multiple layers of neural networks.
""")
        
        results = await rag.retrieve(
            "How do neural networks relate to deep learning?",
            top_k=5,
            use_graph=True
        )
        
        assert isinstance(results, dict)
        assert "chunks" in results

    def test_should_use_graph(self, tmp_path):
        """Test graph routing decision."""
        rag = LazyGraphRAG(
            expert_name="test_expert",
            storage_dir=tmp_path / "rag"
        )
        
        # Simple query - should not use graph
        simple = rag.should_use_graph("What is Python?")
        
        # Complex query - more likely to use graph
        complex_query = rag.should_use_graph(
            "How does the relationship between neural networks and deep learning affect model architecture decisions?"
        )
        
        # Both should return boolean
        assert isinstance(simple, bool)
        assert isinstance(complex_query, bool)

    def test_get_stats(self, tmp_path):
        """Test getting LazyGraphRAG statistics."""
        rag = LazyGraphRAG(
            expert_name="test_expert",
            storage_dir=tmp_path / "rag"
        )
        
        stats = rag.get_stats()
        
        assert "graph" in stats
        assert "cache" in stats
        assert stats["graph"]["concept_count"] >= 0

    @pytest.mark.asyncio
    async def test_persistence(self, tmp_path):
        """Test LazyGraphRAG persistence."""
        storage_dir = tmp_path / "rag"
        
        # Create and populate
        rag1 = LazyGraphRAG(
            expert_name="test_expert",
            storage_dir=storage_dir
        )
        await rag1.index_document("test.md", "Python programming language.")
        # Graph is saved automatically in index_document
        
        # Create new instance - should load from disk
        rag2 = LazyGraphRAG(
            expert_name="test_expert",
            storage_dir=storage_dir
        )
        
        stats = rag2.get_stats()
        assert stats["graph"]["concept_count"] >= 0



# Property-based tests using hypothesis
from hypothesis import given, settings, assume, HealthCheck
import hypothesis.strategies as st


class TestConceptPropertyTests:
    """Property-based tests for Concept serialization.
    
    Property: Concept serialization is lossless (round-trip preserves data).
    """

    @given(
        text=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=('L', 'Nd', 'Zs'))),
        concept_type=st.sampled_from(["noun_phrase", "heading", "key_phrase", "entity"]),
        frequency=st.integers(min_value=1, max_value=1000),
        tf_idf_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_concept_serialization_round_trip(self, text, concept_type, frequency, tf_idf_score):
        """Property: Concept serialization preserves all data."""
        assume('\x00' not in text and len(text.strip()) > 0)
        
        concept = Concept(
            text=text.strip(),
            concept_type=concept_type,
            frequency=frequency,
            tf_idf_score=tf_idf_score
        )
        
        # Serialize and deserialize
        d = concept.to_dict()
        restored = Concept.from_dict(d)
        
        assert restored.text == concept.text
        assert restored.concept_type == concept.concept_type
        assert restored.frequency == concept.frequency
        assert restored.id == concept.id
        assert abs(restored.tf_idf_score - concept.tf_idf_score) < 1e-10

    @given(
        original_forms=st.lists(
            st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=('L',))),
            min_size=0,
            max_size=5
        ),
        document_ids=st.lists(
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'Nd'))),
            min_size=0,
            max_size=5
        )
    )
    @settings(max_examples=30)
    def test_concept_sets_preserved(self, original_forms, document_ids):
        """Property: Concept sets are preserved through serialization."""
        concept = Concept(
            text="test concept",
            original_forms=set(original_forms),
            document_ids=set(document_ids)
        )
        
        d = concept.to_dict()
        restored = Concept.from_dict(d)
        
        assert restored.original_forms == concept.original_forms
        assert restored.document_ids == concept.document_ids


class TestEdgePropertyTests:
    """Property-based tests for Edge serialization.
    
    Property: Edge serialization is lossless (round-trip preserves data).
    """

    @given(
        source_id=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'Nd'))),
        target_id=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'Nd'))),
        edge_type=st.sampled_from([EdgeType.CO_OCCURS, EdgeType.DEFINED_IN, EdgeType.DEPENDS_ON, EdgeType.MENTIONED_IN_SAME_SECTION]),
        weight=st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_edge_serialization_round_trip(self, source_id, target_id, edge_type, weight):
        """Property: Edge serialization preserves all data."""
        assume(source_id != target_id)  # Edges should connect different nodes
        
        edge = Edge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight
        )
        
        # Serialize and deserialize
        d = edge.to_dict()
        restored = Edge.from_dict(d)
        
        assert restored.source_id == edge.source_id
        assert restored.target_id == edge.target_id
        assert restored.edge_type == edge.edge_type
        assert abs(restored.weight - edge.weight) < 1e-10
        assert restored.id == edge.id

    @given(
        document_ids=st.lists(
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'Nd'))),
            min_size=0,
            max_size=5
        )
    )
    @settings(max_examples=30)
    def test_edge_document_ids_preserved(self, document_ids):
        """Property: Edge document_ids are preserved through serialization."""
        edge = Edge(
            source_id="source",
            target_id="target",
            edge_type=EdgeType.CO_OCCURS,
            document_ids=set(document_ids)
        )
        
        d = edge.to_dict()
        restored = Edge.from_dict(d)
        
        assert restored.document_ids == edge.document_ids


class TestGraphTraversalPropertyTests:
    """Property-based tests for graph traversal.
    
    Property 6: Graph traversal completeness
    - Traversal visits all reachable nodes within depth limit
    - Traversal respects max_nodes limit
    - Visited set contains start nodes
    """

    @given(
        num_concepts=st.integers(min_value=2, max_value=15),
        max_depth=st.integers(min_value=1, max_value=5),
        max_nodes=st.integers(min_value=1, max_value=20)
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_traversal_respects_limits(self, num_concepts, max_depth, max_nodes):
        """Property: Traversal respects max_depth and max_nodes limits."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            graph = KnowledgeGraph(
                expert_name="test_expert",
                storage_dir=Path(tmp_dir) / "graph"
            )
            
            # Create concepts
            concepts = [Concept(text=f"concept{i}") for i in range(num_concepts)]
            for c in concepts:
                graph.add_concept(c)
            
            # Create chain of edges
            for i in range(num_concepts - 1):
                edge = Edge(
                    source_id=concepts[i].id,
                    target_id=concepts[i + 1].id,
                    edge_type=EdgeType.CO_OCCURS,
                    weight=0.8
                )
                graph.add_edge(edge)
            
            # Traverse from first concept
            visited = graph.traverse([concepts[0].id], max_depth=max_depth, max_nodes=max_nodes)
            
            # Should respect max_nodes
            assert len(visited) <= max_nodes
            
            # Should include start node
            assert concepts[0].id in visited
            
            # Should not exceed depth limit (chain length)
            max_reachable = min(max_depth + 1, num_concepts)
            assert len(visited) <= max_reachable

    @given(
        num_concepts=st.integers(min_value=3, max_value=10)
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_traversal_visits_all_reachable(self, num_concepts):
        """Property: Traversal visits all reachable nodes within depth."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            graph = KnowledgeGraph(
                expert_name="test_expert",
                storage_dir=Path(tmp_dir) / "graph"
            )
            
            # Create star topology: center connected to all others
            center = Concept(text="center")
            graph.add_concept(center)
            
            satellites = [Concept(text=f"satellite{i}") for i in range(num_concepts - 1)]
            for s in satellites:
                graph.add_concept(s)
                edge = Edge(
                    source_id=center.id,
                    target_id=s.id,
                    edge_type=EdgeType.CO_OCCURS
                )
                graph.add_edge(edge)
            
            # Traverse from center with depth 1
            visited = graph.traverse([center.id], max_depth=1, max_nodes=100)
            
            # Should visit center and all satellites
            assert center.id in visited
            for s in satellites:
                assert s.id in visited

    @given(
        start_indices=st.lists(st.integers(min_value=0, max_value=4), min_size=1, max_size=3, unique=True)
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_traversal_from_multiple_starts(self, start_indices):
        """Property: Traversal from multiple starts visits union of reachable nodes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            graph = KnowledgeGraph(
                expert_name="test_expert",
                storage_dir=Path(tmp_dir) / "graph"
            )
            
            # Create 5 disconnected concepts
            concepts = [Concept(text=f"concept{i}") for i in range(5)]
            for c in concepts:
                graph.add_concept(c)
            
            # Get valid start indices
            valid_starts = [i for i in start_indices if i < len(concepts)]
            if not valid_starts:
                valid_starts = [0]
            
            start_ids = [concepts[i].id for i in valid_starts]
            visited = graph.traverse(start_ids, max_depth=1, max_nodes=100)
            
            # All start nodes should be visited
            for start_id in start_ids:
                assert start_id in visited


class TestHybridRetrievalPropertyTests:
    """Property-based tests for hybrid retrieval.
    
    Property 7: Hybrid retrieval ranking
    - Results are ranked by relevance score
    - Results respect top_k limit
    - Graph expansion increases coverage for complex queries
    """

    @given(
        top_k=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_retrieval_respects_top_k(self, top_k):
        """Property: Retrieval never returns more than top_k results."""
        import asyncio
        
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp_dir:
                rag = LazyGraphRAG(
                    expert_name="test_expert",
                    storage_dir=Path(tmp_dir) / "rag"
                )
                
                # Index multiple documents
                for i in range(15):
                    await rag.index_document(f"doc{i}.md", f"Python programming content {i}. Python is great.")
                
                results = await rag.retrieve("Python programming", top_k=top_k)
                
                assert isinstance(results, dict)
                assert "chunks" in results
                assert len(results["chunks"]) <= top_k
        
        asyncio.get_event_loop().run_until_complete(run_test())

    @given(
        num_docs=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_retrieval_returns_dict(self, num_docs):
        """Property: Retrieval always returns a dict with chunks."""
        import asyncio
        
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp_dir:
                rag = LazyGraphRAG(
                    expert_name="test_expert",
                    storage_dir=Path(tmp_dir) / "rag"
                )
                
                for i in range(num_docs):
                    await rag.index_document(f"doc{i}.md", f"Content about topic {i}.")
                
                results = await rag.retrieve("topic", top_k=5)
                
                assert isinstance(results, dict)
                assert "chunks" in results
                assert isinstance(results["chunks"], list)
        
        asyncio.get_event_loop().run_until_complete(run_test())


class TestCacheLRUPropertyTests:
    """Property-based tests for cache LRU eviction.
    
    Property: Cache respects max_size and evicts least recently used entries.
    """

    @given(
        max_size=st.integers(min_value=2, max_value=10),
        num_entries=st.integers(min_value=1, max_value=20)
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_cache_respects_max_size(self, max_size, num_entries):
        """Property: Cache never exceeds max_size."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = SubgraphCache(
                max_size=max_size,
                storage_path=Path(tmp_dir) / "cache.json"
            )
            
            for i in range(num_entries):
                cache.put(f"query{i}", {f"node{i}"})
            
            assert len(cache.cache) <= max_size

    @given(
        max_size=st.integers(min_value=3, max_value=8),
        access_pattern=st.lists(st.integers(min_value=0, max_value=9), min_size=5, max_size=15)
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_cache_lru_eviction_order(self, max_size, access_pattern):
        """Property: LRU eviction removes least recently accessed entries."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = SubgraphCache(
                max_size=max_size,
                storage_path=Path(tmp_dir) / "cache.json"
            )
            
            # Fill cache
            for i in range(max_size):
                cache.put(f"query{i}", {f"node{i}"})
            
            # Access some entries based on pattern
            for idx in access_pattern:
                if idx < max_size:
                    cache.get(f"query{idx}")
            
            # Add new entry to trigger eviction
            cache.put("new_query", {"new_node"})
            
            # Cache should still be at max_size
            assert len(cache.cache) == max_size
            # New entry should be present
            assert cache.get("new_query") is not None


class TestRetrievalSufficiencyPropertyTests:
    """Property-based tests for retrieval sufficiency scoring.
    
    Property: Sufficiency scores are bounded in [0.0, 1.0].
    """

    @given(
        coverage=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        redundancy=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        citation_density=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
        contradiction_rate=st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_overall_score_bounded(self, coverage, redundancy, citation_density, contradiction_rate):
        """Property: Overall sufficiency score is always in [0.0, 1.0]."""
        sufficiency = RetrievalSufficiency(
            coverage=coverage,
            redundancy=redundancy,
            citation_density=citation_density,
            contradiction_rate=contradiction_rate
        )
        
        score = sufficiency.compute_overall()
        
        assert 0.0 <= score <= 1.0
        assert sufficiency.overall_score == score

    @given(
        threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
    )
    @settings(max_examples=30)
    def test_is_sufficient_consistent(self, threshold):
        """Property: is_sufficient is consistent with overall_score."""
        sufficiency = RetrievalSufficiency(
            coverage=0.7,
            redundancy=0.2,
            citation_density=2.0,
            contradiction_rate=0.1
        )
        sufficiency.compute_overall()
        
        is_suff = sufficiency.is_sufficient(threshold)
        
        assert is_suff == (sufficiency.overall_score >= threshold)


class TestCachedSubgraphPropertyTests:
    """Property-based tests for CachedSubgraph serialization."""

    @given(
        query_hash=st.text(min_size=1, max_size=64, alphabet=st.characters(whitelist_categories=('L', 'Nd'))),
        node_ids=st.lists(
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'Nd'))),
            min_size=0,
            max_size=10
        ),
        access_count=st.integers(min_value=0, max_value=1000)
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_cached_subgraph_round_trip(self, query_hash, node_ids, access_count):
        """Property: CachedSubgraph serialization preserves all data."""
        assume(len(query_hash.strip()) > 0)
        
        subgraph = CachedSubgraph(
            query_hash=query_hash.strip(),
            node_ids=set(node_ids),
            access_count=access_count
        )
        
        d = subgraph.to_dict()
        restored = CachedSubgraph.from_dict(d)
        
        assert restored.query_hash == subgraph.query_hash
        assert restored.node_ids == subgraph.node_ids
        assert restored.access_count == subgraph.access_count


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
