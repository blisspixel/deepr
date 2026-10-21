"""Case-bound source context and immutable-answer bindings for blinded review.

Reviewers receive the frozen evidence itself. Hashes guard identities; reviewer
judgment still decides whether an answer uses that evidence within its scope.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from deepr.evals.correction_survival_cases import (
    CASE_SET_VERSION,
    CASES,
    REVIEW_LABELS,
    RUBRIC,
    Case,
    case_set_sha256,
    source_inventory,
    source_inventory_sha256,
    world,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _review_contexts(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Resolve source bytes only for the exact scheduled frozen case identity."""
    ids = run.get("case_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(item, str) for item in ids):
        raise ValueError("review requires a nonempty scheduled case list")
    if len(ids) != len(set(ids)):
        raise ValueError("review case list contains duplicate identities")
    by_id = {case.case_id: case for case in CASES}
    try:
        scheduled = tuple(by_id[item] for item in ids)
    except KeyError as error:
        raise ValueError("review names an unknown case") from error
    if run.get("case_set_version") != CASE_SET_VERSION or run.get("case_set_sha256") != case_set_sha256(scheduled):
        raise ValueError("review was produced from a different frozen case set")
    if run.get("rubric") != RUBRIC:
        raise ValueError("review case rubric differs from the frozen rubric")
    distractors = run.get("distractors_per_world")
    if not isinstance(distractors, int) or isinstance(distractors, bool) or distractors < 0:
        raise ValueError("review distractor count must be a non-negative integer")
    return {case.case_id: _case_context(run, case, distractors) for case in scheduled}


def _case_context(run: dict[str, Any], case: Case, distractors: int) -> dict[str, Any]:
    """Admit only the source inventory actually bound to the collected world."""
    frozen = world(case.world_id)
    sources = source_inventory(frozen, distractors)
    fingerprint = source_inventory_sha256(sources)
    recorded = run.get("source_inventory_sha256")
    if recorded is None:
        if distractors:
            raise ValueError("review lacks a bound auxiliary source inventory; use the compatible producer")
    elif not isinstance(recorded, dict) or recorded.get(frozen.world_id) != fingerprint:
        raise ValueError("review source inventory differs from the collected world")
    return {
        "kind": "deepr.correction-survival-review-context.v1",
        "case_set_sha256": run["case_set_sha256"],
        "question": case.question,
        "world_id": frozen.world_id,
        "cutoff": frozen.cutoff,
        "distractors_per_world": distractors,
        "source_inventory_sha256": fingerprint,
        "sources": [asdict(source) | {"text_sha256": _sha(source.text)} for source in sources],
        "obligations": [asdict(obligation) for obligation in case.obligations],
        "rubric": RUBRIC,
    }


def blinded_review_packet(run: dict[str, Any], *, salt: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Answers under opaque ids, and the key that maps them back to arms.

    Labels are bound by opaque id and answer hash before the key is opened.
    """
    contexts = _review_contexts(run)
    items = []
    key: dict[str, str] = {}
    for attempt in run["attempts"]:
        if attempt["status"] != "completed":
            continue
        if attempt["case_id"] not in contexts:
            raise ValueError("attempt names a case outside the scheduled case set")
        opaque = _sha(f"{salt}:{attempt['attempt_id']}")[:16]
        key[opaque] = attempt["attempt_id"]
        items.append(
            {
                "item_id": opaque,
                "case_id": attempt["case_id"],
                "answer_sha256": attempt["answer_sha256"],
                "obligations": sorted(attempt["stage_receipts"]),
                "review_context": deepcopy(contexts[attempt["case_id"]]),
            }
        )
    items.sort(key=lambda item: item["item_id"])
    return items, key


def bind_review_labels(
    run: dict[str, Any],
    key: dict[str, str],
    labels: list[dict[str, Any]],
    existing: dict[tuple[str, str], str] | None = None,
) -> dict[tuple[str, str], str]:
    """Attach reviewer labels to (attempt, obligation), checking every binding.

    Pass earlier bindings as ``existing``: a slot is labelled once, across
    calls. Freezing labels before the key is opened is a procedure the caller
    owns; this function only refuses bindings that do not match the answers.
    """
    attempts = {attempt["attempt_id"]: attempt for attempt in run["attempts"]}
    bound: dict[tuple[str, str], str] = dict(existing or {})
    for label in labels:
        attempt = attempts.get(key.get(str(label.get("item_id")), ""))
        if attempt is None:
            raise ValueError(f"unknown review item {label.get('item_id')!r}")
        if label.get("answer_sha256") != attempt["answer_sha256"]:
            raise ValueError(f"label for {label.get('item_id')!r} is bound to a different answer")
        obligation = str(label.get("obligation_id"))
        if obligation not in attempt["stage_receipts"]:
            raise ValueError(f"unknown obligation {obligation!r} for {label.get('item_id')!r}")
        verdict = str(label.get("label"))
        if verdict not in REVIEW_LABELS:
            raise ValueError(f"label must be one of {REVIEW_LABELS}, got {verdict!r}")
        if not str(label.get("reviewer") or "").strip():
            raise ValueError("every label needs an accountable reviewer")
        slot = (attempt["attempt_id"], obligation)
        if slot in bound:
            raise ValueError(f"duplicate label for {slot}")
        bound[slot] = verdict
    return bound
