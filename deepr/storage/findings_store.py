"""Persistent storage for research findings.

Offloads findings to persistent storage to manage memory during
long research sessions, with efficient retrieval by relevance.

Usage:
    from deepr.storage.findings_store import FindingsStore

    store = FindingsStore()

    # Store a finding
    stored = await store.store_finding(
        job_id="job123",
        phase=1,
        text="Key finding about topic X",
        metadata={"source": "https://example.com", "confidence": 0.85}
    )

    # Retrieve relevant findings
    findings = await store.retrieve_relevant(
        job_id="job123",
        query="topic X applications",
        top_k=5
    )
"""

import json
import sqlite3
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path
from collections import Counter
import math


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


# Default database path
DEFAULT_DB_PATH = Path("data/findings.db")


@dataclass
class StoredFinding:
    """A finding stored in persistent storage."""
    id: str
    job_id: str
    phase: int
    text: str
    confidence: float
    source: Optional[str]
    finding_type: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    tokens: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.tokens:
            self.tokens = self._tokenize(self.text)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenize text for search."""
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        return [t for t in text.split() if len(t) > 2]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "phase": self.phase,
            "text": self.text,
            "confidence": self.confidence,
            "source": self.source,
            "finding_type": self.finding_type,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_row(cls, row: tuple) -> "StoredFinding":
        """Create from database row."""
        (id, job_id, phase, text, confidence, source,
         finding_type, timestamp_str, metadata_json) = row

        return cls(
            id=id,
            job_id=job_id,
            phase=phase,
            text=text,
            confidence=confidence,
            source=source,
            finding_type=finding_type,
            timestamp=datetime.fromisoformat(timestamp_str),
            metadata=json.loads(metadata_json) if metadata_json else {},
        )


class FindingsStore:
    """Persistent storage for research findings.

    Uses SQLite for storage with simple TF-IDF-like retrieval
    for finding relevant findings.

    Attributes:
        db_path: Path to SQLite database
    """

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize the findings store.

        Args:
            db_path: Path to database file (default: data/findings.db)
        """
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

        # In-memory token index for fast retrieval
        self._token_index: Dict[str, Dict[str, int]] = {}  # token -> {finding_id: count}
        self._doc_lengths: Dict[str, int] = {}  # finding_id -> token count
        self._load_index()

    def _create_tables(self):
        """Create database tables."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS findings (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                phase INTEGER NOT NULL,
                text TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                source TEXT,
                finding_type TEXT NOT NULL DEFAULT 'fact',
                timestamp TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_findings_job ON findings(job_id);
            CREATE INDEX IF NOT EXISTS idx_findings_phase ON findings(job_id, phase);

            CREATE TABLE IF NOT EXISTS finding_tokens (
                finding_id TEXT NOT NULL,
                token TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (finding_id, token),
                FOREIGN KEY (finding_id) REFERENCES findings(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_tokens_token ON finding_tokens(token);
        """)
        self._conn.commit()

    def _load_index(self):
        """Load token index from database."""
        rows = self._conn.execute(
            "SELECT finding_id, token, count FROM finding_tokens"
        ).fetchall()

        for finding_id, token, count in rows:
            if token not in self._token_index:
                self._token_index[token] = {}
            self._token_index[token][finding_id] = count
            self._doc_lengths[finding_id] = self._doc_lengths.get(finding_id, 0) + count

    async def store_finding(
        self,
        job_id: str,
        phase: int,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        confidence: float = 0.5,
        source: Optional[str] = None,
        finding_type: str = "fact",
    ) -> StoredFinding:
        """Store a finding in persistent storage.

        Args:
            job_id: Job identifier
            phase: Research phase number
            text: Finding text
            metadata: Optional additional metadata
            confidence: Confidence score (0-1)
            source: Source URL or reference
            finding_type: Type of finding

        Returns:
            StoredFinding object
        """
        # Generate ID from content hash
        content_hash = hashlib.md5(f"{job_id}:{text}".encode()).hexdigest()[:16]
        finding_id = f"f_{content_hash}"

        timestamp = _utc_now()
        metadata = metadata or {}

        # Create finding object
        finding = StoredFinding(
            id=finding_id,
            job_id=job_id,
            phase=phase,
            text=text,
            confidence=confidence,
            source=source,
            finding_type=finding_type,
            timestamp=timestamp,
            metadata=metadata,
        )

        # Store in database
        self._conn.execute(
            """INSERT OR REPLACE INTO findings
               (id, job_id, phase, text, confidence, source, finding_type, timestamp, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                finding.id,
                finding.job_id,
                finding.phase,
                finding.text,
                finding.confidence,
                finding.source,
                finding.finding_type,
                finding.timestamp.isoformat(),
                json.dumps(finding.metadata),
            )
        )

        # Store tokens for search
        token_counts = Counter(finding.tokens)
        for token, count in token_counts.items():
            self._conn.execute(
                """INSERT OR REPLACE INTO finding_tokens
                   (finding_id, token, count)
                   VALUES (?, ?, ?)""",
                (finding.id, token, count)
            )

            # Update in-memory index
            if token not in self._token_index:
                self._token_index[token] = {}
            self._token_index[token][finding.id] = count

        self._doc_lengths[finding.id] = len(finding.tokens)
        self._conn.commit()

        return finding

    async def retrieve_relevant(
        self,
        job_id: str,
        query: str,
        top_k: int = 10,
        phase: Optional[int] = None,
        min_confidence: float = 0.0,
    ) -> List[StoredFinding]:
        """Retrieve findings relevant to a query.

        Uses TF-IDF-like scoring for relevance ranking.

        Args:
            job_id: Job to search within
            query: Search query
            top_k: Maximum findings to return
            phase: Optional phase filter
            min_confidence: Minimum confidence filter

        Returns:
            List of relevant StoredFinding objects
        """
        # Tokenize query
        query_tokens = StoredFinding._tokenize(query)

        if not query_tokens:
            return []

        # Get candidate findings
        candidates = await self._get_candidates(job_id, query_tokens, phase)

        if not candidates:
            return []

        # Score candidates using TF-IDF-like scoring
        scored = []
        total_docs = len(self._doc_lengths)

        for finding_id in candidates:
            score = self._calculate_relevance_score(
                finding_id, query_tokens, total_docs
            )
            scored.append((finding_id, score))

        # Sort by score
        scored.sort(key=lambda x: x[1], reverse=True)

        # Retrieve top findings
        result = []
        for finding_id, score in scored[:top_k]:
            finding = await self._get_finding(finding_id)
            if finding and finding.confidence >= min_confidence:
                result.append(finding)

        return result

    async def get_findings_by_phase(
        self,
        job_id: str,
        phase: int,
    ) -> List[StoredFinding]:
        """Get all findings for a specific phase.

        Args:
            job_id: Job identifier
            phase: Phase number

        Returns:
            List of findings
        """
        rows = self._conn.execute(
            """SELECT id, job_id, phase, text, confidence, source,
                      finding_type, timestamp, metadata_json
               FROM findings
               WHERE job_id = ? AND phase = ?
               ORDER BY timestamp""",
            (job_id, phase)
        ).fetchall()

        return [StoredFinding.from_row(row) for row in rows]

    async def get_all_findings(
        self,
        job_id: str,
    ) -> List[StoredFinding]:
        """Get all findings for a job.

        Args:
            job_id: Job identifier

        Returns:
            List of all findings
        """
        rows = self._conn.execute(
            """SELECT id, job_id, phase, text, confidence, source,
                      finding_type, timestamp, metadata_json
               FROM findings
               WHERE job_id = ?
               ORDER BY phase, timestamp""",
            (job_id,)
        ).fetchall()

        return [StoredFinding.from_row(row) for row in rows]

    async def delete_job_findings(
        self,
        job_id: str,
    ) -> int:
        """Delete all findings for a job.

        Args:
            job_id: Job identifier

        Returns:
            Number of findings deleted
        """
        # Get finding IDs for cleanup
        rows = self._conn.execute(
            "SELECT id FROM findings WHERE job_id = ?",
            (job_id,)
        ).fetchall()

        finding_ids = [row[0] for row in rows]

        # Delete tokens
        for finding_id in finding_ids:
            self._conn.execute(
                "DELETE FROM finding_tokens WHERE finding_id = ?",
                (finding_id,)
            )

            # Clean up in-memory index
            for token_findings in self._token_index.values():
                token_findings.pop(finding_id, None)
            self._doc_lengths.pop(finding_id, None)

        # Delete findings
        cursor = self._conn.execute(
            "DELETE FROM findings WHERE job_id = ?",
            (job_id,)
        )
        self._conn.commit()

        return cursor.rowcount

    async def get_stats(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        """Get storage statistics.

        Args:
            job_id: Optional job to filter to

        Returns:
            Statistics dictionary
        """
        if job_id:
            row = self._conn.execute(
                """SELECT COUNT(*), AVG(confidence), COUNT(DISTINCT phase)
                   FROM findings WHERE job_id = ?""",
                (job_id,)
            ).fetchone()
        else:
            row = self._conn.execute(
                """SELECT COUNT(*), AVG(confidence), COUNT(DISTINCT job_id)
                   FROM findings"""
            ).fetchone()

        count, avg_conf, distinct = row

        return {
            "total_findings": count or 0,
            "average_confidence": avg_conf or 0.0,
            "distinct_jobs_or_phases": distinct or 0,
            "unique_tokens": len(self._token_index),
            "indexed_documents": len(self._doc_lengths),
        }

    async def _get_candidates(
        self,
        job_id: str,
        query_tokens: List[str],
        phase: Optional[int],
    ) -> set:
        """Get candidate finding IDs for a query.

        Args:
            job_id: Job identifier
            query_tokens: Query tokens
            phase: Optional phase filter

        Returns:
            Set of candidate finding IDs
        """
        candidates = set()

        for token in query_tokens:
            if token in self._token_index:
                candidates.update(self._token_index[token].keys())

        # Filter to job and phase
        if phase is not None:
            rows = self._conn.execute(
                "SELECT id FROM findings WHERE job_id = ? AND phase = ?",
                (job_id, phase)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id FROM findings WHERE job_id = ?",
                (job_id,)
            ).fetchall()

        valid_ids = {row[0] for row in rows}
        return candidates & valid_ids

    def _calculate_relevance_score(
        self,
        finding_id: str,
        query_tokens: List[str],
        total_docs: int,
    ) -> float:
        """Calculate TF-IDF-like relevance score.

        Args:
            finding_id: Finding to score
            query_tokens: Query tokens
            total_docs: Total number of documents

        Returns:
            Relevance score
        """
        score = 0.0
        doc_length = self._doc_lengths.get(finding_id, 1)

        for token in query_tokens:
            if token not in self._token_index:
                continue

            token_findings = self._token_index[token]
            if finding_id not in token_findings:
                continue

            # Term frequency
            tf = token_findings[finding_id] / doc_length

            # Inverse document frequency
            doc_freq = len(token_findings)
            idf = math.log((total_docs + 1) / (doc_freq + 1))

            score += tf * idf

        return score

    async def _get_finding(self, finding_id: str) -> Optional[StoredFinding]:
        """Get a finding by ID.

        Args:
            finding_id: Finding identifier

        Returns:
            StoredFinding or None
        """
        row = self._conn.execute(
            """SELECT id, job_id, phase, text, confidence, source,
                      finding_type, timestamp, metadata_json
               FROM findings WHERE id = ?""",
            (finding_id,)
        ).fetchone()

        if not row:
            return None

        return StoredFinding.from_row(row)

    def close(self):
        """Close database connection."""
        self._conn.close()
