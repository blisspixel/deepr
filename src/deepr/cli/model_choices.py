"""Lifecycle-aware presentation of finite CLI model choices.

Historical identities remain accepted without becoming advertised defaults.
This module grants no dispatch or migration authority.
"""

from typing import Any

import click

from deepr.providers.registry_pricing import get_resolved_model_capability
from deepr.routing.deprecation import check_deprecation, is_shutdown

__all__ = ["ModelChoice", "is_shutdown", "model_help", "model_note", "planner_model_choice", "research_model_choice"]


def model_note(model: str) -> str:
    """Return the existing lifecycle notice without changing the selected ID."""
    capability = get_resolved_model_capability(model)
    if capability and capability.access_note:
        return capability.access_note
    entry = check_deprecation(capability.model if capability else model)
    return entry.warning if entry and entry.sunset_date else ""


def model_help(description: str, default: str) -> str:
    note = model_note(default)
    return f"{description}. {note}" if note else description


class ModelChoice(click.Choice[str]):
    """Advertise current members; still accept historical ids for notice or refusal."""

    def __init__(self, models: list[str], *, historical: list[str] | None = None) -> None:
        self.accepted = tuple(dict.fromkeys([*models, *(historical or [])]))
        super().__init__([model for model in models if not is_shutdown(model)])

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> str:
        selected = value if value in self.accepted else super().convert(value, param, ctx)
        note = model_note(selected)
        if note and not (ctx and ctx.resilient_parsing):
            click.echo(note, err=True)
        return str(selected)


_CURRENT_OPENAI = ["gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna", "gpt-6-astra"]
_HISTORICAL_OPENAI = [
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "o4-mini-deep-research",
    "o3-deep-research",
]


def research_model_choice() -> ModelChoice:
    """Current OpenAI research ids, plus historical ids that still price or refuse."""
    return ModelChoice(_CURRENT_OPENAI, historical=_HISTORICAL_OPENAI)


def planner_model_choice() -> ModelChoice:
    """Current planner ids. Retiring GPT-5 ids stay accepted and unadvertised."""
    return ModelChoice(_CURRENT_OPENAI, historical=_HISTORICAL_OPENAI[:6])


def retained_task_models() -> dict[str, tuple[str, str]]:
    """Read shipped defaults without loading credentials or benchmark overrides."""
    from deepr.config import ProviderConfig

    return dict(ProviderConfig.model_fields["TASK_MODEL_MAP"].default)


def research_preview_example() -> str:
    provider, model = retained_task_models()["deep_research"]
    return f'deepr research "your question" --provider {provider} --model {model} --preview'
