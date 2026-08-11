"""AI-generated portrait images for domain experts.

Supports multiple image generation providers (OpenAI, Google, xAI).
Auto-detects which provider is available from environment variables.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

logger = logging.getLogger(__name__)

# The house art style every expert portrait shares, so a whole library reads as
# one coherent, branded set - the "Deepr Expert look". Override with
# ``DEEPR_PORTRAIT_STYLE`` to set your own consistent look (e.g. "flat vector,
# muted palette"); a per-run ``--style`` wins over both.
DEFAULT_PORTRAIT_STYLE = (
    "Premium vector-style portrait in a consistent 'Deepr Expert' look: "
    "sophisticated modern-scholar aesthetic like a high-end SaaS avatar; clean "
    "minimalist lines with subtle cyber-futurist tech accents; soft cinematic "
    "studio lighting with a gentle rim light; confident three-quarter angle, "
    "warm approachable expression; deep teal and indigo accent palette on a soft "
    "off-white background with a faint gradient; a small symbolic icon from the "
    "expert's own domain subtly integrated; head-and-shoulders, square and "
    "circle-crop friendly; ultra-professional and trustworthy; no logos, no "
    "clutter, no harsh shadows"
)

# Style preference env var (see ``portrait_style``).
PORTRAIT_STYLE_ENV = "DEEPR_PORTRAIT_STYLE"

# Approximate per-image cost for metered providers, used for budget
# confirmation, reservation, and ledger entries.
PORTRAIT_COST_ESTIMATE_USD = 0.04
XAI_PORTRAIT_COST_ESTIMATE_USD = 0.02

# A loopback OpenAI-compatible image endpoint is not sufficient proof of local
# execution. A proxy can retain cloud credentials and forward arbitrary model
# aliases while appearing to be local. This configuration remains visible for
# migration, but it cannot authorize execution until a supported backend has a
# stable identity and exact materialized-model attestation contract.
LOCAL_IMAGE_URL_ENV = "DEEPR_LOCAL_IMAGE_URL"

_MAX_APPEARANCE_CHARS = 600
"""Long enough for a described scene, short enough that no image model truncates it."""
METERED_IMAGE_AUTO_ENV = "DEEPR_ALLOW_METERED_IMAGE_AUTO"


def _require_attested_local_image_capacity() -> NoReturn:
    raise RuntimeError(
        "Local portrait execution is blocked because no supported image backend can prove exact local-only capacity"
    )


def default_portraits_dir() -> Path:
    """Return the canonical runtime portrait directory."""
    from deepr.config import runtime_data_path

    return runtime_data_path("portraits")


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _local_image_base_url(value: str | None = None) -> str:
    """Return the configured image endpoint only when it is owned loopback."""
    raw = os.getenv(LOCAL_IMAGE_URL_ENV, "") if value is None else value
    if not raw.strip():
        raise RuntimeError(f"{LOCAL_IMAGE_URL_ENV} is not set")

    from deepr.backends.capacity import validate_owned_local_http_url

    try:
        base_url = validate_owned_local_http_url(
            raw,
            service_name="image",
            allowed_paths=frozenset({"", "/v1"}),
        )
    except ValueError as error:
        raise RuntimeError(f"{LOCAL_IMAGE_URL_ENV} cannot be classified as local/$0: {error}") from None
    return base_url if base_url.endswith("/v1") else f"{base_url}/v1"


def portrait_cost(provider: str | None) -> float:
    """Return the bounded metered estimate, rejecting unproven local labels."""
    if provider == "local":
        _require_attested_local_image_capacity()
    if provider == "xai":
        return XAI_PORTRAIT_COST_ESTIMATE_USD
    return PORTRAIT_COST_ESTIMATE_USD


def portrait_style(override: str | None = None) -> str:
    """The consistent portrait art style: explicit override, else the
    ``DEEPR_PORTRAIT_STYLE`` preference, else the house default."""
    if override and override.strip():
        return override.strip()
    env = os.getenv(PORTRAIT_STYLE_ENV, "").strip()
    return env or DEFAULT_PORTRAIT_STYLE


def _build_prompt(
    name: str,
    domain: str | None,
    description: str | None,
    *,
    style: str | None = None,
    appearance: str | None = None,
) -> str:
    """Build an image generation prompt for one expert.

    An expert that has written its own ``appearance`` gets that, and nothing
    else describing the subject. Everything below this branch is the fallback
    for an expert with no self-account yet, and it produces a picture of the
    *field* rather than of the one holding a view about it: two experts on one
    domain come out identical apart from a hash-seeded demographic rotation,
    which is backwards for the thing a portrait is for. The rotation exists so
    the fallback is at least varied, not because varying it is the goal.

    The style clause stays constant across the library either way, so a
    self-chosen portrait still sits beside the others.
    """
    import hashlib

    if chosen := " ".join((appearance or "").split()):
        # Trailing punctuation is stripped because the expert writes a sentence
        # and the style clause is appended as another one.
        chosen = chosen[:_MAX_APPEARANCE_CHARS].rstrip(" .,;:")
        return f"{chosen}. {portrait_style(style)}. No text or watermarks."

    # Deterministic diversity based on expert name. Non-crypto: md5 is used as a stable
    # seed for portrait diversity rotation only, not for security/passwords/signatures.
    seed = int(hashlib.sha256(name.encode()).hexdigest(), 16)  # stable diversity seed (sha256)
    genders = ["woman", "man", "woman", "man", "non-binary person"]
    ethnicities = [
        "East Asian",
        "South Asian",
        "Black",
        "Latino",
        "Middle Eastern",
        "white",
        "Southeast Asian",
        "Indigenous",
        "mixed-race",
    ]
    ages = ["young", "middle-aged", "senior", "young", "middle-aged"]
    gender = genders[seed % len(genders)]
    ethnicity = ethnicities[(seed // 7) % len(ethnicities)]
    age = ages[(seed // 13) % len(ages)]

    domain_hint = domain or description or name
    return (
        f"Professional portrait of a {age} {ethnicity} {gender} who is an expert in "
        f"{domain_hint[:100]}. Confident, approachable expression. "
        f"{portrait_style(style)}. No text or watermarks."
    )


def _resolve_output_dir(output_dir: str | Path | None) -> Path:
    return Path(output_dir) if output_dir is not None else default_portraits_dir()


def _archive_existing_portrait(filepath: Path) -> Path | None:
    if not filepath.exists():
        return None
    archive_dir = filepath.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    archive_path = archive_dir / f"{filepath.stem}-{stamp}-{uuid.uuid4().hex[:8]}{filepath.suffix}"
    shutil.copy2(filepath, archive_path)
    return archive_path


def _write_portrait_file(filepath: Path, image_bytes: bytes) -> Path | None:
    archive_path = _archive_existing_portrait(filepath)
    temp_path = filepath.with_name(f".{filepath.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_bytes(image_bytes)
        temp_path.replace(filepath)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return archive_path


def detect_provider() -> str | None:
    """Return the best available image provider, cheapest-first, or None.

    A configured loopback image endpoint is rejected until its server identity
    and exact materialized model can be proven. Metered APIs are not
    auto-selected from keys by default because image generation is a separate
    money side effect. Pass ``provider="openai"``, ``provider="google"``, or
    ``provider="xai"`` for explicit paid generation, or set
    ``DEEPR_ALLOW_METERED_IMAGE_AUTO=1`` to opt into metered auto-selection.
    """
    local_image_url = os.getenv(LOCAL_IMAGE_URL_ENV, "")
    if local_image_url.strip():
        _local_image_base_url(local_image_url)
        _require_attested_local_image_capacity()
    metered_auto = _truthy_env(METERED_IMAGE_AUTO_ENV)
    if not metered_auto:
        return None
    if metered_auto and os.getenv("OPENAI_API_KEY"):
        return "openai"
    if metered_auto and (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        return "google"
    if os.getenv("XAI_API_KEY"):
        return "xai"
    return None


async def generate_portrait(
    name: str,
    domain: str | None = None,
    description: str | None = None,
    *,
    provider: str | None = None,
    style: str | None = None,
    output_dir: str | Path | None = None,
    appearance: str | None = None,
) -> str:
    """Generate a portrait image for an expert.

    Args:
        name: Expert name (used in prompt and filename).
        domain: Expert domain for prompt context.
        description: Expert description for prompt context.
        provider: Force a specific provider (openai/google/xai).
                  Auto-detected if None.
        output_dir: Directory to save the portrait image.
        appearance: How the expert says it wants to be depicted. When set, this
                    is the whole subject of the prompt and domain/description
                    are ignored, because the expert's own account of itself
                    outranks anything inferred from its topic.

    Returns:
        Relative URL path to the saved portrait (e.g. ``/portraits/my-expert.png``).

    Raises:
        RuntimeError: If no provider is available or generation fails.
    """
    provider = provider or detect_provider()
    if not provider:
        raise RuntimeError(
            "No image generator available. Pass provider='openai'/'google'/'xai' for explicit paid "
            "image generation, or set DEEPR_ALLOW_METERED_IMAGE_AUTO=1. Loopback image endpoints "
            "remain blocked until exact local-only capacity can be attested."
        )
    if provider == "local":
        _local_image_base_url()
        _require_attested_local_image_capacity()
    else:
        from deepr.experts.metered_mutation_gate import require_metered_expert_mutation

        require_metered_expert_mutation(
            "api_expert_portrait",
            safe_alternative="no attested zero-dollar portrait backend is currently available",
        )

    prompt = _build_prompt(name, domain, description, style=style, appearance=appearance)
    logger.info("Generating portrait for '%s' via %s", name, provider)

    if provider == "local":
        image_bytes = await _generate_local(prompt)
    elif provider == "openai":
        image_bytes = await _generate_openai(prompt)
    elif provider == "google":
        image_bytes = await _generate_google(prompt)
    elif provider == "xai":
        image_bytes = await _generate_xai(prompt)
    else:
        raise RuntimeError(f"Unknown provider: {provider}")

    out = _resolve_output_dir(output_dir)
    await asyncio.to_thread(out.mkdir, parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in name).strip().replace(" ", "-").lower()
    if not safe_name:
        safe_name = "portrait"
    filename = f"{safe_name}.png"
    filepath = out / filename
    archive_path = await asyncio.to_thread(_write_portrait_file, filepath, image_bytes)
    if archive_path is not None:
        logger.info("Existing portrait archived to %s before replacement", archive_path)
    logger.info("Portrait saved to %s (%d bytes)", filepath, len(image_bytes))

    return f"/portraits/{filename}"


def _self_chosen_appearance(expert_name: str) -> str:
    """How this expert says it wants to look, or "" if it has not said.

    Read here rather than taken from the caller so every path that generates a
    portrait honours it, including the batch command and anything that grows a
    portrait call later. Failures are swallowed to "": an unreadable self.json
    should fall back to the generic prompt, not stop a portrait run.
    """
    import json

    try:
        from deepr.experts.expert_layout import self_path

        path = self_path(expert_name)
        if not path.exists():
            return ""
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ImportError):
        return ""
    return str(data.get("appearance") or "") if isinstance(data, dict) else ""


async def generate_and_save_portrait(
    profile: object,
    store: object,
    *,
    provider: str | None = None,
    style: str | None = None,
    output_dir: str | Path | None = None,
) -> str:
    """Generate a portrait, attach it to ``profile``, persist via ``store``, and
    record the cost. ``store`` only needs a ``save(profile)`` method.
    """
    from deepr.experts.portrait_cost_gate import (
        record_portrait_cost,
        reserve_portrait_cost,
    )

    expert_name = str(getattr(profile, "name", "expert"))
    appearance = _self_chosen_appearance(expert_name)
    effective_provider = provider or detect_provider()
    if effective_provider == "local":
        _local_image_base_url()
        _require_attested_local_image_capacity()
    if effective_provider and effective_provider != "local":
        from deepr.experts.metered_mutation_gate import require_metered_expert_mutation

        require_metered_expert_mutation(
            "api_expert_portrait",
            safe_alternative="no attested zero-dollar portrait backend is currently available",
        )
    reservation = reserve_portrait_cost(
        expert_name=expert_name,
        provider=effective_provider,
        detect_provider=detect_provider,
        portrait_cost=portrait_cost,
    )
    effective_provider = reservation.effective_provider
    if not effective_provider:
        raise RuntimeError(
            "No image generator available. Pass provider='openai'/'google'/'xai' for explicit paid "
            "image generation, or set DEEPR_ALLOW_METERED_IMAGE_AUTO=1."
        )

    try:
        portrait_url = await generate_portrait(
            name=expert_name,
            domain=getattr(profile, "domain", None),
            description=getattr(profile, "description", None),
            provider=effective_provider,
            style=style,
            output_dir=output_dir,
            appearance=appearance,
        )
    except Exception:
        # Once generate_portrait starts, a remote provider may have accepted
        # and billed the request even if generation, decoding, or file writing
        # later fails. Settle the full reserved estimate conservatively.
        record_portrait_cost(
            expert_name=expert_name,
            reservation=reservation,
            source="experts.portraits",
            metadata={
                "outcome": "failed",
                "settlement_reason": "provider_dispatch_or_completion_uncertain",
            },
        )
        raise

    record_portrait_cost(
        expert_name=expert_name,
        reservation=reservation,
        source="experts.portraits",
        metadata={"outcome": "completed"},
    )
    profile.portrait_url = portrait_url  # type: ignore[attr-defined]
    store.save(profile)  # type: ignore[attr-defined]
    return portrait_url


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


async def _generate_openai(prompt: str) -> bytes:
    """Reject direct OpenAI image dispatch until durable lifecycle accounting ships."""
    del prompt
    raise RuntimeError("Metered portrait execution is blocked until every image call has durable accounting")


async def _generate_google(prompt: str) -> bytes:
    """Reject direct Google image dispatch until durable lifecycle accounting ships."""
    del prompt
    raise RuntimeError("Metered portrait execution is blocked until every image call has durable accounting")


async def _generate_xai(prompt: str) -> bytes:
    """Reject direct xAI image dispatch until durable lifecycle accounting ships."""
    del prompt
    raise RuntimeError("Metered portrait execution is blocked until every image call has durable accounting")


async def _generate_local(prompt: str) -> bytes:
    """Reject the legacy unverified loopback image transport before dispatch."""
    del prompt
    _local_image_base_url()
    _require_attested_local_image_capacity()
