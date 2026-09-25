"""Blinded reviewer packets, a private assignment key, and exact label binding.

The packet shows each answered cell under a random opaque id, in random order,
with the case question, organizer criteria, world cutoff and the label fields
that case requires. It never contains arm names, memory state, cost, latency,
paths or answer digests that could be matched against the run root. The
private key maps each opaque id to one case, world, arm and answer digest.

Harness-written identifiers (study finding ids, the rehearsal expert name,
prompt section headings) are masked in the displayed text because an answer
that echoes them reveals which arms had memory. Masking is a form operation on
the harness's own markers; the key records both the exact answer digest and
the displayed-text digest so the binding stays exact.

Binding checks form only: every label names exactly one keyed answer, every
answered cell has exactly one label per reviewer file, and answer bytes still
match their digests. It does not judge the labels, verify reviewer identity, or
prove a reviewer could not infer an arm from the answer's substance.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from pathlib import Path
from typing import Any

from deepr.evals.expert_value import ARM_ORDER
from deepr.evals.expert_value_rehearsal_workbook import label_fields, world_label_context

KEY_SCHEMA = "deepr-expert-value-assignment-key-v1"
PACKET_SCHEMA = "deepr-expert-value-review-packet-v1"
BINDING_SCHEMA = "deepr-expert-value-label-binding-v1"
_HARNESS_MARKER = re.compile(
    r"\b[a-z_]+-[0-9a-f]{16}\b|rehearsal-expert|prior notes|expert memory|memory truncated|end notes",
    re.IGNORECASE,
)
MASK = "[harness marker removed]"


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _read_answer(run_root: Path, cell: dict[str, Any]) -> bytes:
    payload = Path(run_root, str(cell["answer_ref"])).read_bytes()
    if _sha(payload) != cell["answer_sha256"]:
        raise ValueError(f"answer bytes changed for {cell['acceptance_case_id']}/{cell['arm']}")
    return payload


def display_text(answer: str) -> tuple[str, int]:
    """Answer text with harness markers masked, and how many were masked."""
    return _HARNESS_MARKER.subn(MASK, answer)


def reviewer_criteria(
    blueprint: dict[str, Any],
    placement: dict[str, Any],
    cutoffs: dict[str, str],
    world_claims: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Reviewer-visible case material; arm policy and role drafts stay private.

    With ``world_claims``, each case also lists the label fields the value
    workbook requires for it, derived from its role and world, without naming
    the role.
    """
    placed = {case["acceptance_case_id"]: case for case in placement["cases"]}
    context = world_label_context(world_claims) if world_claims else None
    criteria: dict[str, dict[str, Any]] = {}
    for case in blueprint["acceptance_cases"]:
        world_id = placed[case["id"]]["source_world_id"]
        entry: dict[str, Any] = {
            "question": case["question"],
            "success_criteria": list(case.get("success_criteria", [])),
            "failure_conditions": list(case.get("failure_conditions", [])),
            "source_world_id": world_id,
            "information_cutoff": cutoffs[world_id],
        }
        if context is not None:
            role = placed[case["id"]].get("evaluation_role_draft", "")
            entry["label_fields"] = label_fields(role, **context[world_id])
        criteria[case["id"]] = entry
    return criteria


def load_cells(run_root: Path) -> list[dict[str, Any]]:
    cells = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((run_root / "cells").rglob("*.json"))]
    if not cells:
        raise ValueError("run root has no terminal cells")
    return cells


def _planned_pairs(run_root: Path) -> tuple[dict[str, Any], set[tuple[str, str, str]]]:
    """The finished run's summary and its planned (case, world, arm) cells."""
    summary_path, plan_path = run_root / "summary.json", run_root / "plan.json"
    if not summary_path.is_file() or not plan_path.is_file():
        raise ValueError("run root has no summary; blind only a run that finished or was stopped cleanly")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    pairs: set[tuple[str, str, str]] = {
        (str(c["case_id"]), str(c["source_world_id"]), str(arm)) for c in plan["cases"] for arm in ARM_ORDER
    }
    return dict(summary), pairs


def build_blind_assignment(
    run_root: Path, criteria: dict[str, dict[str, Any]], *, rubric: dict[str, Any] | None = None
) -> tuple[bytes, bytes]:
    """Return ``(packet_bytes, key_bytes)`` for one finished rehearsal run.

    Planned cells with no terminal record are listed as missing in the key, so
    the review denominator stays the planned matrix.
    """
    summary, planned = _planned_pairs(run_root)
    cells = load_cells(run_root)
    rng = secrets.SystemRandom()
    entries: list[dict[str, Any]] = []
    non_reviewable: list[dict[str, Any]] = []
    by_case: dict[str, list[dict[str, Any]]] = {}
    seen_pairs: set[tuple[str, str, str]] = set()
    for cell in cells:
        identity = {k: cell[k] for k in ("acceptance_case_id", "source_world_id", "arm")}
        seen_pairs.add((cell["acceptance_case_id"], cell["source_world_id"], cell["arm"]))
        if cell["status"] != "answered":
            non_reviewable.append({**identity, "status": cell["status"], "reason": cell.get("reason")})
            continue
        case = criteria.get(cell["acceptance_case_id"])
        if case is None:
            raise ValueError(f"no reviewer criteria for case {cell['acceptance_case_id']}")
        if cell.get("question_sha256") not in (None, _sha(case["question"].encode("utf-8"))):
            raise ValueError(f"case {cell['acceptance_case_id']} was answered for a different question")
        answer = _read_answer(run_root, cell)
        shown, masked = display_text(answer.decode("utf-8"))
        opaque = secrets.token_hex(8)
        while any(e["opaque_id"] == opaque for e in entries):
            opaque = secrets.token_hex(8)
        entries.append(
            {
                "opaque_id": opaque,
                **identity,
                "answer_ref": cell["answer_ref"],
                "answer_sha256": _sha(answer),
                "display_sha256": _sha(shown.encode("utf-8")),
                "masked_markers": masked,
            }
        )
        by_case.setdefault(cell["acceptance_case_id"], []).append({"opaque_id": opaque, "answer": shown})
    for case_id, world_id, arm in sorted(planned - seen_pairs):
        non_reviewable.append(
            {"acceptance_case_id": case_id, "source_world_id": world_id, "arm": arm, "status": "missing"}
        )
    case_ids = sorted(by_case)
    rng.shuffle(case_ids)
    packet_cases = []
    for case_id in case_ids:
        items = by_case[case_id]
        rng.shuffle(items)
        packet_cases.append({"case": criteria[case_id], "answers": items})
    packet = {
        "schema_version": PACKET_SCHEMA,
        "instructions": (
            "Score each answer independently against its case criteria and the frozen sources, "
            "filling exactly the label fields listed for its case. Answers are shown in random order "
            "under random ids; some had internal harness markers removed. If you suspect how an "
            "answer was produced, write it in `suspected_production` before the key is revealed, "
            "and do not let it change the score. Do not open the run root."
        ),
        "rubric": rubric or {},
        "cases": packet_cases,
    }
    packet_bytes = _canonical(packet)
    leaked = [arm for arm in ARM_ORDER if arm.encode("utf-8") in packet_bytes]
    if leaked:
        raise ValueError(f"reviewer packet contains arm identifiers: {', '.join(leaked)}")
    key = {
        "schema_version": KEY_SCHEMA,
        "packet_sha256": _sha(packet_bytes),
        "run_status": summary.get("status"),
        "entries": sorted(entries, key=lambda e: e["opaque_id"]),
        "non_reviewable": non_reviewable,
        "planned_cells": len(planned),
        "terminal_cells": len(cells),
        "reviewable_cells": len(entries),
        "answers_with_masked_markers": sum(1 for e in entries if e["masked_markers"]),
    }
    return packet_bytes, _canonical(key)


def _one_label_per_answer(entries: dict[str, dict[str, Any]], labels: list[Any]) -> dict[str, dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for label in labels:
        opaque = label.get("opaque_id")
        if opaque not in entries:
            raise ValueError(f"label refers to an unknown answer id: {opaque!r}")
        if opaque in seen:
            raise ValueError(f"answer {opaque} has more than one label from this reviewer")
        shown = label.get("display_sha256", label.get("answer_sha256"))
        if shown not in (None, entries[opaque]["display_sha256"], entries[opaque]["answer_sha256"]):
            raise ValueError(f"label for {opaque} was made against different answer bytes")
        seen[opaque] = label
    missing = sorted(set(entries) - set(seen))
    if missing:
        raise ValueError(f"{len(missing)} reviewable answer(s) have no label")
    return seen


def bind_review_labels(run_root: Path, key_bytes: bytes, packet_bytes: bytes, labels_bytes: bytes) -> dict[str, Any]:
    """Join frozen labels to the private key after checking one-to-one binding."""
    key = json.loads(key_bytes)
    if key.get("schema_version") != KEY_SCHEMA:
        raise ValueError("not an assignment key")
    if key["packet_sha256"] != _sha(packet_bytes):
        raise ValueError("labels were collected against a different reviewer packet")
    labels = json.loads(labels_bytes)
    reviewer = labels.get("reviewer") or {}
    if not isinstance(reviewer.get("id"), str) or not reviewer["id"].strip():
        raise ValueError("labels must name a reviewer id")
    entries = {entry["opaque_id"]: entry for entry in key["entries"]}
    seen = _one_label_per_answer(entries, labels.get("labels", []))
    joined = []
    for opaque, entry in sorted(entries.items()):
        current = (run_root / entry["answer_ref"]).read_bytes()
        if _sha(current) != entry["answer_sha256"]:
            raise ValueError(f"answer bytes for {opaque} changed after assignment")
        joined.append({**entry, "label": {k: v for k, v in seen[opaque].items() if k != "opaque_id"}})
    return {
        "schema_version": BINDING_SCHEMA,
        "status": "labels_bound",
        "packet_sha256": key["packet_sha256"],
        "key_sha256": _sha(key_bytes),
        "labels_sha256": _sha(labels_bytes),
        "reviewer": {"id": reviewer["id"], "identity_verified": False},
        "bound": joined,
        "non_reviewable": key["non_reviewable"],
        "semantic_scores_validated": False,
        "arm_inference_excluded": False,
    }


__all__ = ["bind_review_labels", "build_blind_assignment", "display_text", "load_cells", "reviewer_criteria"]
