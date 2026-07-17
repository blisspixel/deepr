"""Shared ceilings, control gates, and artifacts for investigation execution."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from deepr.experts.chat_backends import ExpertChatBackend, ExpertChatRequest
from deepr.experts.investigation.models import (
    DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS,
    InvestigationBounds,
    Phase,
    RunState,
    canonical_json,
)
from deepr.experts.investigation.protocol import PromptPacket
from deepr.experts.investigation.store import InvestigationStorageError, InvestigationStore

_REVIEW_OPERATIONS = frozenset({"checker", "synthesis", "learning_claim_verifier"})


class InvestigationPaused(RuntimeError):
    """Raised between side effects when pause was requested."""


class InvestigationCancelled(RuntimeError):
    """Raised when cancellation prevents any later artifact side effect."""


class InvestigationBudgetExhausted(RuntimeError):
    """Raised when the hash-bound parent envelope has no remaining capacity."""


@dataclass(frozen=True)
class RetrievalReservation:
    expert_key: str
    search_queries: int
    page_fetches: int


def _usage_tokens(usage: Any, *names: str) -> int:
    for name in names:
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        if value is not None:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                continue
    return 0


def _settled_output_tokens(text: str, measured_output: int) -> int:
    if measured_output > 0:
        return measured_output
    return max(1, math.ceil(len(text.encode("utf-8")) / 4))


class InvestigationRuntime:
    """Conservatively account for every child action under one run plan."""

    def __init__(self, store: InvestigationStore, run_id: str, backend: ExpertChatBackend) -> None:
        self.store = store
        self.run_id = run_id
        self.plan = store.load_plan(run_id)
        self.state = store.load_state(run_id)
        self.bounds = InvestigationBounds.from_dict(self.plan["bounds"])
        self.backend = backend
        self._started = time.monotonic()
        self._elapsed_base = float(self.state.get("usage", {}).get("elapsed_seconds", 0.0) or 0.0)
        if backend.metered or backend.provider != "local":
            raise InvestigationStorageError("local investigation execution requires a non-metered local backend")
        selected_model = str(self.plan["capacity"]["model"])
        backend_model = str(backend.model or "")
        if backend_model and backend_model != selected_model:
            raise InvestigationStorageError("execution backend model does not match the hash-bound plan")

    def _elapsed(self) -> float:
        return self._elapsed_base + (time.monotonic() - self._started)

    def _usage(self) -> dict[str, Any]:
        usage = self.state.get("usage")
        if not isinstance(usage, dict):
            raise InvestigationStorageError("investigation usage state is invalid")
        return usage

    def _save(self) -> None:
        self._usage()["elapsed_seconds"] = round(self._elapsed(), 6)
        self.state = self.store.save_state(
            self.run_id,
            self.state,
            expected_version=int(self.state["version"]),
        )

    def _check_elapsed(self) -> None:
        if self._elapsed() > self.bounds.max_elapsed_seconds:
            raise InvestigationBudgetExhausted("investigation elapsed-time ceiling is exhausted")

    def control_gate(self, *, after_dispatch: bool = False) -> None:
        """Stop before new work; after dispatch, cancellation also blocks late writes."""
        self._check_elapsed()
        requested = str(self.store.load_control(self.run_id).get("requested", "run") or "run")
        if requested == "cancel":
            raise InvestigationCancelled("investigation cancellation was requested")
        if requested == "pause" and not after_dispatch:
            raise InvestigationPaused("investigation pause was requested")

    def transition(self, phase: Phase, status: RunState = RunState.RUNNING) -> None:
        self.control_gate()
        self.state["phase"] = phase.value
        self.state["state"] = status.value
        self._save()
        self.store.append_event(
            self.run_id,
            event_type="phase_entered",
            phase=phase,
            status=status,
            detail={},
        )

    def _model_for(self, packet: PromptPacket) -> str:
        capacity = self.plan["capacity"]
        if packet.operation in _REVIEW_OPERATIONS:
            return str(capacity.get("review_model", capacity["model"]))
        return str(capacity["model"])

    def _context_window_for(self, packet: PromptPacket) -> int:
        capacity = self.plan["capacity"]
        if packet.operation in _REVIEW_OPERATIONS:
            return int(
                capacity.get(
                    "review_context_window_tokens",
                    capacity.get("context_window_tokens", DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS),
                )
            )
        return int(capacity.get("context_window_tokens", DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS))

    def _reserve_prompt(
        self,
        packet: PromptPacket,
        *,
        model: str,
        context_window_tokens: int,
    ) -> tuple[int, int]:
        self.control_gate()
        prompt_bytes = len(canonical_json(packet.messages).encode("utf-8"))
        if prompt_bytes > self.bounds.max_prompt_bytes_per_call:
            raise InvestigationBudgetExhausted("model prompt exceeds the per-call byte ceiling")
        estimated_input = max(1, math.ceil(prompt_bytes / 4))
        if estimated_input + self.bounds.max_output_tokens_per_call > context_window_tokens:
            raise InvestigationBudgetExhausted("model prompt plus output ceiling exceeds the pinned context window")
        usage = self._usage()
        if int(usage.get("generation_calls", 0)) + 1 > self.bounds.max_generation_calls:
            raise InvestigationBudgetExhausted("generation-call ceiling is exhausted")
        if int(usage.get("input_tokens", 0)) + estimated_input > self.bounds.max_input_tokens:
            raise InvestigationBudgetExhausted("input-token ceiling is exhausted")
        usage["generation_calls"] = int(usage.get("generation_calls", 0)) + 1
        usage["prompt_bytes"] = int(usage.get("prompt_bytes", 0)) + prompt_bytes
        usage["input_tokens"] = int(usage.get("input_tokens", 0)) + estimated_input
        self._save()
        self.store.append_event(
            self.run_id,
            event_type="model_dispatch_reserved",
            phase=str(self.state["phase"]),
            status=RunState.RUNNING,
            detail={
                "operation": packet.operation,
                "expert_name": packet.expert_name,
                "model": model,
                "context_window_tokens": context_window_tokens,
                "prompt_bytes": prompt_bytes,
                "estimated_input_tokens": estimated_input,
                "generation_call": usage["generation_calls"],
            },
        )
        return prompt_bytes, estimated_input

    async def complete(self, packet: PromptPacket) -> str:
        """Make one bounded local call after conservatively reserving it."""
        model = self._model_for(packet)
        context_window_tokens = self._context_window_for(packet)
        _prompt_bytes, estimated_input = self._reserve_prompt(
            packet,
            model=model,
            context_window_tokens=context_window_tokens,
        )
        try:
            result = await self.backend.complete(
                ExpertChatRequest(
                    model=model,
                    messages=packet.messages,
                    extra={
                        "max_tokens": self.bounds.max_output_tokens_per_call,
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"},
                        "num_ctx": context_window_tokens,
                    },
                )
            )
        except Exception as exc:
            self.store.append_event(
                self.run_id,
                event_type="model_dispatch_failed",
                phase=str(self.state["phase"]),
                status=RunState.RUNNING,
                detail={
                    "operation": packet.operation,
                    "expert_name": packet.expert_name,
                    "error_type": type(exc).__name__,
                    "call_counted_conservatively": True,
                },
            )
            raise
        text = result.text
        measured_input = _usage_tokens(result.usage, "prompt_tokens", "input_tokens")
        measured_output = _usage_tokens(result.usage, "completion_tokens", "output_tokens")
        charged_output = _settled_output_tokens(text, measured_output)
        usage = self._usage()
        if measured_input > estimated_input:
            usage["input_tokens"] = int(usage.get("input_tokens", 0)) + measured_input - estimated_input
        usage["output_tokens"] = int(usage.get("output_tokens", 0)) + charged_output
        if measured_input > 0 and measured_input + charged_output > context_window_tokens:
            self._save()
            raise InvestigationBudgetExhausted("measured model usage exceeds the pinned context window")
        if int(usage["input_tokens"]) > self.bounds.max_input_tokens:
            self._save()
            raise InvestigationBudgetExhausted("measured input-token ceiling is exhausted")
        if charged_output > self.bounds.max_output_tokens_per_call:
            self._save()
            raise InvestigationBudgetExhausted("model output exceeds the per-call token ceiling")
        if int(usage["output_tokens"]) > self.bounds.max_output_tokens:
            self._save()
            raise InvestigationBudgetExhausted("output-token ceiling is exhausted")
        self._save()
        self.store.append_event(
            self.run_id,
            event_type="model_dispatch_completed",
            phase=str(self.state["phase"]),
            status=RunState.RUNNING,
            detail={
                "operation": packet.operation,
                "expert_name": packet.expert_name,
                "model": model,
                "context_window_tokens": context_window_tokens,
                "input_tokens": max(measured_input, estimated_input),
                "output_tokens": charged_output,
                "provider_request_id": result.provider_request_id,
                "stop_reason": result.stop_reason,
                "cost_usd": 0.0,
            },
        )
        self.control_gate(after_dispatch=True)
        return text

    def reserve_retrieval(self, expert_key: str, *, search_queries: int, page_fetches: int) -> RetrievalReservation:
        self.control_gate()
        usage = self._usage()
        if int(usage.get("search_queries", 0)) + search_queries > self.bounds.max_search_queries:
            raise InvestigationBudgetExhausted("search-query ceiling is exhausted")
        if int(usage.get("page_fetches", 0)) + page_fetches > self.bounds.max_page_fetches:
            raise InvestigationBudgetExhausted("page-fetch ceiling is exhausted")
        usage["search_queries"] = int(usage.get("search_queries", 0)) + search_queries
        usage["page_fetches"] = int(usage.get("page_fetches", 0)) + page_fetches
        self._save()
        reservation = RetrievalReservation(expert_key, search_queries, page_fetches)
        self.store.append_event(
            self.run_id,
            event_type="retrieval_reserved",
            phase=Phase.RESEARCH,
            status=RunState.RUNNING,
            detail={
                "expert_key": expert_key,
                "search_queries": search_queries,
                "page_fetches": page_fetches,
            },
        )
        return reservation

    def settle_retrieval(
        self,
        reservation: RetrievalReservation,
        *,
        actual_search_queries: int,
        actual_page_fetches: int,
    ) -> None:
        if not 0 <= actual_search_queries <= reservation.search_queries:
            raise InvestigationStorageError("retrieval search settlement exceeds its reservation")
        if not 0 <= actual_page_fetches <= reservation.page_fetches:
            raise InvestigationStorageError("retrieval page settlement exceeds its reservation")
        usage = self._usage()
        usage["search_queries"] = int(usage.get("search_queries", 0)) - (
            reservation.search_queries - actual_search_queries
        )
        usage["page_fetches"] = int(usage.get("page_fetches", 0)) - (reservation.page_fetches - actual_page_fetches)
        self._save()
        self.store.append_event(
            self.run_id,
            event_type="retrieval_settled",
            phase=Phase.RESEARCH,
            status=RunState.RUNNING,
            detail={
                "expert_key": reservation.expert_key,
                "search_queries": actual_search_queries,
                "page_fetches": actual_page_fetches,
                "cost_usd": 0.0,
            },
        )
        self.control_gate(after_dispatch=True)

    def artifact(self, logical_key: str) -> dict[str, Any] | None:
        artifacts = self.state.get("artifacts")
        if not isinstance(artifacts, dict):
            raise InvestigationStorageError("investigation artifact index is invalid")
        reference = artifacts.get(logical_key)
        if not isinstance(reference, dict):
            return None
        return self.store.read_artifact(self.run_id, reference)

    def artifact_reference(self, logical_key: str) -> dict[str, Any] | None:
        artifacts = self.state.get("artifacts")
        if not isinstance(artifacts, dict):
            raise InvestigationStorageError("investigation artifact index is invalid")
        reference = artifacts.get(logical_key)
        return dict(reference) if isinstance(reference, dict) else None

    def put_artifact(
        self,
        logical_key: str,
        *,
        phase: Phase,
        key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.control_gate(after_dispatch=True)
        reference = self.store.write_artifact(
            self.run_id,
            phase=phase,
            key=key,
            payload=payload,
            max_disk_bytes=self.bounds.max_disk_bytes,
        )
        artifacts = self.state.setdefault("artifacts", {})
        if not isinstance(artifacts, dict):
            raise InvestigationStorageError("investigation artifact index is invalid")
        existing = artifacts.get(logical_key)
        if isinstance(existing, dict) and existing.get("sha256") != reference["sha256"]:
            raise InvestigationStorageError("logical artifact idempotency conflict")
        artifacts[logical_key] = reference
        self._usage()["artifact_bytes"] = self.store.disk_usage(self.run_id)
        self._save()
        self.store.append_event(
            self.run_id,
            event_type="artifact_committed",
            phase=phase,
            status=RunState.RUNNING,
            detail={"logical_key": logical_key, "path": reference["path"], "sha256": reference["sha256"]},
        )
        return payload

    def finish(self, status: RunState, *, phase: Phase = Phase.COMPLETE) -> dict[str, Any]:
        self.state["phase"] = phase.value
        self.state["state"] = status.value
        self._usage()["artifact_bytes"] = self.store.disk_usage(self.run_id)
        self._save()
        self.store.append_event(
            self.run_id,
            event_type="run_finished",
            phase=phase,
            status=status,
            detail={"cost_usd": float(self._usage().get("cost_usd", 0.0) or 0.0)},
        )
        return self.state

    def record_error(self, exc: BaseException) -> None:
        errors = self.state.setdefault("errors", [])
        if not isinstance(errors, list):
            errors = []
            self.state["errors"] = errors
        errors.append(
            {
                "phase": str(self.state.get("phase", "")),
                "error_type": type(exc).__name__,
                "message": str(exc)[:2000],
            }
        )
        del errors[:-20]
        self._save()


__all__ = [
    "InvestigationBudgetExhausted",
    "InvestigationCancelled",
    "InvestigationPaused",
    "InvestigationRuntime",
    "RetrievalReservation",
]
