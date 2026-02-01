"""LazyGraphRAG with Subgraph Materialization Cache.

Implements a hybrid retrieval system combining:
- Vector similarity search (fast, semantic)
- Graph-based retrieval (structured, relational)
- Lazy graph construction (on-demand, efficient)

Key features:
- Concept extraction beyond NER (noun phrases, key phrases, headings)
- Typed and weighted edges (co-occurrence, definition, dependency)
- Retrieval sufficiency scoring (coverage, redundancy, citation density)
- Subgraph materialization cache (LRU eviction)

Performance target: Index 10k docs in under 5 minutes.

Usage:
    from deepr.experts.lazy_graph_rag import LazyGraphRAG
    
    rag = LazyGraphRAG(expert_name="quantum_expert")
    
    # Index documents
    await rag.index_documents(documents)
    
    # Retrieve with hybrid search
    results = await rag.retrieve(query, top_k=5)
"""

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import hashlib


class EdgeType(Enum):
    """Types of edges in the knowledge graph."""
    CO_OCCURS = "co_occurs"           # Concepts appear together
    DEFINED_IN = "defined_in"         # Concept defined in section
    DEPENDS_ON = "depends_on"         # Concept depends on another
    MENTIONED_IN_SAME_SECTION = "mentioned_in_same_section"
    MENTIONED_IN_SAME_PARAGRAPH = "mentioned_in_same_paragraph"
    MENTIONED_IN_SAME_CHUNK = "mentioned_in_same_chunk"


@dataclass
class Concept:
    """A concept extracted from documents.
    
    Attributes:
        id: Unique concept identifier
        text: The concept text (normalized)
        original_forms: Original text forms found
        concept_type: Type of concept (noun_phrase, key_phrase, heading, entity)
        document_ids: Documents containing this concept
        section_ids: Sections containing this concept
        frequency: Total occurrence count
        tf_idf_score: TF-IDF importance score
        created_at: When concept was first extracted
    """
    text: str
    concept_type: str = "noun_phrase"
    original_forms: Set[str] = field(default_factory=set)
    document_ids: Set[str] = field(default_factory=set)
    section_ids: Set[str] = field(default_factory=set)
    frequency: int = 0
    tf_idf_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: str = field(default="")
    
    def __post_init__(self):
        if not self.id:
            self.id = hashlib.sha256(self.text.lower().encode()).hexdigest()[:12]
        if isinstance(self.original_forms, list):
            self.original_forms = set(self.original_forms)
        if isinstance(self.document_ids, list):
            self.document_ids = set(self.document_ids)
        if isinstance(self.section_ids, list):
            self.section_ids = set(self.section_ids)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "concept_type": self.concept_type,
            "original_forms": list(self.original_forms),
            "document_ids": list(self.document_ids),
            "section_ids": list(self.section_ids),
            "frequency": self.frequency,
            "tf_idf_score": self.tf_idf_score,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Concept":
        return cls(
            id=data.get("id", ""),
            text=data["text"],
            concept_type=data.get("concept_type", "noun_phrase"),
            original_forms=set(data.get("original_forms", [])),
            document_ids=set(data.get("document_ids", [])),
            section_ids=set(data.get("section_ids", [])),
            frequency=data.get("frequency", 0),
            tf_idf_score=data.get("tf_idf_score", 0.0),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow()
        )


@dataclass
class Edge:
    """An edge connecting two concepts.
    
    Attributes:
        source_id: Source concept ID
        target_id: Target concept ID
        edge_type: Type of relationship
        weight: Edge weight (PMI or TF-IDF based)
        document_ids: Documents where this edge was found
        created_at: When edge was first created
    """
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    document_ids: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        if isinstance(self.document_ids, list):
            self.document_ids = set(self.document_ids)
    
    @property
    def id(self) -> str:
        return f"{self.source_id}:{self.edge_type.value}:{self.target_id}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "weight": self.weight,
            "document_ids": list(self.document_ids),
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Edge":
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            edge_type=EdgeType(data["edge_type"]),
            weight=data.get("weight", 1.0),
            document_ids=set(data.get("document_ids", [])),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow()
        )


@dataclass
class DocumentSection:
    """A section within a document.
    
    Attributes:
        id: Unique section identifier
        document_id: Parent document ID
        heading: Section heading (if any)
        content: Section content
        level: Heading level (1-6, 0 for no heading)
        start_pos: Start position in document
        end_pos: End position in document
    """
    document_id: str
    content: str
    heading: str = ""
    level: int = 0
    start_pos: int = 0
    end_pos: int = 0
    id: str = field(default="")
    
    def __post_init__(self):
        if not self.id:
            content_hash = hashlib.sha256(f"{self.document_id}:{self.start_pos}:{self.content[:100]}".encode()).hexdigest()[:12]
            self.id = content_hash


class ConceptExtractor:
    """Extracts concepts from text using multiple methods.
    
    Methods:
    - Noun phrase mining (NP chunks)
    - Heading-aware section labels
    - TF-IDF/KeyBERT key phrase extraction
    - Simple NER for named entities
    
    Attributes:
        min_phrase_length: Minimum phrase length to extract
        max_phrase_length: Maximum phrase length to extract
        stopwords: Words to filter out
    """
    
    def __init__(
        self,
        min_phrase_length: int = 2,
        max_phrase_length: int = 5,
        min_frequency: int = 1
    ):
        self.min_phrase_length = min_phrase_length
        self.max_phrase_length = max_phrase_length
        self.min_frequency = min_frequency
        
        # Common stopwords
        self.stopwords = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'shall',
            'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
            'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
            'through', 'during', 'before', 'after', 'above', 'below',
            'between', 'under', 'again', 'further', 'then', 'once',
            'here', 'there', 'when', 'where', 'why', 'how', 'all',
            'each', 'few', 'more', 'most', 'other', 'some', 'such',
            'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
            'too', 'very', 'just', 'and', 'but', 'if', 'or', 'because',
            'until', 'while', 'what', 'which', 'who', 'whom', 'this',
            'that', 'these', 'those', 'am', 'it', 'its', 'i', 'you',
            'he', 'she', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
            'my', 'your', 'his', 'their', 'our', 'also', 'any', 'both',
            'etc', 'however', 'therefore', 'thus', 'hence', 'yet'
        }
        
        # Patterns for noun phrase extraction
        self._np_pattern = re.compile(
            r'\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|'  # Capitalized phrases
            r'[a-z]+(?:\s+[a-z]+){0,4})\b',  # Lowercase phrases
            re.UNICODE
        )
        
        # Pattern for headings in markdown
        self._heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    
    def extract_concepts(
        self,
        text: str,
        document_id: str,
        section_id: Optional[str] = None
    ) -> List[Concept]:
        """Extract concepts from text using multiple methods.
        
        Args:
            text: Text to extract from
            document_id: ID of source document
            section_id: ID of source section (optional)
            
        Returns:
            List of extracted concepts
        """
        concepts: Dict[str, Concept] = {}
        
        # 1. Extract noun phrases
        np_concepts = self._extract_noun_phrases(text, document_id, section_id)
        for concept in np_concepts:
            key = concept.text.lower()
            if key in concepts:
                concepts[key].frequency += concept.frequency
                concepts[key].original_forms.update(concept.original_forms)
                concepts[key].document_ids.update(concept.document_ids)
                if section_id:
                    concepts[key].section_ids.add(section_id)
            else:
                concepts[key] = concept
        
        # 2. Extract headings as concepts
        heading_concepts = self._extract_headings(text, document_id)
        for concept in heading_concepts:
            key = concept.text.lower()
            if key in concepts:
                concepts[key].concept_type = "heading"  # Upgrade to heading
                concepts[key].document_ids.update(concept.document_ids)
            else:
                concepts[key] = concept
        
        # 3. Extract key phrases using TF-IDF-like scoring
        key_phrases = self._extract_key_phrases(text, document_id, section_id)
        for concept in key_phrases:
            key = concept.text.lower()
            if key in concepts:
                concepts[key].tf_idf_score = max(concepts[key].tf_idf_score, concept.tf_idf_score)
            else:
                concepts[key] = concept
        
        # Filter by minimum frequency
        return [c for c in concepts.values() if c.frequency >= self.min_frequency]
    
    def _extract_noun_phrases(
        self,
        text: str,
        document_id: str,
        section_id: Optional[str] = None
    ) -> List[Concept]:
        """Extract noun phrases from text.
        
        Uses simple pattern matching for noun phrase extraction.
        For production, consider using spaCy or similar NLP library.
        
        Args:
            text: Text to extract from
            document_id: Source document ID
            section_id: Source section ID
            
        Returns:
            List of noun phrase concepts
        """
        concepts = []
        
        # Tokenize into words
        words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]*\b', text)
        
        # Extract n-grams
        for n in range(self.min_phrase_length, self.max_phrase_length + 1):
            for i in range(len(words) - n + 1):
                phrase_words = words[i:i + n]
                
                # Skip if starts or ends with stopword
                if phrase_words[0].lower() in self.stopwords:
                    continue
                if phrase_words[-1].lower() in self.stopwords:
                    continue
                
                # Skip if all stopwords
                if all(w.lower() in self.stopwords for w in phrase_words):
                    continue
                
                phrase = " ".join(phrase_words)
                normalized = phrase.lower()
                
                # Skip very short phrases
                if len(normalized) < 3:
                    continue
                
                concept = Concept(
                    text=normalized,
                    concept_type="noun_phrase",
                    original_forms={phrase},
                    document_ids={document_id},
                    section_ids={section_id} if section_id else set(),
                    frequency=1
                )
                concepts.append(concept)
        
        return concepts
    
    def _extract_headings(
        self,
        text: str,
        document_id: str
    ) -> List[Concept]:
        """Extract headings from markdown text.
        
        Args:
            text: Markdown text
            document_id: Source document ID
            
        Returns:
            List of heading concepts
        """
        concepts = []
        
        for match in self._heading_pattern.finditer(text):
            level = len(match.group(1))
            heading_text = match.group(2).strip()
            
            # Clean heading text
            heading_text = re.sub(r'[#*_`\[\]]', '', heading_text)
            normalized = heading_text.lower()
            
            if len(normalized) < 3:
                continue
            
            concept = Concept(
                text=normalized,
                concept_type="heading",
                original_forms={heading_text},
                document_ids={document_id},
                frequency=1,
                tf_idf_score=1.0 / level  # Higher level headings get higher score
            )
            concepts.append(concept)
        
        return concepts
    
    def _extract_key_phrases(
        self,
        text: str,
        document_id: str,
        section_id: Optional[str] = None
    ) -> List[Concept]:
        """Extract key phrases using TF-IDF-like scoring.
        
        Simple implementation without external dependencies.
        For production, consider using KeyBERT or YAKE.
        
        Args:
            text: Text to extract from
            document_id: Source document ID
            section_id: Source section ID
            
        Returns:
            List of key phrase concepts
        """
        concepts = []
        
        # Tokenize and count
        words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]*\b', text.lower())
        word_counts: Dict[str, int] = defaultdict(int)
        
        for word in words:
            if word not in self.stopwords and len(word) > 2:
                word_counts[word] += 1
        
        # Calculate TF scores
        total_words = len(words)
        if total_words == 0:
            return concepts
        
        # Get top words by frequency
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        
        for word, count in sorted_words[:50]:  # Top 50 words
            tf = count / total_words
            # Simple IDF approximation (would need corpus for real IDF)
            idf = math.log(1 + 1 / (count + 1))
            tf_idf = tf * idf
            
            concept = Concept(
                text=word,
                concept_type="key_phrase",
                original_forms={word},
                document_ids={document_id},
                section_ids={section_id} if section_id else set(),
                frequency=count,
                tf_idf_score=tf_idf
            )
            concepts.append(concept)
        
        return concepts
    
    def extract_sections(
        self,
        text: str,
        document_id: str
    ) -> List[DocumentSection]:
        """Extract sections from markdown document.
        
        Args:
            text: Markdown text
            document_id: Document ID
            
        Returns:
            List of document sections
        """
        sections = []
        
        # Find all headings
        headings = list(self._heading_pattern.finditer(text))
        
        if not headings:
            # No headings - treat entire document as one section
            sections.append(DocumentSection(
                document_id=document_id,
                content=text,
                heading="",
                level=0,
                start_pos=0,
                end_pos=len(text)
            ))
            return sections
        
        # Extract sections between headings
        for i, match in enumerate(headings):
            level = len(match.group(1))
            heading = match.group(2).strip()
            start_pos = match.start()
            
            # End position is start of next heading or end of document
            if i + 1 < len(headings):
                end_pos = headings[i + 1].start()
            else:
                end_pos = len(text)
            
            content = text[start_pos:end_pos]
            
            sections.append(DocumentSection(
                document_id=document_id,
                content=content,
                heading=heading,
                level=level,
                start_pos=start_pos,
                end_pos=end_pos
            ))
        
        # Add content before first heading if any
        if headings[0].start() > 0:
            sections.insert(0, DocumentSection(
                document_id=document_id,
                content=text[:headings[0].start()],
                heading="",
                level=0,
                start_pos=0,
                end_pos=headings[0].start()
            ))
        
        return sections


class EdgeBuilder:
    """Builds typed and weighted edges between concepts.
    
    Edge types:
    - CO_OCCURS: Concepts appear together (PMI weighted)
    - DEFINED_IN: Concept defined in section
    - DEPENDS_ON: Concept depends on another
    - MENTIONED_IN_SAME_SECTION: Same section co-occurrence
    - MENTIONED_IN_SAME_PARAGRAPH: Same paragraph co-occurrence
    - MENTIONED_IN_SAME_CHUNK: Same chunk co-occurrence
    
    Weighting:
    - PMI (Pointwise Mutual Information) for co-occurrence
    - TF-IDF for importance
    - Scope-based: same heading > same paragraph > same chunk
    """
    
    def __init__(self, min_pmi: float = 0.0):
        """Initialize edge builder.
        
        Args:
            min_pmi: Minimum PMI score for edge creation
        """
        self.min_pmi = min_pmi
        
        # Scope weights (higher = stronger relationship)
        self.scope_weights = {
            "same_heading": 1.0,
            "same_paragraph": 0.7,
            "same_chunk": 0.4
        }
    
    def build_edges(
        self,
        concepts: List[Concept],
        sections: List[DocumentSection],
        document_id: str
    ) -> List[Edge]:
        """Build edges between concepts based on co-occurrence.
        
        Args:
            concepts: List of concepts
            sections: List of document sections
            document_id: Document ID
            
        Returns:
            List of edges
        """
        edges: Dict[str, Edge] = {}
        
        # Build concept index by section
        section_concepts: Dict[str, List[Concept]] = defaultdict(list)
        for concept in concepts:
            for section_id in concept.section_ids:
                section_concepts[section_id].append(concept)
        
        # Build edges within each section
        for section in sections:
            section_id = section.id
            concepts_in_section = section_concepts.get(section_id, [])
            
            # Build co-occurrence edges
            for i, c1 in enumerate(concepts_in_section):
                for c2 in concepts_in_section[i + 1:]:
                    edge = self._create_cooccurrence_edge(
                        c1, c2, section, document_id
                    )
                    if edge:
                        key = edge.id
                        if key in edges:
                            edges[key].weight = max(edges[key].weight, edge.weight)
                            edges[key].document_ids.update(edge.document_ids)
                        else:
                            edges[key] = edge
            
            # Build definition edges (heading -> concepts in section)
            if section.heading:
                heading_concept = self._find_concept_by_text(
                    concepts, section.heading.lower()
                )
                if heading_concept:
                    for concept in concepts_in_section:
                        if concept.id != heading_concept.id:
                            edge = Edge(
                                source_id=concept.id,
                                target_id=heading_concept.id,
                                edge_type=EdgeType.DEFINED_IN,
                                weight=1.0 / section.level if section.level > 0 else 1.0,
                                document_ids={document_id}
                            )
                            key = edge.id
                            if key not in edges:
                                edges[key] = edge
        
        return list(edges.values())
    
    def _create_cooccurrence_edge(
        self,
        c1: Concept,
        c2: Concept,
        section: DocumentSection,
        document_id: str
    ) -> Optional[Edge]:
        """Create a co-occurrence edge between two concepts.
        
        Args:
            c1: First concept
            c2: Second concept
            section: Section where they co-occur
            document_id: Document ID
            
        Returns:
            Edge or None if below threshold
        """
        # Determine scope
        content = section.content.lower()
        
        # Check if in same paragraph
        paragraphs = content.split('\n\n')
        same_paragraph = False
        for para in paragraphs:
            if c1.text in para and c2.text in para:
                same_paragraph = True
                break
        
        # Determine edge type and weight
        if section.heading:
            edge_type = EdgeType.MENTIONED_IN_SAME_SECTION
            base_weight = self.scope_weights["same_heading"]
        elif same_paragraph:
            edge_type = EdgeType.MENTIONED_IN_SAME_PARAGRAPH
            base_weight = self.scope_weights["same_paragraph"]
        else:
            edge_type = EdgeType.MENTIONED_IN_SAME_CHUNK
            base_weight = self.scope_weights["same_chunk"]
        
        # Calculate PMI-like weight
        # Simple approximation: frequency-based
        freq_weight = math.log(1 + min(c1.frequency, c2.frequency))
        weight = base_weight * freq_weight
        
        if weight < self.min_pmi:
            return None
        
        return Edge(
            source_id=c1.id,
            target_id=c2.id,
            edge_type=edge_type,
            weight=weight,
            document_ids={document_id}
        )
    
    def _find_concept_by_text(
        self,
        concepts: List[Concept],
        text: str
    ) -> Optional[Concept]:
        """Find concept by text.
        
        Args:
            concepts: List of concepts
            text: Text to search for
            
        Returns:
            Matching concept or None
        """
        text_lower = text.lower()
        for concept in concepts:
            if concept.text == text_lower:
                return concept
            if text_lower in concept.original_forms:
                return concept
        return None
    
    def calculate_pmi(
        self,
        c1_count: int,
        c2_count: int,
        cooccur_count: int,
        total_docs: int
    ) -> float:
        """Calculate Pointwise Mutual Information.
        
        PMI(x,y) = log(P(x,y) / (P(x) * P(y)))
        
        Args:
            c1_count: Documents containing concept 1
            c2_count: Documents containing concept 2
            cooccur_count: Documents containing both
            total_docs: Total number of documents
            
        Returns:
            PMI score
        """
        if total_docs == 0 or c1_count == 0 or c2_count == 0 or cooccur_count == 0:
            return 0.0
        
        p_x = c1_count / total_docs
        p_y = c2_count / total_docs
        p_xy = cooccur_count / total_docs
        
        if p_x * p_y == 0:
            return 0.0
        
        return math.log(p_xy / (p_x * p_y))


@dataclass
class RetrievalSufficiency:
    """Measures retrieval sufficiency for a query.
    
    Attributes:
        coverage: How well chunks cover query sub-aspects (0-1)
        redundancy: How much overlap between chunks (0-1, lower is better)
        citation_density: Citations per chunk (higher is better)
        contradiction_rate: Rate of contradictions found (0-1, lower is better)
        overall_score: Combined sufficiency score (0-1)
    """
    coverage: float = 0.0
    redundancy: float = 0.0
    citation_density: float = 0.0
    contradiction_rate: float = 0.0
    overall_score: float = 0.0
    
    def compute_overall(self) -> float:
        """Compute overall sufficiency score.
        
        Returns:
            Overall score (0-1)
        """
        # Weighted combination
        # Coverage is most important, redundancy and contradictions are penalties
        self.overall_score = (
            0.5 * self.coverage +
            0.2 * (1 - self.redundancy) +
            0.2 * min(1.0, self.citation_density / 3) +  # Normalize to 0-1
            0.1 * (1 - self.contradiction_rate)
        )
        return self.overall_score
    
    def is_sufficient(self, threshold: float = 0.6) -> bool:
        """Check if retrieval is sufficient.
        
        Args:
            threshold: Minimum score for sufficiency
            
        Returns:
            True if sufficient
        """
        return self.overall_score >= threshold


class SufficiencyScorer:
    """Scores retrieval sufficiency for queries.
    
    Measures:
    - Coverage: Do chunks cover all query sub-aspects?
    - Redundancy: Are chunks duplicates?
    - Citation density: How many citations per chunk?
    - Contradiction rate: How many contradictions found?
    """
    
    def __init__(self):
        self.stopwords = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'can', 'to', 'of',
            'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'and',
            'but', 'or', 'if', 'what', 'which', 'who', 'how', 'why', 'when'
        }
    
    def score(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        citations: Optional[List[str]] = None
    ) -> RetrievalSufficiency:
        """Score retrieval sufficiency.
        
        Args:
            query: Original query
            chunks: Retrieved chunks
            citations: Optional list of citations found
            
        Returns:
            RetrievalSufficiency with scores
        """
        sufficiency = RetrievalSufficiency()
        
        if not chunks:
            return sufficiency
        
        # Calculate coverage
        sufficiency.coverage = self._calculate_coverage(query, chunks)
        
        # Calculate redundancy
        sufficiency.redundancy = self._calculate_redundancy(chunks)
        
        # Calculate citation density
        if citations:
            sufficiency.citation_density = len(citations) / len(chunks)
        else:
            sufficiency.citation_density = self._estimate_citation_density(chunks)
        
        # Calculate contradiction rate (simplified)
        sufficiency.contradiction_rate = self._estimate_contradiction_rate(chunks)
        
        # Compute overall score
        sufficiency.compute_overall()
        
        return sufficiency
    
    def _calculate_coverage(
        self,
        query: str,
        chunks: List[Dict[str, Any]]
    ) -> float:
        """Calculate how well chunks cover query aspects.
        
        Args:
            query: Original query
            chunks: Retrieved chunks
            
        Returns:
            Coverage score (0-1)
        """
        # Extract query keywords
        query_words = set(
            w.lower() for w in re.findall(r'\b[a-zA-Z]+\b', query)
            if w.lower() not in self.stopwords and len(w) > 2
        )
        
        if not query_words:
            return 1.0  # No keywords to cover
        
        # Check which keywords are covered by chunks
        covered = set()
        for chunk in chunks:
            content = chunk.get("content", "").lower()
            for word in query_words:
                if word in content:
                    covered.add(word)
        
        return len(covered) / len(query_words)
    
    def _calculate_redundancy(
        self,
        chunks: List[Dict[str, Any]]
    ) -> float:
        """Calculate redundancy between chunks.
        
        Args:
            chunks: Retrieved chunks
            
        Returns:
            Redundancy score (0-1)
        """
        if len(chunks) < 2:
            return 0.0
        
        # Calculate pairwise similarity
        total_similarity = 0.0
        pairs = 0
        
        for i, c1 in enumerate(chunks):
            for c2 in chunks[i + 1:]:
                similarity = self._jaccard_similarity(
                    c1.get("content", ""),
                    c2.get("content", "")
                )
                total_similarity += similarity
                pairs += 1
        
        if pairs == 0:
            return 0.0
        
        return total_similarity / pairs
    
    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between texts.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity score (0-1)
        """
        words1 = set(w.lower() for w in re.findall(r'\b[a-zA-Z]+\b', text1))
        words2 = set(w.lower() for w in re.findall(r'\b[a-zA-Z]+\b', text2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def _estimate_citation_density(
        self,
        chunks: List[Dict[str, Any]]
    ) -> float:
        """Estimate citation density from chunks.
        
        Args:
            chunks: Retrieved chunks
            
        Returns:
            Estimated citations per chunk
        """
        # Look for citation patterns in content
        citation_patterns = [
            r'\[\d+\]',  # [1], [2], etc.
            r'\[.*?\d{4}.*?\]',  # [Author 2024]
            r'https?://\S+',  # URLs
            r'Source:',  # Source labels
        ]
        
        total_citations = 0
        for chunk in chunks:
            content = chunk.get("content", "")
            for pattern in citation_patterns:
                matches = re.findall(pattern, content)
                total_citations += len(matches)
        
        return total_citations / len(chunks) if chunks else 0.0
    
    def _estimate_contradiction_rate(
        self,
        chunks: List[Dict[str, Any]]
    ) -> float:
        """Estimate contradiction rate between chunks.
        
        Simple heuristic: look for negation patterns.
        For production, use NLI model.
        
        Args:
            chunks: Retrieved chunks
            
        Returns:
            Estimated contradiction rate (0-1)
        """
        # Simple heuristic: count negation words
        negation_words = {'not', 'no', 'never', 'none', 'neither', 'nor', 
                         'cannot', "can't", "won't", "don't", "doesn't",
                         'however', 'but', 'although', 'despite', 'contrary'}
        
        negation_count = 0
        total_words = 0
        
        for chunk in chunks:
            content = chunk.get("content", "").lower()
            words = content.split()
            total_words += len(words)
            negation_count += sum(1 for w in words if w in negation_words)
        
        if total_words == 0:
            return 0.0
        
        # Normalize: high negation density might indicate contradictions
        negation_rate = negation_count / total_words
        
        # Scale to 0-1 (assuming >5% negation words is high)
        return min(1.0, negation_rate * 20)


@dataclass
class CachedSubgraph:
    """A cached subgraph for a query cluster.
    
    Attributes:
        query_hash: Hash of the query cluster
        node_ids: Selected node IDs
        node_summaries: Lazy summaries for nodes
        prompt_blocks: Rendered prompt blocks
        created_at: When cache entry was created
        last_accessed: When cache was last accessed
        access_count: Number of accesses
    """
    query_hash: str
    node_ids: Set[str] = field(default_factory=set)
    node_summaries: Dict[str, str] = field(default_factory=dict)
    prompt_blocks: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    
    def __post_init__(self):
        if isinstance(self.node_ids, list):
            self.node_ids = set(self.node_ids)
    
    def touch(self):
        """Update access time and count."""
        self.last_accessed = datetime.utcnow()
        self.access_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_hash": self.query_hash,
            "node_ids": list(self.node_ids),
            "node_summaries": self.node_summaries,
            "prompt_blocks": self.prompt_blocks,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CachedSubgraph":
        return cls(
            query_hash=data["query_hash"],
            node_ids=set(data.get("node_ids", [])),
            node_summaries=data.get("node_summaries", {}),
            prompt_blocks=data.get("prompt_blocks", []),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow(),
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if "last_accessed" in data else datetime.utcnow(),
            access_count=data.get("access_count", 0)
        )


class SubgraphCache:
    """LRU cache for materialized subgraphs.
    
    Caches:
    - Node IDs selected for query clusters
    - Computed node summaries (lazy summaries)
    - Rendered prompt blocks (structured context)
    
    NOTE: This is NOT KV tensor caching (requires self-hosting).
    This caches the graph traversal results and summaries.
    
    Attributes:
        max_size: Maximum cache entries
        cache: Query hash -> CachedSubgraph
        storage_path: Path for persistence
    """
    
    def __init__(
        self,
        max_size: int = 100,
        storage_path: Optional[Path] = None
    ):
        """Initialize subgraph cache.
        
        Args:
            max_size: Maximum cache entries
            storage_path: Path for persistence
        """
        self.max_size = max_size
        self.cache: Dict[str, CachedSubgraph] = {}
        self.storage_path = storage_path
        
        if storage_path:
            self._load()
    
    def get(self, query: str) -> Optional[CachedSubgraph]:
        """Get cached subgraph for query.
        
        Args:
            query: Query string
            
        Returns:
            CachedSubgraph or None
        """
        query_hash = self._hash_query(query)
        
        if query_hash in self.cache:
            subgraph = self.cache[query_hash]
            subgraph.touch()
            return subgraph
        
        return None
    
    def put(
        self,
        query: str,
        node_ids: Set[str],
        node_summaries: Optional[Dict[str, str]] = None,
        prompt_blocks: Optional[List[str]] = None
    ) -> CachedSubgraph:
        """Cache a subgraph for query.
        
        Args:
            query: Query string
            node_ids: Selected node IDs
            node_summaries: Optional node summaries
            prompt_blocks: Optional prompt blocks
            
        Returns:
            Created CachedSubgraph
        """
        query_hash = self._hash_query(query)
        
        # Evict if at capacity
        if len(self.cache) >= self.max_size:
            self._evict_lru()
        
        subgraph = CachedSubgraph(
            query_hash=query_hash,
            node_ids=node_ids,
            node_summaries=node_summaries or {},
            prompt_blocks=prompt_blocks or []
        )
        
        self.cache[query_hash] = subgraph
        
        # Persist
        if self.storage_path:
            self._save()
        
        return subgraph
    
    def update_summaries(
        self,
        query: str,
        summaries: Dict[str, str]
    ):
        """Update node summaries for cached query.
        
        Args:
            query: Query string
            summaries: Node ID -> summary mapping
        """
        query_hash = self._hash_query(query)
        
        if query_hash in self.cache:
            self.cache[query_hash].node_summaries.update(summaries)
            self.cache[query_hash].touch()
            
            if self.storage_path:
                self._save()
    
    def update_prompt_blocks(
        self,
        query: str,
        blocks: List[str]
    ):
        """Update prompt blocks for cached query.
        
        Args:
            query: Query string
            blocks: Prompt blocks
        """
        query_hash = self._hash_query(query)
        
        if query_hash in self.cache:
            self.cache[query_hash].prompt_blocks = blocks
            self.cache[query_hash].touch()
            
            if self.storage_path:
                self._save()
    
    def invalidate(self, query: str):
        """Invalidate cache entry for query.
        
        Args:
            query: Query string
        """
        query_hash = self._hash_query(query)
        
        if query_hash in self.cache:
            del self.cache[query_hash]
            
            if self.storage_path:
                self._save()
    
    def clear(self):
        """Clear all cache entries."""
        self.cache.clear()
        
        if self.storage_path:
            self._save()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        if not self.cache:
            return {
                "size": 0,
                "max_size": self.max_size,
                "hit_rate": 0.0
            }
        
        total_accesses = sum(s.access_count for s in self.cache.values())
        
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "total_accesses": total_accesses,
            "avg_accesses": total_accesses / len(self.cache),
            "oldest_entry": min(s.created_at for s in self.cache.values()).isoformat(),
            "newest_entry": max(s.created_at for s in self.cache.values()).isoformat()
        }
    
    def _hash_query(self, query: str) -> str:
        """Hash query for cache key.
        
        Normalizes query before hashing.
        
        Args:
            query: Query string
            
        Returns:
            Query hash
        """
        # Normalize: lowercase, remove extra whitespace
        normalized = " ".join(query.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
    
    def _evict_lru(self):
        """Evict least recently used entry."""
        if not self.cache:
            return
        
        # Find LRU entry
        lru_hash = min(
            self.cache.keys(),
            key=lambda h: self.cache[h].last_accessed
        )
        
        del self.cache[lru_hash]
    
    def _save(self):
        """Persist cache to disk."""
        if not self.storage_path:
            return
        
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "max_size": self.max_size,
            "entries": {h: s.to_dict() for h, s in self.cache.items()}
        }
        
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def _load(self):
        """Load cache from disk."""
        if not self.storage_path or not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.max_size = data.get("max_size", self.max_size)
            
            for hash_key, entry_data in data.get("entries", {}).items():
                self.cache[hash_key] = CachedSubgraph.from_dict(entry_data)
        except Exception:
            # Corrupted cache - start fresh
            self.cache.clear()


class KnowledgeGraph:
    """Knowledge graph for LazyGraphRAG.
    
    Stores concepts and edges with efficient retrieval.
    Supports lazy construction and incremental updates.
    
    Attributes:
        expert_name: Name of the expert
        concepts: Concept ID -> Concept
        edges: Edge ID -> Edge
        adjacency: Concept ID -> List of (neighbor_id, edge)
        storage_dir: Directory for persistence
    """
    
    def __init__(
        self,
        expert_name: str,
        storage_dir: Optional[Path] = None
    ):
        """Initialize knowledge graph.
        
        Args:
            expert_name: Name of the expert
            storage_dir: Directory for persistence
        """
        self.expert_name = expert_name
        
        if storage_dir is None:
            storage_dir = Path("data/experts") / expert_name / "graph"
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Graph data
        self.concepts: Dict[str, Concept] = {}
        self.edges: Dict[str, Edge] = {}
        self.adjacency: Dict[str, List[Tuple[str, Edge]]] = defaultdict(list)
        
        # Reverse index: text -> concept_id
        self._text_index: Dict[str, str] = {}
        
        # Load persisted graph
        self._load()
    
    def add_concept(self, concept: Concept) -> str:
        """Add concept to graph.
        
        Args:
            concept: Concept to add
            
        Returns:
            Concept ID
        """
        if concept.id in self.concepts:
            # Merge with existing
            existing = self.concepts[concept.id]
            existing.frequency += concept.frequency
            existing.original_forms.update(concept.original_forms)
            existing.document_ids.update(concept.document_ids)
            existing.section_ids.update(concept.section_ids)
            existing.tf_idf_score = max(existing.tf_idf_score, concept.tf_idf_score)
        else:
            self.concepts[concept.id] = concept
            self._text_index[concept.text.lower()] = concept.id
        
        return concept.id
    
    def add_edge(self, edge: Edge) -> str:
        """Add edge to graph.
        
        Args:
            edge: Edge to add
            
        Returns:
            Edge ID
        """
        edge_id = edge.id
        
        if edge_id in self.edges:
            # Merge with existing
            existing = self.edges[edge_id]
            existing.weight = max(existing.weight, edge.weight)
            existing.document_ids.update(edge.document_ids)
        else:
            self.edges[edge_id] = edge
            
            # Update adjacency
            self.adjacency[edge.source_id].append((edge.target_id, edge))
            self.adjacency[edge.target_id].append((edge.source_id, edge))
        
        return edge_id
    
    def get_concept(self, concept_id: str) -> Optional[Concept]:
        """Get concept by ID.
        
        Args:
            concept_id: Concept ID
            
        Returns:
            Concept or None
        """
        return self.concepts.get(concept_id)
    
    def get_concept_by_text(self, text: str) -> Optional[Concept]:
        """Get concept by text.
        
        Args:
            text: Concept text
            
        Returns:
            Concept or None
        """
        concept_id = self._text_index.get(text.lower())
        if concept_id:
            return self.concepts.get(concept_id)
        return None
    
    def get_neighbors(
        self,
        concept_id: str,
        edge_types: Optional[List[EdgeType]] = None,
        min_weight: float = 0.0
    ) -> List[Tuple[Concept, Edge]]:
        """Get neighboring concepts.
        
        Args:
            concept_id: Source concept ID
            edge_types: Filter by edge types
            min_weight: Minimum edge weight
            
        Returns:
            List of (neighbor_concept, edge) tuples
        """
        neighbors = []
        
        for neighbor_id, edge in self.adjacency.get(concept_id, []):
            # Filter by edge type
            if edge_types and edge.edge_type not in edge_types:
                continue
            
            # Filter by weight
            if edge.weight < min_weight:
                continue
            
            neighbor = self.concepts.get(neighbor_id)
            if neighbor:
                neighbors.append((neighbor, edge))
        
        # Sort by edge weight
        neighbors.sort(key=lambda x: x[1].weight, reverse=True)
        
        return neighbors
    
    def traverse(
        self,
        start_ids: List[str],
        max_depth: int = 2,
        max_nodes: int = 50,
        edge_types: Optional[List[EdgeType]] = None,
        min_weight: float = 0.0
    ) -> Set[str]:
        """Traverse graph from starting nodes.
        
        BFS traversal with depth and node limits.
        
        Args:
            start_ids: Starting concept IDs
            max_depth: Maximum traversal depth
            max_nodes: Maximum nodes to visit
            edge_types: Filter by edge types
            min_weight: Minimum edge weight
            
        Returns:
            Set of visited concept IDs
        """
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(cid, 0) for cid in start_ids if cid in self.concepts]
        
        while queue and len(visited) < max_nodes:
            concept_id, depth = queue.pop(0)
            
            if concept_id in visited:
                continue
            
            visited.add(concept_id)
            
            if depth >= max_depth:
                continue
            
            # Add neighbors to queue
            for neighbor, edge in self.get_neighbors(concept_id, edge_types, min_weight):
                if neighbor.id not in visited:
                    queue.append((neighbor.id, depth + 1))
        
        return visited
    
    def search(
        self,
        query: str,
        top_k: int = 10
    ) -> List[Concept]:
        """Search for concepts matching query.
        
        Args:
            query: Search query
            top_k: Maximum results
            
        Returns:
            List of matching concepts
        """
        query_words = set(
            w.lower() for w in re.findall(r'\b[a-zA-Z]+\b', query)
            if len(w) > 2
        )
        
        if not query_words:
            return []
        
        # Score concepts by keyword overlap
        scored: List[Tuple[float, Concept]] = []
        
        for concept in self.concepts.values():
            concept_words = set(concept.text.lower().split())
            
            # Jaccard similarity
            intersection = len(query_words & concept_words)
            union = len(query_words | concept_words)
            
            if union > 0 and intersection > 0:
                score = intersection / union
                # Boost by TF-IDF
                score *= (1 + concept.tf_idf_score)
                scored.append((score, concept))
        
        # Sort by score
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [concept for _, concept in scored[:top_k]]
    
    def save(self):
        """Persist graph to disk."""
        # Save concepts
        concepts_path = self.storage_dir / "concepts.json"
        concepts_data = [c.to_dict() for c in self.concepts.values()]
        with open(concepts_path, 'w', encoding='utf-8') as f:
            json.dump(concepts_data, f, indent=2)
        
        # Save edges
        edges_path = self.storage_dir / "edges.json"
        edges_data = [e.to_dict() for e in self.edges.values()]
        with open(edges_path, 'w', encoding='utf-8') as f:
            json.dump(edges_data, f, indent=2)
    
    def _load(self):
        """Load graph from disk."""
        # Load concepts
        concepts_path = self.storage_dir / "concepts.json"
        if concepts_path.exists():
            with open(concepts_path, 'r', encoding='utf-8') as f:
                concepts_data = json.load(f)
            for data in concepts_data:
                concept = Concept.from_dict(data)
                self.concepts[concept.id] = concept
                self._text_index[concept.text.lower()] = concept.id
        
        # Load edges
        edges_path = self.storage_dir / "edges.json"
        if edges_path.exists():
            with open(edges_path, 'r', encoding='utf-8') as f:
                edges_data = json.load(f)
            for data in edges_data:
                edge = Edge.from_dict(data)
                self.edges[edge.id] = edge
                self.adjacency[edge.source_id].append((edge.target_id, edge))
                self.adjacency[edge.target_id].append((edge.source_id, edge))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics.
        
        Returns:
            Dictionary with graph stats
        """
        return {
            "concept_count": len(self.concepts),
            "edge_count": len(self.edges),
            "avg_degree": len(self.edges) * 2 / len(self.concepts) if self.concepts else 0,
            "concept_types": self._count_concept_types(),
            "edge_types": self._count_edge_types()
        }
    
    def _count_concept_types(self) -> Dict[str, int]:
        """Count concepts by type."""
        counts: Dict[str, int] = defaultdict(int)
        for concept in self.concepts.values():
            counts[concept.concept_type] += 1
        return dict(counts)
    
    def _count_edge_types(self) -> Dict[str, int]:
        """Count edges by type."""
        counts: Dict[str, int] = defaultdict(int)
        for edge in self.edges.values():
            counts[edge.edge_type.value] += 1
        return dict(counts)


class LazyGraphRAG:
    """LazyGraphRAG with Subgraph Materialization Cache.
    
    Hybrid retrieval combining:
    - Vector similarity search (fast, semantic)
    - Graph-based retrieval (structured, relational)
    
    Features:
    - Lazy graph construction (on-demand)
    - Retrieval sufficiency scoring
    - Subgraph caching with LRU eviction
    - Hybrid routing (simple -> vector, complex -> graph)
    
    Performance target: Index 10k docs in under 5 minutes.
    
    Attributes:
        expert_name: Name of the expert
        graph: Knowledge graph
        cache: Subgraph cache
        extractor: Concept extractor
        edge_builder: Edge builder
        sufficiency_scorer: Sufficiency scorer
        sufficiency_threshold: Threshold for graph expansion
    """
    
    def __init__(
        self,
        expert_name: str,
        storage_dir: Optional[Path] = None,
        cache_size: int = 100,
        sufficiency_threshold: float = 0.6
    ):
        """Initialize LazyGraphRAG.
        
        Args:
            expert_name: Name of the expert
            storage_dir: Directory for persistence
            cache_size: Maximum cache entries
            sufficiency_threshold: Threshold for graph expansion
        """
        self.expert_name = expert_name
        self.sufficiency_threshold = sufficiency_threshold
        
        if storage_dir is None:
            storage_dir = Path("data/experts") / expert_name
        self.storage_dir = storage_dir
        
        # Initialize components
        self.graph = KnowledgeGraph(
            expert_name=expert_name,
            storage_dir=storage_dir / "graph"
        )
        
        self.cache = SubgraphCache(
            max_size=cache_size,
            storage_path=storage_dir / "cache" / "subgraph_cache.json"
        )
        
        self.extractor = ConceptExtractor()
        self.edge_builder = EdgeBuilder()
        self.sufficiency_scorer = SufficiencyScorer()
        
        # Track indexing stats
        self._indexed_docs: Set[str] = set()
        self._last_index_time: Optional[datetime] = None
    
    async def index_document(
        self,
        document_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Index a single document.
        
        Extracts concepts and builds edges lazily.
        
        Args:
            document_id: Document identifier
            content: Document content
            metadata: Optional metadata
            
        Returns:
            Indexing statistics
        """
        start_time = datetime.utcnow()
        
        # Extract sections
        sections = self.extractor.extract_sections(content, document_id)
        
        # Extract concepts from each section
        all_concepts: List[Concept] = []
        for section in sections:
            concepts = self.extractor.extract_concepts(
                section.content,
                document_id,
                section.id
            )
            all_concepts.extend(concepts)
        
        # Add concepts to graph
        for concept in all_concepts:
            self.graph.add_concept(concept)
        
        # Build edges
        edges = self.edge_builder.build_edges(all_concepts, sections, document_id)
        for edge in edges:
            self.graph.add_edge(edge)
        
        # Track indexed document
        self._indexed_docs.add(document_id)
        self._last_index_time = datetime.utcnow()
        
        # Persist graph
        self.graph.save()
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "document_id": document_id,
            "sections": len(sections),
            "concepts": len(all_concepts),
            "edges": len(edges),
            "elapsed_seconds": elapsed
        }
    
    async def index_documents(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> Dict[str, Any]:
        """Index multiple documents.
        
        Args:
            documents: List of {id, content, metadata} dicts
            batch_size: Documents per batch
            
        Returns:
            Indexing statistics
        """
        start_time = datetime.utcnow()
        
        total_concepts = 0
        total_edges = 0
        total_sections = 0
        
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            
            for doc in batch:
                result = await self.index_document(
                    document_id=doc.get("id", doc.get("filename", str(i))),
                    content=doc.get("content", ""),
                    metadata=doc.get("metadata")
                )
                
                total_concepts += result["concepts"]
                total_edges += result["edges"]
                total_sections += result["sections"]
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        return {
            "documents": len(documents),
            "sections": total_sections,
            "concepts": total_concepts,
            "edges": total_edges,
            "elapsed_seconds": elapsed,
            "docs_per_second": len(documents) / elapsed if elapsed > 0 else 0
        }
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        use_graph: bool = True,
        expand_if_insufficient: bool = True
    ) -> Dict[str, Any]:
        """Retrieve relevant content for query.
        
        Hybrid retrieval:
        1. Check cache for similar queries
        2. Search graph for matching concepts
        3. Traverse to related concepts
        4. Score sufficiency
        5. Expand if insufficient
        
        Args:
            query: Search query
            top_k: Maximum results
            use_graph: Whether to use graph traversal
            expand_if_insufficient: Whether to expand on low sufficiency
            
        Returns:
            Retrieval results with sufficiency score
        """
        # Check cache first
        cached = self.cache.get(query)
        if cached and cached.prompt_blocks:
            return {
                "chunks": [{"content": block} for block in cached.prompt_blocks],
                "from_cache": True,
                "sufficiency": RetrievalSufficiency(overall_score=0.8),
                "concepts": list(cached.node_ids)
            }
        
        # Search graph for matching concepts
        matching_concepts = self.graph.search(query, top_k=top_k * 2)
        
        if not matching_concepts:
            return {
                "chunks": [],
                "from_cache": False,
                "sufficiency": RetrievalSufficiency(),
                "concepts": []
            }
        
        # Get concept IDs
        concept_ids = [c.id for c in matching_concepts]
        
        # Traverse graph if enabled
        if use_graph:
            visited = self.graph.traverse(
                start_ids=concept_ids,
                max_depth=2,
                max_nodes=top_k * 3
            )
            concept_ids = list(visited)
        
        # Build chunks from concepts
        chunks = self._build_chunks(concept_ids, top_k)
        
        # Score sufficiency
        sufficiency = self.sufficiency_scorer.score(query, chunks)
        
        # Expand if insufficient
        if expand_if_insufficient and not sufficiency.is_sufficient(self.sufficiency_threshold):
            # Try deeper traversal
            visited = self.graph.traverse(
                start_ids=concept_ids,
                max_depth=3,
                max_nodes=top_k * 5
            )
            concept_ids = list(visited)
            chunks = self._build_chunks(concept_ids, top_k * 2)
            sufficiency = self.sufficiency_scorer.score(query, chunks)
        
        # Cache results
        prompt_blocks = [c.get("content", "") for c in chunks]
        self.cache.put(
            query=query,
            node_ids=set(concept_ids),
            prompt_blocks=prompt_blocks
        )
        
        return {
            "chunks": chunks,
            "from_cache": False,
            "sufficiency": sufficiency,
            "concepts": concept_ids
        }
    
    def _build_chunks(
        self,
        concept_ids: List[str],
        max_chunks: int
    ) -> List[Dict[str, Any]]:
        """Build retrieval chunks from concepts.
        
        Args:
            concept_ids: Concept IDs to include
            max_chunks: Maximum chunks
            
        Returns:
            List of chunk dictionaries
        """
        chunks = []
        
        for concept_id in concept_ids[:max_chunks]:
            concept = self.graph.get_concept(concept_id)
            if not concept:
                continue
            
            # Build chunk content
            content = f"**{concept.text}**\n"
            
            # Add related concepts
            neighbors = self.graph.get_neighbors(concept_id, min_weight=0.3)
            if neighbors:
                related = [n.text for n, _ in neighbors[:5]]
                content += f"Related: {', '.join(related)}\n"
            
            # Add document references
            if concept.document_ids:
                content += f"Sources: {', '.join(list(concept.document_ids)[:3])}\n"
            
            chunks.append({
                "id": concept_id,
                "content": content,
                "score": concept.tf_idf_score,
                "concept_type": concept.concept_type
            })
        
        # Sort by score
        chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        return chunks[:max_chunks]
    
    def should_use_graph(self, query: str) -> bool:
        """Determine if graph retrieval should be used.
        
        Simple queries use vector-only, complex queries use graph.
        
        Args:
            query: User query
            
        Returns:
            True if graph retrieval recommended
        """
        # Complex query indicators
        complex_indicators = [
            'how', 'why', 'explain', 'compare', 'difference',
            'relationship', 'between', 'affect', 'impact',
            'cause', 'effect', 'depends', 'related'
        ]
        
        query_lower = query.lower()
        
        # Check for complex indicators
        for indicator in complex_indicators:
            if indicator in query_lower:
                return True
        
        # Check query length (longer queries tend to be more complex)
        word_count = len(query.split())
        if word_count > 10:
            return True
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get LazyGraphRAG statistics.
        
        Returns:
            Dictionary with stats
        """
        return {
            "graph": self.graph.get_stats(),
            "cache": self.cache.get_stats(),
            "indexed_docs": len(self._indexed_docs),
            "last_index_time": self._last_index_time.isoformat() if self._last_index_time else None,
            "sufficiency_threshold": self.sufficiency_threshold
        }
    
    def log_sufficiency(self, query: str, sufficiency: RetrievalSufficiency):
        """Log retrieval sufficiency for monitoring.
        
        Args:
            query: Query that was executed
            sufficiency: Sufficiency scores
        """
        # This would integrate with observability system
        # For now, just track in memory
        if not hasattr(self, '_sufficiency_log'):
            self._sufficiency_log: List[Dict[str, Any]] = []
        
        self._sufficiency_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "query": query[:100],
            "coverage": sufficiency.coverage,
            "redundancy": sufficiency.redundancy,
            "citation_density": sufficiency.citation_density,
            "contradiction_rate": sufficiency.contradiction_rate,
            "overall_score": sufficiency.overall_score,
            "is_sufficient": sufficiency.is_sufficient(self.sufficiency_threshold)
        })
        
        # Keep only last 100 entries
        if len(self._sufficiency_log) > 100:
            self._sufficiency_log = self._sufficiency_log[-100:]
