"""AI-generated portrait images for domain experts.

Supports multiple image generation providers (OpenAI, Google, xAI).
Auto-detects which provider is available from environment variables.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _build_prompt(name: str, domain: str | None, description: str | None) -> str:
    """Build an image generation prompt from expert metadata."""
    parts = [
        "Professional portrait of an expert",
    ]
    if domain:
        parts.append(f"specializing in {domain}")
    if description:
        parts.append(f"who {description[:120]}")
    parts.append(
        "— stylized digital illustration, clean background, "
        "warm lighting, academic/professional aesthetic, "
        "suitable as an avatar. No text or watermarks."
    )
    return ", ".join(parts)


def detect_provider() -> str | None:
    """Return the first available image-generation provider, or None."""
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
        raise RuntimeError("No image generation API key found. Set OPENAI_API_KEY, GEMINI_API_KEY, or XAI_API_KEY.")

    prompt = _build_prompt(name, domain, description)
    logger.info("Generating portrait for '%s' via %s", name, provider)

    if provider == "openai":
        image_bytes = await _generate_openai(prompt)
    elif provider == "google":
        image_bytes = await _generate_google(prompt)
    elif provider == "xai":
        image_bytes = await _generate_xai(prompt)
    else:
        raise RuntimeError(f"Unknown provider: {provider}")

    # Save to disk
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in name).strip().replace(" ", "-").lower()
    if not safe_name:
        safe_name = "portrait"
    filename = f"{safe_name}.png"
    filepath = out / filename
    filepath.write_bytes(image_bytes)
    logger.info("Portrait saved to %s (%d bytes)", filepath, len(image_bytes))

    return f"/portraits/{filename}"


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
        response_format="b64_json",
    )

    b64 = result.data[0].b64_json
    if not b64:
        raise RuntimeError("OpenAI returned empty image data")
    return base64.b64decode(b64)


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
