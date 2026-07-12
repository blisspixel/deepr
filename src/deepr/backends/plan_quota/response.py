"""Minimal AsyncOpenAI-shaped response objects for plan-quota adapters."""

from __future__ import annotations


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content
        self.role = "assistant"


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)


class PlanQuotaResponse:
    """One assistant choice with no metered token-usage payload."""

    def __init__(self, content: str) -> None:
        self.choices = [_Choice(content)]
        self.usage = None
