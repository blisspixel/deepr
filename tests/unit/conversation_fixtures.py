"""Shared deterministic fixtures for durable expert-conversation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from deepr.experts.conversation.models import (
    HOST_ACTION_BOUNDARY,
    BackendSelection,
    ConsultationMode,
    ConversationBounds,
    ConversationExecutionContext,
    ConversationStartRequest,
    ExpertSnapshotInput,
    TurnExecutionResult,
    TurnUsage,
)


def answer_artifact(
    *,
    semantic_status: str = "answered",
    expert_names: list[str] | None = None,
    direct_answer: str = "Use an idempotent durable transition.",
) -> dict[str, Any]:
    experts = expert_names or ["reliability_engineering"]
    return {
        "direct_answer": direct_answer,
        "experts_consulted": experts,
        "assumptions": [{"text": "The caller supplies stable request ids.", "source": "model_proposed"}],
        "evidence": [
            {
                "evidence_ref": "belief-42",
                "source_type": "expert_state",
                "expert_name": experts[0],
                "citation": "source-7",
            }
        ],
        "uncertainty": {
            "kind": "qualitative",
            "value": "medium",
            "rationale": "Crash injection is still required.",
        },
        "agreements": ["Duplicate delivery must not dispatch twice."],
        "dissent": [
            {
                "position": "A broker could own replay instead.",
                "expert_names": [experts[0]],
                "evidence_refs": ["belief-42"],
            }
        ],
        "decision_implications": [
            {"proposal": "Gate release on restart and replay tests.", "authority": "proposal_only"}
        ],
        "change_conditions": ["Exactly-once dispatch is proven under crash injection."],
        "unresolved_gaps": ["Cross-process lease recovery needs validation."],
        "recommended_next_question": "Which crash points should the harness inject?",
        "semantic_status": semantic_status,
        "host_action_boundary": HOST_ACTION_BOUNDARY,
    }


def expert_snapshot(
    name: str = "reliability_engineering",
    *,
    marker: str = "42",
    packet: dict[str, Any] | None = None,
) -> ExpertSnapshotInput:
    return ExpertSnapshotInput(
        expert_name=name,
        state_sha256=marker[0] * 64,
        source_position=f"belief-events:{marker}",
        packet=packet
        or {
            "beliefs": [
                {
                    "belief_id": f"belief-{marker}",
                    "claim": "Retries require idempotency.",
                    "confidence": 0.91,
                    "citation_refs": ["source-7"],
                }
            ],
            "gaps": ["Outcome calibration is pending."],
        },
    )


def start_request(
    *,
    owner_id: str = "owner-a",
    idempotency_key: str = "start-001",
    message: str = "What failure would invalidate this rollout?",
    snapshots: tuple[ExpertSnapshotInput, ...] | None = None,
    bounds: ConversationBounds | None = None,
    mode: ConsultationMode = ConsultationMode.FOCUSED,
    retention_days: int = 30,
) -> ConversationStartRequest:
    return ConversationStartRequest(
        owner_id=owner_id,
        idempotency_key=idempotency_key,
        message=message,
        decision_brief="Choose whether to expose a durable local service.",
        expert_snapshots=snapshots or (expert_snapshot(),),
        backend=BackendSelection.local("fixture-local-model"),
        bounds=bounds or ConversationBounds(),
        mode=mode,
        retention_days=retention_days,
    )


def completed_result(
    *,
    artifact: dict[str, Any] | None = None,
    usage: TurnUsage | None = None,
) -> TurnExecutionResult:
    return TurnExecutionResult.completed(
        artifact or answer_artifact(),
        usage=usage or TurnUsage(model_calls=1, input_tokens=120, output_tokens=80, elapsed_ms=900),
        consult_trace_id="trace_fixture_0001",
        consult_lifecycle_trace_id="trace_fixture_0001",
    )


class MutableClock:
    def __init__(self, value: datetime | None = None) -> None:
        self.value = value or datetime(2026, 7, 15, 16, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: float) -> None:
        self.value += timedelta(**kwargs)


class CompletingExecutor:
    def __init__(self) -> None:
        self.contexts: list[ConversationExecutionContext] = []

    async def execute(self, context: ConversationExecutionContext) -> TurnExecutionResult:
        self.contexts.append(context)
        return completed_result()
