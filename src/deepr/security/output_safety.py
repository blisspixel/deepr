"""Safety helpers for derived host-facing output payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from deepr.utils.prompt_security import PromptSanitizer

_BEARER_SECRET_RE = re.compile(r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)[^\s\"'<>]+")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:key|api[_-]?key|access[_-]?token|token|secret|sig|signature|"
    r"x-goog-api-key|x-goog-signature|x-amz-security-token|x-amz-signature)=)[^&\s\"'<>]+"
)
_NAMED_SECRET_RE = re.compile(
    r"(?i)(?P<label>\b(?:api[_-]?key|access[_-]?key|account[_-]?key|private[_-]?key|token|secret|password|"
    r"passwd|client[_-]?secret|credential|connection[_-]?string))"
    r"(?P<separator>\s*[:=]\s*)(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,<>]+)"
)
_ENV_ASSIGNMENT_RE = re.compile(
    r"(?P<label>\b[A-Z][A-Z0-9_.-]{1,127})(?P<separator>\s*[:=]\s*)"
    r"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,<>]+)"
)
_SENSITIVE_FIELD_RE = re.compile(
    r"(?i)^(?:api[_-]?key|access[_-]?key|account[_-]?key|private[_-]?key|secret[_-]?access[_-]?key|"
    r"auth[_-]?token|access[_-]?token|client[_-]?secret|token|secret|password|passwd|credential|credentials|"
    r"connection[_-]?string|authorization)$"
)
_SENSITIVE_ENV_FIELD_RE = re.compile(
    r"^[A-Z][A-Z0-9_.-]{1,127}(?:_API_KEY|_SECRET_ACCESS_KEY|_SERVICE_ACCOUNT_KEY|_PRIVATE_KEY|"
    r"_SIGNING_KEY|_ENCRYPTION_KEY|_SECRET_KEY|_ACCESS_TOKEN|_AUTH_TOKEN|_BEARER_TOKEN|_BOT_TOKEN|"
    r"_API_TOKEN|_REFRESH_TOKEN|_ID_TOKEN|_CLIENT_SECRET|_WEBHOOK_SECRET|_APP_SECRET|_API_SECRET|"
    r"_PASSWORD|_PASSWD|_CREDENTIAL|_CREDENTIALS|_CONNECTION_STRING)$"
)
_KNOWN_ENV_SECRET_FIELDS = frozenset(
    {
        "AWS_SECURITY_TOKEN",
        "AWS_SESSION_TOKEN",
        "AZURE_OPENAI_KEY",
        "GITHUB_TOKEN",
        "GITLAB_TOKEN",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
        "SLACK_TOKEN",
    }
)
_SENSITIVE_HEADER_FIELD_RE = re.compile(
    r"(?i)^(?:proxy[_-]?authorization|x[_-]api[_-]?key|"
    r"x[_-]goog[_-]api[_-]?key|x[_-]auth[_-]?token|x[_-]access[_-]?token|"
    r"x[_-]amz[_-]security[_-]?token|ocp[_-]apim[_-]subscription[_-]?key)$"
)
_AMBIGUOUS_HEADER_FIELD_RE = re.compile(r"(?i)^(?:cookie|set[_-]?cookie)$")
_HEADER_CONTAINER_RE = re.compile(r"(?i)^(?:(?:http|request|response)[_-]?)?headers?$")
_TOKEN_SECRET_RE = re.compile(
    r"(?i)\b(?:(?:sk|xai|ghp|gho|github_pat|glpat)[-_][A-Za-z0-9_-]{8,}|"
    r"AIza[A-Za-z0-9_-]{8,}|AKIA[0-9A-Z]{16})\b"
)
_URL_CREDENTIAL_RE = re.compile(
    r"(?i)((?:https?|postgres(?:ql)?|mysql|mariadb|mssql|sqlserver|mongodb(?:\+srv)?|rediss?|amqps?|s?ftp)://)"
    r"[^/\s:@]+:[^/\s@]+@"
)
_JWT_SECRET_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*\b")
_MAX_HOST_PAYLOAD_DEPTH = 96
_NESTING_LIMIT_MARKER = "[CONTENT OMITTED: nesting limit exceeded]"
_HIGH_CONFIDENCE_SECRET_LABELS = frozenset(
    {
        "api_key",
        "access_key",
        "account_key",
        "private_key",
        "password",
        "passwd",
        "client_secret",
        "credential",
        "connection_string",
    }
)


def _redact_host_secrets(text: str) -> str:
    """Redact recognized credential forms without altering ordinary prose."""
    redacted = _BEARER_SECRET_RE.sub(r"\1[REDACTED]", text)
    redacted = _QUERY_SECRET_RE.sub(r"\1[REDACTED]", redacted)
    redacted = _ENV_ASSIGNMENT_RE.sub(_redact_sensitive_env_assignment, redacted)
    redacted = _NAMED_SECRET_RE.sub(_redact_credential_like_assignment, redacted)
    redacted = _TOKEN_SECRET_RE.sub("[REDACTED]", redacted)
    redacted = _URL_CREDENTIAL_RE.sub(r"\1[REDACTED]@", redacted)
    return _JWT_SECRET_RE.sub("[REDACTED]", redacted)


def _redact_sensitive_env_assignment(match: re.Match[str]) -> str:
    if not _is_sensitive_env_field(match.group("label")):
        return match.group(0)
    return f"{match.group('label')}{match.group('separator')}[REDACTED]"


def _redact_credential_like_assignment(match: re.Match[str]) -> str:
    label = match.group("label").casefold().replace("-", "_")
    separator = match.group("separator")
    raw_value = match.group("value").strip("\"'")
    is_structured_assignment = "=" in separator or label in _HIGH_CONFIDENCE_SECRET_LABELS
    if not is_structured_assignment:
        return match.group(0)
    has_whitespace = any(character.isspace() for character in raw_value)
    has_digit = any(character.isdigit() for character in raw_value)
    separators = sum(not character.isalnum() for character in raw_value)
    if has_whitespace or len(raw_value) >= 16 or (len(raw_value) >= 12 and (has_digit or separators >= 2)):
        return f"{match.group('label')}{separator}[REDACTED]"
    return match.group(0)


def _is_sensitive_field_name(field_name: str, *, header_context: bool) -> bool:
    unambiguous = (
        _SENSITIVE_FIELD_RE.fullmatch(field_name) is not None
        or _is_sensitive_env_field(field_name)
        or _SENSITIVE_HEADER_FIELD_RE.fullmatch(field_name) is not None
    )
    return unambiguous or (header_context and _AMBIGUOUS_HEADER_FIELD_RE.fullmatch(field_name) is not None)


def _is_sensitive_env_field(field_name: str) -> bool:
    return field_name in _KNOWN_ENV_SECRET_FIELDS or _SENSITIVE_ENV_FIELD_RE.fullmatch(field_name) is not None


def sanitize_host_facing_payload(value: Any, *, source_label: str = "host-facing payload") -> Any:
    """Redact credentials and neutralize directives in derived payload text.

    This guards JSON payloads that downstream hosts may place into prompts.
    It is not a truth or grounding check, and it does not mutate canonical
    expert state.
    """
    sanitizer = PromptSanitizer()
    return _sanitize_host_facing_payload(value, source_label=source_label, sanitizer=sanitizer)


def _sanitize_host_facing_payload(
    value: Any,
    *,
    source_label: str,
    sanitizer: PromptSanitizer,
    sensitive_field: bool = False,
    depth: int = 0,
    header_context: bool = False,
) -> Any:
    if sensitive_field:
        return None if value is None else "[REDACTED]"
    if depth > _MAX_HOST_PAYLOAD_DEPTH:
        return _NESTING_LIMIT_MARKER
    if isinstance(value, str):
        redacted = _redact_host_secrets(value)
        return sanitizer.sanitize_untrusted_content(redacted, source_label=source_label).sanitized
    if isinstance(value, Mapping):
        return {
            _sanitize_host_facing_payload(key, source_label=source_label, sanitizer=sanitizer)
            if isinstance(key, str)
            else key: (
                _sanitize_host_facing_payload(
                    child,
                    source_label=source_label,
                    sanitizer=sanitizer,
                    sensitive_field=isinstance(key, str)
                    and _is_sensitive_field_name(key, header_context=header_context),
                    depth=depth + 1,
                    header_context=isinstance(key, str) and _HEADER_CONTAINER_RE.fullmatch(key) is not None,
                )
            )
            for key, child in value.items()
        }
    if isinstance(value, list | tuple):
        return [
            _sanitize_host_facing_payload(
                item,
                source_label=source_label,
                sanitizer=sanitizer,
                depth=depth + 1,
                header_context=header_context,
            )
            for item in value
        ]
    return value
