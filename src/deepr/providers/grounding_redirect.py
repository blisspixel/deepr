"""Bounded redirect resolution for Google grounding URLs."""

from __future__ import annotations

import asyncio
import logging

import httpx
import requests

from deepr.utils.pinned_http import close_pinned_response, pinned_head
from deepr.utils.security import SSRFError, resolve_safe_url_ips

logger = logging.getLogger(__name__)

GROUNDING_REDIRECT_HOST = "vertexaisearch.cloud.google.com"
GROUNDING_REDIRECT_PREFIX = "/grounding-api-redirect/"
MAX_GROUNDING_REDIRECT_HOPS = 5


async def resolve_grounding_redirect_url(url: str, timeout: float = 10.0) -> str:
    """Resolve one Google grounding redirect chain with per-hop IP pinning."""
    try:
        parsed_url = httpx.URL(url)
    except httpx.InvalidURL:
        return url
    if parsed_url.host != GROUNDING_REDIRECT_HOST or not parsed_url.path.startswith(GROUNDING_REDIRECT_PREFIX):
        return url

    try:
        current_url = url
        for redirect_count in range(MAX_GROUNDING_REDIRECT_HOPS + 1):
            try:
                response = await asyncio.to_thread(pinned_head, current_url, timeout=timeout)
            except SSRFError:
                logger.warning("SSRF: grounding redirect hop is not a public HTTP(S) target")
                return url
            try:
                if not response.is_redirect:
                    try:
                        resolve_safe_url_ips(str(response.url))
                    except SSRFError:
                        return url
                    return str(response.url)
                if redirect_count >= MAX_GROUNDING_REDIRECT_HOPS:
                    logger.warning("Grounding redirect exceeded %d hops", MAX_GROUNDING_REDIRECT_HOPS)
                    return url
                location = response.headers.get("location") or response.headers.get("Location")
                if not location:
                    logger.warning("Grounding redirect response omitted Location")
                    return url
                current_url = str(httpx.URL(current_url).join(location))
            finally:
                close_pinned_response(response)
        return url
    except (requests.RequestException, httpx.HTTPError, httpx.InvalidURL) as exc:
        logger.debug("Failed to resolve grounding redirect: %s", exc)
        return url
