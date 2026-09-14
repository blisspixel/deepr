"""Lemonade as an attested local image backend.

`DEEPR_LOCAL_IMAGE_URL` stays blocked, and correctly so: a bare loopback URL is
not evidence of local execution, because a proxy listening on 127.0.0.1 can
hold cloud credentials and forward the request while looking exactly like a
local server. Nothing on the client side distinguishes the two.

Lemonade closes that specific gap, which is why it gets its own transport
rather than re-opening the generic one. Before any render, this module asks the
server two questions and refuses unless both answer:

- **Stable identity.** The base URL must pass the owned-loopback check, and the
  model listing must be served in Lemonade's documented shape.
- **Exact materialized model.** The chosen model must appear in the server's own
  listing with ``downloaded: true``, a local image ``recipe`` (stable-diffusion
  .cpp or TheNoise), and a concrete ``checkpoint`` naming a weights file. A
  cloud proxy can forward a model *alias*; it cannot truthfully report a
  materialized checkpoint that sd-cpp will load off this disk.

That is a stronger claim than the CLI transport's operator attestation, because
it is re-checked against the running server at dispatch time instead of trusted
from an environment variable. It is still not proof that the bytes were
computed locally; it is proof that the server names a local checkpoint and a
local backend for the request being made.
"""

from __future__ import annotations

import base64
import os
from typing import Any

LEMONADE_URL_ENV = "DEEPR_LEMONADE_URL"
LEMONADE_IMAGE_MODEL_ENV = "DEEPR_LEMONADE_IMAGE_MODEL"

DEFAULT_LEMONADE_URL = "http://127.0.0.1:13305"
"""Lemonade's documented default port. Overridable, still ownership-checked."""

_LOCAL_IMAGE_RECIPES = frozenset({"sd-cpp", "thenoise"})
"""Recipes that render on this machine.

An allowlist rather than "any recipe with an image default", because Lemonade
can also front cloud providers (`lemonade cloud`), and those must never be
mistaken for owned local capacity."""

_PREFERRED_MODELS = ("SDXL-Base-1.0", "Flux-2-Klein-4B", "SD-1.5")
"""Portrait-quality first, deterministic so a roster renders as one set.

Selection must not drift between runs: a roster whose portraits came from three
different checkpoints does not read as a coherent house style."""

_RENDER_TIMEOUT_S = 1800
"""Half an hour. A diffusion pass runs for minutes, and a short timeout would
kill work that was going to succeed."""

_LISTING_TIMEOUT_S = 10


def base_url(value: str | None = None) -> str:
    """Return the canonical owned-loopback Lemonade API root.

    Raises:
        RuntimeError: When the configured URL cannot be classified as local.
    """
    raw = (os.getenv(LEMONADE_URL_ENV, "") or DEFAULT_LEMONADE_URL) if value is None else value
    from deepr.backends.capacity import validate_owned_local_http_url

    try:
        checked = validate_owned_local_http_url(
            raw,
            service_name="Lemonade image",
            allowed_paths=frozenset({"", "/v1", "/api/v1"}),
        )
    except ValueError as error:
        raise RuntimeError(f"{LEMONADE_URL_ENV} cannot be classified as local/$0: {error}") from None
    if checked.endswith("/api/v1") or checked.endswith("/v1"):
        return checked
    return f"{checked}/api/v1"


def _list_models(root: str) -> list[dict[str, Any]]:
    import httpx

    response = httpx.get(f"{root}/models", timeout=_LISTING_TIMEOUT_S)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _is_attested(entry: dict[str, Any]) -> bool:
    """True when this entry names a materialized local image model.

    ``image_defaults`` also separates generators from post-processors: the
    upscaler ships with the same recipe but cannot answer a text prompt.
    """
    return bool(
        entry.get("downloaded") is True
        and str(entry.get("recipe", "")).strip().lower() in _LOCAL_IMAGE_RECIPES
        and str(entry.get("checkpoint", "")).strip()
        and isinstance(entry.get("image_defaults"), dict)
    )


def attested_model(root: str | None = None) -> tuple[str, str] | None:
    """Return ``(model_id, checkpoint)`` for the model a render would use.

    ``None`` when Lemonade is unreachable or nothing local is materialized, so
    callers fall through to the next capacity source rather than failing.
    """
    try:
        api_root = root or base_url()
        entries = _list_models(api_root)
    except Exception:
        return None

    eligible = {
        str(entry["id"]): str(entry["checkpoint"]) for entry in entries if _is_attested(entry) and entry.get("id")
    }
    if not eligible:
        return None

    requested = os.getenv(LEMONADE_IMAGE_MODEL_ENV, "").strip()
    if requested:
        # An explicit choice that is not materialized is an error worth showing,
        # not something to silently paper over with a different checkpoint.
        return (requested, eligible[requested]) if requested in eligible else None

    for candidate in _PREFERRED_MODELS:
        if candidate in eligible:
            return candidate, eligible[candidate]
    first = sorted(eligible)[0]
    return first, eligible[first]


def is_available() -> bool:
    """True when a render could run locally right now."""
    return attested_model() is not None


def render(prompt: str) -> bytes:
    """Render one prompt through Lemonade and return PNG bytes.

    Raises:
        RuntimeError: When no attested local model is available, or the server
            returns no image.
    """
    import httpx

    api_root = base_url()
    selection = attested_model(api_root)
    if selection is None:
        requested = os.getenv(LEMONADE_IMAGE_MODEL_ENV, "").strip()
        detail = (
            f"{LEMONADE_IMAGE_MODEL_ENV}={requested} is not a downloaded local image model on this Lemonade server"
            if requested
            else "no downloaded local image model is available on this Lemonade server"
        )
        raise RuntimeError(f"Lemonade image execution is blocked because {detail}")

    model, _checkpoint = selection
    response = httpx.post(
        f"{api_root}/images/generations",
        json={"model": model, "prompt": prompt, "n": 1},
        timeout=_RENDER_TIMEOUT_S,
    )
    response.raise_for_status()
    payload = response.json()
    entries = payload.get("data") if isinstance(payload, dict) else None
    encoded = (
        entries[0].get("b64_json") if isinstance(entries, list) and entries and isinstance(entries[0], dict) else None
    )
    if not encoded:
        raise RuntimeError(f"Lemonade returned no image for model {model}")
    return base64.b64decode(encoded)


__all__ = [
    "LEMONADE_IMAGE_MODEL_ENV",
    "LEMONADE_URL_ENV",
    "attested_model",
    "base_url",
    "is_available",
    "render",
]
