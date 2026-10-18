"""Human configuration display; loading and authority remain in Settings."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from deepr.config import configuration_source_summary

if TYPE_CHECKING:
    from deepr.core.settings import Settings


def format_settings(settings: Settings, *, mask_keys: bool = True) -> str:
    """Show compatibility defaults and the requested/effective budget separately."""
    lines = [
        "Deepr Configuration",
        "=" * 50,
        f"Source: {settings._source}",
        configuration_source_summary(),
        "",
        "Core Settings:",
        f"  Environment: {settings.environment}",
        f"  Debug: {settings.debug}",
        f"  Log Level: {settings.log_level}",
        f"  Data Dir: {Path(settings.data_dir).expanduser().resolve()}",
        "",
        "Compatibility Provider Settings (not execution authority):",
        f"  Default Provider: {settings.default_provider}",
        f"  Default Model: {settings.default_model}",
        f"  Deep Research Provider: {settings.deep_research_provider}",
        f"  Deep Research Model: {settings.deep_research_model}",
        "",
        "Configured Providers:",
    ]

    for name, config in settings.providers.items():
        key_display = "***" if mask_keys and config.api_key else (config.api_key or "(not set)")
        status = "enabled" if config.enabled and config.is_configured() else "disabled"
        lines.append(f"  {name}:")
        lines.append(f"    API Key: {key_display}")
        lines.append(f"    Model: {config.default_model or '(default)'}")
        lines.append(f"    Status: {status}")

    lines.extend(
        [
            "",
            "Storage:",
            f"  Type: {settings.storage.type.value}",
            f"  Path: {Path(settings.storage.local_path).expanduser().resolve()}",
            "",
            "Budget Limits:",
            *[
                f"  {label}: ${getattr(settings.budget, key):.2f} effective "
                f"(${settings._requested_budget.get(key, getattr(settings.budget, key)):.2f} requested)"
                for label, key in (
                    ("Per Job", "max_cost_per_job"),
                    ("Daily", "daily_limit"),
                    ("Monthly", "monthly_limit"),
                )
            ],
            f"  Reason: {settings._budget_reason}",
            "  Numeric ceilings do not authorize a provider. Inspect: deepr budget status.",
            "  Attended OpenRouter requires deepr budget authorize openrouter and its live execution checks.",
        ]
    )

    if settings._overrides:
        lines.extend(["", "Overrides:"])
        for key, source in sorted(settings._overrides.items()):
            lines.append(f"  {key}: from {source}")

    return "\n".join(lines)
