"""Driving a plan-quota CLI as a Deepr chat backend.

``PlanQuotaChatClient`` adapts a vendor CLI to the *minimal* async chat surface
Deepr's seams already use - ``client.chat.completions.create(model=, messages=)``
returning an object with ``.choices[0].message.content`` - exactly like
``ollama_chat_client`` does for a local model. Because it satisfies that one
surface, a single instance serves *both* the research answer and the
verification-gated belief extraction in ``ReportAbsorber``, so ``expert sync
--plan <id>`` runs end to end on prepaid capacity with no silent metered call.

Every call records one quota observation (append-only ``quota_ledger.jsonl``) and
one $0 cost-ledger event (so ``costs show`` and anomaly detection still see
volume even though the marginal dollar cost is zero). An exhaustion signature in
the CLI output is recorded as a terminal quota event and surfaced as an error so
the scheduler reschedules instead of silently failing.

``make_plan_quota_research_fn`` wraps the same client as the ``research_fn`` seam
``(query, budget) -> {"answer", "cost", ...}`` (report, never raise).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from deepr.backends.local import _local_prompt  # shared research-prompt builder
from deepr.backends.plan_quota.adapters import PlanQuotaAdapter, parse_reset_after_seconds
from deepr.backends.plan_quota.cli_runner import DEFAULT_TIMEOUT_S, CliResult, run_cli
from deepr.backends.quota_ledger import (
    QuotaConfidence,
    QuotaEventType,
    QuotaLedger,
    QuotaLedgerEvent,
)

logger = logging.getLogger(__name__)

ResearchFn = Callable[[str, float], Awaitable[dict[str, Any]]]
ContextBuilder = Callable[[str], Awaitable[Any]]
CliRunner = Callable[..., Awaitable[CliResult]]


class PlanQuotaError(RuntimeError):
    """A plan-quota CLI call failed (launch, timeout, non-zero, empty output)."""


class PlanQuotaExhausted(PlanQuotaError):
    """The plan-quota CLI reported its quota/credits are exhausted."""


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content
        self.role = "assistant"


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [_Choice(content)]
        self.usage = None


class _Completions:
    def __init__(self, client: PlanQuotaChatClient) -> None:
        self._client = client

    async def create(self, **kwargs: Any) -> _Response:
        return await self._client._run_chat(kwargs)


class _Chat:
    def __init__(self, client: PlanQuotaChatClient) -> None:
        self.completions = _Completions(client)


class PlanQuotaChatClient:
    """An AsyncOpenAI-shaped chat client backed by a vendor CLI subprocess."""

    def __init__(
        self,
        adapter: PlanQuotaAdapter,
        *,
        model: str | None = None,
        runner: CliRunner = run_cli,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
        account_id: str = "",
        quota_ledger_path: Path | None = None,
        cost_ledger_path: Path | None = None,
        operation: str = "plan_quota_research",
    ) -> None:
        self.adapter = adapter
        self.model = model
        self._runner = runner
        self._env = env
        self._cwd = cwd
        self._timeout = timeout
        self._account_id = account_id
        self._quota_ledger_path = quota_ledger_path
        self._cost_ledger_path = cost_ledger_path
        self._operation = operation
        self.chat = _Chat(self)

    async def _run_chat(self, kwargs: dict[str, Any]) -> _Response:
        messages = kwargs.get("messages") or []
        wants_json = (kwargs.get("response_format") or {}).get("type") == "json_object"
        prompt = _flatten_messages(messages, wants_json=wants_json)
        # Ignore the caller's model name: Deepr's internal ids (e.g. gpt-5-mini)
        # are meaningless to a vendor CLI, which uses its plan's model or the
        # operator's explicit --plan-model. Passing the wrong --model would fail.
        model = self.model

        result = await self._runner(
            self.adapter.build_argv(prompt, model),
            timeout=self._timeout,
            env=self._env,
            cwd=self._cwd,
        )
        answer = self._interpret(result)
        return _Response(answer)

    def _interpret(self, result: CliResult) -> str:
        """Turn a CliResult into an answer or raise a typed error. Records quota."""
        combined = f"{result.stdout}\n{result.stderr}"
        if self.adapter.looks_exhausted(combined):
            reset_at = self._reset_at_from(combined)
            self._record_quota(QuotaEventType.EXHAUSTED, detail="exhaustion signature in CLI output", reset_at=reset_at)
            when = f" (resets ~{reset_at:%H:%M UTC})" if reset_at else ""
            raise PlanQuotaExhausted(
                f"{self.adapter.display_name} quota appears exhausted - reschedule after reset{when}"
            )
        if result.launch_error:
            raise PlanQuotaError(f"{self.adapter.exe} failed to launch: {result.launch_error}")
        if result.timed_out:
            raise PlanQuotaError(f"{self.adapter.exe} timed out after {self._timeout:.0f}s")
        if not result.ok:
            raise PlanQuotaError(f"{self.adapter.exe} exited {result.returncode}: {result.stderr.strip()[:200]}")

        answer = self.adapter.parse_answer(result.stdout)
        if not answer:
            hint = " (agy drops stdout under a non-TTY pipe; a PTY is required)" if self.adapter.needs_pty else ""
            raise PlanQuotaError(f"{self.adapter.exe} returned no output{hint}")

        self._record_quota(QuotaEventType.USAGE_OBSERVED, detail="one plan-quota call")
        self._record_cost()
        return answer

    def _reset_at_from(self, text: str) -> datetime | None:
        seconds = parse_reset_after_seconds(text)
        return datetime.now(UTC) + timedelta(seconds=seconds) if seconds else None

    def _record_quota(self, event_type: QuotaEventType, *, detail: str, reset_at: datetime | None = None) -> None:
        try:
            QuotaLedger(self._quota_ledger_path).record_event(
                QuotaLedgerEvent(
                    backend_id=self.adapter.backend_id,
                    event_type=event_type,
                    account_id=self._account_id,
                    cost_model=self.adapter.cost_model,
                    window_kind=self.adapter.window_kind,
                    units_used=1.0 if event_type == QuotaEventType.USAGE_OBSERVED else None,
                    unit_name=self.adapter.unit_name,
                    # We can observe usage but not trustworthy remaining quota -
                    # vendors don't expose it. UNKNOWN keeps auto-routing off
                    # until a real remaining signal exists (eligibility gate).
                    remaining_confidence=QuotaConfidence.UNKNOWN,
                    reset_at=reset_at,
                    overage_enabled=False,
                    detail=detail,
                )
            )
        except Exception as e:  # ledger write is best-effort; never break a run
            logger.warning("plan-quota quota ledger write failed for %s: %s", self.adapter.backend_id, e)

    def _record_cost(self) -> None:
        try:
            from deepr.observability.cost_ledger import CostLedger

            CostLedger(self._cost_ledger_path).record_event(
                operation=self._operation,
                provider=f"plan_quota:{self.adapter.backend_id}",
                cost_usd=0.0,
                model=self.model or self.adapter.exe,
                source="plan_quota",
                metadata={
                    "backend_id": self.adapter.backend_id,
                    "cost_model": self.adapter.cost_model.value,
                    "quota_units": 1,
                    "unit_name": self.adapter.unit_name,
                },
            )
        except Exception as e:  # cost ledger write is best-effort
            logger.warning("plan-quota cost ledger write failed for %s: %s", self.adapter.backend_id, e)


def _flatten_messages(messages: list[dict[str, Any]], *, wants_json: bool) -> str:
    """Flatten OpenAI-style messages into one prompt a CLI accepts as an arg."""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content") or ""
        if role == "system":
            parts.append(f"[System instructions]\n{content}")
        elif role == "assistant":
            parts.append(f"[Prior assistant turn]\n{content}")
        else:
            parts.append(str(content))
    prompt = "\n\n".join(parts)
    if wants_json:
        prompt += "\n\nRespond with ONLY a single valid JSON object. No prose, no code fences."
    return prompt


def make_plan_quota_research_fn(
    adapter: PlanQuotaAdapter,
    *,
    model: str | None = None,
    context_builder: ContextBuilder | None = None,
    client: PlanQuotaChatClient | None = None,
    **client_kwargs: Any,
) -> ResearchFn:
    """Build a ``research_fn`` that answers via a plan-quota CLI at $0 marginal.

    Satisfies the sync/gap-fill seam ``(query, budget) -> {"answer", "cost"}``.
    ``cost`` is always 0.0 (prepaid plan capacity); ``budget`` is ignored. Errors
    are returned in the result, never raised, per the seam contract.
    """
    chat = client if client is not None else PlanQuotaChatClient(adapter, model=model, **client_kwargs)

    async def research_fn(query: str, budget: float) -> dict[str, Any]:
        try:
            context = await context_builder(query) if context_builder is not None else None
            prompt, metadata = _local_prompt(query, context)
            response = await chat.chat.completions.create(
                model=model or "",
                messages=[{"role": "user", "content": prompt}],
            )
            answer = response.choices[0].message.content or ""
            result: dict[str, Any] = {"answer": answer, "cost": 0.0, "backend": f"plan_quota:{adapter.backend_id}"}
            if metadata is not None:
                result["fresh_context"] = metadata
            if context is not None and hasattr(context, "to_source_pack"):
                result["source_pack"] = context.to_source_pack()
            return result
        except PlanQuotaExhausted as e:
            return {"answer": "", "cost": 0.0, "error": str(e), "quota_exhausted": True}
        except Exception as e:  # seam contract: report, do not raise
            return {"answer": "", "cost": 0.0, "error": f"{adapter.backend_id} backend error: {e}"}

    return research_fn


async def probe_plan_quota(
    adapter: PlanQuotaAdapter,
    *,
    model: str | None = None,
    runner: CliRunner = run_cli,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """A small round-trip proving the CLI runs and is authenticated. Never raises.

    Marginal cost is $0/prepaid, but it does consume one plan unit, so it is not
    literally free like the local probe - the caller decides when to run it.
    Returns ``{ok, backend, reply, latency_ms, error}``.
    """
    result = await runner(
        adapter.build_argv("Reply with exactly: OK", model),
        timeout=timeout,
        env=env,
        cwd=cwd,
    )
    if adapter.looks_exhausted(f"{result.stdout}\n{result.stderr}"):
        return {
            "ok": False,
            "backend": adapter.backend_id,
            "reply": "",
            "latency_ms": result.duration_ms,
            "error": "quota exhausted",
        }
    if not result.ok:
        err = result.launch_error or (
            "timed out" if result.timed_out else f"exit {result.returncode}: {result.stderr.strip()[:160]}"
        )
        return {"ok": False, "backend": adapter.backend_id, "reply": "", "latency_ms": result.duration_ms, "error": err}
    reply = adapter.parse_answer(result.stdout)
    return {
        "ok": bool(reply),
        "backend": adapter.backend_id,
        "reply": reply,
        "latency_ms": result.duration_ms,
        "error": "" if reply else "no output",
    }
