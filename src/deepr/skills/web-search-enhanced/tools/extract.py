"""Structured extraction from research text."""

from __future__ import annotations

import re
from typing import Any


def structured_extract(text: str, extract_type: str = "all") -> dict[str, Any]:
    """Extract structured facts, entities, and relationships from text.

    Args:
        text: Research text to analyze
        extract_type: What to extract — "facts", "entities", "relationships", or "all"

    Returns:
        Dictionary with extracted data
    """
    result: dict[str, Any] = {}

    if extract_type in ("facts", "all"):
        result["facts"] = _extract_facts(text)

    if extract_type in ("entities", "all"):
        result["entities"] = _extract_entities(text)

    if extract_type in ("relationships", "all"):
        result["relationships"] = _extract_relationships(text)

    result["source_length"] = len(text)
    result["extract_type"] = extract_type
    return result


def _extract_facts(text: str) -> list[dict[str, str]]:
    """Extract factual statements from text."""
    facts = []
    sentences = re.split(r"[.!?]\s+", text)

    fact_indicators = [
        "is",
        "are",
        "was",
        "were",
        "has",
        "have",
        "had",
        "shows",
        "found",
        "reported",
        "according",
        "data",
        "percent",
        "%",
        "million",
        "billion",
        "increased",
        "decreased",
        "grew",
        "declined",
    ]

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or len(sentence) < 20:
            continue
        lower = sentence.lower()
        if any(indicator in lower for indicator in fact_indicators):
            facts.append(
                {
                    "statement": sentence[:500],
                    "type": "quantitative" if any(c.isdigit() for c in sentence) else "qualitative",
                }
            )

    return facts[:50]  # Cap at 50 facts


def _extract_entities(text: str) -> list[dict[str, str]]:
    """Extract named entities from text using pattern matching."""
    entities = []
    seen = set()

    # Capitalized multi-word names (simple NER)
    for match in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text):
        name = match.group(1)
        if name not in seen and len(name) > 3:
            seen.add(name)
            entities.append({"name": name, "type": "named_entity"})

    # Numbers with units
    for match in re.finditer(r"(\$[\d,.]+\s*(?:million|billion|trillion)?|\d+(?:\.\d+)?%)", text):
        value = match.group(1)
        if value not in seen:
            seen.add(value)
            entities.append({"name": value, "type": "metric"})

    return entities[:100]


def _extract_relationships(text: str) -> list[dict[str, str]]:
    """Extract entity relationships from text."""
    relationships = []

    # Simple pattern: X acquired/partnered/invested Y
    patterns = [
        (r"(\b[A-Z]\w+)\s+(?:acquired|bought|purchased)\s+(\b[A-Z]\w+)", "acquired"),
        (r"(\b[A-Z]\w+)\s+(?:partnered|collaborated)\s+(?:with\s+)?(\b[A-Z]\w+)", "partnered_with"),
        (r"(\b[A-Z]\w+)\s+(?:invested|funded)\s+(?:in\s+)?(\b[A-Z]\w+)", "invested_in"),
        (r"(\b[A-Z]\w+)\s+(?:competes|competing)\s+(?:with\s+)?(\b[A-Z]\w+)", "competes_with"),
    ]

    for pattern, rel_type in patterns:
        for match in re.finditer(pattern, text):
            relationships.append(
                {
                    "source": match.group(1),
                    "target": match.group(2),
                    "type": rel_type,
                }
            )

    return relationships[:50]
