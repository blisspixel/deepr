"""Belief system for expert consciousness.

Implements belief objects with:
- Claim, confidence, evidence tracking
- Belief revision with conflict resolution
- Confidence decay over time
- Cross-expert knowledge sharing

Usage:
    from deepr.experts.beliefs import Belief, BeliefStore

    belief = Belief(
        claim="Python 3.12 supports pattern matching",
        confidence=0.95,
        evidence_refs=["doc_001", "doc_002"],
        domain="python"
    )

    store = BeliefStore(expert_name="python_expert")
    store.add_belief(belief)
"""

import json
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# A source *identifier* is a compact token (URL or namespaced id like
# ``report:<id>`` / ``doc_001``) with no whitespace. Free-text evidence
# excerpts (report quotes - which always contain spaces) are grounding, not
# independent origins, so they must not count toward source independence.
_URL_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)

if TYPE_CHECKING:
    from deepr.core.contracts import Claim


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class ConflictResolution(Enum):
    """Conflict resolution strategies."""

    NEWER_WINS = "newer_wins"
    HIGHER_CONFIDENCE = "higher_confidence"
    MERGE = "merge"
    ASK_USER = "ask_user"
    ADJUDICATE = "adjudicate"


@dataclass
class Belief:
    """A belief held by an expert.

    Attributes:
        claim: The belief statement
        confidence: Confidence level 0-1
        evidence_refs: References to supporting evidence
        domain: Knowledge domain
        created_at: When belief was formed
        updated_at: When belief was last updated
        contradictions_with: IDs of contradicting beliefs
        source_type: How belief was acquired
        decay_rate: Confidence decay rate per day
        history: History of belief changes
    """

    claim: str
    confidence: float
    evidence_refs: list[str] = field(default_factory=list)
    domain: str = ""
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    contradictions_with: list[str] = field(default_factory=list)
    source_type: str = "learned"  # learned, inferred, user_provided
    decay_rate: float = 0.01  # Per day
    history: list[dict[str, Any]] = field(default_factory=list)
    id: str = field(default="")
    # Provenance tier of the weakest source: "primary" (operator docs),
    # "secondary" (official / first-party tools), or "tertiary" (web / research
    # syntheses; the default, and the retroactive default for legacy beliefs).
    trust_class: str = "tertiary"
    # Cross-vendor maker-checker assurance (maker_checker.py): "cross_vendor" /
    # "same_vendor_fresh_context" / "unverified" (default; also could-not-verify).
    grounding_assurance: str = "unverified"
    # Usage salience (docs/design/belief-lifecycle.md): how often this
    # belief was load-bearing in an answer, bumped via record_retrieval -
    # and ONLY from surfaces that already mutate the expert; read-side
    # queries (validate, why, digest, contested, what-changed) stay pure.
    # Protective signal only: recent usage shields a belief from archival;
    # absence of usage never condemns one (read-only consumers leave no
    # trace by design).
    retrieval_count: int = 0
    last_retrieved_at: datetime | None = None

    def __post_init__(self):
        if not self.id:
            import hashlib

            content = f"{self.claim}:{self.domain}:{self.created_at.isoformat()}"
            self.id = hashlib.sha256(content.encode()).hexdigest()[:12]

    def _trust_ceiling(self) -> float:
        """Deterministic confidence cap from source trust (v2.15 evidence).

        Floors are computed at read time (like decay), so they apply
        retroactively and through every write path - absorb, sync, merge,
        adjudication. No model judgment can lift them; only new,
        better-sourced evidence can:

        - tertiary, single source: 0.60 (one web result cannot make a
          belief near-certain - also the deterministic backstop against
          ingestion-time prompt injection)
        - tertiary, two+ independent sources: 0.80
        - secondary/primary: uncapped (1.0)

        Independence counts distinct source *identifiers* (URLs by host, so a
        syndicated origin counts once; namespaced ids like ``report:<id>``),
        never free-text quote excerpts - absorb stores ``[f"report:{id}",
        *quotes]`` and the quotes ground one source, not new origins. Counting
        them would falsely lift a single-source belief to 0.80. Deterministic
        (a safety floor no model can lift) and fails safe toward 0.60.
        """
        if self.trust_class in ("primary", "secondary"):
            return 1.0
        return 0.80 if self._independent_source_count() >= 2 else 0.60

    def _independent_source_count(self) -> int:
        """Distinct independent source identifiers among ``evidence_refs``.

        Form-only and conservative: free-text excerpts (any ref containing
        whitespace - i.e. a quote) are skipped; URLs collapse to their host so
        the same origin counts once; remaining compact ids count by value.
        """
        keys: set[str] = set()
        for ref in self.evidence_refs:
            token = str(ref).strip()
            if not token or any(ch.isspace() for ch in token):
                continue  # a quote excerpt grounds one source; it is not a new origin
            if _URL_SCHEME_RE.match(token):
                host = (urlparse(token).netloc or "").lower().removeprefix("www.")
                keys.add(f"url:{host}" if host else token.lower())
            else:
                keys.add(token.lower())
        return len(keys)

    def get_current_confidence(self) -> float:
        """Get confidence with decay and the source-trust ceiling applied.

        Returns:
            Current confidence after decay, capped by trust class.
        """
        days_elapsed = (datetime.now(UTC) - self.updated_at).days
        decayed = self.confidence * math.exp(-self.decay_rate * days_elapsed)
        return max(0.0, min(self._trust_ceiling(), decayed))

    def update_confidence(self, new_confidence: float, reason: str = ""):
        """Update belief confidence.

        Args:
            new_confidence: New confidence value
            reason: Reason for update
        """
        self.history.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "old_confidence": self.confidence,
                "new_confidence": new_confidence,
                "reason": reason,
            }
        )
        self.confidence = new_confidence
        self.updated_at = datetime.now(UTC)

    def add_evidence(self, evidence_ref: str):
        """Add evidence reference.

        Args:
            evidence_ref: Reference to evidence
        """
        if evidence_ref not in self.evidence_refs:
            self.evidence_refs.append(evidence_ref)
            self.updated_at = datetime.now(UTC)

    def add_contradiction(self, belief_id: str):
        """Mark contradiction with another belief.

        Args:
            belief_id: ID of contradicting belief
        """
        if belief_id not in self.contradictions_with:
            self.contradictions_with.append(belief_id)

    def is_stale(self, threshold: float = 0.3) -> bool:
        """Check if belief is stale.

        Args:
            threshold: Confidence threshold for staleness

        Returns:
            True if current confidence below threshold
        """
        return self.get_current_confidence() < threshold

    def to_claim(self) -> "Claim":
        """Convert to canonical Claim type.

        Returns:
            Claim with confidence decay applied.
        """
        from deepr.core.contracts import Claim, Source, TrustClass

        trust = {
            "primary": TrustClass.PRIMARY,
            "secondary": TrustClass.SECONDARY,
        }.get(self.trust_class, TrustClass.TERTIARY)
        sources = [Source.create(title=ref, trust_class=trust) for ref in self.evidence_refs]
        return Claim(
            id=self.id,
            statement=self.claim,
            domain=self.domain,
            confidence=self.get_current_confidence(),
            sources=sources,
            created_at=self.created_at,
            updated_at=self.updated_at,
            contradicts=list(self.contradictions_with),
            tags=[self.source_type] if self.source_type else [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "claim": self.claim,
            "confidence": self.confidence,
            "evidence_refs": self.evidence_refs,
            "domain": self.domain,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "contradictions_with": self.contradictions_with,
            "source_type": self.source_type,
            "decay_rate": self.decay_rate,
            "history": self.history,
            "trust_class": self.trust_class,
            "grounding_assurance": self.grounding_assurance,
            "retrieval_count": self.retrieval_count,
            "last_retrieved_at": self.last_retrieved_at.isoformat() if self.last_retrieved_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Belief":
        return cls(
            id=data.get("id", ""),
            claim=data["claim"],
            confidence=data["confidence"],
            evidence_refs=data.get("evidence_refs", []),
            domain=data.get("domain", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(UTC),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(UTC),
            contradictions_with=data.get("contradictions_with", []),
            source_type=data.get("source_type", "learned"),
            decay_rate=data.get("decay_rate", 0.01),
            history=data.get("history", []),
            # Pre-floor beliefs default tertiary: retroactive honesty
            trust_class=data.get("trust_class", "tertiary"),
            grounding_assurance=data.get("grounding_assurance", "unverified"),
            retrieval_count=int(data.get("retrieval_count", 0) or 0),
            last_retrieved_at=(
                datetime.fromisoformat(data["last_retrieved_at"]) if data.get("last_retrieved_at") else None
            ),
        )


@dataclass
class BeliefChange:
    """Record of a belief change.

    Attributes:
        belief_id: ID of changed belief
        change_type: Type of change
        old_claim: Previous claim (if changed)
        new_claim: New claim
        old_confidence: Previous confidence
        new_confidence: New confidence
        reason: Reason for change
        evidence: Evidence that triggered change
        timestamp: When change occurred (record time: when the store
            learned about it)
        invalidated_at: Optional world-valid time - when the underlying
            fact stopped being true, as distinct from when the store
            retired it (bi-temporal semantics, Graphiti pattern; see
            docs/design/belief-lifecycle.md). Only meaningful on
            archived/revised events.
        snapshot: Full belief dict captured at archival, so an archive is
            reversible from the event log alone (restore_belief).
    """

    belief_id: str
    change_type: str  # created, updated, revised, archived
    new_claim: str
    new_confidence: float
    old_claim: str = ""
    old_confidence: float = 0.0
    reason: str = ""
    evidence: str = ""
    timestamp: datetime = field(default_factory=_utc_now)
    invalidated_at: datetime | None = None
    snapshot: dict[str, Any] | None = None

    def to_expression(self) -> str:
        """Generate natural language expression of change.

        Returns:
            Human-readable description of belief change
        """
        if self.change_type == "created":
            return f"I now believe that {self.new_claim} (confidence: {self.new_confidence:.0%})"

        if self.change_type == "revised" and self.old_claim:
            return (
                f"I used to think {self.old_claim}, "
                f"but now I believe {self.new_claim} "
                f"because {self.reason or 'new evidence'}"
            )

        if self.change_type == "updated":
            conf_change = self.new_confidence - self.old_confidence
            direction = "more" if conf_change > 0 else "less"
            return (
                f"I'm now {direction} confident that {self.new_claim} "
                f"({self.old_confidence:.0%} → {self.new_confidence:.0%})"
            )

        if self.change_type == "archived":
            return f"I no longer hold the belief that {self.old_claim}"

        return f"Belief updated: {self.new_claim}"

    def to_dict(self) -> dict[str, Any]:
        out = {
            "belief_id": self.belief_id,
            "change_type": self.change_type,
            "old_claim": self.old_claim,
            "new_claim": self.new_claim,
            "old_confidence": self.old_confidence,
            "new_confidence": self.new_confidence,
            "reason": self.reason,
            "evidence": self.evidence,
            "timestamp": self.timestamp.isoformat(),
        }
        # Optional bi-temporal/archival fields are emitted only when set,
        # keeping event-log lines lean and pre-change events byte-identical.
        if self.invalidated_at is not None:
            out["invalidated_at"] = self.invalidated_at.isoformat()
        if self.snapshot is not None:
            out["snapshot"] = self.snapshot
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BeliefChange":
        return cls(
            belief_id=data["belief_id"],
            change_type=data["change_type"],
            new_claim=data.get("new_claim", ""),
            new_confidence=float(data.get("new_confidence", 0.0)),
            old_claim=data.get("old_claim", ""),
            old_confidence=float(data.get("old_confidence", 0.0)),
            reason=data.get("reason", ""),
            evidence=data.get("evidence", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else _utc_now(),
            invalidated_at=(datetime.fromisoformat(data["invalidated_at"]) if data.get("invalidated_at") else None),
            snapshot=data.get("snapshot"),
        )


# Edge types for the typed belief graph (TKG step 2, see
# docs/design/temporal-knowledge-graph.md). "contradicts" is symmetric;
# the others are directed src -> dst.
EDGE_TYPES = ("supports", "contradicts", "enables", "derived_from")
_SYMMETRIC_EDGE_TYPES = ("contradicts",)

# Provenance string recorded on edges created by the one-time migration of
# legacy contradictions_with lists.
_MIGRATED_PROVENANCE = "migrated:contradictions_with"


@dataclass
class Edge:
    """A typed relationship between two beliefs.

    Provenance accumulates: re-asserting the same relationship from a new
    report adds provenance to the existing edge instead of duplicating it
    (the dedup policy from the TKG design doc).
    """

    src_id: str
    dst_id: str
    edge_type: str  # one of EDGE_TYPES
    provenance: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)

    def key(self) -> tuple[str, str, str]:
        """Canonical identity. Symmetric types sort endpoints so A-B == B-A."""
        if self.edge_type in _SYMMETRIC_EDGE_TYPES:
            lo, hi = sorted((self.src_id, self.dst_id))
            return (lo, hi, self.edge_type)
        return (self.src_id, self.dst_id, self.edge_type)

    def touches(self, belief_id: str) -> bool:
        return belief_id in (self.src_id, self.dst_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "src_id": self.src_id,
            "dst_id": self.dst_id,
            "edge_type": self.edge_type,
            "provenance": list(self.provenance),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Edge":
        return cls(
            src_id=data["src_id"],
            dst_id=data["dst_id"],
            edge_type=data["edge_type"],
            provenance=list(data.get("provenance", [])),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else _utc_now(),
        )


class BeliefStore:
    """Store and manage beliefs for an expert.

    Attributes:
        expert_name: Name of the expert
        beliefs: Dictionary of beliefs by ID
        domain_index: Index of beliefs by domain
        edges: Typed belief-graph edges keyed by canonical identity
        conflict_resolution: Default conflict resolution strategy
    """

    def __init__(
        self,
        expert_name: str,
        storage_dir: Path | None = None,
        conflict_resolution: ConflictResolution = ConflictResolution.HIGHER_CONFIDENCE,
    ):
        """Initialize belief store.

        Args:
            expert_name: Name of the expert
            storage_dir: Directory for storage
            conflict_resolution: Default conflict resolution strategy
        """
        self.expert_name = expert_name
        self.conflict_resolution = conflict_resolution

        if storage_dir is None:
            # Resolve through the one canonical resolver so beliefs land in the
            # SAME directory as the rest of the expert's state (profile, loop
            # runs, subscriptions). It slugifies + containment-checks the name,
            # so untrusted MCP args like ``../python_expert`` cannot escape the
            # experts root. (Previously this used the raw name and split one
            # expert across two directories - the bug `expert cleanup` repairs.)
            from deepr.experts.paths import canonical_expert_dir

            storage_dir = canonical_expert_dir(expert_name) / "beliefs"
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.storage_path = self.storage_dir / "beliefs.json"
        self.changes_path = self.storage_dir / "changes.json"
        # Append-only belief event log (TKG step 1): every change is kept here
        # while changes.json remains a capped legacy window.
        self.events_path = self.storage_dir / "events.jsonl"

        self.beliefs: dict[str, Belief] = {}
        self.domain_index: dict[str, set[str]] = {}
        self.changes: list[BeliefChange] = []
        self.edges: dict[tuple[str, str, str], Edge] = {}

        self._load()

    def add_edge(
        self,
        src_id: str,
        dst_id: str,
        edge_type: str,
        provenance: str = "",
        *,
        save: bool = True,
    ) -> Edge:
        """Record a typed edge between two beliefs (deduplicating by identity).

        Re-asserting an existing relationship appends new provenance to the
        existing edge. For ``contradicts`` edges the beliefs' legacy
        ``contradictions_with`` lists are kept in sync (both directions) so
        every existing reader keeps working during the migration window.
        """
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"Unknown edge type: {edge_type!r} (expected one of {EDGE_TYPES})")
        if src_id == dst_id:
            raise ValueError("An edge cannot connect a belief to itself")

        edge = Edge(src_id=src_id, dst_id=dst_id, edge_type=edge_type)
        existing = self.edges.get(edge.key())
        if existing is not None:
            if provenance and provenance not in existing.provenance:
                existing.provenance.append(provenance)
            edge = existing
        else:
            if provenance:
                edge.provenance.append(provenance)
            self.edges[edge.key()] = edge

        if edge_type == "contradicts":
            a, b = self.beliefs.get(src_id), self.beliefs.get(dst_id)
            if a is not None:
                a.add_contradiction(dst_id)
            if b is not None:
                b.add_contradiction(src_id)

        if save:
            self._save()
        return edge

    def edges_for(self, belief_id: str, edge_type: str | None = None) -> list[Edge]:
        """All edges touching a belief, optionally filtered by type."""
        return [
            e for e in self.edges.values() if e.touches(belief_id) and (edge_type is None or e.edge_type == edge_type)
        ]

    @property
    def has_event_log(self) -> bool:
        """True when the append-only event log exists (new-format stores)."""
        return self.events_path.exists()

    def _record_change(self, change: BeliefChange) -> None:
        """Record a belief change in both the legacy window and event log."""
        if change.timestamp.tzinfo is None:
            change.timestamp = change.timestamp.replace(tzinfo=UTC)
        if self.changes:
            latest = self.changes[-1].timestamp
            latest = latest if latest.tzinfo else latest.replace(tzinfo=UTC)
            change.timestamp = max(change.timestamp, latest + timedelta(microseconds=1))

        self.changes.append(change)
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(change.to_dict()) + "\n")

    def iter_events(self, since: datetime | None = None) -> list[BeliefChange]:
        """Read belief events from the append-only log, oldest first.

        Args:
            since: If given, only events strictly after this timestamp.

        Returns:
            All matching events (the log is unbounded, unlike ``changes``).
            Malformed lines are skipped with a warning, never fatal.
        """
        if since is not None and since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        events: list[BeliefChange] = []
        if not self.events_path.exists():
            return events
        with open(self.events_path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    change = BeliefChange.from_dict(json.loads(line))
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    logger.warning("Skipping malformed belief event (%s:%d): %s", self.events_path, line_no, exc)
                    continue
                ts = change.timestamp if change.timestamp.tzinfo else change.timestamp.replace(tzinfo=UTC)
                if since is not None and ts <= since:
                    continue
                events.append(change)
        return events

    def add_belief(
        self, belief: Belief, check_conflicts: bool = True, dedup: bool = True
    ) -> tuple[Belief, BeliefChange | None]:
        """Add a belief to the store.

        Args:
            belief: Belief to add
            check_conflicts: Whether to check for conflicts
            dedup: Merge into a lexically-similar existing belief. A caller that
                confirmed the candidate is a *distinct* fact passes dedup=False
                (the >0.7 overlap is a router, not a verdict; AGENTIC_BALANCE.md).

        Returns:
            Tuple of (added/updated belief, change record)
        """
        # Check for existing similar belief
        existing = self._find_similar(belief) if dedup else None

        if existing:
            # Resolve conflict
            return self._resolve_conflict(existing, belief)

        # Add belief first so add_edge can mirror contradictions_with
        self.beliefs[belief.id] = belief
        self._index_belief(belief)

        # Check for contradictions (typed edge + legacy field, via add_edge)
        if check_conflicts:
            contradictions = self._find_contradictions(belief)
            for contra in contradictions:
                self.add_edge(belief.id, contra.id, "contradicts", provenance="detected:add_belief", save=False)
            # Same-polarity related beliefs become supports edges - the
            # structure explain_belief walks (TKG steps 2/4)
            for related in self._find_related(belief):
                self.add_edge(belief.id, related.id, "supports", provenance="detected:add_belief", save=False)

        change = BeliefChange(
            belief_id=belief.id, change_type="created", new_claim=belief.claim, new_confidence=belief.confidence
        )
        self._record_change(change)

        self._save()
        return belief, change

    def add_contested_belief(self, belief: Belief, conflicting: list[Belief]) -> tuple[Belief, BeliefChange]:
        """Store a belief as contested: contradiction edges, no merge, no revision.

        Unlike ``add_belief``, this never routes through similarity merging or
        conflict-resolution strategies, so the existing beliefs it contradicts
        are guaranteed untouched (NEWER_WINS / HIGHER_CONFIDENCE would otherwise
        revise them). Both sides get contradiction edges so the conflict stays
        queryable - a belief-revision candidate for ``resolve-conflicts`` /
        health-check, never a silent drop or a silent overwrite.

        Args:
            belief: The new, contested belief to record.
            conflicting: Existing beliefs it contradicts (edges added both ways).

        Returns:
            Tuple of (stored belief, change record).
        """
        self.beliefs[belief.id] = belief
        self._index_belief(belief)

        for other in conflicting:
            self.add_edge(belief.id, other.id, "contradicts", provenance="contested:absorb", save=False)

        change = BeliefChange(
            belief_id=belief.id,
            change_type="created",
            new_claim=belief.claim,
            new_confidence=belief.confidence,
            reason="contested: contradicts " + ", ".join(other.id for other in conflicting),
        )
        self._record_change(change)

        self._save()
        return belief, change

    def update_belief(
        self,
        belief_id: str,
        new_confidence: float | None = None,
        new_evidence: str | None = None,
        reason: str = "",
    ) -> BeliefChange | None:
        """Update an existing belief.

        Args:
            belief_id: ID of belief to update
            new_confidence: New confidence value
            new_evidence: New evidence reference
            reason: Reason for update

        Returns:
            BeliefChange record or None
        """
        if belief_id not in self.beliefs:
            return None

        belief = self.beliefs[belief_id]
        old_confidence = belief.confidence

        if new_confidence is not None:
            belief.update_confidence(new_confidence, reason)

        if new_evidence:
            belief.add_evidence(new_evidence)

        change = BeliefChange(
            belief_id=belief_id,
            change_type="updated",
            old_claim=belief.claim,
            new_claim=belief.claim,
            old_confidence=old_confidence,
            new_confidence=belief.confidence,
            reason=reason,
            evidence=new_evidence or "",
        )
        self._record_change(change)

        self._save()
        return change

    def revise_belief(
        self,
        belief_id: str,
        new_claim: str,
        new_confidence: float,
        reason: str,
        evidence: str = "",
        invalidated_at: datetime | None = None,
    ) -> BeliefChange | None:
        """Revise a belief with new information.

        Args:
            belief_id: ID of belief to revise
            new_claim: New claim statement
            new_confidence: New confidence
            reason: Reason for revision
            evidence: Supporting evidence
            invalidated_at: Optional world-valid time at which the OLD
                claim stopped being true (bi-temporal semantics; the event
                timestamp records when the store learned of it)

        Returns:
            BeliefChange record or None
        """
        if belief_id not in self.beliefs:
            return None

        belief = self.beliefs[belief_id]
        old_claim = belief.claim
        old_confidence = belief.confidence

        # Update belief
        belief.claim = new_claim
        belief.update_confidence(new_confidence, reason)
        if evidence:
            belief.add_evidence(evidence)

        change = BeliefChange(
            belief_id=belief_id,
            change_type="revised",
            old_claim=old_claim,
            new_claim=new_claim,
            old_confidence=old_confidence,
            new_confidence=new_confidence,
            reason=reason,
            evidence=evidence,
            invalidated_at=invalidated_at,
        )
        self._record_change(change)

        self._save()
        return change

    def archive_belief(
        self, belief_id: str, reason: str = "", invalidated_at: datetime | None = None
    ) -> BeliefChange | None:
        """Archive a belief (soft delete, reversible from the event log).

        The archival event carries a full snapshot of the belief so
        ``restore_belief`` can rebuild it - reversibility is executable,
        not aspirational (docs/design/belief-lifecycle.md). Edges touching
        the archived belief are kept; the contested view already renders
        dangling edges honestly.

        Args:
            belief_id: ID of belief to archive
            reason: Reason for archiving
            invalidated_at: Optional world-valid time - when the underlying
                fact stopped being true (bi-temporal semantics), as
                distinct from the event timestamp (when the store retired
                the belief).

        Returns:
            BeliefChange record or None
        """
        if belief_id not in self.beliefs:
            return None

        belief = self.beliefs[belief_id]

        change = BeliefChange(
            belief_id=belief_id,
            change_type="archived",
            old_claim=belief.claim,
            new_claim="",
            old_confidence=belief.confidence,
            new_confidence=0.0,
            reason=reason,
            invalidated_at=invalidated_at,
            snapshot=belief.to_dict(),
        )
        self._record_change(change)

        # Remove from active beliefs
        del self.beliefs[belief_id]
        self._unindex_belief(belief)

        self._save()
        return change

    def restore_belief(self, belief_id: str) -> Belief | None:
        """Restore an archived belief from its archival snapshot.

        Scans the event log for the most recent ``archived`` event carrying
        a snapshot for this belief and re-adds it verbatim (no similarity
        merge, no conflict resolution - the belief returns exactly as it
        left). Pre-snapshot archival events (older stores) cannot be
        restored; the method returns None for those.

        Args:
            belief_id: ID of the belief to restore.

        Returns:
            The restored Belief, the live Belief if it was never archived,
            or None when no restorable snapshot exists.
        """
        existing = self.beliefs.get(belief_id)
        if existing is not None:
            return existing

        snapshot: dict[str, Any] | None = None
        for event in self.iter_events():
            if event.belief_id == belief_id and event.change_type == "archived" and event.snapshot:
                snapshot = event.snapshot  # latest archival wins
        if snapshot is None:
            return None

        belief = Belief.from_dict(snapshot)
        self.beliefs[belief.id] = belief
        self._index_belief(belief)

        change = BeliefChange(
            belief_id=belief.id,
            change_type="created",
            new_claim=belief.claim,
            new_confidence=belief.confidence,
            reason="restored from archival snapshot",
        )
        self._record_change(change)

        self._save()
        return belief

    def record_retrieval(self, belief_ids: list[str], context: str = "") -> int:
        """Record that beliefs were load-bearing in an answer (usage salience).

        Call ONLY from surfaces that already mutate the expert (e.g. chat
        knowledge assembly); the read-side query surface (validate, why,
        digest, contested, what-changed) is documented pure and MCP
        READ_ONLY mode depends on that staying true. Usage is state, not
        events - retrieval tallies would bloat the append-only log.

        Args:
            belief_ids: IDs of the beliefs that were actually used.
            context: Optional free-text note for debug logging only.

        Returns:
            Number of beliefs whose counters were updated.
        """
        now = _utc_now()
        touched = 0
        for bid in belief_ids:
            belief = self.beliefs.get(bid)
            if belief is None:
                continue
            belief.retrieval_count += 1
            belief.last_retrieved_at = now
            touched += 1
        if touched:
            logger.debug("Recorded retrieval of %d belief(s)%s", touched, f" ({context})" if context else "")
            self._save()
        return touched

    def archive_candidates(self, *, min_confidence: float = 0.2, unused_days: int = 90) -> list[Belief]:
        """Beliefs eligible for lifecycle archival (docs/design/belief-lifecycle.md).

        A belief is a candidate only if ALL gates pass:

        - current (decayed, trust-capped) confidence below ``min_confidence``
        - not updated or re-evidenced within ``unused_days``
        - no recorded retrieval within ``unused_days`` (usage protects;
          its absence never condemns - the other gates must also hold)
        - not a side of any open contradiction (contested beliefs are
          signal, never garbage - the Rashomon rule)

        Returns:
            Candidates sorted by current confidence, weakest first.
        """
        cutoff = _utc_now() - timedelta(days=unused_days)

        def _aware(ts: datetime) -> datetime:
            return ts if ts.tzinfo else ts.replace(tzinfo=UTC)

        candidates = []
        for belief in self.beliefs.values():
            if belief.get_current_confidence() >= min_confidence:
                continue
            if _aware(belief.updated_at) > cutoff:
                continue
            if belief.last_retrieved_at is not None and _aware(belief.last_retrieved_at) > cutoff:
                continue
            if belief.contradictions_with or self.edges_for(belief.id, "contradicts"):
                continue
            candidates.append(belief)
        return sorted(candidates, key=lambda b: b.get_current_confidence())

    def archive_stale(
        self, *, min_confidence: float = 0.2, unused_days: int = 90, reason: str = ""
    ) -> list[BeliefChange]:
        """Archive every current archive candidate (the consolidation pass).

        Each archival is event-logged with a full snapshot and the
        thresholds used, so the pass is reversible belief-by-belief via
        ``restore_belief``. $0 - no LLM, pure store operation.

        Returns:
            The archival change records (empty when nothing qualified).
        """
        changes = []
        for belief in self.archive_candidates(min_confidence=min_confidence, unused_days=unused_days):
            change = self.archive_belief(
                belief.id,
                reason=reason
                or (
                    f"lifecycle: confidence {belief.get_current_confidence():.2f} < {min_confidence}, "
                    f"unused {unused_days}+ days"
                ),
            )
            if change is not None:
                changes.append(change)
        return changes

    def get_beliefs_by_domain(self, domain: str) -> list[Belief]:
        """Get all beliefs in a domain.

        Args:
            domain: Domain to query

        Returns:
            List of beliefs in domain
        """
        belief_ids = self.domain_index.get(domain, set())
        return [self.beliefs[bid] for bid in belief_ids if bid in self.beliefs]

    def get_stale_beliefs(self, threshold: float = 0.3) -> list[Belief]:
        """Get beliefs that have become stale.

        Args:
            threshold: Confidence threshold

        Returns:
            List of stale beliefs
        """
        return [b for b in self.beliefs.values() if b.is_stale(threshold)]

    def get_contradictions(self, belief_id: str) -> list[Belief]:
        """Get beliefs that contradict a given belief.

        Args:
            belief_id: ID of belief

        Returns:
            List of contradicting beliefs
        """
        if belief_id not in self.beliefs:
            return []

        belief = self.beliefs[belief_id]
        return [self.beliefs[cid] for cid in belief.contradictions_with if cid in self.beliefs]

    def get_recent_changes(self, limit: int = 10) -> list[BeliefChange]:
        """Get recent belief changes.

        Args:
            limit: Maximum changes to return

        Returns:
            List of recent changes
        """
        return self.changes[-limit:]

    def find_similar_with_score(self, belief: Belief) -> tuple[Belief, float] | None:
        """First same-domain word-overlap match (>0.7) + score, or None (a high-recall router, not a merge verdict; AGENTIC_BALANCE.md)."""
        belief_words = set(belief.claim.lower().split())
        for existing in self.get_beliefs_by_domain(belief.domain):
            existing_words = set(existing.claim.lower().split())
            overlap = len(belief_words & existing_words)
            similarity = overlap / max(len(belief_words), len(existing_words), 1)
            if similarity > 0.7:
                return existing, similarity
        return None

    def _find_similar(self, belief: Belief) -> Belief | None:
        """Lexical router; see :meth:`find_similar_with_score` for the caveat."""
        match = self.find_similar_with_score(belief)
        return match[0] if match else None

    def _find_related(self, belief: Belief) -> list[Belief]:
        """Same-domain beliefs in the related-but-distinct similarity band.

        Same word-overlap machinery as _find_similar (>0.7 merges) and the
        contradiction heuristic, restricted to matching polarity: overlap in
        [0.35, 0.7) reads as "talks about the same thing, compatible claim".
        These become `supports` edges so explain_belief has chains to walk.
        Free and phrasing-level - the same precision caveats as the negation
        heuristic apply, which is why edges carry provenance and are
        advisory structure, never a confidence input.

        Returns at most the 3 strongest matches to keep the graph sparse.
        """
        negation_words = {"not", "no", "never", "false", "incorrect", "wrong"}
        belief_words = set(belief.claim.lower().split())
        has_negation = bool(belief_words & negation_words)

        scored: list[tuple[float, Belief]] = []
        for existing in self.get_beliefs_by_domain(belief.domain):
            if existing.id == belief.id:
                continue
            existing_words = set(existing.claim.lower().split())
            if bool(existing_words & negation_words) != has_negation:
                continue
            overlap = len(belief_words & existing_words)
            similarity = overlap / max(len(belief_words), len(existing_words), 1)
            if 0.35 <= similarity < 0.7:
                scored.append((similarity, existing))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [b for _, b in scored[:3]]

    def _find_contradictions(self, belief: Belief) -> list[Belief]:
        """Find same-domain beliefs that may contradict the given one.

        This is a high-recall *router*, not a verdict: it routes candidate
        pairs into the model-based contradiction check, and must never be
        treated as a confirmed contradiction on its own (see
        docs/design/checks-deterministic-vs-agentic.md). It delegates the
        single-pair test to the canonical
        :meth:`ConflictResolver.beliefs_contradict` predicate so there is one
        lexical heuristic, not a drifting second copy.

        Args:
            belief: Belief to check

        Returns:
            List of candidate contradicting beliefs (lexical, unverified)
        """
        # Local import: conflict_resolver imports Belief from this module, so a
        # top-level import would be circular.
        from deepr.experts.conflict_resolver import ConflictResolver

        return [
            existing
            for existing in self.get_beliefs_by_domain(belief.domain)
            if existing.id != belief.id and ConflictResolver.beliefs_contradict(belief, existing)
        ]

    def _resolve_conflict(self, existing: Belief, new: Belief) -> tuple[Belief, BeliefChange | None]:
        """Resolve conflict between beliefs.

        Args:
            existing: Existing belief
            new: New belief

        Returns:
            Tuple of (resolved belief, change record)
        """
        if self.conflict_resolution == ConflictResolution.NEWER_WINS:
            # Replace with new belief
            change = self.revise_belief(existing.id, new.claim, new.confidence, "Newer information available")
            return self.beliefs[existing.id], change

        if self.conflict_resolution == ConflictResolution.HIGHER_CONFIDENCE:
            if new.confidence > existing.confidence:
                change = self.revise_belief(existing.id, new.claim, new.confidence, "Higher confidence evidence")
                return self.beliefs[existing.id], change
            else:
                # Keep existing, but note the new evidence
                existing.add_evidence(f"conflicting:{new.id}")
                return existing, None

        if self.conflict_resolution == ConflictResolution.MERGE:
            # Merge evidence, average confidence
            merged_confidence = (existing.confidence + new.confidence) / 2
            for ref in new.evidence_refs:
                existing.add_evidence(ref)
            existing.update_confidence(merged_confidence, "Merged with new evidence")

            change = BeliefChange(
                belief_id=existing.id,
                change_type="updated",
                old_claim=existing.claim,
                new_claim=existing.claim,
                old_confidence=existing.confidence,
                new_confidence=merged_confidence,
                reason="Merged beliefs",
            )
            self._record_change(change)
            self._save()
            return existing, change

        # ASK_USER - return both for user decision
        return existing, None

    def _index_belief(self, belief: Belief):
        """Add belief to domain index."""
        if belief.domain not in self.domain_index:
            self.domain_index[belief.domain] = set()
        self.domain_index[belief.domain].add(belief.id)

    def _unindex_belief(self, belief: Belief):
        """Remove belief from domain index."""
        if belief.domain in self.domain_index:
            self.domain_index[belief.domain].discard(belief.id)

    def _save(self):
        """Save beliefs to disk."""
        data = {
            "edges": [e.to_dict() for e in self.edges.values()],
            "beliefs": {bid: b.to_dict() for bid, b in self.beliefs.items()},
            "changes": [c.to_dict() for c in self.changes[-100:]],  # Keep last 100 changes
        }

        from deepr.utils.atomic_io import atomic_write_json

        atomic_write_json(self.storage_path, data)

    def _load(self):
        """Load beliefs from disk.

        Catches corrupt/oversized files and starts fresh rather than
        crashing the expert load entirely. A 50 MB ceiling guards
        against poisoned belief files from corpus imports.
        """
        if not self.storage_path.exists():
            return

        try:
            if self.storage_path.stat().st_size > 50 * 1024 * 1024:
                logger.error(
                    "Belief store at %s exceeds 50 MB; refusing to load. Inspect and reduce manually.",
                    self.storage_path,
                )
                return
            with open(self.storage_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load beliefs from %s: %s. Starting fresh.", self.storage_path, exc)
            return

        self.beliefs = {bid: Belief.from_dict(bdata) for bid, bdata in data.get("beliefs", {}).items()}

        # Rebuild domain index
        for belief in self.beliefs.values():
            self._index_belief(belief)

        # Load typed edges
        for edata in data.get("edges", []):
            try:
                edge = Edge.from_dict(edata)
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed edge in %s: %s", self.storage_path, exc)
                continue
            self.edges[edge.key()] = edge

        # One-time, idempotent migration (TKG step 2): legacy
        # contradictions_with lists become typed contradicts edges. Key-based
        # dedup makes re-running free; the legacy field stays in sync (both
        # directions are already recorded on the beliefs) for one release.
        migrated = 0
        for belief in self.beliefs.values():
            for other_id in belief.contradictions_with:
                probe = Edge(src_id=belief.id, dst_id=other_id, edge_type="contradicts")
                if probe.key() not in self.edges:
                    probe.provenance.append(_MIGRATED_PROVENANCE)
                    self.edges[probe.key()] = probe
                    migrated += 1
        if migrated:
            logger.info("Migrated %d contradictions_with pair(s) to typed edges for %s", migrated, self.expert_name)
            self._save()

        # Load changes (canonical from_dict carries the optional
        # bi-temporal/snapshot fields; absent fields default to None)
        for cdata in data.get("changes", []):
            try:
                self.changes.append(BeliefChange.from_dict(cdata))
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed change record in %s: %s", self.storage_path, exc)


class SharedBeliefStore:
    """Shared belief store for cross-expert knowledge sharing.

    Beliefs are namespaced by domain to prevent conflicts.
    Each expert can contribute and consume shared beliefs.

    Attributes:
        storage_dir: Directory for shared storage
        domain_stores: Per-domain belief stores
        domain_velocities: Domain velocity for TTL calculation
    """

    # Default domain velocities (days until stale)
    DEFAULT_VELOCITIES = {
        "technology": 90,
        "science": 365,
        "business": 180,
        "general": 365,
        "current_events": 7,
        "regulations": 180,
    }

    def __init__(self, storage_dir: Path | None = None):
        """Initialize shared belief store.

        Args:
            storage_dir: Directory for storage
        """
        if storage_dir is None:
            storage_dir = Path("data/shared/beliefs")
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.storage_path = self.storage_dir / "shared_beliefs.json"
        self.domain_stores: dict[str, dict[str, Belief]] = {}
        self.contributors: dict[str, set[str]] = {}  # belief_id -> expert_names

        self._load()

    def share_belief(self, belief: Belief, expert_name: str, min_confidence: float = 0.7) -> bool:
        """Share a belief from an expert.

        Args:
            belief: Belief to share
            expert_name: Name of contributing expert
            min_confidence: Minimum confidence to share

        Returns:
            True if belief was shared
        """
        # Only share high-confidence beliefs
        if belief.get_current_confidence() < min_confidence:
            return False

        domain = belief.domain or "general"

        if domain not in self.domain_stores:
            self.domain_stores[domain] = {}

        # Check for existing similar belief
        existing = self._find_similar_in_domain(belief, domain)

        if existing:
            # Merge evidence and update confidence
            for ref in belief.evidence_refs:
                existing.add_evidence(ref)

            # Weighted average based on number of contributors
            num_contributors = len(self.contributors.get(existing.id, set()))
            new_confidence = (existing.confidence * num_contributors + belief.confidence) / (num_contributors + 1)
            existing.update_confidence(new_confidence, f"Corroborated by {expert_name}")

            # Track contributor
            if existing.id not in self.contributors:
                self.contributors[existing.id] = set()
            self.contributors[existing.id].add(expert_name)
        else:
            # Add new shared belief
            self.domain_stores[domain][belief.id] = belief
            self.contributors[belief.id] = {expert_name}

        self._save()
        return True

    def get_shared_beliefs(self, domain: str, min_confidence: float = 0.5, exclude_stale: bool = True) -> list[Belief]:
        """Get shared beliefs for a domain.

        Args:
            domain: Domain to query
            min_confidence: Minimum confidence threshold
            exclude_stale: Whether to exclude stale beliefs

        Returns:
            List of shared beliefs
        """
        if domain not in self.domain_stores:
            return []

        beliefs = []
        stale_threshold = self._get_stale_threshold(domain)

        for belief in self.domain_stores[domain].values():
            current_conf = belief.get_current_confidence()

            if current_conf < min_confidence:
                continue

            if exclude_stale and belief.is_stale(stale_threshold):
                continue

            beliefs.append(belief)

        return sorted(beliefs, key=lambda b: b.get_current_confidence(), reverse=True)

    def import_to_expert(self, expert_store: BeliefStore, domain: str, max_beliefs: int = 10) -> int:
        """Import shared beliefs to an expert's store.

        Args:
            expert_store: Expert's belief store
            domain: Domain to import from
            max_beliefs: Maximum beliefs to import

        Returns:
            Number of beliefs imported
        """
        shared = self.get_shared_beliefs(domain)[:max_beliefs]
        imported = 0

        for belief in shared:
            # Create copy for expert
            expert_belief = Belief(
                claim=belief.claim,
                confidence=belief.confidence * 0.9,  # Slight discount for shared
                evidence_refs=belief.evidence_refs.copy(),
                domain=belief.domain,
                source_type="shared",
            )

            expert_store.add_belief(expert_belief, check_conflicts=True)
            imported += 1

        return imported

    def get_contributors(self, belief_id: str) -> set[str]:
        """Get experts who contributed to a belief.

        Args:
            belief_id: ID of belief

        Returns:
            Set of expert names
        """
        return self.contributors.get(belief_id, set())

    def cleanup_stale(self) -> int:
        """Remove stale beliefs from shared store.

        Returns:
            Number of beliefs removed
        """
        removed = 0

        for domain, beliefs in list(self.domain_stores.items()):
            threshold = self._get_stale_threshold(domain)

            stale_ids = [bid for bid, belief in beliefs.items() if belief.is_stale(threshold)]

            for bid in stale_ids:
                del beliefs[bid]
                if bid in self.contributors:
                    del self.contributors[bid]
                removed += 1

        if removed > 0:
            self._save()

        return removed

    def _find_similar_in_domain(self, belief: Belief, domain: str) -> Belief | None:
        """Find similar belief in domain.

        Args:
            belief: Belief to compare
            domain: Domain to search

        Returns:
            Similar belief or None
        """
        if domain not in self.domain_stores:
            return None

        belief_words = set(belief.claim.lower().split())

        for existing in self.domain_stores[domain].values():
            existing_words = set(existing.claim.lower().split())
            overlap = len(belief_words & existing_words)
            similarity = overlap / max(len(belief_words), len(existing_words), 1)

            if similarity > 0.7:
                return existing

        return None

    def _get_stale_threshold(self, domain: str) -> float:
        """Get staleness threshold for domain.

        Args:
            domain: Domain name

        Returns:
            Confidence threshold for staleness
        """
        velocity_days = self.DEFAULT_VELOCITIES.get(domain, 365)
        # Faster domains have higher staleness threshold
        return 0.5 if velocity_days < 30 else 0.3

    def _save(self):
        """Save shared beliefs to disk."""
        data = {
            "domains": {
                domain: {bid: b.to_dict() for bid, b in beliefs.items()}
                for domain, beliefs in self.domain_stores.items()
            },
            "contributors": {bid: list(experts) for bid, experts in self.contributors.items()},
        }

        from deepr.utils.atomic_io import atomic_write_json

        atomic_write_json(self.storage_path, data)

    def _load(self):
        """Load shared beliefs from disk."""
        if not self.storage_path.exists():
            return

        with open(self.storage_path, encoding="utf-8") as f:
            data = json.load(f)

        for domain, beliefs in data.get("domains", {}).items():
            self.domain_stores[domain] = {bid: Belief.from_dict(bdata) for bid, bdata in beliefs.items()}

        self.contributors = {bid: set(experts) for bid, experts in data.get("contributors", {}).items()}
