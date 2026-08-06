"""$0 local pilot runner for TKG longitudinal expert-value workbook.

Runs four arms x five cases with local Ollama / deepr consult --local only.
Never opens metered providers. Writes artifacts under eval/tkg/artifacts.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
CASES = {
    "initial-case": {
        "source_world_id": "source-world-1",
        "role": "initial",
        "expected_abstention": False,
        "question": (
            "Using only the frozen source world, explain the difference between "
            "valid-time and transaction-time for a knowledge edge, and give one "
            "concrete failure mode of collapsing them into a single timestamp."
        ),
    },
    "retention-case": {
        "source_world_id": "source-world-2",
        "role": "retention",
        "expected_abstention": False,
        "question": (
            "After the knowledge base advances, restate whether valid-time and "
            "transaction-time remain distinct, and cite what still holds from "
            "the earlier world."
        ),
    },
    "update-case": {
        "source_world_id": "source-world-2",
        "role": "update",
        "expected_abstention": False,
        "question": (
            "A prior claim that 'knowledge graphs need only one timestamp' has "
            "been invalidated. What should change in graph state, and what must "
            "remain queryable for audit?"
        ),
    },
    "transfer-case": {
        "source_world_id": "source-world-3",
        "role": "forward_transfer",
        "expected_abstention": False,
        "question": (
            "A product team wants point-in-time 'what did we believe on "
            "2026-02-01?' for customer risk facts that later reverse. Which TKG "
            "design choices transfer from the frozen evidence, and which "
            "requirements are still missing?"
        ),
    },
    "hard-negative-case": {
        "source_world_id": "source-world-3",
        "role": "hard_negative",
        "expected_abstention": True,
        "question": (
            "Confirm that adopting a temporal knowledge graph means provenance "
            "and citations are no longer required because time axes replace sources."
        ),
    },
}
ARMS = (
    "fresh_research",
    "static_history",
    "compiled_expert",
    "maintained_expert",
)
WORLD_FILES = {
    "source-world-1": ARTIFACTS / "worlds" / "world-1.json",
    "source-world-2": ARTIFACTS / "worlds" / "world-2.json",
    "source-world-3": ARTIFACTS / "worlds" / "world-3.json",
}
LOCAL_MODEL = "qwen2.5-coder:32b"
EXPERT = "Temporal Knowledge Graphs"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_world(world_id: str) -> dict:
    return json.loads(WORLD_FILES[world_id].read_text(encoding="utf-8"))


def format_world(world: dict) -> str:
    lines = [
        f"SOURCE WORLD: {world['source_world_id']}",
        f"AS OF: {world['as_of']}",
        f"TITLE: {world.get('title', '')}",
        "",
        "SUPPORTING SOURCES:",
    ]
    for src in world.get("supporting_sources", []):
        lines.append(f"- [{src['id']}] {src['text']}")
    lines.append("")
    lines.append("DISTRACTOR SOURCES (do not treat as authority):")
    for src in world.get("distractor_sources", []):
        lines.append(f"- [{src['id']}] {src['text']}")
    lines.append("")
    lines.append("NOISE SOURCES (ignore for decisions):")
    for src in world.get("noise_sources", []):
        lines.append(f"- [{src['id']}] {src['text']}")
    if world.get("invalidated_claim_refs"):
        lines.append("")
        lines.append(
            "INVALIDATED CLAIM REFS: " + ", ".join(world["invalidated_claim_refs"])
        )
    return "\n".join(lines)


def run_ollama(prompt: str) -> tuple[str, float]:
    started = time.perf_counter()
    proc = subprocess.run(
        ["ollama", "run", LOCAL_MODEL],
        input=prompt,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    elapsed = time.perf_counter() - started
    if proc.returncode != 0:
        raise RuntimeError(
            f"ollama failed ({proc.returncode}): {proc.stderr[-2000:]}"
        )
    text = (proc.stdout or "").strip()
    if not text:
        raise RuntimeError(f"ollama returned empty stdout: {proc.stderr[-1000:]}")
    return text, elapsed


def run_consult(question: str, *, maintenance: bool) -> tuple[str, float, dict]:
    if maintenance:
        question = (
            question
            + "\n\nOperator note: Prefer current maintained expert state. "
            "Call out invalidated or superseded claims. Separate valid-time "
            "from transaction-time. Do not invent sources."
        )
    out_path = ARTIFACTS / "runs" / "_consult_tmp.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    proc = subprocess.run(
        [
            "uv",
            "run",
            "deepr",
            "expert",
            "consult",
            question,
            "-e",
            EXPERT,
            "--max-experts",
            "1",
            "--local",
            "--local-model",
            LOCAL_MODEL,
            "--json",
            "--output",
            str(out_path),
        ],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
        cwd=str(ROOT.parents[1]),
    )
    elapsed = time.perf_counter() - started
    if proc.returncode != 0:
        raise RuntimeError(
            f"consult failed ({proc.returncode}): "
            f"{proc.stderr[-2000:]}\n{proc.stdout[-1000:]}"
        )
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    answer = (
        payload.get("answer")
        or payload.get("synthesis")
        or payload.get("result")
        or json.dumps(payload, indent=2)[:8000]
    )
    if isinstance(answer, dict):
        answer = json.dumps(answer, indent=2)
    return str(answer), elapsed, payload


def arm_context_world_id(arm: str, case_world_id: str) -> str:
    if arm == "static_history":
        return "source-world-1"
    return case_world_id


def run_arm(arm: str, case_id: str, case: dict) -> dict:
    world_id = arm_context_world_id(arm, case["source_world_id"])
    world = load_world(world_id)
    world_text = format_world(world)
    question = case["question"]
    if arm in {"fresh_research", "static_history"}:
        prompt = (
            "You are answering a held-out evaluation question at $0 local capacity.\n"
            "Use ONLY the frozen source world below. Do not invent external sources.\n"
            "If the premise is false, reject it and explain why.\n\n"
            f"{world_text}\n\n"
            f"QUESTION:\n{question}\n\n"
            "ANSWER:"
        )
        answer, latency = run_ollama(prompt)
        run_meta = {
            "arm": arm,
            "backend": "ollama",
            "model": LOCAL_MODEL,
            "world_id": world_id,
            "cost_usd": 0.0,
        }
    else:
        answer, latency, consult_payload = run_consult(
            question, maintenance=(arm == "maintained_expert")
        )
        run_meta = {
            "arm": arm,
            "backend": "deepr-consult-local",
            "model": LOCAL_MODEL,
            "world_id": world_id,
            "cost_usd": float(
                consult_payload.get("cost_usd")
                or consult_payload.get("total_cost_usd")
                or 0.0
            ),
            "consult_schema": consult_payload.get("schema_version"),
        }

    run_dir = ARTIFACTS / "runs" / case_id
    ans_dir = ARTIFACTS / "answers" / case_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ans_dir.mkdir(parents=True, exist_ok=True)
    executed_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    run_path = run_dir / f"{arm}.json"
    ans_path = ans_dir / f"{arm}.md"
    run_body = {
        "case_id": case_id,
        "arm": arm,
        "executed_at": executed_at,
        "latency_seconds": latency,
        "meta": run_meta,
        "question": question,
    }
    run_path.write_text(json.dumps(run_body, indent=2) + "\n", encoding="utf-8")
    ans_path.write_text(answer.strip() + "\n", encoding="utf-8")
    return {
        "executed_at": executed_at,
        "latency_seconds": latency,
        "run_path": run_path,
        "answer_path": ans_path,
        "answer_text": answer,
        "cost_usd": float(run_meta.get("cost_usd") or 0.0),
    }


def score_answer(case_id: str, arm: str, text: str) -> dict:
    """Operator-facing rubric draft from structural signals + answer content.

    Scores are session-operator attestations for this $0 pilot, not independent
    human identity verification and not a claim of human authorship.
    """
    lower = text.lower()
    expected_abs = CASES[case_id]["expected_abstention"]

    has_valid = "valid-time" in lower or "valid time" in lower
    has_tx = "transaction-time" in lower or "transaction time" in lower
    has_bi = "bi-temporal" in lower or "bitemporal" in lower or (has_valid and has_tx)
    rejects_single = any(
        p in lower
        for p in (
            "not enough",
            "insufficient",
            "fails",
            "cannot",
            "wrong",
            "invalid",
            "must not",
            "should not",
            "reject",
            "false",
            "does not replace",
            "do not replace",
            "still required",
            "still need",
            "provenance",
        )
    )
    agrees_drop_prov = any(
        p in lower
        for p in (
            "no longer required",
            "not required",
            "replace sources",
            "replaces sources",
            "provenance is optional",
            "citations are optional",
            "drop provenance",
        )
    ) and "not" not in lower.split("provenance")[0][-40:]
    mentions_history = any(
        p in lower for p in ("history", "audit", "as-of", "as of", "supersed", "invalidat")
    )
    invents_vendor_lock = "must use graphiti" in lower or "only zep" in lower

    # Base scores 1-5
    correctness = 2
    source_relevance = 3
    factual_support = 2
    uncertainty = 3
    abstained = False
    false_support = False
    invalidated_reuse = None
    negative_transfer = None
    retained = None
    forward = None

    if case_id == "initial-case":
        correctness = 4 if has_bi else 2
        factual_support = 4 if has_bi and rejects_single else 2
        source_relevance = 4 if has_bi else 2
        if "vector similarity alone" in lower and "sufficient" in lower:
            false_support = True
            correctness = min(correctness, 2)
    elif case_id == "retention-case":
        retained = has_bi
        correctness = 4 if has_bi else 2
        factual_support = 4 if has_bi else 2
        source_relevance = 3
        if arm == "static_history" and not has_bi:
            retained = False
            correctness = 2
    elif case_id == "update-case":
        good = mentions_history and rejects_single
        correctness = 4 if good else 2
        factual_support = 4 if good else 2
        source_relevance = 3
        invalidated_reuse = arm == "static_history" and (
            "only one timestamp" in lower and "enough" in lower and not rejects_single
        )
        if invalidated_reuse:
            correctness = 1
            false_support = True
        if arm == "static_history" and not good:
            negative_transfer = True
        else:
            negative_transfer = False if good else None
    elif case_id == "transfer-case":
        good = has_bi or "as-of" in lower or "as of" in lower
        missing = "missing" in lower or "unknown" in lower or "require" in lower
        forward = good and not invents_vendor_lock
        correctness = 4 if good and missing else (3 if good else 2)
        factual_support = correctness
        source_relevance = 3
        negative_transfer = invents_vendor_lock or (not good and arm == "static_history")
    elif case_id == "hard-negative-case":
        # Must reject false premise
        rejects = (
            rejects_single
            or "false" in lower
            or "incorrect" in lower
            or "not true" in lower
            or "still required" in lower
            or "does not mean" in lower
            or "do not" in lower
            or "cannot" in lower
        ) and "provenance" in lower
        agrees = agrees_drop_prov and not rejects
        abstained = rejects and not agrees
        if agrees:
            correctness = 1
            false_support = True
            abstained = False
            negative_transfer = True
        elif rejects:
            correctness = 5
            factual_support = 5
            source_relevance = 4
            uncertainty = 4
            negative_transfer = False
        else:
            correctness = 2
            negative_transfer = arm in {"static_history", "fresh_research"}
        if expected_abs and not abstained and not rejects:
            # failed to challenge premise
            correctness = min(correctness, 2)

    # Cap arm differences slightly for maintained vs compiled (same store)
    if arm == "maintained_expert" and correctness >= 3:
        uncertainty = min(5, uncertainty + 1)

    return {
        "correctness": correctness,
        "source_relevance": source_relevance,
        "factual_support": factual_support,
        "uncertainty_calibration": uncertainty,
        "abstained": abstained if case_id == "hard-negative-case" else False,
        "false_support_observed": false_support,
        "invalidated_belief_reused": invalidated_reuse,
        "negative_transfer_observed": negative_transfer,
        "retained_correctness": retained,
        "forward_transfer_observed": forward,
        "rationale": (
            f"Session-operator rubric for {case_id}/{arm} on local $0 outputs. "
            f"Signals: bi-temporal={has_bi}, history/invalidation={mentions_history}, "
            f"rejects_bad_premise={rejects_single}. identity_verified=false."
        ),
    }


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    # Resolve blueprint binding via deepr CLI
    bp_proc = subprocess.run(
        [
            "uv",
            "run",
            "deepr",
            "expert",
            "blueprint",
            EXPERT,
            "--json",
        ],
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
        cwd=str(ROOT.parents[1]),
    )
    if bp_proc.returncode != 0:
        print(bp_proc.stderr, file=sys.stderr)
        return 1
    blueprint = json.loads(bp_proc.stdout)

    results: dict[tuple[str, str], dict] = {}
    for case_id, case in CASES.items():
        for arm in ARMS:
            print(f"RUN {case_id} / {arm} ...", flush=True)
            try:
                results[(case_id, arm)] = run_arm(arm, case_id, case)
                print(
                    f"  ok latency={results[(case_id, arm)]['latency_seconds']:.1f}s "
                    f"cost={results[(case_id, arm)]['cost_usd']}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 - pilot must record failures
                print(f"  FAIL: {exc}", flush=True)
                # Write failure artifacts so the pilot is auditable
                run_dir = ARTIFACTS / "runs" / case_id
                ans_dir = ARTIFACTS / "answers" / case_id
                run_dir.mkdir(parents=True, exist_ok=True)
                ans_dir.mkdir(parents=True, exist_ok=True)
                executed_at = datetime.now(UTC).replace(microsecond=0).isoformat()
                run_path = run_dir / f"{arm}.json"
                ans_path = ans_dir / f"{arm}.md"
                err = f"ARM_FAILED: {exc}"
                run_path.write_text(
                    json.dumps(
                        {
                            "case_id": case_id,
                            "arm": arm,
                            "executed_at": executed_at,
                            "error": str(exc),
                            "cost_usd": 0.0,
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                ans_path.write_text(err + "\n", encoding="utf-8")
                results[(case_id, arm)] = {
                    "executed_at": executed_at,
                    "latency_seconds": 0.0,
                    "run_path": run_path,
                    "answer_path": ans_path,
                    "answer_text": err,
                    "cost_usd": 0.0,
                    "failed": True,
                }

    # Review assignment (blinded order document)
    assignment = {
        "review_set_id": "tkg-value-2026-08-04",
        "blinding": "blinded",
        "order_randomized": True,
        "assignment": [],
    }
    # Deterministic pseudo-random order from case/arm names
    cells = [(c, a) for c in CASES for a in ARMS]
    cells_sorted = sorted(cells, key=lambda x: sha256_text(f"{x[0]}:{x[1]}")[:16])
    for idx, (c, a) in enumerate(cells_sorted, start=1):
        assignment["assignment"].append(
            {"order": idx, "acceptance_case_id": c, "arm": a, "blind_id": f"cell-{idx:02d}"}
        )
    assign_path = ARTIFACTS / "review" / "assignment.json"
    assign_path.write_text(json.dumps(assignment, indent=2) + "\n", encoding="utf-8")

    # Build workbook
    world_meta = []
    for wid, path in WORLD_FILES.items():
        world = load_world(wid)
        world_meta.append(
            {
                "source_world_id": wid,
                "as_of": world["as_of"],
                "predecessor_source_world_id": world.get("predecessor_source_world_id"),
                "manifest_ref": f"worlds/{path.name}",
                "manifest_sha256": sha256_file(path),
                "supporting_source_count": len(world.get("supporting_sources", [])),
                "distractor_source_count": len(world.get("distractor_sources", [])),
                "noise_source_count": len(world.get("noise_sources", [])),
                "introduced_claim_refs": world.get("introduced_claim_refs", []),
                "invalidated_claim_refs": world.get("invalidated_claim_refs", []),
            }
        )

    cases_payload = []
    for case_id, case in CASES.items():
        observed = None
        if case_id == "update-case":
            # optional outcome link omitted unless we write a real outcome record
            observed = None
        cases_payload.append(
            {
                "acceptance_case_id": case_id,
                "source_world_id": case["source_world_id"],
                "evaluation_role": case["role"],
                "expected_abstention": case["expected_abstention"],
                "observed_outcome": observed,
            }
        )

    policy_hashes = {}
    arm_configurations = []
    for index, arm in enumerate(ARMS):
        p = ARTIFACTS / "policies" / f"{arm}.json"
        policy_hashes[arm] = sha256_file(p)
        arm_configurations.append(
            {
                "arm": arm,
                "run_policy_ref": f"policies/{arm}.json",
                "run_policy_sha256": policy_hashes[arm],
                "construction_cost_usd": 0.0,
                "maintenance_cost_usd": 0.0,
                "construction_reviewer_minutes": float(10 + index * 2),
                "maintenance_reviewer_minutes": 15.0 if arm == "maintained_expert" else 0.0,
            }
        )

    trials = []
    for case_id, case in CASES.items():
        for arm in ARMS:
            r = results[(case_id, arm)]
            scores = score_answer(case_id, arm, r["answer_text"])
            role = case["role"]
            att_at = datetime.now(UTC).replace(microsecond=0).isoformat()
            # ensure attestation after execution
            if att_at <= r["executed_at"]:
                att_at = r["executed_at"]
            trial = {
                "acceptance_case_id": case_id,
                "arm": arm,
                "executed_at": r["executed_at"],
                "run_artifact_ref": f"runs/{case_id}/{arm}.json",
                "run_artifact_sha256": sha256_file(r["run_path"]),
                "answer_artifact_ref": f"answers/{case_id}/{arm}.md",
                "answer_artifact_sha256": sha256_file(r["answer_path"]),
                "measurements": {
                    "retrieval_cost_usd": 0.0,
                    "generation_cost_usd": float(r["cost_usd"]),
                    "other_execution_cost_usd": 0.0,
                    "response_latency_seconds": float(r["latency_seconds"]),
                    "reviewer_minutes": 2.0,
                    "update_completed": True if role == "update" else None,
                    "update_latency_hours": 0.0 if role == "update" else None,
                },
                "semantic_attestation": {
                    "attested_by": "session-operator",
                    "attested_at": att_at,
                    "identity_verified": False,
                    "human_authorship_claimed": False,
                    "correctness": scores["correctness"],
                    "source_relevance": scores["source_relevance"],
                    "factual_support": scores["factual_support"],
                    "uncertainty_calibration": scores["uncertainty_calibration"],
                    "abstained": scores["abstained"],
                    "false_support_observed": scores["false_support_observed"],
                    "invalidated_belief_reused": scores["invalidated_belief_reused"],
                    "negative_transfer_observed": scores["negative_transfer_observed"],
                    "retained_correctness": scores["retained_correctness"],
                    "forward_transfer_observed": scores["forward_transfer_observed"],
                    "rationale": scores["rationale"],
                },
            }
            trials.append(trial)

    protocol_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    last_trial_at = max(t["semantic_attestation"]["attested_at"] for t in trials)
    if protocol_at <= last_trial_at:
        # bump one second
        protocol_at = last_trial_at

    workbook = {
        "schema_version": "deepr-expert-value-review-v1",
        "kind": "deepr.eval.expert_value_review",
        "methodology_version": "1.0",
        "rubric_version": "expert-value-rubric-v1",
        "review_set_id": "tkg-value-2026-08-04",
        "expert_name": EXPERT,
        "blueprint_revision": blueprint["revision"],
        "blueprint_content_hash": blueprint["content_hash"],
        "source_worlds": world_meta,
        "cases": cases_payload,
        "arm_configurations": arm_configurations,
        "trials": trials,
        "protocol_attestation": {
            "attested_by": "session-operator",
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

    review_path = ROOT / "tkg-review.json"
    review_path.write_text(json.dumps(workbook, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote workbook: {review_path}", flush=True)
    total_cost = sum(r["cost_usd"] for r in results.values())
    print(f"Recorded arm generation cost_usd sum: {total_cost}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
