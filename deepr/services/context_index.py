"""Context index for semantic search across research reports.

Provides embedding-based similarity search to find related prior research.
Uses SQLite for metadata storage and numpy for embedding vectors.
"""

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A search result from the context index."""

    report_id: str
    job_id: str
    prompt: str
    created_at: datetime
    similarity: float
    report_path: Path
    model: Optional[str] = None
    summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "report_id": self.report_id,
            "job_id": self.job_id,
            "prompt": self.prompt,
            "created_at": self.created_at.isoformat(),
            "similarity": self.similarity,
            "report_path": str(self.report_path),
            "model": self.model,
            "summary": self.summary,
        }


class ContextIndex:
    """Index of research reports for semantic similarity search.

    Indexes report metadata and embeddings for fast similarity search.
    Enables finding related prior research before starting new queries.

    Storage:
        data/context_index.db - SQLite metadata
        data/context_embeddings.npy - Numpy embedding vectors
    """

    def __init__(self, data_dir: Optional[Path] = None, reports_dir: Optional[Path] = None):
        """Initialize context index.

        Args:
            data_dir: Directory for index storage (default: data/)
            reports_dir: Directory containing reports (default: reports/)
        """
        self.data_dir = Path(data_dir) if data_dir else Path("data")
        self.reports_dir = Path(reports_dir) if reports_dir else Path("reports")

        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.data_dir / "context_index.db"
        self.embeddings_path = self.data_dir / "context_embeddings.npy"

        self._init_db()
        self._load_embeddings()

    def _init_db(self):
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                prompt TEXT NOT NULL,
                model TEXT,
                created_at TEXT NOT NULL,
                report_path TEXT NOT NULL,
                summary TEXT,
                embedding_idx INTEGER,
                indexed_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at
            ON reports(created_at DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_id
            ON reports(job_id)
        """)

        # FTS5 for keyword search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS reports_fts USING fts5(
                report_id,
                prompt,
                summary,
                content='reports',
                content_rowid='rowid'
            )
        """)

        conn.commit()
        conn.close()

    def _load_embeddings(self):
        """Load embeddings from disk."""
        if self.embeddings_path.exists():
            self.embeddings = np.load(self.embeddings_path)
        else:
            self.embeddings = None

    def _save_embeddings(self):
        """Save embeddings to disk."""
        if self.embeddings is not None:
            np.save(self.embeddings_path, self.embeddings)

    @staticmethod
    def _generate_report_id(job_id: str, created_at: str) -> str:
        """Generate unique report ID from job ID and timestamp."""
        content = f"{job_id}:{created_at}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _scan_reports(self) -> List[Dict[str, Any]]:
        """Scan reports directory for unindexed reports."""
        reports = []

        if not self.reports_dir.exists():
            return reports

        for report_dir in self.reports_dir.iterdir():
            if not report_dir.is_dir():
                continue

            metadata_path = report_dir / "metadata.json"
            if not metadata_path.exists():
                continue

            try:
                with open(metadata_path, encoding="utf-8") as f:
                    metadata = json.load(f)

                reports.append(
                    {
                        "metadata": metadata,
                        "path": report_dir,
                        "metadata_path": metadata_path,
                    }
                )
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read metadata from %s: %s", metadata_path, e)

        return reports

    def _is_indexed(self, job_id: str) -> bool:
        """Check if a job is already indexed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM reports WHERE job_id = ?", (job_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    async def index_reports(self, force: bool = False) -> int:
        """Index all unindexed reports.

        Args:
            force: Re-index all reports even if already indexed

        Returns:
            Number of reports indexed
        """
        from openai import AsyncOpenAI

        reports = self._scan_reports()
        if not reports:
            logger.info("No reports found to index")
            return 0

        # Filter to unindexed reports
        if not force:
            reports = [r for r in reports if not self._is_indexed(r["metadata"].get("job_id", ""))]

        if not reports:
            logger.info("All reports already indexed")
            return 0

        logger.info("Indexing %d reports", len(reports))

        client = AsyncOpenAI()
        new_embeddings = []
        indexed_count = 0

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for report_data in reports:
            metadata = report_data["metadata"]
            report_path = report_data["path"]

            job_id = metadata.get("job_id", "")
            prompt = metadata.get("prompt", "")
            model = metadata.get("model", "")
            created_at = metadata.get("created_at", datetime.now(timezone.utc).isoformat())

            if not prompt:
                continue

            report_id = self._generate_report_id(job_id, created_at)

            # Generate summary from report content
            report_file = report_path / "report.md"
            summary = ""
            if report_file.exists():
                try:
                    content = report_file.read_text(encoding="utf-8")
                    # Extract first 500 chars as summary
                    summary = content[:500].replace("\n", " ").strip()
                except OSError:
                    pass

            # Generate embedding
            try:
                embed_text = f"{prompt}\n\n{summary}"[:8000]
                response = await client.embeddings.create(model="text-embedding-3-small", input=embed_text)
                embedding = np.array(response.data[0].embedding)
                embedding_idx = len(new_embeddings)
                if self.embeddings is not None:
                    embedding_idx += len(self.embeddings)
                new_embeddings.append(embedding)
            except Exception as e:
                logger.error("Failed to embed report %s: %s", job_id, e)
                embedding_idx = None

            # Insert into database
            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO reports
                    (report_id, job_id, prompt, model, created_at, report_path, summary, embedding_idx, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        report_id,
                        job_id,
                        prompt,
                        model,
                        created_at,
                        str(report_path),
                        summary,
                        embedding_idx,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

                # Update FTS index
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO reports_fts (report_id, prompt, summary)
                    VALUES (?, ?, ?)
                """,
                    (report_id, prompt, summary),
                )

                indexed_count += 1
            except sqlite3.Error as e:
                logger.error("Failed to index report %s: %s", job_id, e)

        conn.commit()
        conn.close()

        # Update embeddings
        if new_embeddings:
            new_embeddings_array = np.array(new_embeddings)
            if self.embeddings is None:
                self.embeddings = new_embeddings_array
            else:
                self.embeddings = np.vstack([self.embeddings, new_embeddings_array])
            self._save_embeddings()

        logger.info("Indexed %d reports", indexed_count)
        return indexed_count

    async def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.7,
        include_keyword: bool = True,
    ) -> List[SearchResult]:
        """Search for related reports.

        Args:
            query: Search query
            top_k: Maximum results to return
            threshold: Minimum similarity threshold (0-1)
            include_keyword: Also include keyword matches

        Returns:
            List of SearchResult objects sorted by relevance
        """
        results: Dict[str, SearchResult] = {}

        # Semantic search
        if self.embeddings is not None and len(self.embeddings) > 0:
            semantic_results = await self._semantic_search(query, top_k * 2, threshold)
            for r in semantic_results:
                results[r.report_id] = r

        # Keyword search (FTS5)
        if include_keyword:
            keyword_results = self._keyword_search(query, top_k)
            for r in keyword_results:
                if r.report_id not in results:
                    results[r.report_id] = r
                else:
                    # Boost score for results matching both
                    results[r.report_id].similarity = min(1.0, results[r.report_id].similarity + 0.1)

        # Sort by similarity and limit
        sorted_results = sorted(results.values(), key=lambda x: x.similarity, reverse=True)
        return sorted_results[:top_k]

    async def _semantic_search(self, query: str, top_k: int, threshold: float) -> List[SearchResult]:
        """Perform semantic similarity search."""
        from openai import AsyncOpenAI

        if self.embeddings is None or len(self.embeddings) == 0:
            return []

        # Embed query
        try:
            client = AsyncOpenAI()
            response = await client.embeddings.create(model="text-embedding-3-small", input=query)
            query_embedding = np.array(response.data[0].embedding)
        except Exception as e:
            logger.error("Failed to embed query: %s", e)
            return []

        # Cosine similarity
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        doc_norms = self.embeddings / np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        similarities = np.dot(doc_norms, query_norm)

        # Get top results above threshold
        top_indices = np.argsort(similarities)[::-1]

        results = []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        for idx in top_indices:
            if len(results) >= top_k:
                break

            similarity = float(similarities[idx])
            if similarity < threshold:
                continue

            # Find report with this embedding index
            cursor.execute("SELECT * FROM reports WHERE embedding_idx = ?", (int(idx),))
            row = cursor.fetchone()
            if not row:
                continue

            results.append(
                SearchResult(
                    report_id=row["report_id"],
                    job_id=row["job_id"],
                    prompt=row["prompt"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    similarity=similarity,
                    report_path=Path(row["report_path"]),
                    model=row["model"],
                    summary=row["summary"],
                )
            )

        conn.close()
        return results

    def _keyword_search(self, query: str, top_k: int) -> List[SearchResult]:
        """Perform keyword search using FTS5."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # FTS5 search
        try:
            cursor.execute(
                """
                SELECT r.*, bm25(reports_fts) as rank
                FROM reports_fts fts
                JOIN reports r ON fts.report_id = r.report_id
                WHERE reports_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """,
                (query, top_k),
            )
            rows = cursor.fetchall()
        except sqlite3.Error:
            # Fallback to LIKE search if FTS fails
            cursor.execute(
                """
                SELECT * FROM reports
                WHERE prompt LIKE ? OR summary LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (f"%{query}%", f"%{query}%", top_k),
            )
            rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append(
                SearchResult(
                    report_id=row["report_id"],
                    job_id=row["job_id"],
                    prompt=row["prompt"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    similarity=0.5,  # Fixed score for keyword matches
                    report_path=Path(row["report_path"]),
                    model=row["model"],
                    summary=row["summary"],
                )
            )

        conn.close()
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM reports")
        report_count = cursor.fetchone()[0]

        cursor.execute("SELECT MIN(created_at), MAX(created_at) FROM reports")
        date_range = cursor.fetchone()

        conn.close()

        return {
            "indexed_reports": report_count,
            "embedding_count": len(self.embeddings) if self.embeddings is not None else 0,
            "oldest_report": date_range[0] if date_range[0] else None,
            "newest_report": date_range[1] if date_range[1] else None,
            "db_path": str(self.db_path),
            "embeddings_path": str(self.embeddings_path),
        }

    def clear(self):
        """Clear the entire index."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reports")
        cursor.execute("DELETE FROM reports_fts")
        conn.commit()
        conn.close()

        self.embeddings = None
        if self.embeddings_path.exists():
            self.embeddings_path.unlink()

        logger.info("Context index cleared")

    async def find_related(
        self,
        prompt: str,
        exclude_job_id: Optional[str] = None,
        top_k: int = 3,
        threshold: float = 0.75,
    ) -> List[SearchResult]:
        """Find related prior research for a given prompt.

        This is used by context discovery (6.1) to automatically detect
        related research before starting a new job.

        Args:
            prompt: The new research prompt to find related research for
            exclude_job_id: Job ID to exclude (e.g., if resuming a job)
            top_k: Maximum related reports to return
            threshold: Minimum similarity threshold (higher = stricter)

        Returns:
            List of SearchResult objects for related prior research
        """
        # Search for related reports
        results = await self.search(
            query=prompt,
            top_k=top_k + 5,  # Fetch extra to filter
            threshold=threshold,
            include_keyword=True,
        )

        # Filter out the excluded job and any very old or low-quality matches
        filtered = []
        for result in results:
            # Skip if same job
            if exclude_job_id and result.job_id == exclude_job_id:
                continue

            # Skip if report path no longer exists
            if not result.report_path.exists():
                continue

            filtered.append(result)

            if len(filtered) >= top_k:
                break

        return filtered

    def get_report_by_job_id(self, job_id: str) -> Optional[SearchResult]:
        """Get a specific report by job ID.

        Used by --context flag (6.3) to fetch explicit context.

        Args:
            job_id: The job ID to look up (can be prefix)

        Returns:
            SearchResult if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Try exact match first, then prefix match
        cursor.execute("SELECT * FROM reports WHERE job_id = ? OR job_id LIKE ?", (job_id, f"{job_id}%"))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return SearchResult(
            report_id=row["report_id"],
            job_id=row["job_id"],
            prompt=row["prompt"],
            created_at=datetime.fromisoformat(row["created_at"]),
            similarity=1.0,  # Exact match
            report_path=Path(row["report_path"]),
            model=row["model"],
            summary=row["summary"],
        )

    def get_report_content(self, job_id: str, max_chars: int = 8000) -> Optional[str]:
        """Get the content of a report for context injection.

        Args:
            job_id: The job ID to get content for
            max_chars: Maximum characters to return (for token budget)

        Returns:
            Report content as string, or None if not found
        """
        result = self.get_report_by_job_id(job_id)
        if not result:
            return None

        report_file = result.report_path / "report.md"
        if not report_file.exists():
            return None

        try:
            content = report_file.read_text(encoding="utf-8")
            if len(content) > max_chars:
                # Truncate intelligently - try to end at a paragraph
                truncated = content[:max_chars]
                last_para = truncated.rfind("\n\n")
                if last_para > max_chars * 0.7:
                    truncated = truncated[:last_para]
                content = truncated + "\n\n[... truncated for context budget ...]"
            return content
        except OSError as e:
            logger.warning("Failed to read report content for %s: %s", job_id, e)
            return None

    def check_stale_context(self, job_id: str, max_age_days: int = 30) -> bool:
        """Check if a report is potentially stale.

        Used to warn users about using old context (6.3).

        Args:
            job_id: The job ID to check
            max_age_days: Maximum age in days before considered stale

        Returns:
            True if the report is older than max_age_days
        """
        result = self.get_report_by_job_id(job_id)
        if not result:
            return True  # Unknown = treat as stale

        age = datetime.now(timezone.utc) - result.created_at.replace(tzinfo=timezone.utc)
        return age.days > max_age_days
