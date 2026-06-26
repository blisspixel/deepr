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
        # Read-side, $0, no state mutation (verified against recon-tool
        # v2.1.18's shipped surface, 2026-06-11)
        "lookup_tenant",
        "analyze_posture",
        "assess_exposure",
        "find_hardening_gaps",
        "chain_lookup",
        "compare_postures",
        "get_fingerprints",
        "get_signals",
        "explain_signal",
        "discover_fingerprint_candidates",
        "get_posteriors",
        "explain_dag",
        "export_graph",
        "get_infrastructure_clusters",
        "cluster_verification_tokens",
    ],
    "require_approval": [
        # Simulation / hypothesis / state-mutating tools
        "simulate_hardening",
        "test_hypothesis",
        "inject_ephemeral_fingerprint",
        "list_ephemeral_fingerprints",
        "clear_ephemeral_fingerprints",
        "reevaluate_domain",
        "reload_data",
    ],
    "progress": False,
}

# Default distillr profile template for the native first-party integration.
# Distillr (distillr package) is a source-ingestion engine: it turns YouTube,
# websites, and arXiv papers into a structured Markdown corpus with synthesis.
# Auto-discovered when the `distill-mcp` binary is on PATH (pip install distillr).
#
# Unlike recon, distillr spends model budget (ingestion runs cost money and take
# minutes), so its profile caps per-call spend, sets a long timeout, enables
# progress notifications, and only auto-approves the free read-side corpus
# tools (find/read insights and concepts, gap/cost/doctor reads). Ingestion,
# synthesis, and watch-list mutation require approval.
# Tool names live-verified against the installed distill-mcp server
# (2026-06-25). The v2.12-era names (query_library,
# ingest_papers/youtube/sites, refresh) no longer exist.
DISTILLR_PROFILE_TEMPLATE: dict[str, Any] = {
    "name": "distillr",
    "description": "Source ingestion engine: YouTube, websites, and arXiv papers into a structured Markdown corpus with cross-source synthesis. Absorbed as academic/strategic knowledge with provenance.",
    "command": "distill-mcp",
    "args": [],
    "transport": "stdio",
    "enabled": True,
    "timeout": 900,  # ingestion runs take minutes; allow up to 15m per call
    "budget_limit": 2.0,  # cap model spend per ingestion call
    "cost_per_call": 0.0,  # actual cost is reported by the tool response
    "auto_approve": [
        # Free read-side: search/read the existing corpus, no new ingestion
        "list_topics",
        "find_insights",
        "read_insight",
        "find_concepts",
        "read_concept",
        "concept_history",
        "concept_diff",
        "research_gaps",
        "list_topic_summary",
        "okf_validate",
        "costs",
        "doctor",
    ],
    "require_approval": [
        # Ingestion, synthesis, derived-export writes, and watch-list mutation
        "discover",
        "papers",
        "learn_topic",
        "process_video_url",
        "search_videos",
        "site_batch",
        "catch_up",  # the freshness/delta pull (re-ingests new material)
        "synthesize",
        "resynthesize_topic",
        "generate_report",
        "ask",
        "find_insights_summary",
        "okf_export",
        "watch_add",
        "watch_remove",
    ],
    "progress": True,
}

# Default primr profile template for the native first-party integration.
# Primr (primr package) is a strategic company-intelligence engine: adaptive
# scraping + AI synthesis into consultant-grade briefs. Auto-discovered when
# the `primr-mcp` binary is on PATH (pip install primr).
#
# Primr is the heaviest instrument: full company analyses take 35-50 minutes
# and cost real money, so EVERY cost-incurring tool requires approval and only
# the free read-side tools (estimate_run, check_jobs, doctor) auto-approve.
# The profile sets a long timeout, a higher per-call budget cap, and progress
# notifications. Async durability (resume after disconnect) is provided by the
# existing MCP task-durability layer.
PRIMR_PROFILE_TEMPLATE: dict[str, Any] = {
    "name": "primr",
    "description": "Strategic company intelligence: adaptive scraping + AI synthesis into consultant-grade briefs (competitive positioning, hiring signals, strategic initiatives, tech stack). Absorbed across infrastructure + strategic categories with provenance.",
    "command": "primr-mcp",
    "args": ["--stdio"],
    "transport": "stdio",
    "enabled": True,
    "timeout": 3600,  # full company runs take 35-50 min; allow up to 60m
    "budget_limit": 5.0,  # cap model spend per company analysis
    "cost_per_call": 0.0,  # actual cost is reported by the tool response
    "auto_approve": [
        # Free read-side (verified against primr v1.29.3's shipped surface,
        # 2026-06-11; the v2.12-era batch_analyze / quick_lookup are gone)
        "estimate_run",  # pre-flight cost/duration estimate, free
        "estimate_strategy",  # per-strategy estimate, free
        "estimate_skill_pack",  # skill-pack estimate, free
        "check_jobs",  # poll async job status, free
        "wait_for_status_change",  # long-poll job status, free
        "show_usage",  # spend/usage report, free
        "doctor",  # health check, free
        "query_roadmap",  # read primr's own roadmap notes, free
        "get_hypotheses",  # read saved hypotheses, free
    ],
    "require_approval": [
        # Spend money or mutate state
        "research_company",
        "generate_strategy",
        "generate_skill_pack",
        "run_qa",
        "delegate_to_agent",
        "save_hypothesis",
        "clear_jobs",
        "cancel_job",
    ],
    "progress": True,
}


def _resolve_env_vars(value: str) -> str:
    """Resolve ``${VAR_NAME}`` patterns from process environment.

    Raises ``ValueError`` when a referenced variable is missing; the
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


def get_distillr_profile() -> MCPClientProfile:
    """Return the default first-party distillr profile.

    Distillr (from the distillr package) is a source-ingestion engine: it
    turns YouTube videos, websites, and arXiv papers into a structured
    Markdown corpus with synthesis. It is auto-discovered when the
    `distill-mcp` command is on PATH (pip install distillr).

    Distillr spends model budget, so the profile caps per-call spend and
    only auto-approves the free read-side tool (query_library).
    """
    return MCPClientProfile.from_dict(DISTILLR_PROFILE_TEMPLATE)


def discover_distillr_profile() -> MCPClientProfile | None:
    """Return a first-party distillr profile if `distill-mcp` is available.

    Enables the native integration for users who have `pip install distillr`
    (which provides the `distill-mcp` stdio MCP server).

    Returns None if the binary is not on PATH. The returned profile is a
    fresh copy from the curated template.
    """
    if shutil.which("distill-mcp") is None:
        return None
    try:
        return MCPClientProfile.from_dict(DISTILLR_PROFILE_TEMPLATE)
    except Exception:
        logger.warning("Failed to construct discovered distillr profile")
        return None


def get_primr_profile() -> MCPClientProfile:
    """Return the default first-party primr profile.

    Primr (from the primr package) is a strategic company-intelligence engine.
    It is auto-discovered when the `primr-mcp` command is on PATH
    (pip install primr).

    Primr runs are long (35-50 min) and costly, so every cost-incurring tool
    requires approval; only the free read-side tools auto-approve.
    """
    return MCPClientProfile.from_dict(PRIMR_PROFILE_TEMPLATE)


def discover_primr_profile() -> MCPClientProfile | None:
    """Return a first-party primr profile if `primr-mcp` is available.

    Enables the native integration for users who have `pip install primr`
    (which provides the `primr-mcp` stdio MCP server).

    Returns None if the binary is not on PATH. The returned profile is a
    fresh copy from the curated template.
    """
    if shutil.which("primr-mcp") is None:
        return None
    try:
        return MCPClientProfile.from_dict(PRIMR_PROFILE_TEMPLATE)
    except Exception:
        logger.warning("Failed to construct discovered primr profile")
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
        discovers and includes first-party instruments that are installed on
        the system (recon when the `recon` binary is on PATH; distillr when
        `distill-mcp` is on PATH; primr when `primr-mcp` is on PATH).

        User profiles take precedence: if the user has explicitly defined a
        profile with the same name, the auto-discovered one is not added.

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

        # Native first-party auto-discovery. This is what makes these
        # instruments feel built-in rather than "yet another MCP server the
        # user had to configure". User-defined profiles always take
        # precedence: an explicit entry with the same name is never replaced.
        _first_party = (
            ("recon", discover_recon_profile, "recon-tool MCP server"),
            ("distillr", discover_distillr_profile, "distillr MCP server"),
            ("primr", discover_primr_profile, "primr MCP server"),
        )
        for name, discover, label in _first_party:
            if any(p.name == name for p in profiles):
                continue
            discovered = discover()
            if discovered and discovered.enabled:
                profiles.append(discovered)
                logger.info("Auto-discovered first-party %s profile (%s)", name, label)

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
