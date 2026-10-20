"""Commit boundary for fully verified report-absorption mutations."""

from __future__ import annotations

from dataclasses import dataclass, field

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.report_absorber_contracts import AbsorbedClaim, ReportAbsorberError


@dataclass(frozen=True)
class StagedAbsorption:
    """One mutation whose model-driven checks completed without a write."""

    belief: Belief
    merge_blocked: bool = False
    conflict: Belief | None = None
    verification: str = "lexical_unverified"
    merge_target: tuple[str, str] | None = None
    candidate_identity: tuple[str, str] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_identity", (self.belief.claim, self.belief.domain))


def _merge_admitted(store: BeliefStore, item: StagedAbsorption, committed: dict[str, Belief]) -> bool:
    """Bind the semantic verdict to the actual target under the store lock."""
    if (
        item.merge_blocked
        or item.merge_target is None
        or item.candidate_identity != (item.belief.claim, item.belief.domain)
    ):
        return False
    target_id, target_claim = item.merge_target
    if target_id in committed:
        target_id = committed[target_id].id
    match = store.find_similar_with_score(item.belief)
    return match is not None and (match[0].id, match[0].claim) == (target_id, target_claim)


class ReportAbsorberCommitError(ReportAbsorberError):
    """A commit failure that explicitly identifies any durable partial state."""

    def __init__(self, message: str, *, committed_belief_ids: tuple[str, ...]) -> None:
        self.committed_belief_ids = committed_belief_ids
        suffix = ", ".join(committed_belief_ids) if committed_belief_ids else "none"
        super().__init__(f"{message}; committed belief ids before failure: {suffix}")


def commit_staged_absorptions(
    store: BeliefStore,
    staged: list[StagedAbsorption],
    *,
    report_id: str,
) -> list[AbsorbedClaim]:
    """Persist staged mutations only after every fallible semantic call passes."""
    absorbed: list[AbsorbedClaim] = []
    committed_ids: list[str] = []
    committed_by_staged_id: dict[str, Belief] = {}
    try:
        for item in staged:
            if item.conflict is not None:
                conflict = committed_by_staged_id.get(item.conflict.id, item.conflict)
                stored, _contested_change = store.add_contested_belief(
                    item.belief,
                    [conflict],
                    verification=item.verification,
                )
                committed_ids.append(stored.id)
                committed_by_staged_id[item.belief.id] = stored
                continue
            with store.mutation():
                pre_ids = set(store.beliefs)
                stored, _belief_change = store.add_belief(
                    item.belief,
                    check_conflicts=True,
                    dedup=_merge_admitted(store, item, committed_by_staged_id),
                    change_reason=f"absorbed_report:{report_id}",
                    edge_provenance=f"report:{report_id}",
                )
            committed_ids.append(stored.id)
            committed_by_staged_id[item.belief.id] = stored
            outcome = "merged" if stored.id in pre_ids else "added"
            absorbed.append(AbsorbedClaim(stored.claim, stored.confidence, stored.id, outcome))
    except Exception as exc:
        raise ReportAbsorberCommitError(
            "Belief commit failed after verification",
            committed_belief_ids=tuple(committed_ids),
        ) from exc
    return absorbed
