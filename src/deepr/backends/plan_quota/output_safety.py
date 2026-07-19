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
_NAMED_VALUE_RE = re.compile(
    r"(?i)(\b[A-Z][A-Z0-9_.-]{0,127}\s*[:=]\s*)"
    r"(\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,<>]+)"
)
_SECRET_LABEL_RE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?key|account[_-]?key|private[_-]?key|token|secret|password|passwd|"
    r"credential|connection[_-]?string)"
)
_TOKEN_SECRET_RE = re.compile(
    r"(?i)\b(?:(?:sk|xai|ghp|gho|github_pat|glpat)[-_][A-Za-z0-9_-]{8,}|"
    r"AIza[A-Za-z0-9_-]{8,}|AKIA[0-9A-Z]{16})\b"
)
_URL_CREDENTIAL_RE = re.compile(
    r"(?i)((?:https?|postgres(?:ql)?|mysql|mariadb|mssql|sqlserver|mongodb(?:\+srv)?|rediss?|amqps?|s?ftp)://)"
    r"[^/\s:@]+:[^/\s@]+@"
)
_JWT_SECRET_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*\b")
_ERROR_HINT_RE = re.compile(
    r"(?i)(?:^|[\s:])(?:error|fatal|failed|failure|denied|invalid|unauthorized|forbidden|not found|unavailable|timed out)(?:\b|:)"
)
_MAX_ERROR_LINES = 3
_MAX_ERROR_LINE_CHARS = 140
_MAX_ERROR_CHARS = 600
_MAX_ERROR_INPUT_CHARS = 64 * 1024
_MAX_ERROR_SOURCE_LINES = 64
_MAX_ERROR_INSPECT_LINE_CHARS = 512
_MAX_PROMPT_INSPECT_CHARS = 64 * 1024
_MAX_PROMPT_LINES = 32
_MAX_SUCCESS_OUTPUT_CHARS = 8 * 1024 * 1024
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
    text = (stderr or "")[-_MAX_ERROR_INPUT_CHARS:]
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = _CONTROL_CHAR_RE.sub(" ", text)
    text = _redact_secrets(text)
    prompt_sample = _bounded_head_tail(prompt, _MAX_PROMPT_INSPECT_CHARS)
    prompt_lines = _bounded_prompt_lines(prompt_sample)

    lines: list[str] = []
    for raw_line in text.splitlines()[-_MAX_ERROR_SOURCE_LINES:]:
        line = " ".join(raw_line.split())
        if not line:
            continue
        inspected_line = _bounded_head_tail(line, _MAX_ERROR_INSPECT_LINE_CHARS)
        if _line_overlaps_prompt(inspected_line, prompt_sample, prompt_lines=prompt_lines):
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


def safe_cli_success_output(output: str) -> str:
    """Redact recognized secrets from a bounded successful CLI response."""
    bounded = output[:_MAX_SUCCESS_OUTPUT_CHARS]
    bounded = _ANSI_ESCAPE_RE.sub("", bounded)
    bounded = _CONTROL_CHAR_RE.sub(" ", bounded)
    sanitized = _redact_secrets(bounded)
    if len(output) > _MAX_SUCCESS_OUTPUT_CHARS:
        sanitized += "\n[output truncated by safety boundary]"
    return sanitized


def _redact_secrets(text: str) -> str:
    redacted = sanitize_log_message(text)
    redacted = _BEARER_SECRET_RE.sub(r"\1[REDACTED]", redacted)
    redacted = _QUERY_SECRET_RE.sub(r"\1[REDACTED]", redacted)
    redacted = _NAMED_VALUE_RE.sub(_redact_named_value, redacted)
    redacted = _TOKEN_SECRET_RE.sub("[REDACTED]", redacted)
    redacted = _URL_CREDENTIAL_RE.sub(r"\1[REDACTED]@", redacted)
    return _JWT_SECRET_RE.sub("[REDACTED]", redacted)


def _redact_named_value(match: re.Match[str]) -> str:
    if _SECRET_LABEL_RE.search(match.group(1)):
        return f"{match.group(1)}[REDACTED]"
    return match.group(0)


def _bounded_error_line(line: str) -> str:
    if len(line) <= _MAX_ERROR_LINE_CHARS:
        return line
    head = 50
    tail = _MAX_ERROR_LINE_CHARS - head - 3
    return f"{line[:head]}...{line[-tail:]}"


def _line_overlaps_prompt(
    line: str,
    prompt: str,
    *,
    prompt_lines: tuple[str, ...] | None = None,
) -> bool:
    if not prompt:
        return False
    if line in prompt:
        return True
    payload = _prompt_echo_payload(line)
    if payload and payload in prompt:
        return True
    resolved_prompt_lines = prompt_lines if prompt_lines is not None else _bounded_prompt_lines(prompt)
    if _contains_prompt_line(line, resolved_prompt_lines):
        return True
    if len(line) < _PROMPT_ECHO_WINDOW:
        return False
    return line[:_PROMPT_ECHO_WINDOW] in prompt or line[-_PROMPT_ECHO_WINDOW:] in prompt


def _prompt_echo_payload(line: str) -> str:
    lowered = line.lower()
    for prefix in ("prompt:", "input:", "user:", "request:"):
        if lowered.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _contains_prompt_line(line: str, prompt_lines: tuple[str, ...]) -> bool:
    return any(prompt_line in line for prompt_line in prompt_lines)


def _bounded_prompt_lines(prompt: str) -> tuple[str, ...]:
    lines = [" ".join(line.split()) for line in prompt.splitlines()]
    normalized = tuple(line for line in lines if len(line) >= 4)
    if len(normalized) <= _MAX_PROMPT_LINES:
        return normalized
    half = _MAX_PROMPT_LINES // 2
    return (*normalized[:half], *normalized[-half:])


def _bounded_head_tail(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = limit // 2
    return f"{text[:head]}{text[-(limit - head) :]}"
