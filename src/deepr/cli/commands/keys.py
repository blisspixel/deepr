"""Provider credential inventory: `deepr keys list`, `keys set`, and `keys check`.

Every credential failure mode this command surfaces was hit in live operation
on one machine in one day: a key present but expired, a key valid for one
endpoint but not another, a fresh key shadowed by a stale exported variable
(dotenv never overrides the process environment), a misspelled variable name
that nothing would ever read, and an empty value that looked set. Each one
surfaced downstream as a misleading provider error. This command makes key
state inspectable up front.

Security posture: values are never printed. Output shows presence, a short
prefix, and length only. `keys set` takes no argv secret: it prompts hidden
and writes `.env`. Storing a key is not spend authority. Attended metered
work still needs a budget, wallet credits, and a provider hard cap.
"""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path

import click

from deepr.cli.colors import console, print_header
from deepr.experts.maximum_charge_contract import absolute_deepr_ceiling_usd
from deepr.security.key_quarantine import QUARANTINE_PREFIX

# Provider key inventory. OpenRouter metadata may be checked; other live
# provider pings stay cost-quarantined.
PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {"env": "OPENAI_API_KEY"},
    "xai": {"env": "XAI_API_KEY"},
    "anthropic": {"env": "ANTHROPIC_API_KEY"},
    "gemini": {"env": "GEMINI_API_KEY"},
    "openrouter": {"env": "OPENROUTER_API_KEY"},
}
_MAX_ENV_BYTES = 64 * 1024
_MAX_KEY_BYTES = 512
# keys check proves the credential is live and has remaining headroom, not that
# it can cover the entire Deepr ceiling in one request.
_KEY_CHECK_HEADROOM_USD = 0.01

_KNOWN_ENV_NAMES = [meta["env"] for meta in PROVIDERS.values()]


def _mask(value: str) -> str:
    """Presence-only rendering: short prefix and length, never the value."""
    prefix = value[:4] if len(value) >= 8 else ""
    return f"{prefix}... ({len(value)} chars)"


def _cwd_env_path() -> Path:
    return Path(".env")


def _user_env_path() -> Path:
    from deepr.config import default_data_dir

    return default_data_dir() / ".env"


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse one .env file. Values stay in memory and are never printed."""
    if not path.exists():
        return {}
    if path.stat().st_size > _MAX_ENV_BYTES:
        raise click.ClickException(f"{path} is too large to read safely")
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name, value = stripped.split("=", 1)
            entries[name.strip()] = value.strip()
    return entries


def _read_env_file() -> dict[str, str]:
    """Merge user-home then cwd `.env`. Cwd wins, matching `load_dotenv` order."""
    merged = dict(_parse_env_file(_user_env_path()))
    merged.update(_parse_env_file(_cwd_env_path()))
    return merged


def _target_env_path() -> Path:
    """Write the checkout `.env` when it exists; otherwise `~/.deepr/.env`."""
    cwd = _cwd_env_path()
    if cwd.exists():
        return cwd
    return _user_env_path()


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
    """Resolve one provider's key state from .env, process env, and quarantine."""
    meta = PROVIDERS[provider]
    env_file = _read_env_file()
    file_value = env_file.get(meta["env"], "")
    process_value = os.environ.get(meta["env"], "")
    quarantined_value = os.environ.get(QUARANTINE_PREFIX + meta["env"], "")
    # dotenv does not override an already-exported variable, so when both exist
    # and differ, the process value is what providers will actually use.
    # CLI startup moves metered keys into quarantine; that copy is still the
    # credential the operator stored and must be visible to `keys check`.
    effective = process_value or quarantined_value or file_value
    shadowed = bool(process_value and file_value and process_value != file_value)
    return {
        "provider": provider,
        "env_var": meta["env"],
        "present": bool(effective),
        "masked": _mask(effective) if effective else None,
        "in_env_file": bool(file_value),
        "in_process_env": bool(process_value),
        "in_quarantine": bool(quarantined_value),
        "shadowed": shadowed,
        "effective_value": effective,  # stripped before any output
    }


def _write_env_key(name: str, value: str, *, path: Path | None = None) -> Path:
    """Replace or append one assignment without printing the secret."""
    from deepr.utils.atomic_io import atomic_write_text

    path = path or _target_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.stat().st_size > _MAX_ENV_BYTES:
            raise click.ClickException(f"{path} is too large to update safely")
        existing = path.read_text(encoding="utf-8").splitlines()
    else:
        existing = []
    lines: list[str] = []
    replaced = False
    for line in existing:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key == name:
                lines.append(f"{name}={value}")
                replaced = True
                continue
        lines.append(line)
    if not replaced:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"{name}={value}")
    atomic_write_text(path, "\n".join(lines) + "\n")
    return path


def _validate(provider: str, key: str, *, required_headroom_usd: float) -> dict[str, object]:
    """Live-check OpenRouter metadata; other providers stay cost-quarantined."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider}")
    if provider != "openrouter":
        del key
        return {"status": "blocked", "reason": "external_metadata_cost_unverified"}
    from deepr.providers.openrouter_key_controls import OpenRouterKeyControlError, inspect_openrouter_key

    ceiling = absolute_deepr_ceiling_usd()
    try:
        observation = inspect_openrouter_key(key, required_headroom_usd=required_headroom_usd)
    except OpenRouterKeyControlError as exc:
        return {"status": "invalid", "reason": str(exc), "deepr_ceiling_usd": ceiling}
    return {
        "status": "valid" if observation.control_eligible else "ineligible",
        "reason": "; ".join(observation.failures) if observation.failures else "openrouter_key_metadata",
        "control_eligible": observation.control_eligible,
        "limit_usd": observation.limit_usd,
        "limit_remaining_usd": observation.limit_remaining_usd,
        "limit_reset": observation.limit_reset,
        "required_headroom_usd": observation.required_headroom_usd,
        "deepr_ceiling_usd": ceiling,
    }


@click.group()
def keys():
    """Inspect, store, and check provider API keys without exposing them."""


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
            else (
                "process env"
                if state["in_process_env"]
                else ("quarantined" if state["in_quarantine"] else ("file .env" if state["in_env_file"] else "missing"))
            )
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
        console.print("  No provider keys found. Run `deepr keys set openrouter` or copy .env.example to .env.")


def _format_limit_summary(result: dict[str, object]) -> str:
    limit = result.get("limit_usd")
    remaining = result.get("limit_remaining_usd")
    if not isinstance(limit, (int, float)) or not isinstance(remaining, (int, float)):
        return str(result.get("reason") or "openrouter_key_metadata")
    reset = result.get("limit_reset")
    cadence = "total cap" if reset is None else str(reset)
    return f"limit ${float(limit):.2f} remaining ${float(remaining):.2f} ({cadence})"


def _check_extra(result: dict[str, object]) -> str:
    extras = {
        "valid": _format_limit_summary(result),
        "no_key": f"set {result['env_var']} in .env",
        "invalid": str(result.get("reason") or "rejected by provider (expired, revoked, or endpoint-restricted)"),
        "blocked": "external validation blocked because endpoint and proxy cost cannot be proven",
        "ineligible": str(result.get("reason") or "key metadata failed Deepr's hard-cap checks"),
    }
    return str(extras.get(str(result["status"]), ""))


@keys.command("check")
@click.option("--provider", "only", type=click.Choice(sorted(PROVIDERS)), default=None, help="Check one provider")
@click.option(
    "--required-headroom",
    type=click.FloatRange(min=0.01),
    default=None,
    help="Required remaining USD under the current key limit (default: $0.01)",
)
@click.option("--json", "json_output", is_flag=True, help="Machine-readable output")
def check_keys(only: str | None, required_headroom: float | None, json_output: bool):
    """Report OpenRouter key metadata, or that other live checks are cost-quarantined."""
    headroom = _KEY_CHECK_HEADROOM_USD if required_headroom is None else required_headroom
    results = []
    for provider in [only] if only else sorted(PROVIDERS):
        state = _key_state(provider)
        key = str(state.pop("effective_value", "") or "")
        if not key:
            results.append({"provider": provider, "status": "no_key", "env_var": state["env_var"]})
            continue
        outcome = _validate(provider, key, required_headroom_usd=headroom)
        results.append({"provider": provider, "env_var": state["env_var"], "shadowed": state["shadowed"], **outcome})
    if json_output:
        click.echo(json.dumps({"results": results}))
        return
    print_header("Provider key check")
    ceiling = absolute_deepr_ceiling_usd()
    for result in results:
        console.print(
            f"  {result['status']:<12}{result['provider']:<12} {_check_extra(result)}",
            markup=False,
        )
        _print_check_follow_up(result, ceiling=ceiling)


def _print_check_follow_up(result: dict[str, object], *, ceiling: float) -> None:
    if result.get("shadowed"):
        console.print(
            "        warning: exported OPENROUTER_API_KEY shadows .env; "
            "the exported value was checked. Unset it in this shell and in "
            "Windows User environment variables to use ~/.deepr/.env.",
            markup=False,
        )
    if result.get("status") == "ineligible" and "exceeds Deepr maximum" in str(result.get("reason") or ""):
        console.print(
            f"        Deepr ceiling in force: ${ceiling:.2f}. "
            "Run `deepr budget set 20` to persist DEEPR_MAX_SPEND_CEILING_USD "
            "in ~/.deepr/.env (max $100), then check again.",
            markup=False,
        )
    if result.get("status") == "valid" and result.get("provider") == "openrouter":
        console.print(
            f"        Deepr ceiling in force: ${ceiling:.2f}. "
            "A stored key is not spend authority. Next: "
            "`deepr budget credits add --amount 20` then "
            "`deepr budget authorize openrouter`.",
            markup=False,
        )


@keys.command("set")
@click.argument("provider", type=click.Choice(sorted(PROVIDERS)))
def set_key(provider: str) -> None:
    """Store a provider key in checkout-local `.env` via a hidden prompt.

    The secret is never accepted as a command-line argument (that lands in
    shell history). Storing a key does not spend money and does not unfreeze
    paid dispatch. Attended OpenRouter work still needs a budget, wallet
    credits, and a finite provider cap.

    EXAMPLES:
      deepr keys set openrouter
    """
    env_var = PROVIDERS[provider]["env"]
    secret = click.prompt(f"{env_var}", hide_input=True, confirmation_prompt=True, err=True)
    secret = secret.strip()
    if not secret:
        raise click.ClickException("empty keys are not stored")
    if len(secret.encode("utf-8")) > _MAX_KEY_BYTES:
        raise click.ClickException("key exceeds the stored-secret size bound")
    path = _write_env_key(env_var, secret)
    secret = ""
    print_header("Provider key stored")
    console.print(f"  wrote {env_var} to {path} (value not shown)")
    console.print("  Restart the shell command so the next `deepr` process reloads it.")
    console.print("  A stored key is optional paid capacity, not a blank cheque.")
    if provider == "openrouter":
        console.print("  Next: `deepr keys check --provider openrouter`.")
