"""Capacity-source detection (read-only, $0).

Reports what research capacity is available to the operator across three
kinds - owned/local hardware, plan-quota CLIs, and metered APIs - so the
operator (and, later, the waterfall router) can prefer capacity they already
pay for over per-call API spend. Detection only: this never runs research and
never spends. Design: docs/design/capacity-waterfall.md.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast
from urllib.parse import SplitResult, urlsplit


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
        CostModel.METERED,
        "GitHub plan, monthly AI credits (metered per token; overflow admin-capped)",
    ),
    ("Cursor CLI", "cursor-agent", CostModel.CREDIT_POOL, "Cursor plan; Auto model free, frontier models metered"),
    (
        "OpenCode CLI",
        "opencode",
        CostModel.CREDIT_POOL,
        "BYO provider; route to an OAuth/subscription or local model for $0/prepaid",
    ),
    ("Antigravity", "agy", CostModel.CALENDAR_WINDOW, "Google AI plan, weekly compute caps"),
    ("Kiro CLI", "kiro-cli", CostModel.CALENDAR_WINDOW, "monthly credits (overage risk - reserve floor)"),
    (
        "Grok Build",
        "grok",
        CostModel.CREDIT_POOL,
        "SuperGrok/X Premium+ subscription; headless use is ToS gray-zone",
    ),
]

_OLLAMA_DEFAULT_URL = "http://localhost:11434"
_STABLE_OLLAMA_CLOUD_DISABLE_SOURCES = frozenset({"config", "both"})


def _parse_owned_local_http_url(value: str, label: str) -> SplitResult:
    raw = value.strip()
    if not raw:
        raise ValueError(f"{label} URL cannot be empty")
    candidate = raw if "://" in raw else f"http://{raw}"
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise ValueError(f"{label} URL is invalid") from exc
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"{label} capacity requires an http or https URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} URL cannot contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{label} URL cannot contain a query or fragment")
    return parsed


def _owned_loopback_address(
    parsed: SplitResult,
    label: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    host = (parsed.hostname or "").lower()
    if host == "localhost":
        host = "127.0.0.1"
    if "%" in host:
        raise ValueError(f"{label} capacity requires an unscoped literal loopback host")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError(
            f"{label} capacity requires a literal loopback host; remote endpoints need explicit cost attestation"
        ) from exc
    if not address.is_loopback:
        raise ValueError(f"{label} capacity requires a loopback host; remote endpoints need explicit cost attestation")
    return address


def validate_owned_local_http_url(
    value: str,
    *,
    service_name: str,
    allowed_paths: frozenset[str] | None = frozenset({""}),
) -> str:
    """Return a canonical, DNS-free loopback URL for owned capacity.

    ``allowed_paths=None`` permits any path while retaining the ownership and
    URL-shape checks. Callers should otherwise enumerate their accepted roots.
    """
    label = f"Owned local {service_name}"
    parsed = _parse_owned_local_http_url(value, label)
    path = parsed.path.rstrip("/")
    if allowed_paths is not None and path not in allowed_paths:
        raise ValueError(f"{label} URL path is not allowed")
    address = _owned_loopback_address(parsed, label)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} URL has an invalid port") from exc

    rendered_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return f"{parsed.scheme}://{rendered_host}{f':{port}' if port is not None else ''}{path}"


def validate_owned_local_ollama_url(value: str) -> str:
    """Return a canonical loopback-only Ollama endpoint."""
    return validate_owned_local_http_url(value, service_name="Ollama")


def validate_owned_local_ollama_cloud_status(payload: Mapping[str, Any]) -> None:
    """Require stable server-side proof that Ollama cloud access is disabled."""
    cloud = payload.get("cloud")
    if (
        not isinstance(cloud, Mapping)
        or cloud.get("disabled") is not True
        or cloud.get("source") not in _STABLE_OLLAMA_CLOUD_DISABLE_SOURCES
    ):
        raise ValueError(
            "Owned local Ollama requires cloud.disabled=true from persistent config; "
            "set disable_ollama_cloud=true in server.json and restart Ollama"
        )


def select_materialized_local_ollama_model(
    entries: list[Any],
    *,
    requested: str | None,
) -> Mapping[str, Any]:
    """Select an exact local GGUF inventory entry with no remote provenance."""
    requested_name = (requested or "").strip()
    candidates = [cast(Mapping[str, Any], entry) for entry in entries if isinstance(entry, Mapping)]
    if requested_name:
        candidates = [entry for entry in candidates if entry.get("name") == requested_name]
        if not candidates:
            raise ValueError("requested model is not an exact entry in the local Ollama inventory")
    for entry in candidates:
        name = entry.get("name")
        size = entry.get("size")
        digest = entry.get("digest")
        details = entry.get("details")
        if not isinstance(name, str) or not name.strip() or name != entry.get("model"):
            continue
        if name.casefold().endswith(":cloud"):
            continue
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            continue
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            continue
        if not isinstance(details, Mapping) or str(details.get("format", "")).casefold() != "gguf":
            continue
        if any(
            value is not None and value is not False and value != ""
            for value in (entry.get(field) for field in ("cloud", "remote", "provider", "url"))
        ):
            continue
        return entry
    raise ValueError("no fully materialized local GGUF model satisfies the zero-cost authority gate")


def _key_is_set(value: str | None) -> bool:
    return bool(value and value.strip() and "your-" not in value.lower())


def ollama_status(base_url: str | None = None, *, timeout: float = 0.5) -> tuple[bool, str]:
    """Probe a local Ollama server. Returns (running, detail). Never raises.

    A short-timeout localhost call: $0, no provider involved. Isolated here so
    tests can stub it without real I/O.
    """
    try:
        url = validate_owned_local_ollama_url(base_url or os.getenv("OLLAMA_HOST") or _OLLAMA_DEFAULT_URL)
    except ValueError as error:
        return False, str(error)
    try:
        import httpx

        with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            resp = client.get(f"{url}/api/tags")
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
    try:
        url = validate_owned_local_ollama_url(base_url or os.getenv("OLLAMA_HOST") or _OLLAMA_DEFAULT_URL)
    except ValueError:
        return []
    try:
        import httpx

        with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            resp = client.get(f"{url}/api/tags")
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
