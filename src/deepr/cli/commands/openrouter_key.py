"""Authenticated, no-inference OpenRouter key-control preview."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click
from dotenv import dotenv_values

from deepr.experts.maximum_charge_contract import ABSOLUTE_DEEPR_CEILING_USD
from deepr.providers.openrouter_key_controls import OpenRouterKeyControlError, inspect_openrouter_key
from deepr.security.key_quarantine import QUARANTINE_PREFIX

_OPENROUTER_KEY_NAME = "OPENROUTER_API_KEY"
_MAX_LOCAL_ENV_BYTES = 64 * 1024


def _read_explicit_local_key() -> tuple[str, str]:
    quarantined = os.environ.get(QUARANTINE_PREFIX + _OPENROUTER_KEY_NAME, "").strip()
    if quarantined:
        return quarantined, "quarantined_environment"
    env_path = Path.cwd() / ".env"
    try:
        if not env_path.is_file() or env_path.stat().st_size > _MAX_LOCAL_ENV_BYTES:
            return "", "unavailable"
        value = dotenv_values(dotenv_path=env_path, interpolate=False).get(_OPENROUTER_KEY_NAME)
    except (OSError, UnicodeError, ValueError):
        return "", "unavailable"
    key = value.strip() if isinstance(value, str) else ""
    return (key, "checkout_local_env") if key else ("", "unavailable")


@click.command("openrouter-key-check")
@click.option(
    "--required-headroom",
    type=click.FloatRange(min=0.01, max=ABSOLUTE_DEEPR_CEILING_USD),
    default=ABSOLUTE_DEEPR_CEILING_USD,
    show_default=True,
    help="Required remaining USD under the current key's monthly limit",
)
@click.option(
    "--from-env",
    is_flag=True,
    help="Use OPENROUTER_API_KEY from quarantine or the checkout-local .env without exporting it",
)
@click.option("--json", "json_output", is_flag=True, help="Emit the sanitized versioned observation")
def openrouter_key_check(required_headroom: float, from_env: bool, json_output: bool) -> None:
    """Inspect current-key controls without inference or dispatch authority."""
    if from_env:
        api_key, api_key_source = _read_explicit_local_key()
        if not api_key:
            raise click.ClickException(
                "No OPENROUTER_API_KEY is available in quarantine or the checkout-local .env; use the hidden prompt"
            )
    else:
        api_key = click.prompt("OpenRouter API key", hide_input=True, confirmation_prompt=False, err=True)
        api_key_source = "hidden_prompt"
    try:
        observation = inspect_openrouter_key(api_key, required_headroom_usd=required_headroom)
    except OpenRouterKeyControlError as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        api_key = ""
    payload = observation.to_dict()
    payload["api_key_source"] = api_key_source
    if json_output:
        click.echo(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False))
    else:
        click.echo(f"Control eligible: {str(observation.control_eligible).lower()}")
        click.echo(f"Monthly key limit: ${observation.limit_usd or 0.0:.2f}")
        click.echo(f"Remaining key limit: ${observation.limit_remaining_usd or 0.0:.2f}")
        click.echo(f"Required headroom: ${observation.required_headroom_usd:.2f}")
        click.echo(f"Maximum monthly limit: ${observation.maximum_monthly_limit_usd:.2f}")
        if observation.failures:
            click.echo("Failures: " + "; ".join(observation.failures))
        click.echo("Read-only key metadata: 0 inference requests, $0.00, dispatch remains blocked.")
    if not observation.control_eligible:
        raise click.exceptions.Exit(1)


__all__ = ["openrouter_key_check"]
