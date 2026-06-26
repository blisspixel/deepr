"""Read-side, cost-$0 health audit of an expert's knowledge state.

``ExpertHealthChecker`` composes existing read-side primitives - the freshness
checker, the conflict detector's free heuristic stage, the gap scorer, and
structural provenance checks - into a single auditable report plus a
budget-aware action menu. It never mutates the expert and never makes a paid
provider call, so it is safe to run on a schedule (the monthly self-maintenance
pass) and cheap enough to call from agents over MCP.

The report is two-phase by design (see ROADMAP Phase 4):

1. An auditable set of findings (what the audit observed), each with a severity.
2. A recommended-action menu, where every corrective step carries the CLI
   command, an estimated cost, and the approval tier that would gate it. The
   audit itself proposes; it never executes. Acting on a recommendation is a
   separate, opt-in, budget-bounded step.
"""

from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from deepr.experts.approval import ApprovalTier

if TYPE_CHECKING:
    from deepr.experts.beliefs import Belief
    from deepr.experts.profile import ExpertProfile

logger = logging.getLogger(__name__)

# Severity ordering, lowest to highest. Used to roll findings up into an
# overall status and to sort the displayed findings.
_SEVERITY_ORDER = {"ok": 0, "info": 1, "warning": 2, "critical": 3}

# Open-gap count at or above which the backlog is flagged for attention.
_GAP_BACKLOG_WARN = 5

# Confidence-decay threshold below which a belief is considered stale (matches
# Belief.is_stale's default).
_STALE_CONFIDENCE_THRESHOLD = 0.3


@dataclass
class HealthFinding:
    """One observation from the audit.

    Attributes:
        category: Stable check identifier (freshness, contradictions,
            provenance, stale_beliefs, gaps, coverage).
        severity: ok | info | warning | critical.
        summary: One-line, human-readable headline.
        detail: Structured specifics for machine consumers / verbose output.
    """

    category: str
    severity: str
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "summary": self.summary,
            "detail": self.detail,
        }


@dataclass
class RecommendedAction:
    """A proposed corrective step, gated by an approval tier.

    The audit emits these but never runs them. ``estimated_cost`` is 0.0 for
    read-side follow-ups (e.g. manual review) and a positive USD estimate for
    anything that would spend on a provider.
    """

    category: str
    description: str
    command: str
    estimated_cost: float = 0.0
    approval_tier: str = ApprovalTier.AUTO_APPROVE.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "description": self.description,
            "command": self.command,
            "estimated_cost": round(self.estimated_cost, 2),
            "approval_tier": self.approval_tier,
        }


@dataclass
class HealthReport:
    """The full result of a health-check run."""

    expert_name: str
    domain: str
    status: str  # healthy | needs_attention | critical
    findings: list[HealthFinding] = field(default_factory=list)
    actions: list[RecommendedAction] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_name": self.expert_name,
            "domain": self.domain,
            "status": self.status,
            "findings": [f.to_dict() for f in self.findings],
            "actions": [a.to_dict() for a in self.actions],
            "generated_at": self.generated_at.isoformat(),
        }


def _approval_tier_for_cost(estimated_cost: float) -> str:
    """Map an estimated spend onto the default approval tier.

    Mirrors the spirit of ApprovalManager.DEFAULT_POLICIES: free is automatic,
    modest spend is a notify, and anything over a dollar needs explicit
    confirmation. The audit never auto-approves a paid action - it only labels
    what tier would gate it if the user chose to run it.
    """
    if estimated_cost <= 0:
        return ApprovalTier.AUTO_APPROVE.value
    if estimated_cost > 1.0:
        return ApprovalTier.CONFIRM.value
    return ApprovalTier.NOTIFY.value


def _load_beliefs(profile: ExpertProfile) -> list[Belief]:
    """Best-effort load of an expert's stored beliefs (the canonical BeliefStore).

    Returns the rich ``experts.beliefs.Belief`` objects that the contradiction
    and confidence-decay checks operate on (they need belief IDs, evidence
    refs, and decay-aware confidence). Worldview synthesis beliefs are a
    different, lighter type and are already represented in the manifest's
    claims, so the provenance and coverage checks cover them - this loader
    deliberately stays scoped to the canonical belief store. A missing or
    corrupt store degrades to an empty list rather than failing the audit.
    """
    try:
        from deepr.experts.beliefs import BeliefStore

        store = BeliefStore(profile.name)
        return list(store.beliefs.values())
    except Exception:
        logger.debug("health-check: could not load BeliefStore for %s", profile.name, exc_info=True)
        return []


class ExpertHealthChecker:
    """Runs a read-side, cost-$0 audit of one expert's knowledge state.

    Usage:
        report = ExpertHealthChecker(profile).run()
    """

    def __init__(self, profile: ExpertProfile):
        self.profile = profile

    def run(self) -> HealthReport:
        """Execute every read-side check and assemble the report.

        Pure read-side: loads the manifest and beliefs, runs the free checks,
        and returns findings plus a recommended-action menu. No provider call,
        no mutation.
        """
        findings: list[HealthFinding] = []
        actions: list[RecommendedAction] = []

        manifest = self.profile.get_manifest()
        beliefs = _load_beliefs(self.profile)

        for check in (
            self._check_freshness,
            self._check_contradictions,
            self._check_provenance,
            self._check_stale_beliefs,
            self._check_archive_candidates,
            self._check_gap_backlog,
            self._check_coverage,
        ):
            finding, action = check(manifest, beliefs)
            findings.append(finding)
            if action is not None:
                actions.append(action)

        status = self._roll_up_status(findings)
        findings.sort(key=lambda f: _SEVERITY_ORDER.get(f.severity, 0), reverse=True)

        return HealthReport(
            expert_name=self.profile.name,
            domain=self.profile.domain or "",
            status=status,
            findings=findings,
            actions=actions,
        )

    # ------------------------------------------------------------------ #
    # Individual checks. Each returns (finding, optional recommended action).
    # ------------------------------------------------------------------ #

    def _check_freshness(self, manifest: Any, beliefs: list[Belief]) -> tuple[HealthFinding, RecommendedAction | None]:
        details = self.profile.get_staleness_details()
        status = details.get("freshness_status", "unknown")

        severity_map = {"incomplete": "critical", "stale": "warning", "aging": "info", "fresh": "ok"}
        severity = severity_map.get(status, "info")

        age_days = details.get("age_days")
        if status == "incomplete":
            summary = "Expert has no knowledge cutoff - needs an initial learning curriculum."
        elif age_days is not None:
            summary = f"Knowledge is {status} ({age_days}d old, threshold {details.get('threshold_days')}d)."
        else:
            summary = f"Knowledge freshness: {status}."

        action = None
        if severity in ("warning", "critical"):
            cost = float(details.get("estimated_refresh_cost", 0.0) or 0.0)
            action = RecommendedAction(
                category="freshness",
                description="Refresh knowledge to clear staleness",
                command=details.get("refresh_command") or f"deepr expert refresh {shlex.quote(self.profile.name)}",
                estimated_cost=cost,
                approval_tier=_approval_tier_for_cost(cost),
            )

        return HealthFinding("freshness", severity, summary, details), action

    def _recorded_contested_pairs(self) -> list[dict[str, Any]]:
        """Open contested pairs recorded in the belief store (absorb/sync flags).

        Separate method so tests can stub it without touching the on-disk
        store; failures are non-fatal - the audit must stay read-only.
        """
        try:
            # BeliefStore.__init__ creates its directory; a read-only audit
            # must not create state, so only open stores that already exist
            # (same CWD-pollution class as the cost-ledger test bug).
            from deepr.config import experts_root
            from deepr.experts.beliefs import BeliefStore
            from deepr.experts.perspective import contested as contested_query

            beliefs_dir = experts_root() / self.profile.name / "beliefs"
            if not beliefs_dir.exists():
                return []
            recorded = contested_query(BeliefStore(self.profile.name), expert_name=self.profile.name)
            return [p for p in recorded["pairs"] if p["status"] == "open"]
        except Exception as exc:
            logger.debug("Could not read recorded contested pairs: %s", exc, exc_info=exc)
            return []

    def _check_contradictions(
        self, manifest: Any, beliefs: list[Belief]
    ) -> tuple[HealthFinding, RecommendedAction | None]:
        """Open contradictions: recorded flags first, then fresh heuristic.

        Two sources, deduplicated by id pair:
        - recorded: contested pairs already flagged at absorb/sync time
          (contradiction edges in the belief store) - these were detected
          when the conflicting claim arrived and persist until adjudicated.
          Previously the audit ignored them and only re-ran the heuristic,
          so the action menu never showed the absorb-time flags.
        - heuristic: newly detected by the free negation heuristic on this
          run (pairs the recorded set does not already cover).
        """
        from deepr.experts.conflict_resolver import ConflictResolver

        recorded_pairs = self._recorded_contested_pairs()

        recorded_keys = {frozenset((p["a"]["belief_id"], p["b"]["belief_id"])) for p in recorded_pairs}
        heuristic_pairs = [
            (a, b)
            for a, b in ConflictResolver.detect_contradictions_heuristic(beliefs)
            if frozenset((a.id, b.id)) not in recorded_keys
        ]

        count = len(recorded_pairs) + len(heuristic_pairs)
        if recorded_pairs:
            severity = "warning"
            summary = (
                f"{count} candidate contradiction(s), lexical/unverified: {len(recorded_pairs)} recorded "
                f"(absorb/sync-time flags), {len(heuristic_pairs)} newly detected (heuristic). "
                "Adjudicate recorded pairs for a model verdict."
            )
        elif heuristic_pairs:
            severity = "info"
            summary = (
                f"{len(heuristic_pairs)} advisory contradiction candidate(s) from the lexical router. "
                "No recorded contested beliefs; do not treat these as semantic contradictions until model-checked."
            )
        else:
            severity = "ok"
            summary = "No belief contradictions detected (recorded + heuristic pass)."
        detail = {
            "count": count,
            "verification": "lexical_unverified",
            "recorded": [
                {
                    "a": p["a"]["claim"],
                    "b": p["b"]["claim"],
                    "a_id": p["a"]["belief_id"],
                    "b_id": p["b"]["belief_id"],
                }
                for p in recorded_pairs[:10]
            ],
            "heuristic": [
                {"a": a.claim, "b": b.claim, "domain": a.domain, "a_id": a.id, "b_id": b.id}
                for a, b in heuristic_pairs[:10]
            ],
        }

        action = None
        if recorded_pairs:
            # resolve-conflicts runs the paid LLM adjudication; a few cents per recorded pair.
            cost = round(0.02 * len(recorded_pairs), 2)
            action = RecommendedAction(
                category="contradictions",
                description=(f"Adjudicate {len(recorded_pairs)} recorded contradiction(s) and revise beliefs"),
                command=f"deepr expert resolve-conflicts {shlex.quote(self.profile.name)}",
                estimated_cost=cost,
                approval_tier=_approval_tier_for_cost(cost),
            )

        return HealthFinding("contradictions", severity, summary, detail), action

    def _check_provenance(self, manifest: Any, beliefs: list[Belief]) -> tuple[HealthFinding, RecommendedAction | None]:
        unsourced = [c for c in manifest.claims if not c.sources]
        count = len(unsourced)
        total = manifest.claim_count
        severity = "warning" if count else "ok"
        summary = (
            f"{count} of {total} claim(s) carry no source provenance."
            if count
            else f"All {total} claim(s) carry source provenance."
        )
        detail = {
            "unsourced_count": count,
            "total_claims": total,
            "examples": [{"id": c.id, "statement": c.statement} for c in unsourced[:10]],
        }
        # Missing provenance is a review signal, not an automated paid fix - no
        # action emitted. (validate-citations / re-research are the manual paths.)
        return HealthFinding("provenance", severity, summary, detail), None

    def _check_stale_beliefs(
        self, manifest: Any, beliefs: list[Belief]
    ) -> tuple[HealthFinding, RecommendedAction | None]:
        stale = [b for b in beliefs if b.is_stale(_STALE_CONFIDENCE_THRESHOLD)]
        count = len(stale)
        severity = "warning" if count else "ok"
        summary = (
            f"{count} belief(s) decayed below confidence {_STALE_CONFIDENCE_THRESHOLD}."
            if count
            else "No beliefs have decayed below the confidence threshold."
        )
        detail = {
            "count": count,
            "threshold": _STALE_CONFIDENCE_THRESHOLD,
            "examples": [
                {"id": b.id, "claim": b.claim, "confidence": round(b.get_current_confidence(), 3)} for b in stale[:10]
            ],
        }
        return HealthFinding("stale_beliefs", severity, summary, detail), None

    def _archive_candidate_summaries(self) -> list[dict[str, Any]]:
        """Lifecycle archive candidates from the belief store (read-only).

        Separate method so tests can stub it; same existence-check pattern
        as ``_recorded_contested_pairs`` - a read-only audit must not
        create state, so only stores that already exist are opened.
        """
        try:
            from deepr.config import experts_root
            from deepr.experts.beliefs import BeliefStore

            beliefs_dir = experts_root() / self.profile.name / "beliefs"
            if not beliefs_dir.exists():
                return []
            store = BeliefStore(self.profile.name)
            return [
                {
                    "id": b.id,
                    "claim": b.claim,
                    "confidence": round(b.get_current_confidence(), 3),
                    "updated_at": b.updated_at.isoformat(),
                    "retrieval_count": b.retrieval_count,
                }
                for b in store.archive_candidates()
            ]
        except Exception as exc:
            logger.debug("Could not compute archive candidates: %s", exc, exc_info=exc)
            return []

    def _check_archive_candidates(
        self, manifest: Any, beliefs: list[Belief]
    ) -> tuple[HealthFinding, RecommendedAction | None]:
        """Lifecycle governance: beliefs eligible for reversible archival.

        Candidates pass ALL gates in BeliefStore.archive_candidates -
        decayed below the floor, long-unevidenced, no recorded usage, and
        not contested (contested beliefs are signal, never garbage). The
        audit proposes; archival itself is the opt-in --archive-stale
        action, event-logged with snapshots so it is reversible
        belief-by-belief (docs/design/belief-lifecycle.md).
        """
        candidates = self._archive_candidate_summaries()
        count = len(candidates)
        severity = "info" if count else "ok"
        summary = (
            f"{count} belief(s) eligible for reversible archival (decayed, unevidenced, unused, uncontested)."
            if count
            else "No beliefs eligible for lifecycle archival."
        )
        detail = {"count": count, "examples": candidates[:10]}

        action = None
        if count:
            action = RecommendedAction(
                category="archive_candidates",
                description=f"Archive {count} stale belief(s) (reversible; snapshots kept in the event log)",
                command=f"deepr expert health-check {shlex.quote(self.profile.name)} --archive-stale",
                estimated_cost=0.0,
                approval_tier=ApprovalTier.CONFIRM.value,
            )

        return HealthFinding("archive_candidates", severity, summary, detail), action

    def _check_gap_backlog(
        self, manifest: Any, beliefs: list[Belief]
    ) -> tuple[HealthFinding, RecommendedAction | None]:
        open_count = manifest.open_gap_count
        top = manifest.top_gaps(5)
        if open_count >= _GAP_BACKLOG_WARN:
            severity = "warning"
        elif open_count:
            severity = "info"
        else:
            severity = "ok"
        summary = f"{open_count} open knowledge gap(s)." if open_count else "No open knowledge gaps."
        detail = {
            "open_gap_count": open_count,
            "top_gaps": [
                {"topic": g.topic, "priority": g.priority, "ev_cost_ratio": round(g.ev_cost_ratio, 3)} for g in top
            ],
        }

        action = None
        if open_count >= _GAP_BACKLOG_WARN:
            n = min(open_count, 3)
            cost = round(sum(g.estimated_cost for g in top[:n]), 2)
            action = RecommendedAction(
                category="gaps",
                description=f"Fill the top {n} highest-value gap(s)",
                command=f"deepr expert fill-gaps {shlex.quote(self.profile.name)} --top {n}",
                estimated_cost=cost,
                approval_tier=_approval_tier_for_cost(cost),
            )

        return HealthFinding("gaps", severity, summary, detail), action

    def _check_coverage(self, manifest: Any, beliefs: list[Belief]) -> tuple[HealthFinding, RecommendedAction | None]:
        documents = self.profile.total_documents
        claims = manifest.claim_count

        # The actionable coverage signal: material was ingested but never
        # synthesized into beliefs/claims (un-synthesized raw knowledge).
        if documents > 0 and claims == 0:
            severity = "warning"
            summary = f"{documents} document(s) ingested but no beliefs synthesized yet."
            action = RecommendedAction(
                category="coverage",
                description="Synthesize ingested documents into beliefs",
                command=f"deepr expert refresh {shlex.quote(self.profile.name)} --synthesize",
                estimated_cost=0.50,
                approval_tier=_approval_tier_for_cost(0.50),
            )
        else:
            severity = "ok"
            summary = f"{claims} claim(s) across {documents} document(s)."
            action = None

        detail = {
            "documents": documents,
            "claims": claims,
            "source_files": len(self.profile.source_files),
            "research_jobs": len(self.profile.research_jobs),
        }
        return HealthFinding("coverage", severity, summary, detail), action

    @staticmethod
    def _roll_up_status(findings: list[HealthFinding]) -> str:
        worst = max((_SEVERITY_ORDER.get(f.severity, 0) for f in findings), default=0)
        if worst >= _SEVERITY_ORDER["critical"]:
            return "critical"
        if worst >= _SEVERITY_ORDER["warning"]:
            return "needs_attention"
        return "healthy"
