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
        # The previously recorded sunset (2026-03-26) did not happen - the
        # unversioned alias is still served by the live API (verified
        # 2026-06-11). Informational entry only: with no sunset date, runs
        # do not warn (a default model that triggered its own deprecation
        # warning on every run was a live-reported confusion).
        sunset_date="",
        warning="The unversioned 'o3-deep-research' alias is still served (verified 2026-06-11). Pin 'o3-deep-research-2025-06-26' for reproducibility, or use 'o4-mini-deep-research' ($2/$8 per MTok) for cheaper runs.",
    ),
    # Grok retirement wave (May 15, 2026)
    "grok-4-1-fast-reasoning": DeprecationEntry(
        old_model="grok-4-1-fast-reasoning",
        new_model="xai/grok-4-3",
        sunset_date="2026-05-15",
        warning="Grok 4.1 Fast Reasoning retires May 15, 2026. Successor: Grok 4.3.",
        auto_migrate=True,
    ),
    "grok-4-1-fast-non-reasoning": DeprecationEntry(
        old_model="grok-4-1-fast-non-reasoning",
        new_model="xai/grok-4-20-non-reasoning",
        sunset_date="2026-05-15",
        warning="Grok 4.1 Fast Non-Reasoning retires May 15, 2026. Successor: Grok 4.20 Non-Reasoning.",
        auto_migrate=True,
    ),
    "grok-4-fast-reasoning": DeprecationEntry(
        old_model="grok-4-fast-reasoning",
        new_model="xai/grok-4-3",
        sunset_date="2026-05-15",
        warning="Grok 4 Fast Reasoning retires May 15, 2026. Successor: Grok 4.3.",
        auto_migrate=True,
    ),
    "grok-4-fast-non-reasoning": DeprecationEntry(
        old_model="grok-4-fast-non-reasoning",
        new_model="xai/grok-4-20-non-reasoning",
        sunset_date="2026-05-15",
        warning="Grok 4 Fast Non-Reasoning retires May 15, 2026. Successor: Grok 4.20 Non-Reasoning.",
        auto_migrate=True,
    ),
    "grok-4-0709": DeprecationEntry(
        old_model="grok-4-0709",
        new_model="xai/grok-4-3",
        sunset_date="2026-05-15",
        warning="Grok 4 (0709) retires May 15, 2026. Successor: Grok 4.3.",
        auto_migrate=True,
    ),
    "grok-code-fast-1": DeprecationEntry(
        old_model="grok-code-fast-1",
        new_model="xai/grok-4-3",
        sunset_date="2026-05-15",
        warning="Grok Code Fast 1 retires May 15, 2026. Successor: Grok 4.3.",
        auto_migrate=True,
    ),
    "grok-3": DeprecationEntry(
        old_model="grok-3",
        new_model="xai/grok-4-3",
        sunset_date="2026-05-15",
        warning="Grok 3 retires May 15, 2026. Successor: Grok 4.3.",
        auto_migrate=True,
    ),
    "grok-imagine-image-pro": DeprecationEntry(
        old_model="grok-imagine-image-pro",
        new_model="xai/grok-imagine-image",
        sunset_date="2026-05-15",
        warning="Grok Imagine Image Pro retires May 15, 2026. Successor: Grok Imagine Image.",
        auto_migrate=True,
    ),
    # Legacy Grok models (older deprecations)
    "grok-3-mini": DeprecationEntry(
        old_model="grok-3-mini",
        new_model="xai/grok-4-3",
        sunset_date="2026-05-15",
        warning="Grok 3 Mini retires May 15, 2026. Successor: Grok 4.3.",
    ),
    # Legacy Gemini
    "gemini-3-pro": DeprecationEntry(
        old_model="gemini-3-pro",
        new_model="gemini-3.1-pro-preview",
        sunset_date="",
        warning="Gemini 3 Pro is superseded by Gemini 3.1 Pro Preview.",
    ),
    "gemini-3-pro-preview": DeprecationEntry(
        old_model="gemini-3-pro-preview",
        new_model="gemini-3.1-pro-preview",
        sunset_date="",
        warning="Gemini 3 Pro Preview is listed in Google's shut-down previous-model set. Use Gemini 3.1 Pro Preview.",
        auto_migrate=True,
    ),
    "gemini-3.1-flash-lite-preview": DeprecationEntry(
        old_model="gemini-3.1-flash-lite-preview",
        new_model="gemini-3.1-flash-lite",
        sunset_date="",
        warning=(
            "Gemini 3.1 Flash-Lite Preview is listed in Google's shut-down previous-model set. "
            "Use Gemini 3.1 Flash-Lite."
        ),
        auto_migrate=True,
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
    # Sort by key length descending so "gpt-4o-mini" matches before "gpt-4o"
    for key in sorted(DEPRECATION_REGISTRY, key=len, reverse=True):
        if model.startswith(key + "-") or model.startswith(key + "/"):
            return DEPRECATION_REGISTRY[key]

    return None


def migrate_model(model: str, confidence: float = 1.0) -> tuple[str, float, str | None]:
    """Resolve a model, auto-migrating if deprecated.

    Returns:
        (resolved_model, confidence, warning_or_none)
        If model is not deprecated, returns (model, confidence, None).
        If deprecated and auto_migrate is True, returns (new_model, confidence, warning).
        If deprecated but auto_migrate is False, returns (model, confidence, warning).
        Confidence is preserved through migration (passed through unchanged).
    """
    entry = check_deprecation(model)
    if entry is None:
        return model, confidence, None

    # Handle edge case: deprecated model with no successor
    if not entry.new_model:
        logger.error("Model %s is retired with no migration path", model)
        return model, confidence, f"Model {model} is retired with no migration path."

    logger.warning(
        "Model deprecation: %s -> %s (confidence=%.4f) (%s)",
        model,
        entry.new_model,
        confidence,
        entry.warning,
    )

    # Strip any provider prefix ("openai/", "xai/", "anthropic/", …)
    # from the successor before returning. Callers like auto_mode pass
    # plain model strings to provider clients which don't understand the
    # prefix form; without this, post-migration calls fail with "model
    # not found" against the new model.
    successor = entry.new_model
    if successor and "/" in successor:
        successor = successor.split("/", 1)[1]

    if entry.auto_migrate:
        return successor, confidence, entry.warning

    return model, confidence, entry.warning
