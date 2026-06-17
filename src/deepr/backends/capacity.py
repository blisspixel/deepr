"""Capacity-source detection (read-only, $0).

Reports what research capacity is available to the operator across three
kinds - owned/local hardware, plan-quota CLIs, and metered APIs - so the
operator (and, later, the waterfall router) can prefer capacity they already
pay for over per-call API spend. Detection only: this never runs research and
never spends. Design: docs/design/capacity-waterfall.md.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from enum import Enum


class CostModel(str, Enum):
    """How a backend's work is paid for, cheapest-at-the-margin first."""

    OWNED_HARDWARE = "owned_hardware"  # local GPU; $0 at the margin
    CREDIT_POOL = "credit_pool"  # monthly prepaid credits (e.g. Claude plan pool)
    ROLLING_WINDOW = "rolling_window"  # N-hour rolling quota (Codex)
    CALENDAR_WINDOW = "calendar_window"  # weekly/monthly compute caps (Antigravity, Kiro)
    METERED = "metered"  # pay per API call - the expensive last resort


class BackendKind(str, Enum):
    LOCAL = "local"
    PLAN_QUOTA = "plan_quota"
    API_METERED = "api_metered"


# Marginal-cost label per cost model (what one more job costs the user now).
_MARGINAL = {
    CostModel.OWNED_HARDWARE: "$0 (local)",
    CostModel.CREDIT_POOL: "quota (prepaid)",
    CostModel.ROLLING_WINDOW: "quota (prepaid)",
    CostModel.CALENDAR_WINDOW: "quota (prepaid)",
    CostModel.METERED: "paid per call",
}


@dataclass
class CapacitySource:
    """One detected (or detectable) place research could run."""

    name: str
    kind: BackendKind
    cost_model: CostModel
    available: bool
    detail: str = ""
    backend_id: str = ""

    @property
    def marginal_cost(self) -> str:
        return _MARGINAL[self.cost_model]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "cost_model": self.cost_model.value,
            "available": self.available,
            "backend_id": self.backend_id,
            "marginal_cost": self.marginal_cost,
            "detail": self.detail,
        }


# Provider env vars and their display names (metered API capacity).
_PROVIDERS: list[tuple[str, str]] = [
    ("OpenAI", "OPENAI_API_KEY"),
    ("Gemini", "GEMINI_API_KEY"),
    ("xAI Grok", "XAI_API_KEY"),
    ("Anthropic", "ANTHROPIC_API_KEY"),
    ("Azure OpenAI", "AZURE_OPENAI_API_KEY"),
]

# Plan-quota CLIs: display name, executable, cost model, install hint.
# (Grok consumer plans have no sanctioned headless path - excluded from the
# plan-quota set; xAI credits flow through the metered API instead.)
_CLI_BACKENDS: list[tuple[str, str, CostModel, str]] = [
    # claude -p moved to a separate API-rate credit pool on 2026-06-15 (stops or
    # overflow-bills when empty) - bounded-prepaid, not free; overflow must be off.
    (
        "Claude Code",
        "claude",
        CostModel.CREDIT_POOL,
        "separate credit pool at API rates (2026-06-15); overflow must be off",
    ),
    ("Codex CLI", "codex", CostModel.ROLLING_WINDOW, "ChatGPT plan, 5h rolling windows"),
    (
        "Copilot CLI",
        "copilot",
        CostModel.CREDIT_POOL,
        "GitHub plan, monthly AI credits (metered per token; overflow admin-capped)",
    ),
    ("Cursor CLI", "cursor-agent", CostModel.CREDIT_POOL, "Cursor plan; Auto model free, frontier models metered"),
    ("Antigravity", "agy", CostModel.CALENDAR_WINDOW, "Google AI plan, weekly compute caps"),
    ("Kiro CLI", "kiro-cli", CostModel.CALENDAR_WINDOW, "monthly credits (overage risk - reserve floor)"),
]

_OLLAMA_DEFAULT_URL = "http://localhost:11434"


def _key_is_set(value: str | None) -> bool:
    return bool(value and value.strip() and "your-" not in value.lower())


def ollama_status(base_url: str | None = None, *, timeout: float = 0.5) -> tuple[bool, str]:
    """Probe a local Ollama server. Returns (running, detail). Never raises.

    A short-timeout localhost call: $0, no provider involved. Isolated here so
    tests can stub it without real I/O.
    """
    url = (base_url or os.getenv("OLLAMA_HOST") or _OLLAMA_DEFAULT_URL).rstrip("/")
    try:
        import httpx

        resp = httpx.get(f"{url}/api/tags", timeout=timeout)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        names = [m.get("name", "") for m in models if isinstance(m, dict)]
        if names:
            return True, f"{len(names)} model(s): {', '.join(names[:3])}{'...' if len(names) > 3 else ''}"
        return True, "running, no models pulled (try: ollama pull llama3.1)"
    except Exception:
        return False, f"not reachable at {url} (start: ollama serve)"


def available_local_models(base_url: str | None = None, *, timeout: float = 2.0) -> list[str]:
    """Names of models the local Ollama server currently has. [] if unreachable.

    Used by the waterfall to pick an admitted model that actually exists right
    now, rather than guessing from list order or an env var. The timeout is more
    forgiving than the status probe's because a false negative here silently
    forfeits owned capacity to the metered API. Never raises.
    """
    url = (base_url or os.getenv("OLLAMA_HOST") or _OLLAMA_DEFAULT_URL).rstrip("/")
    try:
        import httpx

        resp = httpx.get(f"{url}/api/tags", timeout=timeout)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        return [m["name"] for m in models if isinstance(m, dict) and m.get("name")]
    except Exception:
        return []


def _detect_local(ollama_probe=ollama_status) -> list[CapacitySource]:
    running, detail = ollama_probe()
    return [
        CapacitySource(
            name="Ollama (local models)",
            kind=BackendKind.LOCAL,
            cost_model=CostModel.OWNED_HARDWARE,
            available=running,
            detail=detail,
            backend_id="ollama",
        )
    ]


def _detect_plan_quota(which=shutil.which) -> list[CapacitySource]:
    sources: list[CapacitySource] = []
    for name, exe, cost_model, hint in _CLI_BACKENDS:
        present = which(exe) is not None
        sources.append(
            CapacitySource(
                name=f"{name} ({exe})",
                kind=BackendKind.PLAN_QUOTA,
                # Presence-only: installed on PATH. Auth, quota window, and
                # overflow state are verified by the adapter at run time, not here.
                available=present,
                cost_model=cost_model,
                backend_id=exe,
                detail=(f"installed (auth/quota checked at run) - {hint}" if present else f"not installed - {hint}"),
            )
        )
    return sources


def _detect_metered(env=None) -> list[CapacitySource]:
    env = env if env is not None else os.environ
    sources: list[CapacitySource] = []
    for name, var in _PROVIDERS:
        configured = _key_is_set(env.get(var))
        sources.append(
            CapacitySource(
                name=name,
                kind=BackendKind.API_METERED,
                cost_model=CostModel.METERED,
                available=configured,
                backend_id=var.lower().removesuffix("_api_key"),
                detail=("API key configured" if configured else f"set {var} to enable"),
            )
        )
    return sources


def detect_capacity(*, ollama_probe=ollama_status, which=shutil.which, env=None) -> list[CapacitySource]:
    """Detect all capacity sources, cheapest-at-the-margin kind first.

    Read-only and $0: probes a local Ollama port, checks which vendor CLIs are
    on PATH, and reads provider env vars. Injectable probes keep it testable
    with no real I/O.
    """
    return _detect_local(ollama_probe) + _detect_plan_quota(which) + _detect_metered(env)
