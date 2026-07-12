"""Driving a plan-quota CLI as a Deepr chat backend.

``PlanQuotaChatClient`` adapts a vendor CLI to the *minimal* async chat surface
Deepr's seams already use - ``client.chat.completions.create(model=, messages=)``
returning an object with ``.choices[0].message.content`` - exactly like
``ollama_chat_client`` does for a local model. Because it satisfies that one
surface, a single instance serves *both* the research answer and the
verification-gated belief extraction in ``ReportAbsorber``, so ``expert sync
--plan <id>`` runs end to end on prepaid capacity with no silent metered call.

Every eligible non-metered dispatch records one $0 cost-ledger event, including
nonzero, timeout, and empty-output outcomes, so ``costs show`` and anomaly
detection see the whole attempt volume. Quota observations distinguish known
usage, exhaustion, and attempts whose usage remains unknown; a process that
never launched does not claim quota use. Metered-at-margin adapters fail before
client setup or subprocess dispatch until they support estimate, reservation,
usage settlement, and canonical cost-ledger accounting. An exhaustion signature
in the CLI output is recorded as a terminal quota event and surfaced as an error
so the scheduler reschedules instead of silently failing.

``make_plan_quota_research_fn`` wraps the same client as the ``research_fn`` seam
``(query, budget) -> {"answer", "cost", ...}`` (report, never raise).
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

from deepr.backends.context_building import (
    ContextBuilder,
    build_context,
    context_evidence_fields,
    context_generation_readiness,
    context_not_ready_error,
)
from deepr.backends.local import _local_prompt  # shared research-prompt builder
from deepr.backends.plan_quota.adapters import PlanQuotaAdapter, parse_reset_at_utc
from deepr.backends.plan_quota.cli_runner import DEFAULT_TIMEOUT_S, CliResult, run_cli
from deepr.backends.plan_quota.safety import evaluate_plan_quota_safety, plan_quota_child_env
from deepr.backends.quota_ledger import (
    QuotaConfidence,
    QuotaEventType,
    QuotaLedger,
    QuotaLedgerEvent,
)
from deepr.utils.security import sanitize_log_message

logger = logging.getLogger(__name__)

ResearchFn = Callable[[str, float], Awaitable[dict[str, Any]]]
CliRunner = Callable[..., Awaitable[CliResult]]

_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BEARER_SECRET_RE = re.compile(r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)[^\s\"'<>]+")
_QUERY_SECRET_RE = re.compile(r"(?i)([?&](?:key|api[_-]?key|access[_-]?token|token|secret)=)[^&\s\"'<>]+")
_NAMED_SECRET_RE = re.compile(
    r"(?i)((?:access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|secret)\s*[:=]\s*)[^\s\"'<>]+"
)
_TOKEN_SECRET_RE = re.compile(
    r"(?i)\b(?:(?:sk|xai|ghp|gho|github_pat|glpat)[-_][A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{8,})\b"
)
_URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")
_JWT_SECRET_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*\b")
_ERROR_HINT_RE = re.compile(
    r"(?i)(?:^|[\s:])(?:error|fatal|failed|failure|denied|invalid|unauthorized|forbidden|not found|unavailable|timed out)(?:\b|:)"
)
_MAX_ERROR_LINES = 3
_MAX_ERROR_LINE_CHARS = 140
_MAX_ERROR_CHARS = 600
_PROMPT_ECHO_WINDOW = 24


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
        resolved_env = env if env is not None else dict(os.environ)
        decision = evaluate_plan_quota_safety(adapter, env=resolved_env)
        if not decision.safe:
            raise PlanQuotaError(decision.reason)
        self.adapter = adapter
        self.model = model
        self._runner = runner
        self._env = plan_quota_child_env(adapter, resolved_env)
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

        argv, stdin, temp_path = _build_invocation(self.adapter, prompt, model)
        started_at = time.time()
        try:
            result = await self._runner(
                argv,
                stdin=stdin,
                timeout=self._timeout,
                env=self._env,
                cwd=self._cwd,
            )
        finally:
            _cleanup_prompt_file(temp_path)
        answer = self._interpret(
            result,
            answer_override=self._recover_transcript_answer(started_at),
            prompt=prompt,
        )
        return _Response(answer)

    def _recover_transcript_answer(self, started_at: float) -> str | None:
        """Read the answer from the CLI's transcript when it drops stdout.

        Antigravity exits 0 with empty stdout under a non-TTY pipe; its reply is
        only in its per-conversation transcript. None means "use stdout" (every
        other CLI) or "no transcript answer found" (which then fails as no output).
        """
        if not self.adapter.answer_from_transcript:
            return None
        from deepr.backends.plan_quota.antigravity_transcript import antigravity_brain_dir, recover_answer

        return recover_answer(antigravity_brain_dir(), since=started_at)

    def _interpret(
        self,
        result: CliResult,
        *,
        answer_override: str | None = None,
        prompt: str = "",
    ) -> str:
        """Turn a CliResult into an answer or raise a typed error. Records quota.

        ``answer_override`` supplies the answer when the CLI does not print it to
        stdout (Antigravity, recovered from its transcript). None means parse
        stdout as usual.
        """
        # Exhaustion is an error condition. Broad legacy signatures may inspect
        # all failed output, but vendor phrases that can also occur in ordinary
        # answer text are registered as error-channel-only and inspect stderr.
        # Successful stdout is never scanned.
        exhaustion_text = _exhaustion_output(self.adapter, result)
        if exhaustion_text is not None:
            reset_at = self._reset_at_from(exhaustion_text)
            when = f" (resets ~{reset_at:%H:%M UTC})" if reset_at else ""
            self._fail_attempt(
                PlanQuotaExhausted,
                f"{self.adapter.display_name} quota appears exhausted - reschedule after reset{when}",
                outcome="exhausted",
                quota_event_type=QuotaEventType.EXHAUSTED,
                quota_units=None,
                vendor_dispatched=True,
                detail="exhaustion signature in CLI output",
                reset_at=reset_at,
            )
        if result.launch_error:
            self._fail_attempt(
                PlanQuotaError,
                f"{self.adapter.exe} failed to launch: {sanitize_log_message(result.launch_error)}",
                outcome="launch_error",
                quota_event_type=None,
                quota_units=None,
                vendor_dispatched=False,
                detail="CLI process did not launch; no quota usage observed",
            )
        if result.timed_out:
            self._fail_attempt(
                PlanQuotaError,
                f"{self.adapter.exe} timed out after {self._timeout:.0f}s",
                outcome="timeout",
                quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                quota_units=None,
                vendor_dispatched=True,
                detail="CLI attempt timed out; quota usage is unknown",
            )
        if not result.ok:
            summary = _safe_cli_error_summary(result.stderr, prompt=prompt)
            self._fail_attempt(
                PlanQuotaError,
                f"{self.adapter.exe} exited {result.returncode}: {summary}",
                outcome="nonzero_exit",
                quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                quota_units=None,
                vendor_dispatched=True,
                detail=f"CLI attempt exited {result.returncode}; quota usage is unknown",
            )

        answer = answer_override if answer_override is not None else self.adapter.parse_answer(result.stdout)
        if not answer:
            hint = (
                " (agy drops stdout under a non-TTY pipe; transcript recovery found no answer)"
                if self.adapter.needs_pty
                else ""
            )
            self._fail_attempt(
                PlanQuotaError,
                f"{self.adapter.exe} returned no output{hint}",
                outcome="empty_output",
                quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                quota_units=None,
                vendor_dispatched=True,
                detail="CLI exited successfully but returned no answer; quota usage is unknown",
            )

        self._record_attempt(
            outcome="success",
            quota_event_type=QuotaEventType.USAGE_OBSERVED,
            quota_units=1.0,
            vendor_dispatched=True,
            detail="one successful plan-quota call",
        )
        return answer

    def _reset_at_from(self, text: str) -> datetime | None:
        return parse_reset_at_utc(text)

    def _fail_attempt(
        self,
        error_type: type[PlanQuotaError],
        message: str,
        *,
        outcome: str,
        quota_event_type: QuotaEventType | None,
        quota_units: float | None,
        vendor_dispatched: bool,
        detail: str,
        reset_at: datetime | None = None,
    ) -> NoReturn:
        """Record a failed attempt, then preserve its primary typed failure."""
        try:
            self._record_attempt(
                outcome=outcome,
                quota_event_type=quota_event_type,
                quota_units=quota_units,
                vendor_dispatched=vendor_dispatched,
                detail=detail,
                reset_at=reset_at,
            )
        except PlanQuotaError as accounting_error:
            message = f"{message}; {accounting_error}"
        raise error_type(message)

    def _record_attempt(
        self,
        *,
        outcome: str,
        quota_event_type: QuotaEventType | None,
        quota_units: float | None,
        vendor_dispatched: bool,
        detail: str,
        reset_at: datetime | None = None,
    ) -> None:
        if quota_event_type is not None:
            self._record_quota(
                quota_event_type,
                outcome=outcome,
                quota_units=quota_units,
                vendor_dispatched=vendor_dispatched,
                detail=detail,
                reset_at=reset_at,
            )
        self._record_cost(
            outcome=outcome,
            quota_units=quota_units,
            vendor_dispatched=vendor_dispatched,
        )

    def _record_quota(
        self,
        event_type: QuotaEventType,
        *,
        outcome: str,
        quota_units: float | None,
        vendor_dispatched: bool,
        detail: str,
        reset_at: datetime | None = None,
    ) -> None:
        try:
            QuotaLedger(self._quota_ledger_path).record_event(
                QuotaLedgerEvent(
                    backend_id=self.adapter.backend_id,
                    event_type=event_type,
                    account_id=self._account_id,
                    cost_model=self.adapter.cost_model,
                    window_kind=self.adapter.window_kind,
                    units_used=quota_units,
                    unit_name=self.adapter.unit_name,
                    # We can observe usage but not trustworthy remaining quota -
                    # vendors don't expose it. UNKNOWN keeps auto-routing off
                    # until a real remaining signal exists (eligibility gate).
                    remaining_confidence=QuotaConfidence.UNKNOWN,
                    reset_at=reset_at,
                    overage_enabled=False,
                    detail=detail,
                    metadata={
                        "outcome": outcome,
                        "vendor_dispatched": vendor_dispatched,
                        "attempted_quota_units": 1 if vendor_dispatched else 0,
                        "quota_usage_observed": quota_units is not None,
                    },
                )
            )
        except Exception as e:  # ledger write is best-effort; never break a run
            logger.warning("plan-quota quota ledger write failed for %s: %s", self.adapter.backend_id, e)

    def _record_cost(self, *, outcome: str, quota_units: float | None, vendor_dispatched: bool) -> None:
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
                    "quota_units": quota_units,
                    "unit_name": self.adapter.unit_name,
                    "outcome": outcome,
                    "vendor_dispatched": vendor_dispatched,
                    "attempted_quota_units": 1 if vendor_dispatched else 0,
                    "quota_usage_observed": quota_units is not None,
                },
            )
        except Exception as e:
            raise PlanQuotaError(f"plan-quota cost ledger write failed for {self.adapter.backend_id}: {e}") from e


def _exhaustion_output(
    adapter: PlanQuotaAdapter,
    result: CliResult,
    *,
    allow_success_stdout: bool = False,
) -> str | None:
    """Return only the output channel that established exhaustion."""
    if adapter.looks_error_channel_exhausted(result.stderr):
        return result.stderr
    if result.ok:
        output = f"{result.stdout}\n{result.stderr}" if allow_success_stdout else result.stderr
        return output if adapter.looks_exhausted(output) else None
    combined = f"{result.stdout}\n{result.stderr}"
    return combined if adapter.looks_exhausted(combined) else None


def _safe_cli_error_summary(stderr: str, *, prompt: str = "") -> str:
    """Return a bounded, redacted tail diagnostic without echoing the prompt.

    Agent CLIs commonly print a long banner and progress stream before the
    actionable terminal error. Returning the head both hides that cause and can
    expose input echoed by a vendor wrapper. This helper keeps only the final
    normalized lines, redacts credential shapes, and replaces any line that
    overlaps a distinctive prompt fragment.
    """
    text = _ANSI_ESCAPE_RE.sub("", stderr or "")
    text = _CONTROL_CHAR_RE.sub(" ", text)
    text = sanitize_log_message(text)
    text = _BEARER_SECRET_RE.sub(r"\1[REDACTED]", text)
    text = _QUERY_SECRET_RE.sub(r"\1[REDACTED]", text)
    text = _NAMED_SECRET_RE.sub(r"\1[REDACTED]", text)
    text = _TOKEN_SECRET_RE.sub("[REDACTED]", text)
    text = _URL_CREDENTIAL_RE.sub(r"\1[REDACTED]@", text)
    text = _JWT_SECRET_RE.sub("[REDACTED]", text)

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        if _line_overlaps_prompt(line, prompt):
            line = "[prompt content redacted]"
        lines.append(_bounded_error_line(line))

    if not lines:
        return "no safe stderr diagnostic; inspect the vendor CLI login and model configuration"

    selected = lines[-_MAX_ERROR_LINES:]
    terminal_cause = next((line for line in reversed(lines) if _ERROR_HINT_RE.search(line)), None)
    if terminal_cause is not None and terminal_cause not in selected:
        selected = [terminal_cause, *selected]
    summary = " | ".join(selected)
    if len(summary) > _MAX_ERROR_CHARS:
        summary = f"...{summary[-(_MAX_ERROR_CHARS - 3) :]}"
    return summary


def _bounded_error_line(line: str) -> str:
    if len(line) <= _MAX_ERROR_LINE_CHARS:
        return line
    head = 50
    tail = _MAX_ERROR_LINE_CHARS - head - 3
    return f"{line[:head]}...{line[-tail:]}"


def _line_overlaps_prompt(line: str, prompt: str) -> bool:
    if not prompt:
        return False
    if line in prompt:
        return True

    payload = _prompt_echo_payload(line)
    if payload and payload in prompt:
        return True
    if _contains_prompt_line(line, prompt):
        return True

    if len(line) < _PROMPT_ECHO_WINDOW:
        return False

    for start in range(0, len(line) - _PROMPT_ECHO_WINDOW + 1):
        if line[start : start + _PROMPT_ECHO_WINDOW] in prompt:
            return True
    return False


def _prompt_echo_payload(line: str) -> str:
    lowered = line.lower()
    for prefix in ("prompt:", "input:", "user:", "request:"):
        if lowered.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _contains_prompt_line(line: str, prompt: str) -> bool:
    for prompt_line in prompt.splitlines():
        normalized = " ".join(prompt_line.split())
        if len(normalized) >= 4 and normalized in line:
            return True
    return False


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


def _build_invocation(
    adapter: PlanQuotaAdapter, prompt: str, model: str | None
) -> tuple[list[str], str | None, str | None]:
    """Resolve how this CLI receives the prompt: file, stdin, or argv.

    Returns ``(argv, stdin, temp_path)``. ``temp_path`` is non-None only for
    file-delivery adapters and must be removed by the caller after the run.
    Long research/synthesis prompts exceed the OS command-line length limit when
    passed as an argument (WinError 206 on Windows), so file and stdin delivery
    are the headless-safe paths; argv stays for short-prompt CLIs.
    """
    if adapter.prompt_is_file:
        import tempfile

        fd, path = tempfile.mkstemp(prefix="deepr-plan-", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(prompt)
        return adapter.build_argv(path, model), None, path
    if adapter.stdin_prompt:
        return adapter.build_argv("-", model), prompt, None
    return adapter.build_argv(prompt, model), None, None


def _cleanup_prompt_file(temp_path: str | None) -> None:
    if not temp_path:
        return
    try:
        os.unlink(temp_path)
    except OSError:  # best-effort; a leaked temp file never breaks a run
        logger.debug("could not remove plan-quota prompt temp file %s", temp_path)


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

    async def research_fn(
        query: str,
        budget: float,
        *,
        prior_source_pack: dict[str, Any] | None = None,
        retrieval_query: str | None = None,
    ) -> dict[str, Any]:
        try:
            context = await build_context(
                context_builder,
                retrieval_query or query,
                prior_source_pack=prior_source_pack,
            )
            evidence_fields = context_evidence_fields(context)
            readiness = context_generation_readiness(context)
            if readiness is not None and not readiness.ready:
                return {
                    "answer": "",
                    "cost": 0.0,
                    "backend": f"plan_quota:{adapter.backend_id}",
                    "error": context_not_ready_error(readiness),
                    "error_code": "fresh_context_not_ready",
                    "retryable": readiness.retryable,
                    "no_metered_fallback": readiness.no_metered_fallback,
                    "context_preflight": readiness.to_dict(),
                    **evidence_fields,
                }
            prompt, metadata = _local_prompt(query, context)
            response = await chat.chat.completions.create(
                model=model or "",
                messages=[{"role": "user", "content": prompt}],
            )
            answer = response.choices[0].message.content or ""
            result: dict[str, Any] = {"answer": answer, "cost": 0.0, "backend": f"plan_quota:{adapter.backend_id}"}
            result.update(evidence_fields)
            if metadata is not None and "fresh_context" not in result:
                result["fresh_context"] = metadata
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
    quota_ledger_path: Path | None = None,
    cost_ledger_path: Path | None = None,
) -> dict[str, Any]:
    """A small round-trip proving the CLI runs and is authenticated. Never raises.

    Eligible backends have $0/prepaid marginal cost but consume one plan unit.
    Metered-at-margin adapters return a typed failure before argv construction
    or runner dispatch. Returns ``{ok, backend, reply, latency_ms, error}``.
    """
    resolved_env = env if env is not None else dict(os.environ)
    decision = evaluate_plan_quota_safety(adapter, env=resolved_env)
    if not decision.safe:
        return {
            "ok": False,
            "backend": adapter.backend_id,
            "reply": "",
            "latency_ms": 0,
            "error": decision.reason,
        }
    run_env = plan_quota_child_env(adapter, resolved_env)
    prompt = "Reply with exactly: OK"
    argv, stdin, temp_path = _build_invocation(adapter, prompt, model)
    started_at = time.time()
    try:
        result = await runner(
            argv,
            stdin=stdin,
            timeout=timeout,
            env=run_env,
            cwd=cwd,
        )
    finally:
        _cleanup_prompt_file(temp_path)
    exhaustion_text = _exhaustion_output(adapter, result, allow_success_stdout=True)
    if exhaustion_text is not None:
        reset_at = _reset_at_from_output(exhaustion_text)
        return _finish_probe_attempt(
            adapter,
            model=model,
            quota_ledger_path=quota_ledger_path,
            cost_ledger_path=cost_ledger_path,
            result=result,
            ok=False,
            reply="",
            error="quota exhausted",
            outcome="exhausted",
            quota_event_type=QuotaEventType.EXHAUSTED,
            quota_units=None,
            vendor_dispatched=True,
            detail="probe-plan exhaustion signature",
            reset_at=reset_at,
        )
    if not result.ok:
        if result.launch_error:
            error = sanitize_log_message(result.launch_error)
            outcome = "launch_error"
            quota_event_type = None
            quota_units = None
            vendor_dispatched = False
            detail = "probe CLI process did not launch; no quota usage observed"
        elif result.timed_out:
            error = f"timed out after {timeout:.0f}s"
            outcome = "timeout"
            quota_event_type = QuotaEventType.ATTEMPT_OBSERVED
            quota_units = None
            vendor_dispatched = True
            detail = "probe CLI attempt timed out; quota usage is unknown"
        else:
            error = f"exit {result.returncode}: {_safe_cli_error_summary(result.stderr, prompt=prompt)}"
            outcome = "nonzero_exit"
            quota_event_type = QuotaEventType.ATTEMPT_OBSERVED
            quota_units = None
            vendor_dispatched = True
            detail = f"probe CLI attempt exited {result.returncode}; quota usage is unknown"
        return _finish_probe_attempt(
            adapter,
            model=model,
            quota_ledger_path=quota_ledger_path,
            cost_ledger_path=cost_ledger_path,
            result=result,
            ok=False,
            reply="",
            error=error,
            outcome=outcome,
            quota_event_type=quota_event_type,
            quota_units=quota_units,
            vendor_dispatched=vendor_dispatched,
            detail=detail,
        )
    if adapter.answer_from_transcript:
        from deepr.backends.plan_quota.antigravity_transcript import antigravity_brain_dir, recover_answer

        reply = recover_answer(antigravity_brain_dir(), since=started_at) or ""
    else:
        reply = adapter.parse_answer(result.stdout)
    if not reply:
        return _finish_probe_attempt(
            adapter,
            model=model,
            quota_ledger_path=quota_ledger_path,
            cost_ledger_path=cost_ledger_path,
            result=result,
            ok=False,
            reply="",
            error="no output",
            outcome="empty_output",
            quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
            quota_units=None,
            vendor_dispatched=True,
            detail="probe CLI exited successfully but returned no answer; quota usage is unknown",
        )
    return _finish_probe_attempt(
        adapter,
        model=model,
        quota_ledger_path=quota_ledger_path,
        cost_ledger_path=cost_ledger_path,
        result=result,
        ok=True,
        reply=reply,
        error="",
        outcome="success",
        quota_event_type=QuotaEventType.USAGE_OBSERVED,
        quota_units=1.0,
        vendor_dispatched=True,
        detail="probe-plan successful plan call",
    )


def _finish_probe_attempt(
    adapter: PlanQuotaAdapter,
    *,
    model: str | None,
    quota_ledger_path: Path | None,
    cost_ledger_path: Path | None,
    result: CliResult,
    ok: bool,
    reply: str,
    error: str,
    outcome: str,
    quota_event_type: QuotaEventType | None,
    quota_units: float | None,
    vendor_dispatched: bool,
    detail: str,
    reset_at: datetime | None = None,
) -> dict[str, Any]:
    quota_recorded = False
    if quota_event_type is not None:
        quota_recorded = _record_probe_quota(
            adapter,
            quota_ledger_path=quota_ledger_path,
            outcome=outcome,
            event_type=quota_event_type,
            quota_units=quota_units,
            vendor_dispatched=vendor_dispatched,
            detail=detail,
            reset_at=reset_at,
        )
    ledger_error = _record_probe_cost(
        adapter,
        model=model,
        cost_ledger_path=cost_ledger_path,
        outcome=outcome,
        quota_units=quota_units,
        vendor_dispatched=vendor_dispatched,
    )
    if ledger_error:
        error = f"{error}; {ledger_error}" if error else ledger_error
        ok = False
    return {
        "ok": ok,
        "backend": adapter.backend_id,
        "reply": reply,
        "latency_ms": result.duration_ms,
        "error": error,
        "outcome": outcome,
        "vendor_dispatched": vendor_dispatched,
        "cost_event_recorded": not bool(ledger_error),
        "quota_observation_recorded": quota_recorded,
    }


def _record_probe_quota(
    adapter: PlanQuotaAdapter,
    *,
    quota_ledger_path: Path | None,
    outcome: str,
    event_type: QuotaEventType,
    quota_units: float | None,
    vendor_dispatched: bool,
    detail: str,
    reset_at: datetime | None,
) -> bool:
    try:
        QuotaLedger(quota_ledger_path).record_event(
            QuotaLedgerEvent(
                backend_id=adapter.backend_id,
                event_type=event_type,
                cost_model=adapter.cost_model,
                window_kind=adapter.window_kind,
                units_used=quota_units,
                unit_name=adapter.unit_name,
                remaining_confidence=QuotaConfidence.UNKNOWN,
                reset_at=reset_at,
                overage_enabled=False,
                detail=detail,
                metadata={
                    "outcome": outcome,
                    "vendor_dispatched": vendor_dispatched,
                    "attempted_quota_units": 1 if vendor_dispatched else 0,
                    "quota_usage_observed": quota_units is not None,
                },
            )
        )
    except Exception as e:
        logger.warning("plan-quota probe quota ledger write failed for %s: %s", adapter.backend_id, e)
        return False
    return True


def _reset_at_from_output(text: str) -> datetime | None:
    return parse_reset_at_utc(text)


def _record_probe_cost(
    adapter: PlanQuotaAdapter,
    *,
    model: str | None,
    cost_ledger_path: Path | None,
    outcome: str,
    quota_units: float | None,
    vendor_dispatched: bool,
) -> str:
    from deepr.observability.cost_ledger import CostLedger

    try:
        CostLedger(cost_ledger_path).record_event(
            operation="plan_quota_probe",
            provider=f"plan_quota:{adapter.backend_id}",
            cost_usd=0.0,
            model=model or adapter.exe,
            source="plan_quota",
            metadata={
                "backend_id": adapter.backend_id,
                "cost_model": adapter.cost_model.value,
                "quota_units": quota_units,
                "unit_name": adapter.unit_name,
                "outcome": outcome,
                "vendor_dispatched": vendor_dispatched,
                "attempted_quota_units": 1 if vendor_dispatched else 0,
                "quota_usage_observed": quota_units is not None,
            },
        )
    except Exception as e:
        return f"cost ledger write failed for plan-quota probe {adapter.backend_id}: {e}"
    return ""
