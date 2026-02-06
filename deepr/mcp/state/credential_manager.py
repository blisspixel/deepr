"""Credential manager for gated content access.

Manages credentials for accessing paywalled or authenticated content
during research, with secure storage and elicitation support.

Usage:
    from deepr.mcp.state.credential_manager import CredentialManager

    manager = CredentialManager()

    # Store a credential
    cred = await manager.store_credential(
        domain="example.com",
        type="api_key",
        value="sk-xxx",
        expires_at=datetime.now() + timedelta(hours=24)
    )

    # Get credential for a URL
    cred = await manager.get_credential_for_url("https://example.com/api/data")

    # Elicit credential from user
    cred = await manager.elicit_credential(
        url="https://paywall.com/article",
        handler=elicitation_handler,
        reason="Article is behind paywall"
    )
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from deepr.mcp.state.elicitation_router import ElicitationHandler, ElicitationRequest


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


# Default database path
DEFAULT_DB_PATH = Path("data/credentials.db")

# Encryption key environment variable (would use proper secrets in production)
ENCRYPTION_KEY_ENV = "DEEPR_CREDENTIAL_KEY"


class CredentialType(Enum):
    """Types of credentials."""

    API_KEY = "api_key"
    SESSION_COOKIE = "session_cookie"
    BEARER_TOKEN = "bearer_token"
    BASIC_AUTH = "basic_auth"
    OAUTH_TOKEN = "oauth_token"


@dataclass
class GatedCredential:
    """A credential for accessing gated content."""

    id: str
    domain: str
    credential_type: CredentialType
    value_hash: str  # Hashed value for storage
    expires_at: Optional[datetime]
    created_at: datetime
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Transient field - not persisted
    _value: Optional[str] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain,
            "credential_type": self.credential_type.value,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "use_count": self.use_count,
            "is_expired": self.is_expired,
        }

    @property
    def is_expired(self) -> bool:
        """Check if credential has expired."""
        if self.expires_at is None:
            return False
        return _utc_now() > self.expires_at

    @property
    def value(self) -> Optional[str]:
        """Get credential value (if available in memory)."""
        return self._value

    @classmethod
    def from_row(
        cls,
        row: tuple,
        decrypted_value: Optional[str] = None,
    ) -> "GatedCredential":
        """Create from database row."""
        (id, domain, cred_type, value_hash, expires_at, created_at, last_used_at, use_count, metadata_json) = row

        cred = cls(
            id=id,
            domain=domain,
            credential_type=CredentialType(cred_type),
            value_hash=value_hash,
            expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
            created_at=datetime.fromisoformat(created_at),
            last_used_at=datetime.fromisoformat(last_used_at) if last_used_at else None,
            use_count=use_count,
            metadata=json.loads(metadata_json) if metadata_json else {},
        )
        cred._value = decrypted_value
        return cred


class CredentialManager:
    """Manages credentials for gated content access.

    Features:
    - Secure storage with hashing
    - Domain-based lookup
    - Expiration handling
    - Usage tracking
    - Elicitation integration

    Attributes:
        db_path: Path to SQLite database
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
    ):
        """Initialize the credential manager.

        Args:
            db_path: Path to database (default: data/credentials.db)
        """
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

        # In-memory credential cache (values only stored temporarily)
        self._value_cache: Dict[str, str] = {}

    def _create_tables(self):
        """Create database tables."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS credentials (
                id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                credential_type TEXT NOT NULL,
                value_hash TEXT NOT NULL,
                value_encrypted TEXT,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                use_count INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_creds_domain ON credentials(domain);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_creds_domain_type ON credentials(domain, credential_type);
        """)
        self._conn.commit()

    async def store_credential(
        self,
        domain: str,
        credential_type: CredentialType,
        value: str,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GatedCredential:
        """Store a credential.

        Args:
            domain: Domain the credential is for
            credential_type: Type of credential
            value: Credential value (will be hashed for storage)
            expires_at: Optional expiration time
            metadata: Optional additional metadata

        Returns:
            Stored GatedCredential
        """
        # Normalize domain
        domain = self._normalize_domain(domain)

        # Generate ID and hash
        cred_id = f"cred_{hashlib.md5(f'{domain}:{credential_type.value}'.encode()).hexdigest()[:12]}"
        value_hash = self._hash_value(value)

        now = _utc_now()
        metadata = metadata or {}

        # Store in database
        self._conn.execute(
            """INSERT OR REPLACE INTO credentials
               (id, domain, credential_type, value_hash, expires_at, created_at, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                cred_id,
                domain,
                credential_type.value,
                value_hash,
                expires_at.isoformat() if expires_at else None,
                now.isoformat(),
                json.dumps(metadata),
            ),
        )
        self._conn.commit()

        # Cache value temporarily
        self._value_cache[cred_id] = value

        cred = GatedCredential(
            id=cred_id,
            domain=domain,
            credential_type=credential_type,
            value_hash=value_hash,
            expires_at=expires_at,
            created_at=now,
            metadata=metadata,
        )
        cred._value = value

        return cred

    async def get_credential(
        self,
        domain: str,
        credential_type: Optional[CredentialType] = None,
    ) -> Optional[GatedCredential]:
        """Get a credential for a domain.

        Args:
            domain: Domain to get credential for
            credential_type: Optional specific type

        Returns:
            GatedCredential or None if not found
        """
        domain = self._normalize_domain(domain)

        if credential_type:
            row = self._conn.execute(
                """SELECT id, domain, credential_type, value_hash, expires_at,
                          created_at, last_used_at, use_count, metadata_json
                   FROM credentials
                   WHERE domain = ? AND credential_type = ?""",
                (domain, credential_type.value),
            ).fetchone()
        else:
            row = self._conn.execute(
                """SELECT id, domain, credential_type, value_hash, expires_at,
                          created_at, last_used_at, use_count, metadata_json
                   FROM credentials
                   WHERE domain = ?
                   ORDER BY created_at DESC
                   LIMIT 1""",
                (domain,),
            ).fetchone()

        if not row:
            return None

        cred_id = row[0]
        cached_value = self._value_cache.get(cred_id)

        cred = GatedCredential.from_row(row, cached_value)

        # Check expiration
        if cred.is_expired:
            await self.delete_credential(cred_id)
            return None

        return cred

    async def get_credential_for_url(
        self,
        url: str,
    ) -> Optional[GatedCredential]:
        """Get a credential for a URL.

        Args:
            url: URL to get credential for

        Returns:
            GatedCredential or None if not found
        """
        parsed = urlparse(url)
        domain = parsed.netloc

        # Try exact domain match first
        cred = await self.get_credential(domain)
        if cred:
            return cred

        # Try parent domain
        parts = domain.split(".")
        if len(parts) > 2:
            parent = ".".join(parts[-2:])
            cred = await self.get_credential(parent)
            if cred:
                return cred

        return None

    async def record_usage(
        self,
        credential_id: str,
    ) -> bool:
        """Record credential usage.

        Args:
            credential_id: Credential ID

        Returns:
            True if recorded, False if not found
        """
        now = _utc_now()

        cursor = self._conn.execute(
            """UPDATE credentials
               SET last_used_at = ?, use_count = use_count + 1
               WHERE id = ?""",
            (now.isoformat(), credential_id),
        )
        self._conn.commit()

        return cursor.rowcount > 0

    async def delete_credential(
        self,
        credential_id: str,
    ) -> bool:
        """Delete a credential.

        Args:
            credential_id: Credential ID

        Returns:
            True if deleted, False if not found
        """
        cursor = self._conn.execute("DELETE FROM credentials WHERE id = ?", (credential_id,))
        self._conn.commit()

        # Clear from cache
        self._value_cache.pop(credential_id, None)

        return cursor.rowcount > 0

    async def elicit_credential(
        self,
        url: str,
        handler: ElicitationHandler,
        reason: str,
        credential_type: CredentialType = CredentialType.SESSION_COOKIE,
        timeout_seconds: int = 300,
    ) -> Optional[GatedCredential]:
        """Elicit a credential from the user.

        Args:
            url: URL requiring credential
            handler: Elicitation handler function
            reason: Reason for requesting credential
            credential_type: Expected credential type
            timeout_seconds: Timeout for user response

        Returns:
            GatedCredential if user provided one, None otherwise
        """
        import uuid

        domain = self._normalize_domain(urlparse(url).netloc)

        # Create elicitation request
        request = ElicitationRequest(
            id=f"cred_elicit_{uuid.uuid4().hex[:8]}",
            message=self._build_credential_message(url, reason, credential_type),
            schema=self._build_credential_schema(credential_type),
            timeout_seconds=timeout_seconds,
            context={
                "url": url,
                "domain": domain,
                "credential_type": credential_type.value,
            },
        )

        # Call handler
        try:
            response = await handler(request)

            if not response:
                return None

            value = response.get("value") or response.get("credential")
            if not value:
                return None

            # Determine expiration
            expires_in = response.get("expires_in_hours", 24)
            expires_at = _utc_now() + timedelta(hours=expires_in)

            # Store credential
            return await self.store_credential(
                domain=domain,
                credential_type=credential_type,
                value=value,
                expires_at=expires_at,
                metadata={"elicited_for_url": url},
            )

        except Exception:
            return None

    async def list_credentials(
        self,
        include_expired: bool = False,
    ) -> List[GatedCredential]:
        """List all credentials.

        Args:
            include_expired: Include expired credentials

        Returns:
            List of GatedCredential objects
        """
        rows = self._conn.execute(
            """SELECT id, domain, credential_type, value_hash, expires_at,
                      created_at, last_used_at, use_count, metadata_json
               FROM credentials
               ORDER BY created_at DESC"""
        ).fetchall()

        credentials = []
        for row in rows:
            cred_id = row[0]
            cached_value = self._value_cache.get(cred_id)
            cred = GatedCredential.from_row(row, cached_value)

            if include_expired or not cred.is_expired:
                credentials.append(cred)

        return credentials

    async def cleanup_expired(self) -> int:
        """Delete expired credentials.

        Returns:
            Number of credentials deleted
        """
        now = _utc_now().isoformat()

        cursor = self._conn.execute(
            """DELETE FROM credentials
               WHERE expires_at IS NOT NULL AND expires_at < ?""",
            (now,),
        )
        self._conn.commit()

        return cursor.rowcount

    def _normalize_domain(self, domain: str) -> str:
        """Normalize a domain name.

        Args:
            domain: Domain to normalize

        Returns:
            Normalized domain
        """
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower()

    def _hash_value(self, value: str) -> str:
        """Hash a credential value.

        Args:
            value: Value to hash

        Returns:
            Hashed value
        """
        return hashlib.sha256(value.encode()).hexdigest()

    def _build_credential_message(
        self,
        url: str,
        reason: str,
        credential_type: CredentialType,
    ) -> str:
        """Build message for credential elicitation.

        Args:
            url: URL requiring credential
            reason: Reason for request
            credential_type: Type of credential needed

        Returns:
            Message string
        """
        type_instructions = {
            CredentialType.API_KEY: "Please provide your API key for this service.",
            CredentialType.SESSION_COOKIE: "Please provide a session cookie value.",
            CredentialType.BEARER_TOKEN: "Please provide a bearer token.",
            CredentialType.BASIC_AUTH: "Please provide username:password.",
            CredentialType.OAUTH_TOKEN: "Please provide your OAuth access token.",
        }

        return (
            f"Credential required to access content.\n\n"
            f"URL: {url}\n"
            f"Reason: {reason}\n\n"
            f"{type_instructions.get(credential_type, 'Please provide credentials.')}\n\n"
            f"The credential will be securely stored and automatically used for future requests to this domain."
        )

    def _build_credential_schema(
        self,
        credential_type: CredentialType,
    ) -> Dict[str, Any]:
        """Build JSON schema for credential input.

        Args:
            credential_type: Type of credential

        Returns:
            JSON schema dict
        """
        return {
            "type": "object",
            "properties": {
                "value": {
                    "type": "string",
                    "description": f"The {credential_type.value} value",
                },
                "expires_in_hours": {
                    "type": "number",
                    "description": "How long the credential is valid (hours)",
                    "default": 24,
                    "minimum": 1,
                    "maximum": 720,  # 30 days max
                },
            },
            "required": ["value"],
        }

    def close(self):
        """Close database connection."""
        self._conn.close()
