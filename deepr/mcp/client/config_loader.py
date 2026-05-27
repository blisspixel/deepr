"""YAML configuration loader for MCP client profiles.

Parses ~/.deepr/integrations.yaml into validated MCPClientProfile objects
with environment variable resolution and field-level error reporting.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any

from deepr.mcp.client.profile import MCPClientProfile

logger = logging.getLogger(__name__)

# Pattern for ${VAR_NAME} environment variable references
_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

# Valid transport types
_VALID_TRANSPORTS = frozenset({"stdio", "sse"})

# Default config path
DEFAULT_CONFIG_PATH = Path.home() / ".deepr" / "integrations.yaml"

# Default recon profile template for the native first-party integration.
# Recon (recon-tool) is a free, fast, passive domain intelligence MCP server.
# Auto-discovered when the `recon` binary is on PATH.
# Tool names reflect the actual shipped surface (lookup_tenant is the primary).
RECON_PROFILE_TEMPLATE: dict[str, Any] = {
    "name": "recon",
    "description": "Passive domain intelligence (tech stack, email security, SaaS fingerprints, related domains) via public DNS + CT + identity endpoints. Cost: $0.",
    "command": "recon",
    "args": ["mcp"],
    "transport": "stdio",
    "enabled": True,
    "timeout": 45,
    "budget_limit": 0.0,
    "cost_per_call": 0.0,
    "auto_approve": [
        "lookup_tenant",
        "analyze_posture",
        "assess_exposure",
        "find_hardening_gaps",
        "chain_lookup",
        "get_posteriors",
        "explain_dag",
    ],
    "require_approval": [
        "simulate_hardening",
        "test_hypothesis",
        "inject_ephemeral_fingerprint",
    ],
    "progress": False,
}


def _resolve_env_vars(value: str) -> str:
    """Resolve ``${VAR_NAME}`` patterns from process environment.

    Raises ``ValueError`` when a referenced variable is missing — the
    previous silent-empty behaviour produced confusing downstream
    errors (e.g. spawning an MCP server with ``API_KEY=""`` and seeing
    a 401 instead of "OPENAI_API_KEY not set").
    """
    missing: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        if var_name not in os.environ:
            missing.append(var_name)
            return ""
        return os.environ[var_name]

    resolved = _ENV_VAR_PATTERN.sub(_replace, value)
    if missing:
        raise ValueError("MCP profile references undefined environment variable(s): " + ", ".join(sorted(set(missing))))
    return resolved


def _resolve_env_dict(env: dict[str, str]) -> dict[str, str]:
    """Resolve environment variable references in an env dict."""
    return {k: _resolve_env_vars(v) for k, v in env.items()}


def get_recon_profile() -> MCPClientProfile:
    """Return the default first-party recon profile.

    Recon (from the recon-tool package) is a free ($0), fast, passive
    domain-intelligence MCP server. It is auto-discovered when the
    `recon` command is on PATH (pip install recon-tool).

    Primary tool is lookup_tenant (with format=json). The profile uses
    the actual tool surface shipped by recon-tool, not legacy names.
    """
    return MCPClientProfile.from_dict(RECON_PROFILE_TEMPLATE)


def discover_recon_profile() -> MCPClientProfile | None:
    """Return a first-party recon profile if the `recon` binary is available.

    This enables the native 1st-class integration for users who have
    `pip install recon-tool` (which provides the `recon` command and
    its stdio MCP server).

    Returns None if the binary is not on PATH, or if we should not
    auto-provide (future extension point for opt-out).

    The returned profile is a fresh copy from the curated template.
    """
    if shutil.which("recon") is None:
        return None
    try:
        return MCPClientProfile.from_dict(RECON_PROFILE_TEMPLATE)
    except Exception:
        logger.warning("Failed to construct discovered recon profile")
        return None


class ConfigLoader:
    """Load and validate MCP client profiles from YAML configuration.

    Example::

        loader = ConfigLoader()
        profiles = loader.load()  # loads from ~/.deepr/integrations.yaml
        errors = loader.validate(raw_dict)
    """

    def load(self, path: Path | None = None) -> list[MCPClientProfile]:
        """Load and validate profiles from YAML config file.

        After loading any user-provided profiles, this method automatically
        discovers and includes first-party instruments that are installed
        on the system (currently: recon when the `recon` binary is on PATH).

        User profiles take precedence: if the user has explicitly defined
        a profile named "recon", the auto-discovered one is not added.

        Args:
            path: Path to YAML config. Defaults to ~/.deepr/integrations.yaml.

        Returns:
            List of validated MCPClientProfile objects (only enabled ones included).
            May include auto-discovered first-party profiles.
        """
        config_path = path or DEFAULT_CONFIG_PATH
        profiles: list[MCPClientProfile] = []

        if config_path.exists():
            try:
                import yaml
            except ImportError as e:
                raise ImportError("PyYAML is required for config loading: pip install pyyaml") from e

            with open(config_path) as f:
                raw = yaml.safe_load(f)

            if raw is not None:
                if not isinstance(raw, dict):
                    raise ValueError(f"Config file must be a YAML mapping, got {type(raw).__name__}")

                errors = self.validate(raw)
                if errors:
                    raise ValueError(f"Config validation failed: {'; '.join(errors)}")

                for entry in raw.get("profiles", []):
                    env = entry.get("env", {})
                    if env:
                        env = _resolve_env_dict(env)
                    profile_data = {**entry, "env": env}
                    profile = MCPClientProfile.from_dict(profile_data)
                    profiles.append(profile)

        # Native first-party auto-discovery (Recon is the pilot).
        # This is what makes recon feel like a built-in instrument rather
        # than "yet another MCP server the user had to configure".
        if not any(p.name == "recon" for p in profiles):
            discovered = discover_recon_profile()
            if discovered and discovered.enabled:
                profiles.append(discovered)
                logger.info("Auto-discovered first-party recon profile (recon-tool MCP server)")

        return profiles

    def validate(self, raw: dict[str, Any]) -> list[str]:
        """Validate raw config dict and return list of errors.

        Args:
            raw: Parsed YAML dict.

        Returns:
            List of validation error strings. Empty means valid.
        """
        errors: list[str] = []

        if "profiles" not in raw:
            errors.append("Missing required field: 'profiles'")
            return errors

        profiles = raw["profiles"]
        if not isinstance(profiles, list):
            errors.append("Field 'profiles' must be a list")
            return errors

        for i, entry in enumerate(profiles):
            prefix = f"profiles[{i}]"

            if not isinstance(entry, dict):
                errors.append(f"{prefix}: must be a mapping")
                continue

            # Required fields
            if not entry.get("name"):
                errors.append(f"{prefix}.name: required field is missing or empty")

            if not entry.get("command"):
                errors.append(f"{prefix}.command: required field is missing or empty")

            # Transport validation
            transport = entry.get("transport", "stdio")
            if transport not in _VALID_TRANSPORTS:
                errors.append(
                    f"{prefix}.transport: invalid value '{transport}', must be one of: {sorted(_VALID_TRANSPORTS)}"
                )

            # Timeout must be positive
            timeout = entry.get("timeout")
            if timeout is not None:
                try:
                    if float(timeout) <= 0:
                        errors.append(f"{prefix}.timeout: must be positive, got {timeout}")
                except (TypeError, ValueError):
                    errors.append(f"{prefix}.timeout: must be a number, got '{timeout}'")

            # Budget limit must be non-negative
            budget_limit = entry.get("budget_limit")
            if budget_limit is not None:
                try:
                    if float(budget_limit) < 0:
                        errors.append(f"{prefix}.budget_limit: must be non-negative, got {budget_limit}")
                except (TypeError, ValueError):
                    errors.append(f"{prefix}.budget_limit: must be a number, got '{budget_limit}'")

        return errors
