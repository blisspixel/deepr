"""AI-generated portrait images for domain experts.

Supports multiple image generation providers (OpenAI, Google, xAI).
Auto-detects which provider is available from environment variables.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from pathlib import Path

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

# Approximate per-image cost for the metered providers, used for budget
# confirmation and ledger entries. Local generation is $0 (see portrait_cost).
PORTRAIT_COST_ESTIMATE_USD = 0.04

# Local image generation (capability-adaptive, $0): point this at a local
# diffusion server that speaks the OpenAI Images API (e.g. ComfyUI/SwarmUI/a
# FLUX server with an OpenAI-compatible shim at /v1). Plain Ollama does NOT
# generate images, so it is not an option here. When set, it is preferred over
# metered providers (cheapest-first, like the research capacity waterfall).
LOCAL_IMAGE_URL_ENV = "DEEPR_LOCAL_IMAGE_URL"
LOCAL_IMAGE_MODEL_ENV = "DEEPR_LOCAL_IMAGE_MODEL"
DEFAULT_LOCAL_IMAGE_MODEL = "flux"


def portrait_cost(provider: str | None) -> float:
    """Per-image cost for a provider: $0 for local, the metered estimate else."""
    return 0.0 if provider == "local" else PORTRAIT_COST_ESTIMATE_USD


def portrait_style(override: str | None = None) -> str:
    """The consistent portrait art style: explicit override, else the
    ``DEEPR_PORTRAIT_STYLE`` preference, else the house default."""
    if override and override.strip():
        return override.strip()
    env = os.getenv(PORTRAIT_STYLE_ENV, "").strip()
    return env or DEFAULT_PORTRAIT_STYLE


def _build_prompt(name: str, domain: str | None, description: str | None, *, style: str | None = None) -> str:
    """Build an image generation prompt from expert metadata.

    Uses a seeded rotation of gender, ethnicity, and age to ensure diverse
    representation across generated portraits, while the *style* clause stays
    constant across the library (``portrait_style``) for a coherent look.
    """
    import hashlib

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


def detect_provider() -> str | None:
    """Return the best available image provider, cheapest-first, or None.

    Local (a configured diffusion endpoint) wins over metered APIs so a user
    with a GPU generates portraits at $0.
    """
    if os.getenv(LOCAL_IMAGE_URL_ENV):
        return "local"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
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
    output_dir: str | Path = "data/portraits",
) -> str:
    """Generate a portrait image for an expert.

    Args:
        name: Expert name (used in prompt and filename).
        domain: Expert domain for prompt context.
        description: Expert description for prompt context.
        provider: Force a specific provider (openai/google/xai).
                  Auto-detected if None.
        output_dir: Directory to save the portrait image.

    Returns:
        Relative URL path to the saved portrait (e.g. ``/portraits/my-expert.png``).

    Raises:
        RuntimeError: If no provider is available or generation fails.
    """
    provider = provider or detect_provider()
    if not provider:
        raise RuntimeError(
            "No image generator available. Set DEEPR_LOCAL_IMAGE_URL (a local FLUX/ComfyUI "
            "OpenAI-images endpoint, $0) or OPENAI_API_KEY / GEMINI_API_KEY / XAI_API_KEY."
        )

    prompt = _build_prompt(name, domain, description, style=style)
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

    # Save to disk (non-blocking mkdir)
    out = Path(output_dir)
    await asyncio.to_thread(out.mkdir, parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in name).strip().replace(" ", "-").lower()
    if not safe_name:
        safe_name = "portrait"
    filename = f"{safe_name}.png"
    filepath = out / filename
    filepath.write_bytes(image_bytes)
    logger.info("Portrait saved to %s (%d bytes)", filepath, len(image_bytes))

    return f"/portraits/{filename}"


async def generate_and_save_portrait(
    profile: object,
    store: object,
    *,
    provider: str | None = None,
    style: str | None = None,
    output_dir: str | Path = "data/portraits",
) -> str:
    """Generate a portrait, attach it to ``profile``, persist via ``store``, and
    record the (best-effort) cost. Shared by the CLI and web so both behave
    identically. ``store`` only needs a ``save(profile)`` method.
    """
    portrait_url = await generate_portrait(
        name=profile.name,
        domain=getattr(profile, "domain", None),
        description=getattr(profile, "description", None),
        provider=provider,
        style=style,
        output_dir=output_dir,
    )
    profile.portrait_url = portrait_url  # type: ignore[attr-defined]
    store.save(profile)  # type: ignore[attr-defined]

    effective_provider = provider or detect_provider()
    try:  # best-effort: the portrait already exists; ledger failure must not break it
        from deepr.experts.cost_safety import get_cost_safety_manager

        get_cost_safety_manager().record_cost(
            session_id=f"portrait_{getattr(profile, 'name', 'expert')}",
            operation_type="portrait_generation",
            actual_cost=portrait_cost(effective_provider),
            provider=effective_provider or "auto",
            source="experts.portraits",
            metadata={"expert": getattr(profile, "name", "")},
        )
    except Exception as cost_exc:
        logger.debug("Portrait cost ledger entry skipped: %s", cost_exc)

    return portrait_url


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


async def _generate_openai(prompt: str) -> bytes:
    """Generate via OpenAI gpt-image-1 (Images API)."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    result = await client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        n=1,
        size="1024x1024",
    )

    b64 = result.data[0].b64_json
    if b64:
        return base64.b64decode(b64)
    # Fallback: download from URL if b64 not available
    url = result.data[0].url
    if url:
        import httpx

        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.get(url)
            resp.raise_for_status()
            return resp.content
    raise RuntimeError("OpenAI returned neither base64 nor URL image data")


async def _generate_google(prompt: str) -> bytes:
    """Generate via Google Imagen API."""
    import httpx

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("No Google API key found")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={api_key}"

    async with httpx.AsyncClient(timeout=120) as http:
        resp = await http.post(
            url,
            json={
                "instances": [{"prompt": prompt}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": "1:1",
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()

    predictions = data.get("predictions", [])
    if not predictions:
        raise RuntimeError("Google Imagen returned no predictions")
    b64 = predictions[0].get("bytesBase64Encoded", "")
    if not b64:
        raise RuntimeError("Google Imagen returned empty image data")
    return base64.b64decode(b64)


async def _generate_xai(prompt: str) -> bytes:
    """Generate via xAI Grok image generation."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=os.getenv("XAI_API_KEY"),
        base_url="https://api.x.ai/v1",
    )

    result = await client.images.generate(
        model="grok-2-image",
        prompt=prompt,
        n=1,
        response_format="b64_json",
    )

    b64 = result.data[0].b64_json
    if not b64:
        raise RuntimeError("xAI returned empty image data")
    return base64.b64decode(b64)


async def _generate_local(prompt: str) -> bytes:
    """Generate via a local OpenAI-Images-compatible endpoint ($0, on your GPU).

    Point ``DEEPR_LOCAL_IMAGE_URL`` at a local diffusion server exposing the
    OpenAI Images API (ComfyUI/SwarmUI/a FLUX server with a ``/v1`` shim);
    ``DEEPR_LOCAL_IMAGE_MODEL`` selects the model (default ``flux``). Nothing is
    billed - it hits your own hardware. Plain Ollama cannot do this (it has no
    image-generation models), so a diffusion server is required.
    """
    from openai import AsyncOpenAI

    base_url = os.getenv(LOCAL_IMAGE_URL_ENV, "").rstrip("/")
    if not base_url:
        raise RuntimeError(f"{LOCAL_IMAGE_URL_ENV} is not set")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    client = AsyncOpenAI(api_key="local", base_url=base_url)
    result = await client.images.generate(
        model=os.getenv(LOCAL_IMAGE_MODEL_ENV, DEFAULT_LOCAL_IMAGE_MODEL),
        prompt=prompt,
        n=1,
        response_format="b64_json",
    )
    b64 = result.data[0].b64_json
    if not b64:
        raise RuntimeError("Local image endpoint returned empty image data")
    return base64.b64decode(b64)
