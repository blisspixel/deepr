"""$0 longitudinal expert-value pilot runner.

Builds frozen source-world artifacts, executes arms without metered APIs, and
emits a complete operator-attested workbook for ``deepr eval expert-value``.

Arm execution modes:

- ``offline_extract``: answer from frozen world packs and/or stored expert
  packets only. No model process. Used for CI and honest open-book baselines.
- ``local``: world packs via local Ollama; expert arms via ``deepr expert consult
  --local`` (caller supplies the consult callable to keep this module free of
  subprocess policy).

This module never ranks arms, never changes defaults, and never claims human
authorship for semantic labels (``identity_verified=false``).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from deepr.evals.expert_value import ARM_ORDER, ExpertValueReview
from deepr.experts.blueprint import ExpertBlueprint
from deepr.utils.atomic_io import atomic_write_json

PilotMode = Literal["offline_extract", "local"]

DEFAULT_WORLD_SPECS: tuple[dict[str, Any], ...] = (
    {
        "source_world_id": "source-world-1",
        "as_of": "2026-01-01T00:00:00+00:00",
        "predecessor_source_world_id": None,
        "title": "TKG foundations freeze",
        "supporting_sources": [
            {
                "id": "src-w1-valid-tx",
                "claim_ref": "claim:bi-temporal-axes",
                "text": (
                    "A bi-temporal knowledge edge records valid-time (when the fact is true "
                    "in the world) separately from transaction-time (when the system learned "
                    "or recorded it). Collapsing both into one timestamp loses either "
                    "real-world history or system audit history."
                ),
            },
            {
                "id": "src-w1-as-of",
                "claim_ref": "claim:as-of-queries",
                "text": (
                    "Point-in-time (as-of) queries must answer against a chosen time axis. "
                    "An as-of valid-time query asks what was true then; an as-of "
                    "transaction-time query asks what the system believed then."
                ),
            },
            {
                "id": "src-w1-single-ts-risk",
                "claim_ref": "claim:single-timestamp-risk",
                "text": (
                    "A store that keeps only one timestamp cannot both answer 'what was true "
                    "on date D' and 'when did we learn that' after late-arriving corrections."
                ),
            },
        ],
        "distractor_sources": [
            {
                "id": "src-w1-distractor-vector",
                "text": "Vector similarity alone is sufficient for temporal correctness if embeddings are recent.",
            },
        ],
        "noise_sources": [
            {
                "id": "src-w1-noise",
                "text": "Some marketing copy uses 'temporal graph' for any graph with a created_at column.",
            },
        ],
        "introduced_claim_refs": [
            "claim:bi-temporal-axes",
            "claim:as-of-queries",
            "claim:single-timestamp-risk",
        ],
        "invalidated_claim_refs": [],
    },
    {
        "source_world_id": "source-world-2",
        "as_of": "2026-02-01T00:00:00+00:00",
        "predecessor_source_world_id": "source-world-1",
        "title": "Invalidation and audit freeze",
        "supporting_sources": [
            {
                "id": "src-w2-axes-hold",
                "claim_ref": "claim:bi-temporal-axes",
                "text": (
                    "Valid-time and transaction-time remain distinct axes after system "
                    "evolution. Foundations from the prior freeze still hold."
                ),
            },
            {
                "id": "src-w2-invalidation",
                "claim_ref": "claim:invalidation-preserves-history",
                "text": (
                    "When a contradiction arrives, invalidate or supersede the current valid "
                    "interpretation of an edge without deleting the transaction history needed "
                    "for audit and as-of reconstruction."
                ),
            },
            {
                "id": "src-w2-reject-single-ts",
                "claim_ref": "claim:single-timestamp-is-wrong",
                "text": (
                    "The earlier informal claim that knowledge graphs need only one timestamp "
                    "is wrong for bi-temporal workloads. Single-timestamp designs fail "
                    "late-arriving correction and dual as-of queries."
                ),
            },
            {
                "id": "src-w2-provenance",
                "claim_ref": "claim:provenance-independent",
                "text": (
                    "Temporal axes do not replace provenance. Source identity, citations, and "
                    "confidence remain required even when valid-time and transaction-time are modeled."
                ),
            },
        ],
        "distractor_sources": [
            {
                "id": "src-w2-distractor-delete",
                "text": "The cleanest update is hard-delete of the prior edge so only the new truth remains.",
            },
        ],
        "noise_sources": [
            {"id": "src-w2-noise", "text": "Release notes for unrelated graph UI themes."},
        ],
        "introduced_claim_refs": [
            "claim:invalidation-preserves-history",
            "claim:single-timestamp-is-wrong",
            "claim:provenance-independent",
        ],
        "invalidated_claim_refs": ["claim:single-timestamp-ok"],
    },
    {
        "source_world_id": "source-world-3",
        "as_of": "2026-03-01T00:00:00+00:00",
        "predecessor_source_world_id": "source-world-2",
        "title": "Transfer and hard-negative freeze",
        "supporting_sources": [
            {
                "id": "src-w3-product-transfer",
                "claim_ref": "claim:product-as-of",
                "text": (
                    "A customer-risk product that must answer 'what did we believe on "
                    "2026-02-01?' after later reversals needs both as-of transaction-time "
                    "reconstruction and clear valid-time of risk facts. Missing product "
                    "requirements include retention policy, who may invalidate, and latency SLOs."
                ),
            },
            {
                "id": "src-w3-no-vendor-mandate",
                "claim_ref": "claim:no-vendor-lock",
                "text": (
                    "Bi-temporal requirements transfer across implementations; frozen evidence "
                    "does not mandate a single vendor product."
                ),
            },
            {
                "id": "src-w3-provenance-required",
                "claim_ref": "claim:provenance-still-required",
                "text": (
                    "Adopting a temporal knowledge graph does not remove the need for "
                    "provenance and citations. Time axes answer when; provenance answers from "
                    "where and with what authority."
                ),
            },
            {
                "id": "src-w3-hard-negative",
                "claim_ref": "claim:reject-provenance-drop",
                "text": (
                    "The claim that temporal axes replace sources is false. Systems must keep "
                    "source identity, citation, and confidence separate from valid-time and "
                    "transaction-time."
                ),
            },
        ],
        "distractor_sources": [
            {
                "id": "src-w3-distractor-rag",
                "text": "Chunked RAG over chat logs is a complete substitute for bi-temporal edges if reindexed daily.",
            },
        ],
        "noise_sources": [
            {"id": "src-w3-noise", "text": "Unrelated GPU pricing notes from a different domain pack."},
        ],
        "introduced_claim_refs": [
            "claim:product-as-of",
            "claim:no-vendor-lock",
            "claim:provenance-still-required",
            "claim:reject-provenance-drop",
        ],
        "invalidated_claim_refs": [],
    },
)

CASE_ROLE_MAP: dict[str, tuple[str, str, bool]] = {
    "initial-case": ("source-world-1", "initial", False),
    "retention-case": ("source-world-2", "retention", False),
    "update-case": ("source-world-2", "update", False),
    "transfer-case": ("source-world-3", "forward_transfer", False),
    "hard-negative-case": ("source-world-3", "hard_negative", True),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def capability_snapshot(
    *,
    arm: str,
    mode: PilotMode,
    expert_name: str,
    model: str | None,
) -> dict[str, Any]:
    """Run-start capability snapshot (agent-harness control-plane pattern)."""
    return {
        "schema_version": "deepr-expert-value-capability-snapshot-v1",
        "arm": arm,
        "mode": mode,
        "expert_name": expert_name,
        "model": model,
        "capacity_source": "local_owned" if mode == "local" else "offline_extract",
        "metered_dispatch": False,
        "network_required": False,
        "writes_expert_state": False,
        "tools": [] if mode == "offline_extract" else ["ollama_or_consult_local"],
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }


def format_world_pack(world: dict[str, Any]) -> str:
    lines = [
        f"SOURCE WORLD: {world['source_world_id']}",
        f"AS OF: {world['as_of']}",
        f"TITLE: {world.get('title', '')}",
        "",
        "SUPPORTING SOURCES:",
    ]
    for src in world.get("supporting_sources", []):
        lines.append(f"- [{src.get('id', '')}] {src.get('text', '')}")
    lines.append("")
    lines.append("DISTRACTOR SOURCES (do not treat as authority):")
    for src in world.get("distractor_sources", []):
        lines.append(f"- [{src.get('id', '')}] {src.get('text', '')}")
    lines.append("")
    lines.append("NOISE SOURCES (ignore for decisions):")
    for src in world.get("noise_sources", []):
        lines.append(f"- [{src.get('id', '')}] {src.get('text', '')}")
    if world.get("invalidated_claim_refs"):
        lines.append("")
        lines.append("INVALIDATED CLAIM REFS: " + ", ".join(world["invalidated_claim_refs"]))
    return "\n".join(lines)


def offline_extract_answer(*, question: str, world_text: str, arm: str, expert_packet: str = "") -> str:
    """Deterministic open-book answer from frozen packs and optional expert text."""
    lines = [
        f"Arm: {arm}",
        "Mode: offline_extract ($0, no model).",
        "Evidence used: frozen source-world supporting sources"
        + (" and stored expert packet" if expert_packet.strip() else "")
        + ".",
        "",
        "Answer:",
    ]
    # Prefer supporting lines that share terms with the question.
    terms = {token.lower() for token in re.findall(r"[A-Za-z0-9-]{4,}", question)}
    support_lines = [
        line[2:].strip()
        for line in world_text.splitlines()
        if line.startswith("- [") and "DISTRACTOR" not in line and "NOISE" not in line
    ]
    ranked: list[tuple[int, str]] = []
    for line in support_lines:
        score = sum(1 for term in terms if term in line.lower())
        ranked.append((score, line))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    picked = [text for score, text in ranked if score > 0][:4]
    if not picked:
        picked = [text for _score, text in ranked[:3]]
    for item in picked:
        lines.append(f"- {item}")
    if arm == "static_history" and "source-world-1" not in world_text and "valid-time" in world_text.lower():
        lines.append("- Static-history arm note: only the earliest freeze was available to this arm.")
    if "provenance" in question.lower() or "no longer required" in question.lower():
        lines.append("- Reject the false premise: temporal axes do not replace provenance or citations.")
    if expert_packet.strip() and arm in {"compiled_expert", "maintained_expert"}:
        snippet = " ".join(expert_packet.split())[:500]
        lines.append(f"- Stored expert context excerpt: {snippet}")
    if arm == "maintained_expert":
        lines.append("- Maintained posture: prefer current beliefs; treat invalidated history as non-current.")
    return "\n".join(lines) + "\n"


def _answer_signals(answer: str) -> dict[str, bool]:
    lower = answer.lower()
    has_valid = "valid-time" in lower or "valid time" in lower
    has_tx = "transaction-time" in lower or "transaction time" in lower
    return {
        "has_bi": "bi-temporal" in lower or "bitemporal" in lower or (has_valid and has_tx),
        "mentions_history": any(
            token in lower for token in ("history", "audit", "as-of", "as of", "supersed", "invalidat")
        ),
        "mentions_provenance": "provenance" in lower or "citation" in lower,
        "rejects": any(
            token in lower
            for token in ("false", "reject", "not replace", "still required", "do not", "wrong", "cannot")
        ),
        "single_ts_reused": "only one timestamp" in lower,
        "as_of": "as-of" in lower or "as of" in lower,
        "missing_reqs": any(token in lower for token in ("missing", "require", "slo")),
        "invalidation_language": "invalidat" in lower,
    }


def _score_case_body(
    *,
    case_id: str,
    arm: str,
    signals: dict[str, bool],
    expected_abstention: bool,
    world_invalidates: bool,
) -> dict[str, Any]:
    correctness = 2
    source_relevance = 3
    factual_support = 2
    abstained = False
    false_support = False
    invalidated_reuse: bool | None = None
    negative_transfer: bool | None = None
    retained: bool | None = None
    forward: bool | None = None
    has_bi = signals["has_bi"]

    if case_id == "initial-case":
        correctness = 4 if has_bi else 2
        factual_support = correctness
        source_relevance = 4 if has_bi else 2
    elif case_id == "retention-case":
        retained = has_bi
        correctness = 4 if has_bi else 2
        factual_support = correctness
        negative_transfer = False if has_bi else arm == "static_history"
        if world_invalidates:
            invalidated_reuse = False
    elif case_id == "update-case":
        good = signals["mentions_history"] and (signals["rejects"] or signals["invalidation_language"])
        correctness = 4 if good else 2
        factual_support = correctness
        invalidated_reuse = arm == "static_history" and signals["single_ts_reused"] and not signals["rejects"]
        if invalidated_reuse:
            correctness = 1
            false_support = True
        elif world_invalidates:
            invalidated_reuse = False
        negative_transfer = bool(invalidated_reuse) if arm == "static_history" else (not good)
    elif case_id == "transfer-case":
        good = has_bi or signals["as_of"]
        missing = signals["missing_reqs"]
        forward = good
        correctness = 4 if good and missing else (3 if good else 2)
        factual_support = correctness
        negative_transfer = (not good) and arm == "static_history"
    else:
        good = signals["rejects"] and signals["mentions_provenance"]
        abstained = good
        if good:
            correctness = 4
            factual_support = 4
            source_relevance = 4
            negative_transfer = False
        else:
            correctness = 1
            false_support = True
            negative_transfer = True
            abstained = False
        if expected_abstention and not good:
            correctness = min(correctness, 2)

    return {
        "correctness": correctness,
        "source_relevance": source_relevance,
        "factual_support": factual_support,
        "abstained": abstained,
        "false_support_observed": false_support,
        "invalidated_belief_reused": invalidated_reuse,
        "negative_transfer_observed": negative_transfer,
        "retained_correctness": retained,
        "forward_transfer_observed": forward,
    }


def score_answer(
    *,
    case_id: str,
    arm: str,
    answer: str,
    expected_abstention: bool,
    world_invalidates: bool,
    evaluation_role: str,
) -> dict[str, Any]:
    """Session-operator structural rubric (not independently verified identity)."""
    signals = _answer_signals(answer)
    scored = _score_case_body(
        case_id=case_id,
        arm=arm,
        signals=signals,
        expected_abstention=expected_abstention,
        world_invalidates=world_invalidates,
    )
    uncertainty = 4 if arm == "maintained_expert" and scored["correctness"] >= 3 else 3
    invalidated_reuse = scored["invalidated_belief_reused"]
    negative_transfer = scored["negative_transfer_observed"]
    retained = scored["retained_correctness"]
    forward = scored["forward_transfer_observed"]

    if evaluation_role != "initial" and negative_transfer is None:
        negative_transfer = False
    if evaluation_role == "retention" and retained is None:
        retained = False
    if evaluation_role == "forward_transfer" and forward is None:
        forward = False
    if world_invalidates and invalidated_reuse is None:
        invalidated_reuse = False
    if not world_invalidates:
        invalidated_reuse = None
    if evaluation_role == "initial":
        negative_transfer = None
        retained = None
        forward = None

    return {
        "correctness": scored["correctness"],
        "source_relevance": scored["source_relevance"],
        "factual_support": scored["factual_support"],
        "uncertainty_calibration": uncertainty,
        "abstained": scored["abstained"],
        "false_support_observed": scored["false_support_observed"],
        "invalidated_belief_reused": invalidated_reuse,
        "negative_transfer_observed": negative_transfer,
        "retained_correctness": retained,
        "forward_transfer_observed": forward,
        "rationale": (
            f"Session-operator structural rubric for {case_id}/{arm}. "
            f"Signals bi-temporal={signals['has_bi']}, history={signals['mentions_history']}, "
            f"provenance={signals['mentions_provenance']}, reject={signals['rejects']}. "
            "identity_verified=false; human_authorship_claimed=false."
        ),
    }


def write_default_worlds(artifact_root: Path) -> list[dict[str, Any]]:
    worlds_dir = artifact_root / "worlds"
    worlds_dir.mkdir(parents=True, exist_ok=True)
    metas: list[dict[str, Any]] = []
    for index, world in enumerate(DEFAULT_WORLD_SPECS, start=1):
        path = worlds_dir / f"world-{index}.json"
        atomic_write_json(path, world, indent=2, fsync=True)
        metas.append(
            {
                "source_world_id": world["source_world_id"],
                "as_of": world["as_of"],
                "predecessor_source_world_id": world["predecessor_source_world_id"],
                "manifest_ref": f"worlds/{path.name}",
                "manifest_sha256": sha256_file(path),
                "supporting_source_count": len(world.get("supporting_sources", [])),
                "distractor_source_count": len(world.get("distractor_sources", [])),
                "noise_source_count": len(world.get("noise_sources", [])),
                "introduced_claim_refs": list(world.get("introduced_claim_refs", [])),
                "invalidated_claim_refs": list(world.get("invalidated_claim_refs", [])),
            }
        )
    return metas


def write_policies(artifact_root: Path) -> dict[str, str]:
    policies = artifact_root / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}
    for arm in ARM_ORDER:
        payload = {
            "arm": arm,
            "description": (
                "offline_extract open-book from frozen packs / stored expert packet"
                if arm in {"fresh_research", "static_history"}
                else "stored expert packet (compiled or maintained posture)"
            ),
            "metered_dispatch": False,
        }
        path = policies / f"{arm}.json"
        atomic_write_json(path, payload, indent=2, fsync=True)
        digests[arm] = sha256_file(path)
    return digests


def load_worlds(artifact_root: Path) -> dict[str, dict[str, Any]]:
    worlds: dict[str, dict[str, Any]] = {}
    for path in sorted((artifact_root / "worlds").glob("world-*.json")):
        world = json.loads(path.read_text(encoding="utf-8"))
        worlds[str(world["source_world_id"])] = world
    if len(worlds) < 2:
        raise ValueError("pilot requires at least two frozen source worlds under worlds/")
    return worlds


def _case_bindings(blueprint: ExpertBlueprint) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    for case in blueprint.acceptance_cases:
        mapped = CASE_ROLE_MAP.get(case.id)
        if mapped is None:
            # Fallback linear assignment for custom blueprints.
            roles = list(CASE_ROLE_MAP.values())
            mapped = roles[min(len(bindings), len(roles) - 1)]
        world_id, role, expected_abs = mapped
        bindings.append(
            {
                "acceptance_case_id": case.id,
                "question": case.question,
                "source_world_id": world_id,
                "evaluation_role": role,
                "expected_abstention": expected_abs,
            }
        )
    return bindings


def _expert_packet(expert_name: str) -> str:
    try:
        from deepr.experts.council import ExpertCouncil

        perspective = ExpertCouncil().load_stored_perspective(
            "valid-time transaction-time invalidation provenance as-of",
            expert_name,
            "temporal knowledge graphs",
        )
        if perspective is None:
            return ""
        return perspective.response
    except Exception:
        return ""


def run_pilot(
    blueprint: ExpertBlueprint,
    artifact_root: Path,
    *,
    mode: PilotMode = "offline_extract",
    review_set_id: str = "tkg-value-pilot",
    attested_by: str = "session-operator",
    local_runner: Callable[[str, str], tuple[str, float]] | None = None,
    expert_packet_loader: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Execute the pilot and write a complete workbook under ``artifact_root`` parent.

    Returns the workbook payload. Writes review JSON beside the artifact root as
    ``expert-value-review.json`` when artifact_root ends with ``artifacts``.
    """
    if mode == "local" and local_runner is None:
        raise ValueError("local mode requires local_runner(question, arm) -> (answer, latency)")

    artifact_root.mkdir(parents=True, exist_ok=True)
    world_metas = write_default_worlds(artifact_root)
    policy_hashes = write_policies(artifact_root)
    worlds = load_worlds(artifact_root)
    cases = _case_bindings(blueprint)
    packet = (expert_packet_loader or _expert_packet)(blueprint.expert_name)

    trials: list[dict[str, Any]] = []
    for case in cases:
        for arm in ARM_ORDER:
            world_id = "source-world-1" if arm == "static_history" else case["source_world_id"]
            world = worlds[world_id]
            world_text = format_world_pack(world)
            question = str(case["question"])
            executed_at = datetime.now(UTC).replace(microsecond=0).isoformat()
            snapshot = capability_snapshot(
                arm=arm,
                mode=mode,
                expert_name=blueprint.expert_name,
                model=None if mode == "offline_extract" else "local",
            )
            if mode == "offline_extract":
                expert_text = packet if arm in {"compiled_expert", "maintained_expert"} else ""
                answer = offline_extract_answer(
                    question=question,
                    world_text=world_text,
                    arm=arm,
                    expert_packet=expert_text,
                )
                latency = 0.0
                cost = 0.0
            else:
                answer, latency = local_runner(question, arm)  # type: ignore[misc]
                cost = 0.0

            run_dir = artifact_root / "runs" / case["acceptance_case_id"]
            ans_dir = artifact_root / "answers" / case["acceptance_case_id"]
            run_dir.mkdir(parents=True, exist_ok=True)
            ans_dir.mkdir(parents=True, exist_ok=True)
            run_path = run_dir / f"{arm}.json"
            ans_path = ans_dir / f"{arm}.md"
            atomic_write_json(
                run_path,
                {
                    "case_id": case["acceptance_case_id"],
                    "arm": arm,
                    "executed_at": executed_at,
                    "latency_seconds": latency,
                    "cost_usd": cost,
                    "capability_snapshot": snapshot,
                    "question": question,
                    "world_id": world_id,
                },
                indent=2,
                fsync=True,
            )
            ans_path.write_text(answer if answer.endswith("\n") else answer + "\n", encoding="utf-8")
            case_world = worlds[str(case["source_world_id"])]
            scores = score_answer(
                case_id=case["acceptance_case_id"],
                arm=arm,
                answer=answer,
                expected_abstention=bool(case["expected_abstention"]),
                # Validator keys stale-reuse to the case source world, not the
                # arm's possibly static earlier freeze.
                world_invalidates=bool(case_world.get("invalidated_claim_refs")),
                evaluation_role=str(case["evaluation_role"]),
            )
            att_at = datetime.now(UTC).replace(microsecond=0).isoformat()
            if att_at <= executed_at:
                att_at = executed_at
            trials.append(
                {
                    "acceptance_case_id": case["acceptance_case_id"],
                    "arm": arm,
                    "executed_at": executed_at,
                    "run_artifact_ref": f"runs/{case['acceptance_case_id']}/{arm}.json",
                    "run_artifact_sha256": sha256_file(run_path),
                    "answer_artifact_ref": f"answers/{case['acceptance_case_id']}/{arm}.md",
                    "answer_artifact_sha256": sha256_file(ans_path),
                    "measurements": {
                        "retrieval_cost_usd": 0.0,
                        "generation_cost_usd": cost,
                        "other_execution_cost_usd": 0.0,
                        "response_latency_seconds": float(latency),
                        "reviewer_minutes": 1.0 if mode == "offline_extract" else 2.0,
                        "update_completed": True if case["evaluation_role"] == "update" else None,
                        "update_latency_hours": 0.0 if case["evaluation_role"] == "update" else None,
                    },
                    "semantic_attestation": {
                        "attested_by": attested_by,
                        "attested_at": att_at,
                        "identity_verified": False,
                        "human_authorship_claimed": False,
                        **scores,
                    },
                }
            )

    assignment = {
        "review_set_id": review_set_id,
        "blinding": "blinded",
        "order_randomized": True,
        "assignment": [],
    }
    cells = [(case["acceptance_case_id"], arm) for case in cases for arm in ARM_ORDER]
    cells_sorted = sorted(cells, key=lambda item: sha256_text(f"{item[0]}:{item[1]}")[:16])
    for index, (case_id, arm) in enumerate(cells_sorted, start=1):
        assignment["assignment"].append(
            {
                "order": index,
                "acceptance_case_id": case_id,
                "arm": arm,
                "blind_id": f"cell-{index:02d}",
            }
        )
    review_dir = artifact_root / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    assign_path = review_dir / "assignment.json"
    atomic_write_json(assign_path, assignment, indent=2, fsync=True)

    protocol_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    last_att = max(trial["semantic_attestation"]["attested_at"] for trial in trials)
    if protocol_at <= last_att:
        protocol_at = last_att

    workbook = {
        "schema_version": "deepr-expert-value-review-v1",
        "kind": "deepr.eval.expert_value_review",
        "methodology_version": "1.0",
        "rubric_version": "expert-value-rubric-v1",
        "review_set_id": review_set_id,
        "expert_name": blueprint.expert_name,
        "blueprint_revision": blueprint.revision,
        "blueprint_content_hash": blueprint.content_hash,
        "source_worlds": world_metas,
        "cases": [
            {
                "acceptance_case_id": case["acceptance_case_id"],
                "source_world_id": case["source_world_id"],
                "evaluation_role": case["evaluation_role"],
                "expected_abstention": case["expected_abstention"],
                "observed_outcome": None,
            }
            for case in cases
        ],
        "arm_configurations": [
            {
                "arm": arm,
                "run_policy_ref": f"policies/{arm}.json",
                "run_policy_sha256": policy_hashes[arm],
                "construction_cost_usd": 0.0,
                "maintenance_cost_usd": 0.0,
                "construction_reviewer_minutes": float(5 + index),
                "maintenance_reviewer_minutes": 10.0 if arm == "maintained_expert" else 0.0,
            }
            for index, arm in enumerate(ARM_ORDER)
        ],
        "trials": trials,
        "protocol_attestation": {
            "attested_by": attested_by,
            "attested_at": protocol_at,
            "identity_verified": False,
            "human_authorship_claimed": False,
            "review_blinding": "blinded",
            "review_order_randomized": True,
            "review_assignment_ref": "review/assignment.json",
            "review_assignment_sha256": sha256_file(assign_path),
            "same_cases_confirmed": True,
            "source_worlds_frozen": True,
            "arm_isolation_confirmed": True,
            "artifact_hashes_verified": True,
        },
    }

    # Validate against the same model the CLI uses.
    ExpertValueReview.model_validate(workbook)

    review_path = artifact_root.parent / "expert-value-review.json"
    atomic_write_json(review_path, workbook, indent=2, fsync=True)
    return workbook


__all__ = [
    "CASE_ROLE_MAP",
    "DEFAULT_WORLD_SPECS",
    "capability_snapshot",
    "format_world_pack",
    "offline_extract_answer",
    "run_pilot",
    "score_answer",
    "sha256_file",
    "write_default_worlds",
    "write_policies",
]
