"""Lifecycle-aware presentation of finite CLI model choices.

Historical identities remain accepted without becoming advertised defaults.
This module grants no dispatch or migration authority.
"""

from datetime import UTC, date, datetime
from typing import Any

import click

from deepr.providers.registry_pricing import get_resolved_model_capability
from deepr.routing.deprecation import check_deprecation


def is_shutdown(model: str, *, today: date | None = None) -> bool:
    """Compare a provider's recorded deadline, never infer it from a model name."""
    entry = check_deprecation(model)
    return bool(
        entry and entry.sunset_date and date.fromisoformat(entry.sunset_date) <= (today or datetime.now(UTC).date())
    )


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
    """Advertise live members; recognize only the original historical set."""

    def __init__(self, models: list[str]) -> None:
        self.accepted = tuple(models)
        super().__init__([model for model in models if not is_shutdown(model)])

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> str:
        selected = value if value in self.accepted else super().convert(value, param, ctx)
        note = model_note(selected)
        if note and not (ctx and ctx.resilient_parsing):
            click.echo(note, err=True)
        return str(selected)


def research_model_choice() -> ModelChoice:
    """The established finite research contract, with historical compatibility."""
    return ModelChoice(["gpt-5.6-sol", "gpt-5.6-terra", "o4-mini-deep-research", "o3-deep-research"])


def retained_task_models() -> dict[str, tuple[str, str]]:
    """Read shipped defaults without loading credentials or benchmark overrides."""
    from deepr.config import ProviderConfig

    return dict(ProviderConfig.model_fields["TASK_MODEL_MAP"].default)


def research_preview_example() -> str:
    provider, model = retained_task_models()["deep_research"]
    return f'deepr research "your question" --provider {provider} --model {model} --preview'
