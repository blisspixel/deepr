"""Model deprecation registry and transparent auto-migration.

Detects deprecated model IDs, warns users, and routes to successors.
Prevents silent breakage when providers remove legacy endpoints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeprecationEntry:
    """A deprecated model and its migration target."""

    old_model: str
    new_model: str
    sunset_date: str = ""  # ISO date string, e.g. "2026-03-26"
    warning: str = ""
    auto_migrate: bool = True


# Canonical deprecation registry.
# Add entries here when providers announce model removal.
DEPRECATION_REGISTRY: dict[str, DeprecationEntry] = {
    # OpenAI legacy deep research aliases
    "o3-deep-research": DeprecationEntry(
        old_model="o3-deep-research",
        new_model="o3-deep-research-2025-06-26",
        sunset_date="2026-03-26",
        warning="OpenAI is removing the unversioned 'o3-deep-research' alias. Use 'o3-deep-research-2025-06-26' or 'o4-mini-deep-research'.",
    ),
    # Legacy Grok models
    "grok-3": DeprecationEntry(
        old_model="grok-3",
        new_model="grok-4.20-0309-reasoning",
        sunset_date="",
        warning="Grok 3 is superseded by Grok 4.20. Auto-migrating to grok-4.20-0309-reasoning.",
    ),
    "grok-3-mini": DeprecationEntry(
        old_model="grok-3-mini",
        new_model="grok-4-1-fast-reasoning",
        sunset_date="",
        warning="Grok 3 Mini is superseded by Grok 4.1 Fast. Auto-migrating.",
    ),
    # Legacy Gemini
    "gemini-3-pro": DeprecationEntry(
        old_model="gemini-3-pro",
        new_model="gemini-3.1-pro-preview",
        sunset_date="",
        warning="Gemini 3 Pro is superseded by Gemini 3.1 Pro Preview.",
    ),
    # Legacy GPT-4o
    "gpt-4o": DeprecationEntry(
        old_model="gpt-4o",
        new_model="gpt-4.1",
        sunset_date="",
        warning="GPT-4o is superseded by GPT-4.1 (1M context, same price). Auto-migrating.",
        auto_migrate=True,
    ),
    "gpt-4o-mini": DeprecationEntry(
        old_model="gpt-4o-mini",
        new_model="gpt-4.1-mini",
        sunset_date="",
        warning="GPT-4o-mini is superseded by GPT-4.1-mini. Auto-migrating.",
        auto_migrate=True,
    ),
}


def check_deprecation(model: str) -> DeprecationEntry | None:
    """Check if a model is deprecated.

    Returns the DeprecationEntry if found, None otherwise.
    Performs exact match then falls back to prefix matching.
    """
    # Exact match
    if model in DEPRECATION_REGISTRY:
        return DEPRECATION_REGISTRY[model]

    # Prefix match for versioned variants (e.g. "gpt-4o-2024-08-06")
    for key, entry in DEPRECATION_REGISTRY.items():
        if model.startswith(key + "-") or model.startswith(key + "/"):
            return entry

    return None


def migrate_model(model: str) -> tuple[str, str | None]:
    """Resolve a model, auto-migrating if deprecated.

    Returns:
        (resolved_model, warning_or_none)
        If model is not deprecated, returns (model, None).
        If deprecated and auto_migrate is True, returns (new_model, warning).
        If deprecated but auto_migrate is False, returns (model, warning).
    """
    entry = check_deprecation(model)
    if entry is None:
        return model, None

    logger.warning("Model deprecation: %s -> %s (%s)", model, entry.new_model, entry.warning)

    if entry.auto_migrate:
        return entry.new_model, entry.warning

    return model, entry.warning
