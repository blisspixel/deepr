"""Model-recorded origins for brief statements, never inferred on read."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

ORIGIN_LABELS = {
    "studied": "Studied sources (recorded attribution)",
    "broader_knowledge": "Broader knowledge, not established by this study",
    "reasoning": "Expert reasoning, not a source observation",
    "unattributed": "Origin not recorded",
}


@dataclass
class OrientationStatement:
    text: str
    origin: str = "unattributed"
    supported_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_orientation_statements(value: Any) -> list[OrientationStatement]:
    """Accept complete structured text only; malformed lists keep legacy prose."""
    if not isinstance(value, list):
        return []
    statements = []
    for raw in value:
        if not isinstance(raw, dict) or not isinstance(raw.get("text"), str) or not raw["text"].strip():
            return []
        origin = raw.get("origin")
        citations = raw.get("supported_by")
        statements.append(
            OrientationStatement(
                text=raw["text"].strip(),
                origin=origin if isinstance(origin, str) and origin in ORIGIN_LABELS else "unattributed",
                supported_by=[fid for fid in citations if isinstance(fid, str) and fid.strip()]
                if isinstance(citations, list)
                else [],
            )
        )
    return statements


def orientation_statements(orientation: str, statements: list[OrientationStatement]) -> list[OrientationStatement]:
    """Use labels only when they cover the displayed paragraph exactly."""
    joined = " ".join(item.text for item in statements)
    if statements and " ".join(joined.split()) == " ".join(orientation.split()):
        return statements
    return [OrientationStatement(orientation)] if orientation else []


def render_orientation(
    orientation: str,
    statements: list[OrientationStatement],
    *,
    binding: str,
    findings: dict[str, bool] | None = None,
) -> str:
    """Plain text for briefs and consultation, retaining unresolved citations."""
    lines = []
    for item in orientation_statements(orientation, statements):
        lines.append(f"{ORIGIN_LABELS.get(item.origin, ORIGIN_LABELS['unattributed'])}: {item.text}")
        if item.supported_by:
            lines.append(f"Cited findings (study binding: {binding}): {', '.join(item.supported_by)}")
            if findings is not None:
                unresolved = [fid for fid in item.supported_by if not findings.get(fid)]
                if unresolved:
                    lines.append(f"Missing or unanchored cited findings: {', '.join(unresolved)}")
        elif item.origin == "studied":
            lines.append("No supporting finding recorded; attribution is unresolved.")
    return "\n".join(lines)
