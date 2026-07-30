"""Strict JSON-object decoding for money and authority records."""

import json
from typing import Any


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r} is not allowed")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON key {key!r} is not allowed")
        document[key] = value
    return document


def loads_strict_json_object(text: str) -> dict[str, Any]:
    """Decode one standards-compliant JSON object with unique keys."""
    document = json.loads(
        text,
        parse_constant=_reject_json_constant,
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    if not isinstance(document, dict):
        raise TypeError("JSON document must be an object")
    return document
