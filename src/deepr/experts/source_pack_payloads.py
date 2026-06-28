"""Payload normalization helpers for source-pack compiler artifacts."""

from __future__ import annotations

from typing import Any


def source_pack_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    source_pack = payload.get("source_pack")
    if isinstance(source_pack, dict):
        return source_pack
    return payload


def sources_from_pack(source_pack: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sources = source_pack.get("sources", [])
    if not isinstance(raw_sources, list):
        return []
    return [source for source in raw_sources if isinstance(source, dict)]


def artifact_generated_at(payload: dict[str, Any], source_pack: dict[str, Any]) -> str:
    for key, source in (("started_at", payload), ("generated_at", source_pack), ("generated_at", payload)):
        value = source.get(key)
        if value:
            return str(value)
    return "1970-01-01T00:00:00+00:00"


__all__ = ["artifact_generated_at", "source_pack_from_payload", "sources_from_pack"]
