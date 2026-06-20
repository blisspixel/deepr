"""Safety helpers for derived host-facing output payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from deepr.utils.prompt_security import PromptSanitizer


def sanitize_host_facing_payload(value: Any, *, source_label: str = "host-facing payload") -> Any:
    """Neutralize directive canaries in derived payload text.

    This guards JSON payloads that downstream hosts may place into prompts.
    It is not a truth or grounding check, and it does not mutate canonical
    expert state.
    """
    sanitizer = PromptSanitizer()
    return _sanitize_host_facing_payload(value, source_label=source_label, sanitizer=sanitizer)


def _sanitize_host_facing_payload(value: Any, *, source_label: str, sanitizer: PromptSanitizer) -> Any:
    if isinstance(value, str):
        return sanitizer.sanitize_untrusted_content(value, source_label=source_label).sanitized
    if isinstance(value, Mapping):
        return {
            _sanitize_host_facing_payload(key, source_label=source_label, sanitizer=sanitizer)
            if isinstance(key, str)
            else key: (_sanitize_host_facing_payload(child, source_label=source_label, sanitizer=sanitizer))
            for key, child in value.items()
        }
    if isinstance(value, list | tuple):
        return [_sanitize_host_facing_payload(item, source_label=source_label, sanitizer=sanitizer) for item in value]
    return value
