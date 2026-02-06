"""Knowledge consolidation for expert continuous self-improvement.

Implements knowledge consolidation features:
- Deduplication of similar beliefs
- Merging related knowledge entries
- Archiving outdated information

Usage:
    from deepr.experts.knowledge_consolidation import KnowledgeConsolidator

    consolidator = KnowledgeConsolidator(expert_name="quantum_expert")

    # Consolidate knowledge
    result = await consolidator.consolidate()
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


import hashlib
from typing import Any, Optional


@dataclass
class KnowledgeEntry:
    """A knowledge entry for consolidation.

    Attributes:
        id: Unique entry identifier
        content: Entry content
        source: Source of the knowledge
        created_at: When entry was created
        updated_at: When entry was last updated
        confidence: Confidence score (0-1)
        tags: Semantic tags
        is_archived: Whether entry is archived
    """

    content: str
    source: str = ""
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    confidence: float = 0.5
    tags: set[str] = field(default_factory=set)
    is_archived: bool = False
    id: str = field(default="")

    def __post_init__(self):
        if not self.id:
            content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:12]
            self.id = content_hash
        if isinstance(self.tags, list):
            self.tags = set(self.tags)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "confidence": self.confidence,
            "tags": list(self.tags),
            "is_archived": self.is_archived,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeEntry":
        return cls(
            id=data.get("id", ""),
            content=data["content"],
            source=data.get("source", ""),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if "updated_at" in data
            else datetime.now(timezone.utc),
            confidence=data.get("confidence", 0.5),
            tags=set(data.get("tags", [])),
            is_archived=data.get("is_archived", False),
        )


@dataclass
class ConsolidationResult:
    """Result of knowledge consolidation.

    Attributes:
        deduplicated: Number of entries deduplicated
        merged: Number of entries merged
        archived: Number of entries archived
        total_before: Total entries before consolidation
        total_after: Total entries after consolidation
        space_saved_bytes: Estimated space saved
        duration_seconds: Time taken for consolidation
    """

    deduplicated: int = 0
    merged: int = 0
    archived: int = 0
    total_before: int = 0
    total_after: int = 0
    space_saved_bytes: int = 0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "deduplicated": self.deduplicated,
            "merged": self.merged,
            "archived": self.archived,
            "total_before": self.total_before,
            "total_after": self.total_after,
            "space_saved_bytes": self.space_saved_bytes,
            "duration_seconds": self.duration_seconds,
        }


class KnowledgeConsolidator:
    """Consolidates expert knowledge for efficiency.

    Features:
    - Deduplication: Remove near-duplicate entries
    - Merging: Combine related entries
    - Archiving: Move outdated entries to archive

    Attributes:
        expert_name: Name of the expert
        storage_dir: Directory for knowledge storage
        similarity_threshold: Threshold for deduplication (0-1)
        archive_age_days: Days after which to archive
    """

    def __init__(
        self,
        expert_name: str,
        storage_dir: Optional[Path] = None,
        similarity_threshold: float = 0.85,
        archive_age_days: int = 180,
    ):
        """Initialize knowledge consolidator.

        Args:
            expert_name: Name of the expert
            storage_dir: Directory for knowledge storage
            similarity_threshold: Threshold for deduplication
            archive_age_days: Days after which to archive
        """
        self.expert_name = expert_name
        self.similarity_threshold = similarity_threshold
        self.archive_age_days = archive_age_days

        if storage_dir is None:
            storage_dir = Path("data/experts") / expert_name / "knowledge"
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Paths
        self.entries_path = self.storage_dir / "entries.json"
        self.archive_path = self.storage_dir / "archive.json"

        # Load entries
        self.entries: list[KnowledgeEntry] = []
        self.archived: list[KnowledgeEntry] = []
        self._load()

    async def consolidate(self) -> ConsolidationResult:
        """Run full knowledge consolidation.

        Returns:
            ConsolidationResult with statistics
        """
        start_time = datetime.now(timezone.utc)
        result = ConsolidationResult()
        result.total_before = len(self.entries)

        # Calculate initial size
        initial_size = self._estimate_size()

        # Step 1: Deduplicate
        dedup_count = self._deduplicate()
        result.deduplicated = dedup_count

        # Step 2: Merge related entries
        merge_count = self._merge_related()
        result.merged = merge_count

        # Step 3: Archive outdated
        archive_count = self._archive_outdated()
        result.archived = archive_count

        # Calculate final stats
        result.total_after = len(self.entries)
        final_size = self._estimate_size()
        result.space_saved_bytes = max(0, initial_size - final_size)
        result.duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Save changes
        self._save()

        return result

    def _deduplicate(self) -> int:
        """Remove near-duplicate entries.

        Returns:
            Number of entries removed
        """
        if len(self.entries) < 2:
            return 0

        removed = 0
        to_remove: set[str] = set()

        # Compare all pairs
        for i, entry1 in enumerate(self.entries):
            if entry1.id in to_remove:
                continue

            for entry2 in self.entries[i + 1 :]:
                if entry2.id in to_remove:
                    continue

                similarity = self._compute_similarity(entry1.content, entry2.content)

                if similarity >= self.similarity_threshold:
                    # Keep the one with higher confidence or more recent
                    if entry1.confidence > entry2.confidence:
                        to_remove.add(entry2.id)
                    elif entry2.confidence > entry1.confidence:
                        to_remove.add(entry1.id)
                    elif entry1.updated_at > entry2.updated_at:
                        to_remove.add(entry2.id)
                    else:
                        to_remove.add(entry1.id)

                    removed += 1

        # Remove duplicates
        self.entries = [e for e in self.entries if e.id not in to_remove]

        return removed

    def _merge_related(self) -> int:
        """Merge related knowledge entries.

        Returns:
            Number of entries merged
        """
        if len(self.entries) < 2:
            return 0

        merged = 0
        to_remove: set[str] = set()

        # Group by tags
        tag_groups: dict[str, list[KnowledgeEntry]] = {}
        for entry in self.entries:
            for tag in entry.tags:
                if tag not in tag_groups:
                    tag_groups[tag] = []
                tag_groups[tag].append(entry)

        # Merge entries with same tags and moderate similarity
        for tag, group in tag_groups.items():
            if len(group) < 2:
                continue

            # Sort by confidence (highest first)
            group.sort(key=lambda e: e.confidence, reverse=True)

            primary = group[0]

            for secondary in group[1:]:
                if secondary.id in to_remove:
                    continue

                similarity = self._compute_similarity(primary.content, secondary.content)

                # Merge if moderately similar (but not duplicate)
                if 0.5 <= similarity < self.similarity_threshold:
                    # Merge content
                    primary.content = self._merge_content(primary.content, secondary.content)
                    primary.confidence = max(primary.confidence, secondary.confidence)
                    primary.tags.update(secondary.tags)
                    primary.updated_at = datetime.now(timezone.utc)

                    to_remove.add(secondary.id)
                    merged += 1

        # Remove merged entries
        self.entries = [e for e in self.entries if e.id not in to_remove]

        return merged

    def _archive_outdated(self) -> int:
        """Archive outdated entries.

        Returns:
            Number of entries archived
        """
        now = datetime.now(timezone.utc)
        archived = 0
        to_archive: list[KnowledgeEntry] = []

        for entry in self.entries:
            age_days = (now - entry.updated_at).days

            if age_days > self.archive_age_days:
                entry.is_archived = True
                to_archive.append(entry)
                archived += 1

        # Move to archive
        self.archived.extend(to_archive)
        self.entries = [e for e in self.entries if not e.is_archived]

        return archived

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """Compute similarity between two texts.

        Uses Jaccard similarity on word sets.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-1)
        """
        words1 = set(self._tokenize(text1))
        words2 = set(self._tokenize(text2))

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words.

        Args:
            text: Text to tokenize

        Returns:
            List of words
        """
        # Simple tokenization
        words = re.findall(r"\b[a-zA-Z]+\b", text.lower())

        # Remove stopwords
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "can",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "and",
            "but",
            "or",
            "if",
            "this",
            "that",
            "these",
            "those",
            "it",
        }

        return [w for w in words if w not in stopwords and len(w) > 2]

    def _merge_content(self, primary: str, secondary: str) -> str:
        """Merge two content strings.

        Args:
            primary: Primary content (kept as base)
            secondary: Secondary content (additions merged)

        Returns:
            Merged content
        """
        # Simple merge: append unique sentences from secondary
        primary_sentences = set(s.strip() for s in primary.split(".") if s.strip())
        secondary_sentences = [s.strip() for s in secondary.split(".") if s.strip()]

        # Find unique sentences in secondary
        unique = [s for s in secondary_sentences if s not in primary_sentences]

        if unique:
            return primary + "\n\nAdditional: " + ". ".join(unique) + "."

        return primary

    def _estimate_size(self) -> int:
        """Estimate storage size of entries.

        Returns:
            Estimated size in bytes
        """
        total = 0
        for entry in self.entries:
            total += len(entry.content.encode("utf-8"))
            total += len(entry.source.encode("utf-8"))
            total += sum(len(t.encode("utf-8")) for t in entry.tags)
        return total

    def add_entry(self, entry: KnowledgeEntry):
        """Add a knowledge entry.

        Args:
            entry: Entry to add
        """
        self.entries.append(entry)

    def get_entries(self, include_archived: bool = False) -> list[KnowledgeEntry]:
        """Get all entries.

        Args:
            include_archived: Whether to include archived entries

        Returns:
            List of entries
        """
        if include_archived:
            return self.entries + self.archived
        return self.entries

    def get_stats(self) -> dict[str, Any]:
        """Get consolidation statistics.

        Returns:
            Dictionary with stats
        """
        return {
            "active_entries": len(self.entries),
            "archived_entries": len(self.archived),
            "total_entries": len(self.entries) + len(self.archived),
            "estimated_size_bytes": self._estimate_size(),
            "similarity_threshold": self.similarity_threshold,
            "archive_age_days": self.archive_age_days,
        }

    def _save(self):
        """Save entries to disk."""
        # Save active entries
        entries_data = [e.to_dict() for e in self.entries]
        with open(self.entries_path, "w", encoding="utf-8") as f:
            json.dump(entries_data, f, indent=2)

        # Save archived entries
        archive_data = [e.to_dict() for e in self.archived]
        with open(self.archive_path, "w", encoding="utf-8") as f:
            json.dump(archive_data, f, indent=2)

    def _load(self):
        """Load entries from disk."""
        # Load active entries
        if self.entries_path.exists():
            with open(self.entries_path, encoding="utf-8") as f:
                entries_data = json.load(f)
            self.entries = [KnowledgeEntry.from_dict(e) for e in entries_data]

        # Load archived entries
        if self.archive_path.exists():
            with open(self.archive_path, encoding="utf-8") as f:
                archive_data = json.load(f)
            self.archived = [KnowledgeEntry.from_dict(e) for e in archive_data]
