"""Immutable zero-call planning for local expert investigations."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from deepr.experts.blueprint import ExpertBlueprintStore
from deepr.experts.consult import resolve_explicit_expert_choices
from deepr.experts.conversation.snapshots import compile_expert_snapshot
from deepr.experts.investigation.inputs import InputLimits, compile_input_bundle
from deepr.experts.investigation.models import (
    DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS,
    MAX_LOCAL_CONTEXT_WINDOW_TOKENS,
    MIN_LOCAL_CONTEXT_WINDOW_TOKENS,
    PLAN_KIND,
    PLAN_SCHEMA_VERSION,
    InvestigationBounds,
    InvestigationContractError,
    LearningMode,
    Phase,
    ProtocolMode,
    maximum_generation_calls,
    new_run_id,
    sha256_json,
    utc_now,
    validate_plan,
)
from deepr.experts.profile_store import ExpertStore


class ProfileStore(Protocol):
    """Read-only profile store required by planning."""

    def list_all(self) -> list[Any]:
        """Return available profiles."""


class BlueprintReader(Protocol):
    """Read-only blueprint presence seam required by planning."""

    def load_latest(self, expert_name: str) -> Any | None:
        """Return the latest blueprint or none."""


def _profile_map(profiles: Sequence[Any]) -> dict[str, Any]:
    return {str(getattr(profile, "name", "")): profile for profile in profiles}


def _resolve_profiles(expert_names: Sequence[str], profiles: Sequence[Any]) -> list[Any]:
    if not expert_names:
        raise InvestigationContractError("at least one explicit expert is required")
    if any(not isinstance(name, str) or not name.strip() for name in expert_names):
        raise InvestigationContractError("expert names must be non-empty strings")
    try:
        choices = resolve_explicit_expert_choices(list(expert_names), profiles)
    except ValueError as exc:
        raise InvestigationContractError(str(exc)) from exc
    by_name = _profile_map(profiles)
    resolved: list[Any] = []
    missing: list[str] = []
    for choice in choices:
        profile = by_name.get(choice["name"])
        if profile is None:
            missing.append(choice["name"])
        else:
            resolved.append(profile)
    if missing:
        raise InvestigationContractError(f"expert profiles not found: {', '.join(missing)}")
    return resolved


def _recorded_local_model(profile: Any) -> str | None:
    provider = str(getattr(profile, "provider", "") or "").strip().casefold()
    model = str(getattr(profile, "model", "") or "").strip()
    if provider == "local" and model and model.casefold() != "ollama":
        return model
    return None


def _choose_local_model(profiles: Sequence[Any], explicit_model: str | None) -> str:
    selected = (explicit_model or "").strip()
    if selected:
        return selected
    recorded = {model for profile in profiles if (model := _recorded_local_model(profile)) is not None}
    if len(recorded) == 1:
        return recorded.pop()
    if not recorded:
        raise InvestigationContractError(
            "an exact --local-model is required because the roster has no common recorded local model"
        )
    raise InvestigationContractError(
        "an exact --local-model is required because the roster records different local models: "
        + ", ".join(sorted(recorded))
    )


def _context_window(value: int, *, field_name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not MIN_LOCAL_CONTEXT_WINDOW_TOKENS <= value <= MAX_LOCAL_CONTEXT_WINDOW_TOKENS
    ):
        raise InvestigationContractError(
            f"{field_name} must be an integer from {MIN_LOCAL_CONTEXT_WINDOW_TOKENS} "
            f"to {MAX_LOCAL_CONTEXT_WINDOW_TOKENS}"
        )
    return value


def _fit_bounds_to_context(bounds: InvestigationBounds, *, minimum_context_tokens: int) -> InvestigationBounds:
    prompt_tokens = min(
        bounds.max_prompt_bytes_per_call // 4,
        minimum_context_tokens - bounds.max_output_tokens_per_call,
    )
    if prompt_tokens < 256:
        raise InvestigationContractError("local context window leaves no usable prompt capacity")
    return InvestigationBounds.from_dict(
        {
            **bounds.to_dict(),
            "max_prompt_bytes_per_call": prompt_tokens * 4,
            "max_input_tokens": bounds.max_generation_calls * prompt_tokens,
        }
    )


def _readiness(profile: Any, snapshot_packet: dict[str, Any], blueprint_reader: BlueprintReader) -> dict[str, Any]:
    summary = snapshot_packet.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    expert = snapshot_packet.get("expert")
    expert = expert if isinstance(expert, dict) else {}
    try:
        blueprint_present = blueprint_reader.load_latest(str(getattr(profile, "name", ""))) is not None
        blueprint_status = "present" if blueprint_present else "absent"
    except Exception as exc:
        blueprint_present = False
        blueprint_status = f"unavailable:{type(exc).__name__}"
    return {
        "profile_present": True,
        "blueprint_present": blueprint_present,
        "blueprint_status": blueprint_status,
        "claim_count": int(summary.get("claim_count", 0) or 0),
        "verified_claim_count": int(summary.get("verified_claim_count", 0) or 0),
        "open_gap_count": int(summary.get("open_gap_count", 0) or 0),
        "contested_open_count": int(summary.get("contested_open_count", 0) or 0),
        "knowledge_cutoff": expert.get("knowledge_cutoff"),
        "last_knowledge_refresh": expert.get("last_knowledge_refresh"),
        "domain_velocity": str(expert.get("domain_velocity", "") or ""),
        "recorded_provider": str(getattr(profile, "provider", "") or ""),
        "recorded_model": str(getattr(profile, "model", "") or ""),
        "qualification_verdict": "not_deterministically_judged",
    }


def _phases(protocol: ProtocolMode, learning: LearningMode) -> list[str]:
    values = [
        Phase.PREFLIGHT.value,
        Phase.CHARTERS.value,
        Phase.RESEARCH.value,
        Phase.POSITIONS.value,
    ]
    if protocol in {ProtocolMode.DISCUSS, ProtocolMode.DEEP}:
        values.append(Phase.DISCUSSION.value)
    if protocol is ProtocolMode.DEEP:
        values.append(Phase.REVISIONS.value)
    values.extend([Phase.CHECK.value, Phase.SYNTHESIS.value])
    if learning is LearningMode.STAGE:
        values.append(Phase.LEARNING.value)
    values.append(Phase.COMPLETE.value)
    return values


def _call_formula(expert_count: int, protocol: ProtocolMode, learning: LearningMode) -> dict[str, Any]:
    discussion_per_expert = 1 if protocol in {ProtocolMode.DISCUSS, ProtocolMode.DEEP} else 0
    revision_per_expert = 1 if protocol is ProtocolMode.DEEP else 0
    learning_per_expert = 2 if learning is LearningMode.STAGE else 0
    maximum = maximum_generation_calls(expert_count, protocol, learning)
    return {
        "expression": "N * (2 + D + V + L) + 1 checker + 1 synthesis",
        "expert_count": expert_count,
        "research_per_expert": 2,
        "discussion_per_expert": discussion_per_expert,
        "revision_per_expert": revision_per_expert,
        "learning_per_expert": learning_per_expert,
        "checker_calls": 1,
        "synthesis_calls": 1,
        "maximum_generation_calls": maximum,
    }


def _egress_manifest(has_urls: bool) -> list[dict[str, Any]]:
    return [
        {
            "destination": "local_ollama",
            "network_boundary": "loopback_or_operator_configured_local_host",
            "data_classes": [
                "question",
                "caller_supplied_text_excerpts",
                "caller_supplied_file_excerpts",
                "expert_frozen_snapshot",
                "retrieved_source_excerpts",
                "blinded_peer_packets",
            ],
            "provider_egress": False,
            "enabled": True,
        },
        {
            "destination": "free_web_retrieval",
            "network_boundary": "public_internet",
            "data_classes": ["question_derived_search_queries", "requested_urls"],
            "provider_egress": True,
            "enabled": True,
            "requested_urls_present": has_urls,
            "file_or_snapshot_content_sent": False,
        },
        {
            "destination": "metered_or_plan_provider",
            "network_boundary": "external_provider",
            "data_classes": [],
            "provider_egress": False,
            "enabled": False,
        },
    ]


def build_investigation_plan(
    *,
    question: str,
    expert_names: Sequence[str],
    input_root: str | Path,
    inline_texts: Sequence[str] = (),
    urls: Sequence[str] = (),
    files: Sequence[str | Path] = (),
    folders: Sequence[str | Path] = (),
    local_model: str | None = None,
    review_model: str | None = None,
    context_window_tokens: int = DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS,
    review_context_window_tokens: int | None = None,
    protocol: ProtocolMode | str = ProtocolMode.DISCUSS,
    learning: LearningMode | str = LearningMode.OFF,
    max_elapsed_seconds: float = 3600.0,
    input_limits: InputLimits | None = None,
    profile_store: ProfileStore | None = None,
    blueprint_reader: BlueprintReader | None = None,
    run_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a complete plan without network access, model calls, or state writes."""
    normalized_question = question.strip() if isinstance(question, str) else ""
    if not normalized_question:
        raise InvestigationContractError("question must be non-empty")
    try:
        protocol_mode = ProtocolMode(protocol)
        learning_mode = LearningMode(learning)
    except ValueError as exc:
        raise InvestigationContractError(str(exc)) from exc
    store = profile_store or ExpertStore(create=False)
    profiles = _resolve_profiles(expert_names, list(store.list_all()))
    model = _choose_local_model(profiles, local_model)
    selected_review_model = (review_model or model).strip()
    if not selected_review_model:
        raise InvestigationContractError("review_model must be an exact local model name")
    selected_context_window = _context_window(context_window_tokens, field_name="context_window_tokens")
    selected_review_context_window = _context_window(
        review_context_window_tokens or selected_context_window,
        field_name="review_context_window_tokens",
    )
    bundle = compile_input_bundle(
        input_root=input_root,
        inline_texts=inline_texts,
        urls=urls,
        files=files,
        folders=folders,
        limits=input_limits,
        created_at=created_at,
    )
    blueprints = blueprint_reader or ExpertBlueprintStore()
    experts: list[dict[str, Any]] = []
    for profile in profiles:
        snapshot = compile_expert_snapshot(profile)
        experts.append(
            {
                "name": snapshot.expert_name,
                "domain": str(getattr(profile, "domain", "") or getattr(profile, "description", "") or ""),
                "snapshot_sha256": snapshot.state_sha256,
                "snapshot_source_position": snapshot.source_position,
                "snapshot": snapshot.packet,
                "readiness": _readiness(profile, snapshot.packet, blueprints),
            }
        )
    bounds = InvestigationBounds.for_plan(
        expert_count=len(experts),
        protocol=protocol_mode,
        learning=learning_mode,
        max_elapsed_seconds=max_elapsed_seconds,
    )
    bounds = _fit_bounds_to_context(
        bounds,
        minimum_context_tokens=min(selected_context_window, selected_review_context_window),
    )
    has_urls = any(item["input_type"] == "url" for item in bundle["items"])
    timestamp = created_at or utc_now()
    material: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "run_id": run_id or new_run_id(),
        "created_at": timestamp,
        "question": normalized_question,
        "experts": experts,
        "protocol": protocol_mode.value,
        "learning": learning_mode.value,
        "phases": _phases(protocol_mode, learning_mode),
        "input_bundle": bundle,
        "capacity": {
            "class": "local",
            "source": "local_owned",
            "provider": "ollama",
            "model": model,
            "review_model": selected_review_model,
            "context_window_tokens": selected_context_window,
            "review_context_window_tokens": selected_review_context_window,
            "fallback": "none",
            "runtime_probe": "not_performed_by_zero_network_preview",
            "recorded_run_cost_usd": 0.0,
        },
        "retrieval": {
            "mode": "free_only_deep_context",
            "network_access_during_plan": False,
            "network_access_during_run": True,
            "cross_expert_url_deduplication": False,
            "content_snapshot_deduplication": True,
            "max_queries_per_expert": 4,
            "max_pages_per_expert": 8,
        },
        "bounds": bounds.to_dict(),
        "call_formula": _call_formula(len(experts), protocol_mode, learning_mode),
        "data_egress": _egress_manifest(has_urls),
        "retention": {
            "policy": "local_run_artifacts",
            "raw_model_reasoning_requested": False,
            "caller_inputs_copied": False,
        },
        "learning_contract": {
            "mode": learning_mode.value,
            "source_pack_evidence_only": True,
            "dialogue_is_evidence": False,
            "domain_relevance_required": learning_mode is LearningMode.STAGE,
            "domain_relevance_judgment": (
                "independent_verifier_model" if learning_mode is LearningMode.STAGE else "not_applicable"
            ),
            "writes_expert_state": False,
            "writes_beliefs": False,
            "writes_graph": False,
            "output": "verified_graph_commit_envelopes_staged_only" if learning_mode is LearningMode.STAGE else "none",
            "review_label": "automatic_verifier_accepted" if learning_mode is LearningMode.STAGE else "not_applicable",
            "human_reviewed": False,
        },
        "confirmation_required": True,
        "preview_activity": {
            "model_calls": 0,
            "network_requests": 0,
            "provider_process_starts": 0,
            "expert_state_writes": 0,
            "cost_usd": 0.0,
        },
    }
    material["plan_sha256"] = sha256_json(material)
    return validate_plan(material)


__all__ = ["BlueprintReader", "ProfileStore", "build_investigation_plan"]
