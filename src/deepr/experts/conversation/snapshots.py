"""Compile bounded, immutable expert packets for conversation starts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from deepr.experts.consult import MAX_CONSULT_EXPERTS, resolve_explicit_expert_choices
from deepr.experts.conversation.models import (
    ConsultationMode,
    ConversationError,
    ErrorCode,
    ExpertSnapshotInput,
    sha256_json,
)
from deepr.experts.expert_routing import score_experts_for_query, select_top_experts
from deepr.experts.handoff import build_expert_handoff


class ExpertProfileStore(Protocol):
    """Read-only profile store needed to freeze a conversation roster."""

    def list_all(self) -> list[Any]:
        """Return available expert profiles."""


def _invalid(message: str, *, field_name: str) -> ConversationError:
    return ConversationError(ErrorCode.INVALID_REQUEST, message, field_name=field_name)


def _validate_selection_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_CONSULT_EXPERTS:
        raise _invalid(
            f"max_experts must be between 1 and {MAX_CONSULT_EXPERTS}.",
            field_name="max_experts",
        )
    return value


def _selected_names(
    profiles: Sequence[Any],
    *,
    message: str,
    requested_experts: Sequence[str] | None,
    max_experts: int,
    mode: ConsultationMode,
) -> tuple[str, ...]:
    limit = _validate_selection_limit(max_experts)
    if requested_experts:
        if any(not isinstance(name, str) or not name.strip() for name in requested_experts):
            raise _invalid("Every expert name must be non-empty text.", field_name="experts")
        try:
            choices = resolve_explicit_expert_choices(list(requested_experts), profiles)
        except ValueError as exc:
            raise _invalid(str(exc), field_name="experts") from exc
        names = tuple(choice["name"] for choice in choices)
    else:
        selection_limit = 1 if mode is ConsultationMode.FOCUSED else limit
        scored = score_experts_for_query(message, list(profiles))
        names = tuple(choice["name"] for choice in select_top_experts(scored, max_experts=selection_limit))

    if not names:
        raise _invalid("No experts are available for this conversation.", field_name="experts")
    if len(names) > limit:
        raise _invalid("The explicit roster exceeds max_experts.", field_name="experts")
    if mode is ConsultationMode.FOCUSED and len(names) != 1:
        raise _invalid("Focused mode requires exactly one expert.", field_name="experts")
    return names


def _source_position(profile: Any, handoff: dict[str, Any]) -> str:
    manifest = handoff.get("manifest")
    if isinstance(manifest, dict) and manifest.get("generated_at"):
        return f"manifest:{manifest['generated_at']}"
    for field_name in ("updated_at", "last_knowledge_refresh", "knowledge_cutoff"):
        value = handoff.get("expert", {}).get(field_name) if isinstance(handoff.get("expert"), dict) else None
        if value:
            return f"profile:{field_name}:{value}"
    name = str(getattr(profile, "name", "unknown"))
    return f"profile:{name}:unversioned"


def compile_expert_snapshot(profile: Any) -> ExpertSnapshotInput:
    """Freeze the bounded read-only portion of one expert handoff."""
    handoff = build_expert_handoff(
        profile,
        max_claims=12,
        max_gaps=8,
        loop_limit=5,
        include_claims=True,
        include_gaps=True,
        include_decisions=False,
    )
    packet = {
        "schema_version": handoff.get("schema_version"),
        "kind": handoff.get("kind"),
        "contract": handoff.get("contract"),
        "expert": handoff.get("expert"),
        "summary": handoff.get("summary"),
        "manifest": handoff.get("manifest"),
        "claims": handoff.get("claims", []),
        "gaps": handoff.get("gaps", []),
        "perspective_state": handoff.get("perspective_state"),
        "loop_status": handoff.get("loop_status"),
    }
    name = str(getattr(profile, "name", "") or "").strip()
    if not name:
        raise _invalid("An expert profile is missing its canonical name.", field_name="experts")
    return ExpertSnapshotInput(
        expert_name=name,
        state_sha256=sha256_json(packet),
        source_position=_source_position(profile, handoff),
        packet=packet,
    )


def compile_conversation_snapshots(
    store: ExpertProfileStore,
    *,
    message: str,
    requested_experts: Sequence[str] | None,
    max_experts: int,
    mode: ConsultationMode,
) -> tuple[ExpertSnapshotInput, ...]:
    """Resolve a roster and freeze every packet before durable reservation."""
    profiles = list(store.list_all())
    names = _selected_names(
        profiles,
        message=message,
        requested_experts=requested_experts,
        max_experts=max_experts,
        mode=mode,
    )
    by_name = {str(getattr(profile, "name", "")): profile for profile in profiles}
    snapshots: list[ExpertSnapshotInput] = []
    for name in names:
        profile = by_name.get(name)
        if profile is None:
            # Keep missing and unauthorized names indistinguishable at the
            # public boundary. The caller only learns that the roster cannot
            # be constructed.
            raise _invalid("One or more requested experts are unavailable.", field_name="experts")
        snapshots.append(compile_expert_snapshot(profile))
    return tuple(snapshots)


__all__ = ["compile_conversation_snapshots", "compile_expert_snapshot"]
