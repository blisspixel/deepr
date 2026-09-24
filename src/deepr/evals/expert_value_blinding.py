"""Blinded reviewer packets, a private assignment key, and exact label binding.

The packet shows each answered cell's exact answer bytes under a random opaque
id, in random order, with the case question, organizer criteria and world
cutoff. It never contains arm names, memory state, cost, latency or paths. The
private key maps each opaque id to one case, world, arm and answer digest.

Binding checks form only: every label names exactly one keyed answer, every
answered cell has exactly one label per reviewer file, and answer bytes still
match their digests. It does not judge the labels, verify reviewer identity, or
prove a reviewer could not infer an arm from the answer text.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path
from typing import Any

from deepr.evals.expert_value import ARM_ORDER

KEY_SCHEMA = "deepr-expert-value-assignment-key-v1"
PACKET_SCHEMA = "deepr-expert-value-review-packet-v1"
BINDING_SCHEMA = "deepr-expert-value-label-binding-v1"


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _read_answer(run_root: Path, cell: dict[str, Any]) -> bytes:
    payload = Path(run_root, str(cell["answer_ref"])).read_bytes()
    if _sha(payload) != cell["answer_sha256"]:
        raise ValueError(f"answer bytes changed for {cell['acceptance_case_id']}/{cell['arm']}")
    return payload


def reviewer_criteria(
    blueprint: dict[str, Any], placement: dict[str, Any], cutoffs: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """Reviewer-visible case material; arm policy and role drafts stay private."""
    worlds = {case["acceptance_case_id"]: case["source_world_id"] for case in placement["cases"]}
    return {
        case["id"]: {
            "question": case["question"],
            "success_criteria": list(case.get("success_criteria", [])),
            "failure_conditions": list(case.get("failure_conditions", [])),
            "source_world_id": worlds[case["id"]],
            "information_cutoff": cutoffs[worlds[case["id"]]],
        }
        for case in blueprint["acceptance_cases"]
    }


def load_cells(run_root: Path) -> list[dict[str, Any]]:
    cells = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((run_root / "cells").rglob("*.json"))]
    if not cells:
        raise ValueError("run root has no terminal cells")
    return cells


def build_blind_assignment(
    run_root: Path, criteria: dict[str, dict[str, Any]], *, rubric: dict[str, Any] | None = None
) -> tuple[bytes, bytes]:
    """Return ``(packet_bytes, key_bytes)`` for one completed rehearsal run.

    ``criteria`` maps case id to the reviewer-visible question, success
    criteria, failure conditions and information cutoff.
    """
    cells = load_cells(run_root)
    rng = secrets.SystemRandom()
    entries: list[dict[str, Any]] = []
    non_reviewable: list[dict[str, Any]] = []
    by_case: dict[str, list[dict[str, Any]]] = {}
    used: set[str] = set()
    for cell in cells:
        identity = {k: cell[k] for k in ("acceptance_case_id", "source_world_id", "arm")}
        if cell["status"] != "answered":
            non_reviewable.append({**identity, "status": cell["status"], "reason": cell.get("reason")})
            continue
        if cell["acceptance_case_id"] not in criteria:
            raise ValueError(f"no reviewer criteria for case {cell['acceptance_case_id']}")
        opaque = secrets.token_hex(8)
        while opaque in used:
            opaque = secrets.token_hex(8)
        used.add(opaque)
        answer = _read_answer(run_root, cell)
        entries.append(
            {"opaque_id": opaque, **identity, "answer_ref": cell["answer_ref"], "answer_sha256": _sha(answer)}
        )
        by_case.setdefault(cell["acceptance_case_id"], []).append(
            {"opaque_id": opaque, "answer": answer.decode("utf-8"), "answer_sha256": _sha(answer)}
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
            "Score each answer independently against its case criteria and sources. Answers are "
            "shown in random order under random ids. Record any guess about how an answer was "
            "produced separately; do not let it change the score."
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
        "entries": sorted(entries, key=lambda e: e["opaque_id"]),
        "non_reviewable": non_reviewable,
        "terminal_cells": len(cells),
        "reviewable_cells": len(entries),
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
        if label.get("answer_sha256") not in (None, entries[opaque]["answer_sha256"]):
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


__all__ = ["bind_review_labels", "build_blind_assignment", "load_cells", "reviewer_criteria"]
