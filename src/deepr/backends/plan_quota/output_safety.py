"""Bounded, redacted diagnostics and exhaustion routing for plan CLIs."""

from __future__ import annotations

import re

from deepr.backends.plan_quota.adapters import PlanQuotaAdapter
from deepr.backends.plan_quota.cli_runner import CliResult
from deepr.utils.security import sanitize_log_message

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


def exhaustion_output(
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


def safe_cli_error_summary(stderr: str, *, prompt: str = "") -> str:
    """Return a bounded, redacted tail diagnostic without prompt echoes."""
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
    return any(
        line[start : start + _PROMPT_ECHO_WINDOW] in prompt for start in range(0, len(line) - _PROMPT_ECHO_WINDOW + 1)
    )


def _prompt_echo_payload(line: str) -> str:
    lowered = line.lower()
    for prefix in ("prompt:", "input:", "user:", "request:"):
        if lowered.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _contains_prompt_line(line: str, prompt: str) -> bool:
    return any(
        len(normalized) >= 4 and normalized in line
        for prompt_line in prompt.splitlines()
        if (normalized := " ".join(prompt_line.split()))
    )
