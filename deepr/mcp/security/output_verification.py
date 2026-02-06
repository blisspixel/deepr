"""Output verification for MCP tool responses.

Provides hash-based verification for tool outputs to ensure
integrity and enable audit trails.

Usage:
    from deepr.mcp.security.output_verification import OutputVerifier

    verifier = OutputVerifier()

    # Record a tool output
    verified = verifier.record_output("web_search", {"results": [...]})

    # Verify the output later
    result = verifier.verify_output(verified.id, {"results": [...]})

    # Get verification chain for a job
    chain = verifier.get_verification_chain("job123")
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


# Default database path
DEFAULT_DB_PATH = Path("data/output_verification.db")


@dataclass
class VerifiedOutput:
    """A verified tool output with hash."""

    id: str
    job_id: Optional[str]
    tool_name: str
    content_hash: str
    timestamp: datetime
    is_verified: bool = True
    verification_error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "tool_name": self.tool_name,
            "content_hash": self.content_hash,
            "timestamp": self.timestamp.isoformat(),
            "is_verified": self.is_verified,
            "verification_error": self.verification_error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_row(cls, row: tuple) -> "VerifiedOutput":
        """Create from database row."""
        (id, job_id, tool_name, content_hash, timestamp, is_verified, verification_error, metadata_json) = row

        return cls(
            id=id,
            job_id=job_id,
            tool_name=tool_name,
            content_hash=content_hash,
            timestamp=datetime.fromisoformat(timestamp),
            is_verified=bool(is_verified),
            verification_error=verification_error,
            metadata=json.loads(metadata_json) if metadata_json else {},
        )


@dataclass
class VerificationChainEntry:
    """An entry in the verification chain."""

    output_id: str
    previous_hash: Optional[str]
    content_hash: str
    chain_hash: str
    sequence: int
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_id": self.output_id,
            "previous_hash": self.previous_hash,
            "content_hash": self.content_hash,
            "chain_hash": self.chain_hash,
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat(),
        }


class OutputVerifier:
    """Verifies and records tool outputs for audit.

    Creates a hash chain of outputs for tamper detection.

    Attributes:
        db_path: Path to SQLite database
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
    ):
        """Initialize the verifier.

        Args:
            db_path: Path to database (default: data/output_verification.db)
        """
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

        # Chain tracking per job
        self._chain_heads: dict[str, str] = {}  # job_id -> last chain_hash

    def _create_tables(self):
        """Create database tables."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS verified_outputs (
                id TEXT PRIMARY KEY,
                job_id TEXT,
                tool_name TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                is_verified INTEGER NOT NULL DEFAULT 1,
                verification_error TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_outputs_job ON verified_outputs(job_id);
            CREATE INDEX IF NOT EXISTS idx_outputs_tool ON verified_outputs(tool_name);

            CREATE TABLE IF NOT EXISTS verification_chain (
                output_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                previous_hash TEXT,
                content_hash TEXT NOT NULL,
                chain_hash TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (output_id) REFERENCES verified_outputs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chain_job ON verification_chain(job_id);
        """)
        self._conn.commit()

    def record_output(
        self,
        tool_name: str,
        content: Any,
        job_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> VerifiedOutput:
        """Record a tool output with hash verification.

        Args:
            tool_name: Name of the tool that produced output
            content: Output content (will be JSON serialized for hashing)
            job_id: Optional job ID for chain tracking
            metadata: Optional additional metadata

        Returns:
            VerifiedOutput with hash
        """
        import secrets

        now = _utc_now()
        content_hash = self._hash_content(content)

        # Generate output ID with random component for uniqueness
        random_suffix = secrets.token_hex(4)
        output_id = f"out_{hashlib.md5(f'{tool_name}:{content_hash}:{now.isoformat()}:{random_suffix}'.encode()).hexdigest()[:12]}"

        output = VerifiedOutput(
            id=output_id,
            job_id=job_id,
            tool_name=tool_name,
            content_hash=content_hash,
            timestamp=now,
            metadata=metadata or {},
        )

        # Store in database
        self._conn.execute(
            """INSERT INTO verified_outputs
               (id, job_id, tool_name, content_hash, timestamp, is_verified, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                output.id,
                output.job_id,
                output.tool_name,
                output.content_hash,
                output.timestamp.isoformat(),
                1,
                json.dumps(output.metadata),
            ),
        )

        # Add to chain if job_id provided
        if job_id:
            self._add_to_chain(output)

        self._conn.commit()
        return output

    def verify_output(
        self,
        output_id: str,
        content: Any,
    ) -> VerifiedOutput:
        """Verify that content matches recorded output.

        Args:
            output_id: ID of recorded output
            content: Content to verify

        Returns:
            VerifiedOutput with verification result
        """
        # Get recorded output
        row = self._conn.execute(
            """SELECT id, job_id, tool_name, content_hash, timestamp,
                      is_verified, verification_error, metadata_json
               FROM verified_outputs WHERE id = ?""",
            (output_id,),
        ).fetchone()

        if not row:
            return VerifiedOutput(
                id=output_id,
                job_id=None,
                tool_name="unknown",
                content_hash="",
                timestamp=_utc_now(),
                is_verified=False,
                verification_error="Output not found",
            )

        output = VerifiedOutput.from_row(row)

        # Compare hashes
        content_hash = self._hash_content(content)

        if content_hash != output.content_hash:
            output.is_verified = False
            output.verification_error = "Content hash mismatch"

            # Update in database
            self._conn.execute(
                """UPDATE verified_outputs
                   SET is_verified = 0, verification_error = ?
                   WHERE id = ?""",
                (output.verification_error, output_id),
            )
            self._conn.commit()

        return output

    def get_verification_chain(
        self,
        job_id: str,
    ) -> list[VerificationChainEntry]:
        """Get the verification chain for a job.

        Args:
            job_id: Job ID

        Returns:
            List of VerificationChainEntry in order
        """
        rows = self._conn.execute(
            """SELECT output_id, previous_hash, content_hash, chain_hash, sequence, timestamp
               FROM verification_chain
               WHERE job_id = ?
               ORDER BY sequence""",
            (job_id,),
        ).fetchall()

        entries = []
        for row in rows:
            output_id, previous_hash, content_hash, chain_hash, sequence, timestamp = row
            entries.append(
                VerificationChainEntry(
                    output_id=output_id,
                    previous_hash=previous_hash,
                    content_hash=content_hash,
                    chain_hash=chain_hash,
                    sequence=sequence,
                    timestamp=datetime.fromisoformat(timestamp),
                )
            )

        return entries

    def verify_chain_integrity(
        self,
        job_id: str,
    ) -> dict:
        """Verify the integrity of a job's verification chain.

        Args:
            job_id: Job ID

        Returns:
            Dict with verification results
        """
        chain = self.get_verification_chain(job_id)

        if not chain:
            return {
                "valid": True,
                "error": None,
                "chain_length": 0,
            }

        # Verify chain links
        for i, entry in enumerate(chain):
            if i == 0:
                # First entry should have no previous hash
                if entry.previous_hash is not None:
                    return {
                        "valid": False,
                        "error": "First chain entry has unexpected previous_hash",
                        "entry_sequence": entry.sequence,
                    }
            else:
                # Previous hash should match prior entry's chain_hash
                expected_previous = chain[i - 1].chain_hash
                if entry.previous_hash != expected_previous:
                    return {
                        "valid": False,
                        "error": f"Chain break at sequence {entry.sequence}",
                        "entry_sequence": entry.sequence,
                    }

            # Verify chain_hash computation
            computed = self._compute_chain_hash(
                entry.content_hash,
                entry.previous_hash,
            )
            if computed != entry.chain_hash:
                return {
                    "valid": False,
                    "error": f"Chain hash mismatch at sequence {entry.sequence}",
                    "entry_sequence": entry.sequence,
                }

        return {
            "valid": True,
            "error": None,
            "chain_length": len(chain),
        }

    def get_output(
        self,
        output_id: str,
    ) -> Optional[VerifiedOutput]:
        """Get a verified output by ID.

        Args:
            output_id: Output ID

        Returns:
            VerifiedOutput or None
        """
        row = self._conn.execute(
            """SELECT id, job_id, tool_name, content_hash, timestamp,
                      is_verified, verification_error, metadata_json
               FROM verified_outputs WHERE id = ?""",
            (output_id,),
        ).fetchone()

        if not row:
            return None

        return VerifiedOutput.from_row(row)

    def get_outputs_for_job(
        self,
        job_id: str,
    ) -> list[VerifiedOutput]:
        """Get all verified outputs for a job.

        Args:
            job_id: Job ID

        Returns:
            List of VerifiedOutput objects
        """
        rows = self._conn.execute(
            """SELECT id, job_id, tool_name, content_hash, timestamp,
                      is_verified, verification_error, metadata_json
               FROM verified_outputs
               WHERE job_id = ?
               ORDER BY timestamp""",
            (job_id,),
        ).fetchall()

        return [VerifiedOutput.from_row(row) for row in rows]

    def get_stats(
        self,
        job_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get verification statistics.

        Args:
            job_id: Optional job ID filter

        Returns:
            Statistics dictionary
        """
        if job_id:
            row = self._conn.execute(
                """SELECT COUNT(*), SUM(CASE WHEN is_verified = 1 THEN 1 ELSE 0 END)
                   FROM verified_outputs WHERE job_id = ?""",
                (job_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                """SELECT COUNT(*), SUM(CASE WHEN is_verified = 1 THEN 1 ELSE 0 END)
                   FROM verified_outputs"""
            ).fetchone()

        total, verified = row
        total = total or 0
        verified = verified or 0

        return {
            "total_outputs": total,
            "verified_outputs": verified,
            "failed_verification": total - verified,
            "verification_rate": verified / total if total > 0 else 1.0,
        }

    def _hash_content(self, content: Any) -> str:
        """Compute hash of content.

        Args:
            content: Content to hash

        Returns:
            SHA256 hash string
        """
        # Serialize to JSON with consistent formatting
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
        else:
            content_str = str(content)

        return hashlib.sha256(content_str.encode("utf-8")).hexdigest()

    def _compute_chain_hash(
        self,
        content_hash: str,
        previous_hash: Optional[str],
    ) -> str:
        """Compute chain hash.

        Args:
            content_hash: Current content hash
            previous_hash: Previous chain hash (or None for first)

        Returns:
            Chain hash
        """
        data = f"{content_hash}|{previous_hash or 'genesis'}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _add_to_chain(self, output: VerifiedOutput):
        """Add output to verification chain.

        Args:
            output: VerifiedOutput to add
        """
        job_id = output.job_id
        if not job_id:
            return

        # Get previous chain hash
        previous_hash = self._chain_heads.get(job_id)

        # Get next sequence number
        row = self._conn.execute("SELECT MAX(sequence) FROM verification_chain WHERE job_id = ?", (job_id,)).fetchone()
        sequence = (row[0] or 0) + 1

        # Compute chain hash
        chain_hash = self._compute_chain_hash(output.content_hash, previous_hash)

        # Store chain entry
        self._conn.execute(
            """INSERT INTO verification_chain
               (output_id, job_id, previous_hash, content_hash, chain_hash, sequence, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                output.id,
                job_id,
                previous_hash,
                output.content_hash,
                chain_hash,
                sequence,
                output.timestamp.isoformat(),
            ),
        )

        # Update chain head
        self._chain_heads[job_id] = chain_hash

    def close(self):
        """Close database connection."""
        self._conn.close()
