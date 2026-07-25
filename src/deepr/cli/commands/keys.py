"""Provider credential visibility: `deepr keys list` and `deepr keys check`.

Every credential failure mode this command surfaces was hit in live operation
on one machine in one day: a key present but expired, a key valid for one
endpoint but not another, a fresh key shadowed by a stale exported variable
(dotenv never overrides the process environment), a misspelled variable name
that nothing would ever read, and an empty value that looked set. Each one
surfaced downstream as a misleading provider error. This command makes key
state inspectable up front, for $0.

Security posture: values are never printed. Output shows presence, a short
prefix, and length only. There is deliberately no `keys set`: secrets passed
as command arguments land in shell history, so the supported write path is
editing .env directly (see .env.example for every spot).
"""

from __future__ import annotations

import difflib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import click

from deepr.cli.colors import console, print_header

# provider -> (env var, free validation endpoint, auth style)
PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {
        "env": "OPENAI_API_KEY",
        "url": "https://api.openai.com/v1/models",
        "auth": "bearer",
    },
    "xai": {
        "env": "XAI_API_KEY",
        "url": "https://api.x.ai/v1/models",
        "auth": "bearer",
    },
    "anthropic": {
        "env": "ANTHROPIC_API_KEY",
        "url": "https://api.anthropic.com/v1/models",
        "auth": "anthropic",
    },
    "gemini": {
        "env": "GEMINI_API_KEY",
        "url": "https://generativelanguage.googleapis.com/v1beta/models",
        "auth": "goog",
    },
}

_KNOWN_ENV_NAMES = [meta["env"] for meta in PROVIDERS.values()]


def _mask(value: str) -> str:
    """Presence-only rendering: short prefix and length, never the value."""
    prefix = value[:4] if len(value) >= 8 else ""
    return f"{prefix}... ({len(value)} chars)"


def _read_env_file() -> dict[str, str]:
    """Parse .env assignments (values kept in memory only, never printed)."""
    path = Path(".env")
    if not path.exists():
        return {}
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name, value = stripped.split("=", 1)
            entries[name.strip()] = value.strip()
    return entries


def _near_miss_names(env_file: dict[str, str]) -> list[tuple[str, str]]:
    """Misspelled key-variable names that nothing will ever read."""
    suspects = []
    for name in env_file:
        if name in _KNOWN_ENV_NAMES or not name.endswith("_KEY"):
            continue
        close = difflib.get_close_matches(name, _KNOWN_ENV_NAMES, n=1, cutoff=0.8)
        if close:
            suspects.append((name, close[0]))
    return suspects


def _key_state(provider: str) -> dict[str, object]:
    """Resolve one provider's key state from .env and the process environment."""
    meta = PROVIDERS[provider]
    env_file = _read_env_file()
    file_value = env_file.get(meta["env"], "")
    process_value = os.environ.get(meta["env"], "")
    # dotenv does not override an already-exported variable, so when both exist
    # and differ, the process value is what providers will actually use.
    effective = process_value or file_value
    shadowed = bool(process_value and file_value and process_value != file_value)
    return {
        "provider": provider,
        "env_var": meta["env"],
        "present": bool(effective),
        "masked": _mask(effective) if effective else None,
        "in_env_file": bool(file_value),
        "in_process_env": bool(process_value),
        "shadowed": shadowed,
        "effective_value": effective,  # stripped before any output
    }


def _validate(provider: str, key: str) -> dict[str, object]:
    """Ping the provider's free models endpoint with the key. $0, no tokens."""
    meta = PROVIDERS[provider]
    if meta["auth"] == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        url = meta["url"]
    elif meta["auth"] == "goog":
        headers = {"x-goog-api-key": key}
        url = meta["url"]
    else:
        headers = {"Authorization": f"Bearer {key}"}
        url = meta["url"]
    # URLs come only from the hardcoded PROVIDERS table above; refuse anything
    # else so the audited urlopen below can never reach file: or custom schemes.
    if not url.startswith("https://"):
        raise ValueError(f"provider validation URL must be https: {url}")
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 - https enforced above, static table
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - https enforced above
            payload = json.load(response)
            models = payload.get("data") or payload.get("models") or []
            return {"status": "valid", "models_visible": len(models)}
    except urllib.error.HTTPError as exc:
        status = "invalid" if exc.code in (401, 403) else f"http_{exc.code}"
        return {"status": status, "http_code": exc.code}
    except Exception as exc:
        return {"status": "unreachable", "detail": str(exc)[:80]}


@click.group()
def keys():
    """Inspect and validate provider API keys without exposing them."""


@keys.command("list")
@click.option("--json", "json_output", is_flag=True, help="Machine-readable output")
def list_keys(json_output: bool):
    """Show which provider keys exist, where, and whether anything is off. $0, offline."""
    states = [_key_state(p) for p in PROVIDERS]
    near_misses = _near_miss_names(_read_env_file())
    for state in states:
        state.pop("effective_value", None)
    if json_output:
        click.echo(json.dumps({"keys": states, "suspect_names": [{"found": f, "expected": e} for f, e in near_misses]}))
        return
    print_header("Provider keys")
    for state in states:
        marker = "ok" if state["present"] else "--"
        origin = (
            "env+file(shadowed)"
            if state["shadowed"]
            else ("process env" if state["in_process_env"] else ("file .env" if state["in_env_file"] else "missing"))
        )
        console.print(
            f"  {marker:<3}{state['provider']:<10} {state['env_var']:<18} {origin:<20} {state['masked'] or ''}",
            markup=False,
        )
        if state["shadowed"]:
            console.print(
                "        warning: the exported variable differs from .env and wins; "
                "unset it for this shell to use the .env value"
            )
    for found, expected in near_misses:
        console.print(
            f"  !! suspect name {found!r} in .env; nothing reads it. Did you mean {expected!r}?", markup=False
        )
    if not any(s["present"] for s in states):
        console.print("  No provider keys found. Copy .env.example to .env and add at least one.")


@keys.command("check")
@click.option("--provider", "only", type=click.Choice(sorted(PROVIDERS)), default=None, help="Check one provider")
@click.option("--json", "json_output", is_flag=True, help="Machine-readable output")
def check_keys(only: str | None, json_output: bool):
    """Live-validate present keys against each provider's free models endpoint. $0."""
    results = []
    for provider in [only] if only else sorted(PROVIDERS):
        state = _key_state(provider)
        key = str(state.pop("effective_value", "") or "")
        if not key:
            results.append({"provider": provider, "status": "no_key", "env_var": state["env_var"]})
            continue
        outcome = _validate(provider, key)
        results.append({"provider": provider, "env_var": state["env_var"], "shadowed": state["shadowed"], **outcome})
    if json_output:
        click.echo(json.dumps({"results": results}))
        return
    print_header("Provider key check")
    for result in results:
        status = result["status"]
        extra = ""
        if status == "valid":
            extra = f"{result.get('models_visible', 0)} models visible"
        elif status == "no_key":
            extra = f"set {result['env_var']} in .env"
        elif status == "invalid":
            extra = "rejected by provider (expired, revoked, or endpoint-restricted)"
        console.print(f"  {status:<12}{result['provider']:<10} {extra}", markup=False)
        if result.get("shadowed"):
            console.print("        warning: exported variable shadows .env; the exported one was checked")
