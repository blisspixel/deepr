"""Source-backed staged learning for completed investigations."""

from __future__ import annotations

from typing import Any

from deepr.experts.beliefs import BeliefStore
from deepr.experts.claim_extraction import (
    CLAIM_EXTRACTION_PROMPT_REF,
    ClaimExtractionBlocked,
    build_claim_extraction_prompt,
)
from deepr.experts.claim_verification import (
    CLAIM_VERIFICATION_PROMPT_REF,
    ClaimVerificationBlocked,
    build_claim_verification_prompt,
)
from deepr.experts.graph_commit_envelope import build_graph_commit_envelope
from deepr.experts.investigation.models import Phase
from deepr.experts.investigation.protocol import PromptPacket
from deepr.experts.investigation.runtime import InvestigationRuntime
from deepr.experts.source_pack_compiler import (
    build_claim_verification,
    build_semantic_claim_extraction,
    build_source_notes,
)

_MAX_STAGED_CLAIMS_PER_EXPERT = 5


def _artifact_path(runtime: InvestigationRuntime, logical_key: str) -> str:
    reference = runtime.artifact_reference(logical_key)
    return str((reference or {}).get("path", "") or "")


def _belief_recall(expert_name: str) -> tuple[Any | None, str]:
    try:
        return BeliefStore(expert_name, read_only=True), "loaded_read_only"
    except Exception as exc:
        return None, f"unavailable:{type(exc).__name__}"


async def stage_expert_learning(
    runtime: InvestigationRuntime,
    *,
    expert: dict[str, Any],
    expert_key: str,
    source_pack: dict[str, Any],
) -> dict[str, Any]:
    """Compile and verify only external source-pack evidence, never dialogue."""
    expert_name = str(expert["name"])
    expert_domain = str(expert.get("domain", "") or "")
    notes_key = f"learning:source-notes:{expert_key}"
    source_notes = runtime.artifact(notes_key)
    if source_notes is None:
        source_pack_path = _artifact_path(runtime, f"source-pack:{expert_key}")
        source_notes = build_source_notes(
            {
                "source_pack": source_pack,
                "query": runtime.plan["question"],
                "answer_query": runtime.plan["question"],
                "topic": expert.get("domain", ""),
            },
            source_pack_artifact=source_pack_path,
        )
        runtime.put_artifact(
            notes_key,
            phase=Phase.LEARNING,
            key=f"source-notes-{expert_key}",
            payload=source_notes,
        )

    extraction_key = f"learning:extraction:{expert_key}"
    extraction = runtime.artifact(extraction_key)
    if extraction is None:
        try:
            extraction_prompt = build_claim_extraction_prompt(
                source_notes,
                {"source_pack": source_pack},
                max_claims=_MAX_STAGED_CLAIMS_PER_EXPERT,
                target_domain=expert_domain,
            )
        except ClaimExtractionBlocked as exc:
            return {
                "expert_name": expert_name,
                "status": "no_op",
                "reason": str(exc),
                "source_note_artifact": _artifact_path(runtime, notes_key),
                "claim_extraction_artifact": "",
                "claim_verification_artifact": "",
                "graph_commit_envelope_artifact": "",
                "automatic_verifier_accepted": False,
                "human_reviewed": False,
                "writes_expert_state": False,
            }
        raw = await runtime.complete(
            PromptPacket(
                operation="learning_claim_compiler",
                expert_name=expert_name,
                messages=extraction_prompt.messages,
            )
        )
        extraction = build_semantic_claim_extraction(
            source_notes,
            raw,
            source_note_artifact=_artifact_path(runtime, notes_key),
            provider="local",
            model=str(runtime.plan["capacity"]["model"]),
            capacity_source="local_owned",
            cost_usd=0.0,
            prompt_ref=CLAIM_EXTRACTION_PROMPT_REF,
            prompt_hash=extraction_prompt.prompt_hash,
            max_candidates=_MAX_STAGED_CLAIMS_PER_EXPERT,
        )
        runtime.put_artifact(
            extraction_key,
            phase=Phase.LEARNING,
            key=f"claim-extraction-{expert_key}",
            payload=extraction,
        )

    ready_count = int((extraction.get("summary", {}) or {}).get("ready_for_verification_count", 0) or 0)
    if ready_count == 0:
        return {
            "expert_name": expert_name,
            "status": "no_verified_candidates",
            "reason": ",".join((extraction.get("summary", {}) or {}).get("failure_reasons", []) or []),
            "source_note_artifact": _artifact_path(runtime, notes_key),
            "claim_extraction_artifact": _artifact_path(runtime, extraction_key),
            "claim_verification_artifact": "",
            "graph_commit_envelope_artifact": "",
            "automatic_verifier_accepted": False,
            "human_reviewed": False,
            "writes_expert_state": False,
        }

    verification_key = f"learning:verification:{expert_key}"
    verification = runtime.artifact(verification_key)
    recall_store, recall_status = _belief_recall(expert_name)
    if verification is None:
        try:
            verification_prompt = build_claim_verification_prompt(
                extraction,
                source_notes,
                {"source_pack": source_pack},
                recall_belief_store=recall_store,
                recall_domain=expert_domain,
                target_domain=expert_domain,
                require_domain_relevance=True,
            )
        except ClaimVerificationBlocked as exc:
            return {
                "expert_name": expert_name,
                "status": "verifier_blocked",
                "reason": str(exc),
                "recall_status": recall_status,
                "source_note_artifact": _artifact_path(runtime, notes_key),
                "claim_extraction_artifact": _artifact_path(runtime, extraction_key),
                "claim_verification_artifact": "",
                "graph_commit_envelope_artifact": "",
                "automatic_verifier_accepted": False,
                "human_reviewed": False,
                "writes_expert_state": False,
            }
        raw = await runtime.complete(
            PromptPacket(
                operation="learning_claim_verifier",
                expert_name=expert_name,
                messages=verification_prompt.messages,
            )
        )
        verification = build_claim_verification(
            extraction,
            raw,
            claim_extraction_artifact=_artifact_path(runtime, extraction_key),
            provider="local",
            model=str(runtime.plan["capacity"].get("review_model", runtime.plan["capacity"]["model"])),
            capacity_source="local_owned",
            cost_usd=0.0,
            prompt_ref=CLAIM_VERIFICATION_PROMPT_REF,
            prompt_hash=verification_prompt.prompt_hash,
            recall_candidates_by_candidate_id=verification_prompt.recall_candidates_by_candidate_id,
            required_domain=expert_domain,
        )
        runtime.put_artifact(
            verification_key,
            phase=Phase.LEARNING,
            key=f"claim-verification-{expert_key}",
            payload=verification,
        )

    envelope_key = f"learning:envelope:{expert_key}"
    envelope = runtime.artifact(envelope_key)
    if envelope is None:
        envelope = build_graph_commit_envelope(
            extraction,
            verification,
            claim_extraction_artifact=_artifact_path(runtime, extraction_key),
            claim_verification_artifact=_artifact_path(runtime, verification_key),
            expert_name=expert_name,
            domain=expert_domain,
            trust_class="tertiary_web_retrieval",
            grounding_assurance="automatic_verifier_accepted",
        )
        runtime.put_artifact(
            envelope_key,
            phase=Phase.LEARNING,
            key=f"graph-commit-envelope-{expert_key}",
            payload=envelope,
        )
    ready_writes = int((envelope.get("summary", {}) or {}).get("ready_write_count", 0) or 0)
    return {
        "expert_name": expert_name,
        "status": str((envelope.get("summary", {}) or {}).get("status", "blocked") or "blocked"),
        "reason": ",".join((envelope.get("summary", {}) or {}).get("failure_reasons", []) or []),
        "recall_status": recall_status,
        "ready_write_count": ready_writes,
        "source_note_artifact": _artifact_path(runtime, notes_key),
        "claim_extraction_artifact": _artifact_path(runtime, extraction_key),
        "claim_verification_artifact": _artifact_path(runtime, verification_key),
        "graph_commit_envelope_artifact": _artifact_path(runtime, envelope_key),
        "automatic_verifier_accepted": ready_writes > 0,
        "human_reviewed": False,
        "writes_expert_state": False,
    }


__all__ = ["stage_expert_learning"]
