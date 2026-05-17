"""YAML configuration loader for MCP client profiles.

Parses ~/.deepr/integrations.yaml into validated MCPClientProfile objects
with environment variable resolution and field-level error reporting.
"""

from __future__ import annotations

import logging
import os
import re
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

# Default recon profile template for proof-of-concept
RECON_PROFILE_TEMPLATE: dict[str, Any] = {
    "name": "recon",
    "command": "recon",
    "args": ["mcp"],
    "transport": "stdio",
    "enabled": True,
    "timeout": 30,
    "budget_limit": 0,
    "auto_approve": ["domain_lookup", "batch_lookup"],
    "require_approval": ["delta"],
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
    """Return the default recon proof-of-concept profile.

    The recon profile is a free tool (budget_limit=0) that provides
    DNS intelligence via domain_lookup and batch_lookup.
    """
    return MCPClientProfile.from_dict(RECON_PROFILE_TEMPLATE)


class ConfigLoader:
    """Load and validate MCP client profiles from YAML configuration.

    Example::

        loader = ConfigLoader()
        profiles = loader.load()  # loads from ~/.deepr/integrations.yaml
        errors = loader.validate(raw_dict)
    """

    def load(self, path: Path | None = None) -> list[MCPClientProfile]:
        """Load and validate profiles from YAML config file.

        Args:
            path: Path to YAML config. Defaults to ~/.deepr/integrations.yaml.

        Returns:
            List of validated MCPClientProfile objects (only enabled ones included).

        Raises:
            FileNotFoundError: If the config file does not exist.
            ValueError: If the config file has invalid structure.
        """
        config_path = path or DEFAULT_CONFIG_PATH

        if not config_path.exists():
            logger.debug("No integrations config at %s", config_path)
            return []

        try:
            import yaml
        except ImportError as e:
            raise ImportError("PyYAML is required for config loading: pip install pyyaml") from e

        with open(config_path) as f:
            raw = yaml.safe_load(f)

        if raw is None:
            return []

        if not isinstance(raw, dict):
            raise ValueError(f"Config file must be a YAML mapping, got {type(raw).__name__}")

        errors = self.validate(raw)
        if errors:
            raise ValueError(f"Config validation failed: {'; '.join(errors)}")

        profiles: list[MCPClientProfile] = []
        for entry in raw.get("profiles", []):
            # Resolve env vars in the env dict
            env = entry.get("env", {})
            if env:
                env = _resolve_env_dict(env)

            profile_data = {**entry, "env": env}
            profile = MCPClientProfile.from_dict(profile_data)
            profiles.append(profile)

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
