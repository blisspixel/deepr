"""Prompt transport and scratch-file cleanup for plan-quota CLIs."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from deepr.backends.plan_quota.adapters import PlanQuotaAdapter

logger = logging.getLogger(__name__)


def flatten_messages(messages: list[dict[str, Any]], *, wants_json: bool) -> str:
    """Flatten OpenAI-style messages into one CLI prompt."""
    parts: list[str] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content") or ""
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


def build_invocation(
    adapter: PlanQuotaAdapter,
    prompt: str,
    model: str | None,
) -> tuple[list[str], str | None, str | None]:
    """Return argv, optional stdin, and an optional scratch prompt path."""
    if adapter.prompt_is_file:
        fd, path = tempfile.mkstemp(prefix="deepr-plan-", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(prompt)
        return adapter.build_argv(path, model), None, path
    if adapter.stdin_prompt:
        return adapter.build_argv("-", model), prompt, None
    return adapter.build_argv(prompt, model), None, None


def cleanup_prompt_file(temp_path: str | None) -> None:
    """Remove a scratch prompt without replacing the primary run outcome."""
    if not temp_path:
        return
    try:
        os.unlink(temp_path)
    except OSError:
        logger.debug("could not remove plan-quota prompt temp file")
